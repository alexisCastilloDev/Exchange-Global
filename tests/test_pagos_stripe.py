"""Pruebas de la HU 'Pago con tarjeta vía Stripe'."""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import stripe
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from stripe._stripe_object import StripeObject

from apps.clientes.models import Cliente, MetodoPago
from apps.divisas.models import CalculoOperacion, CalculoTriangulacion, Cotizacion, Divisa, Pago
from apps.divisas import pagos_stripe
from apps.divisas.pagos_stripe import (
    _a_dict,
    _configuracion_solo_tarjeta,
    _monto_en_unidad_minima_stripe,
    _moneda_de_liquidacion,
    _obtener_o_crear_cliente_stripe,
    _resolver_metodo_pago_tarjeta,
)


def _stripe_object(datos):
    """Construye un ``StripeObject`` real a partir de un dict, recursivamente.

    Reproduce lo que realmente devuelve el SDK de Stripe (``stripe.Webhook
    .construct_event``, ``checkout.Session.retrieve``, etc.): a diferencia
    de un dict plano o un ``SimpleNamespace``, no tiene ``.get()`` ni es
    iterable, así que sirve para detectar bugs que un mock más simple no
    hubiera encontrado (ver ``_a_dict``).
    """
    return StripeObject.construct_from(datos, 'sk_test_fake')

User = get_user_model()


def _crear_cliente_logueado(client, username, identificador):
    """Crea un usuario con un cliente asociado y lo loguea con rol 'cliente'."""
    usuario = User.objects.create_user(username=username, password='password123')
    cliente = Cliente.objects.create(
        user=usuario,
        identificador=identificador,
        nombre='Cliente',
        apellido='Stripe',
        email=f'{username}@test.com',
        is_active=True,
    )
    usuario.clientes.add(cliente)
    client.login(username=username, password='password123')
    session = client.session
    session['keycloak_roles'] = ['cliente']
    session.save()
    return usuario, cliente


def _crear_divisa_cotizada(codigo, nombre, tasa_compra, tasa_venta):
    """Crea una divisa activa con una cotización vigente."""
    divisa = Divisa.objects.create(codigo=codigo, nombre=nombre, simbolo=codigo, activa=True)
    Cotizacion.objects.create(divisa=divisa, tasa_compra=tasa_compra, tasa_venta=tasa_venta)
    return divisa


def _crear_tarjeta_stripe(cliente, referencia_externa='pm_guardado_123'):
    """Crea un MetodoPago de tarjeta ya vinculado a Stripe para ese cliente."""
    return MetodoPago.objects.create(
        cliente=cliente,
        tipo_medio=MetodoPago.TIPO_TARJETA,
        nombre_titular=str(cliente),
        entidad_financiera='Visa',
        numero_tarjeta='4242',
        proveedor_externo=MetodoPago.PROVEEDOR_STRIPE,
        referencia_externa=referencia_externa,
    )


class MontoYMonedaTest(TestCase):
    """Pruebas unitarias de las conversiones de monto y moneda hacia Stripe."""

    def test_pyg_no_usa_centavos(self):
        """PYG es 'sin decimales' en Stripe: el monto se manda tal cual."""
        self.assertEqual(_monto_en_unidad_minima_stripe(Decimal('747400.00'), 'PYG'), 747400)

    def test_otra_moneda_se_multiplica_por_cien(self):
        """Una moneda común (EUR) se manda en centavos."""
        self.assertEqual(_monto_en_unidad_minima_stripe(Decimal('89.22'), 'EUR'), 8922)

    def test_moneda_de_liquidacion_de_una_operacion_es_siempre_pyg(self):
        """Una compra/venta siempre liquida en PYG, sin importar la divisa operada."""
        operacion = CalculoOperacion(codigo_divisa='USD')
        self.assertEqual(_moneda_de_liquidacion(operacion), 'PYG')

    def test_moneda_de_liquidacion_de_un_cambio_es_la_divisa_de_origen(self):
        """Un cambio se cobra en su divisa de ORIGEN (lo que el cliente entrega), no en la de destino."""
        cambio = CalculoTriangulacion(codigo_divisa_origen='USD', codigo_divisa_destino='EUR')
        self.assertEqual(_moneda_de_liquidacion(cambio), 'USD')


class ADictTest(TestCase):
    """Pruebas unitarias de la conversión de un StripeObject real a dict plano.

    ``StripeObject`` (lo que de verdad devuelve el SDK, a diferencia de un
    dict o un ``SimpleNamespace`` en un mock) no tiene ``.get()``: llamarlo
    tira ``AttributeError``. Esto rompió en producción ``_procesar_sesion_completada``
    y ``confirmar_tarjeta_stripe_view`` porque los tests mockeaban con dicts
    planos, que sí tienen ``.get()`` y no detectaron el problema.
    """

    def test_convierte_un_stripe_object_real_a_dict_plano(self):
        """Un StripeObject real (con anidados) se aplana por completo."""
        objeto = _stripe_object({'a': 1, 'metadata': {'x': 'y'}})

        resultado = _a_dict(objeto)

        self.assertEqual(resultado, {'a': 1, 'metadata': {'x': 'y'}})
        self.assertEqual(resultado.get('a'), 1)

    def test_un_dict_plano_se_devuelve_sin_tocar(self):
        """Un dict ya plano (como los que arman los tests) no necesita conversión."""
        self.assertEqual(_a_dict({'a': 1}), {'a': 1})

    def test_none_se_convierte_en_dict_vacio(self):
        """Sin metadata (``None``), no hay nada que convertir."""
        self.assertEqual(_a_dict(None), {})


