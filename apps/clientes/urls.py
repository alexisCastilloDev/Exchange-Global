from django import views
from django.urls import path
from .views import (
    ClienteCreateView, 
    ClienteDetailView,
    ClienteUpdateView, 
    ClienteSoftDeleteView, 
    ClienteHistorialBajasView,
    AsociarUsuariosClienteView
)
from apps.clientes import views

urlpatterns = [
    path('nuevo/', ClienteCreateView.as_view(), name='cliente_create'),
    path('<int:pk>/', ClienteDetailView.as_view(), name='cliente_detail'),
    path('<int:pk>/editar/', ClienteUpdateView.as_view(), name='cliente_update'),
    path('<int:pk>/asociar-usuarios/', AsociarUsuariosClienteView.as_view(), name='cliente_asociar_usuarios'),
    path('<int:pk>/eliminar/', ClienteSoftDeleteView.as_view(), name='cliente_delete'),
    path('historial-bajas/', ClienteHistorialBajasView.as_view(), name='cliente_historial_bajas'),

    path(
        'seleccionar/',
        views.seleccionar_cliente_view,
        name='seleccionar_cliente',
    ),
    path(
        'cambiar/<int:cliente_id>/',
        views.cambiar_cliente_view,
        name='cambiar_cliente',
    ),
]
