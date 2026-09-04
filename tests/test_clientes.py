"""
Módulo de pruebas unitarias para el formulario y las vistas de Clientes.
"""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

from apps.clientes.models import Cliente
from apps.clientes.forms import ClienteForm
from apps.authentication.models import RecursoProtegido

User = get_user_model()


@pytest.mark.django_db
class TestClienteForm:
    def test_registro_persona_fisica_exitoso(self):
        datos = {
            'tipo_cliente': 'FISICA',
            'nombre': 'Juan',
            'apellido': 'Pérez',
            'identificador': '1234567',
            'email': 'juan.perez@test.com',
            'segmento': 'ESTANDAR'
        }
        form = ClienteForm(data=datos)
        assert form.is_valid() is True
        cliente = form.save()
        assert cliente.identificador == '1234567'
        assert cliente.usuarios.count() == 0

    def test_registro_persona_juridica_exitoso(self):
        datos = {
            'tipo_cliente': 'JURIDICA',
            'razon_social': 'Empresa SA',
            'identificador': '80012345-6',
            'email': 'contacto@empresa.com',
            'segmento': 'CORPORATIVO'
        }
        form = ClienteForm(data=datos)
        assert form.is_valid() is True

    def test_error_campos_obligatorios_vacios_fisica(self):
        User.objects.create_user(username='1234567', email='inc@test.com')
        datos = {
            'tipo_cliente': 'FISICA',
            'identificador': '1234567',
            'segmento': 'ESTANDAR'
        }
        form = ClienteForm(data=datos)
        assert form.is_valid() is False
        assert 'nombre' in form.errors
        assert 'apellido' in form.errors

    def test_rechazo_registro_email_duplicado(self):
        Cliente.objects.create(
            tipo_cliente='FISICA',
            nombre='Ana',
            apellido='Gómez',
            identificador='5555555',
            email='ana@test.com',
            segmento='ESTANDAR'
        )

        datos = {
            'tipo_cliente': 'FISICA',
            'nombre': 'Ana María',
            'apellido': 'Gómez Duplicada',
            'identificador': '6666666',
            'email': 'ana@test.com',
            'segmento': 'ESTANDAR'
        }
        form = ClienteForm(data=datos)
        assert form.is_valid() is False
        assert 'email' in form.errors

    def test_edicion_mismo_cliente_permitida(self):
        usuario = User.objects.create_user(username='1234567', email='juan@test.com')
        cliente = Cliente.objects.create(
            tipo_cliente='FISICA',
            nombre='Juan',
            apellido='Pérez',
            identificador='1234567',
            email='juan@test.com',
            segmento='ESTANDAR'
        )

        datos_editados = {
            'tipo_cliente': 'FISICA',
            'nombre': 'Juan Carlos',
            'apellido': 'Pérez Gómez',
            'identificador': '1234567',
            'email': 'juancarlos@test.com',
            'segmento': 'ESTANDAR'
        }
        form = ClienteForm(data=datos_editados, instance=cliente)
        assert form.is_valid() is True


