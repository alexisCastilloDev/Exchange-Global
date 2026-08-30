from django.shortcuts import render
from django.contrib.auth.decorators import login_required


def home(request):
    return render(request, 'home.html')


@login_required
def panel_protegido(request):
    """
    Vista de prueba para demostrar que el acceso está protegido
    por sesión/token válido
    """
    return render(request, 'panel.html')


@login_required
def panel_admin(request):
    """
    Vista a la que se redirige a los usuarios con rol admin
    tras el login
    """
    return render(request, 'panel_admin.html')