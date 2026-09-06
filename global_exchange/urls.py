from django.contrib import admin
from django.urls import path, include
from global_exchange.views import home, panel_protegido
from apps.authentication.views import CustomOIDCLogoutView, CustomOIDCCallbackView
from apps.clientes.views import PanelAdminView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('panel/', panel_protegido, name='panel_protegido'),
    path('panel-admin/', PanelAdminView.as_view(), name='panel_admin'),
    path('usuarios/', include('apps.users.urls')),
    path('oidc/logout/', CustomOIDCLogoutView.as_view(), name='oidc_logout'),
    path('oidc/callback/', CustomOIDCCallbackView.as_view(), name='oidc_authentication_callback'),
    path('oidc/', include('mozilla_django_oidc.urls')),
    path('clientes/', include('apps.clientes.urls')),
    path('divisas/', include('apps.divisas.urls')),   # <- esta línea es la que rescatás de GE-18/20
]