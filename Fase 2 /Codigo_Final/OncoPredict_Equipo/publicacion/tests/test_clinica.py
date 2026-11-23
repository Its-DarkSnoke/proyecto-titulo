import os
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg2
import pytest
from werkzeug.security import generate_password_hash

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
URL=os.environ.get('TEST_DATABASE_URL')
os.environ['SECRET_KEY']='solo-pruebas-clinica'
if URL:
    os.environ['DATABASE_URL']=URL
from portal import app

PASSWORD='Prueba-clinica-2026'


@pytest.fixture
def estado():
    if not URL:
        pytest.skip('Se requiere una base de pruebas desechable.')
    app.config.update(TESTING=True)
    conn=psycopg2.connect(URL)
    with conn:
        with conn.cursor() as c:
            c.execute('TRUNCATE pacientes,doctores RESTART IDENTITY CASCADE')
            for nombre,tipo in [('Doctor Mama','mama'),('Doctor Pulmon','pulmon')]:
                c.execute('INSERT INTO doctores(nombre,correo,password_hash,especializacion) VALUES (%s,%s,%s,%s)',(nombre,tipo+'@test.cl',generate_password_hash(PASSWORD),tipo))
            c.execute("INSERT INTO pacientes(rut,nombre,edad,correo,password_hash) VALUES ('11111111-1','Paciente Existente',40,'existente@test.cl',%s)",(generate_password_hash(PASSWORD),))
    yield conn
    conn.close()


def cliente_doctor(doctor=1):
    cliente=app.test_client()
    with cliente.session_transaction() as s:
        s.update(id=doctor,rol='doctor',csrf='csrf-prueba')
    return cliente


def post(cliente,ruta,datos=None):
    with cliente.session_transaction() as s:
        s.setdefault('csrf','csrf-prueba')
        token=s['csrf']
    return cliente.post(ruta,data={'csrf':token,**(datos or {})})


def turno(conn,doctor=1,pasado=False):
    inicio=(datetime.now(ZoneInfo('America/Santiago'))+timedelta(days=-1 if pasado else 1)).replace(hour=9,minute=0,second=0,microsecond=0)
    with conn:
        with conn.cursor() as c:
            c.execute('INSERT INTO disponibilidad_doctores(doctor_id,inicio,fin) VALUES (%s,%s,%s) RETURNING id',(doctor,inicio,inicio+timedelta(minutes=30)))
            return c.fetchone()[0],inicio


DATOS={'rut':'22222222-2','nombre':'Paciente Nuevo','edad':'35','correo':'nuevo@test.cl','motivo':'Consulta de evaluación'}


def test_portada_agenda_y_creacion_turnos(estado):
    c=app.test_client()
    assert c.get('/').status_code==200
    assert b'Consultar disponibilidad' in c.get('/').data
    assert c.get('/doctor/agenda').status_code==302
    medico=cliente_doctor()
    dia=(datetime.now(ZoneInfo('America/Santiago'))+timedelta(days=1)).date().isoformat()
    assert post(medico,'/doctor/agenda',{'fecha':dia,'desde':'09:00','hasta':'10:30'}).status_code==302
    assert post(medico,'/doctor/agenda',{'fecha':dia,'desde':'09:00','hasta':'10:30'}).status_code==302
    with estado.cursor() as sql:
        sql.execute('SELECT count(*) FROM disponibilidad_doctores')
        assert sql.fetchone()[0]==3
    assert c.get('/agendar?fecha='+dia).status_code==200
    assert c.get('/agendar?fecha=no-valida').status_code==400
    assert c.get('/agendar?doctor=mal').status_code==400


def test_reserva_sin_credenciales_ni_programa(estado):
    id,inicio=turno(estado)
    c=app.test_client()
    r=post(c,f'/reservar/{id}',DATOS)
    assert r.status_code==302
    assert c.get('/reserva-pendiente').status_code==200
    with estado.cursor() as sql:
        sql.execute('SELECT password_hash FROM pacientes WHERE rut=%s',(DATOS['rut'],))
        assert sql.fetchone()[0] is None
        sql.execute('SELECT count(*) FROM doctor_paciente')
        assert sql.fetchone()[0]==0
        sql.execute('SELECT estado FROM citas')
        assert sql.fetchone()[0]=='pendiente'
        sql.execute('SELECT count(*) FROM pagos')
        assert sql.fetchone()[0]==0
    respuesta=post(c,'/acceso/paciente',{'correo':DATOS['correo'],'password':PASSWORD})
    assert respuesta.status_code==200
    assert b'incorrectos' in respuesta.data
    assert app.test_client().get('/reserva-pendiente').status_code==302


