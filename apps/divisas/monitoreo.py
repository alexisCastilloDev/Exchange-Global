"""Monitoreo de transacciones para el analista cambiario: listado, filtros, totales y reportes.

Implementa la HU "Monitoreo de transacciones y reportes" (epic GE-14). A
diferencia de ``apps.divisas.reportes`` (que arma el reporte de *un*
cliente) y de ``apps.divisas.ganancias`` (que solo cuenta las
transacciones completadas), este módulo reúne **todas** las transacciones
de **todos** los clientes y de los dos canales, en cualquier estado:

- ``online``: compras/ventas (``CalculoOperacion``) y cambios entre divisas
  (``CalculoTriangulacion``) iniciados por el cliente.
- ``ventanilla``: operaciones de mostrador (``apps.caja.models.OperacionVentanilla``).

El "tipo" de operación se expresa, como en ``ganancias``, desde la
perspectiva de la **casa de cambio** (``CASA_COMPRA``/``CASA_VENTA``/
``CAMBIO``): ``CalculoOperacion.TIPO_COMPRA`` es el cliente comprando, es
decir, la casa vendiendo, mientras que ``OperacionVentanilla.TIPO_COMPRA``
ya está escrito desde la casa. Sin esa inversión, filtrar por tipo
mezclaría operaciones económicamente opuestas.

Una ``OperacionVentanilla`` no tiene estado propio (se liquida en efectivo
en el momento), así que se muestra siempre como ``ESTADO_COMPLETADA``.

``generar_monitoreo`` es el único punto de entrada: lo usan tanto la
pantalla (``apps.divisas.views.MonitoreoTransaccionesView``) como las dos
descargas (``DescargarMonitoreoView``), para que listado, PDF y Excel
vean siempre los mismos datos con los mismos filtros. El módulo es de
solo lectura: ninguna función de acá modifica una transacción.
"""

from collections import OrderedDict
from decimal import Decimal
from io import BytesIO

from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.caja.models import OperacionVentanilla
from apps.divisas.ganancias import (
    CAMBIO,
    CANAL_ONLINE,
    CANAL_VENTANILLA,
    CASA_COMPRA,
    CASA_VENTA,
    TIPO_CHOICES,
)
from apps.divisas.models import CalculoOperacion, CalculoTriangulacion
from apps.divisas.reportes import _parsear_fecha

CANAL_CHOICES = (
    (CANAL_ONLINE, 'En línea'),
    (CANAL_VENTANILLA, 'Ventanilla'),
)

ESTADO_COMPLETADA = 'COMPLETADA'
ESTADO_CHOICES = tuple(CalculoOperacion.ESTADO_CHOICES) + ((ESTADO_COMPLETADA, 'Completada (ventanilla)'),)

MOTIVOS_ATENCION = {
    CalculoOperacion.ESTADO_PAGADA: 'Entrega pendiente',
    CalculoOperacion.ESTADO_ENTREGA_FALLIDA: 'Entrega incierta',
    CalculoOperacion.ESTADO_PAGO_EXPIRADO: 'Pago fuera de plazo',
}
"""Estados que requieren atención del analista (criterio 3), con su motivo.

- ``PAGADA``: el pago se registró pero la entrega todavía no se completó
  (``apps.divisas.entrega.realizar_entrega`` la pasa a "Acreditada"/"Retirada"
  apenas termina; una transacción que sigue "Pagada" quedó sin entregar).
- ``ENTREGA_FALLIDA``: la transferencia saliente no respondió o fue
  rechazada; no se sabe si sipap-sim llegó a procesarla, por eso es
  "incierta" (reintentar es seguro porque sipap-sim es idempotente por
  referencia).
- ``PAGO_EXPIRADO``: el pago llegó después de vencida la tasa fijada.
"""


def _etiqueta_cliente(cliente):
    """Nombre o razón social del cliente con su identificador."""
    return f'{cliente.nombre_completo} ({cliente.identificador})'


