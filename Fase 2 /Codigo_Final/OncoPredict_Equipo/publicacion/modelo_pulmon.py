"""Entrada validada y salida técnica del prototipo académico de pulmón."""
from functools import lru_cache
from math import isfinite
from pathlib import Path


BASE = Path(__file__).resolve().parent
VARIABLES = (
    'Age', 'Gender', 'Smoker', 'Years_of_Smoking', 'Cigarettes_per_Day',
    'Passive_Smoker', 'Family_History', 'Air_Pollution_Exposure',
    'Occupational_Exposure', 'Indoor_Pollution', 'Healthcare_Access',
)
CATEGORIAS = {
    'Gender': {'Female', 'Male'},
    'Smoker': {'No', 'Yes'},
    'Passive_Smoker': {'No', 'Yes'},
    'Family_History': {'No', 'Yes'},
    'Air_Pollution_Exposure': {'Low', 'Medium', 'High'},
    'Occupational_Exposure': {'No', 'Yes'},
    'Indoor_Pollution': {'No', 'Yes'},
    'Healthcare_Access': {'Poor', 'Good'},
}


def validar_entrada_pulmon(formulario, edad_paciente):
    """Acepta solo las variables previas a un posible diagnóstico."""
    errores = []
    try:
        edad = int(edad_paciente)
        anios = int(formulario.get('Years_of_Smoking', ''))
        cigarrillos = int(formulario.get('Cigarettes_per_Day', ''))
    except (TypeError, ValueError):
        return None, ['Edad, años fumando y cigarrillos por día deben ser números enteros.']
    if not 18 <= edad <= 100:
        errores.append('La edad debe estar entre 18 y 100 años para esta evaluación experimental.')
    if not 0 <= anios <= min(80, edad):
        errores.append('Los años fumando deben estar entre 0 y la edad del paciente.')
    if not 0 <= cigarrillos <= 100:
        errores.append('Los cigarrillos por día deben estar entre 0 y 100.')
    datos = {'Age': edad, 'Years_of_Smoking': anios, 'Cigarettes_per_Day': cigarrillos}
    for clave, permitidos in CATEGORIAS.items():
        valor = formulario.get(clave, '')
        if valor not in permitidos:
            errores.append(f'Selecciona un valor válido para {clave}.')
        else:
            datos[clave] = valor
    if datos.get('Smoker') == 'No' and (anios != 0 or cigarrillos != 0):
        errores.append('Si no fuma, años fumando y cigarrillos por día deben ser 0.')
    if datos.get('Smoker') == 'Yes' and (anios == 0 or cigarrillos == 0):
        errores.append('Si fuma, indica años fumando y cigarrillos por día mayores que 0.')
    return (None, errores) if errores else (datos, [])


@lru_cache(maxsize=1)
def cargar_modelo_pulmon():
    import joblib

    archivo = BASE / 'modelo_pulmon_demo.joblib'
    if not archivo.is_file():
        raise FileNotFoundError(f'Falta el modelo de pulmón: {archivo}')
    artefacto = joblib.load(archivo)
    if not isinstance(artefacto, dict) or tuple(artefacto.get('variables', ())) != VARIABLES:
        raise ValueError('Las variables del modelo de pulmón no coinciden con el formulario.')
    modelo = artefacto['modelo']
    if 'Yes' not in modelo.classes_:
        raise ValueError('El modelo no contiene la clase positiva esperada.')
    umbral = float(artefacto['umbral'])
    if not isfinite(umbral) or not 0 < umbral < 1:
        raise ValueError('El umbral del modelo no es válido.')
    return modelo, umbral


def evaluar_pulmon(datos):
    """Devuelve puntaje técnico, umbral y etiqueta de apoyo; no diagnóstico."""
    import pandas as pd

    modelo, umbral = cargar_modelo_pulmon()
    fila = pd.DataFrame([{clave: datos[clave] for clave in VARIABLES}], columns=VARIABLES)
    indice_positivo = list(modelo.classes_).index('Yes')
    puntaje = float(modelo.predict_proba(fila)[0][indice_positivo])
    if not isfinite(puntaje) or not 0 <= puntaje <= 1:
        raise ValueError('El modelo devolvió un puntaje inválido.')
    resultado = ('Señal positiva para revisión' if puntaje >= umbral
                 else 'Sin señal positiva en el modelo')
    return puntaje, umbral, resultado
