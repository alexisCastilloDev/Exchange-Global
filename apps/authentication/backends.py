"""
Backend de autenticación que conecta Django con Keycloak vía OIDC.

Además de autenticar, sincroniza los roles de negocio que vienen en el
token de Keycloak (claim `realm_access.roles` o el claim personalizado `roles`) 
hacia Django Groups, para que el sistema de permisos nativo de Django 
(`user.has_perm(...)`) pueda usarse como mecanismo de autorización granular por rol.

Deliberadamente NO se usa `is_superuser`: ese flag hace que Django
ignore cualquier chequeo de permisos, lo cual anularía por completo la
gestión de permisos por rol.
Sincroniza roles de Keycloak hacia Django Groups para autorización
granular (GE-7). No usa is_superuser para no bypasear permisos.
"""
from django.contrib.auth.models import Group
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

ROLES_DE_NEGOCIO = {'admin', 'cliente', 'analista_cambiario', 'cajero'}


class KeycloakOIDCAuthenticationBackend(OIDCAuthenticationBackend):

    def verify_claims(self, claims):
        claims_verified = super().verify_claims(claims)
        email_verified = claims.get('email_verified', False)
        return claims_verified and email_verified

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
        """
        
        user.first_name = claims.get('given_name', '')
        user.last_name = claims.get('family_name', '')
        
        # 1. Extraer roles (Soporte para realm_access y el mapper personalizado 'roles')
        realm_access = claims.get('realm_access', {})
        roles_realm = realm_access.get('roles', [])
        
        # Leemos los roles del mapper personalizado 'roles'
        roles_custom = claims.get('roles', [])
        # Si Keycloak manda un solo rol como texto simple (String), lo convertimos a lista
        if isinstance(roles_custom, str):
            roles_custom = [roles_custom]

        # Unimos ambas listas de roles por seguridad y filtramos los permitidos
        roles_keycloak = set(roles_realm) | set(roles_custom)
        roles_negocio = roles_keycloak & ROLES_DE_NEGOCIO

        # Acceso al panel /admin/ de Django y vistas de staff solo para el rol admin.
        user.is_staff = 'admin' in roles_negocio
        user.is_superuser = False
        user.save()

        self._sincronizar_grupos(user, roles_negocio)

    def _sincronizar_grupos(self, user, roles_negocio):
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