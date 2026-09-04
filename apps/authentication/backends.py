"""
Backend OIDC para Keycloak -> sincroniza roles a Groups de Django.

Características:
- verifica email_verified
- busca usuario por email; si no existe, busca por preferred_username
- extrae roles desde:
    - realm_access.roles
    - claim 'roles' (mapper opcional)
    - resource_access.<client>.roles (client roles)
- sincroniza solo los grupos definidos en ROLES_DE_NEGOCIO
- marca is_staff True sólo si 'admin' está presente (útil para /admin/)
- NO usa is_superuser (por seguridad)
"""

from django.contrib.auth.models import Group
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

# Si preferís centralizar roles, reemplaza esta definición por:
# from .constants import ROLES_DE_NEGOCIO
ROLES_DE_NEGOCIO = {'admin', 'cliente', 'analista_cambiario', 'cajero'}


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
        Actualiza datos básicos y sincroniza roles -> grupos.
        Soporta roles en realm_access, en claim 'roles' y en resource_access.
        """
        # Actualizar nombre/apellido sin sobreescribir si vienen vacíos
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

        # Consolidar roles y filtrar por los que manejamos
        roles_keycloak = set(roles_realm) | set(roles_custom) | set(client_roles)
        roles_negocio = roles_keycloak & ROLES_DE_NEGOCIO

        # is_staff para acceder al admin site (no sustituye permisos)
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

        # Sincronizar grupos (solo los roles definidos en ROLES_DE_NEGOCIO)
        self._sincronizar_grupos(user, roles_negocio)

    def _sincronizar_grupos(self, user, roles_negocio):
        """
        Sincroniza únicamente los grupos en ROLES_DE_NEGOCIO:
        - Añade grupos que faltan.
        - Quita del usuario solo los grupos gestionados y que quedaron obsoletos.
        De esta forma NO tocamos otros groups que el usuario pueda tener.
        """
        grupos_actuales = set(
            user.groups.filter(name__in=ROLES_DE_NEGOCIO).values_list('name', flat=True)
        )

        # Añadir grupos nuevos
        for nombre_rol in roles_negocio - grupos_actuales:
            grupo, _ = Group.objects.get_or_create(name=nombre_rol)
            user.groups.add(grupo)

        # Quitar grupos que ya no corresponden (solo dentro del conjunto que gestionamos)
        for nombre_rol in grupos_actuales - roles_negocio:
            grupo = Group.objects.filter(name=nombre_rol).first()
            if grupo:
                user.groups.remove(grupo)