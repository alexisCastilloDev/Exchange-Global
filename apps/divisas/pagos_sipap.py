"""Pago por transferencia bancaria o billetera digital vía SIPAP.

Implementa la HU "Pago por transferencia bancaria vía SIPAP", pensada
—igual que ``apps.divisas.pagos_stripe``— como continuación de la HU
"Asociación de pagos a transacciones" (GE-25, ver
``apps.divisas.models.Pago``). SIPAP es el sistema de pagos interbancario
del Banco Central del Paraguay: no tiene un sandbox público al que un
proyecto académico pueda conectarse, así que se lo simula con
"sipap-sim" (``sipap_sim/``, en la raíz del repositorio), un proyecto
Django independiente que corre en su propio contenedor y con su propia
base, y que además de bancos simula billeteras digitales — este módulo
no distingue entre unos y otras: ambas se pagan con el mismo flujo
(``MetodoPago.TIPO_TRANSFERENCIA`` y ``MetodoPago.TIPO_BILLETERA`` llegan
acá por igual, ver ``apps.divisas.views.PagarTransaccionOperacionView.post``).
Este módulo le habla a sipap-sim solo por HTTP (``settings.SIPAP_BASE_URL``),
sin compartir código con él; si en algún momento se integra con el
sistema real, solo hay que apuntar esa URL a él y, si cambiara algo del
contrato HTTP, ajustar este módulo — el resto (``Pago.registrar_pago``/
``registrar_pago_observado`` como único punto de escritura) no cambia.

A diferencia de Stripe, una transferencia bancaria no es inmediata: el
cliente sale del sistema (se lo redirige a la "banca en línea" de
sipap-sim), aprueba o rechaza ahí, y la confirmación llega después por
webhook. Por eso acá hace falta un registro propio de "pago pendiente"
(``apps.divisas.models.SolicitudPagoSipap``) que no existía para Stripe.

La cuenta con la que se paga no la elige el cliente en sipap-sim: la
identifica este módulo (``_resolver_metodo_pago_sipap``) a partir del
``MetodoPago`` guardado que eligió en la pantalla de pago de siempre —
el mismo que ya validó su número de cuenta y CI/RUC contra sipap-sim al
registrarlo (ver ``apps.clientes.validacion_sipap``) — y se le manda a
sipap-sim al pedir la solicitud de cobro. Así, la "banca en línea" nunca
le muestra al cliente las cuentas de otros clientes de prueba del
sistema: solo reconoce la que ya le identificaron.

Diseño elegido para cada criterio de aceptación:

- Criterio 1 (solicitud con monto exacto y referencia única): al iniciar
  el pago, ``_obtener_o_crear_solicitud`` crea una ``SolicitudPagoSipap``
  con ``apps.divisas.models.monto_a_pagar``/``moneda_a_pagar`` (el mismo
  monto que calcula el sistema para cualquier medio de pago, nunca
  editable por el cliente) y una referencia única
  (``_generar_referencia``), se la pide a sipap-sim junto con la cuenta
  del método de pago elegido (``POST /api/solicitudes-cobro/``) y se
  redirige al cliente al ``link_pago`` que devuelve: su "banca en línea"
  simulada, que ya la reconoce.
- Criterio 2 (confirmación con identificador, banco y medio): el webhook
  (``sipap_webhook_view``), ante un evento ``"acreditada"`` cuyo monto
  coincide, llama a ``Pago.registrar_pago`` con el identificador de la
  operación SIPAP y el tipo de medio real (transferencia o billetera) de
  la solicitud.
- Criterio 3 (monto que no coincide → observado): si el monto confirmado
  difiere del esperado, llama en cambio a ``Pago.registrar_pago_observado``
  (con la diferencia) en vez de ``registrar_pago``: queda un ``Pago`` con
  ``observado=True`` para revisión, y la transacción **no** pasa a
  "Pagada". La "banca en línea" de sipap-sim siempre acredita el monto
  solicitado (no deja cambiarlo), así que este caso no se puede disparar
  desde ahí; igual queda cubierto por los tests del webhook, para el día
  en que una confirmación real reporte un monto distinto por otro motivo.
- Criterio 4 (confirmación no verificable): ``_firma_valida`` revisa la
  firma HMAC antes de mirar el contenido del payload; si no coincide, se
  responde 400 sin tocar ninguna transacción.
- Criterio 5 (rechazada o vencida sin completarse): un evento
  ``"rechazada"`` deja la ``SolicitudPagoSipap`` en ese estado sin crear
  ningún ``Pago``; si nunca llega ninguna confirmación,
  ``marcar_vencida_si_corresponde`` la pasa perezosamente a "Vencida" la
  próxima vez que el cliente visita la pantalla de pago (mismo patrón que
  ``CalculoOperacion.marcar_vencida_si_corresponde``). En ambos casos la
  transacción sigue "Confirmada" y volver a iniciar el pago genera una
  solicitud nueva (misma fila, nueva referencia y nuevo link de pago)
  para reintentar. Un evento ``"saldo_insuficiente"`` es distinto a
  propósito: sipap-sim ya detectó que la cuenta elegida no tenía fondos
  (lo detecta solo, sin que el cliente apruebe o rechace nada), así que
  no tiene sentido dejar la transacción abierta para reintentar con la
  misma cuenta — se cancela directamente (``ESTADO_CANCELADA_FONDOS_CLIENTE``).
- Criterio 6 (SIPAP no responde): ``_crear_solicitud_cobro_en_sipap`` es
  el único punto donde este módulo le habla a sipap-sim por HTTP; un
  timeout, una conexión rechazada (contenedor apagado) o una respuesta de
  error (``SIM_MODO_FALLA=error`` del lado del simulador) se traducen en
  ``SipapComunicacionError`` sin tocar la transacción, igual que un corte
  de comunicación con un banco real.
"""

