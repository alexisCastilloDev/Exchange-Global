"""Tablero de control de ganancias: indicadores, evolución y distribución (HU GE, epic GE-14).

La ganancia de cada transacción completada es la comisión que cobra Global
Exchange, siempre normalizada a guaraníes:

- Una compra o venta online (``CalculoOperacion``) y una operación de
  ventanilla (``apps.caja.models.OperacionVentanilla``) ya cobran su
  comisión en PYG (ver ``apps.divisas.views._calcular_importe_operacion``,
  que calculan ambas).
- Un cambio entre divisas (``CalculoTriangulacion``) cobra su comisión en
  la divisa de **destino**, no en PYG (ver
  ``apps.divisas.views._calcular_triangulacion``): se reconvierte
  multiplicándola por ``tasa_venta_aplicada``, la misma tasa con la que esa
  comisión se descontó del monto bruto en destino.

El "tipo de operación" del tablero (``CASA_COMPRA``/``CASA_VENTA``/``CAMBIO``)
está siempre en la perspectiva de la **casa de cambio**, no del cliente: es
la misma inversión, ya resuelta una vez para ``apps.divisas.factura_electronica.
_tipo_transaccion``, entre ``CalculoOperacion`` (perspectiva del cliente: su
``TIPO_COMPRA`` es el cliente comprando, es decir, la casa *vendiendo*) y
``OperacionVentanilla`` (perspectiva de la casa de entrada: su ``TIPO_COMPRA``
ya significa "la casa compra"). Sin esta inversión, agrupar por tipo
mezclaría operaciones económicamente opuestas bajo la misma etiqueta.

Solo cuentan las transacciones *completadas* (criterio 6): ``ACREDITADA`` o
``RETIRADA`` para ``CalculoOperacion``/``CalculoTriangulacion`` (ver
``apps.divisas.reportes.ESTADOS_COMPLETADOS``, el mismo criterio que ya usa
el reporte de transacciones del cliente); una ``OperacionVentanilla`` no
tiene ningún estado propio — se liquida en efectivo en el momento, así que
toda fila ya está completada por definición.
"""

from collections import OrderedDict
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from apps.caja.models import OperacionVentanilla
from apps.divisas.models import CalculoOperacion, CalculoTriangulacion
from apps.divisas.reportes import ESTADOS_COMPLETADOS

CASA_COMPRA = 'CASA_COMPRA'
CASA_VENTA = 'CASA_VENTA'
CAMBIO = 'CAMBIO'
TIPO_CHOICES = (
    (CASA_COMPRA, 'Compra'),
    (CASA_VENTA, 'Venta'),
    (CAMBIO, 'Cambio'),
)

CANAL_ONLINE = 'online'
CANAL_VENTANILLA = 'ventanilla'
CANAL_CHOICES = (
    (CANAL_ONLINE, 'Online'),
    (CANAL_VENTANILLA, 'Ventanilla'),
)

PERIODO_HOY = 'hoy'
PERIODO_SEMANA = 'semana'
PERIODO_MES = 'mes'
PERIODO_ANIO = 'anio'
PERIODOS = OrderedDict([
    (PERIODO_HOY, 'Hoy'),
    (PERIODO_SEMANA, 'Última semana'),
    (PERIODO_MES, 'Último mes'),
    (PERIODO_ANIO, 'Último año'),
])
PERIODO_POR_DEFECTO = PERIODO_MES

_DURACION_DIAS_POR_PERIODO = {
    PERIODO_HOY: 1,
    PERIODO_SEMANA: 7,
    PERIODO_MES: 30,
    PERIODO_ANIO: 365,
}


def _parsear_fecha(valor):
    """Convierte ``'YYYY-MM-DD'`` a ``date``, o ``None`` si falta o no es válido."""
    if not valor:
        return None
    try:
        return datetime.strptime(valor, '%Y-%m-%d').date()
    except ValueError:
        return None


