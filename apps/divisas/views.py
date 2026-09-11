from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView

from apps.divisas.forms import CotizacionForm, DivisaForm
from apps.divisas.models import Cotizacion, Divisa


class TasasVigentesListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Divisa
    template_name = 'divisas/tasas_vigentes.html'
    context_object_name = 'divisas'

    def test_func(self):
        """
        Autorización 100% contra Keycloak (sesión), sin auth.Group.
        Acceso para 'admin' o para el rol de negocio 'agente'.
        AJUSTA 'agente' si el rol real en Keycloak se llama distinto.
        """
        roles = self.request.session.get('keycloak_roles', [])
        return bool(
            {'admin', 'agente', 'analista', 'analista_cambiario'}
            & set(roles)
        )

    def get_queryset(self):
        """
        Criterio de Aceptación 4: Las divisas inactivas no se muestran.
        """
        return Divisa.objects.filter(activa=True)


class ActualizarCotizacionView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Cotizacion
    form_class = CotizacionForm
    template_name = 'divisas/cotizacion_form.html'
    context_object_name = 'cotizacion'
    success_url = reverse_lazy('divisas:tasas_vigentes')

    def test_func(self):
        roles = self.request.session.get('keycloak_roles', [])
        return bool({'admin', 'analista', 'analista_cambiario'} & set(roles))

    def get_object(self, queryset=None):
        divisa = get_object_or_404(
            Divisa,
            pk=self.kwargs['divisa_id'],
            activa=True,
        )
        return Cotizacion(divisa=divisa)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['divisa'] = self.object.divisa
        return context

    def form_valid(self, form):
        form.instance.divisa = self.object.divisa
        form.instance.usuario = self.request.user
        super().form_valid(form)
        messages.success(
            self.request,
            f'Cotización de {self.object.divisa.codigo} actualizada correctamente.',
        )
        return redirect('divisas:tasas_vigentes')


class AdminDivisasMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Control de acceso: solo administradores (rol 'admin' en Keycloak)."""
    def test_func(self):
        roles = self.request.session.get('keycloak_roles', [])
        return 'admin' in roles


class DivisaListView(AdminDivisasMixin, ListView):
    model = Divisa
    template_name = 'divisas/divisa_list.html'
    context_object_name = 'divisas'
    ordering = 'codigo'


class DivisaCreateView(AdminDivisasMixin, CreateView):
    model = Divisa
    form_class = DivisaForm
    template_name = 'divisas/divisa_form.html'
    success_url = reverse_lazy('divisas:lista_divisas')

    def form_valid(self, form):
        form.instance.activa = True
        return super().form_valid(form)


class DivisaUpdateView(AdminDivisasMixin, UpdateView):
    model = Divisa
    form_class = DivisaForm
    template_name = 'divisas/divisa_form.html'
    success_url = reverse_lazy('divisas:lista_divisas')