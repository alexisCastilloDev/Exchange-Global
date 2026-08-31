from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class MenuNavegacionTest(TestCase):

    def setUp(self):
        self.url_home = reverse('home')

        # Usuario Cliente
        self.user_cliente = User.objects.create_user(
            username='cliente_test',
            first_name='Juan',
            last_name='Perez',
            email='cliente@test.com',
        )

        # Usuario Administrador (Nombre de grupo: 'admin')
        self.user_admin = User.objects.create_user(
            username='admin_test',
            first_name='Carlos',
            last_name='Admin',
            email='admin@test.com',
            is_staff=True,
            is_superuser=True,
        )
        group_admin, _ = Group.objects.get_or_create(name='admin')
        self.user_admin.groups.add(group_admin)

        permisos = Permission.objects.all()
        self.user_admin.user_permissions.set(permisos)
        self.user_admin.save()

    def test_menu_usuario_anonimo(self):
        """CA1 & CA2: Usuario no autenticado ve la opción 'Inicio' y 'Iniciar Sesión'"""
        response = self.client.get(self.url_home)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Inicio')
        self.assertContains(response, 'Iniciar Sesión con Keycloak SSO')
        self.assertNotContains(response, 'Gestión de Usuarios')

    def test_menu_usuario_cliente_no_ve_gestion_usuarios(self):
        """CA2: Usuario autenticado sin rol Administrador NO ve la opción de administración"""
        self.client.force_login(self.user_cliente)
        response = self.client.get(self.url_home)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cerrar sesión')
        self.assertNotContains(response, 'Gestión de Usuarios')

    def test_menu_usuario_admin_ve_gestion_usuarios(self):
        """CA1 & CA2: Usuario con rol 'Administrador' VE la opción 'Gestión de Usuarios'"""
        self.client.force_login(self.user_admin)
        response = self.client.get(self.url_home)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Gestión de Usuarios')

    @patch('mozilla_django_oidc.middleware.SessionRefresh.process_request', return_value=None)
    def test_redireccion_opcion_menu(self, mock_oidc):
        """CA3: Al hacer clic en una opción del menú redirige correctamente (Status 200)"""
        self.client.force_login(
            self.user_admin,
            backend='apps.authentication.backends.KeycloakOIDCAuthenticationBackend'
        )

        session = self.client.session
        session['oidc_id_token'] = 'fake_id_token'
        session['oidc_access_token'] = 'fake_access_token'
        session.save()

        url_gestion = reverse('lista_usuarios')
        response = self.client.get(url_gestion, follow=True)
        self.assertEqual(response.status_code, 200)