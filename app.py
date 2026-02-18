from flask import Flask, render_template, request, redirect, session
import sqlite3

app = Flask(__name__)
app.secret_key = "tayta_pancho_secret"

# Crear base de datos
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

@app.route("/")
def index():
    conn = sqlite3.connect("hermandad.db")
    c = conn.cursor()
    c.execute("SELECT * FROM avisos ORDER BY id DESC")
    avisos = c.fetchall()
    conn.close()
    return render_template("index.html", avisos=avisos)

@app.route("/acceso-interno", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("hermandad.db")
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (username,password))
        user = c.fetchone()
        conn.close()

        if user:
            session["user"] = user[1]
            session["role"] = user[3]
            return redirect("/panel")
        else:
            return "Credenciales incorrectas"

    return render_template("login.html")

@app.route("/panel", methods=["GET","POST"])
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

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True)
