from keycloak import KeycloakAdmin
from django.conf import settings


def _obtener_keycloak_admin():
    """
    Crea una instancia de KeycloakAdmin usando client credentials.
    Ajustá los argumentos si tu instalación de python-keycloak necesita
    username/password en vez de client_secret_key.
    """
    return KeycloakAdmin(
        server_url=settings.KEYCLOAK_SERVER_URL,
        realm_name=settings.KEYCLOAK_REALM,
        client_id=settings.KEYCLOAK_CLIENT_ID,
        client_secret_key=settings.KEYCLOAK_CLIENT_SECRET,
        verify=True
    )


def _buscar_user_id_por_email(keycloak_admin, email):
    """
    Busca el id de usuario en Keycloak por email. Algunas instalaciones
    no exponen get_user_id por email, así que intentamos varios métodos.
    Devuelve user_id o None.
    """
    # Intento directo (si la librería soporta get_user_id con username/email)
    try:
        user_id = keycloak_admin.get_user_id(email)
        if user_id:
            return user_id
    except Exception:
        pass

    # Intento búsqueda por query (email)
    try:
        users = keycloak_admin.get_users({"email": email})
        if users:
            # get_users devuelve lista de dicts con 'id'
            return users[0].get('id')
    except Exception:
        pass

    # Intento buscar por username igual al email
    try:
        users = keycloak_admin.get_users({"username": email})
        if users:
            return users[0].get('id')
    except Exception:
        pass

    return None


def actualizar_usuario_en_keycloak(email, first_name, last_name, is_active):
    """
    Actualiza el usuario en Keycloak. Lanza ValueError si no se puede
    encontrar el usuario o si falla la actualización.
    """
    if not email:
        raise ValueError("El usuario no tiene email; no se puede sincronizar con Keycloak.")

    keycloak_admin = _obtener_keycloak_admin()

    # Buscar user id de Keycloak
    user_id_keycloak = _buscar_user_id_por_email(keycloak_admin, email)
    if not user_id_keycloak:
        raise ValueError(f"No se encontró el usuario con email '{email}' en Keycloak")

    payload = {
        "firstName": first_name or "",
        "lastName": last_name or "",
        "enabled": bool(is_active),
    }

    try:
        keycloak_admin.update_user(user_id=user_id_keycloak, payload=payload)
    except Exception as exc:
        # En caso de error de la librería Keycloak, encapsulamos la excepción
        raise RuntimeError(f"Error al actualizar usuario en Keycloak: {exc}")