def _atencion(estado_codigo):
    """Devuelve el motivo de atención de un estado, o ``''`` si no requiere atención."""
    return MOTIVOS_ATENCION.get(estado_codigo, '')


def _fila_operacion(operacion):
    """Normaliza una compra o venta online (perspectiva del cliente invertida a la de la casa)."""
    tipo_codigo = CASA_VENTA if operacion.tipo == CalculoOperacion.TIPO_COMPRA else CASA_COMPRA
    estado_codigo = operacion.estado_efectivo
    return {
        'id': operacion.pk,
        'tipo_modelo': 'operacion',
        'canal': CANAL_ONLINE,
        'creado_en': operacion.creado_en,
        'cliente': _etiqueta_cliente(operacion.cliente),
        'cliente_id': operacion.cliente_id,
        'tipo_codigo': tipo_codigo,
        'tipo': dict(TIPO_CHOICES)[tipo_codigo],
        'divisa': operacion.codigo_divisa,
        'divisas': [operacion.codigo_divisa],
        'monto_origen': operacion.monto_origen,
        'tasa': operacion.tasa_aplicada,
        'decimales_tasa': 2,
        'comision': operacion.comision,
        'monto_final': operacion.monto_final,
        'moneda_final': 'PYG',
        'monto_pyg': operacion.monto_final,
        'estado_codigo': estado_codigo,
        'estado': operacion.get_estado_efectivo_display(),
        'atencion': _atencion(estado_codigo),
        'url_detalle': reverse('divisas:monitoreo_detalle', kwargs={'tipo': 'operacion', 'pk': operacion.pk}),
    }


def _fila_cambio(cambio):
    """Normaliza un cambio entre divisas online."""
    estado_codigo = cambio.estado_efectivo
    return {
        'id': cambio.pk,
        'tipo_modelo': 'cambio',
        'canal': CANAL_ONLINE,
        'creado_en': cambio.creado_en,
        'cliente': _etiqueta_cliente(cambio.cliente),
        'cliente_id': cambio.cliente_id,
        'tipo_codigo': CAMBIO,
        'tipo': CalculoTriangulacion.TIPO_DISPLAY,
        'divisa': f'{cambio.codigo_divisa_origen} → {cambio.codigo_divisa_destino}',
        'divisas': [cambio.codigo_divisa_origen, cambio.codigo_divisa_destino],
        'monto_origen': cambio.monto_origen,
        'tasa': cambio.tasa_cruzada,
        'decimales_tasa': 6,
        'comision': cambio.comision,
        'monto_final': cambio.monto_final,
        'moneda_final': cambio.codigo_divisa_destino,
        'monto_pyg': cambio.monto_equivalente_pyg,
        'estado_codigo': estado_codigo,
        'estado': cambio.get_estado_efectivo_display(),
        'atencion': _atencion(estado_codigo),
        'url_detalle': reverse('divisas:monitoreo_detalle', kwargs={'tipo': 'cambio', 'pk': cambio.pk}),
    }


def _fila_ventanilla(operacion):
    """Normaliza una operación de ventanilla (ya está en perspectiva de la casa, siempre completada)."""
    tipo_codigo = CASA_COMPRA if operacion.tipo == OperacionVentanilla.TIPO_COMPRA else CASA_VENTA
    cliente = operacion.cliente_nombre or 'Cliente de mostrador'
    if operacion.cliente_identificador:
        cliente = f'{cliente} ({operacion.cliente_identificador})'
    return {
        'id': operacion.pk,
        'tipo_modelo': 'ventanilla',
        'canal': CANAL_VENTANILLA,
        'creado_en': operacion.creado_en,
        'cliente': cliente,
        'cliente_id': None,
        'tipo_codigo': tipo_codigo,
        'tipo': dict(TIPO_CHOICES)[tipo_codigo],
        'divisa': operacion.divisa.codigo,
        'divisas': [operacion.divisa.codigo],
        'monto_origen': operacion.monto_divisa,
        'tasa': operacion.tasa_aplicada,
        'decimales_tasa': 2,
        'comision': operacion.comision,
        'monto_final': operacion.monto_pyg,
        'moneda_final': 'PYG',
        'monto_pyg': operacion.monto_pyg,
        'estado_codigo': ESTADO_COMPLETADA,
        'estado': dict(ESTADO_CHOICES)[ESTADO_COMPLETADA],
        'atencion': '',
        'url_detalle': reverse('divisas:monitoreo_detalle', kwargs={'tipo': 'ventanilla', 'pk': operacion.pk}),
    }


