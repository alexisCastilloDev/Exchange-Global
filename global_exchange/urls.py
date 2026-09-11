"""
URL configuration for global_exchange project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include
from global_exchange.views import home, panel_protegido, perfil
from apps.authentication.views import CustomOIDCLogoutView, CustomOIDCCallbackView
from apps.clientes.views import PanelAdminView

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
    path('clientes/', include('apps.clientes.urls')),
    path('divisas/', include('apps.divisas.urls')),
]