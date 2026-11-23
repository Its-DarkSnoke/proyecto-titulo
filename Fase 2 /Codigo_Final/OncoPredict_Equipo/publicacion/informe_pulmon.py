"""Generación de una ficha PDF de apoyo para la atención de pulmón."""
from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


CHILE = ZoneInfo('America/Santiago')
VERDE = colors.HexColor('#087c83')
GRIS = colors.HexColor('#657b85')
BORDE = colors.HexColor('#dce8e9')
VARIABLES = (
    ('Age', 'Edad'), ('Gender', 'Género'), ('Smoker', 'Fumador'),
    ('Years_of_Smoking', 'Años fumando'), ('Cigarettes_per_Day', 'Cigarrillos por día'),
    ('Passive_Smoker', 'Exposición pasiva'), ('Family_History', 'Antecedentes familiares'),
    ('Air_Pollution_Exposure', 'Contaminación del aire'),
    ('Occupational_Exposure', 'Exposición ocupacional'),
    ('Indoor_Pollution', 'Contaminación interior'),
    ('Healthcare_Access', 'Acceso a atención de salud'),
)
VALORES_ES = {'Female': 'Mujer', 'Male': 'Hombre', 'Yes': 'Sí', 'No': 'No',
              'Low': 'Baja', 'Medium': 'Media', 'High': 'Alta',
              'Poor': 'Limitado', 'Good': 'Bueno'}


def generar_informe_pulmon(paciente, doctor, evaluacion=None):
    """Construye el PDF en memoria para un paciente ya autorizado por la ruta."""
    salida = BytesIO()
    doc = SimpleDocTemplate(salida, pagesize=A4, leftMargin=19*mm, rightMargin=19*mm,
                            topMargin=16*mm, bottomMargin=16*mm, title='Ficha de apoyo - pulmón')
    estilos = getSampleStyleSheet()
    estilos.add(ParagraphStyle(name='OncoTitulo', parent=estilos['Title'], fontName='Helvetica-Bold',
                               fontSize=18, leading=22, textColor=VERDE, spaceAfter=7))
    estilos.add(ParagraphStyle(name='OncoSeccion', parent=estilos['Heading2'], fontSize=11,
                               leading=14, textColor=VERDE, spaceBefore=13, spaceAfter=7))
    estilos.add(ParagraphStyle(name='OncoTexto', parent=estilos['BodyText'], fontSize=9, leading=13))
    estilos.add(ParagraphStyle(name='OncoNota', parent=estilos['BodyText'], fontSize=8,
                               leading=12, textColor=GRIS))

    def par(valor, estilo='OncoTexto'):
        return Paragraph(escape(str(valor if valor is not None else 'No registrado')), estilos[estilo])

    def tabla(filas):
        t = Table([[par(k, 'OncoNota'), par(v)] for k, v in filas], colWidths=[51*mm, 119*mm])
        t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 3.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
            ('LINEBELOW', (0, 0), (-1, -1), .4, BORDE),
        ]))
        return t

    hoy = datetime.now(CHILE).strftime('%d/%m/%Y %H:%M')
    contenido = [
        par('ONCOPREDICT · FICHA DE APOYO', 'OncoNota'), Spacer(1, 4*mm),
        par('Evaluación de pulmón', 'OncoTitulo'),
        par(f'Generado el {hoy}, hora de Santiago.', 'OncoNota'), Spacer(1, 5*mm),
        HRFlowable(width='100%', thickness=1, color=BORDE),
        par('Paciente y profesional', 'OncoSeccion'),
        tabla([('Paciente', paciente['nombre']), ('RUT', paciente['rut']),
               ('Edad registrada', f"{paciente['edad']} años"), ('Correo', paciente['correo']),
               ('Doctor', doctor['nombre'])]),
        par('Factores registrados', 'OncoSeccion'),
    ]
    datos = evaluacion.get('datos') if evaluacion else None
    presentes = [(etiqueta, VALORES_ES.get(datos[clave], datos[clave]))
                 for clave, etiqueta in VARIABLES if isinstance(datos, dict) and clave in datos]
    contenido.append(tabla(presentes) if presentes else par('Aún no hay factores de pulmón registrados para este paciente.'))
    contenido.append(par('Resultado experimental', 'OncoSeccion'))
    contenido.append(par(evaluacion['resultado'] if evaluacion else 'Sin resultado del modelo registrado.'))
    if isinstance(datos, dict) and 'puntaje_modelo' in datos and 'umbral_modelo' in datos:
        contenido.append(par(f"Puntaje técnico: {datos['puntaje_modelo']:.3f} · "
                             f"Umbral aplicado: {datos['umbral_modelo']:.3f}"))
    contenido.extend([
        Spacer(1, 3*mm),
        par('El prototipo académico obtuvo 7 % de precisión y 66 % de recall para la clase positiva en prueba. '
            'Su salida no confirma ni descarta cáncer y no es una probabilidad clínica.', 'OncoNota'),
        par('Evaluación del doctor', 'OncoSeccion'),
        par('Hallazgos, exámenes revisados y plan de seguimiento:', 'OncoNota'),
        Spacer(1, 15*mm), HRFlowable(width='100%', thickness=.5, color=BORDE),
        Spacer(1, 7*mm), HRFlowable(width='100%', thickness=.5, color=BORDE),
        Spacer(1, 8*mm), par('Firma / identificación del doctor: ____________________________________'),
    ])

    def pie(canvas, pagina):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(GRIS)
        canvas.drawCentredString(A4[0]/2, 11*mm, f'OncoPredict · Proyecto académico · Página {pagina.page}')
        canvas.restoreState()

    doc.build(contenido, onFirstPage=pie, onLaterPages=pie)
    salida.seek(0)
    return salida
