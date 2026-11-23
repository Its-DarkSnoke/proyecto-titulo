import os
import sys
from pathlib import Path
from types import SimpleNamespace

import psycopg2
import pytest
from werkzeug.security import generate_password_hash, check_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
TEST_URL = os.environ.get('TEST_DATABASE_URL')
os.environ['SECRET_KEY'] = 'solo-pruebas-aisladas'
if TEST_URL:
    os.environ['DATABASE_URL'] = TEST_URL
from portal import app

PASSWORD = 'Una-clave-de-prueba-2026'


@pytest.fixture()
def estado():
    if not TEST_URL:
        pytest.skip('Se necesita TEST_DATABASE_URL de una base desechable.')
    app.config.update(TESTING=True)
    conexion = psycopg2.connect(TEST_URL)
    with conexion:
        with conexion.cursor() as cursor:
            cursor.execute(Path(__file__).resolve().parents[1].joinpath('schema.sql').read_text(encoding='utf-8'))
            cursor.execute('TRUNCATE evaluaciones,doctor_paciente,pacientes,doctores RESTART IDENTITY CASCADE')
            for correo,tipo in [('mama@test.cl','mama'),('pulmon@test.cl','pulmon'),('otro@test.cl','mama')]:
                cursor.execute('INSERT INTO doctores(nombre,correo,password_hash,especializacion) VALUES (%s,%s,%s,%s)',
                               (correo,correo,generate_password_hash(PASSWORD),tipo))
            for rut,nombre,correo in [('12345678-5','Ana Perez','ana@test.cl'),('11111111-1','Otra Persona','otra@test.cl')]:
                cursor.execute('INSERT INTO pacientes(rut,nombre,edad,correo,password_hash) VALUES (%s,%s,40,%s,%s)',
                               (rut,nombre,correo,generate_password_hash(PASSWORD)))
            cursor.execute('INSERT INTO doctor_paciente VALUES (1,1),(2,1),(3,2)')
    yield conexion
    conexion.close()


def entrar(cliente, rol, correo):
    cliente.get('/acceso/' + rol)
    with cliente.session_transaction() as sesion:
        csrf = sesion['csrf']
    return cliente.post('/acceso/' + rol, data={'csrf':csrf,'correo':correo,'password':PASSWORD}, follow_redirects=True)


def enviar(cliente, ruta, datos=None):
    with cliente.session_transaction() as sesion:
        csrf = sesion['csrf']
    return cliente.post(ruta, data={'csrf':csrf, **(datos or {})}, follow_redirects=True)


def test_logins_roles_y_especialidad(estado):
    cliente = app.test_client()
    assert cliente.get('/doctor').status_code == 302
    assert entrar(cliente,'doctor','mama@test.cl').status_code == 200
    assert cliente.get('/doctor/pulmon').status_code == 403
    assert cliente.get('/paciente').status_code == 403
    assert cliente.get('/doctor/pacientes/2').status_code == 404
    assert cliente.get('/registro').status_code == 404
    assert enviar(cliente,'/salir').status_code == 200
    assert entrar(cliente,'paciente','ana@test.cl').status_code == 200
    assert cliente.get('/doctor/mama').status_code == 403
    assert cliente.get('/doctor/pacientes/nuevo').status_code == 403
    assert enviar(cliente,'/doctor/evaluaciones/1/publicar').status_code == 403


def test_csrf_login_incorrecto_y_pulmon(estado):
    cliente = app.test_client()
    assert cliente.post('/acceso/doctor',data={}).status_code == 400
    assert cliente.get('/acceso/administrador').status_code == 404
    entrar(cliente,'doctor','pulmon@test.cl')
    assert b'Oncolog' in cliente.get('/doctor/pulmon').data
    assert enviar(cliente,'/doctor/pacientes/1',{}).status_code == 403
    cliente.post('/salir',data={'csrf':'incorrecto'})
    assert cliente.get('/doctor/pulmon').status_code == 200


def test_registro_se_deriva_a_la_agenda(estado):
    cliente = app.test_client()
    entrar(cliente,'doctor','mama@test.cl')
    respuesta = enviar(cliente,'/doctor/pacientes/nuevo',{})
    assert respuesta.status_code == 200
    assert b'Mi agenda' in respuesta.data
    with estado.cursor() as cursor:
        cursor.execute('SELECT count(*) FROM pacientes')
        assert cursor.fetchone()[0] == 2


