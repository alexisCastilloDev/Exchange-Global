import pytest
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.conf import settings
from django.shortcuts import resolve_url
from apps.divisas.models import Divisa, Cotizacion

User = get_user_model()


def _login_con_roles(client, user, roles):
    """Simula lo que backends.py deja en sesión tras un login real con esos roles."""
    client.force_login(user)
    session = client.session
    session['keycloak_roles'] = roles
    session.save()


@pytest.mark.django_db
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

        self.url = reverse('divisas:tasas_vigentes')

    def test_acceso_denegado_usuarios_no_autenticados(self):
        """Prueba de seguridad: un usuario anónimo es redirigido al login."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        ruta_login = resolve_url(settings.LOGIN_URL)
        self.assertTrue(ruta_login in response.url)

    def test_acceso_denegado_usuarios_sin_rol(self):
        """
        Autenticado pero SIN 'agentes' ni 'admin' en la sesión
        recibe un error 403 (Prohibido).
        """
        _login_con_roles(self.client, self.usuario_sin_rol, roles=[])
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_ca4_divisas_inactivas_no_se_muestran(self):
        """CA4: Las divisas inactivas no deben aparecer en el listado."""
        _login_con_roles(self.client, self.agente, roles=['agentes'])
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        divisas_en_contexto = response.context['divisas']

        self.assertIn(self.usd, divisas_en_contexto)
        self.assertIn(self.eur, divisas_en_contexto)
        self.assertNotIn(self.ars, divisas_en_contexto, "La divisa inactiva ARS no debería estar en el contexto.")

    def test_ca1_y_ca3_muestra_tasas_y_fecha(self):
        """CA1 y CA3: muestra tasas de compra/venta y fecha de actualización."""
        _login_con_roles(self.client, self.agente, roles=['agentes'])
        response = self.client.get(self.url)

        self.assertContains(response, '7300.50')
        self.assertContains(response, '7400.00')
        self.assertContains(response, 'USD')

    def test_ca2_divisa_sin_cotizacion_muestra_mensaje(self):
        """CA2: divisas sin cotización muestran el texto "sin cotización"."""
        _login_con_roles(self.client, self.agente, roles=['agentes'])
        response = self.client.get(self.url)

        self.assertContains(response, 'EUR')
        self.assertContains(response, 'sin cotización')