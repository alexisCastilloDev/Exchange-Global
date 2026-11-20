"""Reporte de transacciones de un cliente: filtrado, totales y exportación a PDF/Excel.

Implementa la HU "Reporte de transacciones del cliente" (GE-39). Las filas
normalizadas (``_fila_operacion``/``_fila_cambio``) son una versión propia,
no reutilizada, de las que ya arma
``apps.divisas.views.MiHistorialTransaccionesView``: esta vista necesita,
además, el filtro por tipo de operación (compra/venta/cambio, ausente en
el historial) y un monto en PYG uniforme entre los tres tipos
(``monto_pyg``) para poder totalizar una compra/venta junto con un cambio
entre divisas sin mezclar unidades distintas.

``generar_reporte`` es el único punto de entrada: resuelve filtros, filas
y totales a partir de los parámetros de la URL, y lo usan tanto la
pantalla (``apps.divisas.views.ReporteTransaccionesClienteView``) como las
dos descargas (``DescargarReporteTransaccionesView``), para que los tres
vean siempre los mismos datos con los mismos filtros (criterio 3).
"""

from collections import OrderedDict
from datetime import datetime
from decimal import Decimal
from io import BytesIO

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.divisas.models import CalculoOperacion, CalculoTriangulacion

TIPO_COMPRA = CalculoOperacion.TIPO_COMPRA
TIPO_VENTA = CalculoOperacion.TIPO_VENTA
TIPO_CAMBIO = 'CAMBIO'
TIPO_CHOICES = (
    (TIPO_COMPRA, 'Compra'),
    (TIPO_VENTA, 'Venta'),
    (TIPO_CAMBIO, 'Cambio'),
)

ESTADOS_COMPLETADOS = ('ACREDITADA', 'RETIRADA')
"""Estados efectivos que cuentan como "completada" (criterio 2): el dinero ya
llegó a destino, acreditado en una cuenta o retirado en efectivo (ver
``apps.divisas.entrega.realizar_entrega``). "Pagada" queda afuera a
propósito: todavía no se le entregó nada al cliente."""


def _parsear_fecha(valor):
    """Convierte ``'YYYY-MM-DD'`` a ``date``, o ``None`` si falta o no es válido."""
    if not valor:
        return None
    try:
        return datetime.strptime(valor, '%Y-%m-%d').date()
    except ValueError:
        return None


def _fila_operacion(operacion):
    """Normaliza una compra o venta para el reporte."""
    return {
        'id': operacion.pk,
        'tipo_modelo': 'operacion',
        'tipo_codigo': operacion.tipo,
        'creado_en': operacion.creado_en,
        'tipo': operacion.get_tipo_display(),
        'estado': operacion.get_estado_efectivo_display(),
        'estado_codigo': operacion.estado_efectivo,
        'divisa': operacion.codigo_divisa,
        'monto_origen': operacion.monto_origen,
        'tasa': operacion.tasa_aplicada,
        'decimales_tasa': 2,
        'comision': operacion.comision,
        'monto_final': operacion.monto_final,
        'moneda_final': 'PYG',
        'monto_pyg': operacion.monto_final,
    }


def _fila_cambio(cambio):
    """Normaliza un cambio entre divisas para el reporte.

    ``monto_pyg`` usa ``monto_equivalente_pyg`` (no ``monto_final``, que
    está en la divisa de destino, no en PYG) para que los totales por
    tipo de operación puedan sumar un cambio junto con una compra o venta
    sin mezclar monedas distintas.
    """
    return {
        'id': cambio.pk,
        'tipo_modelo': 'cambio',
        'tipo_codigo': TIPO_CAMBIO,
        'creado_en': cambio.creado_en,
        'tipo': CalculoTriangulacion.TIPO_DISPLAY,
        'estado': cambio.get_estado_efectivo_display(),
        'estado_codigo': cambio.estado_efectivo,
        'divisa': f'{cambio.codigo_divisa_origen} → {cambio.codigo_divisa_destino}',
        'monto_origen': cambio.monto_origen,
        'tasa': cambio.tasa_cruzada,
        'decimales_tasa': 6,
        'comision': cambio.comision,
        'monto_final': cambio.monto_final,
        'moneda_final': cambio.codigo_divisa_destino,
        'monto_pyg': cambio.monto_equivalente_pyg,
    }


def _transacciones_cliente(cliente):
    """Todas las compras, ventas y cambios del cliente, normalizados, del más reciente al más antiguo."""
    filas = [
        _fila_operacion(operacion)
        for operacion in CalculoOperacion.objects.filter(cliente=cliente).select_related('usuario')
    ]
    filas.extend(
        _fila_cambio(cambio)
        for cambio in CalculoTriangulacion.objects.filter(cliente=cliente).select_related('usuario')
    )
    return sorted(filas, key=lambda fila: fila['creado_en'], reverse=True)


def _validar_rango(fecha_desde, fecha_hasta):
    """Valida un rango de fechas ya parseado (criterio 5). Devuelve el error, o ``None`` si es válido."""
    hoy = timezone.localdate()
    if fecha_desde > fecha_hasta:
        return 'La fecha inicial no puede ser posterior a la fecha final.'
    if fecha_desde > hoy or fecha_hasta > hoy:
        return 'No se puede consultar un rango con fechas futuras.'
    return None


def calcular_totales(filas):
    """Calcula los totales por tipo de operación y por divisa, solo sobre transacciones completadas (criterio 2).

    El monto por tipo usa el equivalente en PYG (``monto_pyg``): es la
    única unidad común entre una compra/venta (liquidada en PYG) y un
    cambio entre dos divisas que no son PYG. El monto por divisa, en
    cambio, suma el monto operado en la moneda de origen de cada fila
    (``monto_origen``), tal como ya se muestra en la columna "Monto" del
    historial — por eso un cambio aparece agrupado bajo su par
    "ORIGEN → DESTINO", igual que en la tabla.
    """
    completadas = [fila for fila in filas if fila['estado_codigo'] in ESTADOS_COMPLETADOS]

    por_tipo = OrderedDict()
    for codigo, etiqueta in TIPO_CHOICES:
        subconjunto = [fila for fila in completadas if fila['tipo_codigo'] == codigo]
        por_tipo[codigo] = {
            'etiqueta': etiqueta,
            'cantidad': len(subconjunto),
            'monto_pyg': sum((fila['monto_pyg'] for fila in subconjunto), Decimal('0.00')),
        }

    por_divisa = OrderedDict()
    for fila in completadas:
        entrada = por_divisa.setdefault(fila['divisa'], {'cantidad': 0, 'monto': Decimal('0.00')})
        entrada['cantidad'] += 1
        entrada['monto'] += fila['monto_origen']

    return {
        'cantidad_completadas': len(completadas),
        'por_tipo': por_tipo,
        'por_divisa': por_divisa,
    }