def _fila_operacion(operacion):
    """Normaliza una compra o venta online para el tablero de ganancias."""
    casa_compra_o_venta = CASA_VENTA if operacion.tipo == CalculoOperacion.TIPO_COMPRA else CASA_COMPRA
    return {
        'canal': CANAL_ONLINE,
        'tipo_codigo': casa_compra_o_venta,
        'creado_en': operacion.creado_en,
        'divisa': operacion.codigo_divisa,
        'ganancia_pyg': operacion.comision,
        'monto_pyg': operacion.monto_final,
    }


def _fila_cambio(cambio):
    """Normaliza un cambio entre divisas online para el tablero de ganancias.

    Ver el docstring del módulo: la comisión de un cambio está en la divisa
    de destino, así que se reconvierte a PYG con la misma tasa de venta con
    la que se descontó del monto bruto en destino.
    """
    ganancia_pyg = (cambio.comision * cambio.tasa_venta_aplicada).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    return {
        'canal': CANAL_ONLINE,
        'tipo_codigo': CAMBIO,
        'creado_en': cambio.creado_en,
        'divisa': f'{cambio.codigo_divisa_origen} → {cambio.codigo_divisa_destino}',
        'ganancia_pyg': ganancia_pyg,
        'monto_pyg': cambio.monto_equivalente_pyg,
    }


def _fila_ventanilla(operacion):
    """Normaliza una operación de ventanilla para el tablero de ganancias.

    A diferencia de ``_fila_operacion``, no hace falta invertir el tipo:
    ``OperacionVentanilla.TIPO_COMPRA``/``TIPO_VENTA`` ya están escritos en
    la perspectiva de la casa (ver el docstring de ese modelo).
    """
    tipo_codigo = CASA_COMPRA if operacion.tipo == OperacionVentanilla.TIPO_COMPRA else CASA_VENTA
    return {
        'canal': CANAL_VENTANILLA,
        'tipo_codigo': tipo_codigo,
        'creado_en': operacion.creado_en,
        'divisa': operacion.divisa.codigo,
        'ganancia_pyg': operacion.comision,
        'monto_pyg': operacion.monto_pyg,
    }


def _todas_las_ganancias():
    """Todas las transacciones completadas de ambos canales, normalizadas (criterio 6)."""
    filas = [
        _fila_operacion(operacion)
        for operacion in CalculoOperacion.objects.select_related('divisa')
        if operacion.estado_efectivo in ESTADOS_COMPLETADOS
    ]
    filas.extend(
        _fila_cambio(cambio)
        for cambio in CalculoTriangulacion.objects.all()
        if cambio.estado_efectivo in ESTADOS_COMPLETADOS
    )
    filas.extend(
        _fila_ventanilla(operacion)
        for operacion in OperacionVentanilla.objects.select_related('divisa')
    )
    return filas


def _en_rango(filas, fecha_desde, fecha_hasta):
    """Filtra las filas cuya fecha de creación (hora local) cae dentro del rango, ambos límites inclusive."""
    return [
        fila for fila in filas
        if fecha_desde <= timezone.localtime(fila['creado_en']).date() <= fecha_hasta
    ]


def _rango_por_periodo(periodo, hoy):
    """Traduce un período fijo (hoy/semana/mes/año) a un rango de fechas terminado hoy."""
    dias = _DURACION_DIAS_POR_PERIODO.get(periodo, _DURACION_DIAS_POR_PERIODO[PERIODO_POR_DEFECTO])
    return hoy - timedelta(days=dias - 1), hoy


