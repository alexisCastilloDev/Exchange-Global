"""Pruebas de la firma y el envío del webhook a Global Exchange."""

import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import Cuenta, Transferencia
from core.webhooks import enviar_confirmacion

WEBHOOK_SECRET_TEST = 'secreto-de-test'
NUMERO_CUENTA_CLIENTE_PYG = '2000000000000101'


@override_settings(SIPAP_WEBHOOK_SECRET=WEBHOOK_SECRET_TEST, GLOBAL_EXCHANGE_WEBHOOK_URL='http://ge.test/webhooks/sipap/')
class EnviarConfirmacionTest(TestCase):
    """``core.webhooks.enviar_confirmacion``."""

    def setUp(self):
        casa = Cuenta.objects.get(es_cuenta_casa_de_cambio=True, moneda='PYG')
        cuenta_cliente = Cuenta.objects.get(numero=NUMERO_CUENTA_CLIENTE_PYG)
        self.transferencia = Transferencia.objects.create(
            cuenta_origen=cuenta_cliente, cuenta_destino=casa,
            monto_solicitado=Decimal('1500000'), monto_acreditado=Decimal('1500000'),
            moneda='PYG', referencia='GE-152-A3F9C1', estado=Transferencia.ESTADO_ACREDITADA,
            resuelto_en=timezone.now(), vence_en=timezone.now(),
        )

    @patch('core.webhooks.requests.post')
    def test_el_cuerpo_sigue_el_formato_esperado_por_global_exchange(self, post_mock):
        enviar_confirmacion(self.transferencia)

        post_mock.assert_called_once()
        _, kwargs = post_mock.call_args
        self.assertEqual(kwargs['headers']['Content-Type'], 'application/json')

        cuerpo = json.loads(kwargs['data'])
        self.assertEqual(cuerpo['id_operacion'], self.transferencia.id)
        self.assertEqual(cuerpo['referencia'], 'GE-152-A3F9C1')
        self.assertEqual(cuerpo['estado'], 'acreditada')
        self.assertEqual(cuerpo['monto'], 1500000.0)
        self.assertEqual(cuerpo['moneda'], 'PYG')
        self.assertEqual(cuerpo['banco_origen'], self.transferencia.cuenta_origen.proveedor.nombre)

    @patch('core.webhooks.requests.post')
    def test_la_firma_es_un_hmac_sha256_valido_del_cuerpo(self, post_mock):
        enviar_confirmacion(self.transferencia)

        _, kwargs = post_mock.call_args
        firma_esperada = hmac.new(
            WEBHOOK_SECRET_TEST.encode('utf-8'), kwargs['data'], hashlib.sha256,
        ).hexdigest()
        self.assertEqual(kwargs['headers']['X-Sipap-Signature'], firma_esperada)

    @patch('core.webhooks.requests.post')
    def test_una_falla_de_red_no_rompe_el_llamador(self, post_mock):
        import requests
        post_mock.side_effect = requests.exceptions.ConnectionError('caído')
        enviar_confirmacion(self.transferencia)
