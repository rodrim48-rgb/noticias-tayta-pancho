import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect("hermandad.db")
c = conn.cursor()

username = "director"
password = "1234"
role = "director"

password_hash = generate_password_hash(password)

c.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES (?,?,?)",
          (username, password_hash, role))

conn.commit()
conn.close()

print("✅ Director creado con contraseña cifrada: usuario=director contraseña=1234")
