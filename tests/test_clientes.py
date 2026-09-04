"""
Módulo de pruebas unitarias para el formulario y las vistas de Clientes.

Incluye pruebas de validación de formulario para creación y edición,
así como pruebas de integración para el control de acceso, actualización de datos,
segmentación (HU GE-62 y GE-8) y baja lógica (HU GE-63).
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
        """Criterio: Registra exitosamente un cliente persona física con datos válidos.
        Ya no requiere que exista un Usuario del sistema vinculado por documento;
        la asociación de usuarios se gestiona aparte, por email."""
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
        assert cliente.usuarios.count() == 0  # sin usuarios asociados todavía

    def test_registro_persona_juridica_exitoso(self):
        """Criterio: Registra persona jurídica con datos válidos."""
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

    def test_rechazo_registro_email_duplicado(self):
        """Criterio: Rechaza el registro si ya existe un Cliente con ese email
        (el email es ahora la clave de asociación, debe ser único)."""
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
        """
        HU GE-62: Valida que al editar un cliente existente manteniendo su mismo identificador,
        el formulario no marque error de duplicado.
        """
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
    """
    Pruebas de integración para las vistas de creación, edición, listado 
    y eliminación (baja lógica) de Clientes.
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
        admin = User.objects.create_user(username='admin_filtro', is_superuser=True)
        
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
        response = client.get(url, {'segmento': 'VIP'})
        
        assert response.status_code == 200
        
        clientes_en_contexto = response.context['clientes']
        assert c_vip in clientes_en_contexto
        assert c_estandar not in clientes_en_contexto

    # =======================================================================
    # NUEVOS TESTS PARA LA HISTORIA GE-63 (Baja lógica y trazabilidad)
    # =======================================================================

    def test_eliminar_cliente_baja_logica(self, client):
        """
        HU GE-63 - Criterio 1:
        Dado que soy administrador, cuando elimino un cliente, entonces el sistema 
        realiza una baja lógica (is_active=False) sin borrar físicamente sus datos.
        """
        admin = User.objects.create_user(username='admin_ge63', is_superuser=True)
        u1 = User.objects.create_user(username='333', email='3@test.com')
        cliente = Cliente.objects.create(
            tipo_cliente='FISICA', nombre='Pedro', apellido='D', identificador='333'
        )
        
        client.force_login(admin)
        url = reverse('cliente_delete', kwargs={'pk': cliente.pk})

        response = client.post(url)
        
        # Validar redirección tras éxito
        assert response.status_code in [301, 302]

        # Validar que el cliente sigue existiendo en BD pero inactivo
        cliente.refresh_from_db()
        assert cliente.is_active is False
        assert Cliente.objects.filter(pk=cliente.pk).exists() is True

    def test_listado_general_oculta_inactivos_por_defecto(self, client):
        """
        HU GE-63 - Criterio 2:
        Dado que un cliente está dado de baja, cuando consulto el listado general,
        entonces el sistema no lo muestra entre los clientes activos por defecto.
        """
        admin = User.objects.create_user(username='admin_ge63_2', is_superuser=True)
        
        u1 = User.objects.create_user(username='444', email='4@test.com')
        cliente_activo = Cliente.objects.create(
            tipo_cliente='FISICA', nombre='Activo', apellido='A', identificador='444'
        )
        
        u2 = User.objects.create_user(username='555', email='5@test.com')
        cliente_inactivo = Cliente.objects.create(
            tipo_cliente='FISICA', nombre='Inactivo', apellido='I', identificador='555', is_active=False
        )

        client.force_login(admin)
        url = reverse('panel_admin')
        response = client.get(url)

        assert response.status_code == 200
        clientes_en_contexto = response.context['clientes']
        
        # El cliente activo debe estar, el inactivo debe ocultarse
        assert cliente_activo in clientes_en_contexto
        assert cliente_inactivo not in clientes_en_contexto

    def test_trazabilidad_historial_cliente_inactivo(self, client):
        """
        HU GE-63 - Criterio 3:
        Dado que un cliente dado de baja tiene operaciones históricas asociadas, 
        cuando reviso ese historial (simulado pidiendo incluir inactivos), 
        entonces sigue siendo accesible para trazabilidad.
        """
        admin = User.objects.create_user(username='admin_ge63_3', is_superuser=True)
        u1 = User.objects.create_user(username='666', email='6@test.com')
        cliente_inactivo = Cliente.objects.create(
            tipo_cliente='FISICA', nombre='Inactivo', apellido='I', identificador='666', is_active=False
        )

        client.force_login(admin)
        url = reverse('panel_admin')
        
        # Enviar parámetro GET para incluir inactivos
        response = client.get(url, {'incluir_inactivos': '1'})

        assert response.status_code == 200
        clientes_en_contexto = response.context['clientes']
        
        # El cliente inactivo ahora debe aparecer listado
        assert cliente_inactivo in clientes_en_contexto

