import sqlite3

conn = sqlite3.connect("hermandad.db")
c = conn.cursor()

c.execute("DELETE FROM users WHERE username='director'")
conn.commit()
conn.close()

print("✅ Usuario director eliminado. Ahora vuelve a ejecutar crear_director.py")
