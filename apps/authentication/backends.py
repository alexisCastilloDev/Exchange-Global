"""
Backend de autenticación que conecta Django con Keycloak vía OIDC.

Además de autenticar, sincroniza los roles de negocio que vienen en el
token de Keycloak (claim `realm_access.roles`) hacia Django Groups, para
que el sistema de permisos nativo de Django (`user.has_perm(...)`) pueda
usarse como mecanismo de autorización granular por rol (ver GE-7).

Deliberadamente NO se usa `is_superuser`: ese flag hace que Django
ignore cualquier chequeo de permisos, lo cual anularía por completo la
gestión de permisos por rol que pide GE-7.
"""
from django.contrib.auth.models import Group
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

# Roles de negocio soportados por el proyecto. Deben coincidir exactamente
# con los "Realm roles" creados en Keycloak.
ROLES_DE_NEGOCIO = {'admin', 'cliente'}


class KeycloakOIDCAuthenticationBackend(OIDCAuthenticationBackend):

    def filter_users_by_claims(self, claims):
        email = claims.get('email')
        if not email:
            return self.UserModel.objects.none()
        return self.UserModel.objects.filter(email__iexact=email)

    def create_user(self, claims):
        user = super().create_user(claims)
        self.update_user_claims(user, claims)
        return user

    def update_user(self, user, claims):
        self.update_user_claims(user, claims)
        return user

    def update_user_claims(self, user, claims):
        """
        Actualiza nombre/apellido y sincroniza el/los rol(es) de Keycloak
        del usuario hacia sus Django Groups.

        Se ejecuta en cada login (no solo en el alta), por lo que un
        cambio de rol hecho por un administrador en Keycloak, o un
        cambio de permisos hecho sobre el Group en GE-7, se refleja la
        próxima vez que el usuario inicia sesión o recarga su sesión.
        """
        user.first_name = claims.get('given_name', '')
        user.last_name = claims.get('family_name', '')

        realm_access = claims.get('realm_access', {})
        roles_keycloak = set(realm_access.get('roles', []))
        roles_negocio = roles_keycloak & ROLES_DE_NEGOCIO

        # Acceso al panel /admin/ de Django solo para el rol admin.
        user.is_staff = 'admin' in roles_negocio
        user.is_superuser = False  # nunca superuser: los permisos deben pasar por Groups
        user.save()

        self._sincronizar_grupos(user, roles_negocio)

    def _sincronizar_grupos(self, user, roles_negocio):
        """
        Deja los Django Groups del usuario exactamente iguales a sus
        roles de negocio actuales en Keycloak (agrega los que faltan,
        saca los que ya no correspondan).
        """
        grupos_actuales = set(user.groups.values_list('name', flat=True))
        if grupos_actuales == roles_negocio:
            return

        for nombre_rol in roles_negocio - grupos_actuales:
            grupo, _ = Group.objects.get_or_create(name=nombre_rol)
            user.groups.add(grupo)

        for nombre_rol in grupos_actuales - roles_negocio:
            grupo = Group.objects.filter(name=nombre_rol).first()
            if grupo:
                user.groups.remove(grupo)