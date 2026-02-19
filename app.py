import os
import math
import sqlite3
from datetime import datetime

from flask import Flask, render_template, request, redirect, session, abort, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "tayta_pancho_secret_super_seguro")

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "hermandad.db")

# Carpeta para imágenes subidas desde el panel
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Límite de tamaño por seguridad (ajústalo si deseas)
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024  # 6 MB

DEFAULT_PROVINCIA = "Pomabamba"
DEFAULT_PER_PAGE = 8
MAX_PER_PAGE = 30

# Cambia esto por tu transmisión real cuando quieras
YOUTUBE_LIVE_EMBED = "https://www.youtube.com/embed/Hmok4xM2SCs"


# -------------------------
# Helpers DB
# -------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# -------------------------
# Helpers utilitarios
# -------------------------
MESES_PE = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
    7: "jul", 8: "ago", 9: "set", 10: "oct", 11: "nov", 12: "dic"
}

def fecha_pe(value: str) -> str:
    """Formato amigable es-PE, sin depender de locale del servidor."""
    if not value:
        return ""
    try:
        # Acepta 'YYYY-MM-DD HH:MM' o ISO con 'T'
        v = value.replace("T", " ").strip()
        if len(v) == 16:
            dt = datetime.strptime(v, "%Y-%m-%d %H:%M")
        else:
            dt = datetime.strptime(v[:19], "%Y-%m-%d %H:%M:%S")
        return f"{dt.day:02d} {MESES_PE.get(dt.month, dt.month)} {dt.year} · {dt.strftime('%H:%M')}"
    except Exception:
        return value

app.jinja_env.filters["fecha_pe"] = fecha_pe


def now_lima_str() -> str:
    """Devuelve fecha/hora estilo 'YYYY-MM-DD HH:MM'."""
    try:
        from zoneinfo import ZoneInfo
        dt = datetime.now(ZoneInfo("America/Lima"))
    except Exception:
        dt = datetime.utcnow()
    return dt.strftime("%Y-%m-%d %H:%M")


def parse_int(value, default=1, min_val=1, max_val=None) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    if n < min_val:
        n = min_val
    if max_val is not None and n > max_val:
        n = max_val
    return n


def allowed_file(filename: str) -> bool:
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def resumen_auto(contenido: str, max_chars: int = 180) -> str:
    texto = (contenido or "").strip().replace("\r", "")
    if len(texto) <= max_chars:
        return texto
    return texto[:max_chars].rstrip() + "…"


def normalize_image_path(path: str):
    """
    Permite rutas relativas seguras dentro de /static:
    - img/...
    - uploads/...
    Si no cumple, retorna None.
    """
    if not path:
        return None
    p = path.strip().lstrip("/")
    if p.startswith("img/") or p.startswith("uploads/"):
        return p
    return None


def build_filters(provincia: str, q: str):
    clauses = []
    params = []

    prov = (provincia or "").strip()
    if prov and prov.lower() != "todos":
        clauses.append("provincia = ?")
        params.append(prov)

    query = (q or "").strip()
    if query:
        like = f"%{query}%"
        clauses.append(
            "(titulo LIKE ? COLLATE NOCASE OR resumen LIKE ? COLLATE NOCASE OR contenido LIKE ? COLLATE NOCASE)"
        )
        params.extend([like, like, like])

    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where_sql, params


