from django.urls import path
from .views import (
    TasasVigentesListView,
    DivisaListView,
    DivisaCreateView,
    DivisaUpdateView,
    ActualizarCotizacionView,
    HistorialCotizacionesView,
    DivisaSoftDeleteView,
    DivisaHistorialBajasView,
    SimulacionDivisasView,
)
"""
Configuración de URLs para la aplicación de divisas.
Contiene las rutas necesarias para la consulta de tasas y la gestión de divisas.
"""

app_name = 'divisas'

urlpatterns = [
    path('tasas-vigentes/', TasasVigentesListView.as_view(), name='tasas_vigentes'),
    path('simulacion/', SimulacionDivisasView.as_view(), name='simulacion_divisas'),
    path('cotizaciones/<int:divisa_id>/actualizar/', ActualizarCotizacionView.as_view(), name='actualizar_cotizacion'),
    path('cotizaciones/<int:divisa_id>/historial/', HistorialCotizacionesView.as_view(), name='historial_cotizaciones'),
    path('administrar/', DivisaListView.as_view(), name='lista_divisas'),
    path('administrar/nueva/', DivisaCreateView.as_view(), name='crear_divisa'),
    path('administrar/editar/<int:pk>/', DivisaUpdateView.as_view(), name='editar_divisa'),
    path('administrar/<int:pk>/baja/', DivisaSoftDeleteView.as_view(), name='baja_divisa'),
    path('administrar/historial-bajas/', DivisaHistorialBajasView.as_view(), name='historial_bajas'),
]
