"""URLs de sipap-sim: la API que consume Global Exchange, la 'banca en línea' y el panel administrativo."""

from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path('api/solicitudes-cobro/', views.crear_solicitud_cobro, name='crear_solicitud_cobro'),
    path('api/transferencias/<str:id_transferencia>/', views.consultar_transferencia, name='consultar_transferencia'),
    path('api/transferencias/', views.crear_transferencia_saliente, name='crear_transferencia_saliente'),
    path('api/cuentas/validar/', views.validar_cuenta, name='validar_cuenta'),
    path('pagar/<str:id_transferencia>/', views.elegir_cuenta_view, name='elegir_cuenta'),
    path('ingresar/', LoginView.as_view(template_name='core/ingresar.html'), name='login'),
    path('salir/', LogoutView.as_view(next_page='login'), name='logout'),
    path('panel/', views.panel_view, name='panel'),
    path('panel/proveedores/', views.proveedores_view, name='proveedores'),
    path('panel/proveedores/<int:pk>/eliminar/', views.eliminar_proveedor_view, name='eliminar_proveedor'),
    path('panel/cuentas/', views.cuentas_view, name='cuentas'),
    path('panel/cuentas/<int:pk>/eliminar/', views.eliminar_cuenta_view, name='eliminar_cuenta'),
]
