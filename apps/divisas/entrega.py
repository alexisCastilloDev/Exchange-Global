"""Entrega al cliente de lo que le corresponde tras un pago ya confirmado.

Hasta esta implementación, una transacción se consideraba completa en
cuanto el cliente pagaba (``Pago.registrar_pago`` la marcaba "Pagada") y
ahí terminaba todo: nunca existió el otro lado de la operación, que
Global Exchange le transfiera al cliente la divisa que compró, los
guaraníes de su venta, o el resultado de su cambio. Este módulo agrega
ese paso, en su versión simple: se intenta en el momento, de forma
sincrónica, inmediatamente después de registrar el pago (ver
``apps.divisas.pagos_stripe``/``apps.divisas.pagos_sipap``, los únicos
llamadores). Si sipap-sim no responde o rechaza la transferencia, no se
reintenta solo ni se inventa un estado intermedio: la transacción pasa
a "Pagada, pero la entrega al cliente falló"
(``ESTADO_ENTREGA_FALLIDA``), visible en el historial para que un
administrador la resuelva a mano. El ``Pago`` ya registrado nunca se
pierde ni se duplica (sipap-sim es idempotente por referencia, ver
``core.views.crear_transferencia_saliente``).

Recién después de que esa transferencia se confirma de verdad contra
sipap-sim se ajusta el saldo propio de Global Exchange
(``CuentaPropia.ajustar_saldos``): así el saldo que se usa para decidir
si una futura operación puede confirmarse siempre queda en espejo con
lo que realmente se transfirió, nunca adelantado a algo que todavía
podría fallar.
"""

import requests
from django.conf import settings

from apps.divisas.models import (
    CalculoOperacion,
    CuentaPropia,
    CuentaPropiaInexistenteError,
    SaldoInsuficienteError,
    divisa_a_entregar,
    divisa_a_pagar,
    monto_a_entregar,
    monto_a_pagar,
)


def _referencia_entrega(transaccion):
    """Referencia única y estable para la entrega de una transacción.

    Siempre la misma para la misma transacción (nunca se regenera), así
    que si se llama dos veces, sipap-sim reconoce la segunda llamada
    como la misma transferencia en vez de pagarle al cliente dos veces.
    """
    tipo = 'OPERACION' if isinstance(transaccion, CalculoOperacion) else 'CAMBIO'
    return f'ENTREGA-{tipo}-{transaccion.pk}'


def _enviar_transferencia_saliente(medio_destino, monto, referencia):
    """Pide a sipap-sim que transfiera ``monto`` desde la casa de cambio a ``medio_destino``.

    Único punto donde este módulo le habla a sipap-sim por HTTP
    (``POST {SIPAP_BASE_URL}/api/transferencias/``).

    Raises:
        requests.exceptions.RequestException: Si sipap-sim no responde,
            la conexión falla, o responde con un error (cuenta de
            destino inexistente, sin cuenta de la casa de cambio en esa
            moneda, etc.) — en la versión simple no se distingue el
            motivo, cualquier falla se trata igual.
    """
    respuesta = requests.post(
        f'{settings.SIPAP_BASE_URL}/api/transferencias/',
        json={
            'cuenta_destino': medio_destino.numero_cuenta,
            'documento': medio_destino.documento_titular,
            'monto': str(monto),
            'referencia': referencia,
        },
        headers={'Authorization': f'Bearer {settings.SIPAP_API_KEY}'},
        timeout=10,
    )
    respuesta.raise_for_status()


def realizar_entrega(transaccion):
    """Entrega a una transacción ya "Pagada" lo que le corresponde al cliente.

    Se llama una sola vez, justo después de que ``Pago.registrar_pago``
    deja la transacción en "Pagada" (nunca antes, y nunca si el pago ya
    existía de antes — ver los llamadores). Si no hay un medio de
    destino elegido (no debería pasar: se exige al pagar, ver
    ``apps.divisas.forms.PagarTransaccionForm``), la llamada a sipap-sim
    falla, o el saldo propio de Global Exchange no alcanza (una
    verificación ya se hizo al confirmar, pero puede haber cambiado
    entretanto), la transacción pasa a "Entrega fallida" en vez de
    quedar "Pagada" como si nada hubiera pasado.

    Args:
        transaccion: Una ``CalculoOperacion`` o ``CalculoTriangulacion``
            recién marcada "Pagada".

    Returns:
        bool: ``True`` si la entrega se completó, ``False`` si falló
        (la transacción ya quedó marcada "Entrega fallida").
    """
    medio_destino = transaccion.medio_destino
    if medio_destino is None:
        transaccion.estado = transaccion.ESTADO_ENTREGA_FALLIDA
        transaccion.save(update_fields=['estado'])
        return False

    referencia = _referencia_entrega(transaccion)
    try:
        _enviar_transferencia_saliente(medio_destino, monto_a_entregar(transaccion), referencia)
    except requests.exceptions.RequestException:
        transaccion.estado = transaccion.ESTADO_ENTREGA_FALLIDA
        transaccion.save(update_fields=['estado'])
        return False

    try:
        CuentaPropia.ajustar_saldos(
            divisa_recibir=divisa_a_pagar(transaccion), monto_recibir=monto_a_pagar(transaccion),
            divisa_entregar=divisa_a_entregar(transaccion), monto_entregar=monto_a_entregar(transaccion),
        )
    except (SaldoInsuficienteError, CuentaPropiaInexistenteError):
        # La transferencia a sipap-sim ya se hizo (es real e irreversible
        # en esta versión simple, sin compensación automática): lo que
        # falló fue solo el espejo interno. Queda igual para que un
        # administrador lo note y corrija el saldo propio a mano.
        transaccion.estado = transaccion.ESTADO_ENTREGA_FALLIDA
        transaccion.save(update_fields=['estado'])
        return False
    return True
