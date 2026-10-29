"""Pago con tarjeta de crédito/débito vía Stripe.

Implementa la HU "Pago con tarjeta vía Stripe", pensada explícitamente como
continuación de la HU "Asociación de pagos a transacciones" (GE-25, ver
``apps.divisas.models.Pago``). Ninguna de las vistas de este módulo toca
``transaccion.estado`` directamente: todas pasan, como cualquier otro medio
de pago, por ``Pago.registrar_pago``, que sigue siendo el único punto de
escritura.

Una tarjeta se agrega como un ``MetodoPago`` más (GE-19), con dos campos
genéricos que la vinculan a Stripe sin guardar nunca el número real:
``proveedor_externo`` (``MetodoPago.PROVEEDOR_STRIPE``) y
``referencia_externa`` (el id de un ``PaymentMethod`` de Stripe). El alta
pasa por ``IniciarAgregarTarjetaStripeView``/``confirmar_tarjeta_stripe_view``
(capturan la tarjeta en la propia página de Stripe, vía un ``SetupIntent``,
y crean el ``MetodoPago`` recién al confirmar); el formulario manual de
GE-19 (``apps.clientes.forms.MetodoPagoForm``) deja de ofrecer "Tarjeta"
como opción para forzar que toda tarjeta nueva pase por ahí.

Al pagar, el cliente elige ese mismo ``MetodoPago`` en el formulario de
pago de siempre; si es de tipo tarjeta, se cobra directo por API con la
``referencia_externa`` guardada (``PaymentIntent`` ``off_session=True``) —
sin mostrar ninguna página de Stripe. Si ese cobro directo falla (rechazo o
porque el banco exige una autenticación adicional, 3-D Secure/SCA), se cae
a una sesión de `Stripe Checkout <https://stripe.com/docs/payments/checkout>`_
para que el cliente confirme ahí, con esa misma tarjeta preseleccionada
(``customer=...``).

Diseño elegido para cada criterio de aceptación:

- Criterio 1 (monto exacto, no modificable): tanto la sesión de Checkout
  como el ``PaymentIntent`` del cobro directo se crean con
  ``apps.divisas.models.monto_a_pagar`` tomado del servidor (siempre
  ``monto_final`` en PYG, porque una tarjeta solo puede pagar una
  compra — ver el docstring de esa función para venta/cambio); el
  cliente nunca tiene un campo para escribir un monto.
- Criterio 2 (confirmación del pago): para Checkout, ``stripe_webhook_view``
  procesa ``checkout.session.completed`` con ``payment_status == "paid"``
  y llama a ``Pago.registrar_pago``; para el cobro directo, la propia
  respuesta síncrona del ``PaymentIntent`` (``status == "succeeded"``) es
  la confirmación, sin esperar ningún webhook. En ambos casos el medio
  queda como ``MetodoPago.TIPO_TARJETA`` y el identificador externo es un
  id de Stripe.
- Criterio 3 (firma inválida): ``stripe.Webhook.construct_event`` valida la
  firma antes de mirar el contenido; si falla, se responde 400 sin tocar
  ninguna transacción.
- Criterio 4 (pago rechazado): con Checkout, un rechazo de tarjeta ocurre
  *dentro* de la página hospedada por Stripe (que ya le muestra al cliente
  el motivo y le permite reintentar sin salir de ahí, sin generar ningún
  webhook porque la sesión nunca se completó). Con el cobro directo de una
  tarjeta guardada, un rechazo se captura como ``stripe.error.CardError``:
  se informa con un mensaje claro y se cae al camino de Checkout para
  reintentar. En ningún caso se toca la transacción.
- Criterio 5 (abandono/cancelación): ``cancel_url`` vuelve a la pantalla de
  detalle de la transacción con un aviso; como el webhook nunca se disparó,
  la transacción sigue "Confirmada" y el botón de pago sigue disponible.
- Criterio 6 (Stripe no responde): toda llamada a la API de Stripe
  (crear/consultar el ``Customer``, crear el ``PaymentIntent`` o la sesión
  de Checkout) está envuelta en un ``try/except stripe.error.StripeError``
  (cubre ``APIConnectionError`` y cualquier otro error de comunicación); si
  falla, se informa el problema sin tocar la transacción.
"""

