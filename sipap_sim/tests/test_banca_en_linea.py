"""Pruebas de la 'banca en línea' simulada (``core.views.elegir_cuenta_view``).

Usan los datos de prueba cargados por la migración
``core.migrations.0002_datos_iniciales``, igual que ``test_api.py``.
"""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Cuenta, Transferencia

NUMERO_CUENTA_CLIENTE_PYG = '2000000000000101'


class ElegirCuentaViewTest(TestCase):
    """Aprobar o rechazar con la cuenta que ya identificó quien pidió el cobro."""

    def setUp(self):
        self.casa = Cuenta.objects.get(es_cuenta_casa_de_cambio=True, moneda='PYG')
        self.cuenta_cliente = Cuenta.objects.get(numero=NUMERO_CUENTA_CLIENTE_PYG)
        self.saldo_cliente_inicial = self.cuenta_cliente.saldo
        self.saldo_casa_inicial = self.casa.saldo
        self.transferencia = Transferencia.objects.create(
            cuenta_sugerida=self.cuenta_cliente, cuenta_destino=self.casa,
            monto_solicitado=Decimal('500000'), moneda='PYG',
            referencia='GE-1', url_retorno='http://ge.test/retorno',
            vence_en=timezone.now() + timezone.timedelta(hours=1),
        )
        self.url = reverse('elegir_cuenta', args=[self.transferencia.id])

    def test_muestra_la_cuenta_identificada_y_su_saldo(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.cuenta_cliente.numero)
        # El template localiza el Decimal (coma en vez de punto): se busca
        # solo la parte entera, para no depender de ese formato exacto.
        self.assertContains(response, str(int(self.cuenta_cliente.saldo)))

    @patch('core.webhooks.requests.post')
    def test_aprobar_mueve_saldo_y_redirige_a_url_retorno(self, post_mock):
        response = self.client.post(self.url, {'accion': 'aprobar'})
        self.assertRedirects(response, 'http://ge.test/retorno', fetch_redirect_response=False)

        self.transferencia.refresh_from_db()
        self.cuenta_cliente.refresh_from_db()
        self.casa.refresh_from_db()
        self.assertEqual(self.transferencia.estado, Transferencia.ESTADO_ACREDITADA)
        self.assertEqual(self.transferencia.cuenta_origen, self.cuenta_cliente)
        self.assertEqual(self.transferencia.monto_acreditado, Decimal('500000'))
        self.assertEqual(self.cuenta_cliente.saldo, self.saldo_cliente_inicial - Decimal('500000'))
        self.assertEqual(self.casa.saldo, self.saldo_casa_inicial + Decimal('500000'))
        post_mock.assert_called_once()

    @patch('core.webhooks.requests.post')
    def test_aprobar_ignora_cualquier_monto_que_mande_el_cliente(self, post_mock):
        """El cliente no elige ningún monto: se acredita siempre el solicitado, aunque mande otro."""
        self.client.post(self.url, {'accion': 'aprobar', 'monto': '1'})

        self.transferencia.refresh_from_db()
        self.assertEqual(self.transferencia.monto_acreditado, Decimal('500000'))

    @patch('core.webhooks.requests.post')
    def test_rechazar_no_mueve_saldo(self, post_mock):
        response = self.client.post(self.url, {'accion': 'rechazar'})
        self.assertRedirects(response, 'http://ge.test/retorno', fetch_redirect_response=False)

        self.transferencia.refresh_from_db()
        self.cuenta_cliente.refresh_from_db()
        self.assertEqual(self.transferencia.estado, Transferencia.ESTADO_RECHAZADA)
        self.assertEqual(self.cuenta_cliente.saldo, self.saldo_cliente_inicial)
        post_mock.assert_called_once()

    def test_no_permite_aprobar_con_saldo_insuficiente(self):
        """Si el monto solicitado supera el saldo de la cuenta identificada, se informa sin aprobar."""
        transferencia_cara = Transferencia.objects.create(
            cuenta_sugerida=self.cuenta_cliente, cuenta_destino=self.casa,
            monto_solicitado=self.saldo_cliente_inicial + Decimal('1'), moneda='PYG',
            referencia='GE-CARA', vence_en=timezone.now() + timezone.timedelta(hours=1),
        )

        response = self.client.post(
            reverse('elegir_cuenta', args=[transferencia_cara.id]), {'accion': 'aprobar'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Saldo insuficiente')
        transferencia_cara.refresh_from_db()
        self.assertEqual(transferencia_cara.estado, Transferencia.ESTADO_PENDIENTE)

    def test_una_transferencia_ya_resuelta_no_se_puede_volver_a_aprobar(self):
        self.transferencia.estado = Transferencia.ESTADO_ACREDITADA
        self.transferencia.save(update_fields=['estado'])

        response = self.client.get(self.url)
        self.assertNotContains(response, '<form')

    def test_una_transferencia_vencida_se_marca_como_tal_al_visitarla(self):
        self.transferencia.vence_en = timezone.now() - timezone.timedelta(seconds=1)
        self.transferencia.save(update_fields=['vence_en'])

        self.client.get(self.url)

        self.transferencia.refresh_from_db()
        self.assertEqual(self.transferencia.estado, Transferencia.ESTADO_VENCIDA)

    def test_sin_cuenta_sugerida_no_muestra_ninguna_cuenta_del_sistema(self):
        """Sin una cuenta identificada, no se le ofrece al cliente elegir entre todas las del sistema."""
        transferencia_sin_cuenta = Transferencia.objects.create(
            cuenta_destino=self.casa, monto_solicitado=Decimal('1000'), moneda='PYG',
            referencia='GE-2', vence_en=timezone.now() + timezone.timedelta(hours=1),
        )

        response = self.client.get(reverse('elegir_cuenta', args=[transferencia_sin_cuenta.id]))

        self.assertEqual(response.status_code, 409)
        self.assertNotContains(response, self.cuenta_cliente.numero, status_code=409)
        self.assertNotContains(response, '<form', status_code=409)
