from threading import Event, Thread

from click import ClickException

from portal import app


def procesar_correos(detener):
    while not detener.is_set():
        try:
            with app.app_context():
                app.cli.main(
                    args=["enviar-confirmacion"],
                    standalone_mode=False,
                )
        except ClickException as error:
            app.logger.warning("Correo de confirmación: %s", error.format_message())
        except Exception:
            app.logger.exception("Error al procesar la cola de correos")

        detener.wait(10)


if __name__ == "__main__":
    detener = Event()
    trabajador = Thread(
        target=procesar_correos,
        args=(detener,),
        name="trabajador-correos",
        daemon=True,
    )
    trabajador.start()

    try:
        app.run(use_reloader=False)
    finally:
        detener.set()