from datetime import timedelta
from decimal import ROUND_HALF_UP

import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import Http404, HttpResponse, HttpResponseBadRequest, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.clientes.forms import AgregarTarjetaStripeForm
from apps.clientes.models import MetodoPago
from apps.divisas.entrega import realizar_entrega
from apps.divisas.models import (
    CalculoOperacion,
    CalculoTriangulacion,
    Divisa,
    Pago,
    PagoRechazadoError,
    estados_con_pago_ya_registrado,
    moneda_a_pagar,
    monto_a_pagar,
)
from apps.divisas.views import _puede_pagarse, _resolver_transaccion_propia

PROVEEDOR_STRIPE = 'STRIPE'

# Monedas para las que Stripe no usa centavos: el monto se manda tal cual,
# en vez de multiplicado por 100. PYG (la moneda de liquidación de toda
# compra/venta, ver `_moneda_de_liquidacion`) es "sin decimales" en Stripe,
# así que es la que más importa acá; el resto de la lista es la que publica
# Stripe en su documentación, por si en el futuro se habilita un cambio que
# liquide en una de ellas.
MONEDAS_SIN_DECIMALES_STRIPE = frozenset({
    'BIF', 'CLP', 'DJF', 'GNF', 'JPY', 'KMF', 'KRW', 'MGA', 'PYG', 'RWF',
    'UGX', 'VND', 'VUV', 'XAF', 'XOF', 'XPF',
})


def _moneda_de_liquidacion(transaccion):
    """Devuelve el código ISO de la moneda en la que se cobra la transacción.

    Delegado en ``apps.divisas.models.moneda_a_pagar``: una compra/venta
    siempre se cobra en PYG; un cambio entre divisas se cobra en su divisa
    de **origen** (lo que el cliente entrega), no en la de destino (lo que
    recibe a cambio) — ver ``monto_a_pagar`` para el porqué.
    """
    return moneda_a_pagar(transaccion)


