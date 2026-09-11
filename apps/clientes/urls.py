from django import views
from django.urls import path
from .views import (
    ClienteCreateView, 
    ClienteDetailView,
    ClienteUpdateView, 
    ClienteSoftDeleteView, 
    AsociarUsuariosClienteView
)
from apps.clientes import views

app_name = 'clientes'

urlpatterns = [
    # --- RUTAS ORIGINALES ---
    path('nuevo/', ClienteCreateView.as_view(), name='cliente_create'),
    path('<int:pk>/', ClienteDetailView.as_view(), name='cliente_detail'),
    path('<int:pk>/editar/', ClienteUpdateView.as_view(), name='cliente_update'),
    path('<int:pk>/asociar-usuarios/', AsociarUsuariosClienteView.as_view(), name='cliente_asociar_usuarios'),
    path('<int:pk>/eliminar/', ClienteSoftDeleteView.as_view(), name='cliente_delete'),

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

    # --- NUEVAS RUTAS PARA GE-19: MÉTODOS DE PAGO ---
    path('metodos-pago/', views.metodo_pago_list, name='metodo_pago_list'),
    path('metodos-pago/nuevo/', views.metodo_pago_create, name='metodo_pago_create'),
    path('metodos-pago/<int:pk>/editar/', views.metodo_pago_update, name='metodo_pago_update'),
    path('metodos-pago/<int:pk>/eliminar/', views.metodo_pago_delete, name='metodo_pago_delete'),
    path('metodos-pago/<int:pk>/predeterminado/', views.metodo_pago_set_default, name='metodo_pago_set_default'),
]