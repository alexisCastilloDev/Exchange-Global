from mozilla_django_oidc.auth import OIDCAuthenticationBackend

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
        user.first_name = claims.get('given_name', '')
        user.last_name = claims.get('family_name', '')
        # Extraer roles del realm de Keycloak (si vienen en las claims)
        realm_access = claims.get('realm_access', {})
        roles = realm_access.get('roles', [])
        
        # Guardar roles en un atributo o sincronizar superusuario/staff si corresponde
        if 'admin' in roles:
            user.is_staff = True
            user.is_superuser = True
        else:
            user.is_staff = False
            user.is_superuser = False
            
        user.save()