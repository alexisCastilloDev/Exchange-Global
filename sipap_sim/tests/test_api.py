"""Pruebas de la API de sipap-sim que consume Global Exchange.

El banco, la cuenta de la casa de cambio y la cuenta de cliente que
necesitan se crean en cada ``setUp`` con ``fixtures.crear_banco_y_cuentas_pyg``
(ver ese módulo): ya no vienen de una migración de datos, sino del panel
administrativo en cualquier entorno real.
"""

import json
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from fixtures import DOCUMENTO_CLIENTE_PYG, NUMERO_CUENTA_CLIENTE_PYG, crear_banco_y_cuentas_pyg
from core.models import Cuenta, Transferencia

API_KEY_TEST = 'api-key-de-test'


def _encabezado_auth(valido=True):
    token = API_KEY_TEST if valido else 'token-incorrecto'
    return {'HTTP_AUTHORIZATION': f'Bearer {token}'}


@override_settings(SIPAP_API_KEY=API_KEY_TEST)
class CrearSolicitudCobroTest(TestCase):
    """``POST /api/solicitudes-cobro/``."""

    def setUp(self):
        self.casa_pyg, self.cliente_pyg = crear_banco_y_cuentas_pyg()

    def test_rechaza_sin_token(self):
        response = self.client.post(reverse('crear_solicitud_cobro'), data={}, content_type='application/json')
        self.assertEqual(response.status_code, 401)

    def test_rechaza_con_token_incorrecto(self):
        response = self.client.post(
            reverse('crear_solicitud_cobro'), data={}, content_type='application/json',
            **_encabezado_auth(valido=False),
        )
        self.assertEqual(response.status_code, 401)

    def test_crea_transferencia_pendiente_y_devuelve_link_de_pago(self):
        payload = {'monto': 1500000, 'moneda': 'PYG', 'referencia': 'GE-152-A3F9C1', 'url_retorno': 'http://ge.test/retorno'}
        response = self.client.post(
            reverse('crear_solicitud_cobro'), data=json.dumps(payload), content_type='application/json',
            **_encabezado_auth(),
        )
        self.assertEqual(response.status_code, 201)
        datos = response.json()
        self.assertIn('id', datos)
        self.assertIn(datos['id'], datos['link_pago'])

        transferencia = Transferencia.objects.get(pk=datos['id'])
        self.assertEqual(transferencia.estado, Transferencia.ESTADO_PENDIENTE)
        self.assertEqual(transferencia.monto_solicitado, Decimal('1500000'))
        self.assertEqual(transferencia.cuenta_destino, self.casa_pyg)
        self.assertIsNone(transferencia.cuenta_origen)

    def test_rechaza_payload_invalido(self):
        response = self.client.post(
            reverse('crear_solicitud_cobro'), data=json.dumps({'moneda': 'PYG'}), content_type='application/json',
            **_encabezado_auth(),
        )
        self.assertEqual(response.status_code, 400)

    def test_con_cuenta_de_origen_la_identifica_como_cuenta_sugerida(self):
        """Si Global Exchange manda el método de pago elegido, queda reconocido de entrada."""
        payload = {
            'monto': 1500000, 'moneda': 'PYG', 'referencia': 'GE-2', 'url_retorno': '',
            'cuenta_origen_numero': NUMERO_CUENTA_CLIENTE_PYG, 'cuenta_origen_documento': DOCUMENTO_CLIENTE_PYG,
        }
        response = self.client.post(
            reverse('crear_solicitud_cobro'), data=json.dumps(payload), content_type='application/json',
            **_encabezado_auth(),
        )
        self.assertEqual(response.status_code, 201)
        transferencia = Transferencia.objects.get(pk=response.json()['id'])
        self.assertEqual(transferencia.cuenta_sugerida, Cuenta.objects.get(numero=NUMERO_CUENTA_CLIENTE_PYG))

    def test_rechaza_si_la_cuenta_de_origen_indicada_no_existe(self):
        payload = {
            'monto': 1500000, 'moneda': 'PYG', 'referencia': 'GE-3', 'url_retorno': '',
            'cuenta_origen_numero': '0000000000000000', 'cuenta_origen_documento': '0000000',
        }
        response = self.client.post(
            reverse('crear_solicitud_cobro'), data=json.dumps(payload), content_type='application/json',
            **_encabezado_auth(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Transferencia.objects.filter(referencia='GE-3').exists())

    @override_settings(SIM_MODO_FALLA='error')
    def test_sim_modo_falla_error_devuelve_500(self):
        payload = {'monto': 100, 'moneda': 'PYG', 'referencia': 'GE-1', 'url_retorno': ''}
        response = self.client.post(
            reverse('crear_solicitud_cobro'), data=json.dumps(payload), content_type='application/json',
            **_encabezado_auth(),
        )
        self.assertEqual(response.status_code, 500)

    @override_settings(SIM_MODO_FALLA='lento')
    def test_sim_modo_falla_lento_duerme_antes_de_responder(self):
        payload = {'monto': 100, 'moneda': 'PYG', 'referencia': 'GE-1', 'url_retorno': ''}
        with patch('core.views.time.sleep') as sleep_mock:
            response = self.client.post(
                reverse('crear_solicitud_cobro'), data=json.dumps(payload), content_type='application/json',
                **_encabezado_auth(),
            )
        sleep_mock.assert_called_once()
        self.assertEqual(response.status_code, 201)


@override_settings(SIPAP_API_KEY=API_KEY_TEST)
class ConsultarTransferenciaTest(TestCase):
    """``GET /api/transferencias/<id>/``."""

    def setUp(self):
        casa, _ = crear_banco_y_cuentas_pyg()
        self.transferencia = Transferencia.objects.create(
            cuenta_destino=casa, monto_solicitado=Decimal('1000'), moneda='PYG',
            referencia='GE-1', vence_en='2099-01-01T00:00:00Z',
        )

    def test_rechaza_sin_token(self):
        response = self.client.get(reverse('consultar_transferencia', args=[self.transferencia.id]))
        self.assertEqual(response.status_code, 401)

    def test_devuelve_el_estado_actual(self):
        response = self.client.get(
            reverse('consultar_transferencia', args=[self.transferencia.id]), **_encabezado_auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['estado'], Transferencia.ESTADO_PENDIENTE)

    def test_404_si_no_existe(self):
        response = self.client.get(reverse('consultar_transferencia', args=['SPI-NO-EXISTE']), **_encabezado_auth())
        self.assertEqual(response.status_code, 404)


@override_settings(SIPAP_API_KEY=API_KEY_TEST)
class ValidarCuentaTest(TestCase):
    """``GET /api/cuentas/validar/``."""

    def setUp(self):
        crear_banco_y_cuentas_pyg()

    def test_rechaza_sin_token(self):
        response = self.client.get(reverse('validar_cuenta'))
        self.assertEqual(response.status_code, 401)

    def test_valida_true_si_numero_y_documento_coinciden(self):
        response = self.client.get(
            reverse('validar_cuenta'),
            {'numero': NUMERO_CUENTA_CLIENTE_PYG, 'documento': DOCUMENTO_CLIENTE_PYG},
            **_encabezado_auth(),
        )
        datos = response.json()
        self.assertTrue(datos['valida'])
        self.assertEqual(datos['titular'], 'Juan Pérez')
        self.assertEqual(datos['proveedor'], 'Banco Itaú Paraguay')
        self.assertEqual(datos['tipo_proveedor'], 'BANCO')
        self.assertEqual(datos['moneda'], 'PYG')

    def test_valida_false_si_no_coinciden(self):
        response = self.client.get(
            reverse('validar_cuenta'), {'numero': NUMERO_CUENTA_CLIENTE_PYG, 'documento': 'otro'}, **_encabezado_auth(),
        )
        self.assertEqual(response.json(), {'valida': False})


@override_settings(SIPAP_API_KEY=API_KEY_TEST)
class CrearTransferenciaSalienteTest(TestCase):
    """``POST /api/transferencias/`` (acreditación a un cliente, Sprint 5)."""

    def setUp(self):
        self.casa, self.cliente = crear_banco_y_cuentas_pyg()

    def test_acredita_de_inmediato_y_mueve_saldo(self):
        saldo_casa_inicial = self.casa.saldo
        saldo_cliente_inicial = self.cliente.saldo

        payload = {
            'cuenta_destino': NUMERO_CUENTA_CLIENTE_PYG, 'documento': DOCUMENTO_CLIENTE_PYG,
            'monto': 50000, 'referencia': 'GE-9',
        }
        response = self.client.post(
            reverse('crear_transferencia_saliente'), data=json.dumps(payload), content_type='application/json',
            **_encabezado_auth(),
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['estado'], Transferencia.ESTADO_ACREDITADA)

        self.casa.refresh_from_db()
        self.cliente.refresh_from_db()
        self.assertEqual(self.casa.saldo, saldo_casa_inicial - Decimal('50000'))
        self.assertEqual(self.cliente.saldo, saldo_cliente_inicial + Decimal('50000'))

    def test_404_si_no_existe_cuenta_con_ese_numero_y_documento(self):
        payload = {
            'cuenta_destino': NUMERO_CUENTA_CLIENTE_PYG, 'documento': 'otro',
            'monto': 50000, 'referencia': 'GE-9',
        }
        response = self.client.post(
            reverse('crear_transferencia_saliente'), data=json.dumps(payload), content_type='application/json',
            **_encabezado_auth(),
        )
        self.assertEqual(response.status_code, 404)
