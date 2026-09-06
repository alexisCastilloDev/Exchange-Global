"""
Configuración de rutas de URL para la aplicación de Clientes.

Nota: PanelAdminView (el listado de clientes) se enruta desde
global_exchange/urls.py bajo /panel-admin/, no acá — este archivo solo
contiene las rutas propias del CRUD de clientes.
"""

from django.urls import path

from .views import ClienteCreateView, ClienteUpdateView, ClienteSoftDeleteView

urlpatterns = [
    path('nuevo/', ClienteCreateView.as_view(), name='cliente_create'),
    path('<int:pk>/editar/', ClienteUpdateView.as_view(), name='cliente_update'),
    # Antes: 'cliente/<int:pk>/eliminar/', que sumado al prefijo global
    # 'clientes/' generaba /clientes/cliente/<pk>/eliminar/ — inconsistente
    # con el resto de las rutas del archivo. Se quita el segmento repetido.
    path('<int:pk>/eliminar/', ClienteSoftDeleteView.as_view(), name='cliente_delete'),
]