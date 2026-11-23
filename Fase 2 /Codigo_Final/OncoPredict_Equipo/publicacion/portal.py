import hmac
import csv
import json
import os
import secrets
import re
import unicodedata
from functools import wraps
from io import StringIO
from pathlib import Path

import click
from dotenv import load_dotenv
from flask import Flask, Response, abort, flash, g, redirect, render_template, request, send_file, session, url_for
from psycopg2 import Error, IntegrityError
from psycopg2.extras import Json, RealDictCursor
from werkzeug.security import check_password_hash, generate_password_hash
from database import conectar_db
from validaciones import rut_valido, validar_paciente

BASE = Path(__file__).resolve().parent
DASHBOARDS_POWERBI = {
    'mama': 'OncoPredict_Mama_Clinico.zip',
    'pulmon': 'OncoPredict_Pulmon_Clinico.zip',
}
load_dotenv(BASE / '.env')
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')
if not app.secret_key:
    raise RuntimeError('Falta SECRET_KEY. Crea publicacion/.env a partir de .env.example.')
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                  SESSION_COOKIE_SECURE=os.getenv('RENDER') == 'true')


def db():
    if 'db' not in g:
        g.db = conectar_db()
        if g.db is None:
            abort(503, 'No se pudo conectar a PostgreSQL. Revisa DATABASE_URL y el servicio.')
    return g.db


@app.teardown_appcontext
def cerrar_db(error=None):
    conexion = g.pop('db', None)
    if conexion is not None:
        conexion.close()


def filas(sql, valores=(), una=False):
    with db().cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(sql, valores)
        return cursor.fetchone() if una else cursor.fetchall()


@app.before_request
def proteger_formularios():
    if request.method == 'POST' and request.endpoint != 'clinica.webpay_retorno':
        esperado = session.get('csrf', '')
        recibido = request.form.get('csrf', '')
        if not esperado or not hmac.compare_digest(esperado.encode('utf-8'), recibido.encode('utf-8')):
            abort(400, 'El formulario venció. Recarga la página e inténtalo de nuevo.')


@app.context_processor
def contexto():
    if 'csrf' not in session and request.endpoint != 'clinica.webpay_retorno':
        session['csrf'] = secrets.token_hex(32)
    return {'csrf': session.get('csrf'), 'cuenta': getattr(g, 'cuenta', None)}


def requiere(rol):
    def decorar(funcion):
        @wraps(funcion)
        def protegida(*args, **kwargs):
            if not session.get('id'):
                return redirect(url_for('login', rol=rol))
            if session.get('rol') != rol:
                abort(403)
            tabla = 'doctores' if rol == 'doctor' else 'pacientes'
            g.cuenta = filas(f'SELECT * FROM {tabla} WHERE id=%s', (session['id'],), una=True)
            if not g.cuenta:
                session.clear()
                return redirect(url_for('login', rol=rol))
            return funcion(*args, **kwargs)
        return protegida
    return decorar


def paciente_asignado(paciente_id):
    paciente = filas('''SELECT p.* FROM pacientes p JOIN doctor_paciente dp
        ON dp.paciente_id=p.id WHERE p.id=%s AND dp.doctor_id=%s''',
        (paciente_id, g.cuenta['id']), una=True)
    if not paciente:
        abort(404)
    return paciente


def correo_valido(correo):
    return len(correo) <= 254 and correo.count('@') == 1 and all(correo.split('@')) and not any(c.isspace() for c in correo)


@app.route('/oncopredict')
def inicio():
    if session.get('rol') == 'doctor':
        return redirect(url_for('panel_doctor'))
    if session.get('rol') == 'paciente':
        return redirect(url_for('panel_paciente'))
    return render_template('inicio_v3.html')


@app.route('/acceso/<rol>', methods=['GET', 'POST'])
def login(rol):
    if rol not in ('doctor', 'paciente'):
        abort(404)
    if request.method == 'POST':
        tabla = 'doctores' if rol == 'doctor' else 'pacientes'
        cuenta = filas(f'SELECT * FROM {tabla} WHERE lower(correo)=%s',
                       (request.form.get('correo', '').strip().lower(),), una=True)
        if cuenta and cuenta.get('password_hash') and check_password_hash(cuenta['password_hash'], request.form.get('password', '')):
            session.clear()
            session.update(id=cuenta['id'], rol=rol)
            return redirect(url_for('inicio'))
        flash('Correo o contraseña incorrectos.')
    return render_template('acceso_v3.html', rol=rol)


@app.post('/salir')
def salir():
    session.clear()
    return redirect(url_for('inicio'))


@app.get('/doctor')
@requiere('doctor')
def panel_doctor():
    return redirect(url_for('especialidad', tipo=g.cuenta['especializacion']))


@app.get('/doctor/<tipo>')
@requiere('doctor')
def especialidad(tipo):
    if tipo != g.cuenta['especializacion']:
        abort(403)
    pacientes = filas('''SELECT p.id,p.rut,p.nombre,p.correo FROM pacientes p
        JOIN doctor_paciente dp ON dp.paciente_id=p.id WHERE dp.doctor_id=%s ORDER BY p.nombre''', (g.cuenta['id'],))
    # Dashboard de mama: historial real del doctor conectado.
    if tipo == 'mama':
        from dashboard_mama import resumen_mama
        resumen = resumen_mama(filas, g.cuenta['id'])
        return render_template('dashboard_mama.html', pacientes=pacientes, tipo=tipo, resumen=resumen)
    if tipo == 'pulmon':
        return render_template('dashboard_pulmon.html', pacientes=pacientes, tipo=tipo)
    return render_template('doctor_v3.html', pacientes=pacientes, tipo=tipo)


@app.get('/doctor/powerbi/<tipo>.zip')
@requiere('doctor')
def descargar_dashboard_powerbi(tipo):
    if tipo != g.cuenta['especializacion'] or tipo not in DASHBOARDS_POWERBI:
        abort(403)
    archivo = BASE / 'recursos_powerbi' / DASHBOARDS_POWERBI[tipo]
    if not archivo.is_file():
        abort(404, 'No se encontró el dashboard de Power BI.')
    respuesta = send_file(archivo, mimetype='application/zip', as_attachment=True,
                          download_name=archivo.name)
    respuesta.headers['Cache-Control'] = 'no-store'
    return respuesta


@app.get('/doctor/<tipo>/dashboard')
@requiere('doctor')
def dashboard_interactivo(tipo):
    if tipo != g.cuenta['especializacion'] or tipo not in DASHBOARDS_POWERBI:
        abort(403)
    ruta = BASE / 'datos_dashboard' / f'{tipo}.json'
    with ruta.open(encoding='utf-8') as archivo:
        datos = json.load(archivo)
    return render_template('dashboard_interactivo.html', tipo=tipo, datos=datos)


@app.route('/doctor/pacientes/nuevo', methods=['GET', 'POST'])
@requiere('doctor')
def nuevo_paciente():
    flash('Las cuentas de pacientes se habilitan desde una cita con pago aprobado en Mi agenda.')
    return redirect(url_for('clinica.agenda_doctor'))


