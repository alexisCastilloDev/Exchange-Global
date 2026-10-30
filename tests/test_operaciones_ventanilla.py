"""Pruebas de la HU 'Gestión de operaciones en ventanilla'."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.caja.models import Caja, OperacionVentanilla, SaldoInicialCaja
from apps.divisas.models import Cotizacion, Divisa

User = get_user_model()


class RegistrarOperacionVentanillaTest(TestCase):
    """Verifica los criterios de aceptación de la HU 'Gestión de operaciones en ventanilla'."""

    def setUp(self):
        """Prepara un cajero logueado, USD cotizado y una caja abierta con saldo.

        PYG ya existe de antemano: la migración de datos
        ``apps.divisas.0014_crear_divisa_pyg`` la garantiza como moneda
        local/base del sistema.
        """
        self.cajero = User.objects.create_user(username='cajero-ventanilla', password='password123')
        self.client.login(username='cajero-ventanilla', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cajero']
        session.save()

        self.pyg = Divisa.objects.get(codigo='PYG')
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        Cotizacion.objects.create(divisa=self.usd, tasa_compra=Decimal('7300.00'), tasa_venta=Decimal('7400.00'))

        self.caja = Caja.objects.create(usuario=self.cajero)
        SaldoInicialCaja.objects.create(caja=self.caja, divisa=self.pyg, monto=Decimal('10000000.00'))
        SaldoInicialCaja.objects.create(caja=self.caja, divisa=self.usd, monto=Decimal('500.00'))

        self.url_comprar = reverse('caja:registrar_operacion', kwargs={'tipo': 'compra'})
        self.url_vender = reverse('caja:registrar_operacion', kwargs={'tipo': 'venta'})
        self.url_panel = reverse('caja:panel')

    def _datos(self, monto='100.00'):
        """Arma el POST de una operación con la divisa de prueba y el monto dado."""
        return {'divisa': str(self.usd.pk), 'monto': monto}

    # --- Criterio 1 ---

    def test_comprar_divisas_ingresa_la_divisa_y_egresa_guaranies(self):
        """Criterio 1: comprar USD ingresa USD y egresa PYG, con la cotización reutilizada."""
        response = self.client.post(self.url_comprar, self._datos('100.00'), follow=True)

        self.assertContains(response, 'La operación se registró correctamente')
        operacion = OperacionVentanilla.objects.get()
        self.assertEqual(operacion.tipo, OperacionVentanilla.TIPO_COMPRA)
        self.assertEqual(operacion.divisa, self.usd)
        self.assertEqual(operacion.monto_divisa, Decimal('100.00'))
        self.assertEqual(operacion.tasa_aplicada, Decimal('7300.00'))  # tasa_compra: la casa compra
        self.assertEqual(operacion.monto_pyg, Decimal('730000.00') - operacion.comision)

        # Ingresó la divisa, egresó guaraníes.
        self.assertEqual(self.caja.saldo_actual(self.usd), Decimal('500.00') + Decimal('100.00'))
        self.assertEqual(
            self.caja.saldo_actual(self.pyg),
            Decimal('10000000.00') - operacion.monto_pyg,
        )

    def test_vender_divisas_egresa_la_divisa_e_ingresa_guaranies(self):
        """Criterio 1: vender USD egresa USD e ingresa PYG, con la cotización reutilizada."""
        response = self.client.post(self.url_vender, self._datos('50.00'), follow=True)

        self.assertContains(response, 'La operación se registró correctamente')
        operacion = OperacionVentanilla.objects.get()
        self.assertEqual(operacion.tipo, OperacionVentanilla.TIPO_VENTA)
        self.assertEqual(operacion.tasa_aplicada, Decimal('7400.00'))  # tasa_venta: la casa vende
        self.assertEqual(operacion.monto_pyg, Decimal('370000.00') + operacion.comision)

        # Egresó la divisa, ingresó guaraníes.
        self.assertEqual(self.caja.saldo_actual(self.usd), Decimal('500.00') - Decimal('50.00'))
        self.assertEqual(
            self.caja.saldo_actual(self.pyg),
            Decimal('10000000.00') + operacion.monto_pyg,
        )

    def test_la_comision_aplicada_se_descuenta_de_una_compra(self):
        """La comisión configurada reduce lo que la caja entrega en una compra."""
        response = self.client.post(self.url_comprar, self._datos('100.00'), follow=True)

        self.assertEqual(response.status_code, 200)
        operacion = OperacionVentanilla.objects.get()
        self.assertGreater(operacion.comision, Decimal('0.00'))
        self.assertEqual(operacion.monto_pyg, Decimal('730000.00') - operacion.comision)

    # --- Criterio 2 ---

    def test_sin_caja_abierta_rechaza_la_operacion_y_no_ofrece_el_formulario(self):
        """Criterio 2: sin caja abierta, la operación se rechaza (POST) y no se ofrece el formulario (GET)."""
        self.caja.delete()

        with self.subTest('POST rechazado'):
            response = self.client.post(self.url_comprar, self._datos(), follow=True)

            self.assertContains(response, 'Necesitás abrir una caja')
            self.assertFalse(OperacionVentanilla.objects.exists())

        with self.subTest('formulario no ofrecido'):
            response = self.client.get(self.url_comprar, follow=True)

            self.assertContains(response, 'Necesitás abrir una caja')
            self.assertNotContains(response, 'name="monto"')

    # --- Criterio 3 ---

    def test_saldo_insuficiente_de_guaranies_rechaza_una_compra(self):
        """Criterio 3: sin guaraníes suficientes para pagarle al cliente, la compra se rechaza."""
        SaldoInicialCaja.objects.filter(caja=self.caja, divisa=self.pyg).update(monto=Decimal('100.00'))

        response = self.client.post(self.url_comprar, self._datos('100.00'), follow=True)

        self.assertContains(response, 'Saldo insuficiente de PYG')
        self.assertFalse(OperacionVentanilla.objects.exists())
        self.assertEqual(self.caja.saldo_actual(self.usd), Decimal('500.00'))

    def test_saldo_insuficiente_de_la_divisa_rechaza_una_venta(self):
        """Criterio 3: sin suficiente divisa para entregarle al cliente, la venta se rechaza."""
        SaldoInicialCaja.objects.filter(caja=self.caja, divisa=self.usd).update(monto=Decimal('10.00'))

        response = self.client.post(self.url_vender, self._datos('50.00'), follow=True)

        self.assertContains(response, 'Saldo insuficiente de USD')
        self.assertFalse(OperacionVentanilla.objects.exists())
        self.assertEqual(self.caja.saldo_actual(self.pyg), Decimal('10000000.00'))

    def test_saldo_exacto_es_suficiente(self):
        """El límite es inclusivo: con el saldo exacto que hace falta, la operación se acepta."""
        SaldoInicialCaja.objects.filter(caja=self.caja, divisa=self.usd).update(monto=Decimal('50.00'))

        response = self.client.post(self.url_vender, self._datos('50.00'), follow=True)

        self.assertContains(response, 'La operación se registró correctamente')
        self.assertEqual(self.caja.saldo_actual(self.usd), Decimal('0.00'))

    # --- Criterio 4 ---

    def test_la_operacion_queda_vinculada_a_la_caja_y_al_cajero_con_tasa_comision_y_montos(self):
        """Criterio 4: la operación guardada referencia la caja, el cajero, tasa, comisión y ambos montos."""
        self.client.post(self.url_comprar, self._datos('100.00'))

        operacion = OperacionVentanilla.objects.get()
        self.assertEqual(operacion.caja, self.caja)
        self.assertEqual(operacion.cajero, self.cajero)
        self.assertEqual(operacion.tasa_aplicada, Decimal('7300.00'))
        self.assertGreater(operacion.comision_porcentaje, Decimal('0'))
        self.assertEqual(operacion.monto_divisa, Decimal('100.00'))
        self.assertIsNotNone(operacion.monto_pyg)

    # --- Validaciones del formulario ---

    def test_un_monto_invalido_no_registra_la_operacion(self):
        """Un monto negativo o no numérico se rechaza con el mismo criterio que el resto del sistema."""
        with self.subTest('negativo'):
            response = self.client.post(self.url_comprar, self._datos('-10.00'))

            self.assertContains(response, 'El monto debe ser mayor que cero.')
            self.assertFalse(OperacionVentanilla.objects.exists())

        with self.subTest('no numérico'):
            response = self.client.post(self.url_comprar, self._datos('abc'))

            self.assertContains(response, 'El monto debe ser un número válido.')
            self.assertFalse(OperacionVentanilla.objects.exists())

    def test_pyg_y_una_divisa_sin_cotizacion_no_se_ofrecen_como_divisa_operable(self):
        """PYG nunca se ofrece (es la moneda contra la que siempre se opera); una divisa sin cotizar, tampoco."""
        eur = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)

        response = self.client.get(self.url_comprar)

        self.assertNotContains(response, f'value="{self.pyg.pk}"')
        self.assertNotContains(response, f'value="{eur.pk}"')

    def test_tipo_de_operacion_desconocido_responde_404(self):
        """Un tipo que no sea 'compra' ni 'venta' en la URL no existe."""
        url = reverse('caja:registrar_operacion', kwargs={'tipo': 'cambio'})

        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    # --- Permisos ---

    def test_usuario_sin_rol_cajero_no_puede_registrar_operaciones(self):
        """Solo el rol cajero puede registrar operaciones de ventanilla."""
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response_get = self.client.get(self.url_comprar)
        response_post = self.client.post(self.url_comprar, self._datos())

        self.assertEqual(response_get.status_code, 403)
        self.assertEqual(response_post.status_code, 403)
        self.assertFalse(OperacionVentanilla.objects.exists())

    def test_usuario_no_autenticado_es_redirigido_al_login(self):
        """Sin sesión iniciada, se redirige al login en vez de registrar la operación."""
        self.client.logout()

        response = self.client.get(self.url_comprar)

        self.assertEqual(response.status_code, 302)


class RegistrarOperacionVentanillaSinDivisaPygTest(TestCase):
    """Confirma que una compra puede resolver PYG sin que un administrador la dé de alta a mano.

    PYG es la moneda local/base del sistema (se cotiza y liquida todo contra
    ella, nunca se la ofrece como una divisa operable más), así que su
    existencia en el catálogo está garantizada por la migración de datos
    ``apps.divisas.0014_crear_divisa_pyg`` en vez de depender de que alguien
    la cree manualmente desde "Divisas" como si fuera una divisa extranjera.
    """

    def setUp(self):
        """Prepara un cajero logueado, USD cotizado y una caja abierta con saldo."""
        self.cajero = User.objects.create_user(username='cajero-sin-pyg', password='password123')
        self.client.login(username='cajero-sin-pyg', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cajero']
        session.save()

        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        Cotizacion.objects.create(divisa=self.usd, tasa_compra=Decimal('7300.00'), tasa_venta=Decimal('7400.00'))

        self.caja = Caja.objects.create(usuario=self.cajero)
        SaldoInicialCaja.objects.create(
            caja=self.caja, divisa=Divisa.objects.get(codigo='PYG'), monto=Decimal('10000000.00'),
        )
        SaldoInicialCaja.objects.create(caja=self.caja, divisa=self.usd, monto=Decimal('500.00'))

        self.url_comprar = reverse('caja:registrar_operacion', kwargs={'tipo': 'compra'})

    def test_la_divisa_pyg_existe_sin_que_ningun_administrador_la_haya_creado(self):
        """PYG está disponible desde el inicio: no depende de un alta manual en el catálogo."""
        pyg = Divisa.objects.get(codigo='PYG')

        self.assertTrue(pyg.activa)
        self.assertEqual(pyg.nombre, 'Guaraní')

    def test_comprar_divisas_funciona_sin_que_nadie_haya_dado_de_alta_pyg_a_mano(self):
        """Una compra resuelve el saldo en PYG sin ningún paso de configuración previo."""
        response = self.client.post(
            self.url_comprar, {'divisa': str(self.usd.pk), 'monto': '100.00'}, follow=True,
        )

        self.assertContains(response, 'La operación se registró correctamente')
        self.assertTrue(OperacionVentanilla.objects.exists())


class CajaSaldoActualTest(TestCase):
    """Pruebas unitarias de 'Caja.saldo_actual', directamente contra el modelo."""

    def setUp(self):
        """Prepara una caja con saldo inicial en PYG y USD, sin operaciones todavía."""
        self.cajero = User.objects.create_user(username='cajero-saldo', password='password123')
        self.pyg = Divisa.objects.get(codigo='PYG')
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        self.caja = Caja.objects.create(usuario=self.cajero)
        SaldoInicialCaja.objects.create(caja=self.caja, divisa=self.pyg, monto=Decimal('1000000.00'))
        SaldoInicialCaja.objects.create(caja=self.caja, divisa=self.usd, monto=Decimal('200.00'))

    def test_sin_operaciones_el_saldo_actual_es_el_saldo_inicial(self):
        """Sin ninguna operación registrada, el saldo actual coincide con el inicial."""
        self.assertEqual(self.caja.saldo_actual(self.pyg), Decimal('1000000.00'))
        self.assertEqual(self.caja.saldo_actual(self.usd), Decimal('200.00'))

    def test_una_divisa_sin_saldo_inicial_registrado_empieza_en_cero(self):
        """Una divisa que no se contó al abrir la caja parte de saldo cero, no de un error."""
        eur = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)

        self.assertEqual(self.caja.saldo_actual(eur), Decimal('0.00'))

    def test_una_compra_suma_la_divisa_y_resta_guaranies(self):
        """Una 'Compra' (la casa compra) ingresa la divisa y egresa guaraníes del saldo actual."""
        OperacionVentanilla.objects.create(
            caja=self.caja, cajero=self.cajero, tipo=OperacionVentanilla.TIPO_COMPRA,
            divisa=self.usd, monto_divisa=Decimal('50.00'), tasa_aplicada=Decimal('7300.00'),
            comision_porcentaje=Decimal('1.00'), comision=Decimal('3650.00'), monto_pyg=Decimal('361350.00'),
        )

        self.assertEqual(self.caja.saldo_actual(self.usd), Decimal('250.00'))
        self.assertEqual(self.caja.saldo_actual(self.pyg), Decimal('638650.00'))

    def test_una_venta_resta_la_divisa_y_suma_guaranies(self):
        """Una 'Venta' (la casa vende) egresa la divisa e ingresa guaraníes al saldo actual."""
        OperacionVentanilla.objects.create(
            caja=self.caja, cajero=self.cajero, tipo=OperacionVentanilla.TIPO_VENTA,
            divisa=self.usd, monto_divisa=Decimal('50.00'), tasa_aplicada=Decimal('7400.00'),
            comision_porcentaje=Decimal('1.00'), comision=Decimal('3700.00'), monto_pyg=Decimal('373700.00'),
        )

        self.assertEqual(self.caja.saldo_actual(self.usd), Decimal('150.00'))
        self.assertEqual(self.caja.saldo_actual(self.pyg), Decimal('1373700.00'))

    def test_una_operacion_de_otra_caja_no_afecta_este_saldo(self):
        """El saldo actual de una caja nunca mezcla operaciones de otra caja."""
        otro_cajero = User.objects.create_user(username='cajero-otro', password='password123')
        otra_caja = Caja.objects.create(usuario=otro_cajero)
        OperacionVentanilla.objects.create(
            caja=otra_caja, cajero=otro_cajero, tipo=OperacionVentanilla.TIPO_COMPRA,
            divisa=self.usd, monto_divisa=Decimal('999.00'), tasa_aplicada=Decimal('7300.00'),
            comision_porcentaje=Decimal('1.00'), comision=Decimal('0.00'), monto_pyg=Decimal('0.00'),
        )

        self.assertEqual(self.caja.saldo_actual(self.usd), Decimal('200.00'))
