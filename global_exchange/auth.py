from mozilla_django_oidc.auth import OIDCAuthenticationBackend

class CustomOIDCBackend(OIDCAuthenticationBackend):
    """
    Backend de autenticación OIDC personalizado para sincronizar
    los roles de Keycloak con los permisos de usuario en Django.
    """

    def _update_user_permissions(self, user, claims):
        """
        Asigna permisos de staff y superuser basándose EXCLUSIVAMENTE
        en los roles asignados en Keycloak.
        """
        # Imprime en consola los datos exactos que Keycloak nos envía
        print("\n=== CLAIMS RECIBIDOS DE KEYCLOAK ===")
        print(claims)
        print("====================================\n")

        # 1. Obtener roles de Realm (Estructura estándar de Keycloak: realm_access.roles)
        realm_access = claims.get('realm_access', {})
        realm_roles = realm_access.get('roles', []) if isinstance(realm_access, dict) else []

        # 2. Obtener roles mapeados al nivel superior (si se configuró un Mapper hacia 'roles')
        top_level_roles = claims.get('roles', []) if isinstance(claims.get('roles'), list) else []

        # 3. Obtener roles de Clientes (resource_access.<cliente>.roles)
        client_roles = []
        resource_access = claims.get('resource_access', {})
        if isinstance(resource_access, dict):
            for client_data in resource_access.values():
                if isinstance(client_data, dict):
                    client_roles.extend(client_data.get('roles', []))

        # Consolidar todos los roles únicos recibidos de Keycloak
        todos_los_roles = set(realm_roles + top_level_roles + client_roles)

        # Evaluar EXCLUSIVAMENTE si el rol 'admin' está presente
        es_admin = 'admin' in todos_los_roles

        user.is_staff = es_admin
        user.is_superuser = es_admin
        user.save()

    def update_user(self, user, claims):
        """Actualiza los permisos del usuario en cada inicio de sesión."""
        user = super().update_user(user, claims)
        self._update_user_permissions(user, claims)
        return user

    def create_user(self, claims):
        """Crea el usuario en Django y asigna sus permisos iniciales tras autenticarse."""
        user = super().create_user(claims)
        self._update_user_permissions(user, claims)
        return user