def _todas_las_transacciones():
    """Todas las transacciones de todos los canales, normalizadas, de la más reciente a la más antigua."""
    filas = [
        _fila_operacion(operacion)
        for operacion in CalculoOperacion.objects.select_related('cliente')
    ]
    filas.extend(
        _fila_cambio(cambio)
        for cambio in CalculoTriangulacion.objects.select_related('cliente')
    )
    filas.extend(
        _fila_ventanilla(operacion)
        for operacion in OperacionVentanilla.objects.select_related('divisa')
    )
    return sorted(filas, key=lambda fila: fila['creado_en'], reverse=True)


def calcular_totales(filas):
    """Calcula los totales por tipo, divisa y estado de las filas dadas (criterio 5).

    Los montos por tipo y por estado usan el equivalente en PYG
    (``monto_pyg``), la única unidad común entre compras/ventas y cambios;
    el monto por divisa suma el monto operado en la moneda de origen de
    cada fila (``monto_origen``), así que un cambio aparece bajo su par
    "ORIGEN → DESTINO". A diferencia del reporte del cliente, acá se
    totalizan **todas** las filas filtradas, sin importar su estado: el
    analista supervisa también lo cancelado o pendiente.
    """
    por_tipo = OrderedDict()
    for codigo, etiqueta in TIPO_CHOICES:
        subconjunto = [fila for fila in filas if fila['tipo_codigo'] == codigo]
        por_tipo[codigo] = {
            'etiqueta': etiqueta,
            'cantidad': len(subconjunto),
            'monto_pyg': sum((fila['monto_pyg'] for fila in subconjunto), Decimal('0.00')),
        }

    por_divisa = OrderedDict()
    for fila in filas:
        entrada = por_divisa.setdefault(fila['divisa'], {'cantidad': 0, 'monto': Decimal('0.00')})
        entrada['cantidad'] += 1
        entrada['monto'] += fila['monto_origen']

    por_estado = OrderedDict()
    for fila in filas:
        entrada = por_estado.setdefault(
            fila['estado_codigo'],
            {'etiqueta': fila['estado'], 'cantidad': 0, 'monto_pyg': Decimal('0.00')},
        )
        entrada['cantidad'] += 1
        entrada['monto_pyg'] += fila['monto_pyg']

    return {
        'cantidad': len(filas),
        'por_tipo': por_tipo,
        'por_divisa': por_divisa,
        'por_estado': por_estado,
    }


def generar_monitoreo(parametros):
    """Resuelve filtros, filas filtradas y totales del monitoreo a partir de ``parametros``.

    ``parametros`` es cualquier mapeo tipo ``QueryDict`` con las claves
    ``fecha_desde``, ``fecha_hasta``, ``cliente`` (texto: nombre o
    identificador, sin distinguir mayúsculas), ``tipo``, ``divisa``
    (código; en un cambio coincide con la divisa de origen o la de
    destino), ``estado``, ``canal`` y ``atencion`` (``'1'`` para ver solo
    las que requieren atención). Todos son opcionales (criterio 2); un
    rango con una fecha inválida o con inicio posterior al fin se informa
    en ``error_rango`` y no lista nada. Las fechas futuras no son un
    error: simplemente no hay transacciones.

    Returns:
        dict: ``filtros`` (los valores ya normalizados, para repoblar el
        formulario), ``error_rango``, ``filas``, ``totales`` y
        ``generado_en``.
    """
    filtros = {
        clave: (parametros.get(clave) or '').strip()
        for clave in ('fecha_desde', 'fecha_hasta', 'cliente', 'tipo', 'divisa', 'estado', 'canal', 'atencion')
    }
    filtros['divisa'] = filtros['divisa'].upper()
    filtros['atencion'] = '1' if filtros['atencion'] == '1' else ''

    resultado = {
        'filtros': filtros,
        'error_rango': None,
        'filas': [],
        'totales': calcular_totales([]),
        'generado_en': timezone.now(),
    }

    fecha_desde = fecha_hasta = None
    if filtros['fecha_desde']:
        fecha_desde = _parsear_fecha(filtros['fecha_desde'])
        if fecha_desde is None:
            resultado['error_rango'] = 'Ingresá una fecha inicial válida.'
            return resultado
    if filtros['fecha_hasta']:
        fecha_hasta = _parsear_fecha(filtros['fecha_hasta'])
        if fecha_hasta is None:
            resultado['error_rango'] = 'Ingresá una fecha final válida.'
            return resultado
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        resultado['error_rango'] = 'La fecha inicial no puede ser posterior a la fecha final.'
        return resultado

    filas = _todas_las_transacciones()
    if fecha_desde:
        filas = [f for f in filas if timezone.localtime(f['creado_en']).date() >= fecha_desde]
    if fecha_hasta:
        filas = [f for f in filas if timezone.localtime(f['creado_en']).date() <= fecha_hasta]
    if filtros['cliente']:
        texto = filtros['cliente'].lower()
        filas = [f for f in filas if texto in f['cliente'].lower()]
    if filtros['tipo']:
        filas = [f for f in filas if f['tipo_codigo'] == filtros['tipo']]
    if filtros['divisa']:
        filas = [f for f in filas if filtros['divisa'] in f['divisas']]
    if filtros['estado']:
        filas = [f for f in filas if f['estado_codigo'] == filtros['estado']]
    if filtros['canal']:
        filas = [f for f in filas if f['canal'] == filtros['canal']]
    if filtros['atencion']:
        filas = [f for f in filas if f['atencion']]

    resultado['filas'] = filas
    resultado['totales'] = calcular_totales(filas)
    return resultado


def _obtener_o_none(transaccion, relacion):
    """Devuelve una relación uno-a-uno inversa opcional, o ``None`` si todavía no existe."""
    try:
        return getattr(transaccion, relacion)
    except getattr(type(transaccion), relacion).RelatedObjectDoesNotExist:
        return None


def detalle_transaccion(tipo, pk):
    """Arma el detalle, de solo lectura, de una transacción para el monitoreo (criterio 4).

    Args:
        tipo (str): ``'operacion'``, ``'cambio'`` o ``'ventanilla'``.
        pk: Identificador (UUID) de la transacción.

    Returns:
        dict | None: ``fila`` (la misma normalización que usa el listado),
        ``transaccion`` (el modelo), ``pago`` (``Pago`` asociado, o ``None``),
        ``medio_origen`` y ``medio_destino`` (texto), ``factura`` (el
        ``DocumentoElectronico`` si existe, o ``None``) y ``cajero``/``caja``
        solo en ventanilla. ``None`` si la transacción no existe.
    """
    if tipo == 'operacion':
        transaccion = CalculoOperacion.objects.select_related('cliente', 'medio_destino').filter(pk=pk).first()
        fila = _fila_operacion(transaccion) if transaccion else None
    elif tipo == 'cambio':
        transaccion = CalculoTriangulacion.objects.select_related('cliente', 'medio_destino').filter(pk=pk).first()
        fila = _fila_cambio(transaccion) if transaccion else None
    elif tipo == 'ventanilla':
        transaccion = OperacionVentanilla.objects.select_related('divisa', 'cajero', 'caja').filter(pk=pk).first()
        fila = _fila_ventanilla(transaccion) if transaccion else None
    else:
        return None
    if transaccion is None:
        return None

    factura = _obtener_o_none(transaccion, 'documento_electronico')
    if tipo == 'ventanilla':
        return {
            'fila': fila,
            'transaccion': transaccion,
            'pago': None,
            'medio_origen': 'Efectivo en ventanilla',
            'medio_destino': 'Efectivo en ventanilla',
            'factura': factura,
        }

    pago = _obtener_o_none(transaccion, 'pago')
    if pago is None:
        medio_origen = ''
    else:
        medio_origen = str(pago.metodo_pago) if pago.metodo_pago else pago.get_medio_pago_display()
    return {
        'fila': fila,
        'transaccion': transaccion,
        'pago': pago,
        'medio_origen': medio_origen,
        'medio_destino': str(transaccion.medio_destino) if transaccion.medio_destino else '',
        'factura': factura,
    }


