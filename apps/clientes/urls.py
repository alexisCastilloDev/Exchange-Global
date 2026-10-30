"""Rutas de clientes, selección de contexto y métodos de pago."""

from django import views
from django.urls import path
from .views import (
    ClienteCreateView,
    ClienteDetailView,
    ClienteUpdateView,
    ClienteSoftDeleteView,
    ClienteHistorialBajasView,
    AsociarUsuariosClienteView,
    SolicitarClienteView,
    SolicitudesClienteListView,
    AprobarSolicitudClienteView,
    RechazarSolicitudClienteView,
)
from apps.clientes import views
from apps.divisas.pagos_stripe import IniciarAgregarTarjetaStripeView, confirmar_tarjeta_stripe_view

app_name = 'clientes'

urlpatterns = [
    # --- RUTAS ORIGINALES ---
    path('nuevo/', ClienteCreateView.as_view(), name='cliente_create'),
    path('<int:pk>/', ClienteDetailView.as_view(), name='cliente_detail'),
    path('<int:pk>/editar/', ClienteUpdateView.as_view(), name='cliente_update'),
    path('<int:pk>/asociar-usuarios/', AsociarUsuariosClienteView.as_view(), name='cliente_asociar_usuarios'),
    path('<int:pk>/eliminar/', ClienteSoftDeleteView.as_view(), name='cliente_delete'),
    path('historial-bajas/', ClienteHistorialBajasView.as_view(), name='cliente_historial_bajas'),
    path('solicitar/', SolicitarClienteView.as_view(), name='solicitar_cliente'),
    path('solicitudes/', SolicitudesClienteListView.as_view(), name='solicitudes_cliente'),
    path('solicitudes/<int:pk>/aprobar/', AprobarSolicitudClienteView.as_view(), name='aprobar_solicitud_cliente'),
    path('solicitudes/<int:pk>/rechazar/', RechazarSolicitudClienteView.as_view(), name='rechazar_solicitud_cliente'),

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
    path('metodos-pago/<int:pk>/eliminar/', views.metodo_pago_delete, name='metodo_pago_delete'),
    path('metodos-pago/<int:pk>/predeterminado/', views.metodo_pago_set_default, name='metodo_pago_set_default'),
    path('metodos-pago/<int:pk>/ver-datos/', views.metodo_pago_reveal, name='metodo_pago_reveal'),
    path('metodos-pago/<int:pk>/movimientos/', views.metodo_pago_movimientos, name='metodo_pago_movimientos'),
    path(
        'metodos-pago/tarjeta/nueva/',
        IniciarAgregarTarjetaStripeView.as_view(),
        name='agregar_tarjeta_stripe',
    ),
    path(
        'metodos-pago/tarjeta/confirmar/',
        confirmar_tarjeta_stripe_view,
        name='confirmar_tarjeta_stripe',
    ),
]
