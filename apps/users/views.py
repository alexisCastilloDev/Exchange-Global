from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Q
from django.contrib import messages
from .services import actualizar_usuario_en_keycloak

User = get_user_model()

def es_administrador(user):
    return user.is_authenticated and user.groups.filter(name='admin').exists()

@user_passes_test(es_administrador)
def lista_usuarios_view(request):
    query = request.GET.get('q', '').strip()
    usuarios = User.objects.all().prefetch_related('groups').order_by('id')

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

@user_passes_test(es_administrador)
def editar_usuario_view(request, user_id):
    usuario = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        
        # Validar el checkbox: evalúa True si está presente en request.POST
        raw_is_active = request.POST.get('is_active')
        is_active = raw_is_active in ['on', 'true', 'True', True]

        try:
            # 1. Intentar actualizar en Keycloak
            actualizar_usuario_en_keycloak(
                email=usuario.email,
                first_name=first_name,
                last_name=last_name,
                is_active=is_active
            )

            # 2. Actualizar en la BD local de Django si Keycloak no falló
            usuario.first_name = first_name
            usuario.last_name = last_name
            usuario.is_active = is_active
            usuario.save()

            messages.success(request, f"Usuario {usuario.email} actualizado correctamente.")
            return redirect('lista_usuarios')

        except Exception as e:
            # Captura el error exacto de la API de Keycloak
            messages.error(request, f"Error al actualizar en Keycloak: {str(e)}")

    return render(request, 'user_edit.html', {'usuario': usuario})