def _formatear_fecha(valor):
    """``'YYYY-MM-DD'`` a ``'DD/MM/YYYY'``, tal como se ingresó en el filtro."""
    fecha = _parsear_fecha(valor)
    return fecha.strftime('%d/%m/%Y') if fecha else valor


def _descripcion_filtros(filtros):
    """Texto legible de los filtros aplicados, para dejarlos documentados en el archivo descargado."""
    partes = []
    if filtros['fecha_desde'] or filtros['fecha_hasta']:
        desde = _formatear_fecha(filtros['fecha_desde']) or 'el inicio'
        hasta = _formatear_fecha(filtros['fecha_hasta']) or 'hoy'
        partes.append(f'Del {desde} al {hasta}')
    if filtros['cliente']:
        partes.append(f"Cliente: {filtros['cliente']}")
    if filtros['tipo']:
        partes.append(f"Tipo: {dict(TIPO_CHOICES).get(filtros['tipo'], filtros['tipo'])}")
    if filtros['divisa']:
        partes.append(f"Divisa: {filtros['divisa']}")
    if filtros['estado']:
        partes.append(f"Estado: {dict(ESTADO_CHOICES).get(filtros['estado'], filtros['estado'])}")
    if filtros['canal']:
        partes.append(f"Canal: {dict(CANAL_CHOICES).get(filtros['canal'], filtros['canal'])}")
    if filtros['atencion']:
        partes.append('Solo las que requieren atención')
    return ' · '.join(partes) or 'Sin filtros (todas las transacciones)'


