"""
Decorador para proteger vistas según el rol de Keycloak requerido.

La autorización es 100% de Keycloak: no se consulta auth.Group ni
auth.Permission. El rol efectivo del usuario está en
`request.session['keycloak_roles']`, cargado ahí por
KeycloakOIDCAuthenticationBackend en cada login.

Como el chequeo es contra la sesión (no contra la base de datos), un
cambio de rol en Keycloak recién se refleja cuando el usuario vuelve a
loguearse — no hay forma de "empujar" el cambio a una sesión activa,
ya que Django no tiene ninguna copia propia del rol para actualizar.
"""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def requiere_permiso(codigo_recurso):
    """Restringe una vista a usuarios cuyo rol coincide con el recurso."""
    def decorador(view_func):
        """Aplica autenticación y autorización a la vista recibida."""
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            """Comprueba el recurso solicitado antes de ejecutar la vista."""
            roles = request.session.get('keycloak_roles', [])
            if codigo_recurso not in roles and 'admin' not in roles:
                messages.error(request, 'No tenés permiso para acceder a esta funcionalidad.')
                return redirect('home')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorador


def requiere_rol(rol_requerido):
    """Protege una vista por rol, permitiendo también el rol global ``admin``."""
    def decorador(view_func):
        """Aplica el control de acceso a la vista decorada."""
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            """Comprueba la presencia del rol requerido en la sesión."""
            roles = request.session.get('keycloak_roles', [])
            if rol_requerido not in roles and 'admin' not in roles:
                messages.error(request, 'No tenés el rol necesario para acceder a esta funcionalidad.')
                return redirect('home')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorador