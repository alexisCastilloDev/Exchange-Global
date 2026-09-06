"""
Vistas generales del proyecto: pantalla de bienvenida y paneles
protegidos por rol de Keycloak (sesión).
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.authentication.decorators import requiere_permiso


def home(request):
    """
    Vista pública de bienvenida.
    """
    return render(request, 'home.html')


@login_required
def panel_protegido(request):
    """
    Vista de prueba para demostrar que el acceso está protegido
    por sesión/token válido (GE-3).
    """
    return render(request, 'panel.html')


@requiere_permiso('panel_admin')
def panel_admin(request):
    """
    Panel exclusivo para el rol admin (o el rol 'panel_admin' en Keycloak).
    El acceso se controla 100% desde Keycloak.
    """
    return render(request, 'panel_admin.html')