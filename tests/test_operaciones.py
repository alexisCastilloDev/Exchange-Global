"""Pruebas del cálculo de importes para compra y venta de divisas."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.divisas.models import CalculoOperacion, Cotizacion, Divisa


User = get_user_model()


class CalculoOperacionTest(TestCase):
    """Verifica tasas, comisión, errores de cotización y vencimiento."""

    def setUp(self):
        """Prepara un analista cambiario autenticado y una divisa cotizada."""
        self.usuario = User.objects.create_user(
            username='analista-operaciones',
            password='password123',
        )
        self.client.login(username='analista-operaciones', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['analista_cambiario']
        session.save()
        self.usd = Divisa.objects.create(
            codigo='USD',
            nombre='Dólar',
            simbolo='$',
            activa=True,
        )
        Cotizacion.objects.create(
            divisa=self.usd,
            tasa_compra=Decimal('7300.00'),
            tasa_venta=Decimal('7400.00'),
        )

    def test_compra_usa_tasa_venta_y_suma_comision(self):
        """Calcula compra con tasa de venta y comisión separada."""
        response = self.client.post(
            reverse('divisas:operar', kwargs={'tipo': 'compra'}),
            {'tipo': 'COMPRA', 'divisa': str(self.usd.pk), 'monto': '100'},
        )

        calculo = CalculoOperacion.objects.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calculo.tasa_aplicada, Decimal('7400.00'))
        self.assertEqual(calculo.comision, Decimal('7400.00'))
        self.assertEqual(calculo.monto_final, Decimal('747400.00'))
        self.assertContains(response, '747400.00')
        self.assertContains(response, '7400.00')

    def test_venta_usa_tasa_compra_y_resta_comision(self):
        """Calcula venta con tasa de compra y descuenta la comisión."""
        response = self.client.post(
            reverse('divisas:operar', kwargs={'tipo': 'venta'}),
            {'tipo': 'VENTA', 'divisa': str(self.usd.pk), 'monto': '100'},
        )

        calculo = CalculoOperacion.objects.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calculo.tasa_aplicada, Decimal('7300.00'))
        self.assertEqual(calculo.comision, Decimal('7300.00'))
        self.assertEqual(calculo.monto_final, Decimal('722700.00'))
        self.assertContains(response, 'Importe a recibir')

    def test_divisa_sin_cotizacion_impide_calcular(self):
        """Muestra error y no crea cálculo cuando falta una cotización."""
        sin_cotizacion = Divisa.objects.create(
            codigo='BRL',
            nombre='Real',
            simbolo='R$',
            activa=True,
        )
        response = self.client.post(
            reverse('divisas:operar', kwargs={'tipo': 'compra'}),
            {'tipo': 'COMPRA', 'divisa': str(sin_cotizacion.pk), 'monto': '100'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CalculoOperacion.objects.exists())
        self.assertContains(response, 'no tiene cotización disponible')

    def test_calculo_vencido_debe_recalcularse_antes_de_confirmar(self):
        """Rechaza confirmación cuando el cálculo ya superó su vigencia."""
        calculo = CalculoOperacion.objects.create(
            usuario=self.usuario,
            tipo=CalculoOperacion.TIPO_COMPRA,
            divisa=self.usd,
            codigo_divisa='USD',
            monto_origen=Decimal('100.00'),
            tasa_aplicada=Decimal('7400.00'),
            comision_porcentaje=Decimal('1.000'),
            comision=Decimal('7400.00'),
            monto_final=Decimal('747400.00'),
            vence_en=timezone.now() - timedelta(seconds=1),
        )

        response = self.client.post(
            reverse('divisas:confirmar_operacion', kwargs={'calculo_id': calculo.pk}),
            follow=True,
        )

        calculo.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(calculo.confirmado_en)
        self.assertContains(response, 'El cálculo venció')

    def test_menu_expone_compra_y_venta(self):
        """Muestra ambos accesos operativos en el menú autenticado."""
        response = self.client.get(reverse('home'))

        self.assertContains(response, reverse('divisas:operar', kwargs={'tipo': 'compra'}))
        self.assertContains(response, reverse('divisas:operar', kwargs={'tipo': 'venta'}))
