def cliente_activo_context(request):
    """Hace disponible el cliente_activo y la lista de clientes en todos los templates."""
    if request.user.is_authenticated and hasattr(request, 'cliente_activo'):
        return {
            'cliente_activo': request.cliente_activo,
            'mis_clientes': request.user.clientes.filter(is_active=True),
        }
    return {'cliente_activo': None, 'mis_clientes': []}