class ClienteStripeTest(TestCase):
    """Pruebas unitarias de la obtención del Customer de Stripe de un cliente."""

    def setUp(self):
        """Prepara un cliente sin ningún Customer de Stripe todavía."""
        self.cliente = Cliente.objects.create(
            identificador='STRIPE-CUST-001', nombre='Ana', apellido='Cliente',
            email='ana@test.com', is_active=True,
        )

    @patch('apps.divisas.pagos_stripe.stripe.Customer.create')
    def test_crea_un_customer_nuevo_si_el_cliente_no_tiene_uno(self, mock_create):
        """La primera vez, crea el Customer en Stripe y lo guarda en el cliente."""
        mock_create.return_value = SimpleNamespace(id='cus_nuevo_123')

        customer_id = _obtener_o_crear_cliente_stripe(self.cliente)

        self.assertEqual(customer_id, 'cus_nuevo_123')
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.stripe_customer_id, 'cus_nuevo_123')
        mock_create.assert_called_once()

    @patch('apps.divisas.pagos_stripe.stripe.Customer.create')
    def test_reutiliza_el_customer_si_el_cliente_ya_tiene_uno(self, mock_create):
        """Si el cliente ya tiene un Customer guardado, no crea uno nuevo."""
        self.cliente.stripe_customer_id = 'cus_existente_456'
        self.cliente.save(update_fields=['stripe_customer_id'])

        customer_id = _obtener_o_crear_cliente_stripe(self.cliente)

        self.assertEqual(customer_id, 'cus_existente_456')
        mock_create.assert_not_called()


class ConfiguracionSoloTarjetaTest(TestCase):
    """Pruebas unitarias de la configuración de Stripe que apaga Link y deja solo tarjeta.

    Sin esto, Checkout ofrece cualquier medio habilitado en la cuenta
    (típicamente también Link); si el cliente lo elige al agregar una
    tarjeta, el ``PaymentMethod`` resultante es de tipo ``"link"``, sin los
    datos de tarjeta que esta HU necesita (ver el bug real que esto
    reprodujo: ``AttributeError: card`` al acceder a ``metodo_stripe.card``).
    """

    def setUp(self):
        """Limpia el caché en memoria antes de cada test, para no heredar el de otro test."""
        pagos_stripe._configuracion_solo_tarjeta_cache['id'] = None
        self.addCleanup(lambda: pagos_stripe._configuracion_solo_tarjeta_cache.update(id=None))

    @patch('apps.divisas.pagos_stripe.stripe.PaymentMethodConfiguration.create')
    @patch('apps.divisas.pagos_stripe.stripe.PaymentMethodConfiguration.list')
    def test_reutiliza_la_configuracion_si_ya_existe(self, mock_list, mock_create):
        """Si ya existe una configuración con ese nombre, la reutiliza en vez de crear otra."""
        mock_list.return_value = SimpleNamespace(
            data=[SimpleNamespace(id='pmc_existente', name='Global Exchange - solo tarjeta')],
        )

        resultado = _configuracion_solo_tarjeta()

        self.assertEqual(resultado, 'pmc_existente')
        mock_create.assert_not_called()

    @patch('apps.divisas.pagos_stripe.stripe.PaymentMethodConfiguration.create')
    @patch('apps.divisas.pagos_stripe.stripe.PaymentMethodConfiguration.list')
    def test_crea_la_configuracion_con_tarjeta_prendida_y_link_apagado_si_no_existe(self, mock_list, mock_create):
        """Sin una configuración previa, crea una nueva con tarjeta prendida y Link apagado."""
        mock_list.return_value = SimpleNamespace(data=[])
        mock_create.return_value = SimpleNamespace(id='pmc_nueva')

        resultado = _configuracion_solo_tarjeta()

        self.assertEqual(resultado, 'pmc_nueva')
        kwargs = mock_create.call_args.kwargs
        self.assertEqual(kwargs['card']['display_preference']['preference'], 'on')
        self.assertEqual(kwargs['link']['display_preference']['preference'], 'off')

    @patch('apps.divisas.pagos_stripe.stripe.PaymentMethodConfiguration.create')
    @patch('apps.divisas.pagos_stripe.stripe.PaymentMethodConfiguration.list')
    def test_segunda_llamada_usa_el_cache_sin_volver_a_llamar_a_stripe(self, mock_list, mock_create):
        """Una vez resuelta, no vuelve a consultar la API en la misma vida del proceso."""
        mock_list.return_value = SimpleNamespace(data=[])
        mock_create.return_value = SimpleNamespace(id='pmc_nueva')

        _configuracion_solo_tarjeta()
        _configuracion_solo_tarjeta()

        mock_list.assert_called_once()
        mock_create.assert_called_once()


class ResolverMetodoPagoTarjetaTest(TestCase):
    """Pruebas unitarias de la resolución del MetodoPago de tarjeta elegido para pagar."""

    def setUp(self):
        """Prepara dos clientes, uno con una tarjeta vinculada a Stripe."""
        self.cliente = Cliente.objects.create(
            identificador='RESOLVER-001', nombre='Bruno', apellido='Cliente',
            email='bruno@test.com', is_active=True,
        )
        self.otro_cliente = Cliente.objects.create(
            identificador='RESOLVER-002', nombre='Carla', apellido='Cliente',
            email='carla@test.com', is_active=True,
        )
        self.tarjeta = _crear_tarjeta_stripe(self.cliente)

    def test_resuelve_la_tarjeta_propia_vinculada_a_stripe(self):
        """Encuentra la tarjeta cuando es del cliente y tiene referencia de Stripe."""
        resultado = _resolver_metodo_pago_tarjeta(self.cliente, self.tarjeta.pk)

        self.assertEqual(resultado, self.tarjeta)

    def test_no_resuelve_nada_sin_id(self):
        """Sin ningún id (p. ej. falta el query param), no hay nada que resolver."""
        self.assertIsNone(_resolver_metodo_pago_tarjeta(self.cliente, None))

    def test_no_resuelve_una_tarjeta_de_otro_cliente(self):
        """La tarjeta de otro cliente no se puede usar para pagar, aunque se adivine el pk."""
        self.assertIsNone(_resolver_metodo_pago_tarjeta(self.otro_cliente, self.tarjeta.pk))

    def test_no_resuelve_un_metodo_sin_referencia_externa(self):
        """Un método de tipo tarjeta sin vínculo real a Stripe no se puede cobrar directo."""
        sin_vinculo = MetodoPago.objects.create(
            cliente=self.cliente, tipo_medio=MetodoPago.TIPO_TARJETA,
            nombre_titular='Bruno', entidad_financiera='Visa', numero_tarjeta='1234',
        )

        self.assertIsNone(_resolver_metodo_pago_tarjeta(self.cliente, sin_vinculo.pk))

    def test_no_resuelve_un_metodo_que_no_es_tarjeta(self):
        """Una transferencia o billetera no sirve para iniciar un cobro con Stripe."""
        transferencia = MetodoPago.objects.create(
            cliente=self.cliente, tipo_medio=MetodoPago.TIPO_TRANSFERENCIA,
            nombre_titular='Bruno', entidad_financiera='Banco', numero_cuenta='123', tipo_cuenta='AHORRO',
        )

        self.assertIsNone(_resolver_metodo_pago_tarjeta(self.cliente, transferencia.pk))


