from urllib.parse import urlencode
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from mozilla_django_oidc.views import OIDCLogoutView, OIDCAuthenticationCallbackView


class CustomOIDCLogoutView(OIDCLogoutView):
    def get(self, request):
        return self.post(request)

    def post(self, request):
        # Extraer el id_token_id guardado por mozilla-django-oidc en la sesión
        id_token = request.session.get('oidc_id_token')

        # Ejecuta el logout de Django (destruye la sesión local)
        super().post(request)

        # Construye el endpoint de logout de Keycloak
        keycloak_logout_url = f"{settings.OIDC_OP_AUTHORIZATION_ENDPOINT.replace('/auth', '/logout')}"

        params = {
            'client_id': settings.OIDC_RP_CLIENT_ID,
            'post_logout_redirect_uri': 'http://localhost:8000/',
        }

        if id_token:
            params['id_token_hint'] = id_token

        return redirect(f"{keycloak_logout_url}?{urlencode(params)}")


class CustomOIDCCallbackView(OIDCAuthenticationCallbackView):
    """
    Sobreescribe el callback de login para redirigir según el rol
    del usuario autenticado.
    """
    def login_success(self):
        response = super().login_success()
        user = self.request.user
        if user.is_staff:
            return redirect(reverse('panel_admin'))
        return redirect(reverse('home'))