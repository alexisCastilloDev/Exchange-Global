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
            cliente_activo = None

            # Caso 1: El usuario está asociado a un ÚNICO cliente
            if clientes_asociados.count() == 1:
                cliente_activo = clientes_asociados.first()
                request.session['cliente_activo_id'] = cliente_activo.pk

            # Caso 2: El usuario tiene MÚLTIPLES clientes y aún no ha seleccionado uno
            elif clientes_asociados.count() > 1:
                if cliente_id:
                    cliente_activo = clientes_asociados.filter(
                        pk=cliente_id
                    ).first()

                # La gestión de métodos de pago es una pantalla personal del cliente
                # y no depende de haber elegido un cliente activo concreto. Al tener
                # varios clientes asociados, se toma el más reciente como contexto
                # operativo del usuario para evitar que el acceso quede bloqueado.
                if request.path in ['/clientes/metodos-pago/', '/clientes/metodos-pago/nuevo/', '/clientes/metodos-pago/<int:pk>/editar/', '/clientes/metodos-pago/<int:pk>/eliminar/']:
                    cliente_activo = clientes_asociados.order_by('-pk').first()
                    request.session['cliente_activo_id'] = cliente_activo.pk

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
                if (
                    cliente_activo is None
                    and path_seleccion
                    and request.path not in [path_seleccion, path_logout]
                ):
                    return redirect('seleccionar_cliente')

            # Cargar el objeto cliente_activo en la request
            request.cliente_activo = cliente_activo

        return self.get_response(request)