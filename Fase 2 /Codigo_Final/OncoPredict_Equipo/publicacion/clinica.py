"""Portal público y agenda. Los pagos y correos se integran en la siguiente etapa."""
from datetime import datetime, timedelta
import os
import unicodedata
from zoneinfo import ZoneInfo

import click
from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer
from psycopg2 import IntegrityError
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash
from werkzeug.exceptions import HTTPException
from validaciones import rut_valido

CHILE = ZoneInfo('America/Santiago')
ACTIVAS = ('pendiente', 'confirmada', 'realizada', 'no_asistio')


class DatosReservaError(ValueError):
    """Los datos no identifican una única ficha sin modificarla."""


def normalizar_rut(valor):
    return ''.join(valor.split()).upper().replace('.', '')


def buscar_paciente_reserva(cursor, rut, correo):
    cursor.execute('''SELECT id,
        regexp_replace(upper(btrim(rut)), '[.[:space:]]', '', 'g') AS rut_normalizado,
        lower(btrim(correo)) AS correo_normalizado
        FROM public.pacientes
        WHERE regexp_replace(upper(btrim(rut)), '[.[:space:]]', '', 'g')=%s
           OR lower(btrim(correo))=%s
        ORDER BY id FOR UPDATE''', (rut, correo))
    candidatos = cursor.fetchall()
    if not candidatos:
        return None
    if len(candidatos) == 1 and candidatos[0]['rut_normalizado'] == rut and candidatos[0]['correo_normalizado'] == correo:
        return candidatos[0]
    raise DatosReservaError('No pudimos verificar una ficha única con estos datos. Revisa el RUT y el correo de contacto o consulta a la clínica. No necesitas iniciar sesión en OncoPredict.')


def obtener_paciente_reserva(cursor, rut, nombre, edad, correo):
    paciente = buscar_paciente_reserva(cursor, rut, correo)
    if paciente:
        return paciente
    cursor.execute('''INSERT INTO public.pacientes(rut,nombre,edad,correo,password_hash)
        VALUES (%s,%s,%s,%s,NULL) ON CONFLICT DO NOTHING RETURNING id''', (rut,nombre,edad,correo))
    paciente = cursor.fetchone()
    if paciente:
        return paciente
    # Otra reserva pudo crear la misma ficha mientras esperábamos el INSERT.
    paciente = buscar_paciente_reserva(cursor, rut, correo)
    if paciente:
        return paciente
    raise DatosReservaError('No se pudo verificar la ficha. Revisa los datos o contacta a la clínica.')


def registrar_clinica(app, db, filas, requiere, nombre_valido, correo_valido):
    bp = Blueprint('clinica', __name__)
    reserva_serializer = URLSafeTimedSerializer(app.secret_key, salt='onco-reserva-retomar')
    reserva_cookie = 'onco_reserva_retomar'
    app.config.setdefault('CLINICA_NOMBRE', os.getenv('CLINICA_NOMBRE', 'Clínica Onco'))

    def reserva_id_actual():
        cita_id = session.get('reserva_clinica')
        if cita_id:
            return cita_id
        token = request.cookies.get(reserva_cookie, '')
        if not token:
            return None
        try:
            carga = reserva_serializer.loads(token, max_age=15 * 60)
            cita_id = carga.get('cita_id') if isinstance(carga, dict) else None
            return int(cita_id) if cita_id else None
        except (BadSignature, TypeError, ValueError):
            return None

    def configurar_cookie_reserva(respuesta, cita_id):
        respuesta.set_cookie(
            reserva_cookie,
            reserva_serializer.dumps({'cita_id': cita_id}),
            max_age=15 * 60,
            httponly=True,
            secure=app.config.get('SESSION_COOKIE_SECURE', False),
            samesite='Lax',
            path='/',
        )
        return respuesta

    def limpiar_cookie_reserva(respuesta):
        respuesta.delete_cookie(reserva_cookie, path='/')
        return respuesta

    def reserva_pendiente_retomable():
        cita_id = reserva_id_actual()
        if not cita_id:
            return False
        cita = filas('''SELECT estado,reserva_vence_en>CURRENT_TIMESTAMP AS vigente
            FROM public.citas WHERE id=%s''', (cita_id,), una=True)
        return bool(cita and cita['estado'] == 'pendiente' and cita['vigente'])

    @bp.errorhandler(HTTPException)
    def error_clinica(error):
        return render_template('clinica_error.html', codigo=error.code, mensaje=error.description), error.code

    def caducar(cursor, doctor_id=None, disponibilidad_id=None):
        sql = "UPDATE public.citas SET estado='expirada' WHERE estado='pendiente' AND reserva_vence_en <= CURRENT_TIMESTAMP"
        valores = []
        if doctor_id is not None:
            sql += ' AND doctor_id=%s'
            valores.append(doctor_id)
        if disponibilidad_id is not None:
            sql += ' AND disponibilidad_id=%s'
            valores.append(disponibilidad_id)
        cursor.execute(sql, valores)

    def fecha_consulta():
        hoy = datetime.now(CHILE).date()
        try:
            fecha = datetime.strptime(request.args.get('fecha', hoy.isoformat()), '%Y-%m-%d').date()
        except ValueError:
            abort(400, 'La fecha no es válida.')
        if abs((fecha - hoy).days) > 366:
            abort(400, 'Selecciona una fecha dentro de un año.')
        return fecha

    @app.context_processor
    def contexto_clinica():
        return {'clinica_nombre': app.config['CLINICA_NOMBRE']}

    @bp.get('/')
    def portada():
        return render_template('clinica_inicio.html', reserva_retomable=reserva_pendiente_retomable())

    @bp.get('/agendar')
    def agendar():
        fecha = fecha_consulta()
        doctores = filas('SELECT id,nombre,especializacion FROM public.doctores ORDER BY nombre')
        doctor = request.args.get('doctor', '', type=str)
        try:
            doctor_id = int(doctor) if doctor else None
        except ValueError:
            abort(400, 'Selecciona un doctor válido.')
        with db():
            with db().cursor() as cursor:
                caducar(cursor)
        reserva_retomable = reserva_pendiente_retomable()
        horarios = filas('''SELECT d.id,d.doctor_id,m.nombre,m.especializacion,d.inicio,d.fin
            FROM public.disponibilidad_doctores d JOIN public.doctores m ON m.id=d.doctor_id
            WHERE d.habilitada AND d.inicio>CURRENT_TIMESTAMP
            AND (d.inicio AT TIME ZONE 'America/Santiago')::date=%s
            AND (%s::integer IS NULL OR d.doctor_id=%s)
            AND NOT EXISTS (SELECT 1 FROM public.citas c
                WHERE c.disponibilidad_id=d.id AND c.estado IN %s)
            ORDER BY d.inicio,m.nombre''', (fecha,doctor_id,doctor_id,ACTIVAS))
        for horario in horarios:
            horario['inicio_local'] = horario['inicio'].astimezone(CHILE)
            horario['fin_local'] = horario['fin'].astimezone(CHILE)
        return render_template('clinica_agendar.html', fecha=fecha, doctores=doctores,
                               doctor_id=doctor_id, horarios=horarios, hoy=datetime.now(CHILE).date(),
                               reserva_retomable=reserva_retomable)

    @bp.route('/reservar/<int:horario_id>', methods=['GET','POST'])
    def reservar(horario_id):
        horario = filas('''SELECT d.*,m.nombre AS doctor_nombre,m.especializacion
            FROM public.disponibilidad_doctores d JOIN public.doctores m ON m.id=d.doctor_id
            WHERE d.id=%s AND d.habilitada AND d.inicio>CURRENT_TIMESTAMP''', (horario_id,), una=True)
        if not horario:
            abort(404, 'El horario ya no está disponible.')
        horario['inicio_local'] = horario['inicio'].astimezone(CHILE)
        if request.method == 'POST':
            rut = normalizar_rut(request.form.get('rut',''))
            nombre = unicodedata.normalize('NFC',' '.join(request.form.get('nombre','').split()))
            correo = request.form.get('correo','').strip().lower()
            edad = request.form.get('edad','')
            motivo = request.form.get('motivo','').strip()
            if not rut_valido(rut) or not nombre_valido(nombre) or not correo_valido(correo) or not edad.isascii() or not edad.isdigit() or not 1 <= len(edad) <= 3 or not 0 <= int(edad) <= 120 or not 3 <= len(motivo) <= 500:
                flash('Revisa RUT, nombre, correo, edad (0–120) y motivo (3–500 caracteres).')
            else:
                try:
                    with db():
                        with db().cursor(cursor_factory=RealDictCursor) as cursor:
                            # El bloqueo y el índice único evitan reservar dos veces el turno.
                            cursor.execute('''SELECT id FROM public.disponibilidad_doctores
                                WHERE id=%s AND habilitada AND inicio>CURRENT_TIMESTAMP FOR UPDATE''', (horario_id,))
                            if not cursor.fetchone():
                                abort(409, 'El horario ya no está disponible.')
                            caducar(cursor, disponibilidad_id=horario_id)
                            cursor.execute('SELECT id FROM public.citas WHERE disponibilidad_id=%s AND estado IN %s', (horario_id, ACTIVAS))
                            if cursor.fetchone():
                                abort(409, 'Otra persona reservó este horario. Selecciona otro.')
                            # Reutiliza la ficha tras comparar ambos datos normalizados.
                            # Nunca modifica nombre, correo, RUT ni credenciales existentes.
                            paciente = obtener_paciente_reserva(cursor, rut, nombre, int(edad), correo)
                            cursor.execute('''INSERT INTO public.citas
                                (doctor_id,paciente_id,fecha_hora,motivo,disponibilidad_id,reserva_vence_en)
                                VALUES (%s,%s,%s,%s,%s,CURRENT_TIMESTAMP+INTERVAL '15 minutes')
                                RETURNING id''', (horario['doctor_id'],paciente['id'],horario['inicio'],motivo,horario_id))
                            cita_id = cursor.fetchone()['id']
                    session['reserva_clinica'] = cita_id
                    respuesta = redirect(url_for('clinica.reserva_pendiente'))
                    return configurar_cookie_reserva(respuesta, cita_id)
                except DatosReservaError as error:
                    flash(str(error))
                except IntegrityError:
                    flash('No se pudo reservar el turno. Revisa los datos o selecciona otro horario.')
        return render_template('clinica_reservar.html', horario=horario)

    @bp.get('/reserva-pendiente')
    def reserva_pendiente():
        cita_id = reserva_id_actual()
        if not cita_id:
            return redirect(url_for('clinica.agendar'))
        session['reserva_clinica'] = cita_id
        with db():
            with db().cursor() as cursor:
                caducar(cursor)
        cita = filas('''SELECT c.id,c.estado,c.fecha_hora,c.reserva_vence_en,c.disponibilidad_id,d.nombre AS doctor_nombre
            FROM public.citas c JOIN public.doctores d ON d.id=c.doctor_id WHERE c.id=%s''', (cita_id,), una=True)
        if not cita:
            abort(404)
        cita['inicio_local'] = cita['fecha_hora'].astimezone(CHILE)
        cita['vence_local'] = cita['reserva_vence_en'].astimezone(CHILE)
        return render_template('clinica_pendiente.html', cita=cita)

    @bp.post('/reserva-pendiente/cancelar')
    def cancelar_reserva():
        cita_id = reserva_id_actual()
        if cita_id:
            with db():
                with db().cursor() as cursor:
                    cursor.execute("UPDATE public.citas SET estado='cancelada' WHERE id=%s AND estado='pendiente'", (cita_id,))
        session.pop('reserva_clinica',None)
        return limpiar_cookie_reserva(redirect(url_for('clinica.agendar')))

    @bp.route('/doctor/agenda', methods=['GET','POST'])
    @requiere('doctor')
    def agenda_doctor():
        if request.method == 'POST':
            try:
                dia = datetime.strptime(request.form.get('fecha',''),'%Y-%m-%d').date()
                desde = datetime.strptime(request.form.get('desde',''),'%H:%M').time()
                hasta = datetime.strptime(request.form.get('hasta',''),'%H:%M').time()
                inicio = datetime.combine(dia,desde,CHILE)
                fin = datetime.combine(dia,hasta,CHILE)
                if inicio <= datetime.now(CHILE) or dia > datetime.now(CHILE).date()+timedelta(days=180) or desde.minute not in (0,30) or hasta.minute not in (0,30) or fin <= inicio:
                    raise ValueError()
            except ValueError:
                flash('Selecciona una fecha futura dentro de 180 días, con inicio y término a la hora o a la media hora.')
            else:
                creados=0
                with db():
                    with db().cursor() as cursor:
                        while inicio < fin:
                            cursor.execute('''INSERT INTO public.disponibilidad_doctores(doctor_id,inicio,fin)
                                VALUES (%s,%s,%s) ON CONFLICT (doctor_id,inicio) DO NOTHING''',
                                (g.cuenta['id'],inicio,inicio+timedelta(minutes=30)))
                            creados += cursor.rowcount
                            inicio += timedelta(minutes=30)
                flash(f'Se crearon {creados} turnos de 30 minutos. Los existentes se conservaron.')
                return redirect(url_for('clinica.agenda_doctor',fecha=dia.isoformat()))
        fecha=fecha_consulta()
        with db():
            with db().cursor() as cursor:
                caducar(cursor,doctor_id=g.cuenta['id'])
        citas=filas('''SELECT c.*,p.nombre,p.rut,p.correo,p.password_hash IS NOT NULL AS tiene_acceso,
            EXISTS(SELECT 1 FROM public.pagos pa WHERE pa.cita_id=c.id AND pa.estado='aprobado') AS pago_aprobado
            FROM public.citas c JOIN public.pacientes p ON p.id=c.paciente_id
            WHERE c.doctor_id=%s AND (c.fecha_hora AT TIME ZONE 'America/Santiago')::date=%s
            ORDER BY c.fecha_hora,c.id''',(g.cuenta['id'],fecha))
        turnos=filas('''SELECT d.*,d.inicio<=CURRENT_TIMESTAMP AS pasado,EXISTS(SELECT 1 FROM public.citas c
            WHERE c.disponibilidad_id=d.id AND c.estado IN %s) AS ocupado
            FROM public.disponibilidad_doctores d WHERE d.doctor_id=%s
            AND (d.inicio AT TIME ZONE 'America/Santiago')::date=%s ORDER BY d.inicio''', (ACTIVAS,g.cuenta['id'],fecha))
        for cita in citas:
            cita['inicio_local']=cita['fecha_hora'].astimezone(CHILE)
        for turno in turnos:
            turno['inicio_local']=turno['inicio'].astimezone(CHILE)
        return render_template('clinica_agenda_doctor.html',fecha=fecha,citas=citas,turnos=turnos,hoy=datetime.now(CHILE).date())

    @bp.post('/doctor/agenda/turnos/<int:turno_id>/alternar')
    @requiere('doctor')
    def alternar_turno(turno_id):
        with db():
            with db().cursor() as cursor:
                cursor.execute('''SELECT id,inicio FROM public.disponibilidad_doctores
                    WHERE id=%s AND doctor_id=%s FOR UPDATE''',(turno_id,g.cuenta['id']))
                turno = cursor.fetchone()
                if not turno:
                    abort(404)
                if turno[1] <= datetime.now(CHILE):
                    abort(409,'Este turno ya comenzó y no se puede modificar. Elige un horario futuro.')
                caducar(cursor,disponibilidad_id=turno_id)
                cursor.execute('SELECT id FROM public.citas WHERE disponibilidad_id=%s AND estado IN %s',(turno_id,ACTIVAS))
                if cursor.fetchone():
                    abort(409,'No se puede deshabilitar un turno ocupado.')
                cursor.execute('UPDATE public.disponibilidad_doctores SET habilitada=NOT habilitada WHERE id=%s',(turno_id,))
        return redirect(url_for('clinica.agenda_doctor',fecha=request.form.get('fecha')))

    @bp.post('/doctor/agenda/citas/<int:cita_id>/estado')
    @requiere('doctor')
    def estado_cita(cita_id):
        estado=request.form.get('estado')
        if estado not in ('realizada','no_asistio'):
            abort(400)
        with db():
            with db().cursor() as cursor:
                cursor.execute('''UPDATE public.citas SET estado=%s WHERE id=%s AND doctor_id=%s
                    AND estado='confirmada' AND fecha_hora<=CURRENT_TIMESTAMP RETURNING id''', (estado,cita_id,g.cuenta['id']))
                if not cursor.fetchone():
                    abort(409,'Solo puedes cerrar una cita propia, confirmada y cuyo horario ya comenzó.')
        return redirect(url_for('clinica.agenda_doctor',fecha=request.form.get('fecha')))

    @bp.post('/doctor/agenda/citas/<int:cita_id>/incorporar')
    @requiere('doctor')
    def incorporar(cita_id):
        password=request.form.get('password','')
        with db():
            with db().cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('''SELECT p.id,p.password_hash FROM public.citas c
                    JOIN public.pacientes p ON p.id=c.paciente_id WHERE c.id=%s AND c.doctor_id=%s
                    AND c.estado IN ('confirmada','realizada')
                    AND EXISTS(SELECT 1 FROM public.pagos pa WHERE pa.cita_id=c.id AND pa.estado='aprobado')
                    FOR UPDATE OF p''',(cita_id,g.cuenta['id']))
                paciente=cursor.fetchone()
                if not paciente:
                    abort(403,'La cuenta solo puede habilitarse desde una cita propia confirmada con pago aprobado.')
                if not paciente['password_hash']:
                    if len(password)<12:
                        abort(400,'La contraseña debe tener al menos 12 caracteres.')
                    cursor.execute('UPDATE public.pacientes SET password_hash=%s WHERE id=%s',(generate_password_hash(password),paciente['id']))
                cursor.execute('INSERT INTO public.doctor_paciente VALUES (%s,%s) ON CONFLICT DO NOTHING',(g.cuenta['id'],paciente['id']))
        flash('Paciente incorporado a OncoPredict. Si ya tenía acceso, su contraseña se conservó.')
        return redirect(url_for('ficha_doctor',paciente_id=paciente['id']))

    @app.cli.command('expirar-reservas')
    def expirar_reservas():
        """Libera reservas vencidas; también se revisan al consultar y reservar."""
        with db():
            with db().cursor() as cursor:
                caducar(cursor)
                cantidad=cursor.rowcount
        click.echo(f'Reservas expiradas: {cantidad}')

    @app.cli.command('diagnosticar-reserva')
    @click.option('--rut', prompt='RUT usado en la reserva')
    @click.option('--correo', prompt='Correo usado en la reserva')
    def diagnosticar_reserva(rut, correo):
        """Consulta de solo lectura en la MISMA conexión que utiliza la aplicación."""
        rut = normalizar_rut(rut)
        correo = correo.strip().lower()
        conexion = filas('''SELECT current_database() AS base,
            inet_server_addr()::text AS servidor, inet_server_port() AS puerto''', una=True)
        conteos = filas('''SELECT
            count(*) FILTER (WHERE rut=%s AND lower(correo)=%s) AS exactas,
            count(*) FILTER (WHERE regexp_replace(upper(btrim(rut)), '[.[:space:]]', '', 'g')=%s) AS por_rut,
            count(*) FILTER (WHERE lower(btrim(correo))=%s) AS por_correo,
            count(*) FILTER (WHERE regexp_replace(upper(btrim(rut)), '[.[:space:]]', '', 'g')=%s
                AND lower(btrim(correo))=%s) AS conjuntas
            FROM public.pacientes''', (rut,correo,rut,correo,rut,correo), una=True)
        click.echo(f"Base de la aplicación: {conexion['base']} | servidor: {conexion['servidor']} | puerto: {conexion['puerto']}")
        click.echo(f"Coincidencias exactas con la búsqueda anterior: {conteos['exactas']}")
        click.echo(f"Por RUT normalizado: {conteos['por_rut']} | por correo normalizado: {conteos['por_correo']} | ambas en la misma ficha: {conteos['conjuntas']}")
        click.echo('No se modificaron datos. Compara la base, el servidor y el puerto con los de pgAdmin.')

    from webpay_prueba import registrar_webpay
    registrar_webpay(bp, db, reserva_id_actual)
    app.register_blueprint(bp)