def test_borrador_publicacion_y_aislamiento(estado,monkeypatch):
    monkeypatch.setitem(sys.modules,'joblib',SimpleNamespace(load=lambda ruta:SimpleNamespace(predict=lambda datos:[0])))
    doctor = app.test_client()
    entrar(doctor,'doctor','mama@test.cl')
    respuesta = enviar(doctor,'/doctor/pacientes/1',{'radio_medio':'10','textura_media':'12','perimetro_medio':'60','area_media':'200'})
    assert b'ANOMAL' in respuesta.data
    paciente = app.test_client()
    entrar(paciente,'paciente','ana@test.cl')
    assert b'ANOMAL' not in paciente.get('/paciente').data
    otro_doctor = app.test_client()
    entrar(otro_doctor,'doctor','otro@test.cl')
    assert enviar(otro_doctor,'/doctor/evaluaciones/1/publicar').status_code == 404
    assert enviar(doctor,'/doctor/evaluaciones/1/publicar').status_code == 200
    assert b'ANOMAL' in paciente.get('/paciente').data
    otro_paciente = app.test_client()
    entrar(otro_paciente,'paciente','otra@test.cl')
    assert b'ANOMAL' not in otro_paciente.get('/paciente').data


def test_cli_y_migracion(estado):
    runner = app.test_cli_runner()
    assert runner.invoke(args=['preparar-db']).exit_code == 0
    assert runner.invoke(args=['crear-doctor','--nombre','Doctor Nuevo','--correo','nuevo@test.cl','--especializacion','pulmon','--password',PASSWORD]).exit_code == 0
    with estado:
        with estado.cursor() as cursor:
            cursor.execute('CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY,correo TEXT UNIQUE,password_hash TEXT)')
            cursor.execute('DELETE FROM usuarios WHERE correo=%s',('migrar@test.cl',))
            cursor.execute('INSERT INTO usuarios(correo,password_hash) VALUES (%s,%s)',('migrar@test.cl',generate_password_hash(PASSWORD)))
    assert runner.invoke(args=['migrar-doctor','--correo','migrar@test.cl','--nombre','Doctor Migrado','--especializacion','mama']).exit_code == 0
    with estado.cursor() as cursor:
        cursor.execute("SELECT d.password_hash=u.password_hash FROM doctores d JOIN usuarios u ON d.correo=u.correo WHERE d.correo='migrar@test.cl'")
        assert cursor.fetchone()[0]
    assert runner.invoke(args=['vincular-paciente','--correo-doctor','otro@test.cl','--rut','12345678-5']).exit_code == 0
    assert runner.invoke(args=['vincular-paciente','--correo-doctor','otro@test.cl','--rut','12345678-5']).exit_code == 0


def test_no_hay_fuga_entre_especialidades_y_validacion(estado, monkeypatch):
    doctor = app.test_client()
    entrar(doctor,'doctor','mama@test.cl')
    respuesta = enviar(doctor,'/doctor/pacientes/1',{'radio_medio':'NaN'})
    assert respuesta.status_code == 200
    with estado.cursor() as cursor:
        cursor.execute('SELECT count(*) FROM evaluaciones')
        assert cursor.fetchone()[0] == 0
    with estado:
        with estado.cursor() as cursor:
            cursor.execute("INSERT INTO evaluaciones(paciente_id,doctor_id,tipo,datos,resultado) VALUES (1,1,'mama','{}','PRIVADO_MAMA')")
    pulmon = app.test_client()
    entrar(pulmon,'doctor','pulmon@test.cl')
    assert b'PRIVADO_MAMA' not in pulmon.get('/doctor/pacientes/1').data
    assert enviar(pulmon,'/doctor/evaluaciones/1/publicar').status_code == 404
    assert doctor.post('/salir',data={'csrf':'ñ'}).status_code == 400


def test_error_modelo_no_guarda_y_login_fallido(estado,monkeypatch):
    cliente = app.test_client()
    cliente.get('/acceso/doctor')
    assert b'incorrectos' in enviar(cliente,'/acceso/doctor',{'correo':'mama@test.cl','password':'incorrecta'}).data
    assert cliente.get('/doctor').status_code == 302
    entrar(cliente,'doctor','mama@test.cl')
    def falla(ruta):
        raise OSError('modelo no disponible')
    monkeypatch.setitem(sys.modules,'joblib',SimpleNamespace(load=falla))
    respuesta = enviar(cliente,'/doctor/pacientes/1',{'radio_medio':'10','textura_media':'12','perimetro_medio':'60','area_media':'200'})
    assert b'No se pudo ejecutar el modelo' in respuesta.data
    with estado.cursor() as cursor:
        cursor.execute('SELECT count(*) FROM evaluaciones')
        assert cursor.fetchone()[0] == 0
