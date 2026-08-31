"""
Configuración de rutas de URL para la aplicación de Clientes.
"""

from django.urls import path

from .views import PanelAdminView, ClienteCreateView, ClienteUpdateView, ClienteSoftDeleteView

urlpatterns = [
    path('panel/', PanelAdminView.as_view(), name='panel_admin'),
    path('nuevo/', ClienteCreateView.as_view(), name='cliente_create'),
    path('<int:pk>/editar/', ClienteUpdateView.as_view(), name='cliente_update'),
    path('cliente/<int:pk>/eliminar/', ClienteSoftDeleteView.as_view(), name='cliente_delete'),
]