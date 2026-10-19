import logging
import os

import psycopg2


def conectar_db():
    try:
        return psycopg2.connect(os.environ['DATABASE_URL'], connect_timeout=10)
    except (KeyError, psycopg2.Error):
        logging.error('No se pudo conectar a PostgreSQL. Revisa DATABASE_URL y el servicio.')
        return None
