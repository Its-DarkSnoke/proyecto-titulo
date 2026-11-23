"""Instala el parche sobre la etapa de agenda con la corrección de reservas."""
import ast
from datetime import datetime
from pathlib import Path
import shutil


def reemplazar(texto, anterior, nuevo, archivo):
    if texto.count(anterior) != 1:
        raise ValueError(f'{archivo} tiene una versión distinta. Se canceló la instalación.')
    return texto.replace(anterior, nuevo, 1)


def instalar(destino, origen):
    portal = destino / 'portal.py'
    clinica = destino / 'clinica.py'
    pendiente = destino / 'templates/clinica_pendiente.html'
    portada = destino / 'templates/clinica_inicio.html'
    archivos = [portal, clinica, pendiente, portada]
    textos = {p: p.read_text(encoding='utf-8-sig') for p in archivos}
    if "'clinica.webpay_retorno'" in textos[portal]:
        raise ValueError('Webpay ya está instalado en esta carpeta.')
    if 'diagnosticar-reserva' not in textos[clinica]:
        raise ValueError('Instala primero la corrección de reservas que incluye diagnosticar-reserva.')
    textos[portal] = reemplazar(textos[portal], "    if request.method == 'POST':\n        esperado = session.get('csrf', '')",
        "    if request.method == 'POST' and request.endpoint != 'clinica.webpay_retorno':\n        esperado = session.get('csrf', '')", portal.name)
    textos[portal] = reemplazar(textos[portal], "    if 'csrf' not in session:\n", "    if 'csrf' not in session and request.endpoint != 'clinica.webpay_retorno':\n", portal.name)
    textos[portal] = reemplazar(textos[portal], "'csrf': session['csrf']", "'csrf': session.get('csrf')", portal.name)
    textos[clinica] = reemplazar(textos[clinica], '    app.register_blueprint(bp)',
        '    from webpay_prueba import registrar_webpay\n    registrar_webpay(bp, db)\n    app.register_blueprint(bp)', clinica.name)
    aviso = 'Esta etapa no incluye la pasarela de pago ni el correo. Una reserva pendiente no equivale a una cita confirmada.'
    boton = '''{% if webpay_habilitado and cita.estado == 'pendiente' %}
    <p>Completa el pago de prueba antes del vencimiento de la reserva.</p>
    <form method="post" action="{{ url_for('clinica.webpay_iniciar') }}">
      <input type="hidden" name="csrf" value="{{ csrf }}">
      <button class="web-boton">Ir a Webpay de prueba</button>
    </form>
    {% elif cita.estado == 'pendiente' %}<p>La reserva está pendiente de pago.</p>{% endif %}'''
    textos[pendiente] = reemplazar(textos[pendiente], f'<div class="web-alerta">{aviso}</div>', boton, pendiente.name)
    aviso = 'Versión de desarrollo: el pago y el envío de correos están pendientes de integración. Las reservas de esta versión no se confirman ni generan cobros.'
    textos[portada] = reemplazar(textos[portada], aviso,
        "{% if webpay_habilitado %}Agenda con Webpay en ambiente de pruebas. Usa las tarjetas de integración para probar la confirmación de citas.{% else %}Las reservas quedan pendientes mientras se habilita el pago de prueba.{% endif %}", portada.name)
    reserva = destino / 'templates/clinica_reservar.html'
    textos[reserva] = reemplazar(reserva.read_text(encoding='utf-8-sig'),
        'El pago aún no está integrado. Esta reserva no confirma una cita, no genera cobros y vencerá a los 15 minutos.',
        'El horario se retiene durante 15 minutos. {% if webpay_habilitado %}Completa el pago de prueba dentro de ese plazo.{% else %}La reserva queda pendiente de pago.{% endif %}', reserva.name)
    agenda = destino / 'templates/clinica_agenda_doctor.html'
    textos[agenda] = reemplazar(agenda.read_text(encoding='utf-8-sig'),
        'Los pagos y correos se conectarán en la siguiente etapa. No se pueden confirmar citas manualmente desde esta pantalla. La incorporación requiere una cita confirmada cuyo horario ya comenzó.',
        'Las citas se confirman al verificar un pago de prueba aprobado. La incorporación requiere una cita confirmada cuyo horario ya comenzó.', agenda.name)
    for p in (portal, clinica):
        ast.parse(textos[p])
    nuevos = {destino / nombre: (origen / nombre).read_text(encoding='utf-8')
              for nombre in ('webpay_prueba.py','templates/webpay_prueba.html')}
    ast.parse(nuevos[destino / 'webpay_prueba.py'])
    if any(p.exists() and p.read_text(encoding='utf-8') != texto for p, texto in nuevos.items()):
        raise ValueError('Ya existen archivos de Webpay. Revisa la instalación anterior.')
    respaldo = destino / ('respaldo_webpay_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    for p in textos:
        copia = respaldo / p.relative_to(destino)
        copia.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, copia)
    for p, texto in {**textos, **nuevos}.items():
        p.write_text(texto, encoding='utf-8')
    return respaldo


if __name__ == '__main__':
    try:
        respaldo = instalar(Path.cwd(), Path(__file__).resolve().parent)
    except (OSError, ValueError, SyntaxError) as error:
        raise SystemExit(str(error)) from None
    print('Webpay de prueba instalado. Respaldo:', respaldo.name)
