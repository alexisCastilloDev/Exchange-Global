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
(``ESTADO_ENTREGA_FALLIDA``), visible tanto para un administrador
("Entregas pendientes") como para el propio cliente (en el detalle de
su transacción), para reintentarla desde cualquiera de los dos lados
(ver ``reintentar_entrega``). El ``Pago`` ya registrado nunca se pierde
ni se duplica (sipap-sim es idempotente por referencia, ver
``core.views.crear_transferencia_saliente``).

Recién después de que esa transferencia se confirma de verdad contra
sipap-sim se ajusta el saldo propio de Global Exchange
(``CuentaPropia.ajustar_saldos``): así el saldo que se usa para decidir
si una futura operación puede confirmarse siempre queda en espejo con
lo que realmente se transfirió, nunca adelantado a algo que todavía
podría fallar.

Una entrega exitosa de una compra o de un cambio entre divisas (HU
"Acreditación de fondos", GE-23) deja la transacción en "Acreditada" en
vez de "Pagada" sin más, con la fecha, hora y referencia externa de esa
acreditación. Una venta exitosa, en cambio, queda "Retirada" (HU
"Retiro de fondos", GE-24, ver ``_es_retiro``): mismo mecanismo de
entrega, al mismo momento (apenas se confirma el pago, sin ninguna
acción extra del cliente — se paga y se recibe, los tres tipos de
transacción por igual), solo que con un nombre de estado distinto a
propósito, para que el cliente distinga de un vistazo si lo que pasó
fue que Global Exchange le entregó algo (compra o cambio) o que él
retiró lo suyo (venta).
"""

import requests
from django.conf import settings
from django.utils import timezone

from apps.divisas.models import (
    CalculoOperacion,
    CalculoTriangulacion,
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


def _es_retiro(transaccion):
    """Indica si una entrega exitosa de esta transacción debe llamarse "Retirada", no "Acreditada".

    Solo una venta (ver ``CalculoOperacion.ESTADO_RETIRADA``, HU "Retiro
    de fondos" GE-24): un cambio entre divisas nunca llega a este caso,
    así que esta función nunca necesita mirar
    ``CalculoTriangulacion.ESTADO_RETIRADA`` (que, a propósito, ni
    siquiera existe — ver su ``ESTADO_CHOICES``).
    """
    return not isinstance(transaccion, CalculoTriangulacion) and transaccion.tipo == CalculoOperacion.TIPO_VENTA


def realizar_entrega(transaccion):
    """Entrega a una transacción ya "Pagada" lo que le corresponde al cliente.

    Se llama una sola vez, justo después de que ``Pago.registrar_pago``
    deja la transacción en "Pagada" (nunca antes, y nunca si el pago ya
    existía de antes — ver los llamadores), o desde ``reintentar_entrega``
    si una entrega anterior quedó fallida. Si no hay un medio de
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
        bool: ``True`` si la entrega se completó (la transacción queda
        "Acreditada" para una compra o un cambio, o "Retirada" para una
        venta, ver ``_es_retiro``), ``False`` si falló (la transacción
        ya quedó marcada "Entrega fallida").
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

    if _es_retiro(transaccion):
        transaccion.estado = transaccion.ESTADO_RETIRADA
        transaccion.retirado_en = timezone.now()
        transaccion.referencia_retiro = referencia
        transaccion.save(update_fields=['estado', 'retirado_en', 'referencia_retiro'])
    else:
        transaccion.estado = transaccion.ESTADO_ACREDITADA
        transaccion.acreditado_en = timezone.now()
        transaccion.referencia_acreditacion = referencia
        transaccion.save(update_fields=['estado', 'acreditado_en', 'referencia_acreditacion'])
    return True


def reintentar_entrega(transaccion):
    """Reintenta la entrega de una transacción que quedó en "Entrega fallida".

    La devuelve primero a "Pagada" (``realizar_entrega`` no sabe
    "reanudar" desde una entrega fallida por sí sola, solo entregar algo
    que está "Pagada") y recién ahí llama a ``realizar_entrega``, que
    decide el resultado final exactamente igual que en el intento
    original. Lo usan tanto un administrador (pantalla "Entregas
    pendientes") como el propio cliente, desde el detalle de su
    transacción.

    Args:
        transaccion: Una ``CalculoOperacion`` o ``CalculoTriangulacion``.

    Returns:
        bool | None: Lo mismo que ``realizar_entrega`` si había algo
        para reintentar, o ``None`` si la transacción ya no estaba en
        "Entrega fallida" (nada que hacer).
    """
    if transaccion.estado != transaccion.ESTADO_ENTREGA_FALLIDA:
        return None
    transaccion.estado = transaccion.ESTADO_PAGADA
    transaccion.save(update_fields=['estado'])
    return realizar_entrega(transaccion)