# -------------------------
# DB init + upgrade (compat)
# -------------------------
def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS avisos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            resumen TEXT NOT NULL,
            contenido TEXT NOT NULL,
            provincia TEXT NOT NULL DEFAULT 'Pomabamba',
            imagen TEXT,
            created_at TEXT NOT NULL,
            featured INTEGER NOT NULL DEFAULT 0
        )
    """)

    c.execute("CREATE INDEX IF NOT EXISTS idx_avisos_provincia_created_at ON avisos (provincia, created_at, id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_avisos_featured ON avisos (provincia, featured, created_at, id)")

    conn.commit()
    conn.close()


def upgrade_db():
    """
    Migra una DB antigua (si existía) agregando columnas faltantes.
    No rompe datos existentes.
    """
    conn = get_conn()
    c = conn.cursor()

    c.execute("PRAGMA table_info(avisos)")
    cols = [row["name"] for row in c.fetchall()]

    def add_col(name: str, coldef: str):
        nonlocal cols
        if name not in cols:
            c.execute(f"ALTER TABLE avisos ADD COLUMN {name} {coldef}")
            c.execute("PRAGMA table_info(avisos)")
            cols = [row["name"] for row in c.fetchall()]

    # Si tu tabla era antigua (solo titulo/contenido), agregamos lo faltante.
    add_col("resumen", "TEXT")
    add_col("provincia", "TEXT")
    add_col("imagen", "TEXT")
    add_col("created_at", "TEXT")
    add_col("featured", "INTEGER")

    # Backfill seguro
    c.execute("UPDATE avisos SET provincia = COALESCE(NULLIF(provincia,''), ?) ", (DEFAULT_PROVINCIA,))
    c.execute("UPDATE avisos SET featured = COALESCE(featured, 0)")
    c.execute("UPDATE avisos SET created_at = COALESCE(NULLIF(created_at,''), ?) ", (now_lima_str(),))
    # resumen: si está vacío, sacar del contenido
    c.execute("""
        UPDATE avisos
        SET resumen = COALESCE(NULLIF(resumen,''), substr(COALESCE(contenido,''), 1, 180))
    """)

    conn.commit()
    conn.close()


def crear_director_si_no_existe():
    """
    Crea usuario director si no existe.
    Cambia el password en producción (idealmente por variable de entorno).
    """
    username = os.environ.get("DIRECTOR_USER", "director")
    password = os.environ.get("DIRECTOR_PASSWORD", "1234")

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username=?", (username,))
    if not c.fetchone():
        c.execute(
            "INSERT INTO users (username, password, role) VALUES (?,?,?)",
            (username, generate_password_hash(password), "director")
        )
        conn.commit()
    conn.close()


init_db()
upgrade_db()
crear_director_si_no_existe()


# -------------------------
# Rutas públicas
# -------------------------
@app.route("/")
def index():
    provincia = (request.args.get("provincia", DEFAULT_PROVINCIA) or DEFAULT_PROVINCIA).strip()
    q = (request.args.get("q", "") or "").strip()
    page = parse_int(request.args.get("page"), default=1, min_val=1)
    per_page = parse_int(request.args.get("per_page"), default=DEFAULT_PER_PAGE, min_val=1, max_val=MAX_PER_PAGE)

    where_sql, params = build_filters(provincia, q)

    select_cols = "id, titulo, resumen, contenido, provincia, imagen, created_at, featured"

    conn = get_conn()
    c = conn.cursor()

    total_found = c.execute(f"SELECT COUNT(*) AS c FROM avisos {where_sql}", params).fetchone()["c"]

    # 1) Buscar destacada
    feat_where_sql = where_sql + (" AND " if where_sql else "WHERE ") + "featured = 1"
    featured = c.execute(
        f"SELECT {select_cols} FROM avisos {feat_where_sql} ORDER BY created_at DESC, id DESC LIMIT 1",
        params
    ).fetchone()

    # 2) Si no hay destacada, caer a la más reciente
    if featured is None:
        featured = c.execute(
            f"SELECT {select_cols} FROM avisos {where_sql} ORDER BY created_at DESC, id DESC LIMIT 1",
            params
        ).fetchone()

    featured_id = featured["id"] if featured else None

    # Lista (excluye featured para no duplicar)
    list_where_sql = where_sql
    list_params = list(params)

    if featured_id:
        list_where_sql = where_sql + (" AND " if where_sql else "WHERE ") + "id != ?"
        list_params.append(featured_id)

    total_list = c.execute(f"SELECT COUNT(*) AS c FROM avisos {list_where_sql}", list_params).fetchone()["c"]
    total_pages = max(1, math.ceil(total_list / per_page)) if per_page else 1
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    items = c.execute(
        f"""
        SELECT {select_cols}
        FROM avisos
        {list_where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        list_params + [per_page, offset]
    ).fetchall()

    conn.close()

    # Meta + OG
    site_title = "Noticias Tayta Pancho"
    page_title = f"{site_title} | {provincia}"
    meta_desc = f"Noticias y comunicados de {provincia}. Información local y cobertura en video."

    # OG image: destacada si existe, si no logo
    og_image_path = "img/logo.png"
    if featured and featured["imagen"]:
        og_image_path = featured["imagen"]

    og = {
        "title": page_title,
        "description": meta_desc,
        "type": "website",
        "url": request.url,
        "image": url_for("static", filename=og_image_path, _external=True),
        "site_name": site_title,
        "locale": "es_PE",
    }

    return render_template(
        "index.html",
        provincia=provincia,
        q=q,
        page=page,
        per_page=per_page,
        total_found=total_found,
        total_pages=total_pages,
        featured=featured,
        items=items,
        og=og,
        meta_desc=meta_desc,
        youtube_embed=YOUTUBE_LIVE_EMBED
    )


