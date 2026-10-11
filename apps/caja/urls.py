"""Rutas para la apertura, consulta y operaciones de ventanilla de la caja de un cajero."""

from django.urls import path

from apps.caja.views import AbrirCajaView, PanelCajaView, RegistrarOperacionVentanillaView

app_name = 'caja'

urlpatterns = [
    path('', PanelCajaView.as_view(), name='panel'),
    path('abrir/', AbrirCajaView.as_view(), name='abrir'),
    path('operaciones/<str:tipo>/', RegistrarOperacionVentanillaView.as_view(), name='registrar_operacion'),
]
