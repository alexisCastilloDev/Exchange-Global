"""
Middleware para la selección de cliente activo.

Excluye del flujo a los usuarios con permiso administrativo (acceder_panel_admin),
en lugar de basarse en is_staff/is_superuser.
"""
from django.shortcuts import redirect
from django.urls import reverse

# Rutas exentas para no generar bucles
RUTAS_EXENTAS = (
    '/clientes/seleccionar/',
    '/clientes/cambiar/',
    '/oidc/',
    '/admin/',
    '/static/',
)


class ClienteActivoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)

        # Si el usuario está autenticado y NO tiene el permiso del panel admin,
        # aplicamos la lógica de selección automática / redirección para elegir cliente.
        if user and user.is_authenticated and not user.has_perm('authentication.acceder_panel_admin'):
            # No ejecutar en rutas exentas
            if not any(request.path.startswith(ruta) for ruta in RUTAS_EXENTAS):
                clientes = user.clientes_asociados.filter(is_active=True)
                cantidad = clientes.count()

                cliente_activo_id = request.session.get('cliente_activo_id')
                cliente_activo_valido = (
                    cliente_activo_id is not None
                    and clientes.filter(pk=cliente_activo_id).exists()
                )

                if cantidad == 1 and not cliente_activo_valido:
                    request.session['cliente_activo_id'] = clientes.first().pk
                elif cantidad > 1 and not cliente_activo_valido:
                    return redirect(reverse('seleccionar_cliente_activo'))

        return self.get_response(request)