from django.urls import path
from .views import ClienteCreateView

urlpatterns = [
    # Esta ruta será: localhost:8000/clientes/nuevo/
    path('nuevo/', ClienteCreateView.as_view(), name='cliente_create'),
]