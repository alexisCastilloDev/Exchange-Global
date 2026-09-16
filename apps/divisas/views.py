"""Vistas para consultar, administrar y simular cotizaciones de divisas."""

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from apps.authentication.forms import CausaBajaForm
from apps.authentication.models import HistorialBaja
from apps.clientes.models import Cliente
from apps.divisas.forms import (
    CalculoOperacionForm,
    ConfiguracionComisionForm,
    CotizacionForm,
    DivisaForm,
    SimulacionDivisasForm,
    TriangulacionForm,
)
from apps.divisas.models import (
    CalculoOperacion,
    CalculoTriangulacion,
    ConfiguracionComision,
    Cotizacion,
    Divisa,
)


def _obtener_cotizacion_operacion(divisa):
    """Obtiene la cotización vigente de una divisa o la tasa unitaria de PYG."""
    if divisa.codigo == 'PYG':
        return Decimal('1.00'), None
    cotizacion = divisa.ultima_cotizacion
    if not cotizacion:
        raise ValueError(f'La divisa {divisa.codigo} no tiene cotización disponible.')
    return cotizacion.tasa_compra, cotizacion


def _obtener_cotizacion_vigente(divisa):
    """Obtiene la cotización vigente de una divisa extranjera o lanza un error."""
    cotizacion = divisa.ultima_cotizacion
    if not cotizacion:
        raise ValueError(f'La divisa {divisa.codigo} no tiene cotización disponible.')
    return cotizacion


def _calcular_importe_operacion(tipo, monto, tasa_compra, tasa_venta, cliente=None):
    """Calcula tasa, comisión y total según compra o venta de divisa.

    La comisión aplicada depende del cliente que opera: su comisión
    personalizada, si tiene una, o la de su segmento (ver
    ``ConfiguracionComision.porcentaje_para``).
    """
    tasa_aplicada = tasa_venta if tipo == CalculoOperacion.TIPO_COMPRA else tasa_compra
    bruto = (monto * tasa_aplicada).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    porcentaje = ConfiguracionComision.porcentaje_para(cliente)
    comision = (bruto * porcentaje / Decimal('100')).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    monto_final = bruto + comision if tipo == CalculoOperacion.TIPO_COMPRA else bruto - comision
    return tasa_aplicada, porcentaje, comision, monto_final


def _calcular_triangulacion(monto, tasa_compra_origen, tasa_venta_destino, cliente=None):
    """Convierte un monto entre divisas extranjeras triangulando por PYG.

    Paso A: el monto origen se convierte a guaraníes con la tasa de compra
    vigente de la divisa origen. Paso B: ese equivalente en guaraníes se
    convierte a la divisa destino con la tasa de venta vigente de la divisa
    destino. La comisión (personalizada, por segmento o por defecto, ver
    ``ConfiguracionComision.porcentaje_para``) se descuenta del monto bruto
    obtenido en el paso B.
    """
    monto_equivalente_pyg = (monto * tasa_compra_origen).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    tasa_cruzada = (tasa_compra_origen / tasa_venta_destino).quantize(
        Decimal('0.000001'), rounding=ROUND_HALF_UP
    )
    bruto = ((monto * tasa_compra_origen) / tasa_venta_destino).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    porcentaje = ConfiguracionComision.porcentaje_para(cliente)
    comision = (bruto * porcentaje / Decimal('100')).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    monto_final = bruto - comision
    return monto_equivalente_pyg, tasa_cruzada, porcentaje, comision, monto_final


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