def _monto_en_unidad_minima_stripe(monto, codigo_moneda):
    """Convierte un monto decimal a la unidad entera que espera Stripe.

    Stripe siempre recibe un entero: la cantidad de centavos para la
    mayoría de las monedas, o el monto tal cual para las "sin decimales"
    (``MONEDAS_SIN_DECIMALES_STRIPE``). Tratar a PYG como si tuviera
    centavos cobraría, por error, 100 veces el monto real.
    """
    if codigo_moneda in MONEDAS_SIN_DECIMALES_STRIPE:
        return int(monto.to_integral_value(rounding=ROUND_HALF_UP))
    return int((monto * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _url_absoluta(request, nombre_url, **kwargs):
    """Arma una URL absoluta (con esquema y dominio) para Stripe.

    ``success_url``/``cancel_url`` los visita el navegador del cliente
    después de pasar por Stripe, así que no pueden ser rutas relativas.
    """
    return request.build_absolute_uri(reverse(nombre_url, kwargs=kwargs))


def _a_dict(stripe_obj):
    """Convierte un objeto de Stripe a un dict plano (recursivamente).

    El SDK de Stripe devuelve ``StripeObject`` en vez de ``dict``: no
    tienen ``.get()`` ni son iterables directamente (llamarlos así tira
    ``AttributeError``/``TypeError``), hay que pedirles ``.to_dict()``
    explícitamente. Un dict ya plano (como los que arman los tests, o un
    valor ``None``) se devuelve tal cual, sin tocarlo.
    """
    if stripe_obj is None:
        return {}
    to_dict = getattr(stripe_obj, 'to_dict', None)
    return to_dict() if callable(to_dict) else stripe_obj


def _obtener_o_crear_cliente_stripe(cliente):
    """Devuelve el ``Customer`` de Stripe de este cliente, creándolo si falta.

    Es lo que permite reutilizar una tarjeta entre pagos sin guardar nunca
    el número real en esta base: la tarjeta se guarda del lado de Stripe,
    contra este ``Customer``, nunca contra un ``MetodoPago`` local.

    Args:
        cliente (apps.clientes.models.Cliente): El cliente que va a pagar.

    Returns:
        str: El id del ``Customer`` de Stripe (``cliente.stripe_customer_id``,
        recién creado si todavía no existía).
    """
    if cliente.stripe_customer_id:
        return cliente.stripe_customer_id

    customer = stripe.Customer.create(
        name=str(cliente),
        email=cliente.email or None,
        metadata={'cliente_id': str(cliente.pk)},
    )
    cliente.stripe_customer_id = customer.id
    cliente.save(update_fields=['stripe_customer_id'])
    return customer.id


_configuracion_solo_tarjeta_cache = {'id': None}


def _configuracion_solo_tarjeta():
    """Devuelve el id de una ``PaymentMethodConfiguration`` que solo habilita tarjeta.

    Stripe ya no deja restringir los medios de pago de una sesión de
    Checkout con ``payment_method_types`` (lo retiró de la API, ver
    docstring del módulo): sin esa restricción, Checkout ofrece cualquier
    medio habilitado en la cuenta, típicamente también "Link" (el
    autocompletado propio de Stripe), que Checkout muestra de forma muy
    prominente. Si el cliente lo elige en vez de una tarjeta, el
    ``PaymentMethod`` resultante es de tipo ``"link"``, no ``"card"``, y no
    tiene los datos (marca, últimos 4 dígitos) que esta HU necesita
    guardar.

    En vez de eso, se usa una ``PaymentMethodConfiguration`` propia (con
    tarjeta prendida y Link apagado) y se la referencia por
    ``payment_method_configuration`` al crear la sesión. Se reutiliza la
    misma configuración entre llamadas (identificada por su nombre, cacheado
    en este proceso) en vez de crear una nueva en cada pago.

    Returns:
        str: El id de la ``PaymentMethodConfiguration`` a usar.
    """
    if _configuracion_solo_tarjeta_cache['id']:
        return _configuracion_solo_tarjeta_cache['id']

    nombre = 'Global Exchange - solo tarjeta'
    for configuracion in stripe.PaymentMethodConfiguration.list(limit=100).data:
        if configuracion.name == nombre:
            _configuracion_solo_tarjeta_cache['id'] = configuracion.id
            return configuracion.id

    nueva = stripe.PaymentMethodConfiguration.create(
        name=nombre,
        card={'display_preference': {'preference': 'on'}},
        link={'display_preference': {'preference': 'off'}},
    )
    _configuracion_solo_tarjeta_cache['id'] = nueva.id
    return nueva.id


def _expires_at_checkout(transaccion):
    """Calcula el ``expires_at`` de una sesión de Checkout alineado con la tasa fijada.

    Stripe exige que ``expires_at`` quede entre 30 minutos y 24 horas
    después de creada la sesión (verificado contra la documentación
    oficial de Stripe Checkout). Dentro de ese rango, se usa
    ``transaccion.tasa_vence_en`` (ver ``CalculoOperacion.tasa_vencida``)
    para que la sesión de Stripe y la tasa fijada venzan lo más cerca
    posible entre sí: pasado ese momento no tiene sentido seguir
    aceptando el pago a esa tasa, aunque ``Pago.registrar_pago`` nunca
    pierde un pago que de todas formas llegue tarde.

    Returns:
        int: Epoch en segundos a pasarle a ``expires_at``.
    """
    ahora = timezone.now()
    minimo = ahora + timedelta(minutes=30)
    maximo = ahora + timedelta(hours=24)
    objetivo = transaccion.tasa_vence_en or maximo
    objetivo = max(minimo, min(objetivo, maximo))
    return int(objetivo.timestamp())


def _resolver_metodo_pago_tarjeta(cliente, metodo_pago_id):
    """Busca el ``MetodoPago`` de tarjeta elegido, con su referencia de Stripe.

    Args:
        cliente (apps.clientes.models.Cliente): El cliente que va a pagar.
        metodo_pago_id: El ``pk`` recibido en ``?metodo_pago=``, tal como lo
            elige el cliente en el formulario de pago de siempre (ver
            ``apps.divisas.views.PagarTransaccionOperacionView.post``).

    Returns:
        apps.clientes.models.MetodoPago | None: El método, si existe, es
        del cliente, es de tipo tarjeta y está vinculado a Stripe con una
        referencia; ``None`` en cualquier otro caso (no se puede cobrar con
        algo que no sabemos identificar en Stripe).
    """
    return MetodoPago.objects.filter(
        pk=metodo_pago_id,
        cliente=cliente,
        tipo_medio=MetodoPago.TIPO_TARJETA,
        proveedor_externo=MetodoPago.PROVEEDOR_STRIPE,
    ).exclude(referencia_externa__isnull=True).exclude(referencia_externa='').first()


class _IniciarPagoStripeBaseView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Base común para iniciar el pago con tarjeta de una transacción propia.

    Las subclases (``IniciarPagoStripeOperacionView`` e
    ``IniciarPagoStripeCambioView``) solo fijan ``model`` (la clase de la
    transacción), ``tipo_transaccion`` (el valor que viaja en los metadatos
    de la sesión de Stripe para que el webhook sepa a cuál transacción
    corresponde) y ``url_detalle`` (adónde volver en cualquier desenlace).
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
        """Cobra directo con la tarjeta elegida, o cae a Stripe si hace falta confirmarla ahí.

        Returns:
            HttpResponse: Redirección al detalle de la transacción (si el
            cobro directo salió bien, o si no se puede pagar todavía, o si
            no se eligió una tarjeta guardada válida, o si Stripe no
            respondió — criterio 6), o a la página de pago de Stripe (para
            confirmar ahí un cobro directo que no se pudo completar solo).
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

        metodo_pago = _resolver_metodo_pago_tarjeta(transaccion.cliente, request.GET.get('metodo_pago'))
        if metodo_pago is None:
            messages.error(request, 'Elegí una tarjeta guardada para pagar con Stripe.')
            return redirect(self.url_detalle, pk=transaccion.pk)

        moneda = _moneda_de_liquidacion(transaccion)
        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            customer_id = _obtener_o_crear_cliente_stripe(transaccion.cliente)
        except stripe.error.StripeError:
            # Criterio 6: Stripe no respondió o la conexión falló. No se
            # toca la transacción, que sigue "Confirmada" tal como estaba.
            messages.error(
                request,
                'No se pudo conectar con Stripe para iniciar el pago. Intentá nuevamente en unos minutos.',
            )
            return redirect(self.url_detalle, pk=transaccion.pk)

        resultado = self._cobrar_con_tarjeta_guardada(
            request, transaccion, customer_id, metodo_pago, moneda,
        )
        if resultado is not None:
            return resultado
        # El cobro directo no se pudo completar solo (rechazo o
        # autenticación adicional exigida por el banco): se cae al flujo
        # de Checkout de abajo para que el cliente lo confirme ahí, con la
        # misma tarjeta ya preseleccionada.

        try:
            sesion = stripe.checkout.Session.create(
                mode='payment',
                customer=customer_id,
                payment_method_configuration=_configuracion_solo_tarjeta(),
                line_items=[{
                    'price_data': {
                        'currency': moneda.lower(),
                        'unit_amount': _monto_en_unidad_minima_stripe(monto_a_pagar(transaccion), moneda),
                        'product_data': {'name': f'Transacción {transaccion.pk}'},
                    },
                    'quantity': 1,
                }],
                metadata={
                    'tipo_transaccion': self.tipo_transaccion,
                    'transaccion_id': str(transaccion.pk),
                    # La misma tarjeta queda preseleccionada en Checkout
                    # (``customer=...``), así que esto es, en la enorme
                    # mayoría de los casos, la que termina usándose; sirve
                    # para que el Pago resultante quede asociado a esa
                    # tarjeta (ver _procesar_sesion_completada), igual que
                    # ya pasa con el cobro directo.
                    'metodo_pago_id': str(metodo_pago.pk),
                },
                success_url=_url_absoluta(request, self.url_detalle, pk=transaccion.pk) + '?pago=iniciado',
                cancel_url=_url_absoluta(request, self.url_detalle, pk=transaccion.pk) + '?pago=cancelado',
                expires_at=_expires_at_checkout(transaccion),
            )
        except stripe.error.StripeError:
            # Criterio 6: Stripe no respondió o la conexión falló. No se
            # toca la transacción, que sigue "Confirmada" tal como estaba.
            messages.error(
                request,
                'No se pudo conectar con Stripe para iniciar el pago. Intentá nuevamente en unos minutos.',
            )
            return redirect(self.url_detalle, pk=transaccion.pk)

        return redirect(sesion.url)

    def _cobrar_con_tarjeta_guardada(self, request, transaccion, customer_id, metodo_pago, moneda):
        """Intenta cobrar directo, sin que el cliente vea ninguna página de Stripe.

        Usa una ``idempotency_key`` fija por transacción: si esta vista se
        llama dos veces para la misma transacción (doble clic, el usuario
        vuelve atrás y refresca), Stripe devuelve el mismo ``PaymentIntent``
        ya creado en vez de cobrar la tarjeta una segunda vez.

        Args:
            metodo_pago (apps.clientes.models.MetodoPago): La tarjeta
                guardada elegida. Se guarda en el ``Pago`` resultante
                (ver ``apps.clientes.views.MetodoPagoMovimientosView``),
                no solo su ``referencia_externa``.

        Returns:
            HttpResponse | None: La redirección final si el cobro directo
            se resolvió (con éxito o con un rechazo definitivo), o ``None``
            si hay que caer al flujo de Checkout para que el cliente lo
            confirme ahí.
        """
        try:
            intent = stripe.PaymentIntent.create(
                amount=_monto_en_unidad_minima_stripe(monto_a_pagar(transaccion), moneda),
                currency=moneda.lower(),
                customer=customer_id,
                payment_method=metodo_pago.referencia_externa,
                off_session=True,
                confirm=True,
                metadata={
                    'tipo_transaccion': self.tipo_transaccion,
                    'transaccion_id': str(transaccion.pk),
                },
                idempotency_key=f'ge22-pago-directo-{transaccion.pk}',
            )
        except stripe.error.CardError as error:
            # Criterio 4: la tarjeta guardada fue rechazada (o el banco
            # exige una autenticación adicional que no se puede resolver
            # sin que el cliente esté presente). No se toca la
            # transacción; se cae a Checkout para que confirme ahí.
            messages.warning(
                request,
                'No se pudo cobrar automáticamente con tu tarjeta guardada '
                f'({error.user_message or "fue rechazada"}). Confirmá el pago para reintentar.',
            )
            return None
        except stripe.error.StripeError:
            messages.error(
                request,
                'No se pudo conectar con Stripe para iniciar el pago. Intentá nuevamente en unos minutos.',
            )
            return redirect(self.url_detalle, pk=transaccion.pk)

        if intent.status != 'succeeded':
            # Por ejemplo, "requires_action" (3-D Secure/SCA): no se puede
            # resolver sin el cliente presente. Se cae a Checkout.
            return None

        try:
            pago, creado = Pago.registrar_pago(
                transaccion,
                medio_pago=MetodoPago.TIPO_TARJETA,
                proveedor=PROVEEDOR_STRIPE,
                identificador_externo=intent.id,
                monto=monto_a_pagar(transaccion),
                metodo_pago=metodo_pago,
            )
        except PagoRechazadoError as error:
            messages.error(request, str(error))
            return redirect(self.url_detalle, pk=transaccion.pk)

        if creado and transaccion.estado == transaccion.ESTADO_PAGADA:
            # Entrega la divisa comprada recién ahora, la primera vez que
            # se registra este pago (nunca en una repetición idempotente:
            # ya se entregó la primera vez), y nunca si el pago llegó
            # fuera de plazo (ver Pago.registrar_pago).
            realizar_entrega(transaccion)

        if transaccion.estado == transaccion.ESTADO_PAGO_EXPIRADO:
            messages.warning(
                request,
                'El pago se registró, pero llegó después de que venció la tasa fijada: '
                'un administrador revisará esta transacción.',
            )
        else:
            messages.success(request, 'El pago con tu tarjeta guardada se realizó correctamente.')
        return redirect(self.url_detalle, pk=transaccion.pk)


class IniciarPagoStripeOperacionView(_IniciarPagoStripeBaseView):
    """Inicia el pago con tarjeta de una compra o venta propia ya "Confirmada".

    No tiene ningún botón propio en la UI: a ella redirige automáticamente
    ``apps.divisas.views.PagarTransaccionOperacionView.post`` cuando el
    método de pago elegido en el formulario de pago normal es de tipo
    "tarjeta" (``MetodoPago.TIPO_TARJETA``), en vez de registrar el pago de
    forma manual.
    """

    model = CalculoOperacion
    tipo_transaccion = 'operacion'
    url_detalle = 'divisas:detalle_transaccion_operacion'


class IniciarPagoStripeCambioView(_IniciarPagoStripeBaseView):
    """Inicia el pago con tarjeta de un cambio entre divisas propio ya "Confirmado".

    Ver ``IniciarPagoStripeOperacionView``: mismo criterio, al que redirige
    ``apps.divisas.views.PagarTransaccionCambioView.post``.
    """

    model = CalculoTriangulacion
    tipo_transaccion = 'cambio'
    url_detalle = 'divisas:detalle_transaccion_cambio'


class IniciarAgregarTarjetaStripeView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Pide el nombre del titular y redirige a Stripe a capturar una tarjeta nueva.

    El número de tarjeta nunca llega a esta vista ni a ningún campo de
    Global Exchange: lo captura Stripe en su propia página, mediante una
    sesión de Checkout en modo ``"setup"`` (guarda una tarjeta sin cobrar
    nada). ``confirmar_tarjeta_stripe_view`` es quien, al volver de Stripe,
    recién ahí crea el ``MetodoPago`` con la referencia que devuelve Stripe.
    """

    def test_func(self):
        """Permite agregar una tarjeta solo a los roles que pueden operar."""
        roles = self.request.session.get('keycloak_roles', [])
        return (
            'cliente' in roles
            and not self.request.user.is_staff
            and self.request.user.clientes.filter(is_active=True).exists()
        )

    def get(self, request, *args, **kwargs):
        """Muestra el formulario mínimo (nombre del titular) previo a Stripe."""
        cliente_activo = getattr(request, 'cliente_activo', None)
        if cliente_activo is None:
            messages.error(request, 'No tenés un cliente activo seleccionado.')
            return redirect('clientes:metodo_pago_list')
        form = AgregarTarjetaStripeForm(initial={'nombre_titular': cliente_activo.nombre_completo})
        return render(request, 'clientes/agregar_tarjeta_stripe.html', {'form': form})

    def post(self, request, *args, **kwargs):
        """Crea la sesión de Stripe (modo "setup") y redirige a completarla ahí.

        Returns:
            HttpResponse: Redirección a Stripe si todo sale bien; de vuelta
            al formulario si hay errores de validación, o al listado de
            métodos de pago si Stripe no respondió (criterio 6, aplicado
            acá al alta de la tarjeta en vez de a un pago).
        """
        cliente_activo = getattr(request, 'cliente_activo', None)
        if cliente_activo is None:
            messages.error(request, 'No tenés un cliente activo seleccionado.')
            return redirect('clientes:metodo_pago_list')

        form = AgregarTarjetaStripeForm(request.POST)
        if not form.is_valid():
            return render(request, 'clientes/agregar_tarjeta_stripe.html', {'form': form})

        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            customer_id = _obtener_o_crear_cliente_stripe(cliente_activo)
            sesion = stripe.checkout.Session.create(
                mode='setup',
                customer=customer_id,
                payment_method_configuration=_configuracion_solo_tarjeta(),
                # Stripe exige una moneda incluso en modo "setup" (no cobra
                # nada; solo la usa para decidir qué métodos ofrecer), así
                # que se manda la de liquidación por defecto del sistema.
                currency='pyg',
                setup_intent_data={
                    'metadata': {
                        'cliente_id': str(cliente_activo.pk),
                        'nombre_titular': form.cleaned_data['nombre_titular'],
                    },
                },
                success_url=(
                    _url_absoluta(request, 'clientes:confirmar_tarjeta_stripe') + '?session_id={CHECKOUT_SESSION_ID}'
                ),
                cancel_url=_url_absoluta(request, 'clientes:metodo_pago_list'),
            )
        except stripe.error.StripeError:
            messages.error(
                request,
                'No se pudo conectar con Stripe para agregar la tarjeta. Intentá nuevamente en unos minutos.',
            )
            return redirect('clientes:metodo_pago_list')

        return redirect(sesion.url)


def confirmar_tarjeta_stripe_view(request):
    """Confirma la tarjeta capturada por Stripe y la guarda como ``MetodoPago``.

    Es el ``success_url`` de ``IniciarAgregarTarjetaStripeView``: Stripe
    vuelve acá con ``?session_id=...`` después de que el cliente completó
    el formulario de tarjeta en su propia página.

    Returns:
        HttpResponse: Redirección al listado de métodos de pago, con un
        mensaje de éxito o de error según corresponda.

    Raises:
        Http404: Si la sesión de Stripe no corresponde al ``Customer`` del
        cliente activo (no hay nada legítimo que hacer con una sesión
        ajena).
    """
    cliente_activo = getattr(request, 'cliente_activo', None)
    if cliente_activo is None:
        messages.error(request, 'No tenés un cliente activo seleccionado.')
        return redirect('clientes:metodo_pago_list')

    session_id = request.GET.get('session_id')
    if not session_id:
        messages.error(request, 'No se recibió la confirmación de Stripe.')
        return redirect('clientes:metodo_pago_list')

    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        sesion = stripe.checkout.Session.retrieve(session_id, expand=['setup_intent'])
        customer_id = _obtener_o_crear_cliente_stripe(cliente_activo)
    except stripe.error.StripeError:
        messages.error(request, 'No se pudo confirmar la tarjeta con Stripe. Intentá nuevamente.')
        return redirect('clientes:metodo_pago_list')

    if sesion.customer != customer_id:
        raise Http404('Sesión de Stripe inválida.')

    setup_intent = sesion.setup_intent
    if setup_intent is None or setup_intent.status != 'succeeded' or not setup_intent.payment_method:
        messages.error(request, 'No se pudo confirmar la tarjeta con Stripe.')
        return redirect('clientes:metodo_pago_list')

    pm_id = setup_intent.payment_method
    if MetodoPago.objects.filter(proveedor_externo=MetodoPago.PROVEEDOR_STRIPE, referencia_externa=pm_id).exists():
        # Confirmación repetida de la misma tarjeta (p. ej. el cliente
        # refrescó esta página): no se duplica el MetodoPago.
        messages.info(request, 'Esa tarjeta ya estaba guardada.')
        return redirect('clientes:metodo_pago_list')

    try:
        metodo_stripe = stripe.PaymentMethod.retrieve(pm_id)
    except stripe.error.StripeError:
        messages.error(request, 'No se pudo recuperar los datos de la tarjeta desde Stripe.')
        return redirect('clientes:metodo_pago_list')

    card = getattr(metodo_stripe, 'card', None)
    if card is None:
        # Defensa adicional a _configuracion_solo_tarjeta: si por lo que
        # sea Stripe guardó un medio que no es una tarjeta (p. ej. Link),
        # no hay datos de tarjeta que guardar. No se crea ningún MetodoPago.
        messages.error(
            request,
            'Lo que guardaste en Stripe no fue una tarjeta '
            f'({getattr(metodo_stripe, "type", "desconocido")}). Reintentá y elegí pagar con tarjeta.',
        )
        return redirect('clientes:metodo_pago_list')

    metadata = _a_dict(setup_intent.metadata)
    MetodoPago.objects.create(
        cliente=cliente_activo,
        tipo_medio=MetodoPago.TIPO_TARJETA,
        nombre_titular=metadata.get('nombre_titular') or cliente_activo.nombre_completo,
        entidad_financiera=card.brand.title(),
        numero_tarjeta=card.last4,
        proveedor_externo=MetodoPago.PROVEEDOR_STRIPE,
        referencia_externa=pm_id,
        # Una tarjeta siempre cobra en PYG (ver moneda_a_pagar): nunca hace
        # falta pedirle esto al cliente, a diferencia de una transferencia
        # o billetera, donde lo confirma sipap-sim.
        moneda=Divisa.objects.get(codigo=Divisa.CODIGO_BASE),
    )
    messages.success(request, 'Tarjeta agregada correctamente.')
    return redirect('clientes:metodo_pago_list')


def _procesar_sesion_completada(session):
    """Registra el pago si Stripe confirma que la sesión de Checkout fue cobrada.

    ``payment_status`` puede quedar en "unpaid" para medios de pago
    asincrónicos todavía no acreditados: ahí no corresponde registrar nada
    todavía (y, por lo tanto, no se modifica la transacción).

    Args:
        session: El objeto ``checkout.session`` que manda Stripe en el
            evento ``checkout.session.completed`` (un ``StripeObject`` real
            en producción; un dict plano en los tests). Se convierte con
            ``_a_dict`` apenas entra, porque ``StripeObject`` no tiene
            ``.get()``.
    """
    session = _a_dict(session)
    if session.get('payment_status') != 'paid':
        return

    metadata = _a_dict(session.get('metadata'))
    tipo_transaccion = metadata.get('tipo_transaccion')
    transaccion_id = metadata.get('transaccion_id')
    if not tipo_transaccion or not transaccion_id:
        return

    model = CalculoOperacion if tipo_transaccion == 'operacion' else CalculoTriangulacion
    try:
        transaccion = model.objects.get(pk=transaccion_id)
    except model.DoesNotExist:
        return

    metodo_pago = MetodoPago.objects.filter(
        pk=metadata.get('metodo_pago_id'), cliente=transaccion.cliente,
    ).first()

    identificador_externo = session.get('payment_intent') or session.get('id')
    try:
        pago, creado = Pago.registrar_pago(
            transaccion,
            medio_pago=MetodoPago.TIPO_TARJETA,
            proveedor=PROVEEDOR_STRIPE,
            identificador_externo=identificador_externo,
            monto=monto_a_pagar(transaccion),
            metodo_pago=metodo_pago,
        )
    except PagoRechazadoError:
        # La transacción ya no está en condiciones de pagarse con este
        # pago (por ejemplo, un reintento de Stripe del mismo evento que
        # llega después de que otro camino ya la marcó "Pagada"). No hay
        # nada más que hacer: registrar_pago ya es idempotente por
        # (proveedor, identificador_externo) para el caso normal de un
        # webhook reenviado.
        return

    if creado and transaccion.estado == transaccion.ESTADO_PAGADA:
        # Igual que en _cobrar_con_tarjeta_guardada: solo se entrega la
        # primera vez que se registra este pago, nunca en una repetición,
        # y nunca si llegó fuera de plazo (ver Pago.registrar_pago).
        realizar_entrega(transaccion)


@csrf_exempt
def stripe_webhook_view(request):
    """Recibe los webhooks de Stripe y confirma, de ser el caso, un pago con tarjeta.

    Es el único lugar donde una notificación de Stripe se traduce en un
    pago real. Queda exento de CSRF porque lo llama Stripe, no un
    navegador con sesión de Django, y en cambio su seguridad depende por
    completo de la verificación de firma de ``stripe.Webhook.construct_event``
    (criterio 3).

    Returns:
        HttpResponse: 200 si el evento se procesó (incluso si no requería
        ninguna acción), 400 si la firma no es válida o el método no es
        POST.
    """
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    payload = request.body
    firma = request.META.get('HTTP_STRIPE_SIGNATURE', '')
    try:
        evento = stripe.Webhook.construct_event(payload, firma, settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        # Criterio 3: firma inválida. Se rechaza sin tocar ninguna
        # transacción y sin procesar el contenido del payload.
        return HttpResponseBadRequest('Firma inválida.')

    if evento['type'] == 'checkout.session.completed':
        _procesar_sesion_completada(evento['data']['object'])

    return HttpResponse(status=200)