@pytest.mark.django_db
class TestAsociacionUsuariosPorEmail:
    """
    HU: Como administrador quiero asociar y gestionar qué usuarios
    pueden operar en representación de cada cliente.
    """

    def test_asociar_usuario_existente_por_email(self, client):
        """Criterio: al buscar y asociar un usuario existente por email,
        ese usuario queda habilitado para operar en representación del cliente."""
        admin = User.objects.create_user(username='admin_assoc', is_superuser=True)
        usuario = User.objects.create_user(username='op1', email='operador@test.com')
        cliente = Cliente.objects.create(
            tipo_cliente='FISICA', nombre='Rosa', apellido='Díaz',
            identificador='777', email='rosa@test.com', segmento='ESTANDAR'
        )

        client.force_login(admin)
        url = reverse('cliente_asociar_usuario', kwargs={'pk': cliente.pk})
        response = client.post(url, {'email': 'operador@test.com'})

        assert response.status_code == 302
        assert cliente.usuarios.filter(pk=usuario.pk).exists()

    def test_rechaza_asociar_email_inexistente(self, client):
        """Criterio: si el email no corresponde a ningún usuario del sistema, no se asocia nada."""
        admin = User.objects.create_user(username='admin_assoc2', is_superuser=True)
        cliente = Cliente.objects.create(
            tipo_cliente='FISICA', nombre='Rosa', apellido='Díaz',
            identificador='778', email='rosa2@test.com', segmento='ESTANDAR'
        )

        client.force_login(admin)
        url = reverse('cliente_asociar_usuario', kwargs={'pk': cliente.pk})
        response = client.post(url, {'email': 'noexiste@test.com'})

        assert response.status_code == 302
        assert cliente.usuarios.count() == 0

    def test_ficha_cliente_lista_usuarios_asociados(self, client):
        """Criterio: al acceder a la ficha de un cliente, veo el listado completo de usuarios vinculados."""
        admin = User.objects.create_user(username='admin_ficha', is_superuser=True)
        u1 = User.objects.create_user(username='op2', email='op2@test.com')
        u2 = User.objects.create_user(username='op3', email='op3@test.com')
        cliente = Cliente.objects.create(
            tipo_cliente='FISICA', nombre='Marta', apellido='Ruiz',
            identificador='779', email='marta@test.com', segmento='ESTANDAR'
        )
        cliente.usuarios.add(u1, u2)

        client.force_login(admin)
        url = reverse('cliente_detail', kwargs={'pk': cliente.pk})
        response = client.get(url)

        assert response.status_code == 200
        usuarios_en_contexto = list(response.context['usuarios_asociados'])
        assert u1 in usuarios_en_contexto
        assert u2 in usuarios_en_contexto

    def test_desasociar_usuario_revoca_acceso(self, client):
        """Criterio: al desasociar un usuario, deja de poder operar en representación del cliente."""
        admin = User.objects.create_user(username='admin_desassoc', is_superuser=True)
        usuario = User.objects.create_user(username='op4', email='op4@test.com')
        cliente = Cliente.objects.create(
            tipo_cliente='FISICA', nombre='Elsa', apellido='Nuñez',
            identificador='780', email='elsa@test.com', segmento='ESTANDAR'
        )
        cliente.usuarios.add(usuario)

        client.force_login(admin)
        url = reverse('cliente_desasociar_usuario', kwargs={'pk': cliente.pk, 'user_id': usuario.pk})
        response = client.post(url)

        assert response.status_code == 302
        assert not cliente.usuarios.filter(pk=usuario.pk).exists()


