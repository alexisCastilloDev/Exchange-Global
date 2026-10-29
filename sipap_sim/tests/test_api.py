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

from fixtures import DOCUMENTO_CLIENTE_PYG, NOMBRE_BANCO, NUMERO_CUENTA_CLIENTE_PYG, crear_banco_y_cuentas_pyg
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

    def test_rechaza_sin_token_o_con_token_incorrecto(self):
        with self.subTest('sin token'):
            response = self.client.post(reverse('crear_solicitud_cobro'), data={}, content_type='application/json')
            self.assertEqual(response.status_code, 401)

        with self.subTest('con token incorrecto'):
            response = self.client.post(
                reverse('crear_solicitud_cobro'), data={}, content_type='application/json',
                **_encabezado_auth(valido=False),
            )
            self.assertEqual(response.status_code, 401)

    def test_crea_transferencia_pendiente_con_o_sin_cuenta_de_origen_identificada(self):
        with self.subTest('sin cuenta de origen'):
            payload = {
                'monto': 1500000, 'moneda': 'PYG', 'referencia': 'GE-152-A3F9C1', 'url_retorno': 'http://ge.test/retorno',
            }
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

        with self.subTest('con cuenta de origen: queda reconocida de entrada'):
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

    def test_rechaza_payload_invalido_o_cuenta_de_origen_inexistente(self):
        with self.subTest('payload inválido'):
            response = self.client.post(
                reverse('crear_solicitud_cobro'), data=json.dumps({'moneda': 'PYG'}), content_type='application/json',
                **_encabezado_auth(),
            )
            self.assertEqual(response.status_code, 400)

        with self.subTest('cuenta de origen indicada no existe'):
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

    def test_sim_modo_falla_error_o_lento(self):
        payload = {'monto': 100, 'moneda': 'PYG', 'referencia': 'GE-1', 'url_retorno': ''}

        with self.subTest('error: responde 500'), self.settings(SIM_MODO_FALLA='error'):
            response = self.client.post(
                reverse('crear_solicitud_cobro'), data=json.dumps(payload), content_type='application/json',
                **_encabezado_auth(),
            )
            self.assertEqual(response.status_code, 500)

        with self.subTest('lento: duerme antes de responder'), self.settings(SIM_MODO_FALLA='lento'):
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

    def test_devuelve_el_estado_actual_o_404_si_no_existe(self):
        with self.subTest('existe'):
            response = self.client.get(
                reverse('consultar_transferencia', args=[self.transferencia.id]), **_encabezado_auth(),
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['estado'], Transferencia.ESTADO_PENDIENTE)

        with self.subTest('no existe'):
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

    def test_valida_segun_coincidan_o_no_numero_y_documento(self):
        with self.subTest('coinciden'):
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
            self.assertEqual(Decimal(datos['saldo']), Decimal('15000000.00'))

        with self.subTest('no coinciden'):
            response = self.client.get(
                reverse('validar_cuenta'), {'numero': NUMERO_CUENTA_CLIENTE_PYG, 'documento': 'otro'}, **_encabezado_auth(),
            )
            self.assertEqual(response.json(), {'valida': False})


@override_settings(SIPAP_API_KEY=API_KEY_TEST)
class ConsultarSaldoCasaDeCambioTest(TestCase):
    """``GET /api/casa-de-cambio/<moneda>/``."""

    def setUp(self):
        self.casa_pyg, _ = crear_banco_y_cuentas_pyg()

    def test_rechaza_sin_token(self):
        response = self.client.get(reverse('consultar_saldo_casa_de_cambio', args=['PYG']))
        self.assertEqual(response.status_code, 401)

    def test_devuelve_el_saldo_si_existe_la_cuenta_o_404_si_no(self):
        with self.subTest('existe'):
            response = self.client.get(
                reverse('consultar_saldo_casa_de_cambio', args=['PYG']), **_encabezado_auth(),
            )
            self.assertEqual(response.status_code, 200)
            datos = response.json()
            self.assertEqual(datos['moneda'], 'PYG')
            self.assertEqual(Decimal(datos['saldo']), self.casa_pyg.saldo)

        with self.subTest('no existe en esa moneda'):
            response = self.client.get(
                reverse('consultar_saldo_casa_de_cambio', args=['USD']), **_encabezado_auth(),
            )
            self.assertEqual(response.status_code, 404)


