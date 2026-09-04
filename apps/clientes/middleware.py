"""
Middleware para la Historia de Usuario: selección de cliente activo.

Cuando un usuario "cliente" (asociado a uno o más Cliente) inicia sesión,
el sistema debe:
- Pedirle que elija en nombre de qué cliente va a operar, si está
  asociado a más de uno.
- Seleccionarlo automáticamente si está asociado a uno solo.
- Mantener el cliente activo en la sesión mientras navega, hasta que
  decida cambiarlo (sin necesidad de cerrar sesión).
"""
from django.shortcuts import redirect
from django.urls import reverse

# Rutas que no deben disparar la redirección a "seleccionar cliente",
# para no generar un bucle de redirecciones.
RUTAS_EXENTAS = (
    '/clientes/seleccionar/',
    '/clientes/cambiar/',
    '/oidc/',
    '/admin/',
    '/static/',
)


class ClienteActivoMiddleware:
    """
    Si el usuario logueado está asociado a más de un Cliente y todavía
    no eligió uno en la sesión actual, lo redirige a la pantalla de
    selección. Si está asociado a uno solo, lo autoselecciona.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)

        if user and user.is_authenticated and not (user.is_staff or user.is_superuser):
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
