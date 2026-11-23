import subprocess
import sys
import time
from pathlib import Path


def main():
    carpeta = Path(__file__).resolve().parent
    comando = [
        sys.executable,
        "-m",
        "flask",
        "--app",
        "app",
        "enviar-confirmacion",
    ]

    print("Envío automático activo. Presiona Ctrl + C para detenerlo.")

    try:
        while True:
            subprocess.run(comando, cwd=carpeta, check=False)
            time.sleep(10)
    except KeyboardInterrupt:
        print("\nEnvío automático detenido.")


if __name__ == "__main__":
    main()