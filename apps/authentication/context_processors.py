"""
Context processor que expone en todos los templates el estado de
autorización del usuario actual, para poder mostrar/ocultar secciones
de la interfaz (sidebar, accesos rápidos, etc.) según lo que el rol
de Keycloak del usuario realmente le permite ver.

No reemplaza la protección real de las vistas (@requiere_permiso /
UserPassesTestMixin) — es solo la capa de UI: nunca hay que confiar
únicamente en esto para decidir qué puede *hacer* un usuario, sólo
qué botones/enlaces tiene sentido mostrarle.
"""


def permisos_ui_context(request):
    if not request.user.is_authenticated:
        return {
            'keycloak_roles': [],
            'es_admin': False,
            'puede_ver_usuarios': False,
            'puede_ver_roles': False,
        }

    roles = request.session.get('keycloak_roles', [])
    es_admin = 'admin' in roles or request.user.is_staff or request.user.is_superuser
    puede_ver_divisas = es_admin or 'agente' in roles

    return {
        'keycloak_roles': roles,
        'es_admin': es_admin,
        'puede_ver_usuarios': es_admin or 'usuarios' in roles,
        'puede_ver_roles': es_admin or 'gestion_roles' in roles,
        'puede_ver_divisas': puede_ver_divisas,
        'puede_administrar_divisas': es_admin,
        'puede_gestionar_metodos_pago': es_admin or 'cliente' in roles,
    }
