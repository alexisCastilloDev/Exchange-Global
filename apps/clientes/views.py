from django.urls import reverse_lazy
from django.shortcuts import redirect  
from django.contrib import messages
from django.views.generic import CreateView, UpdateView, ListView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin, PermissionRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.contrib.messages.views import SuccessMessageMixin
from .models import Cliente
from .forms import ClienteForm


class PanelAdminView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    Vista para renderizar el panel de administración con la lista de clientes.
    """

    model = Cliente
    template_name = 'panel_admin.html'
    context_object_name = 'clientes'
    permission_required = 'authentication.acceder_panel_admin'

    def has_permission(self):
        """
        Valida si el usuario actual posee permisos de staff, superusuario
        o el permiso específico para acceder al panel de administración.
        """
        user = self.request.user
        return user.is_staff or user.is_superuser or user.has_perm(self.permission_required)

    def handle_no_permission(self):
        """
        Redirige al inicio con un mensaje de error cuando el usuario no tiene permisos.
        """
        # 1. Agregamos el mensaje de error que el test está esperando
        messages.error(self.request, "No tienes los permisos necesarios para acceder a este panel.")
        
        # 2. Redirigimos al home en lugar del login
        return redirect('home')

class ClienteCreateView(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, CreateView):
    """
    Vista para el alta de nuevos clientes en el sistema.
    """

    model = Cliente
    form_class = ClienteForm
    template_name = 'clientes/cliente_form.html'
    success_url = reverse_lazy('home')

    def get_success_message(self, cleaned_data):
        nombre_display = (
            self.object.razon_social 
            if self.object.tipo_cliente == Cliente.TIPO_JURIDICA 
            else f"{self.object.nombre} {self.object.apellido}"
        )
        return f"¡El cliente {nombre_display} ha sido registrado exitosamente!"

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser


class ClienteUpdateView(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, UpdateView):
    """
    Vista para la edición de datos de un cliente existente.
    """

    model = Cliente
    form_class = ClienteForm
    template_name = 'clientes/cliente_form.html'
    success_url = reverse_lazy('home')

    def get_success_message(self, cleaned_data):
        nombre_display = (
            self.object.razon_social 
            if self.object.tipo_cliente == Cliente.TIPO_JURIDICA 
            else f"{self.object.nombre} {self.object.apellido}"
        )
        return f"¡Los datos de {nombre_display} se han actualizado correctamente!"

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser