"""Rutas para consulta, simulación y administración de divisas."""

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
    CalculoOperacionView,
    confirmar_calculo_operacion_view,
    TriangulacionOperacionView,
    confirmar_triangulacion_view,
    ConfiguracionComisionListView,
    ActualizarComisionView,
    HistorialTransaccionesView,
)
"""
Configuración de URLs para la aplicación de divisas.
Contiene las rutas necesarias para la consulta de tasas y la gestión de divisas.
"""

app_name = 'divisas'

urlpatterns = [
    path('tasas-vigentes/', TasasVigentesListView.as_view(), name='tasas_vigentes'),
    path('simulacion/', SimulacionDivisasView.as_view(), name='simulacion_divisas'),
    path('operar/<str:tipo>/', CalculoOperacionView.as_view(), name='operar'),
    path('operar/<str:tipo>/confirmar/', confirmar_calculo_operacion_view, name='confirmar_operacion'),
    path('triangulacion/', TriangulacionOperacionView.as_view(), name='triangulacion'),
    path(
        'triangulacion/<uuid:calculo_id>/confirmar/',
        confirmar_triangulacion_view,
        name='confirmar_triangulacion',
    ),
    path('cotizaciones/<int:divisa_id>/actualizar/', ActualizarCotizacionView.as_view(), name='actualizar_cotizacion'),
    path('cotizaciones/<int:divisa_id>/historial/', HistorialCotizacionesView.as_view(), name='historial_cotizaciones'),
    path('transacciones/', HistorialTransaccionesView.as_view(), name='historial_transacciones'),
    path('comisiones/', ConfiguracionComisionListView.as_view(), name='comisiones'),
    path('comisiones/<str:segmento>/editar/', ActualizarComisionView.as_view(), name='actualizar_comision'),
    path('administrar/', DivisaListView.as_view(), name='lista_divisas'),
    path('administrar/nueva/', DivisaCreateView.as_view(), name='crear_divisa'),
    path('administrar/editar/<int:pk>/', DivisaUpdateView.as_view(), name='editar_divisa'),
    path('administrar/<int:pk>/baja/', DivisaSoftDeleteView.as_view(), name='baja_divisa'),
    path('administrar/historial-bajas/', DivisaHistorialBajasView.as_view(), name='historial_bajas'),
]
