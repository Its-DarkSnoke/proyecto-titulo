from database import conectar_db
from dotenv import load_dotenv

load_dotenv()

if __name__ == '__main__':
    conexion = conectar_db()
    if conexion is None:
        raise SystemExit('No se pudo inicializar la base de datos.')
    try:
        with conexion:
            with conexion.cursor() as cursor:
                cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios (
                    id SERIAL PRIMARY KEY,
                    correo TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL
                )''')
    finally:
        conexion.close()
    print('Tabla usuarios preparada.')
