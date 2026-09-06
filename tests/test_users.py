from unittest.mock import patch
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(username='admin', email='admin@test.com', is_active=True, is_staff=True)


def _login_con_roles(client, user, roles):
    """Simula lo que backends.py deja en sesión tras un login real con esos roles."""
    client.force_login(user)
    session = client.session
    session['keycloak_roles'] = roles
    session.save()


@pytest.mark.django_db
def test_lista_usuarios_filtro_buscador(client, admin_user):
    """CA1 / CA4: Verifica listado y filtrado por nombre o email."""
    _login_con_roles(client, admin_user, roles=['admin'])
    User.objects.create_user(username='juan', email='juan@test.com', first_name='Juan')
    User.objects.create_user(username='pedro', email='pedro@test.com', first_name='Pedro')

    response = client.get(reverse('lista_usuarios') + '?q=Juan')
    assert response.status_code == 200
    assert 'juan@test.com' in response.content.decode('utf-8')
    assert 'pedro@test.com' not in response.content.decode('utf-8')


@pytest.mark.django_db
@patch('apps.users.views.actualizar_usuario_en_keycloak')
def test_editar_usuario_y_deshabilitar(mock_keycloak, client, admin_user):
    """CA2 / CA3: Edita el usuario y desactiva su estado sincronizando con Keycloak."""
    _login_con_roles(client, admin_user, roles=['admin'])
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

    mock_keycloak.assert_called_once_with(
        email='cliente@test.com',
        first_name='Carlos Editado',
        last_name='Pérez',
        is_active=False
    )