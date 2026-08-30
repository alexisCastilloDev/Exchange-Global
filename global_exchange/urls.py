"""
URL configuration for global_exchange project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from global_exchange.views import home, panel_protegido, panel_admin
from apps.authentication.views import CustomOIDCLogoutView, CustomOIDCCallbackView

urlpatterns = [
    path('', home, name='home'),
    path('panel/', panel_protegido, name='panel_protegido'),
    path('panel-admin/', panel_admin, name='panel_admin'),
    path('admin/', admin.site.urls),
    path('oidc/logout/', CustomOIDCLogoutView.as_view(), name='oidc_logout'),
    path('oidc/callback/', CustomOIDCCallbackView.as_view(), name='oidc_authentication_callback'),
    path('oidc/', include('mozilla_django_oidc.urls')),
]