@app.route('/doctor/pacientes/<int:paciente_id>', methods=['GET', 'POST'])
@requiere('doctor')
def ficha_doctor(paciente_id):
    paciente = paciente_asignado(paciente_id)
    tipo = g.cuenta['especializacion']
    if request.method == 'POST' and tipo == 'pulmon':
        from modelo_pulmon import evaluar_pulmon, validar_entrada_pulmon

        datos, errores = validar_entrada_pulmon(request.form, paciente['edad'])
        if errores:
            for mensaje in errores:
                flash(mensaje)
        else:
            try:
                puntaje, umbral, resultado = evaluar_pulmon(datos)
            except Exception:
                app.logger.exception('No se pudo ejecutar el modelo de pulmón')
                flash('No se pudo ejecutar el modelo de pulmón. Revisa el archivo y las dependencias.')
            else:
                datos.update(puntaje_modelo=round(puntaje, 6), umbral_modelo=round(umbral, 6))
                with db():
                    with db().cursor() as cursor:
                        cursor.execute('''INSERT INTO evaluaciones(paciente_id,doctor_id,tipo,datos,resultado)
                            VALUES (%s,%s,%s,%s,%s)''',
                            (paciente_id,g.cuenta['id'],tipo,Json(datos),resultado))
                flash('Señal experimental guardada como borrador para revisión del doctor.')
                return redirect(url_for('ficha_doctor', paciente_id=paciente_id))
    elif request.method == 'POST':
        if tipo != 'mama':
            abort(403)
        formulario = dict(request.form)
        formulario.update(rut=paciente['rut'], nombre=paciente['nombre'], edad=str(paciente['edad']))
        datos, errores = validar_paciente(formulario)
        if errores:
            for mensaje in errores.values():
                flash(mensaje)
        else:
            try:
                import joblib
                modelo = joblib.load(BASE / 'modelo_cancer.pkl')
                prediccion = modelo.predict([[datos[k] for k in ('radio_medio','textura_media','perimetro_medio','area_media')]])[0]
                if prediccion not in (0, 1):
                    raise ValueError('Clase de modelo desconocida')
            except Exception:
                app.logger.exception('No se pudo ejecutar el modelo de mama')
                flash('No se pudo ejecutar el modelo. Revisa el archivo y sus dependencias.')
            else:
                resultado = 'ANOMALÍA MALIGNA' if prediccion == 0 else 'ANOMALÍA BENIGNA'
                with db():
                    with db().cursor() as cursor:
                        cursor.execute('''INSERT INTO evaluaciones(paciente_id,doctor_id,tipo,datos,resultado)
                            VALUES (%s,%s,%s,%s,%s)''', (paciente_id,g.cuenta['id'],tipo,Json(datos),resultado))
                flash('Evaluación guardada como borrador. Revísala antes de publicarla.')
                return redirect(url_for('ficha_doctor', paciente_id=paciente_id))
    evaluaciones = filas('''SELECT * FROM evaluaciones WHERE paciente_id=%s AND doctor_id=%s
        AND tipo=%s ORDER BY creada_en DESC,id DESC''', (paciente_id,g.cuenta['id'],tipo))
    return render_template('ficha_v3.html', paciente=paciente, evaluaciones=evaluaciones, tipo=tipo, medico=True)


@app.get('/doctor/pacientes/<int:paciente_id>/informe-pulmon.pdf')
@requiere('doctor')
def descargar_informe_pulmon(paciente_id):
    if g.cuenta['especializacion'] != 'pulmon':
        abort(403)
    paciente = paciente_asignado(paciente_id)
    evaluacion = filas('''SELECT datos,resultado FROM evaluaciones
        WHERE paciente_id=%s AND doctor_id=%s AND tipo='pulmon'
        ORDER BY creada_en DESC,id DESC LIMIT 1''', (paciente_id,g.cuenta['id']), una=True)
    from informe_pulmon import generar_informe_pulmon
    archivo = generar_informe_pulmon(paciente, g.cuenta, evaluacion)
    respuesta = send_file(archivo, mimetype='application/pdf', as_attachment=True,
                          download_name=f'informe_pulmon_paciente_{paciente_id}.pdf')
    respuesta.headers['Cache-Control'] = 'no-store'
    return respuesta


@app.get('/doctor/pulmon/evaluaciones.csv')
@requiere('doctor')
def exportar_evaluaciones_pulmon():
    """Descarga registros del doctor para Power BI sin nombre, RUT ni correo."""
    if g.cuenta['especializacion'] != 'pulmon':
        abort(403)
    from modelo_pulmon import VARIABLES

    evaluaciones = filas('''SELECT e.id,e.paciente_id,e.creada_en,e.publicada,e.resultado,e.datos
        FROM evaluaciones e JOIN doctor_paciente dp
          ON dp.paciente_id=e.paciente_id AND dp.doctor_id=e.doctor_id
        WHERE e.doctor_id=%s AND e.tipo='pulmon'
        ORDER BY e.creada_en,e.id''', (g.cuenta['id'],))
    salida = StringIO()
    escritor = csv.writer(salida)
    escritor.writerow(['evaluacion_id','codigo_paciente','fecha','publicada','resultado',
                       'puntaje_modelo','umbral_modelo',*VARIABLES])
    for evaluacion in evaluaciones:
        datos = evaluacion['datos'] or {}
        escritor.writerow([evaluacion['id'], f"P-{evaluacion['paciente_id']}",
                           evaluacion['creada_en'].isoformat(), evaluacion['publicada'],
                           evaluacion['resultado'], datos.get('puntaje_modelo', ''),
                           datos.get('umbral_modelo', ''),
                           *(datos.get(clave, '') for clave in VARIABLES)])
    return Response('\ufeff' + salida.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename="evaluaciones_pulmon_powerbi.csv"',
                             'Cache-Control': 'no-store'})


