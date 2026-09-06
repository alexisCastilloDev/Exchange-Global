"""
Backend OIDC para Keycloak -> autenticación Y autorización 100% en Keycloak.

Los roles del usuario se guardan tal cual llegan del token en
`request.session['keycloak_roles']`, sin persistir nada en las tablas
auth.Group / auth.Permission de Django. La sesión se refresca en cada
login, que es el único momento en que Django "aprende" el estado
actual de roles en Keycloak.

Características:
- verifica email_verified
- busca usuario por email; si no existe, busca por preferred_username
- extrae roles desde:
    - realm_access.roles
    - claim 'roles' (mapper opcional)
    - resource_access.<client>.roles (client roles)
- marca is_staff True sólo si 'admin' está presente (útil para /admin/)
- NO usa is_superuser (por seguridad)
"""

from mozilla_django_oidc.auth import OIDCAuthenticationBackend

# Roles técnicos que Keycloak agrega solo a todo usuario y que NO
# representan un permiso de negocio real.
ROLES_TECNICOS_EXCLUIDOS = {
    'offline_access',
    'uma_authorization',
    'default-roles-global',  # ajustar si el realm no se llama "global"
}


class KeycloakOIDCAuthenticationBackend(OIDCAuthenticationBackend):
    def verify_claims(self, claims):
        """
        Verifica claims basales y que el email esté verificado.
        """
        claims_verified = super().verify_claims(claims)
        email_verified = claims.get('email_verified', False)
        return claims_verified and bool(email_verified)

    def filter_users_by_claims(self, claims):
        """
        Localiza usuarios existentes:
         - primero por email (insensible a mayúsculas),
         - fallback a preferred_username si no hay email.
        """
        email = claims.get('email')
        if email:
            return self.UserModel.objects.filter(email__iexact=email)

        preferred = claims.get('preferred_username')
        if preferred:
            return self.UserModel.objects.filter(username__iexact=preferred)

        return self.UserModel.objects.none()

    def create_user(self, claims):
        user = super().create_user(claims)
        self.update_user_claims(user, claims)
        return user

    def update_user(self, user, claims):
        self.update_user_claims(user, claims)
        return user

    def update_user_claims(self, user, claims):
        """
        Actualiza datos básicos y guarda los roles en la sesión.
        Soporta roles en realm_access, en claim 'roles' y en resource_access.
        """
        given = claims.get('given_name')
        family = claims.get('family_name')
        changed = False
        if given and user.first_name != given:
            user.first_name = given
            changed = True
        if family and user.last_name != family:
            user.last_name = family
            changed = True

        # 1) roles en realm_access
        realm_access = claims.get('realm_access', {}) or {}
        roles_realm = realm_access.get('roles', []) or []

        # 2) roles en claim 'roles' (mapper personalizado)
        roles_custom = claims.get('roles', []) or []
        if isinstance(roles_custom, str):
            roles_custom = [roles_custom]

        # 3) roles en resource_access (client roles)
        resource_access = claims.get('resource_access', {}) or {}
        client_roles = set()
        if isinstance(resource_access, dict):
            for client_info in resource_access.values():
                if isinstance(client_info, dict):
                    client_roles.update(client_info.get('roles', []) or [])

        # Consolidar y excluir roles técnicos de Keycloak
        roles_keycloak = set(roles_realm) | set(roles_custom) | set(client_roles)
        roles_negocio = roles_keycloak - ROLES_TECNICOS_EXCLUIDOS

        # is_staff para acceder al admin site (no sustituye autorización)
        is_staff_value = ('admin' in roles_negocio)
        if user.is_staff != is_staff_value:
            user.is_staff = is_staff_value
            changed = True

        # Nunca permitir is_superuser por token
        if user.is_superuser:
            user.is_superuser = False
            changed = True

        if changed:
            user.save(update_fields=['first_name', 'last_name', 'is_staff', 'is_superuser'])

        # Única fuente de autorización: la sesión, no auth.Group.
        self.request.session['keycloak_roles'] = sorted(roles_negocio)