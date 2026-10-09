"""Pruebas de la HU 'Apertura de Caja'."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from apps.caja.models import Caja, SaldoInicialCaja
from apps.divisas.models import Cotizacion, Divisa

User = get_user_model()


class AperturaCajaTest(TestCase):
    """Verifica los criterios de aceptación de la HU 'Apertura de Caja'."""

    def setUp(self):
        """Prepara un cajero logueado y dos divisas activas."""
        self.cajero = User.objects.create_user(username='cajero-001', password='password123')
        self.client.login(username='cajero-001', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cajero']
        session.save()
        self.pyg = Divisa.objects.create(codigo='PYG', nombre='Guaraní', simbolo='Gs.', activa=True)
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        Cotizacion.objects.create(divisa=self.usd, tasa_compra=Decimal('7300.00'), tasa_venta=Decimal('7400.00'))
        self.url_abrir = reverse('caja:abrir')
        self.url_panel = reverse('caja:panel')

    def _datos(self, saldo_pyg='500000.00', saldo_usd='100.00'):
        """Arma el POST de apertura con un saldo para cada divisa de prueba."""
        return {
            f'saldo_{self.pyg.pk}': saldo_pyg,
            f'saldo_{self.usd.pk}': saldo_usd,
        }

    def test_abre_la_caja_con_el_saldo_inicial_de_cada_moneda(self):
        """Criterio 1: crea la caja 'Abierta', asociada al cajero, con fecha de apertura."""
        response = self.client.post(self.url_abrir, self._datos(), follow=True)

        self.assertEqual(response.status_code, 200)
        caja = Caja.objects.get()
        self.assertEqual(caja.usuario, self.cajero)
        self.assertEqual(caja.estado, Caja.ESTADO_ABIERTA)
        self.assertIsNotNone(caja.abierta_en)
        self.assertContains(response, 'La caja fue abierta correctamente')

        saldos = {s.divisa.codigo: s.monto for s in caja.saldos_iniciales.all()}
        self.assertEqual(saldos, {'PYG': Decimal('500000.00'), 'USD': Decimal('100.00')})

    def test_no_se_puede_abrir_una_segunda_caja_sin_cerrar_la_actual(self):
        """Criterio 2: con una caja ya abierta, rechaza abrir otra."""
        self.client.post(self.url_abrir, self._datos())
        self.assertEqual(Caja.objects.count(), 1)

        response = self.client.post(self.url_abrir, self._datos(), follow=True)

        self.assertContains(response, 'Ya tenés una caja abierta')
        self.assertEqual(Caja.objects.count(), 1)

    def test_el_formulario_de_apertura_no_se_ofrece_si_ya_hay_una_caja_abierta(self):
        """Criterio 2: tampoco se puede acceder al formulario con una caja ya abierta."""
        self.client.post(self.url_abrir, self._datos())

        response = self.client.get(self.url_abrir, follow=True)

        self.assertContains(response, 'Ya tenés una caja abierta')
        self.assertNotContains(response, 'name="saldo_')

    def test_saldo_inicial_negativo_no_crea_la_caja(self):
        """Criterio 3: un saldo negativo en alguna moneda rechaza la apertura sin crear nada."""
        response = self.client.post(self.url_abrir, self._datos(saldo_usd='-1.00'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'no puede ser negativo')
        self.assertFalse(Caja.objects.exists())

    def test_saldo_inicial_con_formato_invalido_no_crea_la_caja(self):
        """Criterio 3: un saldo no numérico rechaza la apertura sin crear nada."""
        response = self.client.post(self.url_abrir, self._datos(saldo_usd='abc'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ingresá un monto válido')
        self.assertFalse(Caja.objects.exists())

    def test_saldo_inicial_en_cero_es_valido(self):
        """Criterio 3: un saldo inicial de cero es válido y sí crea la caja."""
        response = self.client.post(self.url_abrir, self._datos(saldo_usd='0'), follow=True)

        self.assertContains(response, 'La caja fue abierta correctamente')
        caja = Caja.objects.get()
        self.assertEqual(
            caja.saldos_iniciales.get(divisa=self.usd).monto,
            Decimal('0.00'),
        )

    def test_una_divisa_activa_sin_cotizacion_no_se_ofrece_para_registrar_saldo(self):
        """Una divisa activa sin ninguna cotización vigente no recibe un campo de saldo."""
        eur = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)

        response = self.client.get(self.url_abrir)

        self.assertNotContains(response, f'name="saldo_{eur.pk}"')
        self.assertContains(response, 'EUR')
        self.assertContains(response, 'Hace falta cotizar')
        self.assertContains(response, 'analista cambiario o un administrador')

    def test_se_puede_abrir_la_caja_sin_la_divisa_sin_cotizar(self):
        """Una divisa sin cotizar no bloquea la apertura: se abre con el resto, sin ese saldo."""
        eur = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)

        response = self.client.post(self.url_abrir, self._datos(), follow=True)

        self.assertContains(response, 'La caja fue abierta correctamente')
        caja = Caja.objects.get()
        self.assertEqual(caja.saldos_iniciales.count(), 2)
        self.assertFalse(caja.saldos_iniciales.filter(divisa=eur).exists())

    def test_el_panel_muestra_el_saldo_inicial_tal_como_se_registro(self):
        """Criterio 4: tras abrir, el panel muestra el saldo inicial por moneda registrado."""
        self.client.post(self.url_abrir, self._datos(saldo_pyg='123456.00', saldo_usd='250.50'))

        response = self.client.get(self.url_panel)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'PYG')
        self.assertContains(response, 'USD')
        self.assertContains(response, '123.456,00')
        self.assertContains(response, '250,50')

    def test_panel_sin_caja_abierta_ofrece_el_acceso_a_abrir_una(self):
        """Sin ninguna caja abierta, el panel lo indica y ofrece abrir una."""
        response = self.client.get(self.url_panel)

        self.assertContains(response, 'Todavía no tenés una caja abierta')
        self.assertContains(response, self.url_abrir)

    def test_usuario_sin_rol_cajero_no_puede_abrir_ni_ver_el_panel(self):
        """Criterio 5: sin rol cajero, se niega el acceso a abrir caja y al panel."""
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response_get_abrir = self.client.get(self.url_abrir)
        response_post_abrir = self.client.post(self.url_abrir, self._datos())
        response_panel = self.client.get(self.url_panel)

        self.assertEqual(response_get_abrir.status_code, 403)
        self.assertEqual(response_post_abrir.status_code, 403)
        self.assertEqual(response_panel.status_code, 403)
        self.assertFalse(Caja.objects.exists())

    def test_usuario_sin_ningun_rol_no_puede_abrir_ni_ver_el_panel(self):
        """Criterio 5: un usuario autenticado sin ningún rol tampoco accede a caja."""
        session = self.client.session
        session['keycloak_roles'] = []
        session.save()

        self.assertEqual(self.client.get(self.url_abrir).status_code, 403)
        self.assertEqual(self.client.get(self.url_panel).status_code, 403)

    def test_usuario_no_autenticado_es_redirigido_al_login(self):
        """Sin sesión iniciada, se redirige al login en vez de mostrar la caja."""
        self.client.logout()

        response = self.client.get(self.url_panel)

        self.assertEqual(response.status_code, 302)


class CajaModeloTest(TestCase):
    """Verifica la restricción de base de datos que respalda el Criterio 2."""

    def setUp(self):
        """Prepara un cajero y una divisa activa."""
        self.cajero = User.objects.create_user(username='cajero-modelo', password='password123')
        self.divisa = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)

    def test_la_base_de_datos_impide_dos_cajas_abiertas_para_el_mismo_cajero(self):
        """Ni siquiera saltando la vista, la base permite dos cajas 'Abierta' del mismo cajero."""
        Caja.objects.create(usuario=self.cajero)

        with self.assertRaises(IntegrityError):
            Caja.objects.create(usuario=self.cajero)

    def test_una_caja_cerrada_no_bloquea_abrir_una_nueva(self):
        """La restricción es solo entre cajas 'Abierta': una 'Cerrada' no cuenta."""
        cerrada = Caja.objects.create(usuario=self.cajero, estado=Caja.ESTADO_CERRADA)
        nueva = Caja.objects.create(usuario=self.cajero)

        self.assertNotEqual(cerrada.pk, nueva.pk)
        self.assertEqual(Caja.objects.filter(usuario=self.cajero).count(), 2)

    def test_saldo_inicial_unico_por_caja_y_divisa(self):
        """No se puede registrar dos saldos iniciales para la misma divisa en una caja."""
        caja = Caja.objects.create(usuario=self.cajero)
        SaldoInicialCaja.objects.create(caja=caja, divisa=self.divisa, monto=Decimal('10.00'))

        with self.assertRaises(IntegrityError):
            SaldoInicialCaja.objects.create(caja=caja, divisa=self.divisa, monto=Decimal('20.00'))
