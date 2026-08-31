import pytest
from django.contrib.auth import get_user_model
from apps.clientes.models import Cliente
from apps.clientes.forms import ClienteForm

User = get_user_model()

@pytest.mark.django_db
class TestClienteForm:

    def test_registro_persona_fisica_exitoso(self):
        """Criterio: Completar datos obligatorios de persona física con usuario existente"""
        usuario = User.objects.create_user(username='usr_fisica', email='fisica@test.com')
        datos = {
            'user': usuario.id,
            'tipo_cliente': 'FISICA',
            'nombre': 'Juan',
            'apellido': 'Pérez',
            'identificador': '1234567'
        }
        form = ClienteForm(data=datos)
        assert form.is_valid() is True

    def test_registro_persona_juridica_exitoso(self):
        """Criterio: Completar datos obligatorios de persona jurídica con usuario existente"""
        usuario = User.objects.create_user(username='usr_juridica', email='empresa@test.com')
        datos = {
            'user': usuario.id,
            'tipo_cliente': 'JURIDICA',
            'razon_social': 'Empresa SA',
            'identificador': '80012345-6'
        }
        form = ClienteForm(data=datos)
        assert form.is_valid() is True

    def test_error_campos_obligatorios_vacios_fisica(self):
        """Criterio: Dejar campos vacíos muestra errores de validación"""
        usuario = User.objects.create_user(username='usr_incompleto', email='inc@test.com')
        datos = {
            'user': usuario.id,
            'tipo_cliente': 'FISICA',
            'identificador': '1234567'
        }
        form = ClienteForm(data=datos)
        assert form.is_valid() is False
        assert 'nombre' in form.errors
        assert 'apellido' in form.errors

    def test_rechazo_registro_por_duplicado(self):
        """Criterio: Identificador (CI/RUC) ya existente rechaza el registro"""
        u1 = User.objects.create_user(username='u1', email='u1@test.com')
        u2 = User.objects.create_user(username='u2', email='u2@test.com')

        Cliente.objects.create(
            user=u1,
            tipo_cliente='FISICA',
            nombre='Ana',
            apellido='Gómez',
            identificador='9999999'
        )

        datos = {
            'user': u2.id,
            'tipo_cliente': 'FISICA',
            'nombre': 'Carlos',
            'apellido': 'López',
            'identificador': '9999999'  # Identificador duplicado
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