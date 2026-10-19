import math
import re
import unicodedata


BIOMETRIAS = {
    'radio_medio': 'Radio medio',
    'textura_media': 'Textura media',
    'perimetro_medio': 'Perímetro medio',
    'area_media': 'Área media',
}


def rut_valido(rut):
    # Sin puntos, con guion y dígito verificador
    if not re.fullmatch(r'[1-9][0-9]{6,7}-[0-9K]', rut):
        return False

    cuerpo, dv = rut.split('-')

    total = sum(
        int(numero) * (2 + indice % 6)
        for indice, numero in enumerate(reversed(cuerpo))
    )

    resto = 11 - total % 11

    if resto == 11:
        esperado = '0'
    elif resto == 10:
        esperado = 'K'
    else:
        esperado = str(resto)

    return dv == esperado


def validar_paciente(formulario):
    datos = {}
    errores = {}

    # RUT
    rut = formulario.get('rut', '').strip().upper()

    if not rut_valido(rut):
        errores['rut'] = (
            'Ingresa un RUT válido sin puntos, con guion y '
            'dígito verificador correcto. Ej.: 12345678-5.'
        )

    datos['rut'] = rut

    # Nombre y apellido
    nombre = unicodedata.normalize(
        'NFC',
        formulario.get('nombre', '')
    )
    nombre = ' '.join(nombre.split())

    partes = re.split(r"[ '\-’]", nombre)

    if (
        not 3 <= len(nombre) <= 100
        or len(nombre.split()) < 2
        or any(not parte or not parte.isalpha() for parte in partes)
    ):
        errores['nombre'] = (
            'Ingresa nombre y apellido. Solo letras, espacios, '
            'guiones o apóstrofes; máximo 100 caracteres.'
        )

    datos['nombre'] = nombre

    # Edad
    edad = formulario.get('edad', '').strip()

    if (
        not re.fullmatch(r'[0-9]{1,3}', edad)
        or not 0 <= int(edad) <= 120
    ):
        errores['edad'] = (
            'La edad debe ser un número entero entre 0 y 120 años.'
        )
    else:
        datos['edad'] = int(edad)

    # Biometrías
    for campo, etiqueta in BIOMETRIAS.items():
        texto = formulario.get(campo, '').strip()

        if not re.fullmatch(r'[0-9]+(?:[.,][0-9]+)?', texto):
            errores[campo] = (
                f'{etiqueta}: ingresa un número positivo. '
                'Puedes usar punto o coma decimal.'
            )
            continue

        try:
            valor = float(texto.replace(',', '.'))
        except (ValueError, OverflowError):
            valor = math.inf

        if not math.isfinite(valor) or valor <= 0:
            errores[campo] = (
                f'{etiqueta}: el valor debe ser mayor que cero y finito.'
            )
        else:
            datos[campo] = valor

    return datos, errores