from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as AuthUserAdmin
from django.utils.translation import ngettext

from .services import actualizar_usuario_en_keycloak

User = get_user_model()

# Si ya está registrado (por contrib.auth), lo desregistramos para poder
# registrar nuestra propia versión. Si no está registrado, ignoramos el error.
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass


@admin.register(User)
class CustomUserAdmin(AuthUserAdmin):
    """
    Extiende el admin por defecto de User agregando una acción para sincronizar
    usuarios seleccionados con Keycloak (first_name, last_name, enabled).
    """
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    list_filter = ('is_active', 'is_staff', 'groups')
    actions = ['sync_to_keycloak']

    def sync_to_keycloak(self, request, queryset):
        """
        Acción admin: sincroniza los usuarios seleccionados con Keycloak.
        Reporta resultados mediante message_user.
        """
        success = 0
        errors = []

        for user in queryset:
            if not user.email:
                errors.append(f"{user.username}: no tiene email")
                continue
            try:
                actualizar_usuario_en_keycloak(
                    email=user.email,
                    first_name=user.first_name or "",
                    last_name=user.last_name or "",
                    is_active=user.is_active
                )
                success += 1
            except Exception as e:
                errors.append(f"{user.username}: {e}")

        if success:
            self.message_user(request, ngettext(
                '%d usuario sincronizado con Keycloak.',
                '%d usuarios sincronizados con Keycloak.',
                success,
            ) % success, level=messages.SUCCESS)

        if errors:
            # Mostrar hasta 10 errores para no saturar la UI
            for m in errors[:10]:
                self.message_user(request, f"Error: {m}", level=messages.ERROR)
            if len(errors) > 10:
                remaining = len(errors) - 10
                self.message_user(request, f"Y {remaining} error(es) más...", level=messages.WARNING)

    sync_to_keycloak.short_description = "Sincronizar usuarios seleccionados con Keycloak"