"""Rutas para la apertura, consulta, operaciones de ventanilla y arqueo de la caja de un cajero."""

from django.urls import path

from apps.caja.views import (
    AbrirCajaView,
    DetalleArqueoCajaView,
    HistorialArqueosCajaView,
    IniciarArqueoCajaView,
    PanelCajaView,
    RegistrarOperacionVentanillaView,
)

app_name = 'caja'

urlpatterns = [
    path('', PanelCajaView.as_view(), name='panel'),
    path('abrir/', AbrirCajaView.as_view(), name='abrir'),
    path('operaciones/<str:tipo>/', RegistrarOperacionVentanillaView.as_view(), name='registrar_operacion'),
    path('arqueo/', IniciarArqueoCajaView.as_view(), name='iniciar_arqueo'),
    path('arqueo/historial/', HistorialArqueosCajaView.as_view(), name='historial_arqueos'),
    path('arqueo/<uuid:pk>/', DetalleArqueoCajaView.as_view(), name='detalle_arqueo'),
]