class IniciarPagoStripeOperacionTest(TestCase):
    """Verifica el cobro con tarjeta de una compra o venta."""

    def setUp(self):
        """Prepara un cliente logueado, una tarjeta vinculada a Stripe y una compra 'Confirmada' en PYG."""
        self.usuario, self.cliente = _crear_cliente_logueado(self.client, 'cliente-stripe-op', 'STRIPE-OP-001')
        self.usd = _crear_divisa_cotizada('USD', 'Dólar', Decimal('7300.00'), Decimal('7400.00'))
        self.tarjeta = _crear_tarjeta_stripe(self.cliente)
        self.transaccion = CalculoOperacion.objects.create(
            usuario=self.usuario,
            cliente=self.cliente,
            tipo=CalculoOperacion.TIPO_COMPRA,
            divisa=self.usd,
            codigo_divisa='USD',
            monto_origen=Decimal('100.00'),
            tasa_aplicada=Decimal('7400.00'),
            comision_porcentaje=Decimal('1.000'),
            comision=Decimal('7400.00'),
            monto_final=Decimal('747400.00'),
            estado=CalculoOperacion.ESTADO_CONFIRMADA,
            vence_en=timezone.now() + timedelta(seconds=300),
            confirmado_en=timezone.now(),
        )
        self.url_base = reverse('divisas:pagar_transaccion_stripe', kwargs={'pk': self.transaccion.pk})
        self.url = f'{self.url_base}?metodo_pago={self.tarjeta.pk}'
        self.detalle_url = reverse('divisas:detalle_transaccion_operacion', kwargs={'pk': self.transaccion.pk})

        parche_customer = patch(
            'apps.divisas.pagos_stripe._obtener_o_crear_cliente_stripe', return_value='cus_test_123',
        )
        self.mock_customer = parche_customer.start()
        self.addCleanup(parche_customer.stop)

        parche_config = patch(
            'apps.divisas.pagos_stripe._configuracion_solo_tarjeta', return_value='pmc_test_fake',
        )
        parche_config.start()
        self.addCleanup(parche_config.stop)

        # La entrega (transferir la divisa comprada al cliente) es un paso
        # posterior a este cobro, con su propia integración HTTP a
        # sipap-sim; estos tests cubren solo el cobro con tarjeta en sí,
        # así que se mockea para que "siempre funcione" sin red real.
        parche_entrega = patch('apps.divisas.pagos_stripe.realizar_entrega', return_value=True)
        parche_entrega.start()
        self.addCleanup(parche_entrega.stop)

    @patch('apps.divisas.pagos_stripe.stripe.checkout.Session.create')
    @patch('apps.divisas.pagos_stripe.stripe.PaymentIntent.create')
    def test_cobra_directo_con_la_tarjeta_elegida_y_marca_pagada(self, mock_payment_intent, mock_checkout):
        """Criterios 1 y 2: cobra por API el monto exacto, sin mostrar ninguna página de Stripe."""
        mock_payment_intent.return_value = SimpleNamespace(id='pi_directo_123', status='succeeded')

        response = self.client.get(self.url, follow=True)

        self.assertContains(response, 'El pago con tu tarjeta guardada se realizó correctamente')
        mock_checkout.assert_not_called()
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_PAGADA)
        pago = Pago.objects.get(calculo_operacion=self.transaccion)
        self.assertEqual(pago.medio_pago, MetodoPago.TIPO_TARJETA)
        self.assertEqual(pago.proveedor, 'STRIPE')
        self.assertEqual(pago.identificador_externo, 'pi_directo_123')
        self.assertEqual(pago.monto, self.transaccion.monto_final)
        kwargs = mock_payment_intent.call_args.kwargs
        self.assertEqual(kwargs['amount'], 747400)
        self.assertEqual(kwargs['currency'], 'pyg')
        self.assertEqual(kwargs['customer'], 'cus_test_123')
        self.assertEqual(kwargs['payment_method'], 'pm_guardado_123')
        self.assertTrue(kwargs['off_session'])
        self.assertTrue(kwargs['confirm'])
        self.assertEqual(kwargs['idempotency_key'], f'ge22-pago-directo-{self.transaccion.pk}')

    @patch('apps.divisas.pagos_stripe.stripe.PaymentIntent.create')
    def test_sin_metodo_de_pago_en_la_url_pide_elegir_uno(self, mock_payment_intent):
        """Sin ``?metodo_pago=``, no hay con qué cobrar: se pide elegir una tarjeta guardada."""
        response = self.client.get(self.url_base, follow=True)

        self.assertContains(response, 'Elegí una tarjeta guardada para pagar con Stripe')
        mock_payment_intent.assert_not_called()
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_CONFIRMADA)

    @patch('apps.divisas.pagos_stripe.stripe.PaymentIntent.create')
    def test_metodo_de_otro_cliente_no_se_puede_usar(self, mock_payment_intent):
        """El pk de una tarjeta ajena en la URL no sirve para cobrar nada."""
        otro_usuario, otro_cliente = _crear_cliente_logueado(
            self.client, 'otro-cliente-stripe-op', 'STRIPE-OP-002',
        )
        tarjeta_ajena = _crear_tarjeta_stripe(otro_cliente, referencia_externa='pm_ajeno')
        self.client.logout()
        self.client.login(username='cliente-stripe-op', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response = self.client.get(f'{self.url_base}?metodo_pago={tarjeta_ajena.pk}', follow=True)

        self.assertContains(response, 'Elegí una tarjeta guardada para pagar con Stripe')
        mock_payment_intent.assert_not_called()

    @patch('apps.divisas.pagos_stripe.stripe.PaymentIntent.create')
    def test_no_permite_pagar_una_transaccion_que_no_esta_confirmada(self, mock_payment_intent):
        """Solo una transacción 'Confirmada' puede iniciar un pago con tarjeta."""
        self.transaccion.estado = CalculoOperacion.ESTADO_PENDIENTE
        self.transaccion.save(update_fields=['estado'])

        response = self.client.get(self.url, follow=True)

        self.assertContains(response, 'no está en condiciones de pagarse')
        mock_payment_intent.assert_not_called()

    @patch('apps.divisas.pagos_stripe.stripe.PaymentIntent.create')
    def test_no_permite_cobrar_si_la_tasa_fijada_ya_vencio(self, mock_payment_intent):
        """Con la tasa vencida, no se inicia ningún cobro nuevo (ni directo ni por Checkout)."""
        self.transaccion.tasa_vence_en = timezone.now() - timedelta(seconds=1)
        self.transaccion.save(update_fields=['tasa_vence_en'])

        response = self.client.get(self.url, follow=True)

        self.assertContains(response, 'ya venció')
        mock_payment_intent.assert_not_called()
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_CONFIRMADA)
        self.assertEqual(Pago.objects.count(), 0)

    @patch('apps.divisas.pagos_stripe.stripe.checkout.Session.create')
    @patch('apps.divisas.pagos_stripe.stripe.PaymentIntent.create')
    def test_la_sesion_de_checkout_vence_junto_con_la_tasa_fijada(self, mock_payment_intent, mock_checkout):
        """``expires_at`` de la sesión de Checkout queda alineado con ``tasa_vence_en``."""
        mock_payment_intent.side_effect = stripe.error.CardError('Rechazada.', param=None, code='card_declined')
        mock_checkout.return_value = SimpleNamespace(url='https://checkout.stripe.com/reintentar')
        self.transaccion.tasa_vence_en = timezone.now() + timedelta(hours=1)
        self.transaccion.save(update_fields=['tasa_vence_en'])

        self.client.get(self.url)

        checkout_kwargs = mock_checkout.call_args.kwargs
        self.assertEqual(
            checkout_kwargs['expires_at'], int(self.transaccion.tasa_vence_en.timestamp()),
        )

    def test_problema_de_comunicacion_al_resolver_el_customer_no_modifica_la_transaccion(self):
        """Criterio 6: si falla la consulta/creación del Customer de Stripe, no se toca la transacción."""
        self.mock_customer.side_effect = stripe.error.APIConnectionError('No se pudo conectar')

        response = self.client.get(self.url, follow=True)

        self.assertContains(response, 'No se pudo conectar con Stripe')
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_CONFIRMADA)
        self.assertEqual(Pago.objects.count(), 0)

    @patch('apps.divisas.pagos_stripe.stripe.checkout.Session.create')
    @patch('apps.divisas.pagos_stripe.stripe.PaymentIntent.create')
    def test_tarjeta_rechazada_cae_a_checkout_sin_tocar_la_transaccion(self, mock_payment_intent, mock_checkout):
        """Criterio 4: si el cobro directo es rechazado, se cae a Checkout para reintentar."""
        mock_payment_intent.side_effect = stripe.error.CardError(
            'Tu tarjeta fue rechazada.', param=None, code='card_declined',
        )
        mock_checkout.return_value = SimpleNamespace(url='https://checkout.stripe.com/reintentar')

        response = self.client.get(self.url)

        self.assertRedirects(response, 'https://checkout.stripe.com/reintentar', fetch_redirect_response=False)
        checkout_kwargs = mock_checkout.call_args.kwargs
        self.assertEqual(checkout_kwargs['customer'], 'cus_test_123')
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_CONFIRMADA)
        self.assertEqual(Pago.objects.count(), 0)

    @patch('apps.divisas.pagos_stripe.stripe.checkout.Session.create')
    @patch('apps.divisas.pagos_stripe.stripe.PaymentIntent.create')
    def test_requiere_autenticacion_cae_a_checkout(self, mock_payment_intent, mock_checkout):
        """Si el banco exige 3-D Secure/SCA, el cobro directo no alcanza y se cae a Checkout."""
        mock_payment_intent.return_value = SimpleNamespace(id='pi_necesita_auth', status='requires_action')
        mock_checkout.return_value = SimpleNamespace(url='https://checkout.stripe.com/confirmar')

        response = self.client.get(self.url)

        self.assertRedirects(response, 'https://checkout.stripe.com/confirmar', fetch_redirect_response=False)
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_CONFIRMADA)
        self.assertEqual(Pago.objects.count(), 0)

    @patch('apps.divisas.pagos_stripe.stripe.checkout.Session.create')
    @patch('apps.divisas.pagos_stripe.stripe.PaymentIntent.create')
    def test_checkout_de_reintento_no_pierde_la_conexion(self, mock_payment_intent, mock_checkout):
        """Criterio 6: si falla también la creación de la sesión de reintento, no se toca la transacción."""
        mock_payment_intent.side_effect = stripe.error.CardError('Rechazada.', param=None, code='card_declined')
        mock_checkout.side_effect = stripe.error.APIConnectionError('No se pudo conectar')

        response = self.client.get(self.url, follow=True)

        self.assertContains(response, 'No se pudo conectar con Stripe')
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_CONFIRMADA)

    def test_usuario_sin_rol_cliente_no_puede_iniciar_el_pago(self):
        """Solo el rol 'cliente' puede iniciar un pago con tarjeta."""
        session = self.client.session
        session['keycloak_roles'] = ['cajero']
        session.save()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_cancelar_el_pago_en_stripe_vuelve_al_detalle_con_aviso(self):
        """Criterio 5: abandonar/cancelar el pago en Stripe no toca la transacción."""
        response = self.client.get(self.detalle_url, {'pago': 'cancelado'})

        self.assertContains(response, 'Cancelaste el pago con tarjeta en Stripe')
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_CONFIRMADA)

    def test_pago_iniciado_muestra_aviso_de_confirmacion_pendiente(self):
        """Al volver con el pago iniciado, se avisa que la confirmación es asíncrona."""
        response = self.client.get(self.detalle_url, {'pago': 'iniciado'})

        self.assertContains(response, 'se está confirmando')


