from django.contrib import admin
from django.urls import path, include
from global_exchange.views import home, panel_protegido, perfil
from apps.authentication.views import CustomOIDCLogoutView, CustomOIDCCallbackView
from apps.clientes import views as clientes_views
from apps.clientes.views import (
    PanelAdminView,
    ClienteCreateView,
    ClienteDetailView,
    ClienteUpdateView,
    ClienteSoftDeleteView,
    ClienteHistorialBajasView,
    AsociarUsuariosClienteView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('panel/', panel_protegido, name='panel_protegido'),
    path('perfil/', perfil, name='perfil'),
    # Enrutado directo a la vista real (antes apuntaba a un stub vacío
    # en global_exchange.views mientras PanelAdminView, con la lógica
    # de filtros de GE-8/GE-63, no estaba registrada en ningún lado).
    path('panel-admin/', PanelAdminView.as_view(), name='panel_admin'),
    path('usuarios/', include('apps.users.urls')),
    path('oidc/logout/', CustomOIDCLogoutView.as_view(), name='oidc_logout'),
    path('oidc/callback/', CustomOIDCCallbackView.as_view(), name='oidc_authentication_callback'),
    path('oidc/', include('mozilla_django_oidc.urls')),

    # Alias de rutas de clientes sin namespace para compatibilidad con templates/tests existentes.
    path('clientes/nuevo/', ClienteCreateView.as_view(), name='cliente_create'),
    path('clientes/<int:pk>/', ClienteDetailView.as_view(), name='cliente_detail'),
    path('clientes/<int:pk>/editar/', ClienteUpdateView.as_view(), name='cliente_update'),
    path('clientes/<int:pk>/asociar-usuarios/', AsociarUsuariosClienteView.as_view(), name='cliente_asociar_usuarios'),
    path('clientes/<int:pk>/eliminar/', ClienteSoftDeleteView.as_view(), name='cliente_delete'),
    path('clientes/historial-bajas/', ClienteHistorialBajasView.as_view(), name='cliente_historial_bajas'),
    path('clientes/seleccionar/', clientes_views.seleccionar_cliente_view, name='seleccionar_cliente'),
    path('clientes/cambiar/<int:cliente_id>/', clientes_views.cambiar_cliente_view, name='cambiar_cliente'),
    path('clientes/metodos-pago/', clientes_views.metodo_pago_list, name='metodo_pago_list'),
    path('clientes/metodos-pago/nuevo/', clientes_views.metodo_pago_create, name='metodo_pago_create'),
    path('clientes/metodos-pago/<int:pk>/editar/', clientes_views.metodo_pago_update, name='metodo_pago_update'),
    path('clientes/metodos-pago/<int:pk>/eliminar/', clientes_views.metodo_pago_delete, name='metodo_pago_delete'),
    path('clientes/metodos-pago/<int:pk>/predeterminado/', clientes_views.metodo_pago_set_default, name='metodo_pago_set_default'),

    path('clientes/', include('apps.clientes.urls')),
    path('divisas/', include('apps.divisas.urls')),   # <- esta línea es la que rescatás de GE-18/20
]