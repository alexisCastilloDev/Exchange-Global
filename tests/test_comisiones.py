"""Pruebas de la comisión configurable por segmento y por cliente."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.clientes.models import Cliente
from apps.divisas.models import ConfiguracionComision, Cotizacion, Divisa

User = get_user_model()


class ConfiguracionComisionResolucionTest(TestCase):
    """Verifica la prioridad de resolución del porcentaje de comisión."""

    def test_usa_el_valor_por_defecto_sin_cliente(self):
        """Sin cliente, se usa el porcentaje por defecto de settings."""
        from django.conf import settings

        porcentaje = ConfiguracionComision.porcentaje_para(None)

        self.assertEqual(porcentaje, Decimal(str(settings.COMISION_OPERACION_PORCENTAJE)))

    def test_usa_la_comision_del_segmento_configurado(self):
        """Si el segmento tiene una configuración, se usa ese porcentaje."""
        cliente = Cliente.objects.create(
            identificador='CI-COM-001',
            nombre='Cliente',
            apellido='Minorista',
            email='minorista@test.com',
            segmento='MINORISTA',
        )
        ConfiguracionComision.objects.create(segmento='MINORISTA', porcentaje=Decimal('2.500'))

        porcentaje = ConfiguracionComision.porcentaje_para(cliente)

        self.assertEqual(porcentaje, Decimal('2.500'))

    def test_comision_personalizada_prevalece_sobre_el_segmento(self):
        """La comisión personalizada del cliente tiene prioridad sobre su segmento."""
        cliente = Cliente.objects.create(
            identificador='CI-COM-002',
            nombre='Cliente',
            apellido='VIP',
            email='vip@test.com',
            segmento='VIP',
            comision_personalizada=Decimal('0.250'),
        )
        ConfiguracionComision.objects.create(segmento='VIP', porcentaje=Decimal('1.500'))

        porcentaje = ConfiguracionComision.porcentaje_para(cliente)

        self.assertEqual(porcentaje, Decimal('0.250'))


class ConfiguracionComisionVistaTest(TestCase):
    """Verifica el acceso y la edición de la comisión por segmento."""

    def setUp(self):
        """Prepara un usuario administrador."""
        self.admin = User.objects.create_user(username='admin-comisiones', password='password123')
        self.client.login(username='admin-comisiones', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

    def test_cliente_no_puede_acceder_a_configurar_comisiones(self):
        """Un rol cliente no puede ver ni editar la configuración de comisiones."""
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response = self.client.get(reverse('divisas:comisiones'))

        self.assertEqual(response.status_code, 403)

    def test_administrador_configura_comision_de_un_segmento(self):
        """El administrador puede crear la comisión de un segmento sin configurar."""
        response = self.client.post(
            reverse('divisas:actualizar_comision', kwargs={'segmento': 'CORPORATIVO'}),
            {'porcentaje': '0.800'},
        )

        self.assertRedirects(response, reverse('divisas:comisiones'))
        configuracion = ConfiguracionComision.objects.get(segmento='CORPORATIVO')
        self.assertEqual(configuracion.porcentaje, Decimal('0.800'))
        self.assertEqual(configuracion.actualizado_por, self.admin)

    def test_analista_cambiario_tambien_puede_configurar_comisiones(self):
        """El rol analista_cambiario tiene el mismo acceso que admin."""
        session = self.client.session
        session['keycloak_roles'] = ['analista_cambiario']
        session.save()

        response = self.client.get(reverse('divisas:comisiones'))

        self.assertEqual(response.status_code, 200)

    def test_rechaza_comision_negativa(self):
        """No permite configurar un porcentaje de comisión negativo."""
        response = self.client.post(
            reverse('divisas:actualizar_comision', kwargs={'segmento': 'MINORISTA'}),
            {'porcentaje': '-1'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ConfiguracionComision.objects.filter(segmento='MINORISTA').exists())


class ComisionEnCalculoOperacionTest(TestCase):
    """Verifica que el cálculo de compra/venta use la comisión del cliente."""

    def setUp(self):
        """Prepara un cliente VIP con una divisa cotizada."""
        self.usuario = User.objects.create_user(username='cliente-vip', password='password123')
        self.client.login(username='cliente-vip', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()
        self.cliente = Cliente.objects.create(
            user=self.usuario,
            identificador='CI-VIP-001',
            nombre='Cliente',
            apellido='VIP',
            email='cliente-vip@test.com',
            segmento='VIP',
            is_active=True,
        )
        self.usuario.clientes.add(self.cliente)
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        Cotizacion.objects.create(divisa=self.usd, tasa_compra=Decimal('7300.00'), tasa_venta=Decimal('7400.00'))

    def test_compra_usa_la_comision_configurada_para_el_segmento(self):
        """La comisión configurada para VIP reemplaza a la comisión por defecto."""
        ConfiguracionComision.objects.create(segmento='VIP', porcentaje=Decimal('2.000'))

        response = self.client.post(
            reverse('divisas:operar', kwargs={'tipo': 'compra'}),
            {'tipo': 'COMPRA', 'divisa': str(self.usd.pk), 'monto': '100'},
        )

        resultado = response.context['resultado']
        self.assertEqual(resultado['comision_porcentaje'], Decimal('2.000'))
        self.assertEqual(resultado['comision'], Decimal('14800.00'))
        self.assertEqual(resultado['monto_final'], Decimal('754800.00'))

    def test_comision_personalizada_del_cliente_prevalece(self):
        """La comisión personalizada del cliente gana incluso con una comisión de segmento."""
        ConfiguracionComision.objects.create(segmento='VIP', porcentaje=Decimal('2.000'))
        self.cliente.comision_personalizada = Decimal('0.000')
        self.cliente.save(update_fields=['comision_personalizada'])

        response = self.client.post(
            reverse('divisas:operar', kwargs={'tipo': 'compra'}),
            {'tipo': 'COMPRA', 'divisa': str(self.usd.pk), 'monto': '100'},
        )

        resultado = response.context['resultado']
        self.assertEqual(resultado['comision_porcentaje'], Decimal('0.000'))
        self.assertEqual(resultado['comision'], Decimal('0.00'))
        self.assertEqual(resultado['monto_final'], Decimal('740000.00'))
