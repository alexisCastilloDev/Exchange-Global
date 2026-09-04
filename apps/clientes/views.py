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
    Panel de administración (requiere permiso 'authentication.acceder_panel_admin').
    """
    model = Cliente
    template_name = 'panel_admin.html'
    context_object_name = 'clientes'
    permission_required = 'authentication.acceder_panel_admin'
    paginate_by = 20

    def get_queryset(self):
        incluir_inactivos = self.request.GET.get('incluir_inactivos') == '1'
        queryset = Cliente.objects.all() if incluir_inactivos else Cliente.activos.all()

        segmento_seleccionado = self.request.GET.get('segmento')
        if segmento_seleccionado:
            queryset = queryset.filter(segmento=segmento_seleccionado)

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
        context = super().get_context_data(**kwargs)
        context['segmentos'] = Cliente.SEGMENTO_CHOICES
        context['segmento_actual'] = self.request.GET.get('segmento', '')
        context['incluir_inactivos'] = self.request.GET.get('incluir_inactivos') == '1'
        context['query'] = self.request.GET.get('q', '')
        return context

    def has_permission(self):
        # Unificar autorización: usar permisos de Django
        user = self.request.user
        return user.has_perm(self.permission_required)

    def handle_no_permission(self):
        messages.error(self.request, "No tienes los permisos necesarios para acceder a este panel.")
        return redirect('home')


class ClienteCreateView(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, CreateView):
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
        # Requiere permiso explícito para operar sobre clientes
        return self.request.user.has_perm('authentication.acceder_clientes')


class ClienteUpdateView(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, UpdateView):
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
        # Permiso necesario para editar clientes
        return self.request.user.has_perm('authentication.acceder_clientes')


class ClienteSoftDeleteView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        # Permiso necesario para dar de baja clientes
        return self.request.user.has_perm('authentication.acceder_clientes')

    def post(self, request, pk, *args, **kwargs):
        cliente = get_object_or_404(Cliente, pk=pk)
        cliente.soft_delete()

        nombre_display = (
            cliente.razon_social 
            if cliente.tipo_cliente == Cliente.TIPO_JURIDICA 
            else f"{cliente.nombre} {cliente.apellido}".strip()
        )

        messages.success(request, f"¡El cliente {nombre_display} ha sido dado de baja correctamente!")
        url_previa = request.META.get('HTTP_REFERER')
        if url_previa:
            return redirect(url_previa)
        return redirect('home')


class ClienteDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Cliente
    template_name = 'clientes/cliente_detail.html'
    context_object_name = 'cliente'

    def test_func(self):
        # Permiso para ver ficha de cliente
        return self.request.user.has_perm('authentication.acceder_clientes')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['usuarios_asociados'] = self.object.usuarios.all().order_by('email')
        context['form_asociar'] = AsociarUsuarioForm()
        return context


class ClienteAsociarUsuarioView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        # Permiso para asociar usuarios a cliente
        return self.request.user.has_perm('authentication.acceder_clientes')

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
    def test_func(self):
        # Permiso para desasociar usuarios de cliente
        return self.request.user.has_perm('authentication.acceder_clientes')

    def post(self, request, pk, user_id, *args, **kwargs):
        cliente = get_object_or_404(Cliente, pk=pk)
        usuario = get_object_or_404(User, pk=user_id)

        cliente.usuarios.remove(usuario)
        messages.success(request, f"Se revocó el acceso de {usuario.email} para este cliente.")
        return redirect('cliente_detail', pk=cliente.pk)


class SeleccionarClienteActivoView(LoginRequiredMixin, View):
    template_name = 'clientes/seleccionar_cliente.html'

    def get(self, request, *args, **kwargs):
        clientes = request.user.clientes_asociados.filter(is_active=True)

        if clientes.count() == 1:
            request.session['cliente_activo_id'] = clientes.first().pk
            return redirect('home')

        return render(request, self.template_name, {'clientes': clientes})

    def post(self, request, *args, **kwargs):
        cliente_id = request.POST.get('cliente_id')
        cliente = get_object_or_404(request.user.clientes_asociados, pk=cliente_id, is_active=True)
        request.session['cliente_activo_id'] = cliente.pk
        messages.success(request, f"Ahora estás operando en representación de {cliente}.")
        return redirect('home')