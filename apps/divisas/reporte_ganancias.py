"""Reporte de ganancias desglosado por período, divisa, tipo, canal y caja/turno (HU "Reporte de ganancias").

Complementa al tablero de control (``apps.divisas.ganancias``): el tablero
resume la ganancia con indicadores y gráficos; este reporte la desglosa en
una tabla, según un único criterio de agrupación elegido por el analista,
y la descarga en PDF y en Excel.

Para que el reporte y el tablero muestren **siempre** la misma ganancia
total para un mismo período (criterio 4), este módulo no recalcula nada por
su cuenta: toma las mismas filas normalizadas
(``apps.divisas.ganancias._todas_las_ganancias``), el mismo filtro por
fechas (``apps.divisas.ganancias._en_rango``) y el mismo total
(``apps.divisas.ganancias.calcular_indicadores``). Por lo tanto, la
definición de "ganancia" (la comisión, normalizada a PYG), de "tipo de
operación" (en la perspectiva de la casa de cambio) y de "completada"
(``ACREDITADA``/``RETIRADA`` online, toda operación de ventanilla) es
exactamente la documentada en ese módulo.

El desglose por caja y turno (criterio 2) es distinto de los demás: no
agrupa filas ya normalizadas sino que recorre las ``apps.caja.models.Caja``
del período (cada caja es un turno de un cajero) y suma sus operaciones de
ventanilla. Una caja todavía "Abierta" se marca como "en curso" y su
ganancia como parcial (criterio 3), porque puede seguir sumando operaciones.

``generar_reporte_ganancias`` es el único punto de entrada: lo usan la
pantalla (``apps.divisas.views.ReporteGananciasView``) y las dos descargas
(``apps.divisas.views.DescargarReporteGananciasView``), para que los tres
vean siempre los mismos datos con los mismos filtros (criterio 5).
"""

from collections import OrderedDict
from decimal import Decimal
from io import BytesIO

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.caja.models import Caja, OperacionVentanilla
from apps.divisas.ganancias import (
    CANAL_CHOICES,
    TIPO_CHOICES,
    _en_rango,
    _parsear_fecha,
    _todas_las_ganancias,
    calcular_indicadores,
)

AGRUPACION_DIA = 'dia'
AGRUPACION_MES = 'mes'
AGRUPACION_DIVISA = 'divisa'
AGRUPACION_TIPO = 'tipo'
AGRUPACION_CANAL = 'canal'
AGRUPACION_CAJA = 'caja'
AGRUPACIONES = OrderedDict([
    (AGRUPACION_DIA, 'Día'),
    (AGRUPACION_MES, 'Mes'),
    (AGRUPACION_DIVISA, 'Divisa'),
    (AGRUPACION_TIPO, 'Tipo de operación'),
    (AGRUPACION_CANAL, 'Canal'),
    (AGRUPACION_CAJA, 'Caja y turno'),
])
"""Criterios de agrupación disponibles (criterios 1 y 2), en el orden en que se ofrecen en pantalla."""

AGRUPACION_POR_DEFECTO = AGRUPACION_DIA

MENSAJE_SIN_DATOS = 'No hay operaciones completadas en el período elegido.'
"""Aviso que se muestra, en vez de un error, cuando el período no tiene operaciones (criterio 6)."""


def _validar_rango(fecha_desde, fecha_hasta):
    """Valida un rango de fechas ya parseado. Devuelve el motivo del error, o ``None`` si es válido.

    Usa los mismos mensajes que ``apps.divisas.ganancias.resolver_periodo``:
    la fecha inicial no puede ser posterior a la final ni ninguna de las dos
    puede estar en el futuro.
    """
    hoy = timezone.localdate()
    if fecha_desde > fecha_hasta:
        return 'La fecha inicial no puede ser posterior a la fecha final.'
    if fecha_desde > hoy or fecha_hasta > hoy:
        return 'No se puede consultar un rango con fechas futuras.'
    return None


