"""Vistas personalizadas para el flujo OIDC con Keycloak."""

from urllib.parse import urlencode
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from mozilla_django_oidc.views import OIDCLogoutView, OIDCAuthenticationCallbackView


class CustomOIDCLogoutView(OIDCLogoutView):
    """Cierra la sesión local y redirige al endpoint de logout de Keycloak."""

    def get(self, request):
        """Permite iniciar el logout mediante una solicitud GET."""
        return self.post(request)

    def post(self, request):
        """Invalida la sesión y construye la URL de salida del proveedor OIDC."""
        id_token = request.session.get('oidc_id_token')
        super().post(request)
        keycloak_logout_url = f"{settings.OIDC_OP_AUTHORIZATION_ENDPOINT.replace('/auth', '/logout')}"
        params = {
            'client_id': settings.OIDC_RP_CLIENT_ID,
            'post_logout_redirect_uri': 'http://localhost:8000/',
        }
        if id_token:
            params['id_token_hint'] = id_token
        return redirect(f"{keycloak_logout_url}?{urlencode(params)}")


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