def test_validacion_y_no_sobrescribe_paciente(estado):
    id,_=turno(estado)
    c=app.test_client()
    assert post(c,f'/reservar/{id}',{**DATOS,'nombre':'Juan123'}).status_code==200
    assert post(c,f'/reservar/{id}',{**DATOS,'rut':'11111111-1','correo':'otro@test.cl'}).status_code==409
    assert post(c,f'/reservar/{id}',{**DATOS,'rut':'11111111-1','correo':'existente@test.cl'}).status_code==302
    with estado.cursor() as sql:
        sql.execute("SELECT nombre,password_hash IS NOT NULL FROM pacientes WHERE rut='11111111-1'")
        assert sql.fetchone()==('Paciente Existente',True)


def test_cancelar_y_expirar_libera_turno(estado):
    id,_=turno(estado)
    c=app.test_client()
    assert post(c,f'/reservar/{id}',DATOS).status_code==302
    assert post(c,'/reserva-pendiente/cancelar').status_code==302
    assert post(c,f'/reservar/{id}',DATOS).status_code==302
    with estado:
        with estado.cursor() as sql:
            sql.execute("UPDATE citas SET reserva_vence_en=now()-interval '1 minute' WHERE estado='pendiente'")
    assert post(c,f'/reservar/{id}',DATOS).status_code==302
    with estado.cursor() as sql:
        sql.execute('SELECT estado,count(*) FROM citas GROUP BY estado')
        assert dict(sql.fetchall())=={'cancelada':1,'expirada':1,'pendiente':1}


def test_dos_reservas_simultaneas(estado):
    id,_=turno(estado)
    barrera=Barrier(2)
    def reservar():
        cliente=app.test_client()
        with cliente.session_transaction() as s:
            s['csrf']='concurrencia'
        barrera.wait(timeout=10)
        return cliente.post(f'/reservar/{id}',data={'csrf':'concurrencia',**DATOS}).status_code
    with ThreadPoolExecutor(max_workers=2) as ejecutor:
        respuestas=list(ejecutor.map(lambda _:reservar(),range(2)))
    assert sorted(respuestas)==[302,409]
    with estado.cursor() as sql:
        sql.execute("SELECT count(*) FROM citas WHERE estado='pendiente'")
        assert sql.fetchone()[0]==1


def test_permisos_turnos_y_csrf(estado):
    id,_=turno(estado)
    assert post(cliente_doctor(2),f'/doctor/agenda/turnos/{id}/alternar',{'fecha':'2026-11-10'}).status_code==404
    assert app.test_client().post(f'/reservar/{id}',data=DATOS).status_code==400
    c=app.test_client()
    with c.session_transaction() as s:
        s.update(id=1,rol='paciente',csrf='prueba')
    assert c.get('/doctor/agenda').status_code==403
    publico=app.test_client()
    assert post(publico,f'/reservar/{id}',DATOS).status_code==302
    assert post(cliente_doctor(),f'/doctor/agenda/turnos/{id}/alternar').status_code==409


def test_incorporacion_requiere_atencion_confirmada(estado):
    id,inicio=turno(estado,pasado=True)
    with estado:
        with estado.cursor() as sql:
            sql.execute('INSERT INTO citas(doctor_id,paciente_id,fecha_hora,motivo,estado,disponibilidad_id) VALUES (1,1,%s,%s,%s,%s) RETURNING id',(inicio,'Consulta','confirmada',id))
            cita=sql.fetchone()[0]
    assert post(cliente_doctor(2),f'/doctor/agenda/citas/{cita}/incorporar').status_code==403
    assert post(cliente_doctor(),f'/doctor/agenda/citas/{cita}/incorporar').status_code==302
    with estado.cursor() as sql:
        sql.execute('SELECT count(*) FROM doctor_paciente WHERE doctor_id=1 AND paciente_id=1')
        assert sql.fetchone()[0]==1
    assert post(cliente_doctor(),f'/doctor/agenda/citas/{cita}/estado',{'estado':'realizada'}).status_code==302
    assert post(cliente_doctor(),f'/doctor/agenda/citas/{cita}/estado',{'estado':'confirmada'}).status_code==400


def test_no_incorpora_pendiente(estado):
    id,_=turno(estado)
    assert post(app.test_client(),f'/reservar/{id}',DATOS).status_code==302
    with estado.cursor() as sql:
        sql.execute('SELECT id FROM citas')
        cita=sql.fetchone()[0]
    assert post(cliente_doctor(),f'/doctor/agenda/citas/{cita}/incorporar',{'password':PASSWORD}).status_code==403