def _clave_y_etiqueta(fila, agrupacion):
    """Clave ordenable y etiqueta legible del grupo al que pertenece ``fila`` según ``agrupacion``.

    - ``dia``: ``'YYYY-MM-DD'`` / ``'DD/MM/YYYY'``.
    - ``mes``: ``'YYYY-MM'`` / ``'MM/YYYY'``.
    - ``divisa``: el código (o el par ``ORIGEN → DESTINO`` de un cambio).
    - ``tipo`` y ``canal``: el código interno / su etiqueta en
      ``TIPO_CHOICES``/``CANAL_CHOICES``.
    """
    if agrupacion in (AGRUPACION_DIA, AGRUPACION_MES):
        fecha = timezone.localtime(fila['creado_en']).date()
        if agrupacion == AGRUPACION_DIA:
            return fecha.isoformat(), fecha.strftime('%d/%m/%Y')
        return fecha.strftime('%Y-%m'), fecha.strftime('%m/%Y')
    if agrupacion == AGRUPACION_DIVISA:
        return fila['divisa'], fila['divisa']
    if agrupacion == AGRUPACION_TIPO:
        return fila['tipo_codigo'], dict(TIPO_CHOICES)[fila['tipo_codigo']]
    return fila['canal'], dict(CANAL_CHOICES)[fila['canal']]


def _orden_de_grupo(agrupacion):
    """Función de orden de los grupos: cronológico, alfabético o el orden de las opciones del modelo."""
    if agrupacion == AGRUPACION_TIPO:
        posiciones = {codigo: indice for indice, (codigo, _) in enumerate(TIPO_CHOICES)}
        return lambda clave: posiciones.get(clave, len(posiciones))
    if agrupacion == AGRUPACION_CANAL:
        posiciones = {codigo: indice for indice, (codigo, _) in enumerate(CANAL_CHOICES)}
        return lambda clave: posiciones.get(clave, len(posiciones))
    return lambda clave: clave


def agrupar_ganancias(filas, agrupacion):
    """Ganancia y cantidad de operaciones de cada grupo según ``agrupacion`` (criterio 1).

    Solo aparecen los grupos que tienen al menos una operación en ``filas``.

    Args:
        filas (list[dict]): Filas normalizadas de
            ``apps.divisas.ganancias._todas_las_ganancias``, ya filtradas
            por el período.
        agrupacion (str): Uno de ``dia``, ``mes``, ``divisa``, ``tipo`` o
            ``canal`` (el desglose por caja lo resuelve
            ``desglosar_por_caja``).

    Returns:
        list[dict]: Una entrada por grupo, con ``clave``, ``etiqueta``,
        ``cantidad`` y ``ganancia_pyg``, en orden cronológico (día/mes),
        alfabético (divisa) o el de ``TIPO_CHOICES``/``CANAL_CHOICES``.
    """
    acumulado = {}
    for fila in filas:
        clave, etiqueta = _clave_y_etiqueta(fila, agrupacion)
        grupo = acumulado.setdefault(
            clave, {'clave': clave, 'etiqueta': etiqueta, 'cantidad': 0, 'ganancia_pyg': Decimal('0.00')},
        )
        grupo['cantidad'] += 1
        grupo['ganancia_pyg'] += fila['ganancia_pyg']
    orden = _orden_de_grupo(agrupacion)
    return [acumulado[clave] for clave in sorted(acumulado, key=orden)]


def _nombre_cajero(usuario):
    """Nombre completo del cajero o, si no lo tiene cargado, su nombre de usuario."""
    return usuario.get_full_name() or usuario.get_username()


def _cajas_del_periodo(fecha_desde, fecha_hasta):
    """Cajas cuyo turno se superpone con el período, de la apertura más antigua a la más reciente.

    Una caja pertenece al período si se abrió antes del fin del rango y,
    además, sigue abierta o se cerró después del inicio del rango (ambas
    fechas en hora local). Así entra también un turno abierto el día
    anterior al rango que siguió operando dentro de él.
    """
    cajas = Caja.objects.select_related('usuario').filter(abierta_en__date__lte=fecha_hasta).order_by('abierta_en')
    return [
        caja for caja in cajas
        if caja.cerrada_en is None or timezone.localtime(caja.cerrada_en).date() >= fecha_desde
    ]


