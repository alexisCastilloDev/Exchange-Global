"""Validación de cuentas bancarias y de billetera digital contra sipap-sim.

Antes de guardar un método de pago de tipo transferencia o billetera (HU
"Métodos de pago", GE-19), se confirma contra sipap-sim que la cuenta
ingresada existe y es del titular indicado — tal cual describe su propia
especificación para ``GET /api/cuentas/validar/``. No hay acá ningún cobro
ni solicitud de pago: es una verificación de datos al registrar el
método, separada de cómo ``apps.divisas.pagos_sipap`` usa SIPAP para
pagar una transacción ya confirmada. Vive en ``apps.clientes`` — no en
``apps.divisas`` — porque la dependencia entre esas dos apps va al revés
(``apps.divisas.pagos_sipap``/``pagos_stripe`` ya importan de
``apps.clientes``; que ``apps.clientes`` importara de ``apps.divisas``
invertiría esa capa sin necesidad).
"""

import requests
from django.conf import settings


class SipapComunicacionError(Exception):
    """Señala que no se pudo validar la cuenta: sipap-sim no respondió o la conexión falló."""


def validar_cuenta(numero, documento):
    """Verifica, contra sipap-sim, que una cuenta exista y sea del titular indicado.

    Args:
        numero (str): Número de cuenta o de billetera ingresado por el cliente.
        documento (str): CI o RUC del titular, ingresado por el cliente.

    Returns:
        dict: ``{'valida': False}`` si no existe una cuenta con ese número
        y ese documento; si existe, además ``titular``, ``proveedor`` (el
        nombre real del banco o billetera — no se confía en lo que
        escriba el cliente) y ``moneda``.

    Raises:
        SipapComunicacionError: si sipap-sim no responde o la conexión falla.
    """
    try:
        respuesta = requests.get(
            f'{settings.SIPAP_BASE_URL}/api/cuentas/validar/',
            params={'numero': numero, 'documento': documento},
            headers={'Authorization': f'Bearer {settings.SIPAP_API_KEY}'},
            timeout=10,
        )
        respuesta.raise_for_status()
        return respuesta.json()
    except (requests.exceptions.RequestException, ValueError) as error:
        raise SipapComunicacionError(str(error)) from error
