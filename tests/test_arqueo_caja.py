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
        """Criterio 1: el arqueo compara lo contado contra el saldo registrado y muestra la diferencia."""
        response = self.client.post(
            self.url_iniciar, self._datos(pyg='950000.00', usd='520.00'), follow=True,
        )

        self.assertContains(response, 'El arqueo se registró correctamente')
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

    def test_la_pantalla_de_detalle_muestra_sobrante_y_faltante_por_divisa(self):
        """Criterio 1: el detalle muestra explícitamente el sobrante/faltante de cada moneda."""
        response = self.client.post(
            self.url_iniciar, self._datos(pyg='950000.00', usd='520.00'), follow=True,
        )

        self.assertContains(response, 'Faltante')
        self.assertContains(response, 'Sobrante')

    def test_un_arqueo_sin_diferencias_lo_indica_explicitamente(self):
        """Cuando lo contado coincide exactamente, el detalle lo muestra sin diferencias."""
        response = self.client.post(self.url_iniciar, self._datos(), follow=True)

        self.assertContains(response, 'coincide exactamente')
        arqueo = ArqueoCaja.objects.get()
        self.assertFalse(arqueo.tiene_diferencias)

    # --- Criterio 2 ---

    def test_una_diferencia_distinta_de_cero_no_bloquea_el_registro(self):
        """Criterio 2: una diferencia (sobrante o faltante) se registra igual, sin rechazar el arqueo."""
        response = self.client.post(
            self.url_iniciar, self._datos(pyg='800000.00', usd='300.00'), follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'El arqueo se registró correctamente')
        arqueo = ArqueoCaja.objects.get()
        self.assertTrue(arqueo.tiene_diferencias)

    def test_una_diferencia_no_bloquea_que_la_caja_siga_operando(self):
        """Criterio 2: tras un arqueo con diferencias, la caja sigue aceptando operaciones de ventanilla."""
        self.client.post(self.url_iniciar, self._datos(pyg='800000.00', usd='300.00'))

        url_venta = reverse('caja:registrar_operacion', kwargs={'tipo': 'venta'})
        response = self.client.post(
            url_venta, {'divisa': str(self.usd.pk), 'monto': '50.00'}, follow=True,
        )

        self.assertContains(response, 'La operación se registró correctamente')

    # --- Criterio 3 ---

    def test_el_arqueo_registra_fecha_hora_cajero_y_ambos_montos(self):
        """Criterio 3: el arqueo guardado tiene fecha, hora, cajero y los montos contados y del sistema."""
        self.client.post(self.url_iniciar, self._datos(pyg='950000.00', usd='520.00'))

        arqueo = ArqueoCaja.objects.get()
        self.assertEqual(arqueo.cajero, self.cajero)
        self.assertIsNotNone(arqueo.creado_en)
        self.assertEqual(arqueo.detalles.count(), 2)

    def test_el_arqueo_queda_disponible_para_consulta_posterior_en_el_detalle(self):
        """Criterio 3: tras registrarlo, se puede volver a consultar el detalle del arqueo."""
        self.client.post(self.url_iniciar, self._datos(pyg='950000.00', usd='520.00'))
        arqueo = ArqueoCaja.objects.get()

        response = self.client.get(reverse('caja:detalle_arqueo', kwargs={'pk': arqueo.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, arqueo.cajero.username)
        self.assertContains(response, 'USD')
        self.assertContains(response, 'PYG')

    def test_el_arqueo_aparece_en_el_historial(self):
        """Criterio 3: el arqueo registrado aparece en el historial de consulta posterior."""
        self.client.post(self.url_iniciar, self._datos())
        arqueo = ArqueoCaja.objects.get()

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

    def test_sin_caja_abierta_rechaza_el_arqueo_y_pide_abrir_una(self):
        """Sin una caja abierta, el arqueo se rechaza e indica abrir una primero."""
        self.caja.delete()

        response = self.client.post(self.url_iniciar, self._datos(), follow=True)

        self.assertContains(response, 'Necesitás abrir una caja')
        self.assertFalse(ArqueoCaja.objects.exists())

    def test_sin_caja_abierta_tampoco_se_ofrece_el_formulario(self):
        """Sin una caja abierta, tampoco se puede acceder al formulario de arqueo."""
        self.caja.delete()

        response = self.client.get(self.url_iniciar, follow=True)

        self.assertContains(response, 'Necesitás abrir una caja')
        self.assertNotContains(response, 'name="contado_')

    # --- Validaciones del formulario ---

    def test_un_monto_negativo_no_registra_el_arqueo(self):
        """Un monto contado negativo se rechaza con el mismo criterio que el resto del sistema."""
        response = self.client.post(self.url_iniciar, self._datos(usd='-10.00'))

        self.assertContains(response, 'El monto contado no puede ser negativo.')
        self.assertFalse(ArqueoCaja.objects.exists())

    def test_un_monto_no_numerico_no_registra_el_arqueo(self):
        """Un monto contado no numérico se rechaza sin crear nada."""
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

    def test_una_divisa_activa_sin_cotizacion_no_se_ofrece_para_arquear(self):
        """Una divisa activa sin cotización vigente no recibe un campo en el formulario de arqueo."""
        eur = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)

        response = self.client.get(self.url_iniciar)

        self.assertNotContains(response, f'name="contado_{eur.pk}"')
        self.assertContains(response, 'EUR')
        self.assertContains(response, 'Hace falta cotizar')
        self.assertContains(response, 'analista cambiario o un administrador')

    def test_se_puede_arquear_sin_la_divisa_sin_cotizar(self):
        """Una divisa sin cotizar no bloquea el arqueo: se registra igual con el resto."""
        eur = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)

        response = self.client.post(self.url_iniciar, self._datos(), follow=True)

        self.assertContains(response, 'El arqueo se registró correctamente')
        arqueo = ArqueoCaja.objects.get()
        self.assertEqual(arqueo.detalles.count(), 2)
        self.assertFalse(arqueo.detalles.filter(divisa=eur).exists())

    def test_un_monto_contado_enviado_a_mano_para_una_divisa_sin_cotizar_se_ignora(self):
        """Forzar 'contado_<pk>' de una divisa sin cotizar en el POST no la incluye en el arqueo."""
        eur = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)
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

    def test_diferencia_positiva_es_sobrante(self):
        """Una diferencia positiva (contado > sistema) es un sobrante."""
        arqueo = ArqueoCaja.objects.create(caja=self.caja, cajero=self.cajero)
        detalle = DetalleArqueoCaja.objects.create(
            arqueo=arqueo, divisa=self.usd, saldo_sistema=Decimal('100.00'), monto_contado=Decimal('120.00'),
        )

        self.assertEqual(detalle.diferencia, Decimal('20.00'))

    def test_diferencia_negativa_es_faltante(self):
        """Una diferencia negativa (contado < sistema) es un faltante."""
        arqueo = ArqueoCaja.objects.create(caja=self.caja, cajero=self.cajero)
        detalle = DetalleArqueoCaja.objects.create(
            arqueo=arqueo, divisa=self.usd, saldo_sistema=Decimal('100.00'), monto_contado=Decimal('80.00'),
        )

        self.assertEqual(detalle.diferencia, Decimal('-20.00'))

    def test_tiene_diferencias_es_false_cuando_todo_coincide(self):
        """'tiene_diferencias' es False si ningún detalle difiere del saldo del sistema."""
        arqueo = ArqueoCaja.objects.create(caja=self.caja, cajero=self.cajero)
        DetalleArqueoCaja.objects.create(
            arqueo=arqueo, divisa=self.usd, saldo_sistema=Decimal('100.00'), monto_contado=Decimal('100.00'),
        )

        self.assertFalse(arqueo.tiene_diferencias)

    def test_tiene_diferencias_es_true_si_al_menos_una_divisa_difiere(self):
        """'tiene_diferencias' es True si al menos una divisa tiene diferencia distinta de cero."""
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