def desglosar_por_caja(fecha_desde, fecha_hasta):
    """Una fila por caja del período con cajero, apertura, cierre, operaciones y ganancia (criterios 2 y 3).

    Solo cuenta las operaciones de ventanilla de cada caja registradas
    dentro del período, con la misma ganancia (``comision``, ya en PYG) que
    usa el tablero para el canal ventanilla. Una caja todavía "Abierta" se
    marca con ``en_curso=True``: no tiene fecha de cierre y su ganancia es
    parcial, porque puede seguir registrando operaciones.

    Returns:
        list[dict]: Una entrada por caja con ``caja_id``, ``cajero``,
        ``abierta_en``, ``cerrada_en`` (``None`` si sigue abierta),
        ``en_curso``, ``cantidad`` y ``ganancia_pyg``.
    """
    cajas = _cajas_del_periodo(fecha_desde, fecha_hasta)
    operaciones = OperacionVentanilla.objects.filter(caja__in=cajas).only('caja_id', 'comision', 'creado_en')

    acumulado = {caja.pk: {'cantidad': 0, 'ganancia_pyg': Decimal('0.00')} for caja in cajas}
    for operacion in operaciones:
        if fecha_desde <= timezone.localtime(operacion.creado_en).date() <= fecha_hasta:
            acumulado[operacion.caja_id]['cantidad'] += 1
            acumulado[operacion.caja_id]['ganancia_pyg'] += operacion.comision

    return [
        {
            'caja_id': caja.pk,
            'cajero': _nombre_cajero(caja.usuario),
            'abierta_en': caja.abierta_en,
            'cerrada_en': caja.cerrada_en,
            'en_curso': caja.estado == Caja.ESTADO_ABIERTA,
            **acumulado[caja.pk],
        }
        for caja in cajas
    ]


