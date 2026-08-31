from django.urls import path
from .views import lista_usuarios_view, editar_usuario_view

urlpatterns = [
    path('', lista_usuarios_view, name='lista_usuarios'),
    path('<int:user_id>/editar/', editar_usuario_view, name='editar_usuario'),
]