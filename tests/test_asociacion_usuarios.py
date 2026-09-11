from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch
from apps.clientes.models import Cliente

User = get_user_model()


class AsociacionUsuarioClienteTest(TestCase):

    def setUp(self):
        # 1. Crear Administrador para acceder a las vistas
        self.admin_user = User.objects.create_superuser(
            username='admin_test',
            email='admin@test.com',
            password='Password123!',
        )

        # 2. Crear Usuarios de prueba (Operadores)
        self.usuario_1 = User.objects.create_user(
            username='operador1',
            email='operador1@test.com',
            password='Password123!',
        )
        self.usuario_2 = User.objects.create_user(
            username='operador2',
            email='operador2@test.com',
            password='Password123!',
        )

        # 3. Crear Usuario titular del cliente
        self.user_titular = User.objects.create_user(
            username='1234567',
            email='juan@test.com',
            password='Password123!',
        )

        # 4. Crear Cliente de prueba asociándole obligatoriamente su `user`
        self.cliente = Cliente.objects.create(
            user=self.user_titular,
            tipo_cliente='FISICA',
            identificador='1234567',
            nombre='Juan',
            apellido='Pérez',
            email='juan@test.com',
        )

        # Autenticar como administrador
        self.client.login(username='admin_test', password='Password123!')

        # La elegibilidad se consulta a Keycloak; para estas pruebas se
        # simulan los roles retornados por la sincronización.
        self.roles_keycloak = patch(
            'apps.clientes.views.sincronizar_usuarios_desde_keycloak',
            return_value={
                self.usuario_1.pk: ['cliente'],
                self.usuario_2.pk: ['cliente'],
                self.user_titular.pk: ['cliente'],
            },
        )
        self.roles_keycloak.start()

    def tearDown(self):
        self.roles_keycloak.stop()
        super().tearDown()

    def test_criterio_1_asociar_usuario_a_cliente(self):
        """Dado que selecciono un cliente, al asociar un usuario, queda vinculado en la relación M2M."""
        url = reverse(
            'cliente_asociar_usuarios', kwargs={'pk': self.cliente.pk}
        )

        # Asociar usuario_1
        data = {'usuarios': [self.usuario_1.pk]}
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 302)  # Redirección exitosa
        self.assertIn(self.usuario_1, self.cliente.usuarios.all())
        self.assertEqual(self.cliente.usuarios.count(), 1)

    def test_criterio_2_ver_listado_usuarios_en_panel(self):
        """Dado que un cliente tiene usuarios asociados, se visualizan en la vista del panel."""
        # Asociar previamente
        self.cliente.usuarios.add(self.usuario_1, self.usuario_2)

        url = reverse('panel_admin')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'operador1')
        self.assertContains(response, 'operador2')

    def test_ficha_preselecciona_todos_los_usuarios_asociados(self):
        """La ficha muestra como seleccionados todos los usuarios vinculados."""
        self.cliente.usuarios.add(self.usuario_1, self.usuario_2)

        url = reverse(
            'cliente_asociar_usuarios', kwargs={'pk': self.cliente.pk}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        usuarios_iniciales = response.context['form'].initial['usuarios']
        self.assertCountEqual(
            usuarios_iniciales,
            [self.usuario_1, self.usuario_2],
        )
        self.assertContains(response, 'operador1')
        self.assertContains(response, 'operador2')

    def test_criterio_3_revocar_asociacion_usuario(self):
        """Dado que un cliente tiene usuarios asociados, al desmarcarlo se remueve el acceso."""
        # Inicialmente el cliente tiene 2 usuarios asociados
        self.cliente.usuarios.add(self.usuario_1, self.usuario_2)
        self.assertEqual(self.cliente.usuarios.count(), 2)

        # POST enviando únicamente el usuario_2 (revocando usuario_1)
        url = reverse(
            'cliente_asociar_usuarios', kwargs={'pk': self.cliente.pk}
        )
        data = {'usuarios': [self.usuario_2.pk]}
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 302)
        # Verificar que el usuario_1 ya NO está asociado
        self.assertNotIn(self.usuario_1, self.cliente.usuarios.all())
        # Verificar que el usuario_2 se mantiene
        self.assertIn(self.usuario_2, self.cliente.usuarios.all())
        self.assertEqual(self.cliente.usuarios.count(), 1)

    def test_seguridad_usuario_no_admin_no_puede_asociar(self):
        """Un usuario normal/no staff no debe tener acceso a asociar usuarios."""
        self.client.logout()
        self.client.login(username='operador1', password='Password123!')

        url = reverse(
            'cliente_asociar_usuarios', kwargs={'pk': self.cliente.pk}
        )
        response = self.client.get(url)

        # Debe denegar el acceso (403 Forbidden) o redirigir
        self.assertIn(response.status_code, [403, 302])

    def test_solo_usuarios_con_rol_cliente_pueden_vincularse(self):
        usuario_sin_rol = User.objects.create_user(
            username='operador-sin-rol',
            email='operador-sin-rol@test.com',
            password='Password123!',
        )
        url = reverse(
            'cliente_asociar_usuarios', kwargs={'pk': self.cliente.pk}
        )

        response = self.client.get(url)
        self.assertContains(response, 'operador1')
        self.assertNotContains(response, 'operador-sin-rol')

        response = self.client.post(url, {'usuarios': [usuario_sin_rol.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.cliente.usuarios.exists())
