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
    """Expone en las plantillas los permisos visibles del usuario actual."""
    if not request.user.is_authenticated:
        return {
            'keycloak_roles': [],
            'es_admin': False,
            'puede_ver_usuarios': False,
            'puede_ver_roles': False,
            'puede_ver_historial_propio': False,
            'puede_ver_caja': False,
            'puede_solicitar_cliente': False,
        }

    roles = request.session.get('keycloak_roles', [])
    es_admin = 'admin' in roles or request.user.is_staff or request.user.is_superuser
    tiene_clientes_asociados = request.user.is_authenticated and request.user.clientes.filter(is_active=True).exists()
    # Puede autogestionar su alta (ver apps.clientes.views.SolicitarClienteView)
    # cualquiera cuyos roles de Keycloak sean, como mucho, 'cliente' (sin
    # ningún otro rol de negocio) y que todavía no tenga un Cliente
    # asociado: cubre tanto al usuario recién registrado sin ningún rol
    # todavía, como a quien ya tiene el rol 'cliente' pero nadie le creó
    # el Cliente. Alguien con OTRO rol de negocio (analista_cambiario,
    # cajero, etc.) es personal, no un cliente en potencia, y nunca
    # debería terminar en esta pantalla aunque tampoco tenga cliente.
    puede_solicitar_cliente = (
        not (set(roles) - {'cliente'}) and not es_admin and not tiene_clientes_asociados
    )
    # Solo administración gestiona el catálogo de divisas. Analistas y
    # clientes tienen accesos separados sobre las tasas.
    puede_ver_divisas = es_admin
    puede_actualizar_tasas = es_admin or 'analista_cambiario' in roles
    puede_ver_tasas = puede_actualizar_tasas or 'cliente' in roles
    puede_operar_divisas = (
        'cliente' in roles
        and tiene_clientes_asociados
        and not es_admin
    )
    puede_configurar_comisiones = es_admin or 'analista_cambiario' in roles
    puede_ver_caja = 'cajero' in roles

    return {
        'keycloak_roles': roles,
        'es_admin': es_admin,
        'puede_ver_usuarios': es_admin or 'usuarios' in roles,
        'puede_ver_roles': es_admin or 'gestion_roles' in roles,
        'puede_ver_divisas': puede_ver_divisas,
        'puede_administrar_divisas': es_admin,
        'puede_gestionar_metodos_pago': 'cliente' in roles and tiene_clientes_asociados,
        'puede_operar_divisas': puede_operar_divisas,
        'puede_ver_historial_propio': puede_operar_divisas,
        'puede_actualizar_tasas': puede_actualizar_tasas,
        'puede_ver_tasas': puede_ver_tasas,
        'puede_configurar_comisiones': puede_configurar_comisiones,
        'puede_ver_caja': puede_ver_caja,
        'puede_solicitar_cliente': puede_solicitar_cliente,
    }
