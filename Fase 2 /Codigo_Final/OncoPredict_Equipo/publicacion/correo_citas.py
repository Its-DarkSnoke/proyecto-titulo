import os
import smtplib
import ssl
from email.message import EmailMessage

import click
from flask.cli import with_appcontext
from psycopg2.extras import RealDictCursor


@click.command('enviar-confirmacion')
@with_appcontext
def enviar_confirmacion():
    """Envía el siguiente correo de confirmación pendiente."""
    from portal import db

    servidor = os.getenv('SMTP_HOST')
    usuario = os.getenv('SMTP_USER')
    clave = os.getenv('SMTP_PASSWORD')
    remitente = os.getenv('SMTP_FROM') or usuario

    if not all((servidor, usuario, clave, remitente)):
        raise click.ClickException(
            'Configura SMTP_HOST, SMTP_USER y SMTP_PASSWORD en .env.'
        )

    fallo = False

    with db() as conexion:
        with conexion.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    n.id,
                    n.destinatario,
                    c.id AS cita_id,
                    c.fecha_hora AT TIME ZONE 'America/Santiago' AS hora_local,
                    d.nombre AS doctor
                FROM public.notificaciones n
                JOIN public.citas c ON c.id = n.cita_id
                JOIN public.doctores d ON d.id = c.doctor_id
                WHERE n.tipo = 'confirmacion_cita'
                  AND n.estado IN ('pendiente', 'fallida')
                  AND n.proximo_intento_en <= CURRENT_TIMESTAMP
                  AND n.intentos < 5
                  AND c.estado = 'confirmada'
                  AND c.fecha_hora > CURRENT_TIMESTAMP
                ORDER BY n.proximo_intento_en, n.id
                LIMIT 1
                FOR UPDATE OF n SKIP LOCKED
                """
            )
            aviso = cursor.fetchone()

            if aviso is None:
                click.echo('No hay confirmaciones listas para enviar.')
                return

            fecha = aviso['hora_local'].strftime('%d/%m/%Y a las %H:%M')
            mensaje = EmailMessage()
            mensaje['From'] = remitente
            mensaje['To'] = aviso['destinatario']
            mensaje['Subject'] = f"Confirmación de cita #{aviso['cita_id']}"
            mensaje.set_content(
                f"Tu cita #{aviso['cita_id']} está confirmada.\n\n"
                f"Profesional: {aviso['doctor']}\n"
                f"Fecha y hora: {fecha} (hora de Santiago)\n\n"
                f"{os.getenv('CLINICA_NOMBRE', 'Clínica Onco')}"
            )

            try:
                with smtplib.SMTP(servidor, 587, timeout=15) as smtp:
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.login(usuario, clave)
                    smtp.send_message(mensaje)
            except (OSError, smtplib.SMTPException):
                fallo = True
                cursor.execute(
                    """
                    UPDATE public.notificaciones
                    SET estado = 'fallida',
                        intentos = intentos + 1,
                        ultimo_error = 'Falló el envío SMTP',
                        proximo_intento_en = CURRENT_TIMESTAMP
                            + INTERVAL '5 minutes'
                    WHERE id = %s
                    """,
                    (aviso['id'],),
                )
            else:
                cursor.execute(
                    """
                    UPDATE public.notificaciones
                    SET estado = 'enviada',
                        intentos = intentos + 1,
                        enviada_en = CURRENT_TIMESTAMP,
                        ultimo_error = NULL
                    WHERE id = %s
                    """,
                    (aviso['id'],),
                )

    if fallo:
        raise click.ClickException(
            'Falló el envío SMTP. Revisa la configuración. '
            'El aviso podrá reintentarse en cinco minutos, hasta cinco intentos.'
        )

    click.echo(f"El servidor SMTP aceptó el correo de la cita #{aviso['cita_id']}.")