from django.urls import path
from .views import (
    ActualizarCotizacionView,
    DivisaCreateView,
    DivisaListView,
    DivisaUpdateView,
    TasasVigentesListView,
)
"""
Configuración de URLs para la aplicación de divisas.
Contiene las rutas necesarias para la consulta de tasas.
"""

app_name = 'divisas'

urlpatterns = [
    path('tasas-vigentes/', TasasVigentesListView.as_view(), name='tasas_vigentes'),
    path('tasas-vigentes/<int:divisa_id>/actualizar/', ActualizarCotizacionView.as_view(), name='actualizar_cotizacion'),
    #rutas para la gestión de divisas (GE-18)
    path('administrar/', DivisaListView.as_view(), name='lista_divisas'),
    path('administrar/nueva/', DivisaCreateView.as_view(), name='crear_divisa'),
    path('administrar/editar/<int:pk>/', DivisaUpdateView.as_view(), name='editar_divisa'),
]