"""Pruebas del flujo OIDC y del backend de autenticación."""

from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory

# Importa tu backend personalizado (ajusta la ruta según la estructura de tu proyecto)
from apps.authentication.backends import KeycloakOIDCAuthenticationBackend
from apps.authentication.views import CustomOIDCCallbackView

User = get_user_model()


# ============================================================================
# 1. TESTS DE RUTAS Y VISTAS DE AUTENTICACIÓN
# ============================================================================

@pytest.mark.django_db
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


def test_logout_returns_to_login_screen(client):
    """CA5: Después de cerrar sesión, Keycloak devuelve al usuario a la pantalla de login."""
    response = client.get(reverse('oidc_logout'))
    params = parse_qs(urlparse(response.url).query)
    assert params['post_logout_redirect_uri'] == ['http://testserver/oidc/authenticate/']


@pytest.mark.django_db
def test_logout_sends_id_token_hint(client):
    """CA5: El id_token guardado se envía para cerrar también la sesión SSO de Keycloak."""
    user = User.objects.create_user(username='salida', password='x')
    client.force_login(user)
    session = client.session
    session['oidc_id_token'] = 'token-de-prueba'
    session.save()

    response = client.post(reverse('oidc_logout'))

    params = parse_qs(urlparse(response.url).query)
    assert params['id_token_hint'] == ['token-de-prueba']
    assert '_auth_user_id' not in client.session


def test_id_token_is_stored_in_session(settings):
    """CA5: Sin OIDC_STORE_ID_TOKEN no habría id_token_hint al cerrar sesión."""
    assert settings.OIDC_STORE_ID_TOKEN is True


def test_protected_route_redirects_unauthenticated_user(client):
    """CA3 / CA4: Si no hay token o sesión válida, redirige al login."""
    # Descomenta y ajusta con el nombre de tu ruta protegida:
    # response = client.get(reverse('protected_view'))
    # assert response.status_code == 302
    pass


# ============================================================================
# 3. ACCESO A LA DOCUMENTACIÓN TÉCNICA (SPHINX)
# ============================================================================

@pytest.mark.django_db
def test_documentacion_requiere_sesion(client):
    """Sin sesión iniciada, redirige al login en vez de servir la documentación."""
    response = client.get(reverse('documentacion'))
    assert response.status_code == 302


@pytest.mark.django_db
def test_documentacion_rechaza_usuario_sin_rol_admin(client):
    """Un usuario autenticado sin rol admin ni is_staff no puede ver la documentación."""
    user = User.objects.create_user(username='cliente1', email='cliente1@test.com')
    client.force_login(user)
    session = client.session
    session['keycloak_roles'] = ['cliente']
    session.save()

    response = client.get(reverse('documentacion'))

    assert response.status_code == 403


@pytest.mark.django_db
def test_documentacion_sirve_el_index_a_un_administrador(client):
    """Un usuario con rol admin en sesión obtiene la portada de la documentación compilada."""
    user = User.objects.create_user(username='admin1', email='admin1@test.com')
    client.force_login(user)
    session = client.session
    session['keycloak_roles'] = ['admin']
    session.save()

    response = client.get(reverse('documentacion'))

    assert response.status_code == 200


@pytest.mark.django_db
def test_documentacion_sirve_archivos_internos_a_staff(client):
    """``is_staff`` también habilita el acceso, sin depender del rol de sesión."""
    user = User.objects.create_user(username='staff1', email='staff1@test.com', is_staff=True)
    client.force_login(user)

    response = client.get(reverse('documentacion_archivo', args=['guia.html']))

    assert response.status_code == 200


# ============================================================================
# 2. TESTS DEL BACKEND (VERIFICACIÓN DE EMAIL Y ROLES)
# ============================================================================

@pytest.fixture
def backend():
    """Construye el backend OIDC bajo prueba."""
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


@pytest.mark.django_db
def test_login_siempre_redirige_a_inicio_sin_importar_el_rol(rf):
    """El callback de Keycloak lleva a "Inicio" sin importar el rol (admin, analista, cliente)."""
    for roles in (['analista_cambiario'], ['admin'], ['cliente'], []):
        request = rf.get('/oidc/callback/')
        request.session = SessionStore()
        request.session['keycloak_roles'] = roles
        request.user = User.objects.create_user(
            username=f'login-{"-".join(roles) or "sin-rol"}',
            email=f'login-{"-".join(roles) or "sin-rol"}@test.com',
            is_staff='admin' in roles,
        )
        callback = CustomOIDCCallbackView()
        callback.request = request

        with patch(
            'mozilla_django_oidc.views.OIDCAuthenticationCallbackView.login_success',
            return_value=None,
        ):
            response = callback.login_success()

        assert response.status_code == 302
        assert response.url == reverse('home')


# ============================================================================
# 4. LOGIN RECHAZADO Y USUARIOS LOCALES INACTIVOS
# ============================================================================

@pytest.mark.django_db
def test_login_en_keycloak_reactiva_usuario_local_inactivo(backend, rf):
    """Un registro local inactivo (resto viejo) se reactiva si Keycloak autenticó al usuario."""
    request = rf.get('/')
    request.session = {}
    user = User.objects.create_user(username='vuelve', email='vuelve@example.com', is_active=False)

    backend.update_user_claims(user, {'email': 'vuelve@example.com', 'realm_access': {'roles': []}}, request=request)
    user.refresh_from_db()

    assert user.is_active is True


@pytest.mark.django_db
def test_login_rechazado_cierra_tambien_la_sesion_de_keycloak(client, settings):
    """Si Django rechaza el login, Keycloak cierra su sesión para que no quede en bucle."""
    session = client.session
    session['oidc_id_token'] = 'token-rechazado'
    session.save()
    request = RequestFactory().get('/oidc/callback/')
    request.session = client.session
    request._messages = FallbackStorage(request)
    callback = CustomOIDCCallbackView()
    callback.request = request

    response = callback.login_failure()

    url = urlparse(response.url)
    params = parse_qs(url.query)
    assert response.url.startswith(settings.OIDC_OP_LOGOUT_ENDPOINT)
    assert params['id_token_hint'] == ['token-rechazado']
    assert params['post_logout_redirect_uri'] == ['http://testserver/']
    assert 'oidc_id_token' not in request.session
    assert any('No se pudo iniciar sesión' in str(m) for m in get_messages(request))


def test_login_rechazado_sin_token_vuelve_al_inicio(rf):
    """Sin id_token (por ejemplo, un state vencido) no hay sesión de Keycloak que cerrar."""
    request = rf.get('/oidc/callback/')
    request.session = {}
    callback = CustomOIDCCallbackView()
    callback.request = request

    response = callback.login_failure()

    assert response.url == '/'


def test_sesion_termina_al_cerrar_el_navegador(settings):
    """Sin "Mantener la sesión iniciada", la sesión no sobrevive al cierre del navegador."""
    assert settings.SESSION_EXPIRE_AT_BROWSER_CLOSE is True
