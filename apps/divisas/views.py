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
    ConfirmarCalculoOperacionForm,
    ConfirmarTriangulacionForm,
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


def _normalizar_tipo_operacion(tipo):
    """Normaliza el tipo de operación recibido por URL y valida que exista.

    Args:
        tipo (str): Tipo indicado en la ruta (por ejemplo ``venta``).

    Returns:
        str: El tipo en mayúsculas, ``COMPRA`` o ``VENTA``.

    Raises:
        Http404: Si el tipo no corresponde a una operación conocida.
    """
    tipo = tipo.upper()
    if tipo not in dict(CalculoOperacion.TIPO_CHOICES):
        raise Http404('El tipo de operación solicitado no existe.')
    return tipo


def _calcular_importe_operacion(tipo, monto, tasa_compra, tasa_venta, cliente=None):
    """Calcula tasa, comisión y total según compra o venta de divisa.

    En una compra el cliente paga con la tasa de venta de la casa más la
    comisión; en una venta recibe el monto valuado con la tasa de compra de
    la casa menos la comisión. La comisión aplicada depende del cliente que
    opera: su comisión personalizada, si tiene una, o la de su segmento (ver
    ``ConfiguracionComision.porcentaje_para``).

    Args:
        tipo (str): ``COMPRA`` o ``VENTA``.
        monto (Decimal): Monto de la divisa extranjera a operar.
        tasa_compra (Decimal): Tasa de compra vigente de la divisa.
        tasa_venta (Decimal): Tasa de venta vigente de la divisa.
        cliente (Cliente): Cliente activo que opera, si lo hay.

    Returns:
        tuple: ``(tasa_aplicada, porcentaje, comision, monto_final)``.
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


class HistorialTransaccionesView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """Lista las transacciones de compra, venta y cambio realizadas por los clientes.

    Reúne en una misma lista ordenada por fecha las compras y ventas
    (``CalculoOperacion``) y los cambios entre divisas (``CalculoTriangulacion``),
    con tipo, estado, usuario, cliente activo, divisa, monto, tasa, comisión e
    importe final de cada una.
    """

    template_name = 'divisas/historial_transacciones.html'
    context_object_name = 'transacciones'
    paginate_by = 20

    def test_func(self):
        """Autoriza la consulta a administración y análisis cambiario."""
        roles = self.request.session.get('keycloak_roles', [])
        return bool({'admin', 'analista_cambiario'} & set(roles))

    @staticmethod
    def _fila_operacion(operacion):
        """Normaliza una compra o venta para mostrarla en el historial."""
        return {
            'creado_en': operacion.creado_en,
            'tipo': operacion.get_tipo_display(),
            'estado': operacion.get_estado_display(),
            'usuario': operacion.usuario,
            'cliente': operacion.cliente,
            'divisa': operacion.codigo_divisa,
            'monto_origen': operacion.monto_origen,
            'tasa': operacion.tasa_aplicada,
            'decimales_tasa': 2,
            'comision': operacion.comision,
            'monto_final': operacion.monto_final,
            'moneda_final': 'PYG',
        }

    @staticmethod
    def _fila_cambio(cambio):
        """Normaliza un cambio entre divisas para mostrarlo en el historial."""
        return {
            'creado_en': cambio.creado_en,
            'tipo': CalculoTriangulacion.TIPO_DISPLAY,
            'estado': cambio.get_estado_display(),
            'usuario': cambio.usuario,
            'cliente': cambio.cliente,
            'divisa': f'{cambio.codigo_divisa_origen} → {cambio.codigo_divisa_destino}',
            'monto_origen': cambio.monto_origen,
            'tasa': cambio.tasa_cruzada,
            'decimales_tasa': 6,
            'comision': cambio.comision,
            'monto_final': cambio.monto_final,
            'moneda_final': cambio.codigo_divisa_destino,
        }

    def get_queryset(self):
        """Devuelve compras, ventas y cambios de todos los clientes, del más reciente al más antiguo."""
        filas = [
            self._fila_operacion(operacion)
            for operacion in CalculoOperacion.objects.select_related('usuario', 'cliente')
        ]
        filas.extend(
            self._fila_cambio(cambio)
            for cambio in CalculoTriangulacion.objects.select_related('usuario', 'cliente')
        )
        return sorted(filas, key=lambda fila: fila['creado_en'], reverse=True)


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
    """Calcula el importe de una compra o venta, como previsualización sin persistir.

    La transacción recién se crea cuando el cliente confirma (ver
    ``confirmar_calculo_operacion_view``); este cálculo es un Paso 1 efímero,
    igual que el simulador, con la diferencia de que expone los campos ocultos
    necesarios para poder confirmarlo en un segundo paso.

    En una venta (``/divisas/operar/venta/``) el importe a recibir se calcula
    con la tasa de compra vigente de la divisa, descontando la comisión del
    cliente activo (ver ``_calcular_importe_operacion``). Un monto inválido
    (negativo, cero o no numérico), una divisa inactiva o una divisa sin
    cotización vigente se rechazan con un mensaje y sin generar ningún
    resultado confirmable.
    """

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
        """Devuelve el tipo recibido en la URL, respondiendo 404 si no es compra ni venta."""
        return _normalizar_tipo_operacion(self.kwargs['tipo'])

    def _contexto(self, form, resultado=None):
        """Construye el contexto común de la pantalla de operación."""
        return {
            'form': form,
            'tipo_operacion': self._tipo(),
            'resultado': resultado,
            'vigencia_segundos': settings.CALCULO_OPERACION_VIGENCIA_SEGUNDOS,
        }

    def get_context_data(self, **kwargs):
        """Prepara el formulario para compra o venta."""
        context = super().get_context_data(**kwargs)
        context.update(self._contexto(CalculoOperacionForm(tipo=self._tipo())))
        return context

    def post(self, request, *args, **kwargs):
        """Valida datos y calcula el importe, sin crear todavía la transacción.

        Args:
            request (HttpRequest): Solicitud POST con ``divisa`` y ``monto``.

        Returns:
            HttpResponse: La pantalla de operación con el detalle del importe
            o con los errores de validación.
        """
        tipo = self._tipo()
        form = CalculoOperacionForm(request.POST, tipo=tipo)
        if not form.is_valid():
            return self.render_to_response(self._contexto(form))

        cliente_activo = getattr(request, 'cliente_activo', None)
        if cliente_activo is None:
            messages.error(request, 'No tenés un cliente activo seleccionado para operar.')
            return self.render_to_response(self._contexto(form))

        divisa = form.cleaned_data['divisa']
        try:
            tasa_compra, cotizacion = _obtener_cotizacion_operacion(divisa)
        except ValueError as exc:
            form.add_error('divisa', str(exc))
            messages.error(request, str(exc))
            return self.render_to_response(self._contexto(form))

        tasa_venta = cotizacion.tasa_venta if cotizacion else tasa_compra
        monto = form.cleaned_data['monto']
        tasa_aplicada, porcentaje, comision, monto_final = _calcular_importe_operacion(
            tipo, monto, tasa_compra, tasa_venta, cliente_activo
        )
        ahora = timezone.now()
        vence_en = ahora + timedelta(seconds=settings.CALCULO_OPERACION_VIGENCIA_SEGUNDOS)
        resultado = {
            'tipo': tipo,
            'divisa': divisa,
            'codigo_divisa': divisa.codigo,
            'monto_origen': monto,
            'tasa_aplicada': tasa_aplicada,
            'comision_porcentaje': porcentaje,
            'comision': comision,
            'monto_final': monto_final,
            'vence_en': vence_en,
            'vence_en_timestamp': vence_en.timestamp(),
            'cotizacion_id': cotizacion.pk,
        }
        return self.render_to_response(self._contexto(form, resultado))


class TriangulacionOperacionView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Calcula el importe de un cambio entre dos divisas extranjeras triangulando por PYG.

    Igual que en la compra y la venta, el cálculo es un Paso 1 efímero: no
    persiste nada y expone los campos ocultos necesarios para confirmarlo en
    un segundo paso (ver ``confirmar_triangulacion_view``), que es el que
    registra la transacción.
    """

    template_name = 'divisas/triangulacion.html'

    def test_func(self):
        """Permite triangular a los mismos roles habilitados para operar."""
        roles = self.request.session.get('keycloak_roles', [])
        return (
            'cliente' in roles
            and not self.request.user.is_staff
            and self.request.user.clientes.filter(is_active=True).exists()
        )

    def _contexto(self, form, resultado=None):
        """Construye el contexto común de la pantalla de triangulación."""
        return {
            'form': form,
            'resultado': resultado,
            'vigencia_segundos': settings.CALCULO_OPERACION_VIGENCIA_SEGUNDOS,
        }

    def get_context_data(self, **kwargs):
        """Prepara el formulario de cambio entre divisas extranjeras."""
        context = super().get_context_data(**kwargs)
        context.update(self._contexto(TriangulacionForm()))
        return context

    def post(self, request, *args, **kwargs):
        """Valida datos, verifica ambas cotizaciones y calcula el importe sin persistirlo.

        Args:
            request (HttpRequest): Solicitud POST con ``divisa_origen``,
                ``divisa_destino`` y ``monto``.

        Returns:
            HttpResponse: La pantalla del cambio con el detalle del importe o
            con los errores de validación.
        """
        form = TriangulacionForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self._contexto(form))

        cliente_activo = getattr(request, 'cliente_activo', None)
        if cliente_activo is None:
            messages.error(request, 'No tenés un cliente activo seleccionado para operar.')
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
        monto_equivalente_pyg, tasa_cruzada, porcentaje, comision, monto_final = _calcular_triangulacion(
            monto, cotizacion_origen.tasa_compra, cotizacion_destino.tasa_venta, cliente_activo
        )
        vence_en = timezone.now() + timedelta(seconds=settings.CALCULO_OPERACION_VIGENCIA_SEGUNDOS)
        resultado = {
            'divisa_origen': origen,
            'divisa_destino': destino,
            'codigo_divisa_origen': origen.codigo,
            'codigo_divisa_destino': destino.codigo,
            'monto_origen': monto,
            'tasa_compra_aplicada': cotizacion_origen.tasa_compra,
            'tasa_venta_aplicada': cotizacion_destino.tasa_venta,
            'tasa_cruzada': tasa_cruzada,
            'monto_equivalente_pyg': monto_equivalente_pyg,
            'comision_porcentaje': porcentaje,
            'comision': comision,
            'monto_final': monto_final,
            'vence_en': vence_en,
            'vence_en_timestamp': vence_en.timestamp(),
            'cotizacion_origen_id': cotizacion_origen.pk,
            'cotizacion_destino_id': cotizacion_destino.pk,
        }
        return self.render_to_response(self._contexto(form, resultado))