@pytest.mark.django_db
class TestSeleccionClienteActivo:
    """
    HU: Como usuario cliente quiero seleccionar el cliente en cuyo
    nombre voy a operar.
    """

    def test_seleccion_automatica_si_un_solo_cliente(self, client):
        """Criterio: si el usuario está asociado a un único cliente, se selecciona
        automáticamente sin pedírselo."""
        usuario = User.objects.create_user(username='cli_unico', email='unico@test.com', is_staff=False)
        cliente = Cliente.objects.create(
            tipo_cliente='FISICA', nombre='Uno', apellido='Solo',
            identificador='900', email='uno@test.com', segmento='ESTANDAR'
        )
        cliente.usuarios.add(usuario)

        client.force_login(usuario)
        response = client.get(reverse('home'))

        assert response.status_code == 200
        assert client.session.get('cliente_activo_id') == cliente.pk

    def test_se_solicita_seleccion_si_hay_multiples_clientes(self, client):
        """Criterio: si el usuario está asociado a más de un cliente, al navegar
        el sistema lo redirige a seleccionar el cliente activo."""
        usuario = User.objects.create_user(username='cli_multi', email='multi@test.com', is_staff=False)
        c1 = Cliente.objects.create(
            tipo_cliente='FISICA', nombre='Cli', apellido='Uno',
            identificador='901', email='c1@test.com', segmento='ESTANDAR'
        )
        c2 = Cliente.objects.create(
            tipo_cliente='FISICA', nombre='Cli', apellido='Dos',
            identificador='902', email='c2@test.com', segmento='ESTANDAR'
        )
        c1.usuarios.add(usuario)
        c2.usuarios.add(usuario)

        client.force_login(usuario)
        response = client.get(reverse('home'))

        assert response.status_code == 302
        assert response.url == reverse('seleccionar_cliente_activo')

    def test_cambio_de_cliente_activo_sin_cerrar_sesion(self, client):
        """Criterio: estando con un cliente activo, puedo cambiar a otro cliente
        asociado a mi cuenta sin cerrar sesión."""
        usuario = User.objects.create_user(username='cli_cambio', email='cambio@test.com', is_staff=False)
        c1 = Cliente.objects.create(
            tipo_cliente='FISICA', nombre='Cli', apellido='Uno',
            identificador='903', email='c1b@test.com', segmento='ESTANDAR'
        )
        c2 = Cliente.objects.create(
            tipo_cliente='FISICA', nombre='Cli', apellido='Dos',
            identificador='904', email='c2b@test.com', segmento='ESTANDAR'
        )
        c1.usuarios.add(usuario)
        c2.usuarios.add(usuario)

        client.force_login(usuario)
        session = client.session
        session['cliente_activo_id'] = c1.pk
        session.save()

        url = reverse('cambiar_cliente_activo')
        response = client.post(url, {'cliente_id': c2.pk})

        assert response.status_code == 302
        assert client.session.get('cliente_activo_id') == c2.pk


@pytest.mark.django_db
class TestListadoClientesAdmin:
    """
    HU: Como administrador quiero visualizar el listado de clientes
    registrados para consultar su información y gestionarlos.
    """

    def test_busqueda_por_nombre(self, client):
        """Criterio: al escribir en el buscador, el listado se filtra correctamente."""
        admin = User.objects.create_user(username='admin_busq', is_superuser=True)
        Cliente.objects.create(
            tipo_cliente='FISICA', nombre='Fernando', apellido='Gómez',
            identificador='950', email='fer@test.com', segmento='ESTANDAR'
        )
        Cliente.objects.create(
            tipo_cliente='FISICA', nombre='Beatriz', apellido='López',
            identificador='951', email='bea@test.com', segmento='ESTANDAR'
        )

        client.force_login(admin)
        url = reverse('panel_admin')
        response = client.get(url, {'q': 'Fernando'})

        assert response.status_code == 200
        nombres = [c.nombre for c in response.context['clientes']]
        assert 'Fernando' in nombres
        assert 'Beatriz' not in nombres

    def test_busqueda_por_identificador(self, client):
        """Criterio: la búsqueda también funciona por CI/RUC."""
        admin = User.objects.create_user(username='admin_busq2', is_superuser=True)
        cliente = Cliente.objects.create(
            tipo_cliente='FISICA', nombre='Hugo', apellido='Vera',
            identificador='952', email='hugo@test.com', segmento='ESTANDAR'
        )

        client.force_login(admin)
        url = reverse('panel_admin')
        response = client.get(url, {'q': '952'})

        assert response.status_code == 200
        assert cliente in response.context['clientes']

    def test_listado_paginado(self, client):
        """Criterio: el listado se muestra paginado."""
        admin = User.objects.create_user(username='admin_pag', is_superuser=True)
        for i in range(25):
            Cliente.objects.create(
                tipo_cliente='FISICA', nombre=f'Cliente{i}', apellido='Test',
                identificador=f'PAG{i}', email=f'pag{i}@test.com', segmento='ESTANDAR'
            )

        client.force_login(admin)
        url = reverse('panel_admin')
        response = client.get(url)

        assert response.status_code == 200
        assert response.context['is_paginated'] is True
        assert len(response.context['clientes']) == 20  # paginate_by

    def test_acceso_a_ficha_de_cliente(self, client):
        """Criterio: al hacer clic en un cliente del listado, accedo a su ficha con el detalle completo."""
        admin = User.objects.create_user(username='admin_ficha2', is_superuser=True)
        cliente = Cliente.objects.create(
            tipo_cliente='FISICA', nombre='Nora', apellido='Sosa',
            identificador='960', email='nora@test.com', segmento='ESTANDAR'
        )

        client.force_login(admin)
        url = reverse('cliente_detail', kwargs={'pk': cliente.pk})
        response = client.get(url)

        assert response.status_code == 200
        assert response.context['cliente'] == cliente
