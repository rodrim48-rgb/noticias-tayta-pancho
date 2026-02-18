from flask import Flask, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

app = Flask(__name__)
app.secret_key = "tayta_pancho_secret_super_seguro"

# -------------------------
# Crear base de datos
# -------------------------
def init_db():
    conn = sqlite3.connect("hermandad.db")
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    password TEXT,
                    role TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS avisos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    titulo TEXT,
                    contenido TEXT)''')

    conn.commit()
    conn.close()

init_db()

# -------------------------
# PORTADA PÚBLICA
# -------------------------
@app.route("/")
def index():
    conn = sqlite3.connect("hermandad.db")
    c = conn.cursor()
    c.execute("SELECT * FROM avisos ORDER BY id DESC")
    avisos = c.fetchall()
    conn.close()
    return render_template("index.html", avisos=avisos)

# -------------------------
# LOGIN OCULTO
# -------------------------
@app.route("/acceso-interno", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("hermandad.db")
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=?", (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session["user"] = user[1]
            session["role"] = user[3]
            return redirect("/panel")
        else:
            return "Credenciales incorrectas"

    return render_template("login.html")

# -------------------------
# PANEL INTERNO
# -------------------------
@app.route("/panel", methods=["GET", "POST"])
def panel():
    if "user" not in session:
        return redirect("/acceso-interno")

    if request.method == "POST" and session["role"] == "director":
        titulo = request.form["titulo"]
        contenido = request.form["contenido"]

        conn = sqlite3.connect("hermandad.db")
        c = conn.cursor()
        c.execute("INSERT INTO avisos (titulo, contenido) VALUES (?,?)",
                  (titulo, contenido))
        conn.commit()
        conn.close()

    return render_template("panel.html", role=session["role"])

# -------------------------
# LOGOUT
# -------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# -------------------------
# CREAR DIRECTOR AUTOMÁTICO (solo si no existe)
# -------------------------
def crear_director():
    conn = sqlite3.connect("hermandad.db")
    c = conn.cursor()

    c.execute("SELECT * FROM users WHERE username='director'")
    if not c.fetchone():
        password_hash = generate_password_hash("1234")
        c.execute("INSERT INTO users (username, password, role) VALUES (?,?,?)",
                  ("director", password_hash, "director"))
        conn.commit()

    conn.close()

crear_director()

# -------------------------
if __name__ == "__main__":
    app.run(debug=True)
