"""URLs de sipap-sim: la API que consume Global Exchange y la 'banca en línea'."""

from django.urls import path

from . import views

urlpatterns = [
    path('api/solicitudes-cobro/', views.crear_solicitud_cobro, name='crear_solicitud_cobro'),
    path('api/transferencias/<str:id_transferencia>/', views.consultar_transferencia, name='consultar_transferencia'),
    path('api/transferencias/', views.crear_transferencia_saliente, name='crear_transferencia_saliente'),
    path('api/cuentas/validar/', views.validar_cuenta, name='validar_cuenta'),
    path('pagar/<str:id_transferencia>/', views.elegir_cuenta_view, name='elegir_cuenta'),
]
