# Publicar OncoPredict

Esta carpeta es una copia preparada para despliegue. No contiene las credenciales
ni los usuarios de la base de datos original.

1. Sube el contenido de esta carpeta a un repositorio privado de GitHub.
   Incluye las carpetas templates y static y el archivo modelo_cancer.pkl.
2. En Render crea una base PostgreSQL y copia su Internal Database URL.
   Revisa el precio y las condiciones antes de confirmar el servicio.
3. Crea un Web Service conectado al repositorio, en la misma región que la base.
4. Configura Python 3 y estas variables de entorno:
   - PYTHON_VERSION: 3.12.8
   - DATABASE_URL: la Internal Database URL de PostgreSQL.
   - SECRET_KEY: una clave aleatoria generada con
     `python -c "import secrets; print(secrets.token_hex(32))"`.
5. Build Command: `pip install -r requirements.txt && python init_db.py`
6. Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT`
7. Despliega y abre la dirección asignada por Render.
8. En /registro crea una cuenta nueva y comprueba el acceso y la predicción
   con datos ficticios. Las cuentas locales no se copian automáticamente.

La creación de la tabla es repetible y no elimina registros existentes.
Para ejecutar localmente, copia .env.example a .env y completa sus valores.
No subas .env a GitHub ni compartas DATABASE_URL o SECRET_KEY en el chat.
