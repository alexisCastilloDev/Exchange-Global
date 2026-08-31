import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.clientes.models import Cliente
from apps.clientes.forms import ClienteForm

User = get_user_model()

# Esta etiqueta le dice a pytest que estas pruebas necesitan acceso a la base de datos
pytestmark = pytest.mark.django_db


class TestClienteForm:
    """ Pruebas para los Criterios de Aceptación 1, 2, 3 y 4 a nivel de Formulario """

    def test_registro_persona_fisica_exitoso(self):
        """ Criterio: Completar datos obligatorios de persona física registra correctamente """
        datos = {
            'tipo_cliente': 'FISICA',
            'nombres': 'Juan',
            'apellidos': 'Pérez',
            'identificador': '1234567'
        }
        form = ClienteForm(data=datos)
        assert form.is_valid() is True

    def test_registro_persona_juridica_exitoso(self):
        """ Criterio: Completar datos específicos de persona jurídica registra correctamente """
        datos = {
            'tipo_cliente': 'JURIDICA',
            'razon_social': 'Mi Empresa S.A.',
            'identificador': '80012345-6'
        }
        form = ClienteForm(data=datos)
        assert form.is_valid() is True

    def test_error_campos_obligatorios_vacios_fisica(self):
        """ Criterio: Dejar campos vacíos muestra errores de validación """
        datos = {
            'tipo_cliente': 'FISICA',
            'identificador': '1234567'
            # Faltan nombres y apellidos
        }
        form = ClienteForm(data=datos)
        assert form.is_valid() is False
        assert 'nombres' in form.errors
        assert 'apellidos' in form.errors

    def test_rechazo_registro_por_duplicado(self):
        """ Criterio: Identificador (CI/RUC) ya existente rechaza el registro """
        # Arrange: Creamos un cliente previo en la base de datos
        Cliente.objects.create(
            tipo_cliente='FISICA', 
            nombres='Ana', 
            apellidos='Gómez', 
            identificador='9999999'
        )

        # Act: Intentamos registrar otro con el mismo identificador
        datos_duplicados = {
            'tipo_cliente': 'JURIDICA',
            'razon_social': 'Otra Empresa',
            'identificador': '9999999' # Mismo identificador
        }
        form = ClienteForm(data=datos_duplicados)

        # Assert: El formulario debe ser inválido por el campo unique
        assert form.is_valid() is False
        assert 'identificador' in form.errors


class TestClienteView:
    """ Pruebas para el control de acceso (Solo administradores) """

    @pytest.fixture
    def admin_user(self):
        """ Fixture para crear un usuario administrador (staff) """
        return User.objects.create_user(username='admin', password='123', is_staff=True)

    @pytest.fixture
    def normal_user(self):
        """ Fixture para crear un usuario común """
        return User.objects.create_user(username='comun', password='123', is_staff=False)

    def test_acceso_denegado_a_usuario_comun(self, client, normal_user):
        """ Criterio: Dado que soy administrador... (Usuario común no debe entrar) """
        # Forzamos el login saltando Keycloak
        client.force_login(normal_user) 
        
        # OJO: Asegúrate de que el nombre 'cliente_create' coincida con el 'name' en tu urls.py
        # url = reverse('cliente_create') 
        url = '/clientes/nuevo/' # Usando la ruta directa si no tienes configurado el reverse aún
        
        response = client.get(url)
        
        # 403 Forbidden porque el UserPassesTestMixin de la vista lo bloquea
        assert response.status_code == 403 

    def test_acceso_permitido_a_administrador(self, client, admin_user):
        """ Criterio: El administrador sí puede ver el formulario """
        client.force_login(admin_user)
        url = '/clientes/nuevo/' # Cambia esto por tu URL real
        
        response = client.get(url)
        
        # 200 OK significa que cargó la página del formulario exitosamente
        assert response.status_code == 200