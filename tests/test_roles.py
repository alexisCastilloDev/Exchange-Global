"""
Tests de la HU GE-7 "Gestión de roles, permisos y control de acceso".

Se testea la lógica de autorización de forma aislada del flujo OIDC
real (usando client.force_login), ya que lo que se valida acá es el
comportamiento del decorador `requiere_permiso` y del panel de
gestión de roles, no el login en sí (eso ya está cubierto en
test_auth.py, GE-3).
"""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from apps.authentication.models import RecursoProtegido

User = get_user_model()


@pytest.fixture
def recurso_panel_admin(db):
    """
    RecursoProtegido de panel_admin, para usar en los tests.

    Ya viene cargado por la data migration 0002_cargar_recursos_iniciales
    (corre también sobre la base de test), así que se usa get_or_create
    en vez de create() para no chocar contra la restricción de unicidad
    si ya existe.
    """
    return RecursoProtegido.objects.get_or_create(
        codigo='panel_admin', defaults={'nombre': 'Panel de administración'}
    )[0]


@pytest.fixture
def grupo_admin(db):
    return Group.objects.get_or_create(name='admin')[0]


@pytest.fixture
def grupo_cliente(db):
    return Group.objects.get_or_create(name='cliente')[0]


@pytest.fixture
def usuario_admin(db, grupo_admin, recurso_panel_admin):
    """Usuario con rol admin y el permiso de panel_admin ya asignado."""
    user = User.objects.create_user(username='admin1', email='admin1@test.com', is_staff=True)
    user.groups.add(grupo_admin)
    permiso = Permission.objects.get(codename='acceder_panel_admin', content_type__app_label='authentication')
    grupo_admin.permissions.add(permiso)
    return user


@pytest.fixture
def usuario_cliente(db, grupo_cliente):
    """Usuario con rol cliente, SIN permisos asignados todavía."""
    user = User.objects.create_user(username='cliente1', email='cliente1@test.com')
    user.groups.add(grupo_cliente)
    return user


# ============================================================================
# CA1: definir permisos de un rol se aplica a todos los usuarios de ese rol
# ============================================================================

@pytest.mark.django_db
def test_admin_asigna_permiso_a_grupo_y_aplica_a_todos_sus_miembros(
    client, usuario_admin, grupo_cliente, recurso_panel_admin
):
    otro_cliente = User.objects.create_user(username='cliente2', email='cliente2@test.com')
    otro_cliente.groups.add(grupo_cliente)

    client.force_login(usuario_admin)
    client.post(reverse('gestion_roles'), {
        'grupo_id': grupo_cliente.id,
        'recursos': ['panel_admin'],
    })

    # Ambos usuarios del grupo cliente quedan con el permiso, sin tocarlos individualmente
    assert grupo_cliente.permissions.filter(codename='acceder_panel_admin').exists()
    client.force_login(otro_cliente)
    response = client.get(reverse('panel_admin'))
    assert response.status_code == 200


# ============================================================================
# CA2: usuario sin permiso es denegado con mensaje
# ============================================================================

@pytest.mark.django_db
def test_usuario_sin_permiso_es_denegado(client, usuario_cliente, recurso_panel_admin):
    client.force_login(usuario_cliente)
    response = client.get(reverse('panel_admin'), follow=True)

    assert response.redirect_chain[0][1] == 302
    mensajes = [str(m) for m in response.context['messages']]
    assert any('permiso' in m.lower() for m in mensajes)


@pytest.mark.django_db
def test_usuario_con_permiso_accede(client, usuario_cliente, grupo_cliente, recurso_panel_admin):
    permiso = Permission.objects.get(codename='acceder_panel_admin', content_type__app_label='authentication')
    grupo_cliente.permissions.add(permiso)

    client.force_login(usuario_cliente)
    response = client.get(reverse('panel_admin'))
    assert response.status_code == 200


# ============================================================================
# CA3: el cambio de permiso aplica sin que el usuario vuelva a loguearse
# ============================================================================

@pytest.mark.django_db
def test_cambio_de_permiso_aplica_sin_relogin(client, usuario_cliente, grupo_cliente, recurso_panel_admin):
    client.force_login(usuario_cliente)

    # Sin permiso: denegado
    response = client.get(reverse('panel_admin'))
    assert response.status_code == 302

    # El admin le agrega el permiso al grupo del usuario "por detrás"
    permiso = Permission.objects.get(codename='acceder_panel_admin', content_type__app_label='authentication')
    grupo_cliente.permissions.add(permiso)

    # El MISMO client, sin volver a loguearse, ya puede entrar
    response = client.get(reverse('panel_admin'))
    assert response.status_code == 200


# ============================================================================
# CA4: acceso directo por URL también se bloquea, no solo el menú
# ============================================================================

@pytest.mark.django_db
def test_acceso_directo_por_url_se_bloquea_igual(client, usuario_cliente, recurso_panel_admin):
    client.force_login(usuario_cliente)
    # Entra directo a la URL, sin pasar por ningún link del menú
    response = client.get('/panel-admin/')
    assert response.status_code == 302


@pytest.mark.django_db
def test_usuario_no_autenticado_es_redirigido_al_login(client, recurso_panel_admin):
    response = client.get(reverse('panel_admin'))
    assert response.status_code == 302