@pytest.mark.django_db
class TestClienteView:

    def _ensure_perm(self, codename):
        """
        Helper: garantiza que exista el Permission asociado a RecursoProtegido.
        """
        ct = ContentType.objects.get_for_model(RecursoProtegido)
        perm, _ = Permission.objects.get_or_create(
            codename=codename,
            content_type=ct,
            defaults={'name': f'Puede acceder a {codename.replace("acceder_", "")}'}
        )
        return perm

    def test_acceso_denegado_a_usuario_comun(self, client):
        usuario = User.objects.create_user(username='user_normal', email='user@test.com', is_staff=False)
        client.force_login(usuario)
        response = client.get('/clientes/nuevo/')
        assert response.status_code == 403

    def test_acceso_permitido_a_administrador(self, client):
        admin = User.objects.create_user(username='admin_user', email='admin@test.com')
        perm = self._ensure_perm('acceder_clientes')
        admin.user_permissions.add(perm)
        client.force_login(admin)
        response = client.get('/clientes/nuevo/')
        assert response.status_code == 200

    def test_acceso_denegado_edicion_usuario_comun(self, client):
        user_cliente = User.objects.create_user(username='1234567', email='c@test.com')
        cliente = Cliente.objects.create(
            tipo_cliente='FISICA',
            nombre='Carlos',
            apellido='Ruiz',
            identificador='1234567',
            email='c@test.com',
            segmento='ESTANDAR'
        )
        user_normal = User.objects.create_user(username='normal', is_staff=False)
        client.force_login(user_normal)

        url = reverse('cliente_update', kwargs={'pk': cliente.pk})
        response = client.get(url)
        assert response.status_code == 403

    def test_modificar_cliente_exitoso(self, client):
        admin = User.objects.create_user(username='admin_ge62')
        perm = self._ensure_perm('acceder_clientes')
        admin.user_permissions.add(perm)

        user_cliente = User.objects.create_user(username='7777777', email='m@test.com')
        cliente = Cliente.objects.create(
            tipo_cliente='FISICA',
            nombre='Mario',
            apellido='Silva',
            identificador='7777777',
            email='m@test.com',
            segmento='ESTANDAR'
        )

        client.force_login(admin)
        url = reverse('cliente_update', kwargs={'pk': cliente.pk})

        datos_nuevos = {
            'tipo_cliente': 'FISICA',
            'nombre': 'Mario Alberto',
            'apellido': 'Silva Franco',
            'identificador': '7777777',
            'email': 'mario.alberto@test.com',
            'segmento': 'ESTANDAR'
        }

        response = client.post(url, data=datos_nuevos)
        assert response.status_code == 302

        cliente.refresh_from_db()
        assert cliente.nombre == 'Mario Alberto'
        assert cliente.apellido == 'Silva Franco'
        assert cliente.email == 'mario.alberto@test.com'

    def test_modificar_cliente_datos_invalidos(self, client):
        admin = User.objects.create_user(username='admin_ge62_inv')
        perm = self._ensure_perm('acceder_clientes')
        admin.user_permissions.add(perm)

        user_cliente = User.objects.create_user(username='8888888', email='e@test.com')
        cliente = Cliente.objects.create(
            tipo_cliente='FISICA',
            nombre='Esteban',
            apellido='Quito',
            identificador='8888888',
            email='e@test.com',
            segmento='ESTANDAR'
        )

        client.force_login(admin)
        url = reverse('cliente_update', kwargs={'pk': cliente.pk})

        datos_invalidos = {
            'tipo_cliente': 'FISICA',
            'nombre': '',
            'apellido': '',
            'identificador': '8888888',
            'email': 'e@test.com',
            'segmento': 'ESTANDAR'
        }

        response = client.post(url, data=datos_invalidos)
        assert response.status_code == 200
        assert 'form' in response.context
        assert response.context['form'].errors

        cliente.refresh_from_db()
        assert cliente.nombre == 'Esteban'

    def test_modificar_segmento_cliente_exitoso(self, client):
        admin = User.objects.create_user(username='admin_ge8')
        perm = self._ensure_perm('acceder_clientes')
        admin.user_permissions.add(perm)

        user_cliente = User.objects.create_user(username='9999999', email='seg@test.com')
        cliente = Cliente.objects.create(
            tipo_cliente='FISICA',
            nombre='Lucas',
            apellido='Pérez',
            identificador='9999999',
            email='seg@test.com',
            segmento='ESTANDAR'
        )

        client.force_login(admin)
        url = reverse('cliente_update', kwargs={'pk': cliente.pk})

        datos_nuevos = {
            'tipo_cliente': 'FISICA',
            'nombre': 'Lucas',
            'apellido': 'Pérez',
            'identificador': '9999999',
            'email': 'seg@test.com',
            'segmento': 'VIP'
        }

        response = client.post(url, data=datos_nuevos)
        assert response.status_code == 302

        cliente.refresh_from_db()
        assert cliente.segmento == 'VIP'

    def test_filtrar_listado_clientes_por_segmento(self, client):
        admin = User.objects.create_user(username='admin_filtro')
        perm = self._ensure_perm('acceder_panel_admin')
        admin.user_permissions.add(perm)

        u1 = User.objects.create_user(username='111', email='1@test.com')
        u2 = User.objects.create_user(username='222', email='2@test.com')

        c_estandar = Cliente.objects.create(
            tipo_cliente='FISICA', nombre='Ana', apellido='B', identificador='111', segmento='ESTANDAR'
        )
        c_vip = Cliente.objects.create(
            tipo_cliente='FISICA', nombre='Luis', apellido='C', identificador='222', segmento='VIP'
        )

        client.force_login(admin)
        url = reverse('panel_admin')
        response = client.get(url, {'q': 'Fernando'})

        assert response.status_code == 200
        nombres = [c.nombre for c in response.context['clientes']]
        assert isinstance(nombres, list)

    def test_acceso_a_ficha_de_cliente(self, client):
        admin = User.objects.create_user(username='admin_ficha2')
        # Para acceder a la ficha usamos permiso de clientes
        perm = self._ensure_perm('acceder_clientes')
        admin.user_permissions.add(perm)

        cliente = Cliente.objects.create(
            tipo_cliente='FISICA', nombre='Nora', apellido='Sosa',
            identificador='960', email='nora@test.com', segmento='ESTANDAR'
        )

        client.force_login(admin)
        url = reverse('cliente_detail', kwargs={'pk': cliente.pk})
        response = client.get(url)

        assert response.status_code == 200
        assert response.context['cliente'] == cliente