def generar_reporte_ganancias(parametros):
    """Resuelve filtros, grupos y totales del reporte de ganancias a partir de los parámetros de la URL.

    ``parametros`` es cualquier mapeo tipo ``QueryDict`` con las claves
    ``fecha_desde``, ``fecha_hasta`` y ``agrupacion`` (las de
    ``request.GET``). El rango de fechas es obligatorio: sin alguna de las
    dos fechas se devuelve ``reporte_generado=False`` sin error, para que
    la pantalla muestre solo el formulario. Un rango ilegible o inválido se
    informa en ``error_rango``. Una agrupación desconocida se reemplaza por
    ``AGRUPACION_POR_DEFECTO``.

    El ``total`` siempre abarca **todas** las operaciones completadas del
    período (ambos canales), calculado igual que el tablero, para que los
    dos coincidan (criterio 4); también con el desglose por caja, que solo
    detalla la ventanilla y por eso informa además su propio
    ``total_cajas``. ``sin_datos`` es ``True`` si el período no tiene
    ninguna operación completada (criterio 6).

    Returns:
        dict: ``reporte_generado``, ``error_rango``, ``sin_datos``,
        ``filtros`` (los valores tal como llegaron, con la agrupación ya
        resuelta), ``agrupacion_etiqueta``, ``grupos`` (o ``cajas`` en el
        desglose por caja), ``total`` (``cantidad`` y ``ganancia_pyg``),
        ``total_cajas`` y ``generado_en``.
    """
    fecha_desde_str = (parametros.get('fecha_desde') or '').strip()
    fecha_hasta_str = (parametros.get('fecha_hasta') or '').strip()
    agrupacion = (parametros.get('agrupacion') or '').strip()
    if agrupacion not in AGRUPACIONES:
        agrupacion = AGRUPACION_POR_DEFECTO

    resultado = {
        'reporte_generado': False,
        'error_rango': None,
        'sin_datos': False,
        'filtros': {
            'fecha_desde': fecha_desde_str,
            'fecha_hasta': fecha_hasta_str,
            'agrupacion': agrupacion,
        },
        'agrupacion_etiqueta': AGRUPACIONES[agrupacion],
        'grupos': [],
        'cajas': [],
        'total': None,
        'total_cajas': None,
        'generado_en': timezone.now(),
    }

    if not (fecha_desde_str and fecha_hasta_str):
        return resultado

    fecha_desde = _parsear_fecha(fecha_desde_str)
    fecha_hasta = _parsear_fecha(fecha_hasta_str)
    if fecha_desde is None or fecha_hasta is None:
        resultado['error_rango'] = 'Ingresá un rango de fechas válido.'
        return resultado

    error_rango = _validar_rango(fecha_desde, fecha_hasta)
    if error_rango:
        resultado['error_rango'] = error_rango
        return resultado

    filas = _en_rango(_todas_las_ganancias(), fecha_desde, fecha_hasta)
    indicadores = calcular_indicadores(filas)
    resultado['reporte_generado'] = True
    resultado['total'] = {
        'cantidad': indicadores['cantidad_operaciones'],
        'ganancia_pyg': indicadores['ganancia_total'],
    }
    resultado['sin_datos'] = indicadores['cantidad_operaciones'] == 0

    if agrupacion == AGRUPACION_CAJA:
        cajas = desglosar_por_caja(fecha_desde, fecha_hasta)
        resultado['cajas'] = cajas
        resultado['total_cajas'] = {
            'cantidad': sum(caja['cantidad'] for caja in cajas),
            'ganancia_pyg': sum((caja['ganancia_pyg'] for caja in cajas), Decimal('0.00')),
            'hay_en_curso': any(caja['en_curso'] for caja in cajas),
        }
    else:
        resultado['grupos'] = agrupar_ganancias(filas, agrupacion)
    return resultado


def _formatear_fecha(valor):
    """``'YYYY-MM-DD'`` a ``'DD/MM/YYYY'``, tal como se ingresó en el filtro."""
    fecha = _parsear_fecha(valor)
    return fecha.strftime('%d/%m/%Y') if fecha else valor


def descripcion_filtros(filtros):
    """Texto legible de los filtros aplicados, para dejarlos documentados en el archivo descargado (criterio 5)."""
    return (
        f"Del {_formatear_fecha(filtros['fecha_desde'])} al {_formatear_fecha(filtros['fecha_hasta'])}"
        f" · Agrupado por: {AGRUPACIONES[filtros['agrupacion']]}"
    )


def _formatear_momento(valor):
    """Fecha y hora en hora local (``'DD/MM/YYYY HH:MM'``), o cadena vacía si no hay valor."""
    return timezone.localtime(valor).strftime('%d/%m/%Y %H:%M') if valor else ''


def _filas_tabla(resultado):
    """Encabezados y filas de la tabla principal, compartidos por el PDF y el Excel.

    Devolver la misma estructura a los dos formatos garantiza que ambos
    archivos muestren exactamente los mismos datos (criterio 5). Los
    importes quedan como ``Decimal``; cada formato decide cómo escribirlos.
    """
    if resultado['filtros']['agrupacion'] == AGRUPACION_CAJA:
        encabezados = ['Cajero', 'Apertura', 'Cierre', 'Operaciones', 'Ganancia (PYG)', 'Observación']
        filas = [
            [
                caja['cajero'],
                _formatear_momento(caja['abierta_en']),
                'En curso' if caja['en_curso'] else _formatear_momento(caja['cerrada_en']),
                caja['cantidad'],
                caja['ganancia_pyg'],
                'Parcial' if caja['en_curso'] else '',
            ]
            for caja in resultado['cajas']
        ]
        return encabezados, filas

    encabezados = [resultado['agrupacion_etiqueta'], 'Operaciones', 'Ganancia (PYG)']
    filas = [[grupo['etiqueta'], grupo['cantidad'], grupo['ganancia_pyg']] for grupo in resultado['grupos']]
    return encabezados, filas


