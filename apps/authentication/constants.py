# Mapa que define qué recursos (RecursoProtegido.codigo) debe tener permiso cada rol.
# Cuando agregues un nuevo rol, añade su entrada aquí y asegúrate de que los recursos
# mencionados existan o serán creados por el comando.
ROLE_PERMISSION_MAP = {
    'admin': [
        'panel_admin',
        'gestion_roles',
        'usuarios',
        'clientes',
        # añade más recursos que admin deba ver
    ],
    'cliente': [
        'clientes',
        # recursos de cliente
    ],
    'analista_cambiario': [
        'clientes',
        'reportes_cambiarios',
    ],
    'cajero': [
        'cajas',
        'clientes',
    ],
}

# Mantener ROLES_DE_NEGOCIO centralizados para que el backend los lea de aquí
ROLES_DE_NEGOCIO = set(ROLE_PERMISSION_MAP.keys())