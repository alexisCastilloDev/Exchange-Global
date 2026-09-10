"""
Módulo de vistas para la aplicación de clientes.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import AsociarUsuarioClienteForm, ClienteForm
from .models import Cliente


@login_required
def seleccionar_cliente_view(request):
    """Vista para que el usuario elija con qué cliente operará."""
    clientes = request.user.clientes.filter(is_active=True)

    # Si solo tiene 1 cliente, lo selecciona automáticamente y redirige
    if clientes.count() == 1:
        request.session['cliente_activo_id'] = clientes.first().pk
        request.session.modified = True
        return redirect('home')

    if request.method == 'POST':
        cliente_id = request.POST.get('cliente_id')
        cliente = get_object_or_404(clientes, pk=cliente_id)

        # Guarda la selección en la sesión HTTP
        request.session['cliente_activo_id'] = cliente.pk
        request.session.modified = True
        messages.success(request, f'Operando en nombre de: {cliente}')

        next_url = request.GET.get('next') or reverse('home')
        return redirect(next_url)

    return render(
        request, 'clientes/seleccionar_cliente.html', {'clientes': clientes}
    )


@login_required
def cambiar_cliente_view(request, cliente_id):
    """Permite cambiar de cliente activo en cualquier momento sin cerrar sesión."""
    cliente = get_object_or_404(
        request.user.clientes.filter(is_active=True), pk=cliente_id
    )

    # Asigna y marca la sesión como modificada explícitamente para asegurar la persistencia en el test client
    request.session['cliente_activo_id'] = cliente.pk
    request.session.modified = True
    request.session.save()

    messages.info(request, f'Cambiaste al cliente: {cliente}')

    # Si hay referer se envía allí, de lo contrario se usa la vista 'home'
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)

    return redirect('home')


class PanelAdminView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Cliente
    template_name = 'panel_admin.html'
    context_object_name = 'clientes'
    paginate_by = 10

    def get_queryset(self):
        incluir_inactivos = self.request.GET.get('incluir_inactivos') == '1'
        queryset = (
            Cliente.objects.all() if incluir_inactivos else Cliente.activos.all()
        )

        segmento_seleccionado = self.request.GET.get('segmento')
        if segmento_seleccionado:
            queryset = queryset.filter(segmento=segmento_seleccionado)

        busqueda = self.request.GET.get('q', '').strip()
        if busqueda:
            queryset = queryset.filter(
                Q(nombre__icontains=busqueda)
                | Q(apellido__icontains=busqueda)
                | Q(razon_social__icontains=busqueda)
                | Q(identificador__icontains=busqueda)
            )

        return queryset.order_by('pk').prefetch_related('usuarios')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['segmentos'] = Cliente.SEGMENTO_CHOICES
        context['segmento_actual'] = self.request.GET.get('segmento', '')
        context['busqueda'] = self.request.GET.get('q', '').strip()
        context['incluir_inactivos'] = (
            self.request.GET.get('incluir_inactivos') == '1'
        )
        return context

    def test_func(self):
        user = self.request.user
        return user.is_staff or user.is_superuser

    def handle_no_permission(self):
        messages.error(
            self.request,
            "No tienes los permisos necesarios para acceder a este panel.",
        )
        return redirect('home')


class ClienteDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Cliente
    template_name = 'clientes/cliente_detail.html'
    context_object_name = 'cliente'

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

    def handle_no_permission(self):
        messages.error(
            self.request,
            "No tienes los permisos necesarios para acceder a esta ficha.",
        )
        return redirect('home')


class ClienteCreateView(
    LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, CreateView
):
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


class ClienteUpdateView(
    LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, UpdateView
):
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


class AsociarUsuariosClienteView(
    LoginRequiredMixin, UserPassesTestMixin, View
):
    """
    Módulo independiente para asociar/desasociar usuarios del sistema a un cliente.
    """

    template_name = 'clientes/asociar_usuarios.html'

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

    def get(self, request, pk, *args, **kwargs):
        cliente = get_object_or_404(Cliente, pk=pk)
        # Pre-seleccionar los usuarios que ya están vinculados
        form = AsociarUsuarioClienteForm(
            initial={'usuarios': cliente.usuarios.all()}
        )
        return render(
            request, self.template_name, {'form': form, 'cliente': cliente}
        )

    def post(self, request, pk, *args, **kwargs):
        cliente = get_object_or_404(Cliente, pk=pk)
        form = AsociarUsuarioClienteForm(request.POST)
        if form.is_valid():
            nuevos_usuarios = form.cleaned_data['usuarios']
            # Actualiza la relación Muchos a Muchos
            cliente.usuarios.set(nuevos_usuarios)
            messages.success(
                request,
                f"Usuarios vinculados correctamente al cliente {cliente}.",
            )
            return redirect('home')
        return render(
            request, self.template_name, {'form': form, 'cliente': cliente}
        )


class ClienteSoftDeleteView(LoginRequiredMixin, UserPassesTestMixin, View):

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

    def post(self, request, pk, *args, **kwargs):
        cliente = get_object_or_404(Cliente, pk=pk)
        cliente.soft_delete()
        nombre_display = (
            cliente.razon_social
            if cliente.tipo_cliente == Cliente.TIPO_JURIDICA
            else f"{cliente.nombre} {cliente.apellido}".strip()
        )
        messages.success(
            request,
            f"¡El cliente {nombre_display} ha sido dado de baja correctamente!",
        )
        url_previa = request.META.get('HTTP_REFERER')
        return redirect(url_previa) if url_previa else redirect('home')