def resolver_periodo(parametros):
    """Decide el rango de fechas a partir de ``?periodo=`` o ``?fecha_desde=``/``?fecha_hasta=``.

    Un rango propio (las dos fechas presentes) tiene prioridad sobre
    ``periodo``. Si es inválido —fecha inicial posterior a la final, o
    cualquiera de las dos en el futuro (criterio implícito de validación,
    mismo criterio que ya usa ``apps.divisas.views.HistorialCotizacionesView``)—
    se devuelve el motivo en vez de un rango, para no calcular nada sobre
    fechas que no tienen sentido.

    Returns:
        tuple: ``(fecha_desde, fecha_hasta, periodo, error)``. ``periodo``
        es ``'custom'`` para un rango propio; ``error`` es ``None`` si el
        rango es válido.
    """
    hoy = timezone.localdate()
    fecha_desde = _parsear_fecha(parametros.get('fecha_desde'))
    fecha_hasta = _parsear_fecha(parametros.get('fecha_hasta'))
    if fecha_desde and fecha_hasta:
        if fecha_desde > fecha_hasta:
            return None, None, None, 'La fecha inicial no puede ser posterior a la fecha final.'
        if fecha_desde > hoy or fecha_hasta > hoy:
            return None, None, None, 'No se puede consultar un rango con fechas futuras.'
        return fecha_desde, fecha_hasta, 'custom', None

    periodo = parametros.get('periodo', PERIODO_POR_DEFECTO)
    if periodo not in PERIODOS:
        periodo = PERIODO_POR_DEFECTO
    desde, hasta = _rango_por_periodo(periodo, hoy)
    return desde, hasta, periodo, None


def _rango_anterior_equivalente(fecha_desde, fecha_hasta):
    """Rango de la misma duración, inmediatamente anterior al rango dado (criterio 5)."""
    duracion = (fecha_hasta - fecha_desde).days + 1
    return fecha_desde - timedelta(days=duracion), fecha_desde - timedelta(days=1)


def calcular_indicadores(filas):
    """Ganancia total, cantidad de operaciones, monto total operado y ganancia promedio (criterio 1).

    Todo en guaraníes: ``monto_pyg`` es el volumen de negocio (el principal
    operado, no la ganancia), para distinguirlo de ``ganancia_total``.
    """
    cantidad = len(filas)
    ganancia_total = sum((fila['ganancia_pyg'] for fila in filas), Decimal('0.00'))
    monto_total_operado = sum((fila['monto_pyg'] for fila in filas), Decimal('0.00'))
    ganancia_promedio = (
        (ganancia_total / cantidad).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if cantidad else Decimal('0.00')
    )
    return {
        'ganancia_total': ganancia_total,
        'cantidad_operaciones': cantidad,
        'monto_total_operado': monto_total_operado,
        'ganancia_promedio': ganancia_promedio,
    }


def calcular_variacion(ganancia_actual, ganancia_anterior):
    """Variación porcentual de ``ganancia_actual`` respecto de ``ganancia_anterior`` (criterio 5).

    ``None`` si el período anterior no tiene ninguna ganancia contra la que
    comparar (división por cero): no hay un porcentaje que tenga sentido
    mostrar en ese caso, ni siquiera "0%" ni "100%".
    """
    if ganancia_anterior == 0:
        return None
    return ((ganancia_actual - ganancia_anterior) / ganancia_anterior * 100).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )


def _agrupacion_segun_duracion(fecha_desde, fecha_hasta):
    """Decide si la evolución se agrupa por día, semana o mes, según la duración del rango (criterio 3)."""
    dias = (fecha_hasta - fecha_desde).days + 1
    if dias <= 31:
        return 'dia'
    if dias <= 180:
        return 'semana'
    return 'mes'


def _clave_periodo(fecha, agrupacion):
    """Clave ordenable del bucket al que pertenece ``fecha``, según la agrupación elegida."""
    if agrupacion == 'dia':
        return fecha.isoformat()
    if agrupacion == 'semana':
        inicio_semana = fecha - timedelta(days=fecha.weekday())
        return inicio_semana.isoformat()
    return fecha.strftime('%Y-%m-01')