@login_required
def confirmar_triangulacion_view(request):
    """Revalida el cálculo previo de un cambio y recién ahí crea la transacción.

    Comprueba que no haya vencido el tiempo de reserva y que ambas
    cotizaciones sigan siendo las usadas al calcular. Si es así, recalcula el
    importe con las tasas actuales (nunca confía en los montos que viajan
    desde el navegador) y registra el cambio en estado "Pendiente de
    confirmación", a nombre del cliente activo, para que figure en el
    historial de transacciones.

    Args:
        request (HttpRequest): Solicitud POST con los campos ocultos del cálculo.

    Returns:
        HttpResponse: Redirección a la pantalla de cambio o al inicio.
    """
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

    cliente_activo = getattr(request, 'cliente_activo', None)
    if cliente_activo is None:
        messages.error(request, 'No tenés un cliente activo seleccionado para operar.')
        return redirect('divisas:triangulacion')

    mensaje_vencido = (
        'El cálculo venció por cambio de cotización. Debe recalcular la operación antes de continuar.'
    )
    form = ConfirmarTriangulacionForm(request.POST)
    if not form.is_valid():
        messages.error(request, mensaje_vencido)
        return redirect('divisas:triangulacion')

    origen = form.cleaned_data['divisa_origen']
    destino = form.cleaned_data['divisa_destino']
    monto = form.cleaned_data['monto']
    try:
        cotizacion_origen = _obtener_cotizacion_vigente(origen)
        cotizacion_destino = _obtener_cotizacion_vigente(destino)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('divisas:triangulacion')

    vencido = (
        timezone.now().timestamp() >= form.cleaned_data['vence_en_timestamp']
        or cotizacion_origen.pk != form.cleaned_data['cotizacion_origen_id']
        or cotizacion_destino.pk != form.cleaned_data['cotizacion_destino_id']
    )
    if vencido:
        messages.error(request, mensaje_vencido)
        return redirect('divisas:triangulacion')

    monto_equivalente_pyg, tasa_cruzada, porcentaje, comision, monto_final = _calcular_triangulacion(
        monto, cotizacion_origen.tasa_compra, cotizacion_destino.tasa_venta, cliente_activo
    )
    ahora = timezone.now()
    CalculoTriangulacion.objects.create(
        usuario=request.user,
        cliente=cliente_activo,
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
        estado=CalculoTriangulacion.ESTADO_PENDIENTE,
        confirmado_en=ahora,
        vence_en=ahora + timedelta(seconds=settings.CALCULO_OPERACION_VIGENCIA_SEGUNDOS),
    )
    messages.success(
        request,
        f'Cambio de {origen.codigo} a {destino.codigo} registrado. Estado: Pendiente de confirmación. '
        f'Importe a recibir: {monto_final} {destino.codigo}.',
    )
    return redirect('divisas:triangulacion')


