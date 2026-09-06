from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse
from apps.clientes.models import Cliente


class ClienteActivoMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.user.is_staff:
            cliente_id = request.session.get('cliente_activo_id')
            clientes_asociados = request.user.clientes.filter(is_active=True)

            # Caso 1: El usuario está asociado a un ÚNICO cliente
            if clientes_asociados.count() == 1:
                request.session['cliente_activo_id'] = (
                    clientes_asociados.first().pk
                )

            # Caso 2: El usuario tiene MÚLTIPLES clientes y aún no ha seleccionado uno
            elif clientes_asociados.count() > 1 and not cliente_id:
                try:
                    path_seleccion = reverse('seleccionar_cliente')
                except NoReverseMatch:
                    path_seleccion = None

                # Intentar resolver las posibles rutas de logout según el sistema de auth
                path_logout = None
                for logout_name in ['logout', 'oidc_logout', 'user_logout']:
                    try:
                        path_logout = reverse(logout_name)
                        break
                    except NoReverseMatch:
                        continue

                # Evitar bucle infinito de redirección
                if path_seleccion and request.path not in [
                    path_seleccion,
                    path_logout,
                ]:
                    return redirect('seleccionar_cliente')

            # Cargar el objeto cliente_activo en la request
            if cliente_id:
                request.cliente_activo = Cliente.objects.filter(
                    pk=cliente_id, is_active=True
                ).first()
            else:
                request.cliente_activo = clientes_asociados.first()

        return self.get_response(request)