@override_settings(SIPAP_API_KEY=API_KEY_TEST)
class ConsultarCuentaCasaDeCambioTest(TestCase):
    """``GET /api/casa-de-cambio/<moneda>/cuenta/``."""

    def setUp(self):
        self.casa_pyg, _ = crear_banco_y_cuentas_pyg()

    def test_rechaza_sin_token(self):
        response = self.client.get(reverse('consultar_cuenta_casa_de_cambio', args=['PYG']))
        self.assertEqual(response.status_code, 401)

    def test_devuelve_los_datos_de_la_cuenta_designada_o_404_si_no_hay_ninguna(self):
        with self.subTest('hay una designada'):
            response = self.client.get(reverse('consultar_cuenta_casa_de_cambio', args=['PYG']), **_encabezado_auth())
            self.assertEqual(response.status_code, 200)
            datos = response.json()
            self.assertEqual(datos['numero'], self.casa_pyg.numero)
            self.assertEqual(datos['titular'], self.casa_pyg.titular)
            self.assertEqual(datos['proveedor'], NOMBRE_BANCO)

        with self.subTest('no hay ninguna en esa moneda'):
            response = self.client.get(reverse('consultar_cuenta_casa_de_cambio', args=['USD']), **_encabezado_auth())
            self.assertEqual(response.status_code, 404)


@override_settings(SIPAP_API_KEY=API_KEY_TEST)
class DesignarCuentaCasaDeCambioTest(TestCase):
    """``POST /api/casa-de-cambio/<moneda>/designar/``: Global Exchange designa la cuenta, no sipap-sim."""

    def setUp(self):
        self.casa_pyg, self.cliente_pyg = crear_banco_y_cuentas_pyg()

    def test_rechaza_sin_token(self):
        response = self.client.post(
            reverse('designar_cuenta_casa_de_cambio', args=['PYG']), data={}, content_type='application/json',
        )
        self.assertEqual(response.status_code, 401)

    def test_designa_una_cuenta_de_cliente_como_la_casa_de_cambio(self):
        """Antes de designarla, es una cuenta común; después, queda marcada y la anterior pierde la marca."""
        payload = {'numero': NUMERO_CUENTA_CLIENTE_PYG, 'documento': DOCUMENTO_CLIENTE_PYG}
        response = self.client.post(
            reverse('designar_cuenta_casa_de_cambio', args=['PYG']), data=json.dumps(payload),
            content_type='application/json', **_encabezado_auth(),
        )

        self.assertEqual(response.status_code, 200)
        datos = response.json()
        self.assertEqual(datos['numero'], NUMERO_CUENTA_CLIENTE_PYG)
        self.cliente_pyg.refresh_from_db()
        self.casa_pyg.refresh_from_db()
        self.assertTrue(self.cliente_pyg.es_cuenta_casa_de_cambio)
        self.assertFalse(self.casa_pyg.es_cuenta_casa_de_cambio)

    def test_rechaza_cuenta_inexistente_de_otra_moneda_o_payload_invalido(self):
        with self.subTest('no existe una cuenta con ese número y documento'):
            payload = {'numero': '0000000000000000', 'documento': '0000000'}
            response = self.client.post(
                reverse('designar_cuenta_casa_de_cambio', args=['PYG']), data=json.dumps(payload),
                content_type='application/json', **_encabezado_auth(),
            )
            self.assertEqual(response.status_code, 404)

        with self.subTest('la cuenta es de otra moneda'):
            payload = {'numero': self.casa_pyg.numero, 'documento': self.casa_pyg.documento}
            response = self.client.post(
                reverse('designar_cuenta_casa_de_cambio', args=['USD']), data=json.dumps(payload),
                content_type='application/json', **_encabezado_auth(),
            )
            self.assertEqual(response.status_code, 400)
            self.casa_pyg.refresh_from_db()
            self.assertTrue(self.casa_pyg.es_cuenta_casa_de_cambio)

        with self.subTest('payload inválido'):
            response = self.client.post(
                reverse('designar_cuenta_casa_de_cambio', args=['PYG']), data=json.dumps({'numero': 'solo-numero'}),
                content_type='application/json', **_encabezado_auth(),
            )
            self.assertEqual(response.status_code, 400)