class IniciarPagoStripeCambioTest(TestCase):
    """Verifica el cobro con tarjeta de un cambio entre divisas."""

    def setUp(self):
        """Prepara un cliente logueado, una tarjeta vinculada a Stripe y un cambio 'Confirmado' en EUR."""
        self.usuario, self.cliente = _crear_cliente_logueado(self.client, 'cliente-stripe-cambio', 'STRIPE-CAMBIO-001')
        self.usd = _crear_divisa_cotizada('USD', 'Dólar', Decimal('7300.00'), Decimal('7400.00'))
        self.eur = _crear_divisa_cotizada('EUR', 'Euro', Decimal('7900.00'), Decimal('8100.00'))
        self.tarjeta = _crear_tarjeta_stripe(self.cliente, referencia_externa='pm_guardado_456')
        self.transaccion = CalculoTriangulacion.objects.create(
            usuario=self.usuario,
            cliente=self.cliente,
            divisa_origen=self.usd,
            divisa_destino=self.eur,
            codigo_divisa_origen='USD',
            codigo_divisa_destino='EUR',
            monto_origen=Decimal('100.00'),
            tasa_compra_aplicada=Decimal('7300.00'),
            tasa_venta_aplicada=Decimal('8100.00'),
            tasa_cruzada=Decimal('0.901235'),
            monto_equivalente_pyg=Decimal('730000.00'),
            comision_porcentaje=Decimal('1.000'),
            comision=Decimal('0.90'),
            monto_final=Decimal('89.22'),
            estado=CalculoTriangulacion.ESTADO_CONFIRMADA,
            vence_en=timezone.now() + timedelta(seconds=300),
            confirmado_en=timezone.now(),
        )
        url_base = reverse('divisas:pagar_transaccion_cambio_stripe', kwargs={'pk': self.transaccion.pk})
        self.url = f'{url_base}?metodo_pago={self.tarjeta.pk}'

        parche_customer = patch(
            'apps.divisas.pagos_stripe._obtener_o_crear_cliente_stripe', return_value='cus_test_456',
        )
        parche_customer.start()
        self.addCleanup(parche_customer.stop)

        parche_config = patch(
            'apps.divisas.pagos_stripe._configuracion_solo_tarjeta', return_value='pmc_test_fake',
        )
        parche_config.start()
        self.addCleanup(parche_config.stop)

        # Ver IniciarPagoStripeOperacionTest.setUp: la entrega queda fuera
        # del alcance de estos tests, que cubren solo el cobro con tarjeta.
        parche_entrega = patch('apps.divisas.pagos_stripe.realizar_entrega', return_value=True)
        parche_entrega.start()
        self.addCleanup(parche_entrega.stop)

    @patch('apps.divisas.pagos_stripe.stripe.checkout.Session.create')
    @patch('apps.divisas.pagos_stripe.stripe.PaymentIntent.create')
    def test_cobra_directo_con_el_monto_en_centavos_de_la_divisa_de_origen(self, mock_payment_intent, mock_checkout):
        """Criterio 1: un cambio se cobra en su divisa de ORIGEN (lo que el cliente entrega), no la de destino."""
        mock_payment_intent.return_value = SimpleNamespace(id='pi_directo_456', status='succeeded')

        response = self.client.get(self.url, follow=True)

        self.assertContains(response, 'El pago con tu tarjeta guardada se realizó correctamente')
        mock_checkout.assert_not_called()
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoTriangulacion.ESTADO_PAGADA)
        pago = Pago.objects.get(calculo_triangulacion=self.transaccion)
        self.assertEqual(pago.monto, self.transaccion.monto_origen)
        kwargs = mock_payment_intent.call_args.kwargs
        self.assertEqual(kwargs['amount'], 10000)
        self.assertEqual(kwargs['currency'], 'usd')
        self.assertEqual(kwargs['payment_method'], 'pm_guardado_456')


