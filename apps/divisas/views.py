"""Vistas para consultar, administrar y simular cotizaciones de divisas."""

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from apps.authentication.forms import CausaBajaForm
from apps.authentication.models import HistorialBaja
from apps.divisas.forms import CalculoOperacionForm, CotizacionForm, DivisaForm, SimulacionDivisasForm
from apps.divisas.models import CalculoOperacion, Cotizacion, Divisa


def _obtener_cotizacion_operacion(divisa):
    """Obtiene la cotización vigente de una divisa o la tasa unitaria de PYG."""
    if divisa.codigo == 'PYG':
        return Decimal('1.00'), None
    cotizacion = divisa.ultima_cotizacion
    if not cotizacion:
        raise ValueError(f'La divisa {divisa.codigo} no tiene cotización disponible.')
    return cotizacion.tasa_compra, cotizacion


def _calcular_importe_operacion(tipo, monto, tasa_compra, tasa_venta):
    """Calcula tasa, comisión y total según compra o venta de divisa."""
    tasa_aplicada = tasa_venta if tipo == CalculoOperacion.TIPO_COMPRA else tasa_compra
    bruto = (monto * tasa_aplicada).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    porcentaje = Decimal(str(settings.COMISION_OPERACION_PORCENTAJE))
    comision = (bruto * porcentaje / Decimal('100')).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    monto_final = bruto + comision if tipo == CalculoOperacion.TIPO_COMPRA else bruto - comision
    return tasa_aplicada, porcentaje, comision, monto_final


class TasasVigentesListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """Lista las tasas de las divisas activas para roles operativos."""
    model = Divisa
    template_name = 'divisas/tasas_vigentes.html'
    context_object_name = 'divisas'

    def test_func(self):
        """
        Autorización contra Keycloak: acceso para administración, analista cambiario,
        cliente.
        """
        roles = self.request.session.get('keycloak_roles', [])
        return bool({'admin', 'analista_cambiario', 'cliente'} & set(roles))

    def get_queryset(self):
        """
        Criterio de Aceptación 4: Las divisas inactivas no se muestran.
        """
        return Divisa.objects.filter(activa=True)


class ActualizarCotizacionView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """Permite a roles autorizados registrar una nueva cotización."""
    model = Cotizacion
    form_class = CotizacionForm
    template_name = 'divisas/cotizacion_form.html'
    context_object_name = 'cotizacion'
    success_url = reverse_lazy('divisas:tasas_vigentes')

    def test_func(self):
        """Comprueba que el usuario sea administrador o analista cambiario."""
        roles = self.request.session.get('keycloak_roles', [])
        return bool({'admin', 'analista_cambiario'} & set(roles))

    def get_object(self, queryset=None):
        """Construye una cotización nueva para la divisa solicitada."""
        divisa = get_object_or_404(
            Divisa,
            pk=self.kwargs['divisa_id'],
            activa=True,
        )
        return Cotizacion(divisa=divisa)

    def get_context_data(self, **kwargs):
        """Agrega la divisa asociada al contexto del formulario."""
        context = super().get_context_data(**kwargs)
        context['divisa'] = self.object.divisa
        return context

    def form_valid(self, form):
        """Asigna divisa y usuario, guarda la tasa y muestra confirmación."""
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
        """Autoriza la consulta del historial a administración y análisis."""
        roles = self.request.session.get('keycloak_roles', [])
        return bool({'admin', 'analista_cambiario'} & set(roles))

    def dispatch(self, request, *args, **kwargs):
        """Resuelve la divisa antes de despachar la solicitud."""
        self.divisa = get_object_or_404(Divisa, pk=kwargs['divisa_id'])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        """Devuelve las cotizaciones históricas de la divisa seleccionada."""
        return self.divisa.cotizaciones.select_related('usuario')

    def get_context_data(self, **kwargs):
        """Agrega la divisa consultada al contexto de la plantilla."""
        context = super().get_context_data(**kwargs)
        context['divisa'] = self.divisa
        return context


