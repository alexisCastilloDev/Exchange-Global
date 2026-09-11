from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.contrib import messages

from apps.authentication.decorators import requiere_permiso
from apps.authentication.forms import CausaBajaForm
from apps.authentication.models import HistorialBaja
from .services import (
    actualizar_usuario_en_keycloak,
    obtener_roles_disponibles,
    obtener_roles_de_usuario,
    actualizar_roles_de_usuario,
    sincronizar_usuarios_desde_keycloak,
)

User = get_user_model()


@requiere_permiso('usuarios')
def lista_usuarios_view(request):
    query = request.GET.get('q', '').strip()
    try:
        roles_por_usuario = sincronizar_usuarios_desde_keycloak()
    except Exception:
        roles_por_usuario = {}
        messages.warning(
            request,
            'No fue posible actualizar los usuarios desde Keycloak. '
            'Se muestran los datos locales disponibles.',
        )

    usuarios = User.objects.filter(is_active=True).order_by('id')

    if query:
        usuarios = usuarios.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query)
        )

    return render(request, 'user_list.html', {
        'usuarios': usuarios,
        'query': query,
        'roles_por_usuario': roles_por_usuario,
    })


@requiere_permiso('usuarios')
def editar_usuario_view(request, user_id):
    usuario = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()

        try:
            actualizar_usuario_en_keycloak(
                email=usuario.email,
                first_name=first_name,
                last_name=last_name,
                is_active=usuario.is_active,
            )

            usuario.first_name = first_name
            usuario.last_name = last_name
            usuario.save(update_fields=['first_name', 'last_name'])

            messages.success(request, f"Usuario {usuario.email} actualizado correctamente.")
            return redirect('lista_usuarios')

        except Exception as e:
            messages.error(request, f"Error al actualizar en Keycloak: {str(e)}")

    return render(request, 'user_edit.html', {'usuario': usuario})


@requiere_permiso('admin')
def baja_usuario_view(request, user_id):
    usuario = get_object_or_404(User, id=user_id)

    if not usuario.is_active:
        messages.info(request, 'El usuario ya se encontraba inactivo.')
        return redirect('lista_usuarios')

    if request.method == 'POST':
        form = CausaBajaForm(request.POST)
        if form.is_valid():
            try:
                actualizar_usuario_en_keycloak(
                    email=usuario.email,
                    first_name=usuario.first_name,
                    last_name=usuario.last_name,
                    is_active=False,
                )
            except Exception as error:
                messages.error(
                    request, f'No se pudo dar de baja el usuario: {error}'
                )
            else:
                usuario.is_active = False
                usuario.save(update_fields=['is_active'])
                HistorialBaja.objects.create(
                    tipo_recurso=HistorialBaja.TIPO_USUARIO,
                    recurso_id=usuario.pk,
                    recurso_nombre=(
                        usuario.get_full_name().strip() or usuario.username
                    ),
                    causa=form.cleaned_data['causa'],
                    realizado_por=request.user,
                )
                messages.success(
                    request, f'El usuario {usuario.email} fue dado de baja.'
                )
                return redirect('lista_usuarios')
    else:
        form = CausaBajaForm()

    return render(
        request,
        'bajas/confirmar_baja.html',
        {
            'form': form,
            'recurso_tipo': 'usuario',
            'recurso_nombre': usuario.get_full_name().strip() or usuario.username,
            'cancelar_url': reverse('lista_usuarios'),
        },
    )


@requiere_permiso('admin')
def historial_bajas_usuarios_view(request):
    registros = HistorialBaja.objects.filter(
        tipo_recurso=HistorialBaja.TIPO_USUARIO
    ).select_related('realizado_por')
    return render(
        request,
        'bajas/historial_bajas.html',
        {
            'registros': registros,
            'titulo': 'Historial de bajas de usuarios',
            'volver_url': reverse('lista_usuarios'),
        },
    )


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
