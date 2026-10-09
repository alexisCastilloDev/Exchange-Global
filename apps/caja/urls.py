"""Rutas para la apertura y consulta de la caja de un cajero."""

from django.urls import path

from apps.caja.views import AbrirCajaView, PanelCajaView

app_name = 'caja'

urlpatterns = [
    path('', PanelCajaView.as_view(), name='panel'),
    path('abrir/', AbrirCajaView.as_view(), name='abrir'),
]
