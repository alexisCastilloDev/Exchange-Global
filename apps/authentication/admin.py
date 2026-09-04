from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

from .models import RecursoProtegido


@admin.register(RecursoProtegido)
class RecursoProtegidoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'perm_codename', 'perm_exists')
    search_fields = ('codigo', 'nombre')
    readonly_fields = ('perm_codename',)
    actions = ['recreate_permission']

    def perm_codename(self, obj):
        return f"acceder_{obj.codigo}"
    perm_codename.short_description = 'Permission codename'

    def perm_exists(self, obj):
        ct = ContentType.objects.get_for_model(RecursoProtegido)
        return Permission.objects.filter(content_type=ct, codename=f"acceder_{obj.codigo}").exists()
    perm_exists.boolean = True
    perm_exists.short_description = 'Permission exists'

    def recreate_permission(self, request, queryset):
        """
        Acción del admin: crea (si falta) el Permission 'acceder_<codigo>'
        para cada RecursoProtegido seleccionado.
        """
        ct = ContentType.objects.get_for_model(RecursoProtegido)
        created = 0
        for recurso in queryset:
            codename = f"acceder_{recurso.codigo}"
            perm, perm_created = Permission.objects.get_or_create(
                codename=codename,
                content_type=ct,
                defaults={'name': f'Puede acceder a {recurso.nombre}'}
            )
            if perm_created:
                created += 1
        if created:
            self.message_user(request, f'Creado(s) {created} permiso(s).', level=messages.SUCCESS)
        else:
            self.message_user(request, 'No se crearon permisos (ya existían).', level=messages.INFO)
    recreate_permission.short_description = 'Crear permiso(s) faltantes para los recursos seleccionados'