import pytest
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from django.conf import settings
from django.shortcuts import resolve_url
from django.utils import timezone
from apps.divisas.models import Divisa, Cotizacion
from apps.authentication.models import HistorialBaja


@pytest.mark.django_db  # Habilita el acceso a la base de datos para pytest
class TasasVigentesTest(TestCase):
    """
    Suite de pruebas para la Historia de Usuario: "Consulta de tasas vigentes".

    Reescrito tras el bugfix de delegación a Keycloak: la autorización
    ya no usa un Group de Django llamado 'Agentes', sino el rol
    'agentes' que backends.py guarda en request.session['keycloak_roles']
    tras el login real contra Keycloak.

    Verifica:
    - Seguridad: Acceso restringido a usuarios con el rol 'analista_cambiario' (Keycloak).
    - CA1: Visualización de tasas de compra y venta.
    - CA2: Indicador de "sin cotización" para divisas sin tasas cargadas.
    - CA3: Visualización de fecha de última actualización.
    - CA4: Ocultamiento de divisas inactivas.
    """

    def setUp(self):
        """
        Configuración inicial para cada prueba.
        Crea usuarios, grupos, divisas y cotizaciones simulando el estado de la base de datos.
        """
        # 1. Configuración de Seguridad
        self.analista = User.objects.create_user(username='analista01', password='password123')

        self.usuario_sin_rol = User.objects.create_user(username='invitado', password='password123')

        # Divisa Activa CON cotización (Para CA1 y CA3)
        self.usd = Divisa.objects.create(codigo='USD', nombre='Dólar', activa=True)
        self.cotizacion_usd = Cotizacion.objects.create(
            divisa=self.usd,
            tasa_compra=7300.50,
            tasa_venta=7400.00
        )

        # Divisa Activa SIN cotización (Para CA2)
        self.eur = Divisa.objects.create(codigo='EUR', nombre='Euro', activa=True)

        # Divisa INACTIVA (Para CA4)
        self.ars = Divisa.objects.create(codigo='ARS', nombre='Peso Argentino', activa=False)

        # URL de la vista
        self.url = reverse('divisas:tasas_vigentes')

    def _login_analista_con_sesion(self):
        """Método auxiliar para loguear e inyectar el rol de Keycloak."""
        self.client.login(username='analista01', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['analista_cambiario']
        session.save()

    def test_acceso_denegado_usuarios_no_autenticados(self):
        """Prueba de seguridad: un usuario anónimo es redirigido al login."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        ruta_login = resolve_url(settings.LOGIN_URL)
        self.assertTrue(ruta_login in response.url)

    def test_acceso_denegado_usuarios_sin_rol(self):
        """
        Prueba de seguridad: Un usuario autenticado pero sin roles en la sesión de Keycloak
        recibe un error 403 (Prohibido).
        """
        self.client.login(username='invitado', password='password123')
        session = self.client.session
        session['keycloak_roles'] = []  # Sin roles permitidos
        session.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_analista_ve_solo_el_acceso_a_actualizar_tasas_en_inicio(self):
        """El analista no administra divisas; solo puede actualizar tasas."""
        self._login_analista_con_sesion()

        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Actualizar tasas')
        self.assertNotContains(response, 'Gestión de divisas')
        self.assertContains(response, self.url)

    def test_ca4_divisas_inactivas_no_se_muestran(self):
        """
        Criterio de Aceptación 4: Las divisas inactivas no deben aparecer en el listado.
        """
        self._login_analista_con_sesion()
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        divisas_en_contexto = response.context['divisas']

        self.assertIn(self.usd, divisas_en_contexto)
        self.assertIn(self.eur, divisas_en_contexto)
        self.assertNotIn(self.ars, divisas_en_contexto, "La divisa inactiva ARS no debería estar en el contexto.")

    def test_ca1_y_ca3_muestra_tasas_y_fecha(self):
        """
        Criterio de Aceptación 1 y 3: Divisas con cotización muestran tasas de compra/venta
        y la fecha de actualización.
        """
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
        """
        Criterio de Aceptación 2: Divisas sin cotización muestran el texto "sin cotización"
        en lugar de valores vacíos o erróneos.
        """
        self._login_analista_con_sesion()
        response = self.client.get(self.url)

        self.assertContains(response, 'EUR')
        self.assertContains(response, 'sin cotización')

    def test_admin_ve_el_boton_nueva_divisa_en_tasas_vigentes(self):
        self.client.logout()
        admin = User.objects.create_user(
            username='admin-tasas', password='password123'
        )
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
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin-divisas', password='password123'
        )
        self.client.login(username='admin-divisas', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['admin']
        session.save()

    def test_admin_registra_divisa_activa_con_datos_obligatorios(self):
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
        divisa = Divisa.objects.create(
            codigo='EUR', nombre='Euro', simbolo='€', activa=True
        )

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
        divisa = Divisa.objects.create(
            codigo='BRL', nombre='Real', simbolo='R$', activa=True
        )
        cotizacion = Cotizacion.objects.create(
            divisa=divisa, tasa_compra=100, tasa_venta=110
        )

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
        activa = Divisa.objects.create(
            codigo='USD', nombre='Dólar', simbolo='$', activa=True
        )
        inactiva = Divisa.objects.create(
            codigo='ARS', nombre='Peso Argentino', simbolo='$', activa=False
        )

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
    def setUp(self):
        self.analista = User.objects.create_user(
            username='analista-cambiario', password='password123'
        )
        self.divisa = Divisa.objects.create(
            codigo='USD', nombre='Dólar', simbolo='$', activa=True
        )
        self.url = reverse(
            'divisas:actualizar_cotizacion',
            kwargs={'divisa_id': self.divisa.pk},
        )
        self.client.login(
            username='analista-cambiario', password='password123'
        )
        session = self.client.session
        session['keycloak_roles'] = ['analista_cambiario']
        session.save()

    def test_analista_ve_el_menu_de_actualizar_tasas(self):
        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Actualizar tasas')
        self.assertContains(response, reverse('divisas:tasas_vigentes'))

    def test_analista_y_agente_comparten_el_acceso_operativo(self):
        response = self.client.get(reverse('divisas:tasas_vigentes'))

        self.assertEqual(response.status_code, 200)

    def test_analista_actualiza_compra_y_venta(self):
        response = self.client.post(
            self.url,
            {'tasa_compra': '7300.50', 'tasa_venta': '7400.00'},
        )

        self.assertEqual(response.status_code, 302)
        cotizacion = Cotizacion.objects.get(divisa=self.divisa)
        self.assertEqual(cotizacion.tasa_compra, 7300.50)
        self.assertEqual(cotizacion.tasa_venta, 7400.00)

    def test_actualizacion_registra_usuario_y_fecha(self):
        response = self.client.post(
            self.url,
            {'tasa_compra': '7300', 'tasa_venta': '7400'},
        )

        self.assertEqual(response.status_code, 302)
        cotizacion = Cotizacion.objects.get(divisa=self.divisa)
        self.assertEqual(cotizacion.usuario, self.analista)
        self.assertIsNotNone(cotizacion.fecha_actualizacion)

    def test_rechaza_compra_mayor_y_valores_no_validos(self):
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
        anterior = Cotizacion.objects.create(
            divisa=self.divisa,
            tasa_compra=7000,
            tasa_venta=7100,
            usuario=self.analista,
        )

        response = self.client.post(
            self.url,
            {'tasa_compra': '7300', 'tasa_venta': '7400'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Cotizacion.objects.filter(divisa=self.divisa).count(), 2)
        anterior.refresh_from_db()
        self.assertEqual(anterior.tasa_compra, 7000)
        self.assertEqual(anterior.tasa_venta, 7100)

    def test_historial_muestra_todas_las_actualizaciones_de_la_divisa(self):
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
            reverse(
                'divisas:historial_cotizaciones',
                kwargs={'divisa_id': self.divisa.pk},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['cotizaciones']), [segunda, primera])
        self.assertContains(response, '7300.00')
        self.assertContains(response, '7000.00')

    def test_usuario_sin_rol_no_puede_actualizar(self):
        session = self.client.session
        session['keycloak_roles'] = []
        session.save()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)


@pytest.mark.django_db
class ConsultaTasasClienteTest(TestCase):
    def test_cliente_visualiza_tasas_actuales_sin_acciones_de_actualizacion(self):
        cliente = User.objects.create_user(
            username='cliente-tasas', password='password123'
        )
        divisa = Divisa.objects.create(
            codigo='EUR', nombre='Euro', simbolo='€', activa=True
        )
        Cotizacion.objects.create(
            divisa=divisa, tasa_compra=7800, tasa_venta=8000
        )
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
            reverse(
                'divisas:actualizar_cotizacion',
                kwargs={'divisa_id': divisa.pk},
            ),
        )
