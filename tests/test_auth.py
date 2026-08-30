import pytest
from django.urls import reverse


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


@pytest.mark.django_db
def test_protected_route_redirects_unauthenticated_user(client):
    """CA3 / CA4: Si no hay token o sesión válida, redirige al login."""
    response = client.get(reverse('panel_protegido'))
    assert response.status_code == 302