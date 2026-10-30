"""
Módulo de pruebas unitarias para el formulario y las vistas de Clientes.

Incluye pruebas de validación de formulario para creación y edición,
así como pruebas de integración para el control de acceso, actualización de datos,
segmentación (HU GE-62 y GE-8) y baja lógica (HU GE-63).
"""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError, transaction
from django.urls import reverse
from apps.clientes.models import Cliente, SolicitudCliente
from apps.clientes.forms import ClienteForm
from apps.authentication.models import HistorialBaja

User = get_user_model()


@pytest.mark.django_db
class TestClienteForm:
    """
    Pruebas unitarias para las reglas de validación de ClienteForm.
    """

    def test_segmento_se_presenta_como_lista_de_opciones_vigentes(self):
        """Verifica que el formulario muestre los segmentos actuales."""
        form = ClienteForm()

        assert form.fields['segmento'].choices == Cliente.SEGMENTO_CHOICES
        assert form.fields['segmento'].widget.__class__.__name__ == 'Select'

    def test_registro_exitoso_con_o_sin_usuario_previo_fisica_o_juridica(self):
        """Criterio: registra si el CI/RUC pertenece a un usuario existente, o aunque no exista ninguno."""
        User.objects.create_user(username='1234567', email='juan.perez@test.com')
        datos_con_usuario = {
            'tipo_cliente': 'FISICA',
            'nombre': 'Juan',
            'apellido': 'Pérez',
            'identificador': '1234567',
            'email': 'juan.perez@test.com',
            'segmento': 'ESTANDAR'
        }
        form = ClienteForm(data=datos_con_usuario)
        assert form.is_valid() is True
        cliente = form.save()
        assert cliente.user.username == '1234567'

        datos_sin_usuario = {
            'tipo_cliente': 'FISICA',
            'nombre': 'Carlos',
            'apellido': 'López',
            'identificador': '9999999',
            'email': 'carlos@test.com',
            'segmento': 'ESTANDAR'
        }
        assert ClienteForm(data=datos_sin_usuario).is_valid() is True

        User.objects.create_user(username='80012345-6', email='contacto@empresa.com')
        datos_juridica = {
            'tipo_cliente': 'JURIDICA',
            'razon_social': 'Empresa SA',
            'identificador': '80012345-6',
            'email': 'contacto@empresa.com',
            'segmento': 'CORPORATIVO'
        }
        assert ClienteForm(data=datos_juridica).is_valid() is True

    def test_rechaza_campos_obligatorios_vacios_o_identificador_ya_vinculado(self):
        """Criterio: campos vacíos, o un CI ya vinculado a otro cliente, muestran sus errores propios."""
        User.objects.create_user(username='1234567', email='inc@test.com')
        datos_incompletos = {
            'tipo_cliente': 'FISICA',
            'identificador': '1234567',
            'segmento': 'ESTANDAR'
        }
        form = ClienteForm(data=datos_incompletos)
        assert form.is_valid() is False
        assert 'nombre' in form.errors
        assert 'apellido' in form.errors

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
        datos_duplicados = {
            'tipo_cliente': 'FISICA',
            'nombre': 'Ana María',
            'apellido': 'Gómez',
            'identificador': '5555555',
            'email': 'ana.otra@test.com',
            'segmento': 'ESTANDAR'
        }
        form = ClienteForm(data=datos_duplicados)
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
    Pruebas de integración para las vistas de creación, edición, listado 
    y eliminación (baja lógica) de Clientes.
    """

    def test_acceso_al_alta_segun_el_rol(self, client):
        """Un usuario común recibe 403 al intentar acceder al alta; un administrador, 200."""
        usuario = User.objects.create_user(
            username='user_normal',
            email='user@test.com',
            is_staff=False
        )
        client.force_login(usuario)
        response = client.get('/clientes/nuevo/')
        assert response.status_code == 403

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
        assert cliente.user.email == 'm@test.com'

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

    def test_comision_personalizada_se_puede_definir_o_dejar_vacia(self, client):
        """Un administrador puede definir una comisión preferencial; si no la define, queda vacía."""
        admin = User.objects.create_user(username='admin_comision', is_staff=True)
        user_cliente = User.objects.create_user(username='6666666', email='pref@test.com')
        cliente = Cliente.objects.create(
            user=user_cliente,
            tipo_cliente='FISICA',
            nombre='Preferencial',
            apellido='Cliente',
            identificador='6666666',
            email='pref@test.com',
            segmento='ESTANDAR',
        )

        client.force_login(admin)
        url = reverse('cliente_update', kwargs={'pk': cliente.pk})

        response = client.post(url, data={
            'tipo_cliente': 'FISICA',
            'nombre': 'Preferencial',
            'apellido': 'Cliente',
            'identificador': '6666666',
            'email': 'pref@test.com',
            'segmento': 'ESTANDAR',
            'comision_personalizada': '0.500',
        })
        assert response.status_code == 302
        cliente.refresh_from_db()
        assert cliente.comision_personalizada == pytest.approx(0.5)

        user_cliente_2 = User.objects.create_user(username='6666667', email='sinpref@test.com')
        cliente_2 = Cliente.objects.create(
            user=user_cliente_2,
            tipo_cliente='FISICA',
            nombre='Regular',
            apellido='Cliente',
            identificador='6666667',
            email='sinpref@test.com',
            segmento='ESTANDAR',
        )
        url_2 = reverse('cliente_update', kwargs={'pk': cliente_2.pk})

        response = client.post(url_2, data={
            'tipo_cliente': 'FISICA',
            'nombre': 'Regular',
            'apellido': 'Cliente',
            'identificador': '6666667',
            'email': 'sinpref@test.com',
            'segmento': 'ESTANDAR',
        })
        assert response.status_code == 302
        cliente_2.refresh_from_db()
        assert cliente_2.comision_personalizada is None

    def test_listado_clientes_es_paginado_y_muestra_datos_principales(self, client):
        """El listado administrativo pagina los clientes y muestra sus datos principales."""
        admin = User.objects.create_user(username='admin_listado', is_staff=True)
        clientes = [
            Cliente.objects.create(
                tipo_cliente='FISICA',
                nombre=f'Cliente {indice}',
                apellido='Listado',
                identificador=f'LIST-{indice}',
            )
            for indice in range(1, 12)
        ]
        client.force_login(admin)

        response = client.get(reverse('panel_admin'))

        assert response.status_code == 200
        assert response.context['is_paginated'] is True
        assert response.context['page_obj'].paginator.count == 11
        assert len(response.context['clientes']) == 10
        assert_contains = response.content.decode()
        assert clientes[0].identificador in assert_contains
        assert clientes[0].nombre in assert_contains

    def test_busqueda_clientes_por_nombre_ci_y_ruc(self, client):
        """El buscador encuentra clientes por nombre, CI o RUC."""
        admin = User.objects.create_user(username='admin_busqueda', is_staff=True)
        cliente_nombre = Cliente.objects.create(
            tipo_cliente='FISICA',
            nombre='LuciaBusqueda',
            apellido='Gomez',
            identificador='CI-1001',
        )
        cliente_ci = Cliente.objects.create(
            tipo_cliente='FISICA',
            nombre='Carlos',
            apellido='Documento',
            identificador='CI-2002',
        )
        cliente_ruc = Cliente.objects.create(
            tipo_cliente='JURIDICA',
            razon_social='EmpresaRucBusqueda',
            identificador='RUC-3003',
        )
        client.force_login(admin)

        for termino, esperado in [
            ('LuciaBusqueda', cliente_nombre),
            ('CI-2002', cliente_ci),
            ('RUC-3003', cliente_ruc),
        ]:
            response = client.get(reverse('panel_admin'), {'q': termino})
            assert response.status_code == 200
            assert list(response.context['clientes']) == [esperado]

    def test_listado_enlaza_a_ficha_detallada_del_cliente(self, client):
        """Seleccionar un cliente del listado abre su ficha completa."""
        admin = User.objects.create_user(username='admin_ficha', is_staff=True)
        usuario = User.objects.create_user(
            username='usuario_ficha',
            email='usuario-ficha@test.com',
        )
        cliente = Cliente.objects.create(
            tipo_cliente='JURIDICA',
            razon_social='Empresa Ficha',
            identificador='RUC-FICHA-1',
            email='empresa-ficha@test.com',
            segmento='PREMIUM',
        )
        cliente.usuarios.add(usuario)
        client.force_login(admin)

        listado = client.get(reverse('panel_admin'))
        ficha_url = reverse('cliente_detail', kwargs={'pk': cliente.pk})
        ficha = client.get(ficha_url)

        assert ficha_url in listado.content.decode()
        assert ficha.status_code == 200
        assert ficha.context['cliente'] == cliente
        assert 'Empresa Ficha' in ficha.content.decode()
        assert 'RUC-FICHA-1' in ficha.content.decode()
        assert 'usuario-ficha@test.com' in ficha.content.decode()
        assert 'usuario_ficha' in ficha.content.decode()

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
            user=u1, tipo_cliente='FISICA', nombre='Ana', apellido='B', identificador='111', segmento='ESTANDAR'
        )
        c_vip = Cliente.objects.create(
            user=u2, tipo_cliente='FISICA', nombre='Luis', apellido='C', identificador='222', segmento='VIP'
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
            user=u1, tipo_cliente='FISICA', nombre='Pedro', apellido='D', identificador='333'
        )
        
        client.force_login(admin)
        url = reverse('cliente_delete', kwargs={'pk': cliente.pk})

        response = client.post(url, {'causa': 'Solicitud del cliente'})
        
        # Validar redirección tras éxito
        assert response.status_code in [301, 302]

        # Validar que el cliente sigue existiendo en BD pero inactivo
        cliente.refresh_from_db()
        assert cliente.is_active is False
        assert Cliente.objects.filter(pk=cliente.pk).exists() is True
        registro = HistorialBaja.objects.get(
            tipo_recurso=HistorialBaja.TIPO_CLIENTE,
            recurso_id=cliente.pk,
        )
        assert registro.causa == 'Solicitud del cliente'

        historial = client.get(reverse('cliente_historial_bajas'))
        assert historial.status_code == 200
        assert 'Solicitud del cliente' in historial.content.decode()

    def test_listado_general_oculta_inactivos_siempre(self, client):
        """
        HU GE-63 - Criterio 2:
        Un cliente dado de baja no aparece en el listado general por defecto, ni
        aunque se envíe el antiguo filtro histórico ('incluir_inactivos'): se
        conserva en la base, pero nunca en el listado operativo.
        """
        admin = User.objects.create_user(username='admin_ge63_2', is_superuser=True)

        u1 = User.objects.create_user(username='444', email='4@test.com')
        cliente_activo = Cliente.objects.create(
            user=u1, tipo_cliente='FISICA', nombre='Activo', apellido='A', identificador='444'
        )

        u2 = User.objects.create_user(username='555', email='5@test.com')
        cliente_inactivo = Cliente.objects.create(
            user=u2, tipo_cliente='FISICA', nombre='Inactivo', apellido='I', identificador='555', is_active=False
        )

        client.force_login(admin)
        url = reverse('panel_admin')
        response = client.get(url)

        assert response.status_code == 200
        clientes_en_contexto = response.context['clientes']
        assert cliente_activo in clientes_en_contexto
        assert cliente_inactivo not in clientes_en_contexto

        response = client.get(url, {'incluir_inactivos': '1'})

        assert response.status_code == 200
        assert cliente_inactivo not in response.context['clientes']


@pytest.mark.django_db
class TestClienteNombreCompleto:
    """Verifica que ``nombre_completo`` muestre solo el nombre, sin identificador ni estado.

    A diferencia de ``__str__`` (pensado para listados administrativos),
    este campo se usa para precargar formularios de cara al propio cliente
    (p. ej. el titular al agregar una tarjeta vía Stripe).
    """

    def test_persona_fisica_devuelve_nombre_y_apellido(self):
        """Para una persona física, es 'nombre apellido', sin el CI ni el estado."""
        cliente = Cliente.objects.create(
            tipo_cliente='FISICA', nombre='Ana', apellido='Gómez',
            identificador='CI-NOMBRE-001', is_active=True,
        )

        assert cliente.nombre_completo == 'Ana Gómez'
        assert cliente.identificador not in cliente.nombre_completo
        assert 'Activo' not in cliente.nombre_completo

    def test_persona_juridica_devuelve_la_razon_social(self):
        """Para una persona jurídica, es la razón social, sin el RUC ni el estado."""
        cliente = Cliente.objects.create(
            tipo_cliente='JURIDICA', razon_social='Importadora SA',
            identificador='RUC-NOMBRE-001', is_active=True,
        )

        assert cliente.nombre_completo == 'Importadora SA'
        assert cliente.identificador not in cliente.nombre_completo


def _loguear_con_rol_cliente(client, usuario):
    """Loguea ``usuario`` y le fija en sesión el rol de Keycloak 'cliente' (sin ningún Cliente asociado)."""
    client.force_login(usuario)
    session = client.session
    session['keycloak_roles'] = ['cliente']
    session.save()


@pytest.mark.django_db
class TestSolicitudCliente:
    """Autoservicio de alta: un usuario con rol 'cliente' sin Cliente asociado pide darse de alta."""

    def test_usuario_sin_cliente_puede_enviar_la_solicitud(self, client):
        """Con los campos completos, se crea en PENDIENTE a nombre del usuario logueado."""
        usuario = User.objects.create_user(username='nuevo-cliente', password='x')
        _loguear_con_rol_cliente(client, usuario)

        response = client.post(reverse('clientes:solicitar_cliente'), {
            'tipo_cliente': 'FISICA', 'nombre': 'Jorge', 'apellido': 'Ferreira', 'identificador': '5910941',
        })

        assert response.status_code == 302
        solicitud = SolicitudCliente.objects.get(usuario=usuario)
        assert solicitud.estado == SolicitudCliente.ESTADO_PENDIENTE
        assert solicitud.nombre == 'Jorge'
        assert solicitud.identificador == '5910941'

    def test_un_usuario_sin_ningun_rol_tambien_puede_solicitar(self, client):
        """No depende del rol 'cliente': un usuario recién registrado puede no tener ningún rol todavía."""
        usuario = User.objects.create_user(username='sin-ningun-rol', password='x')
        client.force_login(usuario)
        session = client.session
        session['keycloak_roles'] = []
        session.save()

        response_formulario = client.get(reverse('clientes:solicitar_cliente'))
        assert response_formulario.status_code == 200

        response_home = client.get(reverse('home'))
        assert response_home.status_code == 302
        assert response_home.url == reverse('clientes:solicitar_cliente')

    def test_con_una_solicitud_pendiente_no_se_puede_enviar_otra(self, client):
        """Ni la vista, ni la base (UniqueConstraint), dejan crear una segunda solicitud pendiente."""
        usuario = User.objects.create_user(username='con-pendiente', password='x')
        SolicitudCliente.objects.create(usuario=usuario, nombre='Jorge', apellido='Ferreira', identificador='1111111')
        _loguear_con_rol_cliente(client, usuario)

        response = client.post(reverse('clientes:solicitar_cliente'), {
            'nombre': 'Jorge', 'apellido': 'Ferreira', 'identificador': '2222222',
        })

        assert response.status_code == 302
        assert SolicitudCliente.objects.filter(usuario=usuario).count() == 1

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                SolicitudCliente.objects.create(usuario=usuario, nombre='Otra', apellido='Vez', identificador='3333333')

    def test_usuario_que_ya_tiene_cliente_es_redirigido_sin_ver_el_formulario(self, client):
        usuario = User.objects.create_user(username='ya-tiene-cliente', password='x')
        cliente = Cliente.objects.create(tipo_cliente='FISICA', nombre='Ya', apellido='Tiene', identificador='4444444', is_active=True)
        cliente.usuarios.add(usuario)
        _loguear_con_rol_cliente(client, usuario)

        response = client.get(reverse('clientes:solicitar_cliente'))

        assert response.status_code == 302

    def test_identificador_ya_usado_por_un_cliente_activo_se_rechaza(self, client):
        Cliente.objects.create(tipo_cliente='FISICA', nombre='Existente', apellido='Cliente', identificador='5555555', is_active=True)
        usuario = User.objects.create_user(username='con-ci-duplicado', password='x')
        _loguear_con_rol_cliente(client, usuario)

        response = client.post(reverse('clientes:solicitar_cliente'), {
            'nombre': 'Nuevo', 'apellido': 'Pedido', 'identificador': '5555555',
        })

        assert response.status_code == 200
        assert not SolicitudCliente.objects.filter(usuario=usuario).exists()

    def test_identificador_ya_pendiente_de_otro_usuario_se_rechaza(self, client):
        otro_usuario = User.objects.create_user(username='otro-pendiente', password='x')
        SolicitudCliente.objects.create(usuario=otro_usuario, nombre='Primero', apellido='En pedir', identificador='6666666')
        usuario = User.objects.create_user(username='segundo-en-pedir', password='x')
        _loguear_con_rol_cliente(client, usuario)

        response = client.post(reverse('clientes:solicitar_cliente'), {
            'nombre': 'Segundo', 'apellido': 'En pedir', 'identificador': '6666666',
        })

        assert response.status_code == 200
        assert not SolicitudCliente.objects.filter(usuario=usuario).exists()

    def test_admin_aprueba_crea_el_cliente_y_lo_asocia_al_usuario(self, client):
        usuario = User.objects.create_user(username='sera-aprobado', password='x')
        solicitud = SolicitudCliente.objects.create(usuario=usuario, nombre='Jorge', apellido='Ferreira', identificador='7777777')
        admin = User.objects.create_user(username='admin-aprueba', password='x', is_staff=True)
        client.force_login(admin)

        response = client.post(reverse('clientes:aprobar_solicitud_cliente', kwargs={'pk': solicitud.pk}))

        assert response.status_code == 302
        solicitud.refresh_from_db()
        assert solicitud.estado == SolicitudCliente.ESTADO_APROBADA
        assert solicitud.revisado_por == admin
        assert solicitud.cliente_creado is not None
        assert solicitud.cliente_creado.identificador == '7777777'
        assert usuario in solicitud.cliente_creado.usuarios.all()

    def test_aprobar_le_agrega_el_rol_cliente_en_keycloak(self, client):
        """Sin esto, el usuario queda asociado en Django pero sin poder operar nada todavía."""
        usuario = User.objects.create_user(username='con-email', email='con-email@test.com', password='x')
        solicitud = SolicitudCliente.objects.create(usuario=usuario, nombre='Con', apellido='Email', identificador='4444400')
        admin = User.objects.create_user(username='admin-rol', password='x', is_staff=True)
        client.force_login(admin)

        with patch('apps.clientes.views.obtener_roles_de_usuario', return_value=['analista_cambiario']) as mock_obtener, \
             patch('apps.clientes.views.actualizar_roles_de_usuario') as mock_actualizar:
            response = client.post(reverse('clientes:aprobar_solicitud_cliente', kwargs={'pk': solicitud.pk}))

        assert response.status_code == 302
        mock_obtener.assert_called_once_with('con-email@test.com')
        mock_actualizar.assert_called_once_with('con-email@test.com', {'analista_cambiario', 'cliente'})

    def test_aprobar_no_rompe_si_falla_la_asignacion_del_rol_en_keycloak(self, client):
        """El Cliente queda creado igual; solo se avisa que el rol no se pudo asignar."""
        usuario = User.objects.create_user(username='keycloak-caido', email='keycloak-caido@test.com', password='x')
        solicitud = SolicitudCliente.objects.create(usuario=usuario, nombre='Keycloak', apellido='Caido', identificador='5555500')
        admin = User.objects.create_user(username='admin-rol-2', password='x', is_staff=True)
        client.force_login(admin)

        with patch('apps.clientes.views.obtener_roles_de_usuario', side_effect=RuntimeError('sin conexión')):
            response = client.post(reverse('clientes:aprobar_solicitud_cliente', kwargs={'pk': solicitud.pk}))

        assert response.status_code == 302
        solicitud.refresh_from_db()
        assert solicitud.estado == SolicitudCliente.ESTADO_APROBADA
        assert solicitud.cliente_creado is not None

    def test_aprobar_le_manda_un_email_de_aviso_al_usuario(self, client):
        usuario = User.objects.create_user(username='avisado-aprobado', email='avisado-aprobado@test.com', password='x')
        solicitud = SolicitudCliente.objects.create(usuario=usuario, nombre='Avisado', apellido='Aprobado', identificador='6161610')
        admin = User.objects.create_user(username='admin-avisa', password='x', is_staff=True)
        client.force_login(admin)

        with patch('apps.clientes.views.obtener_roles_de_usuario', return_value=[]), \
             patch('apps.clientes.views.actualizar_roles_de_usuario'):
            client.post(reverse('clientes:aprobar_solicitud_cliente', kwargs={'pk': solicitud.pk}))

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ['avisado-aprobado@test.com']
        assert 'aprobada' in mail.outbox[0].subject.lower()

    def test_rechazar_le_manda_un_email_con_el_motivo(self, client):
        usuario = User.objects.create_user(username='avisado-rechazado', email='avisado-rechazado@test.com', password='x')
        solicitud = SolicitudCliente.objects.create(usuario=usuario, nombre='Avisado', apellido='Rechazado', identificador='6262620')
        admin = User.objects.create_user(username='admin-avisa-2', password='x', is_staff=True)
        client.force_login(admin)

        client.post(reverse('clientes:rechazar_solicitud_cliente', kwargs={'pk': solicitud.pk}), {'motivo': 'CI no coincide.'})

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ['avisado-rechazado@test.com']
        assert 'rechazada' in mail.outbox[0].subject.lower()
        assert 'CI no coincide.' in mail.outbox[0].body

    def test_sin_email_no_se_manda_ningun_aviso_ni_rompe_nada(self, client):
        usuario = User.objects.create_user(username='sin-email-aviso', password='x')
        solicitud = SolicitudCliente.objects.create(usuario=usuario, nombre='Sin', apellido='Email', identificador='6363630')
        admin = User.objects.create_user(username='admin-sin-email', password='x', is_staff=True)
        client.force_login(admin)

        response = client.post(reverse('clientes:aprobar_solicitud_cliente', kwargs={'pk': solicitud.pk}))

        assert response.status_code == 302
        assert len(mail.outbox) == 0

    def test_solicitud_juridica_se_puede_enviar_y_aprobar_con_razon_social(self, client):
        """Una solicitud jurídica pide razón social (no nombre/apellido) y crea un Cliente JURIDICA."""
        usuario = User.objects.create_user(username='empresa-solicitante', password='x')
        _loguear_con_rol_cliente(client, usuario)

        response = client.post(reverse('clientes:solicitar_cliente'), {
            'tipo_cliente': 'JURIDICA', 'razon_social': 'Importadora SA', 'identificador': '80099999-1',
        })

        assert response.status_code == 302
        solicitud = SolicitudCliente.objects.get(usuario=usuario)
        assert solicitud.tipo_cliente == 'JURIDICA'
        assert solicitud.razon_social == 'Importadora SA'
        assert solicitud.nombre_completo == 'Importadora SA'

        admin = User.objects.create_user(username='admin-aprueba-juridica', password='x', is_staff=True)
        client.force_login(admin)
        client.post(reverse('clientes:aprobar_solicitud_cliente', kwargs={'pk': solicitud.pk}))

        solicitud.refresh_from_db()
        assert solicitud.cliente_creado.tipo_cliente == 'JURIDICA'
        assert solicitud.cliente_creado.razon_social == 'Importadora SA'

    def test_solicitud_fisica_sin_apellido_se_rechaza_y_juridica_sin_razon_social_tambien(self, client):
        usuario = User.objects.create_user(username='sin-datos-completos', password='x')
        _loguear_con_rol_cliente(client, usuario)

        respuesta_fisica = client.post(reverse('clientes:solicitar_cliente'), {
            'tipo_cliente': 'FISICA', 'nombre': 'Solo Nombre', 'identificador': '6060606',
        })
        assert respuesta_fisica.status_code == 200  # el form vuelve a mostrarse con el error
        assert not SolicitudCliente.objects.filter(identificador='6060606').exists()

        respuesta_juridica = client.post(reverse('clientes:solicitar_cliente'), {
            'tipo_cliente': 'JURIDICA', 'identificador': '7070707',
        })
        assert respuesta_juridica.status_code == 200
        assert not SolicitudCliente.objects.filter(identificador='7070707').exists()

    def test_admin_rechaza_exige_motivo_y_no_crea_ningun_cliente(self, client):
        usuario = User.objects.create_user(username='sera-rechazado', password='x')
        solicitud = SolicitudCliente.objects.create(usuario=usuario, nombre='Jorge', apellido='Ferreira', identificador='8888888')
        admin = User.objects.create_user(username='admin-rechaza', password='x', is_staff=True)
        client.force_login(admin)

        response = client.post(reverse('clientes:rechazar_solicitud_cliente', kwargs={'pk': solicitud.pk}), {
            'motivo': 'Datos insuficientes.',
        })

        assert response.status_code == 302
        solicitud.refresh_from_db()
        assert solicitud.estado == SolicitudCliente.ESTADO_RECHAZADA
        assert solicitud.motivo_rechazo == 'Datos insuficientes.'
        assert not Cliente.objects.filter(identificador='8888888').exists()

        # El usuario puede volver a solicitar después del rechazo.
        _loguear_con_rol_cliente(client, usuario)
        response = client.get(reverse('clientes:solicitar_cliente'))
        assert response.status_code == 200
        assert b'Datos insuficientes.' in response.content

    def test_un_cliente_comun_no_puede_administrar_solicitudes(self, client):
        usuario = User.objects.create_user(username='cliente-comun', password='x')
        solicitud = SolicitudCliente.objects.create(usuario=usuario, nombre='Jorge', apellido='Ferreira', identificador='9999990')
        _loguear_con_rol_cliente(client, usuario)

        assert client.get(reverse('clientes:solicitudes_cliente')).status_code == 403
        assert client.post(reverse('clientes:aprobar_solicitud_cliente', kwargs={'pk': solicitud.pk})).status_code == 403
        assert client.post(reverse('clientes:rechazar_solicitud_cliente', kwargs={'pk': solicitud.pk})).status_code == 403

    def test_el_link_para_solicitar_aparece_solo_para_quien_corresponde(self, client):
        """El link/tarjeta se ve en las pantallas donde corresponde; en home, directamente lo redirige."""
        sin_cliente = User.objects.create_user(username='ve-el-link', password='x')
        _loguear_con_rol_cliente(client, sin_cliente)
        # home() lo redirige directo a solicitar_cliente (ver test de redirección aparte);
        # la tarjeta/link se verifica en una pantalla donde sí aterriza, como tasas vigentes.
        assert b'Solicitar ser cliente' in client.get(reverse('divisas:tasas_vigentes')).content

        con_cliente = User.objects.create_user(username='no-ve-el-link', password='x')
        cliente = Cliente.objects.create(tipo_cliente='FISICA', nombre='Con', apellido='Cliente', identificador='0101010', is_active=True)
        cliente.usuarios.add(con_cliente)
        _loguear_con_rol_cliente(client, con_cliente)
        response_home = client.get(reverse('home'))
        assert response_home.status_code == 200
        assert b'Solicitar ser cliente' not in response_home.content

    def test_home_redirige_directo_a_solicitar_cliente_si_no_tiene_ninguno(self, client):
        """Un usuario con rol 'cliente' sin Cliente asociado aterriza directo en la solicitud, no en home."""
        sin_cliente = User.objects.create_user(username='aterriza-en-solicitud', password='x')
        _loguear_con_rol_cliente(client, sin_cliente)

        response = client.get(reverse('home'))

        assert response.status_code == 302
        assert response.url == reverse('clientes:solicitar_cliente')

    def test_home_no_redirige_a_un_admin_ni_a_quien_ya_tiene_cliente(self, client):
        admin = User.objects.create_user(username='admin-home', password='x', is_staff=True)
        client.force_login(admin)
        session = client.session
        session['keycloak_roles'] = ['admin']
        session.save()
        assert client.get(reverse('home')).status_code == 200

        con_cliente = User.objects.create_user(username='con-cliente-home', password='x')
        cliente = Cliente.objects.create(tipo_cliente='FISICA', nombre='Ya', apellido='Tiene', identificador='0202020', is_active=True)
        cliente.usuarios.add(con_cliente)
        _loguear_con_rol_cliente(client, con_cliente)
        assert client.get(reverse('home')).status_code == 200