@login_required
def confirmar_calculo_operacion_view(request, tipo):
    """Revalida el cálculo previo (Paso 1) y recién ahí crea la transacción.

    El Paso 1 ("Calcular importe") no persiste nada: viaja como campos
    ocultos. Acá se revalida que la cotización usada siga siendo la vigente y
    que no haya pasado el tiempo de reserva antes de crear el registro, ya
    directamente en estado "Pendiente de confirmación". Sirve tanto para la
    compra como para la venta de divisas; la transacción queda registrada
    con el tipo de la ruta, el cliente activo, la divisa, el monto y la fecha
    de creación.

    Args:
        request (HttpRequest): Solicitud POST con los campos ocultos del Paso 1.
        tipo (str): ``compra`` o ``venta``, según la ruta.

    Returns:
        HttpResponse: Redirección a la pantalla de operación o al inicio.

    Raises:
        Http404: Si el tipo de la ruta no es compra ni venta.
    """
    tipo = _normalizar_tipo_operacion(tipo)
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

    cliente_activo = getattr(request, 'cliente_activo', None)
    if cliente_activo is None:
        messages.error(request, 'No tenés un cliente activo seleccionado para operar.')
        return redirect('divisas:operar', tipo=tipo.lower())

    mensaje_vencido = (
        'El cálculo venció por cambio de cotización. Debe recalcular la operación antes de continuar.'
    )
    form = ConfirmarCalculoOperacionForm(request.POST)
    if not form.is_valid():
        messages.error(request, mensaje_vencido)
        return redirect('divisas:operar', tipo=tipo.lower())

    divisa = form.cleaned_data['divisa']
    monto = form.cleaned_data['monto']
    cotizacion_actual = divisa.ultima_cotizacion
    if cotizacion_actual is None:
        messages.error(request, f'La divisa {divisa.codigo} no tiene cotización disponible.')
        return redirect('divisas:operar', tipo=tipo.lower())
    vencido = (
        timezone.now().timestamp() >= form.cleaned_data['vence_en_timestamp']
        or cotizacion_actual.pk != form.cleaned_data['cotizacion_id']
    )
    if vencido:
        messages.error(request, mensaje_vencido)
        return redirect('divisas:operar', tipo=tipo.lower())

    tasa_aplicada, porcentaje, comision, monto_final = _calcular_importe_operacion(
        tipo, monto, cotizacion_actual.tasa_compra, cotizacion_actual.tasa_venta, cliente_activo
    )
    ahora = timezone.now()
    CalculoOperacion.objects.create(
        usuario=request.user,
        cliente=cliente_activo,
        tipo=tipo,
        divisa=divisa,
        codigo_divisa=divisa.codigo,
        monto_origen=monto,
        tasa_aplicada=tasa_aplicada,
        comision_porcentaje=porcentaje,
        comision=comision,
        monto_final=monto_final,
        estado=CalculoOperacion.ESTADO_PENDIENTE,
        confirmado_en=ahora,
        vence_en=ahora + timedelta(seconds=settings.CALCULO_OPERACION_VIGENCIA_SEGUNDOS),
    )
    tipo_display = dict(CalculoOperacion.TIPO_CHOICES)[tipo]
    etiqueta_importe = 'a pagar' if tipo == CalculoOperacion.TIPO_COMPRA else 'a recibir'
    messages.success(
        request,
        f'{tipo_display} de {divisa.codigo} registrada. Estado: Pendiente de confirmación. '
        f'Importe {etiqueta_importe}: {monto_final} PYG.',
    )
    return redirect('divisas:operar', tipo=tipo.lower())


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
