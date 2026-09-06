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
                # Rutas permitidas sin tener cliente seleccionado en la sesión
                rutas_permitidas = []

                for url_name in ['seleccionar_cliente', 'logout', 'oidc_logout', 'user_logout']:
                    try:
                        rutas_permitidas.append(reverse(url_name))
                    except NoReverseMatch:
                        pass

                # Permitir el acceso si la URL consultada es la vista de cambio o selección
                es_ruta_exenta = (
                    request.path in rutas_permitidas or
                    request.resolver_match and request.resolver_match.url_name == 'cambiar_cliente'
                )

                if not es_ruta_exenta:
                    return redirect('seleccionar_cliente')

            # Cargar el objeto cliente_activo en la request
            if cliente_id:
                request.cliente_activo = Cliente.objects.filter(
                    pk=cliente_id, is_active=True
                ).first()
            else:
                request.cliente_activo = clientes_asociados.first()

        return self.get_response(request)