def generar_reporte(cliente, parametros):
    """Resuelve filtros, filas filtradas y totales para el reporte de ``cliente``.

    ``parametros`` es cualquier mapeo tipo ``QueryDict`` con las claves
    ``tipo``, ``estado``, ``fecha_desde`` y ``fecha_hasta`` (las mismas
    que llegan por ``request.GET`` tanto en la pantalla como en las
    descargas). El rango de fechas es obligatorio para generar el reporte
    (criterio 1): si falta alguna de las dos fechas, se devuelve
    ``reporte_generado=False`` sin error, para que la pantalla muestre
    solo el formulario vacío. Si las dos vienen pero el rango no es
    válido, se devuelve el motivo en ``error_rango`` (criterio 5). El
    tipo de operación y el estado son opcionales.
    """
    tipo = (parametros.get('tipo') or '').strip()
    estado = (parametros.get('estado') or '').strip()
    fecha_desde_str = (parametros.get('fecha_desde') or '').strip()
    fecha_hasta_str = (parametros.get('fecha_hasta') or '').strip()

    filtros = {
        'tipo': tipo,
        'estado': estado,
        'fecha_desde': fecha_desde_str,
        'fecha_hasta': fecha_hasta_str,
    }

    resultado = {
        'reporte_generado': False,
        'error_rango': None,
        'filas': [],
        'totales': None,
        'filtros': filtros,
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

    filas = _transacciones_cliente(cliente)
    filas = [
        fila for fila in filas
        if fecha_desde <= timezone.localtime(fila['creado_en']).date() <= fecha_hasta
    ]
    if tipo:
        filas = [fila for fila in filas if fila['tipo_codigo'] == tipo]
    if estado:
        filas = [fila for fila in filas if fila['estado_codigo'] == estado]

    resultado['reporte_generado'] = True
    resultado['filas'] = filas
    resultado['totales'] = calcular_totales(filas)
    return resultado


def _formatear_fecha(valor):
    """``'YYYY-MM-DD'`` a ``'DD/MM/YYYY'``, tal como se ingresó en el filtro."""
    fecha = _parsear_fecha(valor)
    return fecha.strftime('%d/%m/%Y') if fecha else valor


def _descripcion_filtros(filtros):
    """Texto legible de los filtros aplicados, para dejarlos documentados en el archivo descargado (criterio 3)."""
    partes = [f"Del {_formatear_fecha(filtros['fecha_desde'])} al {_formatear_fecha(filtros['fecha_hasta'])}"]
    if filtros['tipo']:
        partes.append(f"Tipo: {dict(TIPO_CHOICES).get(filtros['tipo'], filtros['tipo'])}")
    if filtros['estado']:
        partes.append(f"Estado: {dict(CalculoOperacion.ESTADO_CHOICES).get(filtros['estado'], filtros['estado'])}")
    return ' · '.join(partes)


def _nombre_cliente(cliente):
    """Nombre o razón social con el identificador, para el encabezado del archivo descargado."""
    return f'{cliente.nombre_completo} ({cliente.identificador})'


def generar_pdf(cliente, filas, totales, filtros, generado_en):
    """Arma el PDF del reporte: filtros aplicados, fecha de generación, listado y totales (criterio 3)."""
    buffer = BytesIO()
    documento = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    estilos = getSampleStyleSheet()

    elementos = [
        Paragraph(f'Reporte de transacciones — {_nombre_cliente(cliente)}', estilos['Title']),
        Paragraph(_descripcion_filtros(filtros), estilos['Normal']),
        Paragraph(f'Generado el {timezone.localtime(generado_en):%d/%m/%Y %H:%M}', estilos['Normal']),
        Spacer(1, 0.5 * cm),
    ]

    encabezados = ['Fecha', 'Tipo', 'Estado', 'Divisa', 'Monto', 'Comisión', 'Importe final']
    filas_tabla = [encabezados]
    for fila in filas:
        filas_tabla.append([
            timezone.localtime(fila['creado_en']).strftime('%d/%m/%Y %H:%M'),
            fila['tipo'],
            fila['estado'],
            fila['divisa'],
            f"{fila['monto_origen']:.2f}",
            f"{fila['comision']:.2f} {fila['moneda_final']}",
            f"{fila['monto_final']:.2f} {fila['moneda_final']}",
        ])
    tabla = Table(filas_tabla, repeatRows=1)
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2a78d6')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f2f2f2')]),
    ]))
    elementos.append(tabla)
    elementos.append(Spacer(1, 0.5 * cm))

    elementos.append(Paragraph('Totales por tipo de operación (transacciones completadas)', estilos['Heading3']))
    totales_tipo = [['Tipo', 'Cantidad', 'Monto (PYG)']]
    for datos in totales['por_tipo'].values():
        totales_tipo.append([datos['etiqueta'], str(datos['cantidad']), f"{datos['monto_pyg']:.2f}"])
    elementos.append(Table(totales_tipo, style=TableStyle([('GRID', (0, 0), (-1, -1), 0.5, colors.grey)])))
    elementos.append(Spacer(1, 0.5 * cm))

    elementos.append(Paragraph('Totales por divisa (transacciones completadas)', estilos['Heading3']))
    totales_divisa = [['Divisa', 'Cantidad', 'Monto operado']]
    for divisa, datos in totales['por_divisa'].items():
        totales_divisa.append([divisa, str(datos['cantidad']), f"{datos['monto']:.2f}"])
    if len(totales_divisa) == 1:
        totales_divisa.append(['Sin transacciones completadas', '-', '-'])
    elementos.append(Table(totales_divisa, style=TableStyle([('GRID', (0, 0), (-1, -1), 0.5, colors.grey)])))

    documento.build(elementos)
    return buffer.getvalue()


def generar_excel(cliente, filas, totales, filtros, generado_en):
    """Arma el Excel del reporte con los mismos datos, filtros y fecha de generación que el PDF (criterio 3)."""
    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Transacciones'

    negrita = Font(bold=True)
    hoja.append([f'Reporte de transacciones — {_nombre_cliente(cliente)}'])
    hoja['A1'].font = Font(bold=True, size=14)
    hoja.append([_descripcion_filtros(filtros)])
    hoja.append([f'Generado el {timezone.localtime(generado_en):%d/%m/%Y %H:%M}'])
    hoja.append([])

    encabezados = ['Fecha', 'Tipo', 'Estado', 'Divisa', 'Monto', 'Tasa aplicada', 'Comisión', 'Moneda', 'Importe final']
    hoja.append(encabezados)
    for celda in hoja[hoja.max_row]:
        celda.font = negrita
    for fila in filas:
        hoja.append([
            timezone.localtime(fila['creado_en']).strftime('%d/%m/%Y %H:%M'),
            fila['tipo'],
            fila['estado'],
            fila['divisa'],
            float(fila['monto_origen']),
            float(fila['tasa']),
            float(fila['comision']),
            fila['moneda_final'],
            float(fila['monto_final']),
        ])

    hoja.append([])
    hoja.append(['Totales por tipo de operación (transacciones completadas)'])
    hoja.append(['Tipo', 'Cantidad', 'Monto (PYG)'])
    for datos in totales['por_tipo'].values():
        hoja.append([datos['etiqueta'], datos['cantidad'], float(datos['monto_pyg'])])

    hoja.append([])
    hoja.append(['Totales por divisa (transacciones completadas)'])
    hoja.append(['Divisa', 'Cantidad', 'Monto operado'])
    for divisa, datos in totales['por_divisa'].items():
        hoja.append([divisa, datos['cantidad'], float(datos['monto'])])

    buffer = BytesIO()
    libro.save(buffer)
    return buffer.getvalue()
