"""
Tests de la HU GE-7 "Gestión de roles, permisos y control de acceso".

Reescrito tras el bugfix de delegación de auth/autz a Keycloak:
- Ya no existen Group/Permission/RecursoProtegido en Django.
- La autorización se verifica contra request.session['keycloak_roles']
  (decorador requiere_permiso en apps.authentication.decorators).
- La asignación real de roles se hace contra la Keycloak Admin API
  (apps.users.services), mockeada acá para no depender de un servidor
  Keycloak real en los tests.
"""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


@pytest.fixture
def usuario_admin(db):
    return User.objects.create_user(username='admin1', email='admin1@test.com', is_staff=True)


@pytest.fixture
def usuario_gestor_roles(db):
    """Tiene el rol específico 'gestion_roles', pero NO 'admin'."""
    return User.objects.create_user(username='gestor1', email='gestor1@test.com')


@pytest.fixture
def usuario_con_permiso_usuarios(db):
    """Tiene el rol 'usuarios', pero NO 'gestion_roles' ni 'admin'."""
    return User.objects.create_user(username='soporte1', email='soporte1@test.com')


@pytest.fixture
def usuario_cliente(db):
    """Sin ningún rol de negocio especial."""
    return User.objects.create_user(username='cliente1', email='cliente1@test.com')


@pytest.fixture
def usuario_objetivo(db):
    """El usuario cuyos datos/roles se van a editar en los tests."""
    return User.objects.create_user(
        username='objetivo1', email='objetivo1@test.com',
        first_name='Ana', last_name='Gómez',
    )


def _login_con_roles(client, user, roles):
    """Simula lo que backends.py deja en sesión tras un login real con esos roles."""
    client.force_login(user)
    session = client.session
    session['keycloak_roles'] = roles
    session.save()


# ============================================================================
# lista_usuarios_view / editar_usuario_view: requieren rol 'usuarios' o 'admin'
# ============================================================================

@pytest.mark.django_db
def test_usuario_no_autenticado_es_redirigido_al_login(client):
    response = client.get(reverse('lista_usuarios'))
    assert response.status_code == 302


@pytest.mark.django_db
def test_usuario_sin_rol_usuarios_es_denegado(client, usuario_cliente):
    _login_con_roles(client, usuario_cliente, roles=['cliente'])
    response = client.get(reverse('lista_usuarios'), follow=True)
    assert response.status_code == 200  # terminó en 'home' tras el redirect
    mensajes = [str(m) for m in response.context['messages']]
    assert any('permiso' in m.lower() for m in mensajes)


@pytest.mark.django_db
def test_usuario_con_rol_usuarios_accede_a_la_lista(client, usuario_con_permiso_usuarios):
    _login_con_roles(client, usuario_con_permiso_usuarios, roles=['usuarios'])
    response = client.get(reverse('lista_usuarios'))
    assert response.status_code == 200


@pytest.mark.django_db
def test_admin_accede_a_la_lista_sin_tener_el_rol_especifico(client, usuario_admin):
    """El rol 'admin' siempre pasa el decorador, sin importar el código de recurso."""
    _login_con_roles(client, usuario_admin, roles=['admin'])
    response = client.get(reverse('lista_usuarios'))
    assert response.status_code == 200


@pytest.mark.django_db
@patch('apps.users.views.sincronizar_usuarios_desde_keycloak')
def test_busqueda_filtra_por_nombre_apellido_o_email(mock_sync, client, usuario_con_permiso_usuarios, usuario_objetivo):
    _login_con_roles(client, usuario_con_permiso_usuarios, roles=['usuarios'])
    response = client.get(reverse('lista_usuarios'), {'q': 'Ana'})
    assert response.status_code == 200
    assert usuario_objetivo in response.context['usuarios']


@pytest.mark.django_db
def test_editar_usuario_actualiza_datos_locales_y_en_keycloak(client, usuario_con_permiso_usuarios, usuario_objetivo):
    _login_con_roles(client, usuario_con_permiso_usuarios, roles=['usuarios'])

    with patch('apps.users.views.actualizar_usuario_en_keycloak') as mock_actualizar:
        response = client.post(
            reverse('editar_usuario', args=[usuario_objetivo.id]),
            {'first_name': 'Ana María', 'last_name': 'Gómez', 'is_active': 'on'},
        )

    mock_actualizar.assert_called_once_with(
        email=usuario_objetivo.email,
        first_name='Ana María',
        last_name='Gómez',
        is_active=True,
    )
    usuario_objetivo.refresh_from_db()
    assert usuario_objetivo.first_name == 'Ana María'
    assert response.status_code == 302


