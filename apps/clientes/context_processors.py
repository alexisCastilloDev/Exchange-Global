"""
Context processor que expone el cliente activo (elegido en
SeleccionarClienteActivoView) a todos los templates, para poder
mostrar por ejemplo "Operando en representación de: <cliente>" y un
link para cambiarlo.
"""
from .models import Cliente


def cliente_activo(request):
    cliente_activo_id = request.session.get('cliente_activo_id')
    if not cliente_activo_id:
        return {'cliente_activo': None}

    cliente = Cliente.objects.filter(pk=cliente_activo_id, is_active=True).first()
    return {'cliente_activo': cliente}
