from keycloak import KeycloakAdmin
from django.conf import settings

def _obtener_keycloak_admin():
    return KeycloakAdmin(
        server_url=settings.KEYCLOAK_SERVER_URL,
        realm_name=settings.KEYCLOAK_REALM,
        client_id=settings.KEYCLOAK_CLIENT_ID,
        client_secret_key=settings.KEYCLOAK_CLIENT_SECRET,
        verify=True
    )

def actualizar_usuario_en_keycloak(email, first_name, last_name, is_active):
    keycloak_admin = _obtener_keycloak_admin()
    user_id_keycloak = keycloak_admin.get_user_id(email)
    
    if not user_id_keycloak:
        raise ValueError(f"No se encontró el usuario {email} en Keycloak")

    keycloak_admin.update_user(
        user_id=user_id_keycloak,
        payload={
            "firstName": first_name,
            "lastName": last_name,
            "enabled": is_active
        }
    )