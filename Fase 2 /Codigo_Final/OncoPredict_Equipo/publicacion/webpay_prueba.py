"""Webpay Plus, exclusivamente en el ambiente de integración."""
import json
import os
import re
import secrets
from urllib.error import URLError
from urllib.request import Request, urlopen

from flask import abort, flash, redirect, render_template, request, session, url_for
from psycopg2.extras import RealDictCursor


ORIGEN = 'https://webpay3gint.transbank.cl'
API = ORIGEN + '/rswebpaytransaction/api/webpay/v1.2/transactions/'
FORMULARIO = ORIGEN + '/webpayserver/initTransaction'
PROVEEDOR = 'webpay_prueba'


class WebpayError(Exception):
    pass


def consultar_webpay(metodo, token='', datos=None):
    if token and not re.fullmatch(r'[0-9a-fA-F]{64}', token):
        raise WebpayError('Token inválido')
    req = Request(API + token, method=metodo,
                  data=json.dumps(datos).encode() if datos is not None else None,
                  headers={'Content-Type': 'application/json', 'Tbk-Api-Key-Id': '597055555532',
                           'Tbk-Api-Key-Secret': '579B532A7440BB0C9079DED94D31EA1615BACEB56610332264630D42D0A36B1C'})
    try:
        with urlopen(req, timeout=8) as respuesta:
            resultado = json.load(respuesta)
    except (URLError, OSError, ValueError) as error:
        raise WebpayError('Transbank no devolvió una respuesta utilizable') from error
    if not isinstance(resultado, dict):
        raise WebpayError('Respuesta inesperada')
    return resultado


