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


def test_logout_redirige_a_keycloak_con_el_post_logout_uri_correcto(client):
    """CA5: El logout invalida y redirige a Keycloak, con el post_logout_redirect_uri correcto."""
    response = client.get(reverse('oidc_logout'))

    assert response.status_code == 302
    assert 'post_logout_redirect_uri' in response.url
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


def test_configuracion_basica_de_autenticacion_y_sesion(settings):
    """Invariantes de configuración que sostienen el resto del flujo OIDC/sesión."""
    # CA1/CA5: rutas críticas de autenticación y logout disponibles.
    assert reverse('oidc_authentication_init') == '/oidc/authenticate/'
    assert reverse('oidc_logout') == '/oidc/logout/'
    # CA5: sin OIDC_STORE_ID_TOKEN no habría id_token_hint al cerrar sesión.
    assert settings.OIDC_STORE_ID_TOKEN is True
    # Sin "Mantener la sesión iniciada", la sesión no sobrevive al cierre del navegador.
    assert settings.SESSION_EXPIRE_AT_BROWSER_CLOSE is True


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
def test_documentacion_segun_el_rol_en_sesion(client):
    """Sin sesión redirige al login; con rol no-admin, 403; con rol admin, 200."""
    # Sin sesión iniciada, redirige al login en vez de servir la documentación.
    response = client.get(reverse('documentacion'))
    assert response.status_code == 302

    # Un usuario autenticado sin rol admin ni is_staff no puede ver la documentación.
    user = User.objects.create_user(username='cliente1', email='cliente1@test.com')
    client.force_login(user)
    session = client.session
    session['keycloak_roles'] = ['cliente']
    session.save()
    response = client.get(reverse('documentacion'))
    assert response.status_code == 403

    # Un usuario con rol admin en sesión obtiene la portada de la documentación compilada.
    admin = User.objects.create_user(username='admin1', email='admin1@test.com')
    client.force_login(admin)
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


def test_verify_claims_segun_email_verified(backend):
    """CA: email_verified=False deniega el acceso; True lo permite."""
    with patch('mozilla_django_oidc.auth.OIDCAuthenticationBackend.verify_claims', return_value=True):
        claims_no_verificado = {'sub': '12345', 'email': 'unverified@example.com', 'email_verified': False}
        assert backend.verify_claims(claims_no_verificado) is False

        claims_verificado = {'sub': '12345', 'email': 'verified@example.com', 'email_verified': True}
        assert backend.verify_claims(claims_verificado) is True


@pytest.mark.django_db
def test_update_user_claims(backend, rf):
    """Guarda los roles de negocio en sesión, los reemplaza (no acumula), y reactiva cuentas inactivas."""
    # Los roles de negocio del token quedan en session['keycloak_roles'].
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

    # Cada login sobreescribe la sesión con los roles ACTUALES, no acumula.
    request_reemplazo = rf.get('/')
    request_reemplazo.session = {'keycloak_roles': ['admin', 'cajero']}  # roles de un login anterior
    cajero = User.objects.create_user(username='cajero1', email='cajero@example.com')
    claims_reemplazo = {'given_name': 'Cajero', 'family_name': 'Uno', 'realm_access': {'roles': ['cliente']}}
    backend.update_user_claims(cajero, claims_reemplazo, request=request_reemplazo)
    cajero.refresh_from_db()
    assert request_reemplazo.session['keycloak_roles'] == ['cliente']
    assert cajero.is_staff is False

    # Un registro local inactivo (resto viejo) se reactiva si Keycloak autenticó al usuario.
    request_inactivo = rf.get('/')
    request_inactivo.session = {}
    inactivo = User.objects.create_user(username='vuelve', email='vuelve@example.com', is_active=False)
    backend.update_user_claims(
        inactivo, {'email': 'vuelve@example.com', 'realm_access': {'roles': []}}, request=request_inactivo,
    )
    inactivo.refresh_from_db()
    assert inactivo.is_active is True


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
# 4. LOGIN RECHAZADO
# ============================================================================

@pytest.mark.django_db
def test_login_failure_cierra_la_sesion_de_keycloak_solo_si_habia_id_token(client, settings):
    """Con id_token en sesión, cierra también la de Keycloak; sin él, solo vuelve al inicio."""
    # Si Django rechaza el login, Keycloak cierra su sesión para que no quede en bucle.
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

    # Sin id_token (por ejemplo, un state vencido) no hay sesión de Keycloak que cerrar.
    request_sin_token = RequestFactory().get('/oidc/callback/')
    request_sin_token.session = {}
    callback_sin_token = CustomOIDCCallbackView()
    callback_sin_token.request = request_sin_token
    response_sin_token = callback_sin_token.login_failure()
    assert response_sin_token.url == '/'
