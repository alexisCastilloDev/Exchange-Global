"""
Módulo de vistas para la aplicación de clientes.
Gestiona el listado, creación, actualización y baja lógica de clientes, 
incorporando las reglas de negocio para segmentación (GE-8) y eliminación segura (GE-63).
"""
from django.urls import reverse_lazy
from django.shortcuts import redirect, get_object_or_404, render
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.views.generic import CreateView, UpdateView, ListView, DetailView
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin, PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin

from .models import Cliente
from .forms import ClienteForm, AsociarUsuarioForm

User = get_user_model()


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
    paginate_by = 20

    def get_queryset(self):
        """
        Construye el QuerySet aplicando filtros de estado (activo/inactivo),
        de segmentación y de búsqueda por texto según los parámetros de la URL.
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

        # Búsqueda por nombre, razón social, CI o RUC
        query = self.request.GET.get('q', '').strip()
        if query:
            queryset = queryset.filter(
                Q(nombre__icontains=query) |
                Q(apellido__icontains=query) |
                Q(razon_social__icontains=query) |
                Q(identificador__icontains=query)
            )

        return queryset.order_by('id')

    def get_context_data(self, **kwargs):
        """
        Añade las opciones de segmentación, el término de búsqueda y el
        estado actual al contexto para construir el formulario de filtrado
        en el template.
        """
        context = super().get_context_data(**kwargs)
        # Opciones de segmentación (GE-8)
        context['segmentos'] = Cliente.SEGMENTO_CHOICES
        context['segmento_actual'] = self.request.GET.get('segmento', '')
        
        # Estado del filtro de inactivos (GE-63)
        context['incluir_inactivos'] = self.request.GET.get('incluir_inactivos') == '1'

        # Término de búsqueda actual
        context['query'] = self.request.GET.get('q', '')
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

class ClienteDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """
    Ficha completa de un cliente: sus datos y el listado de usuarios
    habilitados a operar en su representación.
    """

    model = Cliente
    template_name = 'clientes/cliente_detail.html'
    context_object_name = 'cliente'

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['usuarios_asociados'] = self.object.usuarios.all().order_by('email')
        context['form_asociar'] = AsociarUsuarioForm()
        return context


class ClienteAsociarUsuarioView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Asocia un usuario existente (buscado por email) a un cliente,
    habilitándolo para operar en representación de dicho cliente.
    """

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

    def post(self, request, pk, *args, **kwargs):
        cliente = get_object_or_404(Cliente, pk=pk)
        form = AsociarUsuarioForm(request.POST)

        if form.is_valid():
            usuario = form.usuario
            if cliente.usuarios.filter(pk=usuario.pk).exists():
                messages.warning(request, f"El usuario {usuario.email} ya está asociado a este cliente.")
            else:
                cliente.usuarios.add(usuario)
                messages.success(request, f"Usuario {usuario.email} asociado correctamente al cliente.")
        else:
            for error in form.errors.get('email', []):
                messages.error(request, error)

        return redirect('cliente_detail', pk=cliente.pk)


class ClienteDesasociarUsuarioView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Revoca el acceso de un usuario para operar en representación de un cliente.
    """

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

    def post(self, request, pk, user_id, *args, **kwargs):
        cliente = get_object_or_404(Cliente, pk=pk)
        usuario = get_object_or_404(User, pk=user_id)

        cliente.usuarios.remove(usuario)
        messages.success(request, f"Se revocó el acceso de {usuario.email} para este cliente.")

        return redirect('cliente_detail', pk=cliente.pk)


class SeleccionarClienteActivoView(LoginRequiredMixin, View):
    """
    Permite a un usuario asociado a uno o más clientes elegir en nombre
    de cuál va a operar. También sirve para cambiar de cliente activo
    sin necesidad de cerrar sesión (se usa como 'seleccionar/' y como
    'cambiar/' en urls.py).
    """
    template_name = 'clientes/seleccionar_cliente.html'

    def get(self, request, *args, **kwargs):
        clientes = request.user.clientes_asociados.filter(is_active=True)

        # Si solo tiene un cliente asociado, se selecciona automáticamente
        # y no se le pide elegir.
        if clientes.count() == 1:
            request.session['cliente_activo_id'] = clientes.first().pk
            return redirect('home')

        return render(request, self.template_name, {'clientes': clientes})

    def post(self, request, *args, **kwargs):
        cliente_id = request.POST.get('cliente_id')
        cliente = get_object_or_404(
            request.user.clientes_asociados, pk=cliente_id, is_active=True
        )
        request.session['cliente_activo_id'] = cliente.pk
        messages.success(request, f"Ahora estás operando en representación de {cliente}.")
        return redirect('home')
