from django.urls import path
from .views import TasasVigentesListView, DivisaListView, DivisaCreateView, DivisaUpdateView
"""
Configuración de URLs para la aplicación de divisas.
Contiene las rutas necesarias para la consulta de tasas.
"""

app_name = 'divisas'

urlpatterns = [
    path('tasas-vigentes/', TasasVigentesListView.as_view(), name='tasas_vigentes'),
    #rutas para la gestión de divisas (GE-18)
    path('administrar/', DivisaListView.as_view(), name='lista_divisas'),
    path('administrar/nueva/', DivisaCreateView.as_view(), name='crear_divisa'),
    path('administrar/editar/<int:pk>/', DivisaUpdateView.as_view(), name='editar_divisa'),
]