class StripeWebhookTest(TestCase):
    """Verifica el webhook que confirma (o descarta) un pago con tarjeta."""

    def setUp(self):
        """Prepara una compra 'Confirmada' y la URL del webhook."""
        self.usuario, self.cliente = _crear_cliente_logueado(self.client, 'cliente-webhook', 'STRIPE-WEBHOOK-001')
        self.usd = _crear_divisa_cotizada('USD', 'Dólar', Decimal('7300.00'), Decimal('7400.00'))
        self.transaccion = CalculoOperacion.objects.create(
            usuario=self.usuario,
            cliente=self.cliente,
            tipo=CalculoOperacion.TIPO_COMPRA,
            divisa=self.usd,
            codigo_divisa='USD',
            monto_origen=Decimal('100.00'),
            tasa_aplicada=Decimal('7400.00'),
            comision_porcentaje=Decimal('1.000'),
            comision=Decimal('7400.00'),
            monto_final=Decimal('747400.00'),
            estado=CalculoOperacion.ESTADO_CONFIRMADA,
            vence_en=timezone.now() + timedelta(seconds=300),
            confirmado_en=timezone.now(),
        )
        self.url = reverse('stripe_webhook')

        # Ver IniciarPagoStripeOperacionTest.setUp: la entrega queda fuera
        # del alcance de estos tests, que cubren solo el webhook de Stripe.
        parche_entrega = patch('apps.divisas.pagos_stripe.realizar_entrega', return_value=True)
        self.mock_entrega = parche_entrega.start()
        self.addCleanup(parche_entrega.stop)

    def _evento_sesion_completada(self, payment_status='paid', payment_intent='pi_123', session_id='cs_123'):
        """Arma el payload de un evento 'checkout.session.completed' para esta transacción."""
        return {
            'type': 'checkout.session.completed',
            'data': {
                'object': {
                    'id': session_id,
                    'payment_intent': payment_intent,
                    'payment_status': payment_status,
                    'metadata': {
                        'tipo_transaccion': 'operacion',
                        'transaccion_id': str(self.transaccion.pk),
                    },
                },
            },
        }

    @patch('apps.divisas.pagos_stripe.stripe.Webhook.construct_event')
    def test_firma_invalida_no_modifica_ninguna_transaccion(self, mock_construct_event):
        """Criterio 3: una firma inválida se rechaza sin tocar ninguna transacción."""
        mock_construct_event.side_effect = stripe.error.SignatureVerificationError('firma inválida', 'sig_header')

        response = self.client.post(
            self.url, data=b'payload-cualquiera', content_type='application/json', HTTP_STRIPE_SIGNATURE='firma-mala',
        )

        self.assertEqual(response.status_code, 400)
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_CONFIRMADA)
        self.assertEqual(Pago.objects.count(), 0)

    @patch('apps.divisas.pagos_stripe.stripe.Webhook.construct_event')
    def test_sesion_completada_y_pagada_registra_el_pago_con_tarjeta(self, mock_construct_event):
        """Criterio 2: una sesión completada y pagada registra el pago con el id de Stripe y medio 'tarjeta'."""
        mock_construct_event.return_value = self._evento_sesion_completada()

        response = self.client.post(
            self.url, data=b'payload', content_type='application/json', HTTP_STRIPE_SIGNATURE='firma-valida',
        )

        self.assertEqual(response.status_code, 200)
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_PAGADA)
        pago = Pago.objects.get(calculo_operacion=self.transaccion)
        self.assertEqual(pago.medio_pago, MetodoPago.TIPO_TARJETA)
        self.assertEqual(pago.proveedor, 'STRIPE')
        self.assertEqual(pago.identificador_externo, 'pi_123')
        self.assertEqual(pago.monto, self.transaccion.monto_final)

    @patch('apps.divisas.pagos_stripe.stripe.Webhook.construct_event')
    def test_sesion_completada_con_la_tasa_ya_vencida_no_entrega_ni_marca_pagada(self, mock_construct_event):
        """Un webhook que llega tarde registra el pago igual, pero como 'Pago fuera de plazo', sin entregar."""
        self.transaccion.tasa_vence_en = timezone.now() - timedelta(seconds=1)
        self.transaccion.save(update_fields=['tasa_vence_en'])
        mock_construct_event.return_value = self._evento_sesion_completada()

        response = self.client.post(
            self.url, data=b'payload', content_type='application/json', HTTP_STRIPE_SIGNATURE='firma-valida',
        )

        self.assertEqual(response.status_code, 200)
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_PAGO_EXPIRADO)
        pago = Pago.objects.get(calculo_operacion=self.transaccion)
        self.assertTrue(pago.fuera_de_plazo)
        self.mock_entrega.assert_not_called()

    @patch('apps.divisas.pagos_stripe.stripe.Webhook.construct_event')
    def test_sesion_no_pagada_no_modifica_la_transaccion(self, mock_construct_event):
        """Criterio 4: si Stripe todavía no cobró la sesión, la transacción sigue 'Confirmada'."""
        mock_construct_event.return_value = self._evento_sesion_completada(payment_status='unpaid')

        response = self.client.post(
            self.url, data=b'payload', content_type='application/json', HTTP_STRIPE_SIGNATURE='firma-valida',
        )

        self.assertEqual(response.status_code, 200)
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_CONFIRMADA)
        self.assertEqual(Pago.objects.count(), 0)

    @patch('apps.divisas.pagos_stripe.stripe.Webhook.construct_event')
    def test_evento_no_relevante_no_modifica_nada(self, mock_construct_event):
        """Criterio 4: un evento de pago fallido (manejado por la propia página de Stripe) no toca nada acá."""
        mock_construct_event.return_value = {
            'type': 'payment_intent.payment_failed',
            'data': {'object': {}},
        }

        response = self.client.post(
            self.url, data=b'payload', content_type='application/json', HTTP_STRIPE_SIGNATURE='firma-valida',
        )

        self.assertEqual(response.status_code, 200)
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_CONFIRMADA)
        self.assertEqual(Pago.objects.count(), 0)

    @patch('apps.divisas.pagos_stripe.stripe.Webhook.construct_event')
    def test_el_mismo_evento_reenviado_no_duplica_el_pago(self, mock_construct_event):
        """La confirmación es idempotente: reenviar el mismo evento no crea un segundo pago."""
        mock_construct_event.return_value = self._evento_sesion_completada()

        self.client.post(
            self.url, data=b'payload', content_type='application/json', HTTP_STRIPE_SIGNATURE='firma-valida',
        )
        response = self.client.post(
            self.url, data=b'payload', content_type='application/json', HTTP_STRIPE_SIGNATURE='firma-valida',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Pago.objects.filter(calculo_operacion=self.transaccion).count(), 1)

    def test_el_webhook_no_acepta_metodos_distintos_de_post(self):
        """La URL del webhook es exclusivamente para POST (Stripe nunca manda GET)."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405)

    @patch('apps.divisas.pagos_stripe.stripe.Webhook.construct_event')
    def test_registra_el_pago_con_un_evento_stripeobject_real(self, mock_construct_event):
        """Regresión: con el StripeObject real que devuelve el SDK (no un dict mockeado), igual registra el pago."""
        mock_construct_event.return_value = _stripe_object(self._evento_sesion_completada())

        response = self.client.post(
            self.url, data=b'payload', content_type='application/json', HTTP_STRIPE_SIGNATURE='firma-valida',
        )

        self.assertEqual(response.status_code, 200)
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_PAGADA)
        pago = Pago.objects.get(calculo_operacion=self.transaccion)
        self.assertEqual(pago.identificador_externo, 'pi_123')


class IniciarAgregarTarjetaStripeTest(TestCase):
    """Verifica el inicio del alta de una tarjeta nueva vía Stripe."""

    def setUp(self):
        """Prepara un cliente logueado sin ninguna tarjeta guardada todavía."""
        self.usuario, self.cliente = _crear_cliente_logueado(self.client, 'cliente-agregar-tarjeta', 'AGREGAR-001')
        self.url = reverse('clientes:agregar_tarjeta_stripe')

    def test_muestra_el_formulario_con_solo_el_nombre_del_cliente_precargado(self):
        """El GET precarga el campo con solo el nombre del cliente, sin su identificador ni su estado."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nombre del Titular')
        # El valor precargado del campo es exactamente "Cliente Stripe": ni
        # el identificador (p. ej. "AGREGAR-001") ni el estado ("Activo")
        # que sí incluye Cliente.__str__ se filtran acá.
        self.assertContains(response, 'value="Cliente Stripe" class="form-control"')

    @patch('apps.divisas.pagos_stripe.stripe.checkout.Session.create')
    @patch('apps.divisas.pagos_stripe._configuracion_solo_tarjeta', return_value='pmc_test_fake')
    @patch('apps.divisas.pagos_stripe._obtener_o_crear_cliente_stripe', return_value='cus_test_789')
    def test_redirige_a_stripe_con_los_datos_en_los_metadatos(self, mock_customer, mock_config, mock_checkout):
        """Crea la sesión de Stripe en modo 'setup', sin Link, y manda ahí el nombre del titular."""
        mock_checkout.return_value = SimpleNamespace(url='https://checkout.stripe.com/agregar-tarjeta')

        response = self.client.post(self.url, {'nombre_titular': 'Cliente Stripe'})

        self.assertRedirects(
            response, 'https://checkout.stripe.com/agregar-tarjeta', fetch_redirect_response=False,
        )
        kwargs = mock_checkout.call_args.kwargs
        self.assertEqual(kwargs['mode'], 'setup')
        self.assertEqual(kwargs['customer'], 'cus_test_789')
        self.assertEqual(kwargs['payment_method_configuration'], 'pmc_test_fake')
        self.assertEqual(
            kwargs['setup_intent_data']['metadata'],
            {'cliente_id': str(self.cliente.pk), 'nombre_titular': 'Cliente Stripe'},
        )

    def test_sin_nombre_del_titular_no_avanza(self):
        """El formulario exige el nombre del titular antes de ir a Stripe."""
        response = self.client.post(self.url, {'nombre_titular': ''})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This field is required.')

    @patch('apps.divisas.pagos_stripe.stripe.checkout.Session.create')
    @patch('apps.divisas.pagos_stripe._configuracion_solo_tarjeta', return_value='pmc_test_fake')
    @patch('apps.divisas.pagos_stripe._obtener_o_crear_cliente_stripe', return_value='cus_test_789')
    def test_problema_de_comunicacion_con_stripe_no_rompe_la_pagina(self, mock_customer, mock_config, mock_checkout):
        """Criterio 6, aplicado al alta: si Stripe no responde, se informa sin romper nada."""
        mock_checkout.side_effect = stripe.error.APIConnectionError('No se pudo conectar')

        response = self.client.post(self.url, {'nombre_titular': 'Cliente Stripe'}, follow=True)

        self.assertContains(response, 'No se pudo conectar con Stripe')
        self.assertEqual(MetodoPago.objects.count(), 0)

    def test_usuario_sin_rol_cliente_no_puede_agregar_tarjeta(self):
        """Solo el rol 'cliente' puede agregar una tarjeta."""
        session = self.client.session
        session['keycloak_roles'] = ['cajero']
        session.save()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)


