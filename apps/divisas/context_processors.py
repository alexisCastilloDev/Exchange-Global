"""
Context processor que expone en todos los templates el indicador de
notificaciones no leídas, para que el usuario cliente vea en la barra
superior cuántas tiene mientras navega por cualquier pantalla del sistema.

Suma dos orígenes: las notificaciones de cambio de tasas (HU GE-51,
``NotificacionTasa``) y las de transacciones y facturas del cliente activo
(HU "Notificaciones sobre transacciones y facturas", ``NotificacionCliente``).
"""

from apps.divisas.models import NotificacionCliente, NotificacionTasa


def notificaciones_cliente_activo(request):
    """Notificaciones de transacciones y facturas del usuario para su cliente activo.

    Filtra siempre por el usuario **y** por el cliente activo, así que una
    notificación de otro cliente, aunque sea del mismo usuario, nunca
    aparece ni se cuenta (criterio 5). Sin cliente activo (por ejemplo, un
    usuario que todavía no eligió uno), no devuelve ninguna.

    Args:
        request (HttpRequest): La request actual, con ``cliente_activo`` ya
            resuelto por ``apps.clientes.middleware.ClienteActivoMiddleware``.

    Returns:
        QuerySet: Las notificaciones de ``NotificacionCliente`` que le
        corresponden al usuario en este momento.
    """
    cliente_activo = getattr(request, 'cliente_activo', None)
    if cliente_activo is None:
        return NotificacionCliente.objects.none()
    return NotificacionCliente.objects.filter(usuario=request.user, cliente=cliente_activo)


def notificaciones_context(request):
    """Expone si el usuario ve notificaciones y cuántas tiene sin leer.

    Las notificaciones están dirigidas a usuarios clientes, así que el
    indicador solo se habilita para quienes tienen el rol ``cliente`` en su
    sesión de Keycloak (el mismo criterio que protege
    ``MisNotificacionesView``). El total suma las de tasas sin leer y las
    de transacciones y facturas sin leer del cliente activo (criterio 4),
    con una consulta de conteo para cada una sobre sus índices.

    Args:
        request (HttpRequest): La request actual.

    Returns:
        dict: ``puede_ver_notificaciones`` (bool), ``notificaciones_no_leidas``
        (int, el total), ``notificaciones_tasa_no_leidas`` (int) y
        ``notificaciones_operaciones_no_leidas`` (int).
    """
    sin_notificaciones = {
        'puede_ver_notificaciones': False,
        'notificaciones_no_leidas': 0,
        'notificaciones_tasa_no_leidas': 0,
        'notificaciones_operaciones_no_leidas': 0,
    }
    if not request.user.is_authenticated:
        return sin_notificaciones

    roles = request.session.get('keycloak_roles', [])
    if 'cliente' not in roles:
        return sin_notificaciones

    tasas = NotificacionTasa.objects.filter(usuario=request.user, leida=False).count()
    operaciones = notificaciones_cliente_activo(request).filter(leida=False).count()
    return {
        'puede_ver_notificaciones': True,
        'notificaciones_no_leidas': tasas + operaciones,
        'notificaciones_tasa_no_leidas': tasas,
        'notificaciones_operaciones_no_leidas': operaciones,
    }
