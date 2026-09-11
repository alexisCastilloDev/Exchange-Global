from django.urls import path
from .views import (
    baja_usuario_view,
    editar_usuario_view,
    editar_roles_view,
    historial_bajas_usuarios_view,
    lista_usuarios_view,
)

urlpatterns = [
    path('', lista_usuarios_view, name='lista_usuarios'),
    path('<int:user_id>/editar/', editar_usuario_view, name='editar_usuario'),
    path('<int:user_id>/baja/', baja_usuario_view, name='baja_usuario'),
    path('<int:user_id>/roles/', editar_roles_view, name='editar_roles'),
    path('historial-bajas/', historial_bajas_usuarios_view, name='historial_bajas_usuarios'),
]
