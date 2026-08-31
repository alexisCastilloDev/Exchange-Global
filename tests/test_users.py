from unittest.mock import patch
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

User = get_user_model()

@pytest.fixture
def admin_user(db):
    user = User.objects.create_user(username='admin', email='admin@test.com', is_active=True)
    grupo_admin, _ = Group.objects.get_or_create(name='admin')
    user.groups.add(grupo_admin)
    return user

@pytest.mark.django_db
def test_lista_usuarios_filtro_buscador(client, admin_user):
    """CA1 / CA4: Verifica listado y filtrado por nombre o email."""
    client.force_login(admin_user)
    User.objects.create_user(username='juan', email='juan@test.com', first_name='Juan')
    User.objects.create_user(username='pedro', email='pedro@test.com', first_name='Pedro')

    # Búsqueda por filtro
    response = client.get(reverse('lista_usuarios') + '?q=Juan')
    assert response.status_code == 200
    assert 'juan@test.com' in response.content.decode('utf-8')
    assert 'pedro@test.com' not in response.content.decode('utf-8')

@pytest.mark.django_db
@patch('apps.users.views.actualizar_usuario_en_keycloak')
def test_editar_usuario_y_deshabilitar(mock_keycloak, client, admin_user):
    """CA2 / CA3: Edita el usuario y desactiva su estado sincronizando con Keycloak."""
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
    assert response.status_code == 302  # Redirección tras guardar

    target_user.refresh_from_db()
    assert target_user.first_name == 'Carlos Editado'
    assert target_user.is_active is False

    # Valida que se llamó a la función de sincronización con Keycloak
    mock_keycloak.assert_called_once_with(
        email='cliente@test.com',
        first_name='Carlos Editado',
        last_name='Pérez',
        is_active=False
    )