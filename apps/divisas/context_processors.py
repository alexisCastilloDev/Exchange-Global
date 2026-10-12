"""
Context processor que expone en todos los templates el indicador de
notificaciones de cambio de tasas (HU GE-51), para que el usuario
cliente vea en la barra superior cuántas notificaciones tiene sin leer
mientras navega por cualquier pantalla del sistema.
"""

from apps.divisas.models import NotificacionTasa


def notificaciones_context(request):
    """Expone si el usuario ve notificaciones y cuántas tiene sin leer.

    Las notificaciones de tasas están dirigidas a usuarios clientes, así
    que el indicador solo se habilita para quienes tienen el rol
    ``cliente`` en su sesión de Keycloak (el mismo criterio que protege
    ``MisNotificacionesView``). La cantidad sale de una única consulta de
    conteo sobre el índice ``(usuario, leida)``.

    Args:
        request (HttpRequest): La request actual.

    Returns:
        dict: ``puede_ver_notificaciones`` (bool) y
        ``notificaciones_no_leidas`` (int).
    """
    if not request.user.is_authenticated:
        return {'puede_ver_notificaciones': False, 'notificaciones_no_leidas': 0}

    roles = request.session.get('keycloak_roles', [])
    if 'cliente' not in roles:
        return {'puede_ver_notificaciones': False, 'notificaciones_no_leidas': 0}

    no_leidas = NotificacionTasa.objects.filter(usuario=request.user, leida=False).count()
    return {'puede_ver_notificaciones': True, 'notificaciones_no_leidas': no_leidas}
