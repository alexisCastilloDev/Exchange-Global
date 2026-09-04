"""
Configuración de rutas de URL para la aplicación de Clientes.
"""

from django.urls import path

from .views import (
    PanelAdminView,
    ClienteCreateView,
    ClienteUpdateView,
    ClienteSoftDeleteView,
    ClienteDetailView,
    ClienteAsociarUsuarioView,
    ClienteDesasociarUsuarioView,
    SeleccionarClienteActivoView,
)

urlpatterns = [
    path('panel/', PanelAdminView.as_view(), name='panel_admin'),
    path('nuevo/', ClienteCreateView.as_view(), name='cliente_create'),
    path('<int:pk>/editar/', ClienteUpdateView.as_view(), name='cliente_update'),
    path('cliente/<int:pk>/eliminar/', ClienteSoftDeleteView.as_view(), name='cliente_delete'),

    # Ficha de cliente + gestión de usuarios asociados (por email)
    path('<int:pk>/', ClienteDetailView.as_view(), name='cliente_detail'),
    path('<int:pk>/usuarios/asociar/', ClienteAsociarUsuarioView.as_view(), name='cliente_asociar_usuario'),
    path('<int:pk>/usuarios/<int:user_id>/desasociar/', ClienteDesasociarUsuarioView.as_view(), name='cliente_desasociar_usuario'),

    # Selección / cambio de cliente activo (usuario cliente, no admin)
    path('seleccionar/', SeleccionarClienteActivoView.as_view(), name='seleccionar_cliente_activo'),
    path('cambiar/', SeleccionarClienteActivoView.as_view(), name='cambiar_cliente_activo'),
]
