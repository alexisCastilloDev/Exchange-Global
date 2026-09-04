"""
Tests de la HU GE-7 "Gestión de roles, permisos y control de acceso".
"""
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from apps.authentication.models import RecursoProtegido

User = get_user_model()


@pytest.fixture
def recurso_panel_admin(db):
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
    user = User.objects.create_user(username='admin1', email='admin1@test.com')
    user.groups.add(grupo_admin)
    # Garantizar permiso
    ct = ContentType.objects.get_for_model(RecursoProtegido)
    permiso, _ = Permission.objects.get_or_create(codename='acceder_panel_admin', content_type=ct, defaults={'name':'Puede acceder a Panel de administración'})
    grupo_admin.permissions.add(permiso)
    return user


@pytest.fixture
def usuario_cliente(db, grupo_cliente):
    user = User.objects.create_user(username='cliente1', email='cliente1@test.com')
    user.groups.add(grupo_cliente)
    return user


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

    assert grupo_cliente.permissions.filter(codename='acceder_panel_admin').exists()
    client.force_login(otro_cliente)
    response = client.get(reverse('panel_admin'))
    assert response.status_code == 200


@pytest.mark.django_db
def test_usuario_sin_permiso_es_denegado(client, usuario_cliente, recurso_panel_admin):
    client.force_login(usuario_cliente)
    response = client.get(reverse('panel_admin'), follow=True)

    assert response.redirect_chain[0][1] == 302
    mensajes = [str(m) for m in response.context['messages']]
    assert any('permiso' in m.lower() for m in mensajes)


@pytest.mark.django_db
def test_usuario_con_permiso_accede(client, usuario_cliente, grupo_cliente, recurso_panel_admin):
    ct = ContentType.objects.get_for_model(RecursoProtegido)
    permiso, _ = Permission.objects.get_or_create(codename='acceder_panel_admin', content_type=ct, defaults={'name':'Puede acceder a Panel de administración'})
    grupo_cliente.permissions.add(permiso)

    client.force_login(usuario_cliente)
    response = client.get(reverse('panel_admin'))
    assert response.status_code == 200


@pytest.mark.django_db
def test_cambio_de_permiso_aplica_sin_relogin(client, usuario_cliente, grupo_cliente, recurso_panel_admin):
    client.force_login(usuario_cliente)

    response = client.get(reverse('panel_admin'))
    assert response.status_code == 302

    ct = ContentType.objects.get_for_model(RecursoProtegido)
    permiso, _ = Permission.objects.get_or_create(codename='acceder_panel_admin', content_type=ct, defaults={'name':'Puede acceder a Panel de administración'})
    grupo_cliente.permissions.add(permiso)

    response = client.get(reverse('panel_admin'))
    assert response.status_code == 200


@pytest.mark.django_db
def test_acceso_directo_por_url_se_bloquea_igual(client, usuario_cliente, recurso_panel_admin):
    client.force_login(usuario_cliente)
    response = client.get('/panel-admin/')
    assert response.status_code == 302


@pytest.mark.django_db
def test_usuario_no_autenticado_es_redirigido_al_login(client, recurso_panel_admin):
    response = client.get(reverse('panel_admin'))
    assert response.status_code == 302