@app.post('/doctor/evaluaciones/<int:evaluacion_id>/publicar')
@requiere('doctor')
def publicar(evaluacion_id):
    with db():
        with db().cursor() as cursor:
            cursor.execute('''UPDATE evaluaciones e SET publicada=TRUE
                WHERE e.id=%s AND e.doctor_id=%s AND e.tipo=%s
                AND EXISTS (SELECT 1 FROM doctor_paciente dp
                    WHERE dp.doctor_id=e.doctor_id AND dp.paciente_id=e.paciente_id)
                RETURNING paciente_id''', (evaluacion_id,g.cuenta['id'],g.cuenta['especializacion']))
            fila = cursor.fetchone()
            if not fila:
                abort(404)
    flash('Resultado publicado para el paciente.')
    return redirect(url_for('ficha_doctor', paciente_id=fila[0]))


@app.get('/paciente')
@requiere('paciente')
def panel_paciente():
    evaluaciones = filas('''SELECT e.*,d.nombre AS doctor_nombre FROM evaluaciones e
        JOIN doctores d ON d.id=e.doctor_id WHERE e.paciente_id=%s AND e.publicada=TRUE
        ORDER BY e.creada_en DESC,e.id DESC''', (g.cuenta['id'],))
    return render_template('ficha_v3.html', paciente=g.cuenta, evaluaciones=evaluaciones, medico=False)


@app.errorhandler(Error)
def error_bd(error):
    app.logger.exception('Error de base de datos')
    if 'db' in g:
        g.db.rollback()
    return render_template('error_v3.html', mensaje='No se pudo completar la operación en la base de datos.'), 503


@app.cli.command('preparar-db')
def preparar_db():
    """Crea tablas sin borrar usuarios ni otras tablas existentes."""
    with db():
        with db().cursor() as cursor:
            cursor.execute((BASE / 'schema.sql').read_text(encoding='utf-8'))
    click.echo('Tablas preparadas. La tabla usuarios se conserva sin cambios.')


@app.cli.command('crear-doctor')
@click.option('--nombre', prompt=True)
@click.option('--correo', prompt=True)
@click.option('--especializacion', type=click.Choice(['mama','pulmon']), prompt=True)
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
def crear_doctor(nombre, correo, especializacion, password):
    correo = correo.strip().lower()
    if not nombre.strip() or not correo_valido(correo) or len(password) < 12:
        raise click.ClickException('Revisa nombre, correo y contraseña (mínimo 12 caracteres).')
    try:
        with db():
            with db().cursor() as cursor:
                cursor.execute('INSERT INTO doctores(nombre,correo,password_hash,especializacion) VALUES (%s,%s,%s,%s)',
                               (nombre.strip(),correo,generate_password_hash(password),especializacion))
    except IntegrityError:
        raise click.ClickException('Ya existe un doctor con ese correo.')
    click.echo('Doctor creado.')


@app.cli.command('migrar-doctor')
@click.option('--correo', prompt=True)
@click.option('--nombre', prompt=True)
@click.option('--especializacion', type=click.Choice(['mama','pulmon']), prompt=True)
def migrar_doctor(correo, nombre, especializacion):
    """Copia una cuenta de usuarios conservando su hash y la cuenta original."""
    correo = correo.strip().lower()
    if not nombre.strip() or not correo_valido(correo):
        raise click.ClickException('Revisa nombre y correo.')
    try:
        with db():
            with db().cursor() as cursor:
                cursor.execute('SELECT password_hash FROM usuarios WHERE lower(correo)=%s', (correo,))
                cuentas = cursor.fetchall()
                if len(cuentas) != 1:
                    raise click.ClickException('Se necesita exactamente un usuario con ese correo.')
                cursor.execute('INSERT INTO doctores(nombre,correo,password_hash,especializacion) VALUES (%s,%s,%s,%s)',
                               (nombre.strip(),correo,cuentas[0][0],especializacion))
    except IntegrityError:
        raise click.ClickException('Ese correo ya existe en doctores.')
    click.echo('Doctor migrado. La cuenta original permanece en usuarios.')


