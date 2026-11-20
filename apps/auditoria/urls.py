"""Rutas de la aplicación de auditoría."""
from django.urls import path

from apps.auditoria.views import RegistroActividadListView

app_name = 'auditoria'

urlpatterns = [
    path('actividades/', RegistroActividadListView.as_view(), name='registro_actividades'),
]
