"""Resumen del historial propio de un doctor. No carga ni modifica el modelo."""
from datetime import datetime, timezone

MESES = ('Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic')


def resumen_mama(consultar, doctor_id, ahora=None):
    # Los meses se agrupan en UTC, tanto en Python como en PostgreSQL.
    ahora = ahora or datetime.now(timezone.utc)
    indice = ahora.year * 12 + ahora.month - 1
    meses = []
    for n in range(indice - 5, indice + 1):
        anio, mes = divmod(n, 12)
        meses.append({'clave': f'{anio:04d}-{mes + 1:02d}',
                      'etiqueta': f'{MESES[mes]} {anio}', 'total': 0, 'publicadas': 0})
    inicio = datetime(int(meses[0]['clave'][:4]), int(meses[0]['clave'][5:]), 1, tzinfo=timezone.utc)
    siguiente_anio, siguiente_mes = divmod(indice + 1, 12)
    fin = datetime(siguiente_anio, siguiente_mes + 1, 1, tzinfo=timezone.utc)
    # La relación de atención se verifica también en las consultas del resumen.
    filtro = """e.doctor_id=%s AND e.tipo='mama' AND EXISTS (
        SELECT 1 FROM doctor_paciente dp
        WHERE dp.doctor_id=e.doctor_id AND dp.paciente_id=e.paciente_id)"""
    totales = dict(consultar(f"""SELECT count(*) AS total,
        count(DISTINCT e.paciente_id) AS pacientes_evaluados,
        count(*) FILTER (WHERE e.publicada) AS publicadas,
        count(*) FILTER (WHERE NOT e.publicada) AS borradores,
        count(*) FILTER (WHERE e.resultado='ANOMALÍA MALIGNA') AS malignas,
        count(*) FILTER (WHERE e.resultado='ANOMALÍA BENIGNA') AS benignas,
        count(*) FILTER (WHERE e.resultado NOT IN ('ANOMALÍA MALIGNA','ANOMALÍA BENIGNA')) AS otros
        FROM evaluaciones e WHERE {filtro}""", (doctor_id,), una=True))
    actividad = consultar(f"""SELECT to_char(e.creada_en AT TIME ZONE 'UTC','YYYY-MM') AS mes,
        count(*) AS total, count(*) FILTER (WHERE e.publicada) AS publicadas
        FROM evaluaciones e WHERE {filtro} AND e.creada_en >= %s AND e.creada_en < %s
        GROUP BY 1 ORDER BY 1""", (doctor_id, inicio, fin))
    por_mes = {fila['mes']: fila for fila in actividad}
    maximo = max((fila['total'] for fila in actividad), default=0)
    for mes in meses:
        if mes['clave'] in por_mes:
            mes.update(total=por_mes[mes['clave']]['total'], publicadas=por_mes[mes['clave']]['publicadas'])
        mes['borradores'] = mes['total'] - mes['publicadas']
        mes['altura_publicadas'] = round(mes['publicadas'] * 100 / maximo, 3) if maximo else 0
        mes['altura_borradores'] = round(mes['borradores'] * 100 / maximo, 3) if maximo else 0
    total = totales['total']
    categorias = []
    for clave, etiqueta, clase in [('benignas','Anomalía benigna','benigna'),
                                  ('malignas','Anomalía maligna','maligna'),
                                  ('otros','Otros resultados','otros')]:
        cantidad = totales[clave]
        categorias.append({'etiqueta': etiqueta, 'cantidad': cantidad, 'clase': clase,
                           'porcentaje': round(cantidad * 100 / total, 1) if total else 0})
    recientes = consultar(f"""SELECT e.id,e.paciente_id,e.resultado,e.publicada,
        e.creada_en AT TIME ZONE 'UTC' AS creada_en,p.nombre
        FROM evaluaciones e JOIN pacientes p ON p.id=e.paciente_id
        WHERE {filtro} ORDER BY e.creada_en DESC,e.id DESC LIMIT 5""", (doctor_id,))
    return {'totales':totales, 'meses':meses, 'categorias':categorias,
            'recientes':recientes, 'maximo':maximo,
            'actividad_total':sum(m['total'] for m in meses),
            'actualizado':ahora.strftime('%d/%m/%Y %H:%M UTC')}
