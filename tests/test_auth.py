from unittest.mock import patch
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model

# Importa tu backend personalizado (ajusta la ruta según la estructura de tu proyecto)
from apps.authentication.backends import KeycloakOIDCAuthenticationBackend

User = get_user_model()


# ============================================================================
# 1. TESTS DE RUTAS Y VISTAS DE AUTENTICACIÓN
# ============================================================================

def test_home_page_unauthenticated(client):
    """CA1 / CA5: El usuario no autenticado ve la opción de login."""
    response = client.get(reverse('home'))
    assert response.status_code == 200
    assert 'Iniciar Sesión con Keycloak SSO' in response.content.decode('utf-8')


def test_oidc_urls_resolved():
    """CA1 / CA5: Las rutas críticas de autenticación y logout están disponibles."""
    assert reverse('oidc_authentication_init') == '/oidc/authenticate/'
    assert reverse('oidc_logout') == '/oidc/logout/'


def test_custom_logout_redirects_to_keycloak(client):
    """CA5: El logout invalida y redirige a Keycloak."""
    response = client.get(reverse('oidc_logout'))
    assert response.status_code == 302
    assert 'post_logout_redirect_uri' in response.url


def test_protected_route_redirects_unauthenticated_user(client):
    """CA3 / CA4: Si no hay token o sesión válida, redirige al login."""
    # Descomenta y ajusta con el nombre de tu ruta protegida:
    # response = client.get(reverse('protected_view'))
    # assert response.status_code == 302
    pass


# ============================================================================
# 2. TESTS DEL BACKEND (VERIFICACIÓN DE EMAIL Y ROLES)
# ============================================================================

@pytest.fixture
def backend():
    return KeycloakOIDCAuthenticationBackend()


def test_verify_claims_rechaza_correo_no_verificado(backend):
    """CA: Si email_verified es False en Keycloak, deniega el acceso."""
    claims = {
        'sub': '12345',
        'email': 'unverified@example.com',
        'email_verified': False,
    }

    with patch('mozilla_django_oidc.auth.OIDCAuthenticationBackend.verify_claims', return_value=True):
        assert backend.verify_claims(claims) is False


def test_verify_claims_acepta_correo_verificado(backend):
    """CA: Si email_verified es True, permite la autenticación."""
    claims = {
        'sub': '12345',
        'email': 'verified@example.com',
        'email_verified': True,
    }

    with patch('mozilla_django_oidc.auth.OIDCAuthenticationBackend.verify_claims', return_value=True):
        assert backend.verify_claims(claims) is True


@pytest.mark.django_db
def test_update_user_claims_guarda_roles_en_sesion(backend, rf):
    """CA: Los roles de negocio del token quedan en session['keycloak_roles']."""
    request = rf.get('/')
    request.session = {}
    user = User.objects.create_user(username='testuser', email='test@example.com')
    claims = {
        'given_name': 'Juan',
        'family_name': 'Pérez',
        'email': 'test@example.com',
        'realm_access': {'roles': ['admin', 'cajero', 'offline_access']},
    }

    backend.update_user_claims(user, claims, request=request)
    user.refresh_from_db()

    assert user.first_name == 'Juan'
    assert user.last_name == 'Pérez'
    assert user.is_staff is True
    assert user.is_superuser is False  # Regla de negocio: nunca superuser
    # 'offline_access' es un rol técnico de Keycloak, no de negocio: debe quedar excluido
    assert request.session['keycloak_roles'] == ['admin', 'cajero']


@pytest.mark.django_db
def test_update_user_claims_reemplaza_roles_previos_en_sesion(backend, rf):
    """CA: cada login sobreescribe la sesión con los roles ACTUALES, no acumula."""
    request = rf.get('/')
    request.session = {'keycloak_roles': ['admin', 'cajero']}  # roles de un login anterior
    user = User.objects.create_user(username='cajero1', email='cajero@example.com')

    # Ahora Keycloak solo le manda el rol 'cliente'
    claims = {
        'given_name': 'Cajero',
        'family_name': 'Uno',
        'realm_access': {'roles': ['cliente']},
    }

    backend.update_user_claims(user, claims, request=request)
    user.refresh_from_db()

    assert request.session['keycloak_roles'] == ['cliente']
    assert user.is_staff is False