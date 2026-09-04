from urllib.parse import urlencode
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from mozilla_django_oidc.views import OIDCLogoutView, OIDCAuthenticationCallbackView


class CustomOIDCLogoutView(OIDCLogoutView):
    def get(self, request):
        return self.post(request)

    def post(self, request):
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
    def login_success(self):
        """
        Tras un login exitoso, redirige según permisos reales en lugar de usar is_staff.
        Si el usuario tiene permiso para el panel admin, lo enviamos a panel_admin,
        en caso contrario a home.
        """
        response = super().login_success()
        user = self.request.user
        if user.has_perm('authentication.acceder_panel_admin'):
            return redirect(reverse('panel_admin'))
        return redirect(reverse('home'))