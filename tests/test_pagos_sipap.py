"""Pruebas de la HU 'Pago por transferencia bancaria vía SIPAP' (bancos y billeteras digitales)."""

import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import Cliente, MetodoPago
from apps.divisas.models import (
    CalculoOperacion,
    CalculoTriangulacion,
    Cotizacion,
    Divisa,
    Pago,
    PagoRechazadoError,
    SolicitudPagoSipap,
)
from apps.divisas.pagos_sipap import (
    SipapComunicacionError,
    _crear_solicitud_cobro_en_sipap,
    _firma_valida,
    _generar_referencia,
    _obtener_o_crear_solicitud,
)

User = get_user_model()

WEBHOOK_SECRET_TEST = 'sipap-secreto-de-test'
BASE_URL_TEST = 'http://sipap-sim.test'
API_KEY_TEST = 'sipap-api-key-de-test'


def _crear_cliente_logueado(client, username, identificador):
    """Crea un usuario con un cliente asociado y lo loguea con rol 'cliente'."""
    usuario = User.objects.create_user(username=username, password='password123')
    cliente = Cliente.objects.create(
        user=usuario,
        identificador=identificador,
        nombre='Cliente',
        apellido='Sipap',
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


def _firmar(payload_bytes, secreto=WEBHOOK_SECRET_TEST):
    """Firma un payload como lo haría el emisor real del webhook, para los tests."""
    return hmac.new(secreto.encode('utf-8'), payload_bytes, hashlib.sha256).hexdigest()


def _simular_sipap_ok(solicitud, url_retorno):
    """Sustituye la llamada HTTP real a sipap-sim por un éxito, como si hubiese respondido bien."""
    solicitud.id_externo = f'SPI-TEST-{solicitud.referencia}'
    solicitud.link_pago = f'{BASE_URL_TEST}/pagar/{solicitud.id_externo}/'


def _crear_metodo_pago_sipap(cliente, tipo_medio=MetodoPago.TIPO_TRANSFERENCIA, numero_cuenta='2000000000000101', documento_titular='3456789'):
    """Crea un método de pago de transferencia o billetera, ya con cuenta y documento (como si sipap-sim ya lo hubiese validado)."""
    return MetodoPago.objects.create(
        cliente=cliente, tipo_medio=tipo_medio, nombre_titular='Juan Pérez',
        entidad_financiera='Banco Itaú Paraguay', numero_cuenta=numero_cuenta, documento_titular=documento_titular,
    )


class GenerarReferenciaTest(TestCase):
    """Pruebas unitarias de la generación de referencias únicas."""

    def test_tiene_el_prefijo_esperado_y_es_distinta_entre_llamadas(self):
        with self.subTest("empieza con 'SIPAP-', para que se distinga a simple vista"):
            self.assertTrue(_generar_referencia().startswith('SIPAP-'))

        with self.subTest('dos solicitudes nunca deberían terminar con la misma referencia'):
            self.assertNotEqual(_generar_referencia(), _generar_referencia())


class FirmaValidaTest(TestCase):
    """Pruebas unitarias de la verificación de firma HMAC del webhook."""

    @override_settings(SIPAP_WEBHOOK_SECRET=WEBHOOK_SECRET_TEST)
    def test_firma_valida_segun_el_caso(self):
        payload = b'{"referencia": "SIPAP-ABC"}'

        with self.subTest('la firma calculada con el secreto correcto se acepta'):
            self.assertTrue(_firma_valida(payload, _firmar(payload)))

        with self.subTest('una firma que no coincide (payload alterado o secreto distinto) se rechaza'):
            self.assertFalse(_firma_valida(payload, _firmar(payload, secreto='otro-secreto')))

        with self.subTest('sin encabezado de firma, se rechaza en vez de tirar una excepción'):
            self.assertFalse(_firma_valida(b'{"a": 1}', ''))


@override_settings(SIPAP_BASE_URL=BASE_URL_TEST, SIPAP_API_KEY=API_KEY_TEST)
class CrearSolicitudCobroEnSipapTest(TestCase):
    """Pruebas unitarias de 'pedirle a sipap-sim' que genere el link de pago de una solicitud."""

    def setUp(self):
        self.cliente = Cliente.objects.create(
            identificador='SIPAP-HTTP-001', nombre='Hugo', apellido='Sipap',
            email='hugo-sipap@test.com', is_active=True,
        )
        self.metodo_pago = _crear_metodo_pago_sipap(self.cliente)

    def _solicitud(self):
        return SolicitudPagoSipap(
            referencia='SIPAP-TEST', monto=Decimal('100.00'), moneda='USD', metodo_pago=self.metodo_pago,
        )

    @patch('apps.divisas.pagos_sipap.requests.post')
    def test_llama_al_endpoint_correcto_con_el_token_y_guarda_lo_que_responde(self, mock_post):
        """Llama a POST {SIPAP_BASE_URL}/api/solicitudes-cobro/ autenticado, y guarda id/link_pago."""
        mock_post.return_value = Mock(
            raise_for_status=Mock(),
            json=Mock(return_value={'id': 'SPI-20261011-000123', 'link_pago': 'http://sipap-sim.test/pagar/SPI-20261011-000123/'}),
        )
        solicitud = self._solicitud()

        _crear_solicitud_cobro_en_sipap(solicitud, 'http://ge.test/detalle/')

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], f'{BASE_URL_TEST}/api/solicitudes-cobro/')
        self.assertEqual(kwargs['headers']['Authorization'], f'Bearer {API_KEY_TEST}')
        self.assertEqual(kwargs['json']['moneda'], 'USD')
        self.assertEqual(kwargs['json']['referencia'], 'SIPAP-TEST')
        self.assertEqual(kwargs['json']['url_retorno'], 'http://ge.test/detalle/')
        self.assertEqual(kwargs['json']['cuenta_origen_numero'], self.metodo_pago.numero_cuenta)
        self.assertEqual(kwargs['json']['cuenta_origen_documento'], self.metodo_pago.documento_titular)
        self.assertEqual(solicitud.id_externo, 'SPI-20261011-000123')
        self.assertEqual(solicitud.link_pago, 'http://sipap-sim.test/pagar/SPI-20261011-000123/')

    @patch('apps.divisas.pagos_sipap.requests.post')
    def test_fallas_de_comunicacion_levantan_sipap_comunicacion_error(self, mock_post):
        """Criterio 6: error de conexión, respuesta no-2xx, o cuerpo no-JSON: todas son una falla de comunicación."""
        import requests

        with self.subTest('error de conexión real (sipap-sim apagado)'):
            mock_post.side_effect = requests.exceptions.ConnectionError('no se pudo conectar')

            with self.assertRaises(SipapComunicacionError):
                _crear_solicitud_cobro_en_sipap(self._solicitud(), 'http://ge.test/detalle/')

        with self.subTest('una respuesta que no sea 2xx (p. ej. SIM_MODO_FALLA=error)'):
            mock_post.side_effect = None
            mock_post.return_value = Mock(raise_for_status=Mock(side_effect=requests.exceptions.HTTPError('500')))

            with self.assertRaises(SipapComunicacionError):
                _crear_solicitud_cobro_en_sipap(self._solicitud(), 'http://ge.test/detalle/')

        with self.subTest('una respuesta 2xx pero con un cuerpo que no se puede decodificar'):
            mock_post.return_value = Mock(raise_for_status=Mock(), json=Mock(side_effect=ValueError('no es json')))

            with self.assertRaises(SipapComunicacionError):
                _crear_solicitud_cobro_en_sipap(self._solicitud(), 'http://ge.test/detalle/')