class ConfirmarTarjetaStripeTest(TestCase):
    """Verifica la confirmación de una tarjeta nueva al volver desde Stripe."""

    def setUp(self):
        """Prepara un cliente logueado y la URL de confirmación."""
        self.usuario, self.cliente = _crear_cliente_logueado(self.client, 'cliente-confirmar-tarjeta', 'CONFIRMAR-001')
        self.url = reverse('clientes:confirmar_tarjeta_stripe')

        parche_customer = patch(
            'apps.divisas.pagos_stripe._obtener_o_crear_cliente_stripe', return_value='cus_test_confirmar',
        )
        self.mock_customer = parche_customer.start()
        self.addCleanup(parche_customer.stop)

    def _sesion_confirmada(self, pm_id='pm_nuevo_123', nombre_titular='Cliente Confirmado', customer='cus_test_confirmar'):
        """Arma, con un StripeObject real, la respuesta de una sesión con el SetupIntent ya exitoso.

        Usar un ``StripeObject`` real en vez de un ``SimpleNamespace`` es
        deliberado: es justamente lo que el SDK devuelve de verdad
        (``checkout.Session.retrieve``), y un mock más simple no hubiera
        detectado el bug real de ``metadata.get(...)`` (ver ``ADictTest``).
        """
        return _stripe_object({
            'customer': customer,
            'setup_intent': {
                'status': 'succeeded',
                'payment_method': pm_id,
                'metadata': {'nombre_titular': nombre_titular},
            },
        })

    @patch('apps.divisas.pagos_stripe.stripe.PaymentMethod.retrieve')
    @patch('apps.divisas.pagos_stripe.stripe.checkout.Session.retrieve')
    def test_confirma_y_crea_el_metodo_de_pago_con_los_datos_de_stripe(self, mock_session_retrieve, mock_pm_retrieve):
        """Crea el MetodoPago con el nombre pedido, la marca y los últimos 4 dígitos que da Stripe."""
        mock_session_retrieve.return_value = self._sesion_confirmada()
        mock_pm_retrieve.return_value = SimpleNamespace(card=SimpleNamespace(brand='visa', last4='4242'))

        response = self.client.get(self.url, {'session_id': 'cs_test_setup_123'}, follow=True)

        # El redirect final es al listado de métodos de pago: la tarjeta
        # recién agregada tiene que aparecer ahí, enmascarada.
        self.assertContains(response, 'Tarjeta agregada correctamente')
        self.assertContains(response, 'Cliente Confirmado')
        self.assertContains(response, '•••• •••• •••• 4242')
        metodo = MetodoPago.objects.get(cliente=self.cliente)
        self.assertEqual(metodo.tipo_medio, MetodoPago.TIPO_TARJETA)
        self.assertEqual(metodo.nombre_titular, 'Cliente Confirmado')
        self.assertEqual(metodo.entidad_financiera, 'Visa')
        self.assertEqual(metodo.numero_tarjeta, '4242')
        self.assertEqual(metodo.proveedor_externo, MetodoPago.PROVEEDOR_STRIPE)
        self.assertEqual(metodo.referencia_externa, 'pm_nuevo_123')
        self.assertEqual(metodo.moneda.codigo, 'PYG')

    def test_sin_session_id_no_crea_nada(self):
        """Sin ``?session_id=``, no hay nada que confirmar."""
        response = self.client.get(self.url, follow=True)

        self.assertContains(response, 'No se recibió la confirmación de Stripe')
        self.assertEqual(MetodoPago.objects.count(), 0)

    @patch('apps.divisas.pagos_stripe.stripe.checkout.Session.retrieve')
    def test_una_sesion_de_otro_customer_responde_404(self, mock_session_retrieve):
        """Una sesión que no corresponde al Customer de este cliente no puede usarse."""
        mock_session_retrieve.return_value = self._sesion_confirmada(customer='cus_de_otro_cliente')

        response = self.client.get(self.url, {'session_id': 'cs_ajena'})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(MetodoPago.objects.count(), 0)

    @patch('apps.divisas.pagos_stripe.stripe.checkout.Session.retrieve')
    def test_setup_intent_no_exitoso_no_crea_nada(self, mock_session_retrieve):
        """Si el SetupIntent no llegó a 'succeeded' (p. ej. se abandonó), no se crea el método."""
        mock_session_retrieve.return_value = SimpleNamespace(
            customer='cus_test_confirmar',
            setup_intent=SimpleNamespace(status='requires_payment_method', payment_method=None, metadata={}),
        )

        response = self.client.get(self.url, {'session_id': 'cs_incompleta'}, follow=True)

        self.assertContains(response, 'No se pudo confirmar la tarjeta con Stripe')
        self.assertEqual(MetodoPago.objects.count(), 0)

    @patch('apps.divisas.pagos_stripe.stripe.PaymentMethod.retrieve')
    @patch('apps.divisas.pagos_stripe.stripe.checkout.Session.retrieve')
    def test_confirmar_dos_veces_la_misma_tarjeta_no_la_duplica(self, mock_session_retrieve, mock_pm_retrieve):
        """Confirmar la misma sesión dos veces (p. ej. refrescar la página) no crea un segundo método."""
        mock_session_retrieve.return_value = self._sesion_confirmada()
        mock_pm_retrieve.return_value = SimpleNamespace(card=SimpleNamespace(brand='visa', last4='4242'))

        self.client.get(self.url, {'session_id': 'cs_test_setup_123'})
        response = self.client.get(self.url, {'session_id': 'cs_test_setup_123'}, follow=True)

        self.assertContains(response, 'Esa tarjeta ya estaba guardada')
        self.assertEqual(MetodoPago.objects.filter(cliente=self.cliente).count(), 1)

    @patch('apps.divisas.pagos_stripe.stripe.checkout.Session.retrieve')
    def test_problema_de_comunicacion_con_stripe_no_crea_nada(self, mock_session_retrieve):
        """Criterio 6, aplicado a la confirmación: si Stripe no responde, no se crea el método."""
        mock_session_retrieve.side_effect = stripe.error.APIConnectionError('No se pudo conectar')

        response = self.client.get(self.url, {'session_id': 'cs_test_setup_123'}, follow=True)

        self.assertContains(response, 'No se pudo confirmar la tarjeta con Stripe')
        self.assertEqual(MetodoPago.objects.count(), 0)

    @patch('apps.divisas.pagos_stripe.stripe.PaymentMethod.retrieve')
    @patch('apps.divisas.pagos_stripe.stripe.checkout.Session.retrieve')
    def test_un_metodo_que_no_es_tarjeta_no_crea_nada(self, mock_session_retrieve, mock_pm_retrieve):
        """Regresión: si el cliente eligió Link (o cualquier otro medio) en vez de una tarjeta, no rompe ni crea nada.

        Reproduce el bug real: antes de la ``PaymentMethodConfiguration``
        que apaga Link, Stripe podía devolver un ``PaymentMethod`` sin
        atributo ``card`` y la vista tiraba ``AttributeError``.
        """
        mock_session_retrieve.return_value = self._sesion_confirmada()
        mock_pm_retrieve.return_value = SimpleNamespace(type='link')

        response = self.client.get(self.url, {'session_id': 'cs_test_setup_123'}, follow=True)

        self.assertContains(response, 'no fue una tarjeta')
        self.assertEqual(MetodoPago.objects.count(), 0)