class ConfiguracionComisionListView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Lista el porcentaje de comisión vigente para cada segmento de clientes."""
    template_name = 'divisas/comision_list.html'

    def test_func(self):
        """Permite configurar comisiones a administración y análisis cambiario."""
        roles = self.request.session.get('keycloak_roles', [])
        return bool({'admin', 'analista_cambiario'} & set(roles))

    def get_context_data(self, **kwargs):
        """Combina cada segmento con su comisión configurada o el valor por defecto."""
        context = super().get_context_data(**kwargs)
        configuraciones = {
            configuracion.segmento: configuracion
            for configuracion in ConfiguracionComision.objects.all()
        }
        context['filas'] = [
            {
                'segmento': codigo,
                'nombre': nombre,
                'configuracion': configuraciones.get(codigo),
                'porcentaje_vigente': (
                    configuraciones[codigo].porcentaje
                    if codigo in configuraciones
                    else settings.COMISION_OPERACION_PORCENTAJE
                ),
            }
            for codigo, nombre in Cliente.SEGMENTO_CHOICES
        ]
        context['comision_default'] = settings.COMISION_OPERACION_PORCENTAJE
        return context


class ActualizarComisionView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """Permite crear o actualizar la comisión configurada para un segmento."""
    model = ConfiguracionComision
    form_class = ConfiguracionComisionForm
    template_name = 'divisas/comision_form.html'
    success_url = reverse_lazy('divisas:comisiones')

    def test_func(self):
        """Permite configurar comisiones a administración y análisis cambiario."""
        roles = self.request.session.get('keycloak_roles', [])
        return bool({'admin', 'analista_cambiario'} & set(roles))

    def get_object(self, queryset=None):
        """Recupera la configuración del segmento o construye una nueva."""
        segmento = self.kwargs['segmento']
        if segmento not in dict(Cliente.SEGMENTO_CHOICES):
            raise Http404('El segmento solicitado no existe.')
        return ConfiguracionComision.objects.filter(segmento=segmento).first() or ConfiguracionComision(
            segmento=segmento, porcentaje=settings.COMISION_OPERACION_PORCENTAJE
        )

    def get_context_data(self, **kwargs):
        """Agrega el nombre legible del segmento al contexto del formulario."""
        context = super().get_context_data(**kwargs)
        context['segmento_nombre'] = dict(Cliente.SEGMENTO_CHOICES).get(self.object.segmento)
        return context

    def form_valid(self, form):
        """Asigna el segmento y el usuario responsable antes de guardar."""
        form.instance.segmento = self.object.segmento
        form.instance.actualizado_por = self.request.user
        super().form_valid(form)
        messages.success(
            self.request,
            f'Comisión de {self.object.get_segmento_display()} actualizada correctamente.',
        )
        return redirect('divisas:comisiones')


class SimulacionDivisasView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Simula una compra, venta o cambio de divisas sin registrar la operación."""
    template_name = 'divisas/simulacion_divisas.html'

    def test_func(self):
        """Permite simular a los roles que operan con divisas."""
        roles = self.request.session.get('keycloak_roles', [])
        return bool({'admin', 'analista_cambiario', 'cliente'} & set(roles))

    def get_context_data(self, **kwargs):
        """Prepara el formulario de simulación."""
        context = super().get_context_data(**kwargs)
        context['form'] = SimulacionDivisasForm()
        context['resultado'] = None
        return context

    def post(self, request, *args, **kwargs):
        """Valida los datos y simula la compra, venta o cambio solicitado."""
        form = SimulacionDivisasForm(request.POST)
        if not form.is_valid():
            return self.render_to_response({'form': form, 'resultado': None})

        tipo = form.cleaned_data['tipo']
        monto = form.cleaned_data['monto']
        cliente_activo = getattr(request, 'cliente_activo', None)

        if tipo == SimulacionDivisasForm.TIPO_CAMBIO:
            origen = form.cleaned_data['divisa_origen']
            destino = form.cleaned_data['divisa_destino']
            try:
                cotizacion_origen = _obtener_cotizacion_vigente(origen)
                cotizacion_destino = _obtener_cotizacion_vigente(destino)
            except ValueError as exc:
                messages.error(request, str(exc))
                return self.render_to_response({'form': form, 'resultado': None})

            monto_equivalente_pyg, tasa_cruzada, porcentaje, comision, monto_final = _calcular_triangulacion(
                monto, cotizacion_origen.tasa_compra, cotizacion_destino.tasa_venta, cliente_activo
            )
            resultado = {
                'tipo': tipo,
                'monto_origen': monto,
                'divisa_origen': origen,
                'divisa_destino': destino,
                'tasa_compra_aplicada': cotizacion_origen.tasa_compra,
                'tasa_venta_aplicada': cotizacion_destino.tasa_venta,
                'tasa_aplicada': tasa_cruzada,
                'monto_equivalente_pyg': monto_equivalente_pyg,
                'comision_porcentaje': porcentaje,
                'comision': comision,
                'monto_final': monto_final,
            }
        else:
            divisa = form.cleaned_data['divisa']
            try:
                cotizacion = _obtener_cotizacion_vigente(divisa)
            except ValueError as exc:
                messages.error(request, str(exc))
                return self.render_to_response({'form': form, 'resultado': None})

            tasa_aplicada, porcentaje, comision, monto_final = _calcular_importe_operacion(
                tipo, monto, cotizacion.tasa_compra, cotizacion.tasa_venta, cliente_activo
            )
            resultado = {
                'tipo': tipo,
                'monto_origen': monto,
                'divisa_origen': divisa,
                'divisa_destino': None,
                'tasa_compra_aplicada': None,
                'tasa_venta_aplicada': None,
                'tasa_aplicada': tasa_aplicada,
                'monto_equivalente_pyg': None,
                'comision_porcentaje': porcentaje,
                'comision': comision,
                'monto_final': monto_final,
            }

        return self.render_to_response({'form': form, 'resultado': resultado})