@app.cli.command('vincular-paciente')
@click.option('--correo-doctor', prompt=True)
@click.option('--rut', prompt=True)
def vincular_paciente(correo_doctor, rut):
    """Vincula una ficha existente a otro doctor sin duplicar al paciente."""
    with db():
        with db().cursor() as cursor:
            cursor.execute('SELECT id FROM doctores WHERE lower(correo)=%s', (correo_doctor.strip().lower(),))
            doctor = cursor.fetchone()
            cursor.execute('SELECT id FROM pacientes WHERE rut=%s', (rut.strip().upper().replace('.', ''),))
            paciente = cursor.fetchone()
            if not doctor or not paciente:
                raise click.ClickException('No se encontró el doctor o el paciente.')
            cursor.execute('INSERT INTO doctor_paciente VALUES (%s,%s) ON CONFLICT DO NOTHING', (doctor[0],paciente[0]))
    click.echo('Paciente vinculado al doctor.')


@app.cli.command('crear-paciente-demo')
@click.option('--correo-doctor', prompt='Correo del doctor de pulmón')
@click.option('--rut', prompt='RUT ficticio válido')
@click.option('--nombre', prompt='Nombre ficticio del paciente')
@click.option('--edad', type=click.IntRange(0, 120), prompt='Edad')
@click.option('--correo', prompt='Correo ficticio del paciente')
def crear_paciente_demo(correo_doctor, rut, nombre, edad, correo):
    """Crea una ficha ficticia sin acceso y la vincula a un doctor de pulmón."""
    correo_doctor = correo_doctor.strip().lower()
    rut = ''.join(rut.split()).upper().replace('.', '')
    nombre = unicodedata.normalize('NFC', ' '.join(nombre.split()))
    correo = correo.strip().lower()
    if not rut_valido(rut):
        raise click.ClickException('RUT inválido. Usa el formato 12345678-5, sin puntos y con dígito verificador correcto.')
    if not nombre_valido(nombre) or len(nombre.split()) < 2:
        raise click.ClickException('Nombre inválido. Escribe nombre y apellido, solo con letras; ejemplo: Paciente Demo.')
    if not correo_valido(correo):
        raise click.ClickException('Correo inválido. Usa un correo ficticio sin espacios; ejemplo: paciente.demo@example.com.')
    try:
        with db():
            with db().cursor() as cursor:
                cursor.execute("SELECT id FROM doctores WHERE lower(correo)=%s AND especializacion='pulmon'", (correo_doctor,))
                doctor = cursor.fetchone()
                if not doctor:
                    raise click.ClickException('No se encontró un doctor de pulmón con ese correo.')
                cursor.execute('''INSERT INTO pacientes(rut,nombre,edad,correo,password_hash)
                    VALUES (%s,%s,%s,%s,NULL) RETURNING id''', (rut,nombre,edad,correo))
                paciente_id = cursor.fetchone()[0]
                cursor.execute('INSERT INTO doctor_paciente(doctor_id,paciente_id) VALUES (%s,%s)',
                               (doctor[0],paciente_id))
    except IntegrityError:
        raise click.ClickException('El RUT o correo ya existe. Usa otro dato ficticio o vincula la ficha existente.')
    click.echo(f'Paciente de prueba creado y vinculado al doctor de pulmón. ID: {paciente_id}.')


def nombre_valido(nombre):
    if not 3 <= len(nombre) <= 100:
        return False

    partes = re.split(r"[\s'’\-]", nombre)

    return all(
        parte and parte.isalpha()
        for parte in partes
    )


from clinica import registrar_clinica
registrar_clinica(app, db, filas, requiere, nombre_valido, correo_valido)

from correo_citas import enviar_confirmacion

app.cli.add_command(enviar_confirmacion)
