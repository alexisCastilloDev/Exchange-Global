"""
URL configuration for global_exchange project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include
from global_exchange.views import home, panel_protegido, panel_admin, gestion_roles
from apps.authentication.views import CustomOIDCLogoutView, CustomOIDCCallbackView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('panel/', panel_protegido, name='panel_protegido'),
    path('panel-admin/', panel_admin, name='panel_admin'),
    path('roles/', gestion_roles, name='gestion_roles'),
    path('usuarios/', include('apps.users.urls')),
    path('oidc/logout/', CustomOIDCLogoutView.as_view(), name='oidc_logout'),
    path('oidc/callback/', CustomOIDCCallbackView.as_view(), name='oidc_authentication_callback'),
    path('oidc/', include('mozilla_django_oidc.urls')),
    path('clientes/', include('apps.clientes.urls')),
]