from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.contrib import messages

from apps.authentication.decorators import requiere_permiso
from .services import (
    actualizar_usuario_en_keycloak,
    obtener_roles_disponibles,
    obtener_roles_de_usuario,
    actualizar_roles_de_usuario,
)

User = get_user_model()


@requiere_permiso('usuarios')
def lista_usuarios_view(request):
    query = request.GET.get('q', '').strip()
    usuarios = User.objects.all().order_by('id')

    if query:
        usuarios = usuarios.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query)
        )

    return render(request, 'user_list.html', {
        'usuarios': usuarios,
        'query': query
    })


@requiere_permiso('usuarios')
def editar_usuario_view(request, user_id):
    usuario = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()

        raw_is_active = request.POST.get('is_active')
        is_active = raw_is_active in ['on', 'true', 'True', True]

        try:
            actualizar_usuario_en_keycloak(
                email=usuario.email,
                first_name=first_name,
                last_name=last_name,
                is_active=is_active
            )

            usuario.first_name = first_name
            usuario.last_name = last_name
            usuario.is_active = is_active
            usuario.save()

            messages.success(request, f"Usuario {usuario.email} actualizado correctamente.")
            return redirect('lista_usuarios')

        except Exception as e:
            messages.error(request, f"Error al actualizar en Keycloak: {str(e)}")

    return render(request, 'user_edit.html', {'usuario': usuario})


@requiere_permiso('gestion_roles')
def editar_roles_view(request, user_id):
    """
    Permite a un admin (rol 'admin' o 'gestion_roles' en Keycloak) asignar
    o quitar realm roles de otro usuario. Todo se lee/escribe directo
    contra la Admin API de Keycloak — Django no persiste el rol en
    ningún lado propio.
    """
    usuario = get_object_or_404(User, id=user_id)

    try:
        roles_disponibles = obtener_roles_disponibles()
        roles_actuales = obtener_roles_de_usuario(usuario.email)
    except Exception as e:
        messages.error(request, f"Error al consultar roles en Keycloak: {str(e)}")
        return redirect('lista_usuarios')

    if request.method == 'POST':
        roles_seleccionados = request.POST.getlist('roles')
        try:
            actualizar_roles_de_usuario(usuario.email, roles_seleccionados)
            messages.success(
                request,
                f"Roles de {usuario.email} actualizados. "
                f"Debe volver a loguearse para que el cambio aplique."
            )
            return redirect('lista_usuarios')
        except Exception as e:
            messages.error(request, f"Error al actualizar roles en Keycloak: {str(e)}")

    return render(request, 'user_roles.html', {
        'usuario': usuario,
        'roles_disponibles': roles_disponibles,
        'roles_actuales': roles_actuales,
    })