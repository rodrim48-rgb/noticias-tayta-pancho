import sqlite3

conn = sqlite3.connect("hermandad.db")
c = conn.cursor()

# Cambia estos datos a los que quieras
username = "director"
password = "1234"
role = "director"

c.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES (?,?,?)",
          (username, password, role))

conn.commit()
conn.close()

print("✅ Director creado: usuario=director contraseña=1234")