def _filas_totales(resultado):
    """Líneas de totales (etiqueta, cantidad, ganancia) que cierran ambos archivos."""
    filas = [['Total general (todos los canales)', resultado['total']['cantidad'], resultado['total']['ganancia_pyg']]]
    if resultado['total_cajas'] is not None:
        etiqueta = 'Total de ventanilla (cajas del período)'
        if resultado['total_cajas']['hay_en_curso']:
            etiqueta += ' — parcial'
        filas.append([etiqueta, resultado['total_cajas']['cantidad'], resultado['total_cajas']['ganancia_pyg']])
    return filas


def _texto_celda(valor):
    """Convierte un valor de la tabla a texto para el PDF, con dos decimales en los importes."""
    if isinstance(valor, Decimal):
        return f'{valor:.2f}'
    return str(valor)


def _valor_excel(valor):
    """Convierte un valor de la tabla a un tipo que Excel trate como número cuando corresponde."""
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


def generar_pdf(resultado):
    """Arma el PDF del reporte: filtros aplicados, fecha de generación, desglose y totales (criterio 5).

    Args:
        resultado (dict): El resultado de ``generar_reporte_ganancias`` con
            ``reporte_generado=True``.

    Returns:
        bytes: El contenido del PDF.
    """
    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )
    estilos = getSampleStyleSheet()

    elementos = [
        Paragraph('Reporte de ganancias', estilos['Title']),
        Paragraph(descripcion_filtros(resultado['filtros']), estilos['Normal']),
        Paragraph(f"Generado el {_formatear_momento(resultado['generado_en'])}", estilos['Normal']),
        Spacer(1, 0.5 * cm),
    ]

    encabezados, filas = _filas_tabla(resultado)
    tabla = Table([encabezados] + [[_texto_celda(valor) for valor in fila] for fila in filas], repeatRows=1)
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2a78d6')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f2f2f2')]),
    ]))
    elementos.append(tabla)
    elementos.append(Spacer(1, 0.5 * cm))

    elementos.append(Paragraph('Totales', estilos['Heading3']))
    totales = [['Concepto', 'Operaciones', 'Ganancia (PYG)']]
    totales.extend([[_texto_celda(valor) for valor in fila] for fila in _filas_totales(resultado)])
    elementos.append(Table(totales, style=TableStyle([('GRID', (0, 0), (-1, -1), 0.5, colors.grey)])))

    documento.build(elementos)
    return buffer.getvalue()


def generar_excel(resultado):
    """Arma el Excel del reporte con los mismos datos, filtros y fecha de generación que el PDF (criterio 5).

    Args:
        resultado (dict): El resultado de ``generar_reporte_ganancias`` con
            ``reporte_generado=True``.

    Returns:
        bytes: El contenido del archivo ``.xlsx``.
    """
    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Ganancias'

    negrita = Font(bold=True)
    hoja.append(['Reporte de ganancias'])
    hoja['A1'].font = Font(bold=True, size=14)
    hoja.append([descripcion_filtros(resultado['filtros'])])
    hoja.append([f"Generado el {_formatear_momento(resultado['generado_en'])}"])
    hoja.append([])

    encabezados, filas = _filas_tabla(resultado)
    hoja.append(encabezados)
    for celda in hoja[hoja.max_row]:
        celda.font = negrita
    for fila in filas:
        hoja.append([_valor_excel(valor) for valor in fila])

    hoja.append([])
    hoja.append(['Totales'])
    hoja[f'A{hoja.max_row}'].font = negrita
    hoja.append(['Concepto', 'Operaciones', 'Ganancia (PYG)'])
    for fila in _filas_totales(resultado):
        hoja.append([_valor_excel(valor) for valor in fila])

    buffer = BytesIO()
    libro.save(buffer)
    return buffer.getvalue()