@app.route("/noticia/<int:noticia_id>")
def noticia(noticia_id: int):
    conn = get_conn()
    c = conn.cursor()

    n = c.execute(
        """
        SELECT id, titulo, resumen, contenido, provincia, imagen, created_at, featured
        FROM avisos
        WHERE id=?
        """,
        (noticia_id,)
    ).fetchone()

    if not n:
        conn.close()
        abort(404)

    related = c.execute(
        """
        SELECT id, titulo, resumen, provincia, imagen, created_at
        FROM avisos
        WHERE provincia=? AND id != ?
        ORDER BY created_at DESC, id DESC
        LIMIT 6
        """,
        (n["provincia"], noticia_id)
    ).fetchall()

    conn.close()

    site_title = "Noticias Tayta Pancho"
    page_title = f"{n['titulo']} | {site_title}"
    meta_desc = (n["resumen"] or resumen_auto(n["contenido"], 180))[:180]

    og_image_path = n["imagen"] if n["imagen"] else "img/logo.png"

    og = {
        "title": page_title,
        "description": meta_desc,
        "type": "article",
        "url": request.url,
        "image": url_for("static", filename=og_image_path, _external=True),
        "site_name": site_title,
        "locale": "es_PE",
    }

    return render_template(
        "noticia.html",
        n=n,
        related=related,
        og=og,
        meta_desc=meta_desc,
        youtube_embed=YOUTUBE_LIVE_EMBED
    )


# -------------------------
# Login y panel
# -------------------------
@app.route("/acceso-interno", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        conn = get_conn()
        c = conn.cursor()
        user = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user"] = user["username"]
            session["role"] = user["role"]
            return redirect("/panel")

        flash("Credenciales incorrectas.", "danger")
        return redirect("/acceso-interno")

    return render_template("login.html")


@app.route("/panel", methods=["GET", "POST"])
def panel():
    if "user" not in session:
        return redirect("/acceso-interno")

    provincias_sugeridas = [
        "Pomabamba",
        "Huari",
        "Asunción",
        "Carlos Fermín Fitzcarrald",
        "Áncash",
        "Todos",
    ]

    if request.method == "POST" and session.get("role") == "director":
        provincia = (request.form.get("provincia") or DEFAULT_PROVINCIA).strip()
        titulo = (request.form.get("titulo") or "").strip()
        resumen = (request.form.get("resumen") or "").strip()
        contenido = (request.form.get("contenido") or "").strip()
        featured = 1 if request.form.get("featured") == "on" else 0

        imagen = None

        # 1) Subida de archivo
        f = request.files.get("imagen_file")
        if f and f.filename:
            if not allowed_file(f.filename):
                flash("Formato no permitido. Usa PNG, JPG, JPEG, WEBP o GIF.", "danger")
                return redirect(url_for("panel"))

            safe_name = secure_filename(f.filename)
            stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            final_name = f"{stamp}-{safe_name}"
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], final_name)
            f.save(save_path)
            imagen = f"uploads/{final_name}"

        # 2) O ruta manual dentro de /static/img o /static/uploads
        else:
            imagen_path = (request.form.get("imagen_path") or "").strip()
            imagen = normalize_image_path(imagen_path)

        if not titulo or not contenido:
            flash("Falta título o contenido.", "danger")
            return redirect(url_for("panel"))

        if not resumen:
            resumen = resumen_auto(contenido)

        created_at = now_lima_str()

        conn = get_conn()
        c = conn.cursor()

        # Si se marca featured, apagamos otras featured de la misma provincia
        if featured and provincia and provincia.lower() != "todos":
            c.execute("UPDATE avisos SET featured=0 WHERE provincia=?", (provincia,))

        c.execute(
            """
            INSERT INTO avisos (titulo, resumen, contenido, provincia, imagen, created_at, featured)
            VALUES (?,?,?,?,?,?,?)
            """,
            (titulo, resumen, contenido, provincia, imagen, created_at, featured)
        )

        conn.commit()
        conn.close()

        flash("Noticia publicada correctamente.", "success")
        return redirect(url_for("index", provincia=provincia))

    # Vista panel: últimas publicaciones
    conn = get_conn()
    posts = conn.execute(
        """
        SELECT id, titulo, provincia, created_at, featured
        FROM avisos
        ORDER BY created_at DESC, id DESC
        LIMIT 25
        """
    ).fetchall()
    conn.close()

    return render_template(
        "panel.html",
        role=session.get("role"),
        user=session.get("user"),
        provincias=provincias_sugeridas,
        posts=posts
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


if __name__ == "__main__":
    app.run(debug=True)