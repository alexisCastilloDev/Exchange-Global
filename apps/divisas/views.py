from decimal import Decimal, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from apps.authentication.forms import CausaBajaForm
from apps.authentication.models import HistorialBaja
from apps.divisas.forms import CotizacionForm, DivisaForm, SimulacionDivisasForm
from apps.divisas.models import Cotizacion, Divisa


class TasasVigentesListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Divisa
    template_name = 'divisas/tasas_vigentes.html'
    context_object_name = 'divisas'

    def test_func(self):
        """
        Autorización contra Keycloak: acceso para administración, analista cambiario,
        cliente o agente.
        """
        roles = self.request.session.get('keycloak_roles', [])
        return bool({'admin', 'agente', 'analista_cambiario', 'cliente'} & set(roles))

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
        return bool({'admin', 'analista_cambiario'} & set(roles))

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


class HistorialCotizacionesView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """Muestra cada cambio registrado para las tasas de una divisa."""

    model = Cotizacion
    template_name = 'divisas/historial_cotizaciones.html'
    context_object_name = 'cotizaciones'

    def test_func(self):
        roles = self.request.session.get('keycloak_roles', [])
        return bool({'admin', 'analista_cambiario'} & set(roles))

    def dispatch(self, request, *args, **kwargs):
        self.divisa = get_object_or_404(Divisa, pk=kwargs['divisa_id'])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return self.divisa.cotizaciones.select_related('usuario')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['divisa'] = self.divisa
        return context


class SimulacionDivisasView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = 'divisas/simulacion_divisas.html'

    def test_func(self):
        roles = self.request.session.get('keycloak_roles', [])
        return bool({'admin', 'agente', 'analista_cambiario', 'cliente'} & set(roles))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['divisas'] = Divisa.objects.filter(activa=True).order_by('codigo')
        context['form'] = SimulacionDivisasForm()
        context['resultado'] = None
        return context

    def post(self, request, *args, **kwargs):
        form = SimulacionDivisasForm(request.POST)
        divisas = Divisa.objects.filter(activa=True).order_by('codigo')

        if form.is_valid():
            origen = form.cleaned_data['divisa_origen']
            destino = form.cleaned_data['divisa_destino']
            monto = form.cleaned_data['monto']

            def get_cotizacion(divisa):
                if getattr(divisa, 'codigo', None) == 'PYG':
                    return type('CotizacionPYG', (), {'tasa_compra': Decimal('1.00'), 'tasa_venta': Decimal('1.00')})()
                cotizacion = divisa.ultima_cotizacion
                if not cotizacion:
                    raise ValueError(f'La divisa {divisa.codigo} no tiene tasa disponible.')
                return cotizacion

            try:
                cotizacion_origen = get_cotizacion(origen)
                cotizacion_destino = get_cotizacion(destino)
            except ValueError as exc:
                messages.error(request, str(exc))
                return self.render_to_response({'form': form, 'divisas': divisas, 'resultado': None})

            tasa_origen = Decimal(str(cotizacion_origen.tasa_venta))
            tasa_destino = Decimal(str(cotizacion_destino.tasa_compra))
            tasa_aplicada = tasa_origen / tasa_destino
            monto_final = (monto * tasa_aplicada).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            context = {
                'form': form,
                'divisas': divisas,
                'resultado': {
                    'monto_origen': monto,
                    'divisa_origen': origen,
                    'divisa_destino': destino,
                    'tasa_aplicada': tasa_aplicada,
                    'monto_final': monto_final,
                },
            }
            return self.render_to_response(context)

        return self.render_to_response({'form': form, 'divisas': divisas, 'resultado': None})


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


class DivisaSoftDeleteView(AdminDivisasMixin, View):
    def get(self, request, pk, *args, **kwargs):
        divisa = get_object_or_404(Divisa, pk=pk)
        return render(
            request,
            'bajas/confirmar_baja.html',
            {
                'form': CausaBajaForm(),
                'recurso_tipo': 'divisa',
                'recurso_nombre': divisa,
                'cancelar_url': reverse_lazy('divisas:lista_divisas'),
            },
        )

    def post(self, request, pk, *args, **kwargs):
        divisa = get_object_or_404(Divisa, pk=pk)
        form = CausaBajaForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                'bajas/confirmar_baja.html',
                {
                    'form': form,
                    'recurso_tipo': 'divisa',
                    'recurso_nombre': divisa,
                    'cancelar_url': reverse_lazy('divisas:lista_divisas'),
                },
            )
        if not divisa.activa:
            messages.info(request, 'La divisa ya se encontraba inactiva.')
            return redirect('divisas:lista_divisas')
        divisa.activa = False
        divisa.save(update_fields=['activa'])
        HistorialBaja.objects.create(
            tipo_recurso=HistorialBaja.TIPO_DIVISA,
            recurso_id=divisa.pk,
            recurso_nombre=str(divisa),
            causa=form.cleaned_data['causa'],
            realizado_por=request.user,
        )
        messages.success(request, f'La divisa {divisa.codigo} fue dada de baja.')
        return redirect('divisas:lista_divisas')


class DivisaHistorialBajasView(AdminDivisasMixin, ListView):
    model = HistorialBaja
    template_name = 'bajas/historial_bajas.html'
    context_object_name = 'registros'

    def get_queryset(self):
        return HistorialBaja.objects.filter(
            tipo_recurso=HistorialBaja.TIPO_DIVISA
        ).select_related('realizado_por')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = 'Historial de bajas de divisas'
        context['volver_url'] = reverse_lazy('divisas:lista_divisas')
        return context