class SolicitudPagoSipapModeloTest(TestCase):
    """Pruebas unitarias del vencimiento perezoso de una solicitud."""

    def setUp(self):
        """Prepara un cliente y una compra 'Confirmada' para asociar las solicitudes."""
        self.cliente = Cliente.objects.create(
            identificador='SIPAP-MODELO-001', nombre='Ana', apellido='Sipap',
            email='ana-sipap@test.com', is_active=True,
        )
        self.usd = _crear_divisa_cotizada('USD', 'Dólar', Decimal('7300.00'), Decimal('7400.00'))
        self.transaccion = CalculoOperacion.objects.create(
            usuario=User.objects.create_user(username='user-sipap-modelo', password='x'),
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

    def test_el_vencimiento_depende_del_plazo_y_de_si_ya_se_resolvio(self):
        # SolicitudPagoSipap.calculo_operacion es OneToOne: cada subTest borra
        # la suya antes del siguiente, para poder seguir usando self.transaccion.
        with self.subTest('mientras no se pase la fecha, no está vencida'):
            solicitud = SolicitudPagoSipap.objects.create(
                calculo_operacion=self.transaccion, referencia='SIPAP-VIG-001',
                monto=Decimal('747400.00'), moneda='PYG', vence_en=timezone.now() + timedelta(hours=1),
            )

            self.assertFalse(solicitud.esta_vencida)
            self.assertFalse(solicitud.marcar_vencida_si_corresponde())
            solicitud.refresh_from_db()
            self.assertEqual(solicitud.estado, SolicitudPagoSipap.ESTADO_PENDIENTE)
            solicitud.delete()

        with self.subTest("pasado el plazo, 'marcar_vencida_si_corresponde' la persiste como 'Vencida'"):
            solicitud = SolicitudPagoSipap.objects.create(
                calculo_operacion=self.transaccion, referencia='SIPAP-VEN-001',
                monto=Decimal('747400.00'), moneda='PYG', vence_en=timezone.now() - timedelta(seconds=1),
            )

            self.assertTrue(solicitud.esta_vencida)
            self.assertTrue(solicitud.marcar_vencida_si_corresponde())
            solicitud.refresh_from_db()
            self.assertEqual(solicitud.estado, SolicitudPagoSipap.ESTADO_VENCIDA)
            solicitud.delete()

        with self.subTest("una solicitud 'Acreditada' no vuelve a marcarse como algo distinto por el paso del tiempo"):
            solicitud = SolicitudPagoSipap.objects.create(
                calculo_operacion=self.transaccion, referencia='SIPAP-ACR-001',
                monto=Decimal('747400.00'), moneda='PYG', vence_en=timezone.now() - timedelta(seconds=1),
                estado=SolicitudPagoSipap.ESTADO_ACREDITADA,
            )

            self.assertFalse(solicitud.esta_vencida)
            self.assertFalse(solicitud.marcar_vencida_si_corresponde())


class RegistrarPagoObservadoTest(TestCase):
    """Verifica ``Pago.registrar_pago_observado``, el punto de entrada de un pago con monto distinto."""

    def setUp(self):
        """Prepara un cliente y una compra ya 'Confirmada'."""
        self.cliente = Cliente.objects.create(
            identificador='SIPAP-OBS-001', nombre='Bruno', apellido='Sipap',
            email='bruno-sipap@test.com', is_active=True,
        )
        self.usd = _crear_divisa_cotizada('USD', 'Dólar', Decimal('7300.00'), Decimal('7400.00'))
        self.transaccion = CalculoOperacion.objects.create(
            usuario=User.objects.create_user(username='user-sipap-obs', password='x'),
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

    def test_registra_el_pago_observado_sin_marcar_pagada(self):
        """Criterio 3: queda un Pago con observado=True y la diferencia, sin marcar 'Pagada'."""
        pago, creado = Pago.registrar_pago_observado(
            self.transaccion, medio_pago=MetodoPago.TIPO_TRANSFERENCIA, proveedor='SIPAP',
            identificador_externo='OP-123', monto=Decimal('700000.00'),
            diferencia=Decimal('700000.00') - Decimal('747400.00'),
        )

        self.assertTrue(creado)
        self.assertTrue(pago.observado)
        self.assertEqual(pago.diferencia, Decimal('-47400.00'))
        self.assertEqual(pago.monto, Decimal('700000.00'))
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_CONFIRMADA)

    def test_es_idempotente_ante_el_mismo_identificador(self):
        """Repetir la misma confirmación no crea un segundo pago observado."""
        Pago.registrar_pago_observado(
            self.transaccion, medio_pago=MetodoPago.TIPO_TRANSFERENCIA, proveedor='SIPAP',
            identificador_externo='OP-456', monto=Decimal('700000.00'), diferencia=Decimal('-47400.00'),
        )

        pago, creado = Pago.registrar_pago_observado(
            self.transaccion, medio_pago=MetodoPago.TIPO_TRANSFERENCIA, proveedor='SIPAP',
            identificador_externo='OP-456', monto=Decimal('700000.00'), diferencia=Decimal('-47400.00'),
        )

        self.assertFalse(creado)
        self.assertEqual(Pago.objects.filter(calculo_operacion=self.transaccion).count(), 1)

    def test_rechaza_si_la_transaccion_no_esta_en_condiciones(self):
        """No se puede observar un pago sobre algo que no está 'Confirmada' (ni antes, ni después de pagarse)."""
        with self.subTest('no está Confirmada'):
            self.transaccion.estado = CalculoOperacion.ESTADO_PENDIENTE
            self.transaccion.save(update_fields=['estado'])

            with self.assertRaises(PagoRechazadoError):
                Pago.registrar_pago_observado(
                    self.transaccion, medio_pago=MetodoPago.TIPO_TRANSFERENCIA, proveedor='SIPAP',
                    identificador_externo='OP-789', monto=Decimal('1.00'), diferencia=Decimal('1.00'),
                )

        with self.subTest('ya está Pagada'):
            self.transaccion.estado = CalculoOperacion.ESTADO_CONFIRMADA
            self.transaccion.save(update_fields=['estado'])
            Pago.registrar_pago(
                self.transaccion, medio_pago=MetodoPago.TIPO_TRANSFERENCIA, proveedor=Pago.PROVEEDOR_MANUAL,
                identificador_externo=str(self.transaccion.pk), monto=self.transaccion.monto_final,
            )

            with self.assertRaises(PagoRechazadoError):
                Pago.registrar_pago_observado(
                    self.transaccion, medio_pago=MetodoPago.TIPO_TRANSFERENCIA, proveedor='SIPAP',
                    identificador_externo='OP-999', monto=Decimal('1.00'), diferencia=Decimal('1.00'),
                )


@patch('apps.divisas.pagos_sipap._crear_solicitud_cobro_en_sipap', side_effect=_simular_sipap_ok)
class IniciarPagoSipapOperacionTest(TestCase):
    """Verifica el inicio del pago por SIPAP (transferencia o billetera) de una compra o venta."""

    def setUp(self):
        """Prepara un cliente logueado y una compra ya 'Confirmada' en PYG."""
        self.usuario, self.cliente = _crear_cliente_logueado(self.client, 'cliente-sipap-op', 'SIPAP-OP-001')
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
        self.metodo_pago = _crear_metodo_pago_sipap(self.cliente)
        self.metodo_billetera = _crear_metodo_pago_sipap(
            self.cliente, tipo_medio=MetodoPago.TIPO_BILLETERA,
            numero_cuenta='2000000000000501', documento_titular='3456789',
        )
        self.url = reverse('divisas:pagar_transaccion_sipap', kwargs={'pk': self.transaccion.pk})
        self.detalle_url = reverse('divisas:detalle_transaccion_operacion', kwargs={'pk': self.transaccion.pk})

    def test_genera_la_solicitud_con_el_monto_exacto_y_redirige_al_link_de_pago(self, mock_crear):
        """Criterio 1: la solicitud se crea con el monto exacto de la transacción, y se redirige a sipap-sim."""
        with self.subTest('transferencia'):
            response = self.client.get(self.url, {'metodo_pago': self.metodo_pago.pk})

            solicitud = SolicitudPagoSipap.objects.get(calculo_operacion=self.transaccion)
            self.assertRedirects(response, solicitud.link_pago, fetch_redirect_response=False)
            self.assertEqual(solicitud.monto, Decimal('747400.00'))
            self.assertEqual(solicitud.moneda, 'PYG')
            self.assertTrue(solicitud.referencia.startswith('SIPAP-'))
            self.assertEqual(solicitud.estado, SolicitudPagoSipap.ESTADO_PENDIENTE)
            self.assertEqual(solicitud.medio_pago, MetodoPago.TIPO_TRANSFERENCIA)
            self.assertEqual(solicitud.metodo_pago, self.metodo_pago)
            mock_crear.assert_called_once()

        with self.subTest('billetera digital: mismo flujo, pero queda registrada como tal'):
            otra_transaccion = CalculoOperacion.objects.create(
                usuario=self.usuario, cliente=self.cliente, tipo=CalculoOperacion.TIPO_COMPRA,
                divisa=self.usd, codigo_divisa='USD', monto_origen=Decimal('100.00'),
                tasa_aplicada=Decimal('7400.00'), comision_porcentaje=Decimal('1.000'),
                comision=Decimal('7400.00'), monto_final=Decimal('747400.00'),
                estado=CalculoOperacion.ESTADO_CONFIRMADA, vence_en=timezone.now() + timedelta(seconds=300),
                confirmado_en=timezone.now(),
            )
            url = reverse('divisas:pagar_transaccion_sipap', kwargs={'pk': otra_transaccion.pk})

            response = self.client.get(url, {'metodo_pago': self.metodo_billetera.pk})

            solicitud = SolicitudPagoSipap.objects.get(calculo_operacion=otra_transaccion)
            self.assertRedirects(response, solicitud.link_pago, fetch_redirect_response=False)
            self.assertEqual(solicitud.medio_pago, MetodoPago.TIPO_BILLETERA)
            self.assertEqual(solicitud.metodo_pago, self.metodo_billetera)

    def test_sin_una_solicitud_posible_no_se_crea_ninguna(self, mock_crear):
        """Sin un método de pago válido, o si sipap-sim no responde: se rechaza sin crear ninguna solicitud."""
        with self.subTest('sin un método de pago propio y válido'):
            response = self.client.get(self.url, follow=True)

            self.assertContains(response, 'Elegí una cuenta bancaria o billetera guardada')
            self.assertFalse(SolicitudPagoSipap.objects.filter(calculo_operacion=self.transaccion).exists())
            mock_crear.assert_not_called()

        with self.subTest('criterio 6: sipap-sim no responde'):
            mock_crear.side_effect = SipapComunicacionError('no se pudo conectar')

            response = self.client.get(self.url, {'metodo_pago': self.metodo_pago.pk}, follow=True)

            self.assertContains(response, 'No se pudo conectar con SIPAP')
            self.assertFalse(SolicitudPagoSipap.objects.filter(calculo_operacion=self.transaccion).exists())
            self.transaccion.refresh_from_db()
            self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_CONFIRMADA)

    def test_revisitar_la_pantalla_reutiliza_la_misma_solicitud_pendiente(self, mock_crear):
        """Visitar dos veces sin pagar no crea una segunda solicitud ni cambia la referencia ni el link."""
        self.client.get(self.url, {'metodo_pago': self.metodo_pago.pk})
        primera = SolicitudPagoSipap.objects.get(calculo_operacion=self.transaccion)

        self.client.get(self.url, {'metodo_pago': self.metodo_pago.pk})

        self.assertEqual(SolicitudPagoSipap.objects.filter(calculo_operacion=self.transaccion).count(), 1)
        primera.refresh_from_db()
        segunda = SolicitudPagoSipap.objects.get(calculo_operacion=self.transaccion)
        self.assertEqual(primera.referencia, segunda.referencia)
        self.assertEqual(primera.link_pago, segunda.link_pago)
        mock_crear.assert_called_once()

    def test_una_carrera_entre_dos_solicitudes_simultaneas_no_rompe_con_un_500(self, mock_crear):
        """Un doble clic (dos solicitudes casi simultáneas) no debe terminar en un IntegrityError sin manejar."""
        ganadora = SolicitudPagoSipap.objects.create(
            calculo_operacion=self.transaccion, referencia='SIPAP-GANADORA', monto=Decimal('747400.00'),
            moneda='PYG', medio_pago=MetodoPago.TIPO_TRANSFERENCIA, metodo_pago=self.metodo_pago,
            vence_en=timezone.now() + timedelta(hours=1), link_pago='http://sipap-sim.test/pagar/ganadora/',
        )
        with patch(
            'apps.divisas.pagos_sipap.SolicitudPagoSipap.objects.filter',
            return_value=SolicitudPagoSipap.objects.none(),
        ):
            response = self.client.get(self.url, {'metodo_pago': self.metodo_pago.pk})

        self.assertRedirects(response, ganadora.link_pago, fetch_redirect_response=False)
        self.assertEqual(SolicitudPagoSipap.objects.filter(calculo_operacion=self.transaccion).count(), 1)

    def test_no_permite_generar_una_solicitud_si_la_transaccion_no_esta_en_condiciones(self, mock_crear):
        """Solo una transacción 'Confirmada', con la tasa todavía vigente, puede iniciar un pago por SIPAP."""
        with self.subTest('no está Confirmada'):
            self.transaccion.estado = CalculoOperacion.ESTADO_PENDIENTE
            self.transaccion.save(update_fields=['estado'])

            response = self.client.get(self.url, {'metodo_pago': self.metodo_pago.pk}, follow=True)

            self.assertContains(response, 'no está en condiciones de pagarse')
            self.assertFalse(SolicitudPagoSipap.objects.filter(calculo_operacion=self.transaccion).exists())
            mock_crear.assert_not_called()

        with self.subTest('la tasa fijada ya venció'):
            self.transaccion.estado = CalculoOperacion.ESTADO_CONFIRMADA
            self.transaccion.tasa_vence_en = timezone.now() - timedelta(seconds=1)
            self.transaccion.save(update_fields=['estado', 'tasa_vence_en'])

            response = self.client.get(self.url, {'metodo_pago': self.metodo_pago.pk}, follow=True)

            self.assertContains(response, 'ya venció')
            self.assertFalse(SolicitudPagoSipap.objects.filter(calculo_operacion=self.transaccion).exists())
            mock_crear.assert_not_called()

    def test_la_solicitud_nunca_dura_mas_que_la_tasa_fijada(self, mock_crear):
        """``vence_en`` de la solicitud nunca supera ``tasa_vence_en`` de la transacción."""
        self.transaccion.tasa_vence_en = timezone.now() + timedelta(minutes=5)
        self.transaccion.save(update_fields=['tasa_vence_en'])

        self.client.get(self.url, {'metodo_pago': self.metodo_pago.pk})

        solicitud = SolicitudPagoSipap.objects.get(calculo_operacion=self.transaccion)
        self.assertEqual(solicitud.vence_en, self.transaccion.tasa_vence_en)

    def test_una_solicitud_vencida_se_reinicia_con_una_referencia_nueva_al_reintentar(self, mock_crear):
        """Criterio 5: tras vencer, volver a iniciar el pago genera una referencia y un link nuevos para reintentar."""
        self.client.get(self.url, {'metodo_pago': self.metodo_pago.pk})
        vencida = SolicitudPagoSipap.objects.get(calculo_operacion=self.transaccion)
        vencida.vence_en = timezone.now() - timedelta(seconds=1)
        vencida.save(update_fields=['vence_en'])
        referencia_vieja = vencida.referencia
        link_pago_viejo = vencida.link_pago

        response = self.client.get(self.url, {'metodo_pago': self.metodo_pago.pk})

        self.assertEqual(SolicitudPagoSipap.objects.filter(calculo_operacion=self.transaccion).count(), 1)
        reiniciada = SolicitudPagoSipap.objects.get(calculo_operacion=self.transaccion)
        self.assertEqual(reiniciada.estado, SolicitudPagoSipap.ESTADO_PENDIENTE)
        self.assertNotEqual(reiniciada.referencia, referencia_vieja)
        self.assertNotEqual(reiniciada.link_pago, link_pago_viejo)
        self.assertRedirects(response, reiniciada.link_pago, fetch_redirect_response=False)

    def test_una_solicitud_observada_no_se_reinicia_sola(self, mock_crear):
        """Una solicitud observada necesita revisión manual: no se puede reintentar sin más."""
        solicitud = SolicitudPagoSipap.objects.create(
            calculo_operacion=self.transaccion, referencia='SIPAP-OBSERVADA-001',
            monto=Decimal('747400.00'), moneda='PYG', vence_en=timezone.now() + timedelta(hours=1),
            estado=SolicitudPagoSipap.ESTADO_OBSERVADA,
        )

        response = self.client.get(self.url, {'metodo_pago': self.metodo_pago.pk}, follow=True)

        self.assertContains(response, 'pendiente de revisión')
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, SolicitudPagoSipap.ESTADO_OBSERVADA)
        mock_crear.assert_not_called()

    def test_usuario_sin_rol_cliente_no_puede_iniciar_el_pago(self, mock_crear):
        """Solo el rol 'cliente' puede iniciar un pago por SIPAP."""
        session = self.client.session
        session['keycloak_roles'] = ['cajero']
        session.save()

        response = self.client.get(self.url, {'metodo_pago': self.metodo_pago.pk})

        self.assertEqual(response.status_code, 403)


@patch('apps.divisas.pagos_sipap._crear_solicitud_cobro_en_sipap', side_effect=_simular_sipap_ok)
class IniciarPagoSipapCambioTest(TestCase):
    """Verifica el inicio del pago por SIPAP de un cambio entre divisas."""

    def setUp(self):
        """Prepara un cliente logueado y un cambio ya 'Confirmado' que liquida en EUR (divisa de origen)."""
        self.usuario, self.cliente = _crear_cliente_logueado(self.client, 'cliente-sipap-cambio', 'SIPAP-CAMBIO-001')
        self.usd = _crear_divisa_cotizada('USD', 'Dólar', Decimal('7300.00'), Decimal('7400.00'))
        self.eur = _crear_divisa_cotizada('EUR', 'Euro', Decimal('7900.00'), Decimal('8100.00'))
        self.transaccion = CalculoTriangulacion.objects.create(
            usuario=self.usuario,
            cliente=self.cliente,
            divisa_origen=self.eur,
            divisa_destino=self.usd,
            codigo_divisa_origen='EUR',
            codigo_divisa_destino='USD',
            monto_origen=Decimal('500.00'),
            tasa_compra_aplicada=Decimal('6100.00'),
            tasa_venta_aplicada=Decimal('5400.00'),
            tasa_cruzada=Decimal('1.129630'),
            monto_equivalente_pyg=Decimal('3050000.00'),
            comision_porcentaje=Decimal('1.000'),
            comision=Decimal('5.65'),
            monto_final=Decimal('559.16'),
            estado=CalculoTriangulacion.ESTADO_CONFIRMADA,
            vence_en=timezone.now() + timedelta(seconds=300),
            confirmado_en=timezone.now(),
        )
        self.metodo_pago = _crear_metodo_pago_sipap(self.cliente)
        self.url = reverse('divisas:pagar_transaccion_cambio_sipap', kwargs={'pk': self.transaccion.pk})

    def test_genera_la_solicitud_con_el_monto_de_la_divisa_de_origen(self, mock_crear):
        """Criterio 1, aplicado al cambio: se cobra monto_origen en la divisa de origen, no monto_final."""
        response = self.client.get(self.url, {'metodo_pago': self.metodo_pago.pk})

        solicitud = SolicitudPagoSipap.objects.get(calculo_triangulacion=self.transaccion)
        self.assertRedirects(response, solicitud.link_pago, fetch_redirect_response=False)
        self.assertEqual(solicitud.monto, Decimal('500.00'))
        self.assertEqual(solicitud.moneda, 'EUR')


class SipapWebhookTest(TestCase):
    """Verifica el webhook que confirma (o descarta) un pago por SIPAP."""

    def setUp(self):
        """Prepara una compra 'Confirmada' con una solicitud SIPAP ya generada."""
        self.usuario, self.cliente = _crear_cliente_logueado(self.client, 'cliente-sipap-webhook', 'SIPAP-WH-001')
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
        self.metodo_pago = _crear_metodo_pago_sipap(self.cliente)
        self.solicitud = SolicitudPagoSipap.objects.create(
            calculo_operacion=self.transaccion, referencia='SIPAP-WEBHOOK-001',
            monto=Decimal('747400.00'), moneda='PYG', vence_en=timezone.now() + timedelta(hours=1),
            metodo_pago=self.metodo_pago,
        )
        self.url = reverse('sipap_webhook')

        # La entrega (transferir la divisa comprada al cliente) es un paso
        # posterior a este webhook, con su propia integración HTTP a
        # sipap-sim; estos tests cubren solo la confirmación del pago en
        # sí, así que se mockea para que "siempre funcione" sin red real.
        parche_entrega = patch('apps.divisas.pagos_sipap.realizar_entrega', return_value=True)
        self.mock_entrega = parche_entrega.start()
        self.addCleanup(parche_entrega.stop)

    def _post(self, datos, secreto=WEBHOOK_SECRET_TEST):
        """Firma y envía un payload al webhook, como lo haría sipap-sim de verdad."""
        payload = json.dumps(datos).encode('utf-8')
        firma = _firmar(payload, secreto)
        return self.client.post(
            self.url, data=payload, content_type='application/json', HTTP_X_SIPAP_SIGNATURE=firma,
        )

    @override_settings(SIPAP_WEBHOOK_SECRET=WEBHOOK_SECRET_TEST)
    def test_firma_invalida_no_modifica_nada(self):
        """Criterio 4: una firma inválida se rechaza sin tocar ninguna transacción ni solicitud."""
        payload = json.dumps({'referencia': self.solicitud.referencia, 'estado': 'acreditada'}).encode('utf-8')
        response = self.client.post(
            self.url, data=payload, content_type='application/json', HTTP_X_SIPAP_SIGNATURE='firma-mala',
        )

        self.assertEqual(response.status_code, 400)
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, SolicitudPagoSipap.ESTADO_PENDIENTE)
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_CONFIRMADA)

    @override_settings(SIPAP_WEBHOOK_SECRET=WEBHOOK_SECRET_TEST)
    def test_acreditada_con_monto_exacto_marca_pagada(self):
        """Criterio 2: con el monto exacto (numérico, como lo manda sipap-sim), registra el pago y pasa a 'Pagada'."""
        response = self._post({
            'id_operacion': 'SPI-20261011-000123', 'referencia': self.solicitud.referencia, 'estado': 'acreditada',
            'monto': 747400, 'moneda': 'PYG', 'banco_origen': 'Banco Itaú Paraguay',
        })

        self.assertEqual(response.status_code, 200)
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_PAGADA)
        pago = Pago.objects.get(calculo_operacion=self.transaccion)
        self.assertFalse(pago.observado)
        self.assertEqual(pago.medio_pago, MetodoPago.TIPO_TRANSFERENCIA)
        self.assertEqual(pago.proveedor, 'SIPAP')
        self.assertEqual(pago.identificador_externo, 'SPI-20261011-000123')
        self.assertEqual(pago.monto, Decimal('747400.00'))
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, SolicitudPagoSipap.ESTADO_ACREDITADA)
        self.assertEqual(self.solicitud.banco_origen, 'Banco Itaú Paraguay')
        self.assertEqual(self.solicitud.pago, pago)
        self.assertEqual(pago.metodo_pago, self.metodo_pago)

    @override_settings(SIPAP_WEBHOOK_SECRET=WEBHOOK_SECRET_TEST)
    def test_acreditada_de_una_venta_tambien_dispara_la_entrega_automatica(self):
        """HU "Retiro de fondos" (GE-24): una venta pagada se entrega sola, igual que una compra o un cambio.

        Mismo mecanismo que GE-23: se paga y se recibe, sin que el
        cliente tenga que pedir nada aparte (``realizar_entrega`` se
        llama apenas se confirma el pago, para los tres tipos de
        transacción por igual).
        """
        venta = CalculoOperacion.objects.create(
            usuario=self.usuario, cliente=self.cliente, tipo=CalculoOperacion.TIPO_VENTA,
            divisa=self.usd, codigo_divisa='USD', monto_origen=Decimal('100.00'),
            tasa_aplicada=Decimal('7300.00'), comision_porcentaje=Decimal('1.000'),
            comision=Decimal('73.00'), monto_final=Decimal('729700.00'),
            estado=CalculoOperacion.ESTADO_CONFIRMADA, vence_en=timezone.now() + timedelta(seconds=300),
            confirmado_en=timezone.now(),
        )
        metodo_pago_usd = _crear_metodo_pago_sipap(
            self.cliente, numero_cuenta='2000000000000202', documento_titular='7654321',
        )
        solicitud = SolicitudPagoSipap.objects.create(
            calculo_operacion=venta, referencia='SIPAP-VENTA-WEBHOOK-001',
            monto=Decimal('100.00'), moneda='USD', vence_en=timezone.now() + timedelta(hours=1),
            metodo_pago=metodo_pago_usd,
        )

        response = self._post({
            'id_operacion': 'SPI-VENTA-001', 'referencia': solicitud.referencia, 'estado': 'acreditada',
            'monto': 100.00, 'moneda': 'USD', 'banco_origen': 'Banco Itaú Paraguay',
        })

        self.assertEqual(response.status_code, 200)
        venta.refresh_from_db()
        self.assertEqual(venta.estado, CalculoOperacion.ESTADO_PAGADA)
        self.mock_entrega.assert_called_once()
        self.assertEqual(self.mock_entrega.call_args.args[0].pk, venta.pk)

    @override_settings(SIPAP_WEBHOOK_SECRET=WEBHOOK_SECRET_TEST)
    def test_acreditada_con_la_tasa_ya_vencida_no_entrega_ni_marca_pagada(self):
        """Una acreditación que llega tarde registra el pago igual, pero como 'Pago fuera de plazo', sin entregar."""
        self.transaccion.tasa_vence_en = timezone.now() - timedelta(seconds=1)
        self.transaccion.save(update_fields=['tasa_vence_en'])

        response = self._post({
            'id_operacion': 'SPI-TARDE-001', 'referencia': self.solicitud.referencia, 'estado': 'acreditada',
            'monto': 747400, 'moneda': 'PYG', 'banco_origen': 'Banco Itaú Paraguay',
        })

        self.assertEqual(response.status_code, 200)
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_PAGO_EXPIRADO)
        pago = Pago.objects.get(calculo_operacion=self.transaccion)
        self.assertTrue(pago.fuera_de_plazo)
        self.mock_entrega.assert_not_called()

    @override_settings(SIPAP_WEBHOOK_SECRET=WEBHOOK_SECRET_TEST)
    def test_acreditada_por_billetera_registra_el_pago_como_billetera(self):
        """El medio de pago que se muestra en el historial sigue siendo el que eligió el cliente, no 'transferencia'."""
        self.solicitud.medio_pago = MetodoPago.TIPO_BILLETERA
        self.solicitud.save(update_fields=['medio_pago'])

        self._post({
            'id_operacion': 'SPI-BILL-001', 'referencia': self.solicitud.referencia, 'estado': 'acreditada',
            'monto': 747400, 'moneda': 'PYG', 'banco_origen': 'Tigo Money',
        })

        pago = Pago.objects.get(calculo_operacion=self.transaccion)
        self.assertEqual(pago.medio_pago, MetodoPago.TIPO_BILLETERA)

    @override_settings(SIPAP_WEBHOOK_SECRET=WEBHOOK_SECRET_TEST)
    def test_acreditada_con_monto_distinto_queda_observada_sin_marcar_pagada(self):
        """Criterio 3: con un monto distinto, el pago queda observado y la transacción sigue 'Confirmada'."""
        response = self._post({
            'referencia': self.solicitud.referencia, 'estado': 'acreditada',
            'id_operacion': 'SIPAP-OP-002', 'monto': '700000.00', 'banco_origen': 'Banco Itaú',
        })

        self.assertEqual(response.status_code, 200)
        self.transaccion.refresh_from_db()
        self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_CONFIRMADA)
        pago = Pago.objects.get(calculo_operacion=self.transaccion)
        self.assertTrue(pago.observado)
        self.assertEqual(pago.diferencia, Decimal('-47400.00'))
        self.assertEqual(pago.monto, Decimal('700000.00'))
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, SolicitudPagoSipap.ESTADO_OBSERVADA)

    @override_settings(SIPAP_WEBHOOK_SECRET=WEBHOOK_SECRET_TEST)
    def test_una_transferencia_que_no_se_concreta_no_crea_ningun_pago(self):
        """Criterio 5: rechazada (queda para reintentar) o sin saldo (se cancela directo); nunca se crea un Pago."""
        with self.subTest('rechazada por el cliente: queda igual, para reintentar'):
            response = self._post({'referencia': self.solicitud.referencia, 'estado': 'rechazada'})

            self.assertEqual(response.status_code, 200)
            self.assertEqual(Pago.objects.filter(calculo_operacion=self.transaccion).count(), 0)
            self.solicitud.refresh_from_db()
            self.assertEqual(self.solicitud.estado, SolicitudPagoSipap.ESTADO_RECHAZADA)
            self.transaccion.refresh_from_db()
            self.assertEqual(self.transaccion.estado, CalculoOperacion.ESTADO_CONFIRMADA)

        with self.subTest('sin saldo: a diferencia de rechazada, cancela la transacción directamente'):
            otra_solicitud = SolicitudPagoSipap.objects.create(
                calculo_operacion=CalculoOperacion.objects.create(
                    usuario=self.usuario, cliente=self.cliente, tipo=CalculoOperacion.TIPO_COMPRA,
                    divisa=self.usd, codigo_divisa='USD', monto_origen=Decimal('50.00'),
                    tasa_aplicada=Decimal('7400.00'), comision_porcentaje=Decimal('1.000'),
                    comision=Decimal('3700.00'), monto_final=Decimal('373700.00'),
                    estado=CalculoOperacion.ESTADO_CONFIRMADA, vence_en=timezone.now() + timedelta(seconds=300),
                    confirmado_en=timezone.now(),
                ),
                referencia='SIPAP-SALDO-INSUF-001', monto=Decimal('373700.00'), moneda='PYG',
                vence_en=timezone.now() + timedelta(hours=1), metodo_pago=self.metodo_pago,
            )

            response = self._post({'referencia': otra_solicitud.referencia, 'estado': 'saldo_insuficiente'})

            self.assertEqual(response.status_code, 200)
            self.assertEqual(Pago.objects.filter(calculo_operacion=otra_solicitud.calculo_operacion).count(), 0)
            otra_solicitud.refresh_from_db()
            self.assertEqual(otra_solicitud.estado, SolicitudPagoSipap.ESTADO_SALDO_INSUFICIENTE)
            otra_solicitud.calculo_operacion.refresh_from_db()
            self.assertEqual(
                otra_solicitud.calculo_operacion.estado, CalculoOperacion.ESTADO_CANCELADA_FONDOS_CLIENTE,
            )

    @override_settings(SIPAP_WEBHOOK_SECRET=WEBHOOK_SECRET_TEST)
    def test_entradas_invalidas_se_ignoran_sin_romper(self):
        """Una referencia desconocida, o un payload que no es JSON válido: se ignoran sin crear ni romper nada."""
        with self.subTest('referencia que no corresponde a ninguna solicitud'):
            response = self._post({'referencia': 'SIPAP-NO-EXISTE', 'estado': 'acreditada', 'monto': '1.00'})

            self.assertEqual(response.status_code, 200)
            self.assertEqual(Pago.objects.count(), 0)

        with self.subTest('payload que no es JSON válido, aunque la firma sea correcta'):
            payload = b'esto no es json'
            firma = _firmar(payload)

            response = self.client.post(
                self.url, data=payload, content_type='application/json', HTTP_X_SIPAP_SIGNATURE=firma,
            )

            self.assertEqual(response.status_code, 400)

    @override_settings(SIPAP_WEBHOOK_SECRET=WEBHOOK_SECRET_TEST)
    def test_el_mismo_evento_reenviado_no_duplica_el_pago(self):
        """La confirmación es idempotente: reenviar el mismo evento no crea un segundo pago."""
        datos = {
            'referencia': self.solicitud.referencia, 'estado': 'acreditada',
            'id_operacion': 'SIPAP-OP-003', 'monto': '747400.00',
        }
        self._post(datos)

        response = self._post(datos)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Pago.objects.filter(calculo_operacion=self.transaccion).count(), 1)

    def test_el_webhook_no_acepta_metodos_distintos_de_post(self):
        """La URL del webhook es exclusivamente para POST (sipap-sim nunca manda GET)."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405)
