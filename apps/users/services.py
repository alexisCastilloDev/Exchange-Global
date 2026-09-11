from django.conf import settings
from django.contrib.auth import get_user_model
from apps.authentication.backends import es_rol_tecnico

try:
    from keycloak import KeycloakAdmin
except ImportError:  # pragma: no cover
    KeycloakAdmin = None


def _obtener_keycloak_admin():
    if KeycloakAdmin is None:
        raise RuntimeError(
            'La integración de Keycloak no está disponible. Verifica la dependencia python-keycloak y la configuración del realm.'
        )
    return KeycloakAdmin(
        server_url=settings.KEYCLOAK_SERVER_URL,
        realm_name=settings.KEYCLOAK_REALM,
        client_id=settings.KEYCLOAK_CLIENT_ID,
        client_secret_key=settings.KEYCLOAK_CLIENT_SECRET,
        verify=True
    )


def sincronizar_usuarios_desde_keycloak():
    """Refleja en Django los usuarios actuales del realm de Keycloak.

    Los usuarios ausentes o deshabilitados se marcan como inactivos para no
    perder relaciones históricas. Devuelve la cantidad sincronizada.
    """
    user_model = get_user_model()
    keycloak_admin = _obtener_keycloak_admin()
    usuarios_keycloak = keycloak_admin.get_users({})
    identificadores = set()
    roles_por_usuario = {}

    for datos in usuarios_keycloak:
        username = (datos.get('username') or '').strip()
        email = (datos.get('email') or '').strip()
        if not username:
            continue

        usuario = user_model.objects.filter(username__iexact=username).first()
        if usuario is None and email:
            usuario = user_model.objects.filter(email__iexact=email).first()
        if usuario is None:
            usuario = user_model(username=username)
            usuario.set_unusable_password()

        usuario.username = username
        usuario.email = email
        usuario.first_name = datos.get('firstName') or ''
        usuario.last_name = datos.get('lastName') or ''
        usuario.is_active = bool(datos.get('enabled', True))
        usuario.save()
        identificadores.add(usuario.pk)
        try:
            roles_por_usuario[usuario.pk] = sorted(
                rol['name']
                for rol in keycloak_admin.get_realm_roles_of_user(datos['id'])
                if not es_rol_tecnico(rol['name'])
            )
        except (KeyError, TypeError):
            roles_por_usuario[usuario.pk] = []

    user_model.objects.exclude(pk__in=identificadores).update(is_active=False)
    return roles_por_usuario


def _obtener_user_id_por_email(keycloak_admin, email):
    """Busca al usuario por email de forma exacta en Keycloak."""
    # Buscar usuarios que coincidan exactamente con el email
    users = keycloak_admin.get_users({"email": email, "exact": True})
    
    if not users:
        # Intento secundario: buscar por username en caso de que coincida con el correo
        users = keycloak_admin.get_users({"username": email, "exact": True})

    if not users:
        raise ValueError(f"No se encontró el usuario {email} en Keycloak")

    return users[0]['id']


def actualizar_usuario_en_keycloak(email, first_name, last_name, is_active):
    keycloak_admin = _obtener_keycloak_admin()
    user_id_keycloak = _obtener_user_id_por_email(keycloak_admin, email)

    keycloak_admin.update_user(
        user_id=user_id_keycloak,
        payload={
            "firstName": first_name,
            "lastName": last_name,
            "enabled": is_active
        }
    )


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
        r['name'] for r in roles if not es_rol_tecnico(r['name'])
    )


def obtener_roles_de_usuario(email):
    """Roles que el usuario ya tiene asignados en Keycloak, ahora mismo."""
    keycloak_admin = _obtener_keycloak_admin()
    user_id_keycloak = _obtener_user_id_por_email(keycloak_admin, email)

    roles = keycloak_admin.get_realm_roles_of_user(user_id_keycloak)
    return sorted(
        r['name'] for r in roles if not es_rol_tecnico(r['name'])
    )


def actualizar_roles_de_usuario(email, roles_deseados):
    """
    Deja al usuario con EXACTAMENTE los roles de `roles_deseados`:
    agrega los que le faltan y le quita los que ya no deberían estar.
    """
    keycloak_admin = _obtener_keycloak_admin()
    user_id_keycloak = _obtener_user_id_por_email(keycloak_admin, email)

    # Obtenemos directamente los roles actuales con el user_id ya validado
    roles_actuales_obj = keycloak_admin.get_realm_roles_of_user(user_id_keycloak)
    roles_actuales = set(
        r['name'] for r in roles_actuales_obj if r['name'] not in ROLES_TECNICOS_EXCLUIDOS
    )
    
    roles_deseados = set(roles_deseados)

    roles_a_agregar = roles_deseados - roles_actuales
    roles_a_quitar = roles_actuales - roles_deseados

    if roles_a_agregar:
        reps = [keycloak_admin.get_realm_role(nombre) for nombre in roles_a_agregar]
        keycloak_admin.assign_realm_roles(user_id=user_id_keycloak, roles=reps)

    if roles_a_quitar:
        reps = [keycloak_admin.get_realm_role(nombre) for nombre in roles_a_quitar]
        keycloak_admin.delete_realm_roles_of_user(user_id=user_id_keycloak, roles=reps)