class CalculoOperacionView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Calcula el importe de una compra o venta y lo conserva hasta vencer."""

    template_name = 'divisas/calculo_operacion.html'

    def test_func(self):
        """Permite calcular a los roles que pueden operar con divisas."""
        roles = self.request.session.get('keycloak_roles', [])
        return (
            'cliente' in roles
            and not self.request.user.is_staff
            and self.request.user.clientes.filter(is_active=True).exists()
        )

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
        cliente_activo = getattr(request, 'cliente_activo', None)
        tasa_aplicada, porcentaje, comision, monto_final = _calcular_importe_operacion(
            tipo, form.cleaned_data['monto'], tasa_compra, tasa_venta, cliente_activo
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


class TriangulacionOperacionView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Calcula el importe de un cambio entre dos divisas extranjeras triangulando por PYG."""

    template_name = 'divisas/triangulacion.html'

    def test_func(self):
        """Permite triangular a los mismos roles habilitados para operar."""
        roles = self.request.session.get('keycloak_roles', [])
        return (
            'cliente' in roles
            and not self.request.user.is_staff
            and self.request.user.clientes.filter(is_active=True).exists()
        )

    def _contexto(self, form, calculo=None):
        """Construye el contexto común de la pantalla de triangulación."""
        return {
            'form': form,
            'calculo': calculo,
            'vigencia_segundos': settings.CALCULO_OPERACION_VIGENCIA_SEGUNDOS,
        }

    def get_context_data(self, **kwargs):
        """Prepara el formulario de cambio entre divisas extranjeras."""
        context = super().get_context_data(**kwargs)
        context.update(self._contexto(TriangulacionForm()))
        return context

    def post(self, request, *args, **kwargs):
        """Valida datos, verifica ambas cotizaciones y guarda el cálculo."""
        form = TriangulacionForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self._contexto(form))

        origen = form.cleaned_data['divisa_origen']
        destino = form.cleaned_data['divisa_destino']
        try:
            cotizacion_origen = _obtener_cotizacion_vigente(origen)
            cotizacion_destino = _obtener_cotizacion_vigente(destino)
        except ValueError as exc:
            messages.error(request, str(exc))
            return self.render_to_response(self._contexto(form))

        monto = form.cleaned_data['monto']
        cliente_activo = getattr(request, 'cliente_activo', None)
        monto_equivalente_pyg, tasa_cruzada, porcentaje, comision, monto_final = _calcular_triangulacion(
            monto, cotizacion_origen.tasa_compra, cotizacion_destino.tasa_venta, cliente_activo
        )
        ahora = timezone.now()
        calculo = CalculoTriangulacion.objects.create(
            usuario=request.user,
            divisa_origen=origen,
            divisa_destino=destino,
            codigo_divisa_origen=origen.codigo,
            codigo_divisa_destino=destino.codigo,
            monto_origen=monto,
            tasa_compra_aplicada=cotizacion_origen.tasa_compra,
            tasa_venta_aplicada=cotizacion_destino.tasa_venta,
            tasa_cruzada=tasa_cruzada,
            monto_equivalente_pyg=monto_equivalente_pyg,
            comision_porcentaje=porcentaje,
            comision=comision,
            monto_final=monto_final,
            vence_en=ahora + timedelta(seconds=settings.CALCULO_OPERACION_VIGENCIA_SEGUNDOS),
        )
        return self.render_to_response(self._contexto(form, calculo))


@login_required
def confirmar_triangulacion_view(request, calculo_id):
    """Confirma una triangulación vigente o exige recalcular si ya venció."""
    if request.method != 'POST':
        return redirect('home')
    roles = request.session.get('keycloak_roles', [])
    if (
        'cliente' not in roles
        or request.user.is_staff
        or not request.user.clientes.filter(is_active=True).exists()
    ):
        messages.error(request, 'Solo un cliente asociado puede confirmar una operación.')
        return redirect('home')
    calculo = get_object_or_404(CalculoTriangulacion, pk=calculo_id, usuario=request.user)
    if calculo.esta_vencido:
        messages.error(
            request,
            'El cálculo venció por cambio de cotización. Debe recalcular la operación antes de continuar.',
        )
        return redirect('divisas:triangulacion')
    if calculo.confirmado_en:
        messages.info(request, 'Este cálculo ya fue confirmado.')
        return redirect('divisas:triangulacion')
    calculo.confirmado_en = timezone.now()
    calculo.save(update_fields=['confirmado_en'])
    messages.success(request, 'El cálculo fue confirmado con la tasa vigente.')
    return redirect('divisas:triangulacion')


@login_required
def confirmar_calculo_operacion_view(request, calculo_id):
    """Confirma un cálculo vigente o exige recalcular si ya venció."""
    if request.method != 'POST':
        return redirect('home')
    roles = request.session.get('keycloak_roles', [])
    if (
        'cliente' not in roles
        or request.user.is_staff
        or not request.user.clientes.filter(is_active=True).exists()
    ):
        messages.error(request, 'Solo un cliente asociado puede confirmar una operación.')
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
