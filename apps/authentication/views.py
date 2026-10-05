"""Vistas personalizadas para el flujo OIDC con Keycloak."""

from urllib.parse import urlencode
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from mozilla_django_oidc.views import OIDCLogoutView, OIDCAuthenticationCallbackView


def url_logout_keycloak(request, id_token, destino):
    """Arma la URL de cierre de sesión de Keycloak que vuelve a ``destino``.

    El ``id_token_hint`` hace que Keycloak cierre su sesión sin pedir
    confirmación (requiere ``OIDC_STORE_ID_TOKEN``).
    """
    params = {
        'client_id': settings.OIDC_RP_CLIENT_ID,
        'post_logout_redirect_uri': request.build_absolute_uri(destino),
    }
    if id_token:
        params['id_token_hint'] = id_token
    return f"{settings.OIDC_OP_LOGOUT_ENDPOINT}?{urlencode(params)}"


class CustomOIDCLogoutView(OIDCLogoutView):
    """Cierra la sesión local y redirige al endpoint de logout de Keycloak."""

    def get(self, request):
        """Permite iniciar el logout mediante una solicitud GET."""
        return self.post(request)

    def post(self, request):
        """Invalida la sesión y construye la URL de salida del proveedor OIDC.

        Al terminar, Keycloak devuelve al usuario a ``oidc_authentication_init``,
        que lo manda directo a la pantalla de inicio de sesión. El
        ``id_token_hint`` hace que Keycloak cierre también su propia sesión;
        sin él la sesión SSO seguía viva y el usuario volvía a entrar sin
        loguearse.
        """
        id_token = request.session.get('oidc_id_token')
        super().post(request)
        return redirect(url_logout_keycloak(request, id_token, reverse('oidc_authentication_init')))


class CustomOIDCCallbackView(OIDCAuthenticationCallbackView):
    """Redirige al usuario autenticado según sus permisos y roles efectivos."""

    def login_success(self):
        """Selecciona el panel de destino después de un login exitoso."""
        response = super().login_success()
        user = self.request.user
        roles = self.request.session.get('keycloak_roles', [])
        if user.is_staff:
            return redirect(reverse('panel_admin'))
        if 'analista_cambiario' in roles:
            return redirect(reverse('divisas:tasas_vigentes'))
        return redirect(reverse('home'))

    def login_failure(self):
        """Si Django rechaza el login, cierra también la sesión de Keycloak.

        Sin esto, la sesión de Keycloak quedaba abierta: cada "Iniciar sesión"
        volvía a entrar automáticamente con la misma cuenta, Django la volvía
        a rechazar y el usuario quedaba atrapado en la pantalla de bienvenida.
        """
        id_token = self.request.session.pop('oidc_id_token', None)
        if not id_token:
            return super().login_failure()
        messages.error(
            self.request,
            'No se pudo iniciar sesión con esa cuenta. Probá de nuevo y, si el '
            'problema sigue, contactá al administrador.',
        )
        return redirect(url_logout_keycloak(self.request, id_token, reverse('home')))
