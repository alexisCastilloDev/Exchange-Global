from django.urls import path
from .views import TasasVigentesListView

"""
Configuración de URLs para la aplicación de divisas.
Contiene las rutas necesarias para la consulta de tasas.
"""

app_name = 'divisas'

urlpatterns = [
    path('tasas-vigentes/', TasasVigentesListView.as_view(), name='tasas_vigentes'),
]