def calcular_evolucion(filas, fecha_desde, fecha_hasta):
    """Ganancia agrupada por día, semana o mes dentro del rango, en orden cronológico (criterio 3)."""
    agrupacion = _agrupacion_segun_duracion(fecha_desde, fecha_hasta)
    acumulado = OrderedDict()
    for fila in filas:
        clave = _clave_periodo(timezone.localtime(fila['creado_en']).date(), agrupacion)
        acumulado[clave] = acumulado.get(clave, Decimal('0.00')) + fila['ganancia_pyg']

    puntos = [{'periodo': clave, 'ganancia': monto} for clave, monto in sorted(acumulado.items())]
    return {'agrupacion': agrupacion, 'puntos': puntos}


def _agrupar_por(filas, obtener_clave):
    """Cantidad y ganancia total por cada valor distinto que devuelve ``obtener_clave``."""
    agrupado = OrderedDict()
    for fila in filas:
        clave = obtener_clave(fila)
        entrada = agrupado.setdefault(clave, {'cantidad': 0, 'ganancia_pyg': Decimal('0.00')})
        entrada['cantidad'] += 1
        entrada['ganancia_pyg'] += fila['ganancia_pyg']
    return agrupado


def calcular_distribucion(filas):
    """Ganancia distribuida por divisa, por tipo de operación y por canal (criterio 4)."""
    por_tipo = OrderedDict()
    for codigo, etiqueta in TIPO_CHOICES:
        subconjunto = [fila for fila in filas if fila['tipo_codigo'] == codigo]
        agrupado = _agrupar_por(subconjunto, lambda fila: fila['tipo_codigo'])
        datos = agrupado.get(codigo, {'cantidad': 0, 'ganancia_pyg': Decimal('0.00')})
        por_tipo[codigo] = {'etiqueta': etiqueta, **datos}

    por_canal = OrderedDict()
    for codigo, etiqueta in CANAL_CHOICES:
        subconjunto = [fila for fila in filas if fila['canal'] == codigo]
        agrupado = _agrupar_por(subconjunto, lambda fila: fila['canal'])
        datos = agrupado.get(codigo, {'cantidad': 0, 'ganancia_pyg': Decimal('0.00')})
        por_canal[codigo] = {'etiqueta': etiqueta, **datos}

    por_divisa = _agrupar_por(filas, lambda fila: fila['divisa'])

    return {'por_tipo': por_tipo, 'por_canal': por_canal, 'por_divisa': por_divisa}


def generar_tablero(parametros):
    """Resuelve el período y arma el tablero completo: indicadores, variación, evolución y distribución.

    Punto de entrada único de ``apps.divisas.views.TableroGananciasView``.
    ``parametros`` es cualquier mapeo tipo ``QueryDict`` con las claves
    ``periodo``, ``fecha_desde`` y ``fecha_hasta`` (las de ``request.GET``).
    """
    fecha_desde, fecha_hasta, periodo, error_rango = resolver_periodo(parametros)
    if error_rango:
        return {
            'error_rango': error_rango,
            'periodo': None,
            'fecha_desde': None,
            'fecha_hasta': None,
            'indicadores': None,
            'variacion_ganancia': None,
            'evolucion': None,
            'distribucion': None,
        }

    todas = _todas_las_ganancias()
    filas = _en_rango(todas, fecha_desde, fecha_hasta)
    indicadores = calcular_indicadores(filas)

    anterior_desde, anterior_hasta = _rango_anterior_equivalente(fecha_desde, fecha_hasta)
    ganancia_anterior = calcular_indicadores(_en_rango(todas, anterior_desde, anterior_hasta))['ganancia_total']
    variacion_ganancia = calcular_variacion(indicadores['ganancia_total'], ganancia_anterior)

    return {
        'error_rango': None,
        'periodo': periodo,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'indicadores': indicadores,
        'variacion_ganancia': variacion_ganancia,
        'evolucion': calcular_evolucion(filas, fecha_desde, fecha_hasta),
        'distribucion': calcular_distribucion(filas),
    }
