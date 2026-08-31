import pytest
from django.contrib.auth import get_user_model
from apps.clientes.models import Cliente
from apps.clientes.forms import ClienteForm

User = get_user_model()

@pytest.mark.django_db
class TestClienteForm:

    def test_registro_persona_fisica_exitoso(self):
        """Criterio: Registra exitosamente si el documento CI pertenece a un usuario existente"""
        User.objects.create_user(username='1234567', email='juan.perez@test.com')
        datos = {
            'tipo_cliente': 'FISICA',
            'nombre': 'Juan',
            'apellido': 'Pérez',
            'identificador': '1234567',
            'email': 'juan.perez@test.com'
        }
        form = ClienteForm(data=datos)
        assert form.is_valid() is True
        cliente = form.save()
        assert cliente.user.username == '1234567'

    def test_rechazo_si_no_existe_usuario_con_documento(self):
        """Criterio: Muestra error si la CI/RUC no pertenece a ningún usuario del sistema"""
        datos = {
            'tipo_cliente': 'FISICA',
            'nombre': 'Carlos',
            'apellido': 'López',
            'identificador': '9999999',
            'email': 'carlos@test.com'
        }
        form = ClienteForm(data=datos)
        assert form.is_valid() is False
        assert 'identificador' in form.errors

    def test_registro_persona_juridica_exitoso(self):
        """Criterio: Registra persona jurídica si el RUC coincide con un usuario registrado"""
        User.objects.create_user(username='80012345-6', email='contacto@empresa.com')
        datos = {
            'tipo_cliente': 'JURIDICA',
            'razon_social': 'Empresa SA',
            'identificador': '80012345-6',
            'email': 'contacto@empresa.com'
        }
        form = ClienteForm(data=datos)
        assert form.is_valid() is True

    def test_error_campos_obligatorios_vacios_fisica(self):
        """Criterio: Dejar campos requeridos vacíos muestra errores de validación"""
        User.objects.create_user(username='1234567', email='inc@test.com')
        datos = {
            'tipo_cliente': 'FISICA',
            'identificador': '1234567'
        }
        form = ClienteForm(data=datos)
        assert form.is_valid() is False
        assert 'nombre' in form.errors
        assert 'apellido' in form.errors

    def test_rechazo_registro_usuario_ya_vinculado(self):
        """Criterio: Rechaza el registro si el usuario con ese documento ya posee perfil de cliente"""
        u1 = User.objects.create_user(username='5555555', email='ana@test.com')
        Cliente.objects.create(
            user=u1,
            tipo_cliente='FISICA',
            nombre='Ana',
            apellido='Gómez',
            identificador='5555555',
            email='ana@test.com'
        )

        datos = {
            'tipo_cliente': 'FISICA',
            'nombre': 'Ana María',
            'apellido': 'Gómez',
            'identificador': '5555555',
            'email': 'ana.otra@test.com'
        }
        form = ClienteForm(data=datos)
        assert form.is_valid() is False
        assert 'identificador' in form.errors


@pytest.mark.django_db
class TestClienteView:

    def test_acceso_denegado_a_usuario_comun(self, client):
        usuario = User.objects.create_user(
            username='user_normal',
            email='user@test.com',
            is_staff=False
        )
        client.force_login(usuario)
        response = client.get('/clientes/nuevo/')
        assert response.status_code == 403

    def test_acceso_permitido_a_administrador(self, client):
        admin = User.objects.create_user(
            username='admin_user',
            email='admin@test.com',
            is_staff=True
        )
        client.force_login(admin)
        response = client.get('/clientes/nuevo/')
        assert response.status_code == 200