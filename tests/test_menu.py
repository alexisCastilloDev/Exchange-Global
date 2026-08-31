from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

User = get_user_model()

class MenuNavegacionTest(TestCase):

    def setUp(self):
        # Crear roles / grupos de prueba
        self.grupo_admin = Group.objects.create(name='Administrador')
        self.grupo_cliente = Group.objects.create(name='Cliente')

        # 1. Usuario Anónimo (no se crea en BD)
        
        # 2. Usuario Estándar / Cliente (Sin rol de administración)
        self.user_cliente = User.objects.create_user(
            username='cliente',
            email='cliente@test.com',
            first_name='Juan',
            last_name='Perez'
        )
        self.user_cliente.groups.add(self.grupo_cliente)

        # 3. Usuario Administrador
        self.user_admin = User.objects.create_user(
            username='admin',
            email='admin@test.com',
            first_name='Carlos',
            last_name='Admin'
        )
        self.user_admin.groups.add(self.grupo_admin)

        # URL de la página de inicio
        self.url_home = reverse('home')  # Ajusta al nombre de tu URL principal

    def test_menu_usuario_anonimo(self):
        """CA1 & CA2: Usuario no autenticado ve el menú básico y no ve 'Gestión de Usuarios'"""
        response = self.client.get(self.url_home)
        self.assertEqual(response.status_code, 200)
        
        # Debe ver opciones públicas
        self.assertContains(response, 'Inicio')
        self.assertContains(response, 'Cotizaciones')
        self.assertContains(response, 'Iniciar Sesión con Keycloak SSO')
        
        # NO debe ver opciones administrativas
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
        self.assertContains(response, reverse('lista_usuarios'))

    def test_redireccion_opcion_menu(self):
        """CA3: Al hacer clic en una opción del menú redirige correctamente (Status 200)"""
        self.client.force_login(self.user_admin)
        
        # Navega a la lista de usuarios desde la URL expuesta en el menú
        url_gestion = reverse('lista_usuarios')
        response = self.client.get(url_gestion)
        
        self.assertEqual(response.status_code, 200)