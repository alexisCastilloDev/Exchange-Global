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


# Roles técnicos que Keycloak agrega a todo usuario/realm y que no se
# deben ofrecer para asignar manualmente (mismo criterio que en backends.py).
ROLES_TECNICOS_EXCLUIDOS = {
    'offline_access',
    'uma_authorization',
    'default-roles-global',
}


def obtener_roles_disponibles():
    """Todos los realm roles de negocio que se le pueden asignar a un usuario."""
    keycloak_admin = _obtener_keycloak_admin()
    roles = keycloak_admin.get_realm_roles()
    return sorted(
        r['name'] for r in roles if r['name'] not in ROLES_TECNICOS_EXCLUIDOS
    )


def obtener_roles_de_usuario(email):
    """Roles que el usuario ya tiene asignados en Keycloak, ahora mismo."""
    keycloak_admin = _obtener_keycloak_admin()
    user_id_keycloak = keycloak_admin.get_user_id(email)
    if not user_id_keycloak:
        raise ValueError(f"No se encontró el usuario {email} en Keycloak")

    roles = keycloak_admin.get_realm_roles_of_user(user_id_keycloak)
    return sorted(
        r['name'] for r in roles if r['name'] not in ROLES_TECNICOS_EXCLUIDOS
    )


def actualizar_roles_de_usuario(email, roles_deseados):
    """
    Deja al usuario con EXACTAMENTE los roles de `roles_deseados`:
    agrega los que le faltan y le quita los que ya no deberían estar.
    """
    keycloak_admin = _obtener_keycloak_admin()
    user_id_keycloak = keycloak_admin.get_user_id(email)
    if not user_id_keycloak:
        raise ValueError(f"No se encontró el usuario {email} en Keycloak")

    roles_actuales = set(obtener_roles_de_usuario(email))
    roles_deseados = set(roles_deseados)

    roles_a_agregar = roles_deseados - roles_actuales
    roles_a_quitar = roles_actuales - roles_deseados

    if roles_a_agregar:
        reps = [keycloak_admin.get_realm_role(nombre) for nombre in roles_a_agregar]
        keycloak_admin.assign_realm_roles(user_id=user_id_keycloak, roles=reps)

    if roles_a_quitar:
        reps = [keycloak_admin.get_realm_role(nombre) for nombre in roles_a_quitar]
        keycloak_admin.delete_realm_roles_of_user(user_id=user_id_keycloak, roles=reps)