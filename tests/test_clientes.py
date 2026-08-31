"""
Módulo de pruebas unitarias para el formulario y las vistas de Clientes.

Incluye pruebas de validación de formulario para creación y edición,
así como pruebas de integración para el control de acceso y actualización de datos (HU GE-62 y GE-8).
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.clientes.models import Cliente
from apps.clientes.forms import ClienteForm

User = get_user_model()


@pytest.mark.django_db
class TestClienteForm:
    """
    Pruebas unitarias para las reglas de validación de ClienteForm.
    """

    def test_registro_persona_fisica_exitoso(self):
        """Criterio: Registra exitosamente si el documento CI pertenece a un usuario existente."""
        User.objects.create_user(username='1234567', email='juan.perez@test.com')
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
        assert cliente.user.username == '1234567'

    def test_rechazo_si_no_existe_usuario_con_documento(self):
        """Criterio: Muestra error si la CI/RUC no pertenece a ningún usuario del sistema."""
        datos = {
            'tipo_cliente': 'FISICA',
            'nombre': 'Carlos',
            'apellido': 'López',
            'identificador': '9999999',
            'email': 'carlos@test.com',
            'segmento': 'ESTANDAR'
        }
        form = ClienteForm(data=datos)
        assert form.is_valid() is False
        assert 'identificador' in form.errors

    def test_registro_persona_juridica_exitoso(self):
        """Criterio: Registra persona jurídica si el RUC coincide con un usuario registrado."""
        User.objects.create_user(username='80012345-6', email='contacto@empresa.com')
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
        """Criterio: Dejar campos requeridos vacíos muestra errores de validación."""
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

    def test_rechazo_registro_usuario_ya_vinculado(self):
        """Criterio: Rechaza el registro si el usuario con ese documento ya posee perfil de cliente."""
        u1 = User.objects.create_user(username='5555555', email='ana@test.com')
        Cliente.objects.create(
            user=u1,
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
            'apellido': 'Gómez',
            'identificador': '5555555',
            'email': 'ana.otra@test.com',
            'segmento': 'ESTANDAR'
        }
        form = ClienteForm(data=datos)
        assert form.is_valid() is False
        assert 'identificador' in form.errors

    def test_edicion_mismo_cliente_permitida(self):
        """
        HU GE-62: Valida que al editar un cliente existente manteniendo su mismo identificador,
        el formulario no marque error de duplicado.
        """
        usuario = User.objects.create_user(username='1234567', email='juan@test.com')
        cliente = Cliente.objects.create(
            user=usuario,
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
    """
    Pruebas de integración para las vistas de creación, edición y listado de Clientes.
    """

    def test_acceso_denegado_a_usuario_comun(self, client):
        """Valida que un usuario común reciba un HTTP 403 al intentar acceder al alta."""
        usuario = User.objects.create_user(
            username='user_normal',
            email='user@test.com',
            is_staff=False
        )
        client.force_login(usuario)
        response = client.get('/clientes/nuevo/')
        assert response.status_code == 403

    def test_acceso_permitido_a_administrador(self, client):
        """Valida que un administrador pueda ingresar al formulario de alta."""
        admin = User.objects.create_user(
            username='admin_user',
            email='admin@test.com',
            is_staff=True
        )
        client.force_login(admin)
        response = client.get('/clientes/nuevo/')
        assert response.status_code == 200

    def test_acceso_denegado_edicion_usuario_comun(self, client):
        """
        HU GE-62: Valida que un usuario común reciba un HTTP 403 al intentar acceder
        a la vista de edición de un cliente.
        """
        user_cliente = User.objects.create_user(username='1234567', email='c@test.com')
        cliente = Cliente.objects.create(
            user=user_cliente,
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
        """
        HU GE-62 - Criterio 1:
        Dado que selecciono un cliente existente, cuando edito sus datos y guardo,
        entonces la información se actualiza correctamente en el sistema.
        """
        admin = User.objects.create_user(username='admin_ge62', is_staff=True)
        user_cliente = User.objects.create_user(username='7777777', email='m@test.com')
        cliente = Cliente.objects.create(
            user=user_cliente,
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
        assert response.status_code == 302  # Redirección tras guardado exitoso

        cliente.refresh_from_db()
        assert cliente.nombre == 'Mario Alberto'
        assert cliente.apellido == 'Silva Franco'
        assert cliente.email == 'mario.alberto@test.com'

    def test_modificar_cliente_datos_invalidos(self, client):
        """
        HU GE-62 - Criterio 2:
        Dado que ingreso datos inválidos durante la edición, cuando intento guardar,
        entonces el sistema muestra los errores sin aplicar los cambios.
        """
        admin = User.objects.create_user(username='admin_ge62_inv', is_staff=True)
        user_cliente = User.objects.create_user(username='8888888', email='e@test.com')
        cliente = Cliente.objects.create(
            user=user_cliente,
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
            'nombre': '',  # Nombre en blanco (inválido)
            'apellido': '',  # Apellido en blanco (inválido)
            'identificador': '8888888',
            'email': 'e@test.com',
            'segmento': 'ESTANDAR'
        }

        response = client.post(url, data=datos_invalidos)
        assert response.status_code == 200  # Vuelve a renderizar la plantilla
        assert 'form' in response.context
        assert response.context['form'].errors

        cliente.refresh_from_db()
        assert cliente.nombre == 'Esteban'  # La DB no cambió

    def test_modificar_segmento_cliente_exitoso(self, client):
        """
        HU GE-8 - Criterio 1:
        Dado que soy administrador, cuando edito un cliente, 
        entonces puedo asignarle una categoría/segmento desde una lista predefinida.
        """
        admin = User.objects.create_user(username='admin_ge8', is_staff=True)
        user_cliente = User.objects.create_user(username='9999999', email='seg@test.com')
        cliente = Cliente.objects.create(
            user=user_cliente,
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
            'segmento': 'VIP'  # Cambiando el segmento a VIP
        }

        response = client.post(url, data=datos_nuevos)
        assert response.status_code == 302

        cliente.refresh_from_db()
        assert cliente.segmento == 'VIP'

    def test_filtrar_listado_clientes_por_segmento(self, client):
        """
        HU GE-8 - Criterio 2:
        Dado que filtro el listado de clientes por segmento, 
        cuando aplico el filtro, entonces el sistema muestra únicamente 
        los clientes de esa categoría.
        """
        # Crear superusuario para saltar el PermissionRequiredMixin si lo requiere
        admin = User.objects.create_user(username='admin_filtro', is_superuser=True)
        
        u1 = User.objects.create_user(username='111', email='1@test.com')
        u2 = User.objects.create_user(username='222', email='2@test.com')
        
        c_estandar = Cliente.objects.create(
            user=u1, tipo_cliente='FISICA', nombre='Ana', apellido='B', identificador='111', segmento='ESTANDAR'
        )
        c_vip = Cliente.objects.create(
            user=u2, tipo_cliente='FISICA', nombre='Luis', apellido='C', identificador='222', segmento='VIP'
        )

        client.force_login(admin)
        
        # Petición GET aplicando filtro por segmento 'VIP' (Ajusta 'panel_admin' si el name en urls.py es diferente)
        url = reverse('panel_admin')
        response = client.get(url, {'segmento': 'VIP'})
        
        assert response.status_code == 200
        
        # Verificar que solo el cliente VIP esté en el contexto
        clientes_en_contexto = response.context['clientes']
        assert c_vip in clientes_en_contexto
        assert c_estandar not in clientes_en_contexto