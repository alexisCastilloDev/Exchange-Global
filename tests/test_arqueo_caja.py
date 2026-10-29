"""Pruebas de la HU 'Arqueo de Caja'."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.caja.models import ArqueoCaja, Caja, DetalleArqueoCaja, SaldoInicialCaja
from apps.divisas.models import Cotizacion, Divisa

User = get_user_model()


class IniciarArqueoCajaTest(TestCase):
    """Verifica los criterios de aceptación de la HU 'Arqueo de Caja'."""

    def setUp(self):
        """Prepara un cajero logueado y una caja abierta con saldo inicial en PYG y USD cotizado.

        PYG ya existe de antemano (migración ``apps.divisas.0014_crear_divisa_pyg``).
        """
        self.cajero = User.objects.create_user(username='cajero-arqueo', password='password123')
        self.client.login(username='cajero-arqueo', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cajero']
        session.save()

        self.pyg = Divisa.objects.get(codigo='PYG')
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        Cotizacion.objects.create(divisa=self.usd, tasa_compra=Decimal('7300.00'), tasa_venta=Decimal('7400.00'))

        self.caja = Caja.objects.create(usuario=self.cajero)
        SaldoInicialCaja.objects.create(caja=self.caja, divisa=self.pyg, monto=Decimal('1000000.00'))
        SaldoInicialCaja.objects.create(caja=self.caja, divisa=self.usd, monto=Decimal('500.00'))

        self.url_iniciar = reverse('caja:iniciar_arqueo')
        self.url_historial = reverse('caja:historial_arqueos')

    def _datos(self, pyg='1000000.00', usd='500.00'):
        """Arma el POST de un arqueo con el monto contado de cada divisa de prueba."""
        return {
            f'contado_{self.pyg.pk}': pyg,
            f'contado_{self.usd.pk}': usd,
        }

    # --- Criterio 1 ---

    def test_arqueo_compara_lo_contado_contra_el_saldo_del_sistema_por_divisa(self):
        """Criterio 1: el arqueo compara lo contado contra el saldo registrado y muestra sobrante/faltante."""
        response = self.client.post(
            self.url_iniciar, self._datos(pyg='950000.00', usd='520.00'), follow=True,
        )

        self.assertContains(response, 'El arqueo se registró correctamente')
        self.assertContains(response, 'Faltante')
        self.assertContains(response, 'Sobrante')
        arqueo = ArqueoCaja.objects.get()
        self.assertEqual(arqueo.caja, self.caja)

        detalle_pyg = arqueo.detalles.get(divisa=self.pyg)
        self.assertEqual(detalle_pyg.saldo_sistema, Decimal('1000000.00'))
        self.assertEqual(detalle_pyg.monto_contado, Decimal('950000.00'))
        self.assertEqual(detalle_pyg.diferencia, Decimal('-50000.00'))  # faltante

        detalle_usd = arqueo.detalles.get(divisa=self.usd)
        self.assertEqual(detalle_usd.saldo_sistema, Decimal('500.00'))
        self.assertEqual(detalle_usd.monto_contado, Decimal('520.00'))
        self.assertEqual(detalle_usd.diferencia, Decimal('20.00'))  # sobrante

    def test_un_arqueo_sin_diferencias_lo_indica_explicitamente(self):
        """Cuando lo contado coincide exactamente, el detalle lo muestra sin diferencias."""
        response = self.client.post(self.url_iniciar, self._datos(), follow=True)

        self.assertContains(response, 'coincide exactamente')
        arqueo = ArqueoCaja.objects.get()
        self.assertFalse(arqueo.tiene_diferencias)

    # --- Criterio 2 ---

    def test_una_diferencia_distinta_de_cero_no_bloquea_el_registro_ni_que_la_caja_siga_operando(self):
        """Criterio 2: una diferencia (sobrante o faltante) se registra igual, y la caja sigue operando."""
        response = self.client.post(
            self.url_iniciar, self._datos(pyg='800000.00', usd='300.00'), follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'El arqueo se registró correctamente')
        arqueo = ArqueoCaja.objects.get()
        self.assertTrue(arqueo.tiene_diferencias)

        url_venta = reverse('caja:registrar_operacion', kwargs={'tipo': 'venta'})
        response = self.client.post(
            url_venta, {'divisa': str(self.usd.pk), 'monto': '50.00'}, follow=True,
        )

        self.assertContains(response, 'La operación se registró correctamente')

    # --- Criterio 3 ---

    def test_el_arqueo_registra_sus_datos_y_queda_disponible_para_consulta_posterior(self):
        """Criterio 3: fecha, hora, cajero y montos quedan guardados, consultables en el detalle y el historial."""
        self.client.post(self.url_iniciar, self._datos(pyg='950000.00', usd='520.00'))
        arqueo = ArqueoCaja.objects.get()

        with self.subTest('datos guardados'):
            self.assertEqual(arqueo.cajero, self.cajero)
            self.assertIsNotNone(arqueo.creado_en)
            self.assertEqual(arqueo.detalles.count(), 2)

        with self.subTest('detalle'):
            response = self.client.get(reverse('caja:detalle_arqueo', kwargs={'pk': arqueo.pk}))

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, arqueo.cajero.username)
            self.assertContains(response, 'USD')
            self.assertContains(response, 'PYG')

        with self.subTest('historial'):
            response = self.client.get(self.url_historial)

            self.assertContains(response, reverse('caja:detalle_arqueo', kwargs={'pk': arqueo.pk}))

    def test_el_saldo_sistema_queda_congelado_aunque_el_saldo_actual_cambie_despues(self):
        """Criterio 3: un arqueo viejo sigue mostrando el saldo del sistema de ese momento, no el actual."""
        self.client.post(self.url_iniciar, self._datos())
        arqueo = ArqueoCaja.objects.get()
        detalle_pyg_original = arqueo.detalles.get(divisa=self.pyg).saldo_sistema

        SaldoInicialCaja.objects.filter(caja=self.caja, divisa=self.pyg).update(monto=Decimal('5000000.00'))

        detalle_pyg_despues = DetalleArqueoCaja.objects.get(arqueo=arqueo, divisa=self.pyg)
        self.assertEqual(detalle_pyg_despues.saldo_sistema, detalle_pyg_original)
        self.assertNotEqual(self.caja.saldo_actual(self.pyg), detalle_pyg_original)

    # --- Prerequisito: caja abierta ---

    def test_sin_caja_abierta_rechaza_el_arqueo_y_no_ofrece_el_formulario(self):
        """Sin una caja abierta, el arqueo se rechaza (POST) y tampoco se ofrece el formulario (GET)."""
        self.caja.delete()

        with self.subTest('POST rechazado'):
            response = self.client.post(self.url_iniciar, self._datos(), follow=True)

            self.assertContains(response, 'Necesitás abrir una caja')
            self.assertFalse(ArqueoCaja.objects.exists())

        with self.subTest('formulario no ofrecido'):
            response = self.client.get(self.url_iniciar, follow=True)

            self.assertContains(response, 'Necesitás abrir una caja')
            self.assertNotContains(response, 'name="contado_')

    # --- Validaciones del formulario ---

    def test_un_monto_contado_invalido_no_registra_el_arqueo(self):
        """Un monto contado negativo o no numérico se rechaza con el mismo criterio que el resto del sistema."""
        with self.subTest('negativo'):
            response = self.client.post(self.url_iniciar, self._datos(usd='-10.00'))

            self.assertContains(response, 'El monto contado no puede ser negativo.')
            self.assertFalse(ArqueoCaja.objects.exists())

        with self.subTest('no numérico'):
            response = self.client.post(self.url_iniciar, self._datos(usd='abc'))

            self.assertContains(response, 'Ingresá un monto válido.')
            self.assertFalse(ArqueoCaja.objects.exists())

    def test_un_monto_contado_en_cero_es_valido(self):
        """Un monto contado de cero es válido: el cajero no tiene nada físico de esa moneda."""
        response = self.client.post(self.url_iniciar, self._datos(usd='0'), follow=True)

        self.assertContains(response, 'El arqueo se registró correctamente')
        arqueo = ArqueoCaja.objects.get()
        self.assertEqual(arqueo.detalles.get(divisa=self.usd).monto_contado, Decimal('0.00'))

    # --- Una divisa sin cotización no se puede arquear ---

    def test_una_divisa_sin_cotizacion_no_se_ofrece_ni_se_puede_forzar_pero_no_bloquea_arquear(self):
        """Una divisa activa sin cotización no recibe campo, no se puede forzar, y no bloquea el resto."""
        eur = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)

        with self.subTest('no se ofrece el campo'):
            response = self.client.get(self.url_iniciar)

            self.assertNotContains(response, f'name="contado_{eur.pk}"')
            self.assertContains(response, 'EUR')
            self.assertContains(response, 'Hace falta cotizar')
            self.assertContains(response, 'analista cambiario o un administrador')

        with self.subTest('el arqueo funciona igual sin esa divisa'):
            response = self.client.post(self.url_iniciar, self._datos(), follow=True)

            self.assertContains(response, 'El arqueo se registró correctamente')
            arqueo = ArqueoCaja.objects.get()
            self.assertEqual(arqueo.detalles.count(), 2)
            self.assertFalse(arqueo.detalles.filter(divisa=eur).exists())

        with self.subTest('un monto forzado a mano se ignora'):
            ArqueoCaja.objects.all().delete()
            datos = self._datos()
            datos[f'contado_{eur.pk}'] = '1000.00'

            response = self.client.post(self.url_iniciar, datos, follow=True)

            self.assertContains(response, 'El arqueo se registró correctamente')
            arqueo = ArqueoCaja.objects.get()
            self.assertFalse(arqueo.detalles.filter(divisa=eur).exists())

    # --- Permisos ---

    def test_usuario_sin_rol_cajero_no_puede_arquear(self):
        """Solo el rol cajero puede iniciar o consultar un arqueo."""
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response_get = self.client.get(self.url_iniciar)
        response_post = self.client.post(self.url_iniciar, self._datos())
        response_historial = self.client.get(self.url_historial)

        self.assertEqual(response_get.status_code, 403)
        self.assertEqual(response_post.status_code, 403)
        self.assertEqual(response_historial.status_code, 403)
        self.assertFalse(ArqueoCaja.objects.exists())

    def test_usuario_no_autenticado_es_redirigido_al_login(self):
        """Sin sesión iniciada, se redirige al login en vez de registrar el arqueo."""
        self.client.logout()

        response = self.client.get(self.url_iniciar)

        self.assertEqual(response.status_code, 302)

    def test_un_cajero_no_puede_consultar_el_detalle_de_un_arqueo_ajeno(self):
        """El detalle de un arqueo es solo para el cajero que lo registró."""
        self.client.post(self.url_iniciar, self._datos())
        arqueo = ArqueoCaja.objects.get()

        otro_cajero = User.objects.create_user(username='cajero-ajeno', password='password123')
        self.client.logout()
        self.client.login(username='cajero-ajeno', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cajero']
        session.save()

        response = self.client.get(reverse('caja:detalle_arqueo', kwargs={'pk': arqueo.pk}))

        self.assertEqual(response.status_code, 404)


class ArqueoCajaModeloTest(TestCase):
    """Pruebas unitarias de 'ArqueoCaja'/'DetalleArqueoCaja' directamente contra el modelo."""

    def setUp(self):
        """Prepara una caja y una divisa activa."""
        self.cajero = User.objects.create_user(username='cajero-modelo-arqueo', password='password123')
        self.caja = Caja.objects.create(usuario=self.cajero)
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)

    def test_el_signo_de_la_diferencia_indica_sobrante_o_faltante(self):
        """Contado > sistema es un sobrante (positivo); contado < sistema, un faltante (negativo)."""
        with self.subTest('sobrante'):
            arqueo = ArqueoCaja.objects.create(caja=self.caja, cajero=self.cajero)
            detalle = DetalleArqueoCaja.objects.create(
                arqueo=arqueo, divisa=self.usd, saldo_sistema=Decimal('100.00'), monto_contado=Decimal('120.00'),
            )

            self.assertEqual(detalle.diferencia, Decimal('20.00'))

        with self.subTest('faltante'):
            arqueo = ArqueoCaja.objects.create(caja=self.caja, cajero=self.cajero)
            detalle = DetalleArqueoCaja.objects.create(
                arqueo=arqueo, divisa=self.usd, saldo_sistema=Decimal('100.00'), monto_contado=Decimal('80.00'),
            )

            self.assertEqual(detalle.diferencia, Decimal('-20.00'))

    def test_tiene_diferencias_segun_si_algun_detalle_difiere_del_sistema(self):
        """'tiene_diferencias' es False si todo coincide, True si al menos una divisa difiere."""
        with self.subTest('todo coincide'):
            arqueo = ArqueoCaja.objects.create(caja=self.caja, cajero=self.cajero)
            DetalleArqueoCaja.objects.create(
                arqueo=arqueo, divisa=self.usd, saldo_sistema=Decimal('100.00'), monto_contado=Decimal('100.00'),
            )

            self.assertFalse(arqueo.tiene_diferencias)

        with self.subTest('una divisa difiere'):
            arqueo = ArqueoCaja.objects.create(caja=self.caja, cajero=self.cajero)
            DetalleArqueoCaja.objects.create(
                arqueo=arqueo, divisa=self.usd, saldo_sistema=Decimal('100.00'), monto_contado=Decimal('99.00'),
            )

            self.assertTrue(arqueo.tiene_diferencias)

    def test_no_se_puede_duplicar_una_divisa_en_el_mismo_arqueo(self):
        """La restricción única impide dos detalles de la misma divisa en un mismo arqueo."""
        from django.db import IntegrityError

        arqueo = ArqueoCaja.objects.create(caja=self.caja, cajero=self.cajero)
        DetalleArqueoCaja.objects.create(
            arqueo=arqueo, divisa=self.usd, saldo_sistema=Decimal('100.00'), monto_contado=Decimal('100.00'),
        )

        with self.assertRaises(IntegrityError):
            DetalleArqueoCaja.objects.create(
                arqueo=arqueo, divisa=self.usd, saldo_sistema=Decimal('100.00'), monto_contado=Decimal('90.00'),
            )
