"""Reset password for a user by document_number."""
import bcrypt
import psycopg2

DOC_NUMBER = "00000000"
NEW_PASSWORD = "Admin123!"

conn = psycopg2.connect(
    host="localhost", port=5432,
    dbname="logistica", user="logistica", password="logistica_dev_2024"
)
cur = conn.cursor()

hashed = bcrypt.hashpw(NEW_PASSWORD.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
cur.execute(
    "UPDATE users SET password_hash = %s WHERE document_number = %s",
    (hashed, DOC_NUMBER)
)

if cur.rowcount == 0:
    print(f"[X] No se encontro usuario con documento {DOC_NUMBER}")
else:
    print(f"[OK] Password actualizada para documento {DOC_NUMBER}")
    print(f"   Nueva password: {NEW_PASSWORD}")

conn.commit()
cur.close()
conn.close()