class SimulacionDivisasView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Calcula conversiones usando las tasas vigentes disponibles."""
    template_name = 'divisas/simulacion_divisas.html'

    def test_func(self):
        """Permite simular a los roles que operan con divisas."""
        roles = self.request.session.get('keycloak_roles', [])
        return bool({'admin', 'analista_cambiario', 'cliente'} & set(roles))

    def get_context_data(self, **kwargs):
        """Prepara el formulario y las divisas activas para la pantalla."""
        context = super().get_context_data(**kwargs)
        context['divisas'] = Divisa.objects.filter(activa=True).order_by('codigo')
        context['form'] = SimulacionDivisasForm()
        context['resultado'] = None
        return context

    def post(self, request, *args, **kwargs):
        """Valida una conversión y devuelve el monto calculado."""
        form = SimulacionDivisasForm(request.POST)
        divisas = Divisa.objects.filter(activa=True).order_by('codigo')

        if form.is_valid():
            origen = form.cleaned_data['divisa_origen']
            destino = form.cleaned_data['divisa_destino']
            monto = form.cleaned_data['monto']

            def get_cotizacion(divisa):
                """Obtiene la cotización vigente o la tasa unitaria de PYG."""
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


class CalculoOperacionView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Calcula el importe de una compra o venta y lo conserva hasta vencer."""

    template_name = 'divisas/calculo_operacion.html'

    def test_func(self):
        """Permite calcular a los roles que pueden operar con divisas."""
        roles = self.request.session.get('keycloak_roles', [])
        return bool({'admin', 'analista_cambiario', 'cliente'} & set(roles))

    def _tipo(self):
        """Devuelve el tipo normalizado recibido en la URL."""
        return self.kwargs['tipo'].upper()

    def _contexto(self, form, calculo=None):
        """Construye el contexto común de la pantalla de operación."""
        return {
            'form': form,
            'tipo_operacion': self._tipo(),
            'calculo': calculo,
            'vigencia_segundos': settings.CALCULO_OPERACION_VIGENCIA_SEGUNDOS,
        }

    def get_context_data(self, **kwargs):
        """Prepara el formulario para compra o venta."""
        context = super().get_context_data(**kwargs)
        context.update(self._contexto(CalculoOperacionForm(tipo=self._tipo())))
        return context

    def post(self, request, *args, **kwargs):
        """Valida datos, obtiene la tasa vigente y guarda el cálculo."""
        tipo = self._tipo()
        form = CalculoOperacionForm(request.POST, tipo=tipo)
        if not form.is_valid():
            return self.render_to_response(self._contexto(form))

        divisa = form.cleaned_data['divisa']
        try:
            tasa_compra, cotizacion = _obtener_cotizacion_operacion(divisa)
        except ValueError as exc:
            form.add_error('divisa', str(exc))
            messages.error(request, str(exc))
            return self.render_to_response(self._contexto(form))

        tasa_venta = cotizacion.tasa_venta if cotizacion else tasa_compra
        tasa_aplicada, porcentaje, comision, monto_final = _calcular_importe_operacion(
            tipo, form.cleaned_data['monto'], tasa_compra, tasa_venta
        )
        ahora = timezone.now()
        calculo = CalculoOperacion.objects.create(
            usuario=request.user,
            tipo=tipo,
            divisa=divisa if divisa.pk else None,
            codigo_divisa=divisa.codigo,
            monto_origen=form.cleaned_data['monto'],
            tasa_aplicada=tasa_aplicada,
            comision_porcentaje=porcentaje,
            comision=comision,
            monto_final=monto_final,
            vence_en=ahora + timedelta(seconds=settings.CALCULO_OPERACION_VIGENCIA_SEGUNDOS),
        )
        return self.render_to_response(self._contexto(form, calculo))


def confirmar_calculo_operacion_view(request, calculo_id):
    """Confirma un cálculo vigente o exige recalcular si ya venció."""
    if request.method != 'POST':
        return redirect('home')
    calculo = get_object_or_404(CalculoOperacion, pk=calculo_id, usuario=request.user)
    if calculo.esta_vencido:
        messages.error(
            request,
            'El cálculo venció por cambio de cotización. Debe recalcular la operación antes de continuar.',
        )
        return redirect('divisas:operar', tipo=calculo.tipo.lower())
    if calculo.confirmado_en:
        messages.info(request, 'Este cálculo ya fue confirmado.')
        return redirect('divisas:operar', tipo=calculo.tipo.lower())
    calculo.confirmado_en = timezone.now()
    calculo.save(update_fields=['confirmado_en'])
    messages.success(request, 'El cálculo fue confirmado con la tasa vigente.')
    return redirect('divisas:operar', tipo=calculo.tipo.lower())


class AdminDivisasMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Control de acceso: solo administradores (rol 'admin' en Keycloak)."""
    def test_func(self):
        """Comprueba que el rol de administrador esté en la sesión."""
        roles = self.request.session.get('keycloak_roles', [])
        return 'admin' in roles


class DivisaListView(AdminDivisasMixin, ListView):
    """Lista el catálogo administrativo de divisas."""
    model = Divisa
    template_name = 'divisas/divisa_list.html'
    context_object_name = 'divisas'
    ordering = 'codigo'


class DivisaCreateView(AdminDivisasMixin, CreateView):
    """Permite registrar una divisa nueva en el catálogo."""
    model = Divisa
    form_class = DivisaForm
    template_name = 'divisas/divisa_form.html'
    success_url = reverse_lazy('divisas:lista_divisas')

    def form_valid(self, form):
        """Marca como activa la divisa recién creada."""
        form.instance.activa = True
        return super().form_valid(form)


class DivisaUpdateView(AdminDivisasMixin, UpdateView):
    """Permite editar los datos de una divisa existente."""
    model = Divisa
    form_class = DivisaForm
    template_name = 'divisas/divisa_form.html'
    success_url = reverse_lazy('divisas:lista_divisas')


class DivisaSoftDeleteView(AdminDivisasMixin, View):
    """Confirma y ejecuta la baja lógica de una divisa."""

    def get(self, request, pk, *args, **kwargs):
        """Muestra el formulario de confirmación de baja."""
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
        """Valida la causa y registra la baja lógica de la divisa."""
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
    """Lista las bajas lógicas registradas para divisas."""
    model = HistorialBaja
    template_name = 'bajas/historial_bajas.html'
    context_object_name = 'registros'

    def get_queryset(self):
        """Devuelve el historial de bajas de divisas con su autor."""
        return HistorialBaja.objects.filter(
            tipo_recurso=HistorialBaja.TIPO_DIVISA
        ).select_related('realizado_por')

    def get_context_data(self, **kwargs):
        """Agrega título y URL de retorno al contexto de la plantilla."""
        context = super().get_context_data(**kwargs)
        context['titulo'] = 'Historial de bajas de divisas'
        context['volver_url'] = reverse_lazy('divisas:lista_divisas')
        return context