import hashlib
import hmac
import json
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import IntegrityError, transaction
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.clientes.models import MetodoPago
from apps.divisas.entrega import realizar_entrega
from apps.divisas.models import (
    CalculoOperacion,
    CalculoTriangulacion,
    Pago,
    PagoRechazadoError,
    SolicitudPagoSipap,
    estados_con_pago_ya_registrado,
    moneda_a_pagar,
    monto_a_pagar,
)
from apps.divisas.views import _puede_pagarse, _resolver_transaccion_propia
import uuid

PROVEEDOR_SIPAP = 'SIPAP'


class SipapComunicacionError(Exception):
    """Señala que no se pudo hablar con sipap-sim para generar una solicitud (criterio 6).

    Envuelve cualquier falla de red real (``requests.exceptions.RequestException``)
    o una respuesta que no se puede interpretar, para que las vistas de
    este módulo no necesiten conocer la librería HTTP usada para llamar a
    sipap-sim, igual que ``stripe.error.StripeError`` desacopla a
    ``apps.divisas.pagos_stripe`` del transporte.
    """


def _generar_referencia():
    """Genera una referencia única y legible para una solicitud de pago SIPAP."""
    return f'SIPAP-{uuid.uuid4().hex[:12].upper()}'


def _firma_valida(payload, firma_recibida):
    """Verifica que un payload de webhook esté firmado con ``SIPAP_WEBHOOK_SECRET``.

    Esquema propio (HMAC-SHA256 sobre el cuerpo crudo de la request, en
    hexadecimal): SIPAP no publica un SDK como el de Stripe, así que no
    hay una firma "oficial" que verificar; es el mismo esquema que
    implementa ``sipap_sim.core.webhooks.enviar_confirmacion`` del lado
    del simulador. La comparación es de tiempo constante
    (``hmac.compare_digest``) para no filtrar por timing cuánto de la
    firma es correcto.

    Args:
        payload (bytes): El cuerpo crudo de la request (``request.body``).
        firma_recibida (str): El valor del encabezado de firma.

    Returns:
        bool: ``True`` si la firma coincide.
    """
    firma_esperada = hmac.new(
        settings.SIPAP_WEBHOOK_SECRET.encode('utf-8'), payload, hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(firma_esperada, firma_recibida or '')


def _resolver_metodo_pago_sipap(cliente, metodo_pago_id):
    """Busca el ``MetodoPago`` de transferencia o billetera elegido, con cuenta y documento.

    Mismo patrón que ``apps.divisas.pagos_stripe._resolver_metodo_pago_tarjeta``:
    sipap-sim necesita saber exactamente con qué cuenta paga el cliente
    (no le ofrece elegir entre todas las del sistema), así que acá se
    exige que el método tenga ``numero_cuenta``/``documento_titular``
    completos — los dos quedan validados contra sipap-sim al registrar el
    método (ver ``apps.clientes.validacion_sipap``), así que en la
    práctica siempre están.

    Args:
        cliente (apps.clientes.models.Cliente): El cliente que va a pagar.
        metodo_pago_id: El ``pk`` recibido en ``?metodo_pago=``, tal como
            lo elige el cliente en el formulario de pago de siempre (ver
            ``apps.divisas.views.PagarTransaccionOperacionView.post``).

    Returns:
        apps.clientes.models.MetodoPago | None: El método, si existe, es
        del cliente, es de transferencia o billetera, y tiene cuenta y
        documento completos; ``None`` en cualquier otro caso.
    """
    return MetodoPago.objects.filter(
        pk=metodo_pago_id,
        cliente=cliente,
        tipo_medio__in=(MetodoPago.TIPO_TRANSFERENCIA, MetodoPago.TIPO_BILLETERA),
    ).exclude(numero_cuenta__isnull=True).exclude(numero_cuenta='').exclude(
        documento_titular__isnull=True,
    ).exclude(documento_titular='').first()


def _crear_solicitud_cobro_en_sipap(solicitud, url_retorno):
    """Pide a sipap-sim que genere el link de pago de una solicitud, y lo guarda en ella.

    Único punto donde este módulo le habla a sipap-sim por HTTP
    (``POST {SIPAP_BASE_URL}/api/solicitudes-cobro/``, autenticado con
    ``Authorization: Bearer {SIPAP_API_KEY}``). Manda también el número
    de cuenta y el documento del ``metodo_pago`` de la solicitud, para
    que la "banca en línea" reconozca esa cuenta de entrada en vez de
    ofrecer todas las del sistema para elegir. Deja
    ``solicitud.id_externo`` y ``solicitud.link_pago`` con lo que
    responda, sin guardar nada: eso lo hace el llamador, después de
    confirmar que esta llamada no falló.

    Args:
        solicitud (apps.divisas.models.SolicitudPagoSipap): La solicitud
            recién armada (todavía no guardada necesariamente), con
            ``metodo_pago`` ya asignado.
        url_retorno (str): La URL absoluta a la que sipap-sim debe
            devolver al cliente después de aprobar o rechazar en su
            "banca en línea" (el detalle de esta misma transacción).

    Raises:
        SipapComunicacionError: Si sipap-sim no responde, la conexión
            falla, responde con un error, o la respuesta no es JSON
            válido (criterio 6).
    """
    try:
        respuesta = requests.post(
            f'{settings.SIPAP_BASE_URL}/api/solicitudes-cobro/',
            json={
                'monto': str(solicitud.monto),
                'moneda': solicitud.moneda,
                'referencia': solicitud.referencia,
                'url_retorno': url_retorno,
                'cuenta_origen_numero': solicitud.metodo_pago.numero_cuenta,
                'cuenta_origen_documento': solicitud.metodo_pago.documento_titular,
            },
            headers={'Authorization': f'Bearer {settings.SIPAP_API_KEY}'},
            timeout=10,
        )
        respuesta.raise_for_status()
        datos = respuesta.json()
    except (requests.exceptions.RequestException, ValueError) as error:
        raise SipapComunicacionError(str(error)) from error

    solicitud.id_externo = datos.get('id') or ''
    solicitud.link_pago = datos.get('link_pago') or ''


def _obtener_o_crear_solicitud(transaccion, tipo_transaccion, metodo_pago, url_retorno):
    """Devuelve la solicitud de pago SIPAP vigente de esta transacción, creándola si falta.

    Como ``SolicitudPagoSipap`` es un ``OneToOneField`` con la transacción
    (nunca dos solicitudes para la misma), reintentar después de una
    solicitud "Rechazada" o "Vencida" reutiliza la misma fila con una
    referencia y un link de pago nuevos, en vez de crear una segunda
    (criterio 5) — y puede quedar asociada a un método de pago distinto,
    si el cliente elige otra cuenta guardada al reintentar. Una solicitud
    "Observada" no se reinicia sola: ya hay un pago real registrado con
    un monto que no coincide, así que hace falta que alguien lo revise
    antes de intentar de nuevo.

    Args:
        transaccion: Una ``CalculoOperacion`` o ``CalculoTriangulacion``
            ya "Confirmada".
        tipo_transaccion (str): ``"operacion"`` o ``"cambio"``, solo para
            mantener la misma convención que
            ``apps.divisas.pagos_stripe`` (no se usa todavía, pero evita
            tener que cambiar la firma si en el futuro hace falta
            diferenciar algo entre los dos tipos).
        metodo_pago (apps.clientes.models.MetodoPago): La cuenta bancaria
            o billetera guardada que el cliente eligió para pagar (ver
            ``_resolver_metodo_pago_sipap``); sipap-sim resuelve
            transferencia y billetera con el mismo flujo, pero hace falta
            recordar cuál es para que el ``Pago`` resultante lo muestre
            bien y para que la "banca en línea" reconozca la cuenta.
        url_retorno (str): A dónde tiene que volver el cliente después de
            resolver el pago en sipap-sim (ver ``_crear_solicitud_cobro_en_sipap``).

    Returns:
        apps.divisas.models.SolicitudPagoSipap: La solicitud vigente
        (pendiente, o resuelta — la vista decide qué hacer según su
        estado), con ``link_pago`` listo para redirigir al cliente.

    Raises:
        SipapComunicacionError: Si falla pedirle a sipap-sim la solicitud
            nueva (criterio 6). No se guarda nada en ese caso.
    """
    campo = 'calculo_operacion' if isinstance(transaccion, CalculoOperacion) else 'calculo_triangulacion'
    solicitud = SolicitudPagoSipap.objects.filter(**{campo: transaccion}).first()
    monto = monto_a_pagar(transaccion)
    moneda = moneda_a_pagar(transaccion)
    vence_en = timezone.now() + timedelta(seconds=settings.SIPAP_SOLICITUD_VIGENCIA_SEGUNDOS)
    if transaccion.tasa_vence_en is not None and transaccion.tasa_vence_en < vence_en:
        # La solicitud de cobro nunca puede durar más que la tasa que la
        # respalda: no tiene sentido dejarla "Pendiente" en sipap-sim
        # después de que, del lado de Global Exchange, ya no corresponde
        # liquidarla a esa tasa.
        vence_en = transaccion.tasa_vence_en

    if solicitud is None:
        solicitud = SolicitudPagoSipap(
            referencia=_generar_referencia(), monto=monto, moneda=moneda,
            medio_pago=metodo_pago.tipo_medio, metodo_pago=metodo_pago,
            vence_en=vence_en, **{campo: transaccion},
        )
        _crear_solicitud_cobro_en_sipap(solicitud, url_retorno)
        try:
            with transaction.atomic():
                solicitud.save()
        except IntegrityError:
            # Carrera entre dos solicitudes simultáneas para la misma
            # transacción (por ejemplo, un doble clic o dos pestañas):
            # la otra ya ganó y creó la fila (``OneToOneField``, nunca
            # dos solicitudes para la misma transacción). La de sipap-sim
            # que se acaba de generar queda huérfana ahí (vence sola,
            # sin que nadie la pague), y se usa la que ya quedó guardada.
            # El ``atomic()`` alrededor del ``save()`` es necesario para
            # que, en Postgres, el error no deje la transacción abierta
            # en un estado roto que bloquee esta misma consulta de abajo.
            return SolicitudPagoSipap.objects.get(**{campo: transaccion})
        return solicitud

    solicitud.marcar_vencida_si_corresponde()
    if solicitud.estado in (SolicitudPagoSipap.ESTADO_RECHAZADA, SolicitudPagoSipap.ESTADO_VENCIDA):
        solicitud.referencia = _generar_referencia()
        solicitud.monto = monto
        solicitud.moneda = moneda
        solicitud.medio_pago = metodo_pago.tipo_medio
        solicitud.metodo_pago = metodo_pago
        solicitud.estado = SolicitudPagoSipap.ESTADO_PENDIENTE
        solicitud.banco_origen = None
        solicitud.vence_en = vence_en
        _crear_solicitud_cobro_en_sipap(solicitud, url_retorno)
        solicitud.save()

    return solicitud


class _IniciarPagoSipapBaseView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Base común para iniciar el pago por transferencia/billetera SIPAP de una transacción propia.

    Las subclases (``IniciarPagoSipapOperacionView``/
    ``IniciarPagoSipapCambioView``) solo fijan ``model``,
    ``tipo_transaccion`` y ``url_detalle``, igual que las de
    ``apps.divisas.pagos_stripe``.
    """

    model = None
    tipo_transaccion = None
    url_detalle = None

    def test_func(self):
        """Permite iniciar el pago solo a los roles que pueden operar."""
        roles = self.request.session.get('keycloak_roles', [])
        return (
            'cliente' in roles
            and not self.request.user.is_staff
            and self.request.user.clientes.filter(is_active=True).exists()
        )

    def get(self, request, *args, **kwargs):
        """Redirige a la "banca en línea" de sipap-sim, creando la solicitud si falta.

        La cuenta bancaria o billetera elegida llega en ``?metodo_pago=``
        (mismo patrón que ``apps.divisas.pagos_stripe`` con
        ``_resolver_metodo_pago_tarjeta``), puesto por
        ``apps.divisas.views.PagarTransaccionOperacionView.post`` al
        redirigir acá: es uno de los métodos guardados del cliente (HU
        "Métodos de pago"), con su cuenta ya validada contra sipap-sim.

        Returns:
            HttpResponse: Redirección externa al ``link_pago`` de
            sipap-sim si todo sale bien; de vuelta al detalle de la
            transacción con un mensaje si no se puede pagar todavía, si
            el método de pago no es válido, si hay un pago observado
            pendiente de revisión, o si sipap-sim no respondió
            (criterio 6).
        """
        transaccion, redireccion = _resolver_transaccion_propia(
            request, self.model, kwargs['pk'], url_fallback=self.url_detalle,
        )
        if redireccion is not None:
            return redireccion
        transaccion.marcar_vencida_si_corresponde()

        if not _puede_pagarse(transaccion):
            if transaccion.estado_efectivo in estados_con_pago_ya_registrado(self.model):
                messages.error(request, 'Esta transacción ya fue pagada.')
            elif transaccion.tasa_vencida:
                messages.error(
                    request,
                    'La tasa fijada al confirmar esta transacción ya venció. Debe recalcularla.',
                )
            else:
                messages.error(request, 'Esta transacción no está en condiciones de pagarse.')
            return redirect(self.url_detalle, pk=transaccion.pk)

        metodo_pago = _resolver_metodo_pago_sipap(transaccion.cliente, request.GET.get('metodo_pago'))
        if metodo_pago is None:
            messages.error(request, 'Elegí una cuenta bancaria o billetera guardada para pagar por SIPAP.')
            return redirect(self.url_detalle, pk=transaccion.pk)

        url_retorno = request.build_absolute_uri(reverse(self.url_detalle, kwargs={'pk': transaccion.pk}))
        try:
            solicitud = _obtener_o_crear_solicitud(transaccion, self.tipo_transaccion, metodo_pago, url_retorno)
        except SipapComunicacionError:
            # Criterio 6: SIPAP no respondió o la conexión falló. No se
            # toca la transacción, que sigue "Confirmada" tal como estaba.
            messages.error(
                request,
                'No se pudo conectar con SIPAP para generar la solicitud de pago. '
                'Intentá nuevamente en unos minutos.',
            )
            return redirect(self.url_detalle, pk=transaccion.pk)

        if solicitud.estado == SolicitudPagoSipap.ESTADO_OBSERVADA:
            messages.warning(
                request,
                'Ya se registró una transferencia para esta transacción, pero por un monto distinto '
                'al esperado. Quedó pendiente de revisión; contactate con un analista o administrador.',
            )
            return redirect(self.url_detalle, pk=transaccion.pk)

        return redirect(solicitud.link_pago)


class IniciarPagoSipapOperacionView(_IniciarPagoSipapBaseView):
    """Inicia el pago por transferencia/billetera SIPAP de una compra o venta propia ya "Confirmada".

    A ella redirige automáticamente
    ``apps.divisas.views.PagarTransaccionOperacionView.post`` cuando el
    método de pago elegido en el formulario de pago normal es de tipo
    "transferencia" o "billetera" (``MetodoPago.TIPO_TRANSFERENCIA``/
    ``MetodoPago.TIPO_BILLETERA``): ambos se resuelven con el mismo flujo
    de sipap-sim, que simula indistintamente bancos y billeteras
    digitales.
    """

    model = CalculoOperacion
    tipo_transaccion = 'operacion'
    url_detalle = 'divisas:detalle_transaccion_operacion'


class IniciarPagoSipapCambioView(_IniciarPagoSipapBaseView):
    """Inicia el pago por transferencia/billetera SIPAP de un cambio entre divisas propio ya "Confirmado".

    Ver ``IniciarPagoSipapOperacionView``: mismo criterio, al que redirige
    ``apps.divisas.views.PagarTransaccionCambioView.post``.
    """

    model = CalculoTriangulacion
    tipo_transaccion = 'cambio'
    url_detalle = 'divisas:detalle_transaccion_cambio'


def _procesar_confirmacion_sipap(solicitud, datos):
    """Resuelve una solicitud pendiente según la confirmación recibida de SIPAP.

    Args:
        solicitud (apps.divisas.models.SolicitudPagoSipap): La solicitud a
            resolver; si ya no está "Pendiente" (repetición del webhook, o
            ya vencida/rechazada), no hace nada.
        datos (dict): El payload ya decodificado del webhook, con
            ``estado`` (``"acreditada"``/``"rechazada"``), ``monto``,
            ``id_operacion`` y ``banco_origen``.
    """
    if solicitud.estado != SolicitudPagoSipap.ESTADO_PENDIENTE:
        return

    transaccion = solicitud.transaccion
    if transaccion is None:
        return

    estado_sipap = (datos.get('estado') or '').lower()
    if estado_sipap == 'rechazada':
        # Criterio 5: queda "Rechazada", sin crear ningún Pago. La
        # transacción sigue "Confirmada" y puede reintentarse.
        solicitud.estado = SolicitudPagoSipap.ESTADO_RECHAZADA
        solicitud.save(update_fields=['estado'])
        return

    if estado_sipap == 'saldo_insuficiente':
        # A diferencia de "rechazada" (una decisión del cliente, que deja
        # la transacción "Confirmada" para reintentar), sipap-sim ya
        # detectó que la cuenta elegida no tenía fondos: no tiene sentido
        # dejarla abierta para reintentar con la misma cuenta, así que se
        # cancela la transacción directamente, sin crear ningún Pago.
        solicitud.estado = SolicitudPagoSipap.ESTADO_SALDO_INSUFICIENTE
        solicitud.save(update_fields=['estado'])
        transaccion.estado = transaccion.ESTADO_CANCELADA_FONDOS_CLIENTE
        transaccion.save(update_fields=['estado'])
        return

    if estado_sipap != 'acreditada':
        return

    try:
        monto_recibido = Decimal(str(datos.get('monto')))
    except (InvalidOperation, TypeError):
        return

    identificador_externo = datos.get('id_operacion') or ''
    solicitud.banco_origen = datos.get('banco_origen') or None

    if monto_recibido == solicitud.monto:
        try:
            pago, creado = Pago.registrar_pago(
                transaccion,
                medio_pago=solicitud.medio_pago,
                proveedor=PROVEEDOR_SIPAP,
                identificador_externo=identificador_externo,
                monto=monto_recibido,
                metodo_pago=solicitud.metodo_pago,
            )
        except PagoRechazadoError:
            # La transacción ya no está en condiciones de pagarse (p. ej.
            # otro medio la pagó mientras tanto). No hay más que hacer.
            return
        if creado and transaccion.estado == transaccion.ESTADO_PAGADA:
            # Entrega lo que corresponda (la divisa comprada, el resultado
            # de un cambio, o los guaraníes de una venta) recién ahora, la
            # primera vez que se registra este pago, nunca en una
            # repetición idempotente del mismo webhook, y nunca si llegó
            # fuera de plazo (ver Pago.registrar_pago).
            realizar_entrega(transaccion)
        solicitud.pago = pago
        solicitud.estado = SolicitudPagoSipap.ESTADO_ACREDITADA
    else:
        # Criterio 3: el monto no coincide. Queda observado, sin marcar
        # la transacción como "Pagada".
        try:
            pago, _creado = Pago.registrar_pago_observado(
                transaccion,
                medio_pago=solicitud.medio_pago,
                proveedor=PROVEEDOR_SIPAP,
                identificador_externo=identificador_externo,
                monto=monto_recibido,
                diferencia=monto_recibido - solicitud.monto,
                metodo_pago=solicitud.metodo_pago,
            )
        except PagoRechazadoError:
            return
        solicitud.pago = pago
        solicitud.estado = SolicitudPagoSipap.ESTADO_OBSERVADA

    solicitud.save()


@csrf_exempt
def sipap_webhook_view(request):
    """Recibe las confirmaciones de sipap-sim y resuelve la solicitud de pago correspondiente.

    Es el único lugar donde una notificación de sipap-sim se traduce en
    un pago real (o en una observación, o en un rechazo). Queda exento de
    CSRF porque lo llama sipap-sim, no un navegador con sesión de Django,
    y en cambio su seguridad depende por completo de ``_firma_valida``
    (criterio 4).

    Returns:
        HttpResponse: 200 si el evento se procesó (incluso si no requería
        ninguna acción, p. ej. una referencia desconocida), 400 si la
        firma no es válida, el payload no es JSON, o el método no es
        POST.
    """
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    payload = request.body
    firma = request.META.get('HTTP_X_SIPAP_SIGNATURE', '')
    if not _firma_valida(payload, firma):
        # Criterio 4: firma inválida. Se rechaza sin tocar ninguna
        # transacción y sin procesar el contenido del payload.
        return HttpResponseBadRequest('Firma inválida.')

    try:
        datos = json.loads(payload)
    except ValueError:
        return HttpResponseBadRequest('Payload inválido.')

    solicitud = SolicitudPagoSipap.objects.filter(referencia=datos.get('referencia')).first()
    if solicitud is None:
        # Referencia desconocida: no es un error del remitente, pero no
        # hay nada legítimo que hacer con ella.
        return HttpResponse(status=200)

    _procesar_confirmacion_sipap(solicitud, datos)
    return HttpResponse(status=200)
