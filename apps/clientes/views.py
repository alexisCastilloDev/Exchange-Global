"""
Módulo de vistas para la aplicación de clientes.
Gestiona el listado, creación, actualización y baja lógica de clientes, 
incorporando las reglas de negocio para segmentación (GE-8) y eliminación segura (GE-63).
"""
from django.urls import reverse_lazy
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.views.generic import CreateView, UpdateView, ListView
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin, PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin

from .models import Cliente
from .forms import ClienteForm


class PanelAdminView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    Vista para renderizar el panel de administración con la lista de clientes.
    
    Historia de Usuario GE-8: Se incluye lógica para filtrar el listado 
    mostrando únicamente los clientes que pertenezcan a la categoría/segmento seleccionado.
    
    Historia de Usuario GE-63: Se listan únicamente los clientes activos por defecto. 
    Se permite incluir inactivos si se requiere revisar el historial.
    """

    model = Cliente
    template_name = 'panel_admin.html'
    context_object_name = 'clientes'
    permission_required = 'authentication.acceder_panel_admin'

    def get_queryset(self):
        """
        Construye el QuerySet aplicando filtros de estado (activo/inactivo) 
        y de segmentación según los parámetros de la URL.
        """
        # GE-63: Mostrar activos por defecto. Mostrar inactivos solo si se solicita explícitamente.
        incluir_inactivos = self.request.GET.get('incluir_inactivos') == '1'
        
        if incluir_inactivos:
            queryset = Cliente.objects.all()  # Trae todo el historial
        else:
            queryset = Cliente.activos.all()  # Trae solo los vigentes

        # GE-8: Filtro adicional por segmento de cliente
        segmento_seleccionado = self.request.GET.get('segmento')
        if segmento_seleccionado:
            queryset = queryset.filter(segmento=segmento_seleccionado)
            
        return queryset

    def get_context_data(self, **kwargs):
        """
        Añade las opciones de segmentación y estado actual al contexto 
        para construir el formulario de filtrado en el template.
        """
        context = super().get_context_data(**kwargs)
        # Opciones de segmentación (GE-8)
        context['segmentos'] = Cliente.SEGMENTO_CHOICES
        context['segmento_actual'] = self.request.GET.get('segmento', '')
        
        # Estado del filtro de inactivos (GE-63)
        context['incluir_inactivos'] = self.request.GET.get('incluir_inactivos') == '1'
        return context

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
        messages.error(self.request, "No tienes los permisos necesarios para acceder a este panel.")
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
    
    Historia de Usuario GE-8: A través del ClienteForm inyectado, permite
    al administrador reasignar la categoría/segmento del cliente.
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


class ClienteSoftDeleteView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Vista para procesar la eliminación (baja lógica) de un cliente.
    
    Historia de Usuario GE-63: Cambia el estado del cliente a inactivo en lugar
    de borrar el registro de la base de datos, preservando su historial.
    """

    def test_func(self):
        """
        Solo administradores (staff o superusuarios) pueden dar de baja clientes.
        """
        return self.request.user.is_staff or self.request.user.is_superuser

    def post(self, request, pk, *args, **kwargs):
        """
        Interpreta la petición POST para realizar la baja lógica.
        """
        cliente = get_object_or_404(Cliente, pk=pk)
        
        # Ejecuta la baja lógica definida en el modelo
        cliente.soft_delete()
        
        # Determina el nombre a mostrar en el mensaje de éxito
        nombre_display = (
            cliente.razon_social 
            if cliente.tipo_cliente == Cliente.TIPO_JURIDICA 
            else f"{cliente.nombre} {cliente.apellido}".strip()
        )
        
        messages.success(request, f"¡El cliente {nombre_display} ha sido dado de baja correctamente!")
        
        # Redirige de vuelta a la página desde la que se hizo la petición o al panel_admin
        url_previa = request.META.get('HTTP_REFERER')
        if url_previa:
            return redirect(url_previa)
        return redirect('home')  # Puedes cambiar 'home' por el 'name' exacto de tu URL para el panel