def registrar_webpay(bp, db, reserva_id_actual=None):
    @bp.app_context_processor
    def datos_webpay():
        try:
            monto = int(os.getenv('WEBPAY_MONTO_PRUEBA', '1000'))
        except ValueError:
            monto = 0
        return {'webpay_habilitado': os.getenv('WEBPAY_PRUEBA') == '1' and 0 < monto <= 1000000,
                'webpay_monto': monto}

    @bp.post('/webpay/iniciar')
    def webpay_iniciar():
        config = datos_webpay()
        cita_id = session.get('reserva_clinica') or (reserva_id_actual() if reserva_id_actual else None)
        if not config['webpay_habilitado'] or not cita_id:
            abort(404)
        session['reserva_clinica'] = cita_id
        retorno = os.getenv('WEBPAY_URL_RETORNO', 'http://127.0.0.1:5000/webpay/retorno')
        try:
            with db():
                with db().cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute('''SELECT id FROM public.citas WHERE id=%s AND estado='pendiente'
                        AND reserva_vence_en>clock_timestamp() AND fecha_hora>clock_timestamp() FOR UPDATE''', (cita_id,))
                    if not cursor.fetchone():
                        abort(409, 'La reserva ya no está disponible para pagar.')
                    cursor.execute('''SELECT referencia_proveedor,monto,estado FROM public.pagos
                        WHERE cita_id=%s AND proveedor=%s AND estado IN ('pendiente','aprobado')
                        ORDER BY id DESC LIMIT 1''', (cita_id, PROVEEDOR))
                    pago = cursor.fetchone()
                    if pago and pago['estado'] == 'aprobado':
                        abort(409, 'Ya existe un pago aprobado para esta reserva.')
                    if not pago:
                        orden = 'CL' + secrets.token_hex(12)
                        monto = config['webpay_monto']
                        resultado = consultar_webpay('POST', datos={'buy_order': orden,
                            'session_id': str(cita_id), 'amount': monto, 'return_url': retorno})
                        token = resultado.get('token', '')
                        if resultado.get('url') != FORMULARIO or not isinstance(token, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', token):
                            raise WebpayError('Respuesta de inicio inválida')
                        cursor.execute('''INSERT INTO public.pagos
                            (cita_id,orden_comercio,proveedor,referencia_proveedor,monto)
                            VALUES (%s,%s,%s,%s,%s)''', (cita_id,orden,PROVEEDOR,token,monto))
                        pago = {'referencia_proveedor': token, 'monto': monto}
        except WebpayError:
            flash('No se pudo iniciar Webpay de prueba. Inténtalo de nuevo mientras la reserva esté vigente.')
            return redirect(url_for('clinica.reserva_pendiente'))
        return render_template('webpay_prueba.html', formulario=FORMULARIO, pago=pago, mensaje=None)

    @bp.route('/webpay/retorno', methods=['GET','POST'])
    def webpay_retorno():
        token = request.values.get('token_ws') or request.values.get('TBK_TOKEN', '')
        if not re.fullmatch(r'[0-9a-fA-F]{64}', token):
            return render_template('webpay_prueba.html', mensaje='Webpay no devolvió una referencia de pago válida.'), 400
        try:
            with db():
                with db().cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute('SELECT cita_id FROM public.pagos WHERE proveedor=%s AND referencia_proveedor=%s', (PROVEEDOR,token))
                    fila = cursor.fetchone()
                    if not fila:
                        abort(404)
                    # Mismo orden de bloqueo que en el inicio del pago.
                    cursor.execute('SELECT estado FROM public.citas WHERE id=%s FOR UPDATE', (fila['cita_id'],))
                    cursor.execute('SELECT * FROM public.pagos WHERE proveedor=%s AND referencia_proveedor=%s FOR UPDATE', (PROVEEDOR,token))
                    pago = cursor.fetchone()
                    if pago['estado'] == 'pendiente':
                        resultado = consultar_webpay('GET', token)
                        if resultado.get('status') == 'INITIALIZED' and request.values.get('token_ws'):
                            try:
                                resultado = consultar_webpay('PUT', token, {})
                            except WebpayError:
                                resultado = consultar_webpay('GET', token)
                        estado = resultado.get('status')
                        if (resultado.get('buy_order') != pago['orden_comercio']
                            or resultado.get('amount') != pago['monto']
                            or resultado.get('session_id') != str(pago['cita_id'])):
                            raise WebpayError('La respuesta no corresponde al pago guardado')
                        if estado == 'AUTHORIZED' and resultado.get('response_code') == 0:
                            cursor.execute('''UPDATE public.pagos SET estado='aprobado', actualizado_en=now(),
                                aprobado_en=now(), codigo_autorizacion=%s WHERE id=%s''', (resultado.get('authorization_code'),pago['id']))
                            cursor.execute('''UPDATE public.citas SET estado='confirmada' WHERE id=%s AND estado='pendiente'
                            
                                AND reserva_vence_en>clock_timestamp() AND fecha_hora>clock_timestamp()''', (pago['cita_id'],))
                            if cursor.rowcount == 1:
                                cursor.execute("""
                                INSERT INTO public.notificaciones (cita_id,destinatario,tipo,clave_evento)SELECT c.id,trim(p.correo),'confirmacion_cita',
                                'confirmacion_cita:' || c.id::text FROM public.citas c JOIN public.pacientes p ON p.id = c.paciente_id
                                WHERE c.id = %s
                                ON CONFLICT (clave_evento) DO NOTHING """,
                                (pago['cita_id'],),
                                )
                            pago['estado'] = 'aprobado'
                        elif estado in ('FAILED','REVERSED','NULLIFIED'):
                            cursor.execute("UPDATE public.pagos SET estado='rechazado',actualizado_en=now() WHERE id=%s", (pago['id'],))
                            pago['estado'] = 'rechazado'
                    cursor.execute('SELECT estado,disponibilidad_id FROM public.citas WHERE id=%s', (pago['cita_id'],))
                    cita = cursor.fetchone()
        except WebpayError:
            return render_template('webpay_prueba.html', mensaje='No pudimos verificar el resultado con Transbank. Recarga esta página para volver a consultar.'), 503
        if pago['estado'] == 'aprobado':
            mensaje = ('Pago de prueba aprobado. Tu cita está confirmada.' if cita['estado'] in ('confirmada','realizada','no_asistio')
                       else 'El pago de prueba fue aprobado, pero la reserva ya no estaba vigente. Contacta a la clínica para revisar el caso.')
        elif pago['estado'] == 'rechazado':
            mensaje = 'El pago de prueba fue rechazado. La cita no se confirmó.'
        else:
            mensaje = 'El pago de prueba sigue sin confirmación. Puedes consultar su resultado recargando esta página.'
        return render_template('webpay_prueba.html', mensaje=mensaje, orden=pago['orden_comercio'], monto=pago['monto'],
                               disponibilidad_id=cita['disponibilidad_id'],
                               reserva_completada=cita['estado'] in ('confirmada','realizada','no_asistio'))
