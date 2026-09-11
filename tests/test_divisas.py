import pytest
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from django.conf import settings
from django.shortcuts import resolve_url
from apps.divisas.models import Divisa, Cotizacion


User = get_user_model()


@pytest.mark.django_db  # Habilita el acceso a la base de datos para pytest
class TasasVigentesTest(TestCase):
    """
    Suite de pruebas para la Historia de Usuario: "Consulta de tasas vigentes".

    Reescrito tras el bugfix de delegación a Keycloak: la autorización
    ya no usa un Group de Django llamado 'Agentes', sino el rol
    'agentes' que backends.py guarda en request.session['keycloak_roles']
    tras el login real contra Keycloak.

    Verifica:
    - Seguridad: acceso restringido a usuarios con el rol 'agentes' (o 'admin') en sesión.
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
        self.grupo_agentes = Group.objects.create(name='Agentes')
        self.agente = User.objects.create_user(username='agente01', password='password123')
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

    def _login_agente_con_sesion(self):
        """Método auxiliar para loguear e inyectar los roles en la sesión de Keycloak."""
        self.client.login(username='agente01', password='password123')
        session = self.client.session
        session['keycloak_roles'] = ['agente', 'Agentes']
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

    def test_agente_ve_el_acceso_a_gestion_de_divisas_en_inicio(self):
        """Un agente autenticado puede llegar a la pantalla desde el inicio."""
        self._login_agente_con_sesion()

        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Gestión de divisas')
        self.assertContains(response, self.url)

    def test_ca4_divisas_inactivas_no_se_muestran(self):
        """
        Criterio de Aceptación 4: Las divisas inactivas no deben aparecer en el listado.
        """
        self._login_agente_con_sesion()
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
        self._login_agente_con_sesion()
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
        self._login_agente_con_sesion()
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
            reverse('divisas:editar_divisa', kwargs={'pk': divisa.pk}),
            {
                'codigo': 'BRL',
                'nombre': 'Real',
                'simbolo': 'R$',
            },
        )

        self.assertEqual(response.status_code, 302)
        divisa.refresh_from_db()
        self.assertFalse(divisa.activa)
        self.assertTrue(Cotizacion.objects.filter(pk=cotizacion.pk).exists())

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