"""Pruebas de tasas, administración, historial y simulación de divisas."""

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.shortcuts import resolve_url
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.authentication.models import HistorialBaja
from apps.divisas.models import Cotizacion, Divisa


@pytest.mark.django_db
class TasasVigentesTest(TestCase):
    """Verifica permisos y contenido de las tasas vigentes."""
    """
    Suite de pruebas para la Historia de Usuario: "Consulta de tasas vigentes".
    Verifica:
    - Seguridad: acceso restringido a usuarios con rol autorizado.
    - CA1: Visualización de tasas de compra y venta.
    - CA2: Indicador de "sin cotización".
    - CA3: Fecha de última actualización.
    - CA4: Ocultamiento de divisas inactivas.
    """

    def setUp(self):
        """Prepara usuarios, divisas y cotizaciones de consulta."""
        self.analista = User.objects.create_user(username='analista01', password='password123')
        self.usuario_sin_rol = User.objects.create_user(username='invitado', password='password123')

        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', activa=True)
        self.cotizacion_usd = Cotizacion.objects.create(
            divisa=self.usd,
            tasa_compra=7300.50,
            tasa_venta=7400.00,
        )

        self.eur = Divisa.objects.create(codigo='EUR', nombre='Euro', activa=True)
        self.ars = Divisa.objects.create(codigo='ARS', nombre='Peso Argentino', activa=False)

        self.url = reverse('divisas:tasas_vigentes')

    def _login_analista_con_sesion(self):
        """Inicia sesión de prueba con el rol de analista cambiario."""
        self.client.login(username='analista01', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['analista_cambiario']
        session.save()

    def test_acceso_denegado_usuarios_no_autenticados(self):
        """Redirige al login a usuarios sin autenticación."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        ruta_login = resolve_url(settings.LOGIN_URL)
        self.assertTrue(ruta_login in response.url)

    def test_acceso_denegado_usuarios_sin_rol(self):
        """Deniega tasas a usuarios sin rol operativo."""
        self.client.login(username='invitado', password='password123')
        session = self.client.session
        session['keycloak_roles'] = []
        session.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_analista_ve_solo_el_acceso_a_actualizar_tasas_en_inicio(self):
        """Muestra al analista el acceso operativo correspondiente."""
        self._login_analista_con_sesion()
        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Actualizar tasas')
        self.assertNotContains(response, 'Gestión de divisas')
        self.assertContains(response, self.url)

    def test_ca4_divisas_inactivas_no_se_muestran(self):
        """Oculta divisas inactivas de las tasas vigentes."""
        self._login_analista_con_sesion()
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        divisas_en_contexto = response.context['divisas']
        self.assertIn(self.usd, divisas_en_contexto)
        self.assertIn(self.eur, divisas_en_contexto)
        self.assertNotIn(self.ars, divisas_en_contexto, 'La divisa inactiva ARS no debería estar en el contexto.')

    def test_ca1_y_ca3_muestra_tasas_y_fecha(self):
        """Muestra tasas actuales y fecha de actualización."""
        self._login_analista_con_sesion()
        response = self.client.get(self.url)

        self.assertContains(response, '7300.50')
        self.assertContains(response, '7400.00')
        self.assertContains(response, 'USD')
        self.assertContains(
            response,
            self.cotizacion_usd.fecha_actualizacion.astimezone(
                timezone.get_current_timezone()
            ).strftime('%d/%m/%Y %H:%M'),
        )

    def test_ca2_divisa_sin_cotizacion_muestra_mensaje(self):
        """Informa cuando una divisa aún no tiene cotización."""
        self._login_analista_con_sesion()
        response = self.client.get(self.url)

        self.assertContains(response, 'EUR')
        self.assertContains(response, 'sin cotización')

    def test_admin_ve_el_boton_nueva_divisa_en_tasas_vigentes(self):
        """Muestra la acción de alta únicamente al administrador."""
        self.client.logout()
        User.objects.create_user(username='admin-tasas', password='password123')
        self.client.login(username='admin-tasas', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nueva divisa')
        self.assertContains(response, reverse('divisas:crear_divisa'))


@pytest.mark.django_db
class AdministracionDivisasTest(TestCase):
    """Verifica altas, ediciones, bajas y listado administrativo."""
    def setUp(self):
        """Prepara un administrador y una divisa editable."""
        self.admin = User.objects.create_user(
            username='admin-divisas', password='password123'
        )
        self.client.login(username='admin-divisas', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

    def test_admin_registra_divisa_activa_con_datos_obligatorios(self):
        """Registra una divisa activa con datos válidos."""
        response = self.client.post(
            reverse('divisas:crear_divisa'),
            {'codigo': 'PYG', 'nombre': 'Guaraní', 'simbolo': '₲'},
        )

        self.assertEqual(response.status_code, 302)
        divisa = Divisa.objects.get(codigo='PYG')
        self.assertEqual(divisa.nombre, 'Guaraní')
        self.assertEqual(divisa.simbolo, '₲')
        self.assertTrue(divisa.activa)

    def test_registro_rechaza_codigo_iso_duplicado(self):
        """Rechaza códigos ISO ya existentes."""
        Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$')

        response = self.client.post(
            reverse('divisas:crear_divisa'),
            {'codigo': 'USD', 'nombre': 'Dólar duplicado', 'simbolo': '$'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context['form'],
            'codigo',
            'Ya existe una divisa con este código ISO.',
        )

    def test_registro_rechaza_campos_vacios_y_codigo_invalido(self):
        """Rechaza datos obligatorios vacíos o códigos inválidos."""
        response = self.client.post(
            reverse('divisas:crear_divisa'),
            {'codigo': 'us', 'nombre': '', 'simbolo': ''},
        )

        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertIn('codigo', form.errors)
        self.assertIn('nombre', form.errors)
        self.assertIn('simbolo', form.errors)

    def test_admin_edita_datos_de_una_divisa(self):
        """Permite actualizar los datos de una divisa."""
        divisa = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)

        response = self.client.post(
            reverse('divisas:editar_divisa', kwargs={'pk': divisa.pk}),
            {
                'codigo': 'EUR',
                'nombre': 'Euro actualizado',
                'simbolo': '€',
                'activa': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        divisa.refresh_from_db()
        self.assertEqual(divisa.nombre, 'Euro actualizado')

    def test_inactivar_conserva_historial_y_no_aparece_en_tasas(self):
        """Conserva historial al inactivar una divisa y la oculta de tasas."""
        divisa = Divisa.objects.create(codigo='BRL', nombre='Real', simbolo='R$', activa=True)
        cotizacion = Cotizacion.objects.create(divisa=divisa, tasa_compra=100, tasa_venta=110)

        response = self.client.post(
            reverse('divisas:baja_divisa', kwargs={'pk': divisa.pk}),
            {'causa': 'Moneda fuera de operacion'},
        )

        self.assertEqual(response.status_code, 302)
        divisa.refresh_from_db()
        self.assertFalse(divisa.activa)
        self.assertTrue(Cotizacion.objects.filter(pk=cotizacion.pk).exists())
        registro = HistorialBaja.objects.get(
            tipo_recurso=HistorialBaja.TIPO_DIVISA,
            recurso_id=divisa.pk,
        )
        self.assertEqual(registro.causa, 'Moneda fuera de operacion')

        historial = self.client.get(reverse('divisas:historial_bajas'))
        self.assertEqual(historial.status_code, 200)
        self.assertContains(historial, 'Moneda fuera de operacion')

        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()
        tasas = self.client.get(reverse('divisas:tasas_vigentes'))
        self.assertNotIn(divisa, tasas.context['divisas'])

    def test_listado_admin_muestra_codigo_nombre_simbolo_y_estado(self):
        """Muestra los datos principales y estado en el catálogo."""
        activa = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        inactiva = Divisa.objects.create(codigo='ARS', nombre='Peso Argentino', simbolo='$', activa=False)

        response = self.client.get(reverse('divisas:lista_divisas'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, activa.codigo)
        self.assertContains(response, activa.nombre)
        self.assertContains(response, activa.simbolo)
        self.assertContains(response, 'Activo')
        self.assertContains(response, inactiva.codigo)
        self.assertContains(response, inactiva.nombre)
        self.assertContains(response, 'Inactivo')


@pytest.mark.django_db
class ActualizacionCotizacionesTest(TestCase):
    """Verifica actualización y trazabilidad de cotizaciones."""
    def setUp(self):
        """Prepara una divisa y usuarios con roles operativos."""
        self.analista = User.objects.create_user(username='analista-cambiario', password='password123')
        self.divisa = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        self.url = reverse('divisas:actualizar_cotizacion', kwargs={'divisa_id': self.divisa.pk})
        self.client.login(username='analista-cambiario', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['analista_cambiario']
        session.save()

    def test_analista_ve_el_menu_de_actualizar_tasas(self):
        """Muestra actualización de tasas al analista autorizado."""
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Actualizar tasas')
        self.assertContains(response, reverse('divisas:tasas_vigentes'))

    def test_analista_tiene_acceso_operativo(self):
        """Verifica el acceso operativo exclusivo del analista cambiario."""
        response = self.client.get(reverse('divisas:tasas_vigentes'))
        self.assertEqual(response.status_code, 200)

    def test_analista_actualiza_compra_y_venta(self):
        """Guarda tasas de compra y venta válidas."""
        response = self.client.post(self.url, {'tasa_compra': '7300.50', 'tasa_venta': '7400.00'})
        self.assertEqual(response.status_code, 302)
        cotizacion = Cotizacion.objects.get(divisa=self.divisa)
        self.assertEqual(cotizacion.tasa_compra, 7300.50)
        self.assertEqual(cotizacion.tasa_venta, 7400.00)

    def test_actualizacion_registra_usuario_y_fecha(self):
        """Registra el usuario y momento de cada cotización."""
        response = self.client.post(self.url, {'tasa_compra': '7300', 'tasa_venta': '7400'})
        self.assertEqual(response.status_code, 302)
        cotizacion = Cotizacion.objects.get(divisa=self.divisa)
        self.assertEqual(cotizacion.usuario, self.analista)
        self.assertIsNotNone(cotizacion.fecha_actualizacion)

    def test_rechaza_compra_mayor_y_valores_no_validos(self):
        """Rechaza tasas negativas o una compra mayor que la venta."""
        for datos in [
            {'tasa_compra': '7500', 'tasa_venta': '7400'},
            {'tasa_compra': '-1', 'tasa_venta': '7400'},
            {'tasa_compra': '7300', 'tasa_venta': '0'},
        ]:
            response = self.client.post(self.url, datos)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.context['form'].is_valid())
        self.assertEqual(Cotizacion.objects.filter(divisa=self.divisa).count(), 0)

    def test_nueva_actualizacion_conserva_la_anterior_en_historial(self):
        """Conserva la cotización anterior al registrar otra."""
        anterior = Cotizacion.objects.create(
            divisa=self.divisa,
            tasa_compra=7000,
            tasa_venta=7100,
            usuario=self.analista,
        )

        response = self.client.post(self.url, {'tasa_compra': '7300', 'tasa_venta': '7400'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Cotizacion.objects.filter(divisa=self.divisa).count(), 2)
        anterior.refresh_from_db()
        self.assertEqual(anterior.tasa_compra, 7000)
        self.assertEqual(anterior.tasa_venta, 7100)

    def test_historial_muestra_todas_las_actualizaciones_de_la_divisa(self):
        """Lista todas las cotizaciones históricas de la divisa."""
        primera = Cotizacion.objects.create(
            divisa=self.divisa,
            tasa_compra=7000,
            tasa_venta=7100,
            usuario=self.analista,
        )
        segunda = Cotizacion.objects.create(
            divisa=self.divisa,
            tasa_compra=7300,
            tasa_venta=7400,
            usuario=self.analista,
        )

        response = self.client.get(
            reverse('divisas:historial_cotizaciones', kwargs={'divisa_id': self.divisa.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['cotizaciones']), [segunda, primera])
        self.assertContains(response, '7300.00')
        self.assertContains(response, '7000.00')

    def test_usuario_sin_rol_no_puede_actualizar(self):
        """Deniega actualización a usuarios sin rol autorizado."""
        session = self.client.session
        session['keycloak_roles'] = []
        session.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)


@pytest.mark.django_db
class ConsultaTasasClienteTest(TestCase):
    """Verifica la consulta de tasas por un cliente."""
    def test_cliente_visualiza_tasas_actuales_sin_acciones_de_actualizacion(self):
        """Permite consultar tasas al cliente sin acciones administrativas."""
        cliente = User.objects.create_user(username='cliente-tasas', password='password123')
        divisa = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)
        Cotizacion.objects.create(divisa=divisa, tasa_compra=7800, tasa_venta=8000)
        self.client.login(username='cliente-tasas', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['cliente']
        session.save()

        response = self.client.get(reverse('divisas:tasas_vigentes'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tasas actuales')
        self.assertContains(response, '7800.00')
        self.assertNotContains(
            response,
            reverse('divisas:actualizar_cotizacion', kwargs={'divisa_id': divisa.pk}),
        )


@pytest.mark.django_db
class SimuladorDivisasTest(TestCase):
    """Verifica conversiones, PYG implícito y validaciones del simulador."""
    def setUp(self):
        """Prepara divisas y tasas para las conversiones."""
        self.analista = User.objects.create_user(username='analista-sim', password='password123')
        self.client.login(username='analista-sim', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['analista_cambiario']
        session.save()

        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', simbolo='$', activa=True)
        self.eur = Divisa.objects.create(codigo='EUR', nombre='Euro', simbolo='€', activa=True)
        self.pyg = Divisa.objects.create(codigo='PYG', nombre='Guaraní', simbolo='₲', activa=True)

        Cotizacion.objects.create(divisa=self.usd, tasa_compra=7300.00, tasa_venta=7400.00)
        Cotizacion.objects.create(divisa=self.eur, tasa_compra=7900.00, tasa_venta=8100.00)
        Cotizacion.objects.create(divisa=self.pyg, tasa_compra=1.00, tasa_venta=1.00)

    def test_simulacion_calcula_monto_resultante_con_tasa_vigente(self):
        """Calcula el monto resultante usando una tasa vigente."""
        response = self.client.post(
            reverse('divisas:simulacion_divisas'),
            {'monto': '100', 'divisa_origen': str(self.usd.pk), 'divisa_destino': str(self.eur.pk)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Monto origen')
        self.assertContains(response, 'Tasa aplicada')
        self.assertContains(response, 'Monto final')
        self.assertContains(response, '93.67')

    def test_simulacion_incluye_guarani_implicitamente_en_las_opciones(self):
        """Incluye PYG aunque no exista como registro persistido."""
        response = self.client.get(reverse('divisas:simulacion_divisas'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Guaraní (PYG)')

    def test_simulacion_calcula_conversion_con_guarani_implicitamente(self):
        """Calcula conversiones que involucran el guaraní implícito."""
        response = self.client.post(
            reverse('divisas:simulacion_divisas'),
            {'monto': '100', 'divisa_origen': str(self.usd.pk), 'divisa_destino': 'PYG'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '740000.00')

    def test_simulacion_rechaza_divisa_sin_tasa_vigente(self):
        """Informa cuando una divisa no tiene una tasa vigente."""
        divisa_sin_tasa = Divisa.objects.create(codigo='BRL', nombre='Real', simbolo='R$', activa=True)

        response = self.client.post(
            reverse('divisas:simulacion_divisas'),
            {'monto': '100', 'divisa_origen': str(self.usd.pk), 'divisa_destino': str(divisa_sin_tasa.pk)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'no tiene tasa disponible')

    def test_simulacion_rechaza_monto_invalido(self):
        """Rechaza montos nulos o negativos en la simulación."""
        response = self.client.post(
            reverse('divisas:simulacion_divisas'),
            {'monto': '0', 'divisa_origen': str(self.usd.pk), 'divisa_destino': str(self.eur.pk)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'El monto debe ser mayor que cero')
