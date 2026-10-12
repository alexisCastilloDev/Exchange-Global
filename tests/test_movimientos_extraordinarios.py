"""Pruebas de la HU 'Gestión de movimientos extraordinarios de Caja'."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.caja.models import Caja, MovimientoExtraordinario, OperacionVentanilla, SaldoInicialCaja
from apps.divisas.models import Cotizacion, Divisa

User = get_user_model()


class RegistrarMovimientoExtraordinarioTest(TestCase):
    """Verifica los criterios de aceptación de 'Gestión de movimientos extraordinarios de Caja'."""

    def setUp(self):
        """Prepara un cajero logueado, USD cotizado y una caja abierta con saldo.

        PYG ya existe de antemano: la migración de datos
        ``apps.divisas.0014_crear_divisa_pyg`` la garantiza como moneda
        local/base del sistema.
        """
        self.cajero = User.objects.create_user(username='cajero-extraordinario', password='password123')
        self.client.login(username='cajero-extraordinario', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cajero']
        session.save()

        self.pyg = Divisa.objects.get(codigo='PYG')
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        Cotizacion.objects.create(divisa=self.usd, tasa_compra=Decimal('7300.00'), tasa_venta=Decimal('7400.00'))

        self.caja = Caja.objects.create(usuario=self.cajero)
        SaldoInicialCaja.objects.create(caja=self.caja, divisa=self.pyg, monto=Decimal('1000000.00'))
        SaldoInicialCaja.objects.create(caja=self.caja, divisa=self.usd, monto=Decimal('500.00'))

        self.url_ingreso = reverse('caja:registrar_movimiento_extraordinario', kwargs={'tipo': 'ingreso'})
        self.url_egreso = reverse('caja:registrar_movimiento_extraordinario', kwargs={'tipo': 'egreso'})

    def _datos(self, monto='100.00', motivo='Retiro para gastos de oficina', divisa=None):
        """Arma el POST de un movimiento con la divisa, monto y motivo dados."""
        divisa = divisa or self.usd
        return {'divisa': str(divisa.pk), 'monto': monto, 'motivo': motivo}

    # --- Criterio 1 ---

    def test_un_ingreso_extraordinario_actualiza_el_saldo_de_la_caja(self):
        """Criterio 1: un ingreso extraordinario de una divisa suma a su saldo actual."""
        response = self.client.post(self.url_ingreso, self._datos('100.00'), follow=True)

        self.assertContains(response, 'El movimiento extraordinario se registró correctamente')
        movimiento = MovimientoExtraordinario.objects.get()
        self.assertEqual(movimiento.tipo, MovimientoExtraordinario.TIPO_INGRESO)
        self.assertEqual(movimiento.divisa, self.usd)
        self.assertEqual(movimiento.monto, Decimal('100.00'))
        self.assertEqual(movimiento.motivo, 'Retiro para gastos de oficina')
        self.assertEqual(self.caja.saldo_actual(self.usd), Decimal('600.00'))

    def test_un_egreso_extraordinario_actualiza_el_saldo_de_la_caja(self):
        """Criterio 1: un egreso extraordinario de una divisa resta de su saldo actual."""
        response = self.client.post(self.url_egreso, self._datos('100.00'), follow=True)

        self.assertContains(response, 'El movimiento extraordinario se registró correctamente')
        movimiento = MovimientoExtraordinario.objects.get()
        self.assertEqual(movimiento.tipo, MovimientoExtraordinario.TIPO_EGRESO)
        self.assertEqual(self.caja.saldo_actual(self.usd), Decimal('400.00'))

    def test_un_movimiento_extraordinario_puede_registrarse_en_guaranies(self):
        """Criterio 1: a diferencia de ventanilla, PYG sí es una divisa operable acá."""
        response = self.client.post(self.url_egreso, self._datos('50000.00', divisa=self.pyg), follow=True)

        self.assertContains(response, 'El movimiento extraordinario se registró correctamente')
        self.assertEqual(self.caja.saldo_actual(self.pyg), Decimal('950000.00'))

    def test_sin_caja_abierta_rechaza_el_movimiento_y_pide_abrir_una(self):
        """Sin caja abierta, el movimiento se rechaza e indica abrir una primero."""
        self.caja.delete()

        response = self.client.post(self.url_ingreso, self._datos(), follow=True)

        self.assertContains(response, 'Necesitás abrir una caja')
        self.assertFalse(MovimientoExtraordinario.objects.exists())

    def test_sin_caja_abierta_tampoco_se_ofrece_el_formulario(self):
        """Sin caja abierta, no se puede acceder al formulario."""
        self.caja.delete()

        response = self.client.get(self.url_ingreso, follow=True)

        self.assertContains(response, 'Necesitás abrir una caja')
        self.assertNotContains(response, 'name="monto"')

    # --- Criterio 2 ---

    def test_un_egreso_mayor_al_saldo_disponible_se_rechaza(self):
        """Criterio 2: un egreso extraordinario mayor al saldo disponible se rechaza e informa el motivo."""
        response = self.client.post(self.url_egreso, self._datos('1000.00'), follow=True)

        self.assertContains(response, 'Saldo insuficiente de USD')
        self.assertFalse(MovimientoExtraordinario.objects.exists())
        self.assertEqual(self.caja.saldo_actual(self.usd), Decimal('500.00'))

    def test_un_egreso_igual_al_saldo_disponible_se_acepta(self):
        """El límite es inclusivo: un egreso por el saldo exacto disponible se acepta."""
        response = self.client.post(self.url_egreso, self._datos('500.00'), follow=True)

        self.assertContains(response, 'El movimiento extraordinario se registró correctamente')
        self.assertEqual(self.caja.saldo_actual(self.usd), Decimal('0.00'))

    def test_un_ingreso_nunca_se_rechaza_por_saldo(self):
        """Un ingreso extraordinario no tiene límite de saldo: siempre puede sumarse."""
        response = self.client.post(self.url_ingreso, self._datos('999999.00'), follow=True)

        self.assertContains(response, 'El movimiento extraordinario se registró correctamente')

    # --- Criterio 3 ---

    def test_sin_motivo_no_se_registra_el_movimiento(self):
        """Criterio 3: sin motivo, el sistema exige ese campo antes de permitir el registro."""
        response = self.client.post(
            self.url_ingreso, {'divisa': str(self.usd.pk), 'monto': '100.00', 'motivo': ''},
        )

        self.assertContains(response, 'Debe indicar el motivo del movimiento.')
        self.assertFalse(MovimientoExtraordinario.objects.exists())

    def test_un_motivo_compuesto_solo_de_espacios_tampoco_se_acepta(self):
        """Criterio 3: un motivo que al recortarlo queda vacío tampoco es válido."""
        response = self.client.post(
            self.url_ingreso, {'divisa': str(self.usd.pk), 'monto': '100.00', 'motivo': '   '},
        )

        self.assertContains(response, 'Debe indicar el motivo del movimiento.')
        self.assertFalse(MovimientoExtraordinario.objects.exists())

    # --- Criterio 4 ---

    def test_el_movimiento_extraordinario_queda_identificado_como_distinto_de_una_operacion_cambiaria(self):
        """Criterio 4: en el panel, un movimiento extraordinario aparece separado de las operaciones de ventanilla."""
        self.client.post(self.url_ingreso, self._datos('100.00', motivo='Refuerzo de caja'))
        OperacionVentanilla.objects.create(
            caja=self.caja, cajero=self.cajero, tipo=OperacionVentanilla.TIPO_COMPRA,
            divisa=self.usd, monto_divisa=Decimal('10.00'), tasa_aplicada=Decimal('7300.00'),
            comision_porcentaje=Decimal('1.00'), comision=Decimal('730.00'), monto_pyg=Decimal('72270.00'),
        )

        response = self.client.get(reverse('caja:panel'))

        self.assertContains(response, 'Últimas operaciones de ventanilla')
        self.assertContains(response, 'Últimos movimientos extraordinarios')
        self.assertContains(response, 'Refuerzo de caja')
        self.assertEqual(len(response.context['operaciones']), 1)
        self.assertEqual(len(response.context['movimientos_extraordinarios']), 1)

    def test_el_movimiento_queda_vinculado_a_la_caja_y_al_cajero_con_tipo_divisa_monto_y_motivo(self):
        """Criterio 4: el movimiento guardado referencia la caja, el cajero, tipo, divisa, monto y motivo."""
        self.client.post(self.url_egreso, self._datos('100.00', motivo='Pago de un servicio'))

        movimiento = MovimientoExtraordinario.objects.get()
        self.assertEqual(movimiento.caja, self.caja)
        self.assertEqual(movimiento.cajero, self.cajero)
        self.assertEqual(movimiento.tipo, MovimientoExtraordinario.TIPO_EGRESO)
        self.assertEqual(movimiento.divisa, self.usd)
        self.assertEqual(movimiento.monto, Decimal('100.00'))
        self.assertEqual(movimiento.motivo, 'Pago de un servicio')
        self.assertIsNotNone(movimiento.creado_en)

    # --- Validaciones del formulario ---

    def test_un_monto_negativo_no_registra_el_movimiento(self):
        """Un monto negativo se rechaza con el mismo criterio que el resto del sistema."""
        response = self.client.post(self.url_ingreso, self._datos('-10.00'))

        self.assertContains(response, 'El monto debe ser mayor que cero.')
        self.assertFalse(MovimientoExtraordinario.objects.exists())

    def test_un_monto_no_numerico_no_registra_el_movimiento(self):
        """Un monto no numérico se rechaza sin crear nada."""
        response = self.client.post(self.url_ingreso, self._datos('abc'))

        self.assertContains(response, 'El monto debe ser un número válido.')
        self.assertFalse(MovimientoExtraordinario.objects.exists())

    def test_pyg_se_ofrece_como_divisa_a_diferencia_de_ventanilla(self):
        """A diferencia de 'OperacionVentanillaForm', PYG sí aparece como opción acá."""
        response = self.client.get(self.url_ingreso)

        self.assertContains(response, f'value="{self.pyg.pk}"')

    def test_una_divisa_activa_sin_cotizacion_se_ofrece_igual(self):
        """A diferencia de ventanilla, una divisa sin cotización vigente sí se puede usar."""
        eur = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)

        response = self.client.get(self.url_ingreso)

        self.assertContains(response, f'value="{eur.pk}"')

    def test_tipo_de_movimiento_desconocido_responde_404(self):
        """Un tipo que no sea 'ingreso' ni 'egreso' en la URL no existe."""
        url = reverse('caja:registrar_movimiento_extraordinario', kwargs={'tipo': 'cambio'})

        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    # --- Permisos ---

    def test_usuario_sin_rol_cajero_no_puede_registrar_movimientos(self):
        """Solo el rol cajero puede registrar movimientos extraordinarios."""
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response_get = self.client.get(self.url_ingreso)
        response_post = self.client.post(self.url_ingreso, self._datos())

        self.assertEqual(response_get.status_code, 403)
        self.assertEqual(response_post.status_code, 403)
        self.assertFalse(MovimientoExtraordinario.objects.exists())

    def test_usuario_no_autenticado_es_redirigido_al_login(self):
        """Sin sesión iniciada, se redirige al login en vez de registrar el movimiento."""
        self.client.logout()

        response = self.client.get(self.url_ingreso)

        self.assertEqual(response.status_code, 302)


class CajaSaldoActualConMovimientosExtraordinariosTest(TestCase):
    """Pruebas unitarias de 'Caja.saldo_actual' con movimientos extraordinarios, contra el modelo."""

    def setUp(self):
        """Prepara una caja con saldo inicial en PYG y USD, sin movimientos todavía."""
        self.cajero = User.objects.create_user(username='cajero-saldo-extra', password='password123')
        self.pyg = Divisa.objects.get(codigo='PYG')
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        self.caja = Caja.objects.create(usuario=self.cajero)
        SaldoInicialCaja.objects.create(caja=self.caja, divisa=self.pyg, monto=Decimal('1000000.00'))
        SaldoInicialCaja.objects.create(caja=self.caja, divisa=self.usd, monto=Decimal('200.00'))

    def test_un_ingreso_extraordinario_suma_al_saldo_actual(self):
        """Un ingreso extraordinario de una divisa suma a su saldo actual."""
        MovimientoExtraordinario.objects.create(
            caja=self.caja, cajero=self.cajero, tipo=MovimientoExtraordinario.TIPO_INGRESO,
            divisa=self.usd, monto=Decimal('50.00'), motivo='Refuerzo de caja',
        )

        self.assertEqual(self.caja.saldo_actual(self.usd), Decimal('250.00'))

    def test_un_egreso_extraordinario_resta_del_saldo_actual(self):
        """Un egreso extraordinario de una divisa resta de su saldo actual."""
        MovimientoExtraordinario.objects.create(
            caja=self.caja, cajero=self.cajero, tipo=MovimientoExtraordinario.TIPO_EGRESO,
            divisa=self.usd, monto=Decimal('50.00'), motivo='Pago de un servicio',
        )

        self.assertEqual(self.caja.saldo_actual(self.usd), Decimal('150.00'))

    def test_operaciones_de_ventanilla_y_movimientos_extraordinarios_se_combinan(self):
        """El saldo actual combina correctamente ventanilla y movimientos extraordinarios."""
        OperacionVentanilla.objects.create(
            caja=self.caja, cajero=self.cajero, tipo=OperacionVentanilla.TIPO_COMPRA,
            divisa=self.usd, monto_divisa=Decimal('50.00'), tasa_aplicada=Decimal('7300.00'),
            comision_porcentaje=Decimal('1.00'), comision=Decimal('3650.00'), monto_pyg=Decimal('361350.00'),
        )
        MovimientoExtraordinario.objects.create(
            caja=self.caja, cajero=self.cajero, tipo=MovimientoExtraordinario.TIPO_EGRESO,
            divisa=self.usd, monto=Decimal('20.00'), motivo='Pago de un servicio',
        )

        # Saldo inicial 200.00 + compra ventanilla 50.00 - egreso extraordinario 20.00.
        self.assertEqual(self.caja.saldo_actual(self.usd), Decimal('230.00'))

    def test_un_movimiento_extraordinario_de_otra_caja_no_afecta_este_saldo(self):
        """El saldo actual de una caja nunca mezcla movimientos extraordinarios de otra caja."""
        otro_cajero = User.objects.create_user(username='cajero-extra-otro', password='password123')
        otra_caja = Caja.objects.create(usuario=otro_cajero)
        MovimientoExtraordinario.objects.create(
            caja=otra_caja, cajero=otro_cajero, tipo=MovimientoExtraordinario.TIPO_INGRESO,
            divisa=self.usd, monto=Decimal('999.00'), motivo='Refuerzo de caja',
        )

        self.assertEqual(self.caja.saldo_actual(self.usd), Decimal('200.00'))
