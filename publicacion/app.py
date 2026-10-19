from flask import Flask, render_template, request, session, redirect, url_for
from database import conectar_db
from werkzeug.security import check_password_hash, generate_password_hash
from markupsafe import escape
from validaciones import validar_paciente
import joblib
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name('.env'))

app = Flask(__name__)
app.secret_key = os.environ['SECRET_KEY']
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                  SESSION_COOKIE_SECURE=os.getenv('RENDER') == 'true')

# Cargar el modelo
try:
    modelo_rf = joblib.load(Path(__file__).with_name('modelo_cancer.pkl'))
except Exception as e:
    print(f"Advertencia: No se pudo cargar el modelo. Error: {e}")
    modelo_rf = None


@app.route('/')
def inicio():
    if 'usuario' in session:
        return redirect(url_for('dashboard'))

    return render_template('login.html')


@app.route('/login', methods=['POST'])
def procesar_login():
    correo_ingresado = request.form['correo']
    password_ingresada = request.form['password']

    conexion = conectar_db()

    if conexion is None:
        return "Error de conexión."

    try:
        cursor = conexion.cursor()

        consulta = "SELECT password_hash FROM usuarios WHERE correo = %s"
        cursor.execute(consulta, (correo_ingresado,))
        usuario = cursor.fetchone()

        cursor.close()
        conexion.close()

        if usuario and check_password_hash(usuario[0], password_ingresada):
            session['usuario'] = correo_ingresado
            return redirect(url_for('dashboard'))

        return "Error: Correo o contraseña incorrectos."

    except Exception as e:
        return f"Hubo un error: {e}"


@app.route('/dashboard')
def dashboard():
    if 'usuario' not in session:
        return redirect(url_for('inicio'))

    return render_template(
        'dashboard.html',
        correo_medico=session['usuario']
    )


@app.route('/predecir', methods=['POST'])
def predecir():
    if 'usuario' not in session:
        return redirect(url_for('inicio'))

    # Validar antes de convertir datos o ejecutar el modelo
    datos, errores = validar_paciente(request.form)

    if errores:
        return render_template(
            'dashboard.html',
            correo_medico=session['usuario'],
            errores=errores,
            valores=request.form
        ), 400

    rut = escape(datos['rut'])
    nombre = escape(datos['nombre'])
    edad = datos['edad']

    radio = datos['radio_medio']
    textura = datos['textura_media']
    perimetro = datos['perimetro_medio']
    area = datos['area_media']

    if modelo_rf is None:
        return "Error: No se pudo cargar el archivo modelo_cancer.pkl."

    vector_entrada = [[radio, textura, perimetro, area]]
    prediccion_num = modelo_rf.predict(vector_entrada)[0]

    # Se conserva la interpretación de clases de tu código original.
    if prediccion_num == 0:
        diagnostico = "ANOMALÍA MALIGNA"
        color_alerta = "#dc3545"
    else:
        diagnostico = "ANOMALÍA BENIGNA"
        color_alerta = "#28a745"

    return f"""
    <div style="font-family: Arial; padding: 40px;">
        <h2 style="color: {color_alerta};">
            Diagnóstico Calculado: {diagnostico}
        </h2>

        <p>
            <strong>Paciente:</strong> {nombre} (RUT: {rut})
        </p>

        <p>
            <strong>Vector analizado:</strong>
            [Radio: {radio}, Textura: {textura},
            Perímetro: {perimetro}, Área: {area}]
        </p>

        <br>

        <a href="/dashboard"
           style="background: #0056b3; color: white;
                  padding: 10px 15px; text-decoration: none;
                  border-radius: 4px;">
            Volver al Panel Médico
        </a>
    </div>
    """


@app.route('/logout')
def logout():
    session.pop('usuario', None)
    return redirect(url_for('inicio'))


@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'GET':
        return render_template('registro.html')

    correo_nuevo = request.form['correo']
    password_nueva = request.form['password']
    hash_seguro = generate_password_hash(password_nueva)

    conexion = conectar_db()

    try:
        cursor = conexion.cursor()

        cursor.execute(
            "INSERT INTO usuarios (correo, password_hash) VALUES (%s, %s)",
            (correo_nuevo, hash_seguro)
        )

        conexion.commit()

        cursor.close()
        conexion.close()

        return f"¡Cuenta creada para {escape(correo_nuevo)}! Ya puedes iniciar sesión."

    except Exception as e:
        return f"Error al registrar: {e}"


if __name__ == '__main__':
    app.run()
