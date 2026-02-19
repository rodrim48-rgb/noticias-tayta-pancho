from flask import Flask, render_template, request, redirect, session, abort, url_for
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = "noticias_tayta_pancho_secret"

DB = "hermandad.db"


# -------------------------
# DB
# -------------------------
def get_conn():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row  # para usar n["titulo"] en vez de n[1]
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT UNIQUE NOT NULL,
      password TEXT NOT NULL,
      role TEXT NOT NULL DEFAULT 'member'
    );
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
    );
    """)

    conn.commit()
    conn.close()


init_db()


# -------------------------
# Público
# -------------------------
@app.route("/")
def index():
    provincia = request.args.get("provincia", "Pomabamba").strip()
    q = request.args.get("q", "").strip()

    conn = get_conn()
    c = conn.cursor()

    # destacada
    c.execute("""
        SELECT * FROM avisos
        WHERE provincia=? AND featured=1
        ORDER BY id DESC
        LIMIT 1
    """, (provincia,))
    destacada = c.fetchone()

    # lista
    if q:
        c.execute("""
            SELECT * FROM avisos
            WHERE provincia=? AND (titulo LIKE ? OR resumen LIKE ? OR contenido LIKE ?)
            ORDER BY id DESC
        """, (provincia, f"%{q}%", f"%{q}%", f"%{q}%"))
    else:
        c.execute("""
            SELECT * FROM avisos
            WHERE provincia=?
            ORDER BY id DESC
        """, (provincia,))

    noticias = c.fetchall()
    conn.close()

    return render_template(
        "index.html",
        provincia=provincia,
        q=q,
        destacada=destacada,
        noticias=noticias
    )


@app.route("/noticia/<int:noticia_id>")
def noticia(noticia_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM avisos WHERE id=?", (noticia_id,))
    n = c.fetchone()
    conn.close()

    if not n:
        abort(404)

    return render_template("noticia.html", n=n)


# -------------------------
# Acceso interno (oculto)
# -------------------------
@app.route("/acceso-interno", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()

        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        conn.close()

        if user:
            session["user"] = user["username"]
            session["role"] = user["role"]
            return redirect("/panel")

        return render_template("login.html", error="Credenciales incorrectas")

    return render_template("login.html", error=None)


@app.route("/panel", methods=["GET", "POST"])
def panel():
    if "user" not in session:
        return redirect("/acceso-interno")

    if session.get("role") != "director":
        return "No autorizado"

    if request.method == "POST":
        titulo = request.form["titulo"].strip()
        resumen = request.form["resumen"].strip()
        contenido = request.form["contenido"].strip()
        provincia = request.form["provincia"].strip()
        featured = 1 if request.form.get("featured") == "on" else 0

        if not resumen:
            resumen = (contenido[:160] + "...") if len(contenido) > 160 else contenido

        created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

        conn = get_conn()
        c = conn.cursor()

        # si marco destacada, quitamos otras destacadas de esa provincia
        if featured == 1:
            c.execute("UPDATE avisos SET featured=0 WHERE provincia=?", (provincia,))

        c.execute("""
            INSERT INTO avisos (titulo, resumen, contenido, provincia, imagen, created_at, featured)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (titulo, resumen, contenido, provincia, None, created_at, featured))

        conn.commit()
        conn.close()

        return redirect(url_for("index", provincia=provincia))

    return render_template("panel.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# -------------------------
# Primera cuenta director (solo una vez)
# -------------------------
@app.route("/crear-director")
def crear_director():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username='director'")
    existe = c.fetchone()

    if not existe:
        c.execute("INSERT INTO users (username, password, role) VALUES (?,?,?)",
                  ("director", "1234", "director"))
        conn.commit()

    conn.close()
    return "Director listo: usuario=director clave=1234 (cámbiala luego)."


if __name__ == "__main__":
    app.run(debug=True)
