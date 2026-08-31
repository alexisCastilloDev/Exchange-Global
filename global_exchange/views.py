"""
Vistas generales del proyecto: pantalla de bienvenida, paneles
protegidos por sesión (GE-3) y gestión de permisos por rol (GE-7).
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, Permission
from django.shortcuts import render, redirect

from apps.authentication.decorators import requiere_permiso
from apps.authentication.models import RecursoProtegido


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
    Panel exclusivo para el rol admin. Valida el permiso
    `acceder_panel_admin` del Group del usuario, tanto si llega desde
    el menú como por URL directa (GE-7).
    """
    return render(request, 'panel_admin.html')


@requiere_permiso('gestion_roles')
def gestion_roles(request):
    """
    Panel donde un administrador define qué recursos puede acceder
    cada rol (Group), marcando/desmarcando permisos.
    """
    grupos = Group.objects.all()
    recursos = RecursoProtegido.objects.all()

    if request.method == 'POST':
        grupo = Group.objects.get(id=request.POST.get('grupo_id'))
        codigos_marcados = request.POST.getlist('recursos')

        grupo.permissions.clear()
        for recurso in recursos:
            if recurso.codigo in codigos_marcados:
                permiso = Permission.objects.get(
                    codename=f'acceder_{recurso.codigo}',
                    content_type__app_label='authentication',
                )
                grupo.permissions.add(permiso)

        messages.success(request, f'Permisos de "{grupo.name}" actualizados.')
        return redirect('gestion_roles')

    # Le agregamos a cada grupo la lista de códigos de recurso que ya
    # tiene permitidos, para que el template sepa qué checkbox marcar.
    codenames_por_recurso = {r.codigo: f'acceder_{r.codigo}' for r in recursos}
    for grupo in grupos:
        codenames_del_grupo = set(grupo.permissions.values_list('codename', flat=True))
        grupo.permisos_codigos = [
            codigo for codigo, codename in codenames_por_recurso.items()
            if codename in codenames_del_grupo
        ]

    return render(request, 'gestion_roles.html', {
        'grupos': grupos,
        'recursos': recursos,
    })