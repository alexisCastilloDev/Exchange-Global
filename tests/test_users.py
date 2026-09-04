from unittest.mock import patch
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from apps.authentication.models import RecursoProtegido

User = get_user_model()

@pytest.fixture
def admin_user(db):
    user = User.objects.create_user(username='admin', email='admin@test.com', is_active=True)
    grupo_admin, _ = Group.objects.get_or_create(name='admin')
    recurso, _ = RecursoProtegido.objects.get_or_create(codigo='panel_admin', defaults={'nombre':'Panel de administración'})
    ct = ContentType.objects.get_for_model(RecursoProtegido)
    permiso, _ = Permission.objects.get_or_create(codename='acceder_panel_admin', content_type=ct, defaults={'name':'Puede acceder a Panel de administración'})
    grupo_admin.permissions.add(permiso)
    user.groups.add(grupo_admin)
    return user

@pytest.mark.django_db
def test_lista_usuarios_filtro_buscador(client, admin_user):
    client.force_login(admin_user)
    User.objects.create_user(username='juan', email='juan@test.com', first_name='Juan')
    User.objects.create_user(username='pedro', email='pedro@test.com', first_name='Pedro')

    response = client.get(reverse('lista_usuarios') + '?q=Juan')
    assert response.status_code == 200
    assert 'juan@test.com' in response.content.decode('utf-8')
    assert 'pedro@test.com' not in response.content.decode('utf-8')

@pytest.mark.django_db
@patch('apps.users.views.actualizar_usuario_en_keycloak')
def test_editar_usuario_y_deshabilitar(mock_keycloak, client, admin_user):
    client.force_login(admin_user)
    target_user = User.objects.create_user(
        username='cliente', email='cliente@test.com', first_name='Carlos', is_active=True
    )

    url = reverse('editar_usuario', args=[target_user.id])
    data = {
        'first_name': 'Carlos Editado',
        'last_name': 'Pérez',
        'is_active': ''  # Desmarcado representa Inactivo
    }

    response = client.post(url, data)
    assert response.status_code == 302

    target_user.refresh_from_db()
    assert target_user.first_name == 'Carlos Editado'
    assert target_user.is_active is False

    mock_keycloak.assert_called_once_with(
        email='cliente@test.com',
        first_name='Carlos Editado',
        last_name='Pérez',
        is_active=False
    )