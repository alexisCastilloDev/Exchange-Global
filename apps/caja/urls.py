"""Rutas para la apertura, consulta, operaciones de ventanilla, movimientos extraordinarios y arqueo de la caja de un cajero."""

from django.urls import path

from apps.caja.views import (
    AbrirCajaView,
    CerrarCajaView,
    DetalleArqueoCajaView,
    HistorialArqueosCajaView,
    HistorialCajasView,
    IniciarArqueoCajaView,
    PanelCajaView,
    RegistrarMovimientoExtraordinarioView,
    RegistrarOperacionVentanillaView,
)

app_name = 'caja'

urlpatterns = [
    path('', PanelCajaView.as_view(), name='panel'),
    path('abrir/', AbrirCajaView.as_view(), name='abrir'),
    path('cerrar/', CerrarCajaView.as_view(), name='cerrar'),
    path('historial/', HistorialCajasView.as_view(), name='historial_cajas'),
    path('operaciones/<str:tipo>/', RegistrarOperacionVentanillaView.as_view(), name='registrar_operacion'),
    path(
        'movimientos/<str:tipo>/',
        RegistrarMovimientoExtraordinarioView.as_view(),
        name='registrar_movimiento_extraordinario',
    ),
    path('arqueo/', IniciarArqueoCajaView.as_view(), name='iniciar_arqueo'),
    path('arqueo/historial/', HistorialArqueosCajaView.as_view(), name='historial_arqueos'),
    path('arqueo/<uuid:pk>/', DetalleArqueoCajaView.as_view(), name='detalle_arqueo'),
]