def generar_pdf(filas, totales, filtros, generado_en):
    """Arma el PDF del monitoreo: filtros aplicados, fecha, listado y totales por tipo, divisa y estado."""
    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        leftMargin=1 * cm, rightMargin=1 * cm,
    )
    estilos = getSampleStyleSheet()
    elementos = [
        Paragraph('Monitoreo de transacciones', estilos['Title']),
        Paragraph(_descripcion_filtros(filtros), estilos['Normal']),
        Paragraph(f'Generado el {timezone.localtime(generado_en):%d/%m/%Y %H:%M}', estilos['Normal']),
        Spacer(1, 0.5 * cm),
    ]

    celda = estilos['BodyText'].clone('celda', fontSize=7, leading=8)
    tabla_filas = [['Fecha', 'Cliente', 'Tipo', 'Canal', 'Divisa', 'Monto', 'Tasa', 'Importe final', 'Estado']]
    for fila in filas:
        tabla_filas.append([
            timezone.localtime(fila['creado_en']).strftime('%d/%m/%Y %H:%M'),
            Paragraph(fila['cliente'], celda),
            fila['tipo'],
            dict(CANAL_CHOICES)[fila['canal']],
            fila['divisa'],
            f"{fila['monto_origen']:.2f}",
            f"{fila['tasa']:.{fila['decimales_tasa']}f}",
            f"{fila['monto_final']:.2f} {fila['moneda_final']}",
            Paragraph(fila['estado'] + (' (!)' if fila['atencion'] else ''), celda),
        ])
    tabla = Table(tabla_filas, repeatRows=1)
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2a78d6')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f2f2f2')]),
    ]))
    elementos.extend([tabla, Spacer(1, 0.5 * cm)])

    estilo_totales = TableStyle([('GRID', (0, 0), (-1, -1), 0.5, colors.grey)])
    elementos.append(Paragraph('Totales por tipo de operación', estilos['Heading3']))
    por_tipo = [['Tipo', 'Cantidad', 'Monto (PYG)']]
    for datos in totales['por_tipo'].values():
        por_tipo.append([datos['etiqueta'], str(datos['cantidad']), f"{datos['monto_pyg']:.2f}"])
    elementos.append(Table(por_tipo, style=estilo_totales))

    elementos.append(Paragraph('Totales por divisa', estilos['Heading3']))
    por_divisa = [['Divisa', 'Cantidad', 'Monto operado']]
    for divisa, datos in totales['por_divisa'].items():
        por_divisa.append([divisa, str(datos['cantidad']), f"{datos['monto']:.2f}"])
    if len(por_divisa) == 1:
        por_divisa.append(['Sin transacciones', '-', '-'])
    elementos.append(Table(por_divisa, style=estilo_totales))

    elementos.append(Paragraph('Totales por estado', estilos['Heading3']))
    por_estado = [['Estado', 'Cantidad', 'Monto (PYG)']]
    for datos in totales['por_estado'].values():
        por_estado.append([datos['etiqueta'], str(datos['cantidad']), f"{datos['monto_pyg']:.2f}"])
    if len(por_estado) == 1:
        por_estado.append(['Sin transacciones', '-', '-'])
    elementos.append(Table(por_estado, style=estilo_totales))

    documento.build(elementos)
    return buffer.getvalue()


def generar_excel(filas, totales, filtros, generado_en):
    """Arma el Excel del monitoreo con los mismos datos, filtros y totales que el PDF."""
    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Transacciones'
    negrita = Font(bold=True)

    hoja.append(['Monitoreo de transacciones'])
    hoja['A1'].font = Font(bold=True, size=14)
    hoja.append([_descripcion_filtros(filtros)])
    hoja.append([f'Generado el {timezone.localtime(generado_en):%d/%m/%Y %H:%M}'])
    hoja.append([])

    hoja.append([
        'Fecha', 'Cliente', 'Tipo', 'Canal', 'Divisa', 'Monto', 'Tasa aplicada',
        'Comisión', 'Moneda', 'Importe final', 'Estado', 'Atención',
    ])
    for celda in hoja[hoja.max_row]:
        celda.font = negrita
    for fila in filas:
        hoja.append([
            timezone.localtime(fila['creado_en']).strftime('%d/%m/%Y %H:%M'),
            fila['cliente'],
            fila['tipo'],
            dict(CANAL_CHOICES)[fila['canal']],
            fila['divisa'],
            float(fila['monto_origen']),
            float(fila['tasa']),
            float(fila['comision']),
            fila['moneda_final'],
            float(fila['monto_final']),
            fila['estado'],
            fila['atencion'],
        ])

    hoja.append([])
    hoja.append(['Totales por tipo de operación'])
    hoja.append(['Tipo', 'Cantidad', 'Monto (PYG)'])
    for datos in totales['por_tipo'].values():
        hoja.append([datos['etiqueta'], datos['cantidad'], float(datos['monto_pyg'])])

    hoja.append([])
    hoja.append(['Totales por divisa'])
    hoja.append(['Divisa', 'Cantidad', 'Monto operado'])
    for divisa, datos in totales['por_divisa'].items():
        hoja.append([divisa, datos['cantidad'], float(datos['monto'])])

    hoja.append([])
    hoja.append(['Totales por estado'])
    hoja.append(['Estado', 'Cantidad', 'Monto (PYG)'])
    for datos in totales['por_estado'].values():
        hoja.append([datos['etiqueta'], datos['cantidad'], float(datos['monto_pyg'])])

    buffer = BytesIO()
    libro.save(buffer)
    return buffer.getvalue()