@pytest.mark.django_db
def test_editar_usuario_muestra_error_si_keycloak_falla(client, usuario_con_permiso_usuarios, usuario_objetivo):
    _login_con_roles(client, usuario_con_permiso_usuarios, roles=['usuarios'])

    with patch('apps.users.views.actualizar_usuario_en_keycloak', side_effect=Exception('timeout')):
        response = client.post(
            reverse('editar_usuario', args=[usuario_objetivo.id]),
            {'first_name': 'Ana María', 'last_name': 'Gómez'},
            follow=True,
        )

    mensajes = [str(m) for m in response.context['messages']]
    assert any('error' in m.lower() for m in mensajes)
    usuario_objetivo.refresh_from_db()
    assert usuario_objetivo.first_name == 'Ana'  # no se guardó nada localmente si Keycloak falló


# ============================================================================
# editar_roles_view: requiere el rol específico 'gestion_roles' (o 'admin')
# ============================================================================

@pytest.mark.django_db
def test_usuario_con_rol_usuarios_no_puede_gestionar_roles(client, usuario_con_permiso_usuarios, usuario_objetivo):
    """'usuarios' no alcanza para /roles/: son permisos distintos."""
    _login_con_roles(client, usuario_con_permiso_usuarios, roles=['usuarios'])
    response = client.get(reverse('editar_roles', args=[usuario_objetivo.id]), follow=True)
    mensajes = [str(m) for m in response.context['messages']]
    assert any('permiso' in m.lower() for m in mensajes)


@pytest.mark.django_db
def test_usuario_con_rol_gestion_roles_ve_el_formulario(client, usuario_gestor_roles, usuario_objetivo):
    _login_con_roles(client, usuario_gestor_roles, roles=['gestion_roles'])

    with patch('apps.users.views.obtener_roles_disponibles', return_value=['admin', 'cajero', 'usuarios']), \
         patch('apps.users.views.obtener_roles_de_usuario', return_value=['cajero']):
        response = client.get(reverse('editar_roles', args=[usuario_objetivo.id]))

    assert response.status_code == 200
    assert response.context['roles_disponibles'] == ['admin', 'cajero', 'usuarios']
    assert response.context['roles_actuales'] == ['cajero']


@pytest.mark.django_db
def test_admin_asigna_roles_y_se_notifica_relogin_requerido(client, usuario_admin, usuario_objetivo):
    _login_con_roles(client, usuario_admin, roles=['admin'])

    with patch('apps.users.views.obtener_roles_disponibles', return_value=['admin', 'cajero']), \
         patch('apps.users.views.obtener_roles_de_usuario', return_value=['cajero']), \
         patch('apps.users.views.actualizar_roles_de_usuario') as mock_actualizar:
        response = client.post(
            reverse('editar_roles', args=[usuario_objetivo.id]),
            {'roles': ['admin', 'cajero']},
            follow=True,
        )

    mock_actualizar.assert_called_once_with(usuario_objetivo.email, ['admin', 'cajero'])
    mensajes = [str(m) for m in response.context['messages']]
    assert any('volver a loguearse' in m.lower() for m in mensajes)


@pytest.mark.django_db
def test_editar_roles_muestra_error_si_keycloak_falla_al_consultar(client, usuario_admin, usuario_objetivo):
    _login_con_roles(client, usuario_admin, roles=['admin'])

    with patch('apps.users.views.obtener_roles_disponibles', side_effect=Exception('conexión rechazada')):
        response = client.get(reverse('editar_roles', args=[usuario_objetivo.id]), follow=True)

    mensajes = [str(m) for m in response.context['messages']]
    assert any('error' in m.lower() for m in mensajes)


@pytest.mark.django_db
def test_cambio_de_rol_no_aplica_sin_relogin(client, usuario_gestor_roles, usuario_objetivo):
    """
    Documenta el comportamiento esperado: aunque el admin cambie los
    roles en Keycloak, el propio USUARIO OBJETIVO no ve el cambio
    reflejado en su sesión activa hasta volver a loguearse.
    """
    _login_con_roles(client, usuario_objetivo, roles=['cliente'])
    response = client.get(reverse('lista_usuarios'))
    assert response.status_code == 302  # sigue sin el rol 'usuarios' en SU sesión actual