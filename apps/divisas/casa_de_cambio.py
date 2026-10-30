"""Consulta a sipap-sim el saldo real de la cuenta de la casa de cambio.

Global Exchange lleva su propio espejo del saldo propio
(``apps.divisas.models.CuentaPropia``), actualizado en cada entrega,
para que confirmar una operación sea una consulta local, sin depender
de que sipap-sim esté arriba en ese instante (ver
``apps.divisas.views._verificar_saldo_casa_de_cambio``). Este módulo es
para el otro uso: mantener esa cuenta propia sincronizada con la
cuenta real en sipap-sim (``apps.divisas.views.CuentaPropiaListView``),
donde un administrador gestiona las cuentas bancarias/billeteras de
verdad — así el saldo que ve un administrador en "Fondos propios"
nunca se desincroniza de lo que hay realmente cargado en sipap-sim.
"""

from datetime import datetime
from decimal import Decimal

import requests
from django.conf import settings


class SipapComunicacionError(Exception):
    """Señala que no se pudo consultar el saldo real: sipap-sim no respondió o la conexión falló."""


class DesignacionCuentaPropiaError(Exception):
    """Señala que sipap-sim rechazó la designación (cuenta inexistente o de otra moneda), con su motivo."""


def consultar_saldo_casa_de_cambio(moneda):
    """Consulta a sipap-sim el saldo real de la cuenta de la casa de cambio en una moneda.

    Args:
        moneda (str): Código de la moneda (p. ej. ``'PYG'``, ``'USD'``).

    Returns:
        Decimal | None: El saldo real, o ``None`` si esa moneda todavía
        no tiene ninguna cuenta de la casa de cambio cargada en
        sipap-sim.

    Raises:
        SipapComunicacionError: Si sipap-sim no responde o la conexión falla.
    """
    try:
        respuesta = requests.get(
            f'{settings.SIPAP_BASE_URL}/api/casa-de-cambio/{moneda}/',
            headers={'Authorization': f'Bearer {settings.SIPAP_API_KEY}'},
            timeout=10,
        )
        if respuesta.status_code == 404:
            return None
        respuesta.raise_for_status()
        datos = respuesta.json()
    except (requests.exceptions.RequestException, ValueError) as error:
        raise SipapComunicacionError(str(error)) from error
    return Decimal(str(datos['saldo']))


def consultar_cuenta_casa_de_cambio(moneda):
    """Consulta a sipap-sim qué cuenta real está designada como la casa de cambio en una moneda.

    Args:
        moneda (str): Código de la moneda (p. ej. ``'PYG'``, ``'USD'``).

    Returns:
        dict | None: ``{'numero', 'titular', 'proveedor'}`` de la cuenta
        designada, o ``None`` si todavía no hay ninguna en esa moneda.

    Raises:
        SipapComunicacionError: Si sipap-sim no responde o la conexión falla.
    """
    try:
        respuesta = requests.get(
            f'{settings.SIPAP_BASE_URL}/api/casa-de-cambio/{moneda}/cuenta/',
            headers={'Authorization': f'Bearer {settings.SIPAP_API_KEY}'},
            timeout=10,
        )
        if respuesta.status_code == 404:
            return None
        respuesta.raise_for_status()
        datos = respuesta.json()
    except (requests.exceptions.RequestException, ValueError) as error:
        raise SipapComunicacionError(str(error)) from error
    return {'numero': datos['numero'], 'titular': datos['titular'], 'proveedor': datos['proveedor']}


def designar_cuenta_casa_de_cambio(moneda, numero_cuenta, documento_titular):
    """Le pide a sipap-sim que designe una cuenta suya como la casa de cambio en una moneda.

    sipap-sim ya no decide esto por sí solo desde su propio panel (ver
    ``core.forms.CuentaForm`` del lado de sipap-sim): la cuenta se crea
    ahí como una más, pero es Global Exchange —acá, desde "Fondos
    propios"— quien le indica cuál cuenta puntual, identificada igual
    que al validar un método de pago (número y documento), le
    corresponde a cada moneda.

    Args:
        moneda (str): Código de la moneda a designar.
        numero_cuenta (str): Número de la cuenta en sipap-sim.
        documento_titular (str): CI o RUC del titular de esa cuenta.

    Returns:
        dict: ``{'numero', 'titular', 'proveedor'}`` de la cuenta recién designada.

    Raises:
        DesignacionCuentaPropiaError: Si no existe ninguna cuenta con ese
            número y documento, o si es de otra moneda (con el motivo
            que informó sipap-sim).
        SipapComunicacionError: Si sipap-sim no responde o la conexión falla.
    """
    try:
        respuesta = requests.post(
            f'{settings.SIPAP_BASE_URL}/api/casa-de-cambio/{moneda}/designar/',
            json={'numero': numero_cuenta, 'documento': documento_titular},
            headers={'Authorization': f'Bearer {settings.SIPAP_API_KEY}'},
            timeout=10,
        )
        if respuesta.status_code in (400, 404):
            raise DesignacionCuentaPropiaError(respuesta.json().get('detalle', 'No se pudo designar la cuenta.'))
        respuesta.raise_for_status()
        datos = respuesta.json()
    except (requests.exceptions.RequestException, ValueError) as error:
        raise SipapComunicacionError(str(error)) from error
    return {'numero': datos['numero'], 'titular': datos['titular'], 'proveedor': datos['proveedor']}


def consultar_movimientos_casa_de_cambio(moneda, limite=50):
    """Consulta a sipap-sim el historial real de movimientos de la cuenta propia en una moneda.

    En vez de llevar un registro propio de movimientos (que duplicaría
    algo que sipap-sim ya guarda, con más detalle), Global Exchange
    muestra este historial directamente desde ahí (ver
    ``apps.divisas.views.HistorialCuentaPropiaView``), con el estilo
    propio del sistema en vez de linkear al admin de sipap-sim.

    Args:
        moneda (str): Código de la moneda (p. ej. ``'PYG'``, ``'USD'``).
        limite (int): Cantidad máxima de movimientos a traer, los más
            recientes primero.

    Returns:
        list[dict]: Cada movimiento con ``direccion`` (``'entrada'`` o
        ``'salida'``), ``estado_display``, ``contraparte``, los montos
        ya convertidos a ``Decimal``, y las fechas ya convertidas a
        ``datetime``.

    Raises:
        SipapComunicacionError: Si sipap-sim no responde o la conexión falla.
    """
    try:
        respuesta = requests.get(
            f'{settings.SIPAP_BASE_URL}/api/casa-de-cambio/{moneda}/movimientos/',
            headers={'Authorization': f'Bearer {settings.SIPAP_API_KEY}'},
            params={'limite': limite},
            timeout=10,
        )
        respuesta.raise_for_status()
        datos = respuesta.json()
    except (requests.exceptions.RequestException, ValueError) as error:
        raise SipapComunicacionError(str(error)) from error

    movimientos = []
    for movimiento in datos['movimientos']:
        movimientos.append({
            **movimiento,
            'monto_solicitado': Decimal(str(movimiento['monto_solicitado'])),
            'monto_acreditado': (
                Decimal(str(movimiento['monto_acreditado']))
                if movimiento['monto_acreditado'] is not None else None
            ),
            'creado_en': datetime.fromisoformat(movimiento['creado_en']),
            'resuelto_en': (
                datetime.fromisoformat(movimiento['resuelto_en']) if movimiento['resuelto_en'] else None
            ),
        })
    return movimientos
