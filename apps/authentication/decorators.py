"""
Decorador para proteger vistas según el permiso asociado a un recurso.
Consulta el sistema de permisos de Django en cada request, por lo que
un cambio de permisos aplica de inmediato, sin relogin.
"""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def requiere_permiso(codigo_recurso):
    permiso_completo = f'authentication.acceder_{codigo_recurso}'

    def decorador(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.has_perm(permiso_completo):
                messages.error(request, 'No tenés permiso para acceder a esta funcionalidad.')
                return redirect('home')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorador