"""Prepara una base local con datos ficticios para ejecutar OncoPredict."""

import argparse
from datetime import datetime, time, timedelta
from getpass import getpass
from pathlib import Path
import secrets
from zoneinfo import ZoneInfo

import psycopg2
from psycopg2 import sql
from werkzeug.security import generate_password_hash

BASE = Path(__file__).resolve().parent
ACCESOS = "ACCESOS_DEMO.txt"


def sembrar_demo(cursor, esquema):
    cursor.execute(esquema)
    accesos = []
    chile = ZoneInfo("America/Santiago")
    fecha = datetime.now(chile).date() + timedelta(days=1)
    personas = (
        ("mama", "Doctora Demo Mama", "Muestra Demo Mama", "12345678-5", 48),
        ("pulmon", "Doctor Demo Pulmon", "Paciente Demo Pulmon", "11111111-1", 57),
    )
    for (tipo, doctor, paciente, rut, edad), hora in zip(personas, [10, 11]):
        correo = f"doctor.{tipo}@oncopredict.test"
        clave = secrets.token_urlsafe(15)
        cursor.execute(
            """INSERT INTO public.doctores(nombre, correo, password_hash, especializacion)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (doctor, correo, generate_password_hash(clave), tipo),
        )
        doctor_id = cursor.fetchone()[0]
        cursor.execute(
            """INSERT INTO public.pacientes(rut, nombre, edad, correo)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (rut, paciente, edad, f"paciente.{tipo}@oncopredict.test"),
        )
        paciente_id = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO public.doctor_paciente(doctor_id, paciente_id) VALUES (%s, %s)",
            (doctor_id, paciente_id),
        )
        inicio = datetime.combine(fecha, time(hora), tzinfo=chile)
        cursor.execute(
            """INSERT INTO public.disponibilidad_doctores(doctor_id, inicio, fin)
               VALUES (%s, %s, %s)""",
            (doctor_id, inicio, inicio + timedelta(minutes=30)),
        )
        accesos.append(f"{doctor}\nCorreo: {correo}\nContraseña: {clave}")
    return accesos, fecha


def preparar(carpeta, administrador, puerto, clave_admin):
    esquema = (carpeta / "schema.sql").read_text(encoding="utf-8")
    sufijo = secrets.token_hex(5)
    base_demo = f"oncopredict_demo_{sufijo}"
    rol_demo = f"oncopredict_app_{sufijo}"
    clave_demo = secrets.token_hex(24)
    local = {"host": "127.0.0.1", "port": puerto, "connect_timeout": 5}

    admin = psycopg2.connect(dbname="postgres", user=administrador, password=clave_admin, **local)
    admin.autocommit = True
    rol_creado = False
    base_creada = False
    accesos_creados = False
    try:
        with admin.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD %s").format(sql.Identifier(rol_demo)), (clave_demo,))
            rol_creado = True
            cursor.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(base_demo), sql.Identifier(rol_demo)
            ))
            base_creada = True
        demo = psycopg2.connect(dbname=base_demo, user=rol_demo, password=clave_demo, **local)
        try:
            with demo, demo.cursor() as cursor:
                accesos, fecha = sembrar_demo(cursor, esquema)
        finally:
            demo.close()

        with (carpeta / ACCESOS).open("x", encoding="utf-8") as archivo:
            accesos_creados = True
            archivo.write("Acceso médico de la demo local\n\n" + "\n\n".join(accesos)
                          + f"\n\nTurnos de ejemplo el {fecha:%d/%m/%Y} a las 10:00 y 11:00 (Chile).\n")
        with (carpeta / ".env").open("x", encoding="utf-8") as archivo:
            archivo.write(
                f"SECRET_KEY={secrets.token_hex(32)}\n"
                f"DATABASE_URL=postgresql://{rol_demo}:{clave_demo}@127.0.0.1:{puerto}/{base_demo}\n"
                "CLINICA_NOMBRE=Clínica Onco · Demo\n"
                "WEBPAY_PRUEBA=1\nWEBPAY_MONTO_PRUEBA=1000\n"
                "WEBPAY_URL_RETORNO=http://127.0.0.1:5000/webpay/retorno\n"
            )
    except Exception:
        if accesos_creados:
            (carpeta / ACCESOS).unlink(missing_ok=True)
        with admin.cursor() as cursor:
            if base_creada:
                cursor.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(base_demo)))
            if rol_creado:
                cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(rol_demo)))
        raise
    finally:
        admin.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usuario", default="postgres", help="Usuario administrador de PostgreSQL")
    parser.add_argument("--puerto", type=int, default=5432, help="Puerto local de PostgreSQL")
    args = parser.parse_args()
    if not 1 <= args.puerto <= 65535:
        parser.error("El puerto debe estar entre 1 y 65535.")
    if (BASE / ".env").exists() or (BASE / ACCESOS).exists():
        raise SystemExit("Esta carpeta ya tiene configuración o accesos. Si corresponde a tu demo, puedes iniciarla.")
    password = getpass(f"Contraseña de PostgreSQL para {args.usuario}: ")
    try:
        preparar(BASE, args.usuario, args.puerto, password)
    except psycopg2.OperationalError:
        raise SystemExit(
            "No se pudo conectar a PostgreSQL o a la nueva base. Revisa el servicio, el usuario, el puerto y la contraseña."
        ) from None
    except psycopg2.Error:
        raise SystemExit(
            "No se pudo preparar la base. El usuario de PostgreSQL debe poder crear bases y roles."
        ) from None
    print(f"Demo lista. Abre {ACCESOS} para ver las cuentas de mama y pulmón.")


if __name__ == "__main__":
    main()