@override_settings(SIPAP_API_KEY=API_KEY_TEST)
class ConsultarMovimientosCasaDeCambioTest(TestCase):
    """``GET /api/casa-de-cambio/<moneda>/movimientos/``."""

    def setUp(self):
        self.casa_pyg, self.cliente_pyg = crear_banco_y_cuentas_pyg()

    def test_rechaza_sin_token(self):
        response = self.client.get(reverse('consultar_movimientos_casa_de_cambio', args=['PYG']))
        self.assertEqual(response.status_code, 401)

    def test_una_entrada_o_una_salida_aparecen_con_su_direccion(self):
        with self.subTest('un cobro pendiente aparece como entrada'):
            Transferencia.objects.create(
                cuenta_destino=self.casa_pyg, monto_solicitado=Decimal('1000'), moneda='PYG',
                referencia='GE-MOV-1', vence_en='2099-01-01T00:00:00Z',
            )

            response = self.client.get(
                reverse('consultar_movimientos_casa_de_cambio', args=['PYG']), **_encabezado_auth(),
            )

            self.assertEqual(response.status_code, 200)
            datos = response.json()
            self.assertEqual(datos['moneda'], 'PYG')
            self.assertEqual(len(datos['movimientos']), 1)
            self.assertEqual(datos['movimientos'][0]['direccion'], 'entrada')
            self.assertEqual(datos['movimientos'][0]['referencia'], 'GE-MOV-1')
            self.assertEqual(Decimal(datos['movimientos'][0]['monto_solicitado']), Decimal('1000'))

        with self.subTest('una salida acreditada aparece como salida, con la contraparte'):
            payload = {
                'cuenta_destino': NUMERO_CUENTA_CLIENTE_PYG, 'documento': DOCUMENTO_CLIENTE_PYG,
                'monto': 5000, 'referencia': 'GE-MOV-2',
            }
            self.client.post(
                reverse('crear_transferencia_saliente'), data=json.dumps(payload), content_type='application/json',
                **_encabezado_auth(),
            )

            response = self.client.get(
                reverse('consultar_movimientos_casa_de_cambio', args=['PYG']), **_encabezado_auth(),
            )

            datos = response.json()
            salida = next(m for m in datos['movimientos'] if m['referencia'] == 'GE-MOV-2')
            self.assertEqual(salida['direccion'], 'salida')
            self.assertEqual(salida['contraparte'], 'Juan Pérez')
            self.assertEqual(salida['estado'], Transferencia.ESTADO_ACREDITADA)

    def test_no_mezcla_movimientos_de_otra_moneda(self):
        Transferencia.objects.create(
            cuenta_destino=self.casa_pyg, monto_solicitado=Decimal('1000'), moneda='PYG',
            referencia='GE-MOV-PYG', vence_en='2099-01-01T00:00:00Z',
        )

        response = self.client.get(
            reverse('consultar_movimientos_casa_de_cambio', args=['USD']), **_encabezado_auth(),
        )

        self.assertEqual(response.json()['movimientos'], [])

    def test_respeta_el_limite_pedido(self):
        for indice in range(3):
            Transferencia.objects.create(
                cuenta_destino=self.casa_pyg, monto_solicitado=Decimal('1000'), moneda='PYG',
                referencia=f'GE-MOV-LIMITE-{indice}', vence_en='2099-01-01T00:00:00Z',
            )

        response = self.client.get(
            reverse('consultar_movimientos_casa_de_cambio', args=['PYG']), {'limite': 2}, **_encabezado_auth(),
        )

        self.assertEqual(len(response.json()['movimientos']), 2)


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

    def test_una_referencia_repetida_no_mueve_el_saldo_dos_veces(self):
        payload = {
            'cuenta_destino': NUMERO_CUENTA_CLIENTE_PYG, 'documento': DOCUMENTO_CLIENTE_PYG,
            'monto': 50000, 'referencia': 'GE-9',
        }
        primera = self.client.post(
            reverse('crear_transferencia_saliente'), data=json.dumps(payload), content_type='application/json',
            **_encabezado_auth(),
        )
        self.assertEqual(primera.status_code, 201)

        saldo_casa_tras_primera = Cuenta.objects.get(pk=self.casa.pk).saldo
        saldo_cliente_tras_primera = Cuenta.objects.get(pk=self.cliente.pk).saldo

        segunda = self.client.post(
            reverse('crear_transferencia_saliente'), data=json.dumps(payload), content_type='application/json',
            **_encabezado_auth(),
        )
        self.assertEqual(segunda.status_code, 200)
        self.assertEqual(segunda.json()['id'], primera.json()['id'])

        self.assertEqual(Cuenta.objects.get(pk=self.casa.pk).saldo, saldo_casa_tras_primera)
        self.assertEqual(Cuenta.objects.get(pk=self.cliente.pk).saldo, saldo_cliente_tras_primera)
        self.assertEqual(Transferencia.objects.filter(referencia='GE-9').count(), 1)
