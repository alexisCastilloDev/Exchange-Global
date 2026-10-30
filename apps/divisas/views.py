"""Vistas para consultar, administrar y simular cotizaciones de divisas."""

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from apps.authentication.forms import CausaBajaForm
from apps.authentication.models import HistorialBaja
from apps.clientes.models import Cliente, MetodoPago
from apps.divisas.casa_de_cambio import (
    DesignacionCuentaPropiaError,
    SipapComunicacionError,
    consultar_cuenta_casa_de_cambio,
    consultar_movimientos_casa_de_cambio,
    consultar_saldo_casa_de_cambio,
    designar_cuenta_casa_de_cambio,
)
from apps.divisas.entrega import reintentar_entrega
from apps.divisas.factura_electronica import (
    consultar_estado_sifen,
    descargar_kude,
    descargar_xml,
    reintentar_emision,
)
from apps.divisas.forms import (
    CalculoOperacionForm,
    ConfiguracionComisionForm,
    ConfiguracionVigenciaForm,
    ConfirmarCalculoOperacionForm,
    ConfirmarTriangulacionForm,
    CotizacionForm,
    DesignarCuentaPropiaForm,
    DivisaForm,
    PagarTransaccionForm,
    SimulacionDivisasForm,
    TriangulacionForm,
)
from apps.divisas.models import (
    CalculoOperacion,
    CalculoTriangulacion,
    ConfiguracionComision,
    ConfiguracionVigencia,
    Cotizacion,
    CuentaPropia,
    Divisa,
    DocumentoElectronico,
    NotificacionTasa,
    divisa_a_entregar,
    estados_con_pago_ya_registrado,
    moneda_a_entregar,
    moneda_a_pagar,
    monto_a_entregar,
    monto_a_pagar,
)


def _puede_pagarse(transaccion):
    """Indica si una transacción está en condiciones de iniciar un pago.

    Ver ``Pago.registrar_pago``: solo una transacción "Confirmada" puede
    pagarse. Se usa tanto para decidir si mostrar el formulario de pago
    como, al enviarlo, para rechazarlo con el mismo criterio sin depender
    únicamente de la validación que hace el propio ``registrar_pago``.

    Además de "Confirmada", exige que la tasa fijada al confirmar no haya
    vencido todavía (``tasa_vencida``): no tiene sentido iniciar un cobro
    nuevo (con tarjeta o por SIPAP) para una tasa que ya no es válida. Un
    pago que de todas formas llegue tarde (por ejemplo, un cobro con
    tarjeta ya iniciado antes de que venciera) nunca se pierde: queda
    registrado como "Pago fuera de plazo" (ver ``Pago.registrar_pago``).
    """
    return transaccion.estado_efectivo == transaccion.ESTADO_CONFIRMADA and not transaccion.tasa_vencida


def _verificar_saldo_casa_de_cambio(transaccion):
    """Verifica que Global Exchange tenga saldo propio suficiente para entregar esta transacción.

    Se llama al confirmar, después del chequeo de cambio de cotización
    (que tiene prioridad): no tiene sentido que el cliente pague algo
    que Global Exchange no va a poder entregarle. El saldo propio se
    lleva en esta misma base (``CuentaPropia``, espejado contra las
    transferencias reales que se mandan a sipap-sim al entregar, ver
    ``apps.divisas.entrega``), así que esto es una consulta local, sin
    red y sin depender de que sipap-sim esté arriba en este instante.

    Returns:
        str | None: ``None`` si hay saldo suficiente (se puede
        confirmar); si no, el mensaje de error con el que se cancela la
        transacción como "saldo insuficiente" (sin fondos, o esa moneda
        no tiene ninguna cuenta propia cargada todavía).
    """
    divisa = divisa_a_entregar(transaccion)
    monto = monto_a_entregar(transaccion)
    cuenta = CuentaPropia.objects.filter(divisa=divisa).first()
    if cuenta is None or cuenta.saldo < monto:
        return (
            f'Global Exchange no dispone de fondos suficientes en {divisa.codigo} para completar '
            'esta operación en este momento. La operación fue cancelada; intentá nuevamente más tarde.'
        )
    return None


def _avisar_resultado_pago_stripe(request):
    """Informa, en la pantalla de detalle, el desenlace de un pago con tarjeta.

    ``IniciarPagoStripeOperacionView``/``IniciarPagoStripeCambioView``
    (ver ``apps.divisas.pagos_stripe``) traen de vuelta al cliente a esta
    misma pantalla con ``?pago=iniciado`` o ``?pago=cancelado`` en la URL,
    según haya completado el pago en Stripe o lo haya abandonado. En
    ningún caso se tocó la transacción desde esta vista: un pago exitoso
    recién se confirma de forma asíncrona cuando llega el webhook de
    Stripe (criterio 2), así que el aviso de "iniciado" es deliberadamente
    tentativo en vez de afirmar que ya está pagada.
    """
    resultado = request.GET.get('pago')
    if resultado == 'iniciado':
        messages.info(
            request,
            'Tu pago con tarjeta fue recibido por Stripe y se está confirmando. '
            'El estado se actualiza automáticamente apenas Stripe lo confirme.',
        )
    elif resultado == 'cancelado':
        messages.warning(
            request,
            'Cancelaste el pago con tarjeta en Stripe. La transacción sigue "Confirmada" y podés reintentarlo cuando quieras.',
        )


def _resolver_transaccion_propia(request, model, pk, url_fallback='divisas:mis_transacciones'):
    """Recupera una transacción propia, o indica por qué no se puede continuar.

    Usada por las pantallas de "Confirmar importe" (implícito, antes de
    crear la transacción), "Confirmar operación" y "Pagar": todas dependen
    de que la transacción pertenezca al cliente activo del momento. Si el
    cliente activo cambia (por ejemplo, en otra pestaña) mientras una de
    estas pantallas sigue abierta con una transacción del cliente
    *anterior*, no corresponde mostrarle al usuario una página de error de
    Django — sigue siendo su cuenta, solo cambió de contexto — así que se
    distinguen dos casos:

    - La transacción no tiene ninguna relación con el usuario autenticado
      (no es de ninguno de sus clientes): es un intento de acceso a una
      transacción ajena de verdad. Se sigue respondiendo 404, sin filtrar
      por cliente en la consulta inicial, para no revelar si el registro
      existe.
    - La transacción es de un cliente propio del usuario, pero no es el
      cliente activo en este momento: no hay nada que ocultar, así que se
      informa con un mensaje y se redirige, en vez de 404.

    Args:
        request (HttpRequest): La request actual, con ``cliente_activo``
            ya resuelto por el middleware.
        model: ``CalculoOperacion`` o ``CalculoTriangulacion``.
        pk: La clave primaria de la transacción.
        url_fallback (str): A dónde redirigir cuando la transacción es de
            otro cliente propio (no cuando es ajena: ahí no se llega a
            redirigir, se responde 404 directamente). Debe ser un nombre de
            URL sin parámetros obligatorios, porque acá no hay ningún ``pk``
            válido al que enviar (justamente el de esta transacción es el
            que no corresponde al cliente activo).

    Returns:
        tuple: ``(transaccion, None)`` si corresponde al cliente activo, o
        ``(None, HttpResponse)`` con la redirección que hay que devolver.

    Raises:
        Http404: Si la transacción no existe, o si no pertenece a ningún
            cliente asociado al usuario autenticado.
    """
    transaccion = get_object_or_404(model, pk=pk)
    if not request.user.clientes.filter(pk=transaccion.cliente_id).exists():
        raise Http404('La transacción solicitada no existe.')

    cliente_activo = getattr(request, 'cliente_activo', None)
    if cliente_activo is None:
        messages.error(request, 'No tenés un cliente activo seleccionado para operar.')
        return None, redirect('home')
    if transaccion.cliente_id != cliente_activo.id:
        messages.error(
            request,
            'Esta transacción no corresponde al cliente activo. Cambiá de cliente para continuar.',
        )
        return None, redirect(url_fallback)
    return transaccion, None


def _obtener_cotizacion_operacion(divisa):
    """Obtiene la cotización vigente de una divisa o la tasa unitaria de PYG."""
    if divisa.es_base:
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

        Tampoco PYG: es la moneda base del sistema (1:1 implícito, sin
        cotización propia que cargar ni actualizar; garantizada en el
        catálogo por las migraciones de datos
        ``apps.divisas.0014_crear_divisa_pyg`` y
        ``apps.divisas.0017_asegurar_divisa_pyg``), no una divisa
        operable más en esta pantalla, igual que ya la excluyen los
        selectores de divisa operable (``DivisaSelect``/``CalculoOperacionForm``).
        """
        return Divisa.objects.filter(activa=True).exclude(codigo=Divisa.CODIGO_BASE)


class ActualizarCotizacionView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """Permite a roles autorizados registrar una nueva cotización.

    PYG queda afuera: no tiene una cotización propia que cargar (ver
    ``TasasVigentesListView``). Se bloquea en ``get``/``post`` —en vez de
    dejar que ``get_object`` levante un 404 crudo— para avisarle a quien
    entre por una URL directa con un mensaje claro, no con una página de
    error de Django.
    """
    model = Cotizacion
    form_class = CotizacionForm
    template_name = 'divisas/cotizacion_form.html'
    context_object_name = 'cotizacion'
    success_url = reverse_lazy('divisas:tasas_vigentes')

    def test_func(self):
        """Comprueba que el usuario sea administrador o analista cambiario."""
        roles = self.request.session.get('keycloak_roles', [])
        return bool({'admin', 'analista_cambiario'} & set(roles))

    def _bloquear_si_es_pyg(self, request):
        """Devuelve una redirección si la divisa objetivo es PYG, o ``None`` si no."""
        divisa = get_object_or_404(Divisa, pk=self.kwargs['divisa_id'])
        if divisa.es_base:
            messages.error(request, 'PYG es la divisa base del sistema: no tiene una cotización para actualizar.')
            return redirect('divisas:tasas_vigentes')
        return None

    def get(self, request, *args, **kwargs):
        """Bloquea el acceso a la pantalla de actualización de PYG."""
        return self._bloquear_si_es_pyg(request) or super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """Bloquea el guardado directo (sin pasar por la pantalla) sobre PYG."""
        return self._bloquear_si_es_pyg(request) or super().post(request, *args, **kwargs)

    def get_object(self, queryset=None):
        """Construye una cotización nueva para la divisa solicitada."""
        divisa = get_object_or_404(
            Divisa.objects.exclude(codigo=Divisa.CODIGO_BASE),
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
    importe final de cada una. El estado que se muestra es el "efectivo"
    (``get_estado_efectivo_display``): si una transacción sigue "Pendiente de
    confirmación" en la base de datos pero ya venció el tiempo para
    confirmarla, se ve como "Vencida" aunque todavía nadie haya vuelto a
    abrir su pantalla de confirmación para que eso quede guardado.
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
            'estado': operacion.get_estado_efectivo_display(),
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
            'estado': cambio.get_estado_efectivo_display(),
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


class MiHistorialTransaccionesView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """Lista, paginadas y filtrables, las transacciones del cliente activo.

    Implementa la HU "Consultar el historial de transacciones": a diferencia
    de ``HistorialTransaccionesView`` (administración y análisis, todos los
    clientes), esta vista muestra únicamente las compras, ventas y cambios
    (``CalculoOperacion``/``CalculoTriangulacion``) registrados a nombre del
    ``cliente_activo`` de la sesión, con los mismos datos por fila (tipo,
    divisa, monto, tasa aplicada, estado y fecha) más comisión e importe
    final. Admite filtrar por rango de fechas de creación y por estado
    efectivo (ver ``CalculoOperacion.estado_efectivo``) mediante los
    parámetros ``fecha_desde``, ``fecha_hasta`` y ``estado`` en la URL; sin
    filtros, muestra todo el historial del cliente. Es una pantalla de solo
    consulta: no ofrece ninguna acción para confirmar, cancelar, reprocesar
    ni eliminar transacciones (ver ``DetalleTransaccionOperacionView`` y
    ``DetalleTransaccionCambioView`` para el detalle de cada una).
    """

    template_name = 'divisas/mis_transacciones.html'
    context_object_name = 'transacciones'
    paginate_by = 20

    def test_func(self):
        """Permite consultar el historial propio a los roles que pueden operar."""
        roles = self.request.session.get('keycloak_roles', [])
        return (
            'cliente' in roles
            and not self.request.user.is_staff
            and self.request.user.clientes.filter(is_active=True).exists()
        )

    def get(self, request, *args, **kwargs):
        """Exige un cliente activo seleccionado antes de listar su historial."""
        cliente_activo = getattr(request, 'cliente_activo', None)
        if cliente_activo is None:
            messages.error(request, 'No tenés un cliente activo seleccionado para operar.')
            return redirect('home')
        self.cliente_activo = cliente_activo
        return super().get(request, *args, **kwargs)

    @staticmethod
    def _fila_operacion(operacion):
        """Normaliza una compra o venta propia para mostrarla en el historial."""
        return {
            'id': operacion.pk,
            'tipo_modelo': 'operacion',
            'creado_en': operacion.creado_en,
            'tipo': operacion.get_tipo_display(),
            'estado': operacion.get_estado_efectivo_display(),
            'estado_codigo': operacion.estado_efectivo,
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
        """Normaliza un cambio entre divisas propio para mostrarlo en el historial."""
        return {
            'id': cambio.pk,
            'tipo_modelo': 'cambio',
            'creado_en': cambio.creado_en,
            'tipo': CalculoTriangulacion.TIPO_DISPLAY,
            'estado': cambio.get_estado_efectivo_display(),
            'estado_codigo': cambio.estado_efectivo,
            'divisa': f'{cambio.codigo_divisa_origen} → {cambio.codigo_divisa_destino}',
            'monto_origen': cambio.monto_origen,
            'tasa': cambio.tasa_cruzada,
            'decimales_tasa': 6,
            'comision': cambio.comision,
            'monto_final': cambio.monto_final,
            'moneda_final': cambio.codigo_divisa_destino,
        }

    @staticmethod
    def _parsear_fecha(valor):
        """Convierte ``'YYYY-MM-DD'`` a ``date``, o ``None`` si falta o no es válido."""
        if not valor:
            return None
        try:
            return datetime.strptime(valor, '%Y-%m-%d').date()
        except ValueError:
            return None

    def _filtrar(self, filas):
        """Aplica sobre las filas normalizadas los filtros de fecha y estado de la URL.

        Se filtra en Python, sobre las filas ya normalizadas, en lugar de con
        ``queryset.filter(...)``, para poder comparar contra el estado
        *efectivo* (que puede ser "Vencida" aunque el campo ``estado`` en la
        base de datos todavía no lo refleje) y contra la fecha ya convertida
        a la zona horaria local, igual que se muestran en la tabla.
        """
        estado = self.request.GET.get('estado', '').strip()
        if estado:
            filas = [fila for fila in filas if fila['estado_codigo'] == estado]

        desde = self._parsear_fecha(self.request.GET.get('fecha_desde'))
        if desde:
            filas = [fila for fila in filas if timezone.localtime(fila['creado_en']).date() >= desde]

        hasta = self._parsear_fecha(self.request.GET.get('fecha_hasta'))
        if hasta:
            filas = [fila for fila in filas if timezone.localtime(fila['creado_en']).date() <= hasta]

        return filas

    def get_queryset(self):
        """Devuelve las transacciones propias, filtradas, del más reciente al más antiguo."""
        filas = [
            self._fila_operacion(operacion)
            for operacion in CalculoOperacion.objects.filter(
                cliente=self.cliente_activo
            ).select_related('usuario')
        ]
        filas.extend(
            self._fila_cambio(cambio)
            for cambio in CalculoTriangulacion.objects.filter(
                cliente=self.cliente_activo
            ).select_related('usuario')
        )
        filas = self._filtrar(filas)
        return sorted(filas, key=lambda fila: fila['creado_en'], reverse=True)

    def get_context_data(self, **kwargs):
        """Agrega el estado de los filtros y si el cliente tiene transacciones sin filtrar."""
        context = super().get_context_data(**kwargs)
        context['tiene_transacciones'] = (
            CalculoOperacion.objects.filter(cliente=self.cliente_activo).exists()
            or CalculoTriangulacion.objects.filter(cliente=self.cliente_activo).exists()
        )
        context['estados_disponibles'] = CalculoOperacion.ESTADO_CHOICES
        context['estado_actual'] = self.request.GET.get('estado', '')
        context['fecha_desde_actual'] = self.request.GET.get('fecha_desde', '')
        context['fecha_hasta_actual'] = self.request.GET.get('fecha_hasta', '')
        querystring = self.request.GET.copy()
        querystring.pop('page', None)
        context['querystring'] = querystring.urlencode()
        return context


class MisFacturasElectronicasListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """Lista las Facturas Electrónicas emitidas para las transacciones del cliente activo.

    Simétrica a ``MiHistorialTransaccionesView``, pero para el documento
    electrónico de cada transacción (ver ``DocumentosElectronicosListView``
    para el equivalente de administración, con todos los clientes). Es de
    solo lectura: el cliente no puede reintentar ni consultar el estado
    SIFEN por su cuenta, esas son acciones de administrador.
    """

    model = DocumentoElectronico
    template_name = 'divisas/mis_facturas_electronicas.html'
    context_object_name = 'documentos'
    paginate_by = 20

    def test_func(self):
        """Permite consultar las facturas propias a los mismos roles que ``MiHistorialTransaccionesView``."""
        roles = self.request.session.get('keycloak_roles', [])
        return (
            'cliente' in roles
            and not self.request.user.is_staff
            and self.request.user.clientes.filter(is_active=True).exists()
        )

    def get(self, request, *args, **kwargs):
        """Exige un cliente activo seleccionado antes de listar sus facturas."""
        cliente_activo = getattr(request, 'cliente_activo', None)
        if cliente_activo is None:
            messages.error(request, 'No tenés un cliente activo seleccionado para operar.')
            return redirect('home')
        self.cliente_activo = cliente_activo
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        """Documentos de las transacciones (compra/venta o cambio) del cliente activo, el más reciente primero."""
        return DocumentoElectronico.objects.filter(
            Q(calculo_operacion__cliente=self.cliente_activo) | Q(calculo_triangulacion__cliente=self.cliente_activo)
        ).select_related('calculo_operacion', 'calculo_triangulacion').order_by('-creado_en')


class DetalleTransaccionOperacionView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Muestra el detalle completo, de solo lectura, de una compra o venta propia.

    Es la pantalla de detalle a la que se accede desde
    ``MiHistorialTransaccionesView`` al hacer clic en una fila. A diferencia
    de ``ConfirmarTransaccionOperacionView``, no ofrece ningún botón para
    confirmar, cancelar ni recalcular: solo expone tipo de operación, divisa,
    monto, tasa aplicada, comisión, importe final, estado y fecha, sin
    importar en qué estado se encuentre la transacción. La única acción que
    sí ofrece es "Reintentar" cuando la entrega quedó fallida (ver
    ``post``, HU "Acreditación de fondos" GE-23 y "Retiro de fondos" GE-24
    — ambas comparten el mismo mecanismo de entrega, automático apenas se
    confirma el pago, sin ninguna acción extra del cliente): el cliente no
    depende solo de un administrador para resolverlo.
    """

    def test_func(self):
        """Permite consultar el detalle solo a los roles que pueden operar."""
        roles = self.request.session.get('keycloak_roles', [])
        return (
            'cliente' in roles
            and not self.request.user.is_staff
            and self.request.user.clientes.filter(is_active=True).exists()
        )

    def get(self, request, *args, **kwargs):
        """Recupera la transacción propia, o informa por qué no se puede continuar."""
        transaccion, redireccion = _resolver_transaccion_propia(request, CalculoOperacion, kwargs['pk'])
        if redireccion is not None:
            return redireccion
        _avisar_resultado_pago_stripe(request)
        return render(request, 'divisas/detalle_transaccion_operacion.html', {'transaccion': transaccion})

    def post(self, request, *args, **kwargs):
        """Reintenta la entrega de la propia transacción, si quedó en "Entrega fallida"."""
        transaccion, redireccion = _resolver_transaccion_propia(request, CalculoOperacion, kwargs['pk'])
        if redireccion is not None:
            return redireccion

        resultado = reintentar_entrega(transaccion)
        if resultado is None:
            messages.info(request, 'Esta transacción ya no está en entrega fallida.')
        elif resultado:
            messages.success(request, 'La entrega se reintentó con éxito.')
        else:
            messages.error(
                request,
                'La entrega volvió a fallar. Un administrador va a revisarla; también podés reintentarla de nuevo.',
            )
        return redirect('divisas:detalle_transaccion_operacion', pk=transaccion.pk)


class DetalleTransaccionCambioView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Muestra el detalle completo, de solo lectura, de un cambio entre divisas propio.

    Es la pantalla de detalle a la que se accede desde
    ``MiHistorialTransaccionesView`` al hacer clic en una fila de tipo
    "Cambio". A diferencia de ``ConfirmarTransaccionCambioView``, no ofrece
    ningún botón para confirmar, cancelar ni recalcular: solo expone las
    divisas, el monto, las tasas aplicadas, la comisión, el importe final, el
    estado y la fecha, sin importar en qué estado se encuentre el cambio. La
    única acción que sí ofrece es "Reintentar" cuando la entrega quedó
    fallida (ver ``post``, HU "Acreditación de fondos" GE-23).
    """

    def test_func(self):
        """Permite consultar el detalle solo a los roles que pueden operar."""
        roles = self.request.session.get('keycloak_roles', [])
        return (
            'cliente' in roles
            and not self.request.user.is_staff
            and self.request.user.clientes.filter(is_active=True).exists()
        )

    def get(self, request, *args, **kwargs):
        """Recupera el cambio propio, o informa por qué no se puede continuar."""
        transaccion, redireccion = _resolver_transaccion_propia(request, CalculoTriangulacion, kwargs['pk'])
        if redireccion is not None:
            return redireccion
        _avisar_resultado_pago_stripe(request)
        return render(request, 'divisas/detalle_transaccion_cambio.html', {'transaccion': transaccion})

    def post(self, request, *args, **kwargs):
        """Reintenta la entrega del propio cambio, si quedó en "Entrega fallida"."""
        transaccion, redireccion = _resolver_transaccion_propia(request, CalculoTriangulacion, kwargs['pk'])
        if redireccion is not None:
            return redireccion

        resultado = reintentar_entrega(transaccion)
        if resultado is None:
            messages.info(request, 'Esta transacción ya no está en entrega fallida.')
        elif resultado:
            messages.success(request, 'La entrega se reintentó con éxito.')
        else:
            messages.error(
                request,
                'La entrega volvió a fallar. Un administrador va a revisarla; también podés reintentarla de nuevo.',
            )
        return redirect('divisas:detalle_transaccion_cambio', pk=transaccion.pk)


class PagarTransaccionOperacionView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Permite pagar una compra o venta propia ya "Confirmada".

    Implementa la HU "Asociación de pagos a transacciones" (GE-25): el
    cliente elige uno de sus métodos de pago guardados
    (``apps.clientes.models.MetodoPago``). Esta vista nunca registra el
    pago ella misma: si el método es de tipo "tarjeta", redirige a
    ``apps.divisas.pagos_stripe.IniciarPagoStripeOperacionView`` (HU "Pago
    con tarjeta vía Stripe"); si es "transferencia" o "billetera", a
    ``apps.divisas.pagos_sipap.IniciarPagoSipapOperacionView`` (HU "Pago
    por transferencia bancaria vía SIPAP" — sipap-sim simula
    indistintamente bancos y billeteras digitales, así que ambos tipos
    comparten el mismo flujo).
    """

    def test_func(self):
        """Permite pagar solo a los roles que pueden operar."""
        roles = self.request.session.get('keycloak_roles', [])
        return (
            'cliente' in roles
            and not self.request.user.is_staff
            and self.request.user.clientes.filter(is_active=True).exists()
        )

    def get(self, request, *args, **kwargs):
        """Muestra el formulario de pago, o por qué todavía no se puede pagar."""
        transaccion, redireccion = _resolver_transaccion_propia(request, CalculoOperacion, kwargs['pk'])
        if redireccion is not None:
            return redireccion
        transaccion.marcar_vencida_si_corresponde()
        form = (
            PagarTransaccionForm(cliente=transaccion.cliente, transaccion=transaccion)
            if _puede_pagarse(transaccion) else None
        )
        return render(request, 'divisas/pagar_transaccion.html', {
            'transaccion': transaccion, 'form': form,
            'monto_a_pagar': monto_a_pagar(transaccion), 'moneda_a_pagar': moneda_a_pagar(transaccion),
            'monto_a_entregar': monto_a_entregar(transaccion), 'moneda_a_entregar': moneda_a_entregar(transaccion),
        })

    def post(self, request, *args, **kwargs):
        """Guarda el medio de destino elegido y registra el pago, o inicia el cobro con Stripe.

        Args:
            request (HttpRequest): Solicitud POST con los campos
                ``medio_origen`` y ``medio_destino``.

        Returns:
            HttpResponse: Redirección a Stripe si el medio de origen es
            "tarjeta", o al detalle de la transacción con el resultado en
            cualquier otro caso.
        """
        transaccion, redireccion = _resolver_transaccion_propia(request, CalculoOperacion, kwargs['pk'])
        if redireccion is not None:
            return redireccion
        transaccion.marcar_vencida_si_corresponde()

        if not _puede_pagarse(transaccion):
            if transaccion.estado_efectivo in estados_con_pago_ya_registrado(CalculoOperacion):
                messages.error(request, 'Esta transacción ya fue pagada.')
            elif transaccion.tasa_vencida:
                messages.error(
                    request,
                    'La tasa fijada al confirmar esta operación ya venció. Debe recalcularla.',
                )
            else:
                messages.error(request, 'Esta transacción no está en condiciones de pagarse.')
            return redirect('divisas:detalle_transaccion_operacion', pk=transaccion.pk)

        if request.POST.get('accion') == 'cancelar':
            transaccion.estado = CalculoOperacion.ESTADO_CANCELADA
            transaccion.save(update_fields=['estado'])
            messages.success(request, 'La operación fue cancelada.')
            return redirect('divisas:detalle_transaccion_operacion', pk=transaccion.pk)

        form = PagarTransaccionForm(request.POST, cliente=transaccion.cliente, transaccion=transaccion)
        if not form.is_valid():
            return render(request, 'divisas/pagar_transaccion.html', {
            'transaccion': transaccion, 'form': form,
            'monto_a_pagar': monto_a_pagar(transaccion), 'moneda_a_pagar': moneda_a_pagar(transaccion),
            'monto_a_entregar': monto_a_entregar(transaccion), 'moneda_a_entregar': moneda_a_entregar(transaccion),
        })

        medio_origen = form.cleaned_data['medio_origen']
        transaccion.medio_destino = form.cleaned_data['medio_destino']
        transaccion.save(update_fields=['medio_destino'])

        if medio_origen.tipo_medio == MetodoPago.TIPO_TARJETA:
            # Un método guardado de tipo "tarjeta" se cobra vía Stripe, no
            # de forma manual: en vez de registrar el pago acá, se redirige
            # a cobrar con esa tarjeta puntual (ver
            # apps.divisas.pagos_stripe.IniciarPagoStripeOperacionView). El
            # parámetro sigue llamándose "metodo_pago" en la URL por
            # compatibilidad con ese módulo, aunque el campo del formulario
            # se llame "medio_origen".
            url = reverse('divisas:pagar_transaccion_stripe', kwargs={'pk': transaccion.pk})
            return redirect(f'{url}?metodo_pago={medio_origen.pk}')
        # Transferencia o billetera digital: ambas se pagan vía SIPAP, no
        # de forma manual (sipap-sim simula indistintamente bancos y
        # billeteras). Se redirige a generar la solicitud de pago (ver
        # apps.divisas.pagos_sipap.IniciarPagoSipapOperacionView),
        # pasando con qué cuenta puntual, igual que con una tarjeta.
        url = reverse('divisas:pagar_transaccion_sipap', kwargs={'pk': transaccion.pk})
        return redirect(f'{url}?metodo_pago={medio_origen.pk}')


class PagarTransaccionCambioView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Permite pagar un cambio entre divisas propio ya "Confirmado".

    Ver ``PagarTransaccionOperacionView``: mismo flujo y mismas HU futuras
    como base, aplicado a ``CalculoTriangulacion`` en vez de a una compra o
    venta. Una diferencia importante: lo que el cliente paga es
    ``monto_origen`` (``apps.divisas.models.monto_a_pagar``), en su divisa
    de origen, no ``monto_final`` — eso es lo que recibe a cambio, no lo
    que entrega.
    """

    def test_func(self):
        """Permite pagar solo a los roles que pueden operar."""
        roles = self.request.session.get('keycloak_roles', [])
        return (
            'cliente' in roles
            and not self.request.user.is_staff
            and self.request.user.clientes.filter(is_active=True).exists()
        )

    def get(self, request, *args, **kwargs):
        """Muestra el formulario de pago, o por qué todavía no se puede pagar."""
        transaccion, redireccion = _resolver_transaccion_propia(request, CalculoTriangulacion, kwargs['pk'])
        if redireccion is not None:
            return redireccion
        transaccion.marcar_vencida_si_corresponde()
        form = (
            PagarTransaccionForm(cliente=transaccion.cliente, transaccion=transaccion)
            if _puede_pagarse(transaccion) else None
        )
        return render(request, 'divisas/pagar_transaccion_cambio.html', {
            'transaccion': transaccion, 'form': form,
            'monto_a_pagar': monto_a_pagar(transaccion), 'moneda_a_pagar': moneda_a_pagar(transaccion),
            'monto_a_entregar': monto_a_entregar(transaccion), 'moneda_a_entregar': moneda_a_entregar(transaccion),
        })

    def post(self, request, *args, **kwargs):
        """Guarda el medio de destino elegido y registra el pago, o inicia el cobro con Stripe.

        Args:
            request (HttpRequest): Solicitud POST con los campos
                ``medio_origen`` y ``medio_destino``.

        Returns:
            HttpResponse: Redirección a Stripe si el medio de origen es
            "tarjeta", o al detalle del cambio con el resultado en
            cualquier otro caso.
        """
        transaccion, redireccion = _resolver_transaccion_propia(request, CalculoTriangulacion, kwargs['pk'])
        if redireccion is not None:
            return redireccion
        transaccion.marcar_vencida_si_corresponde()

        if not _puede_pagarse(transaccion):
            if transaccion.estado_efectivo in estados_con_pago_ya_registrado(CalculoTriangulacion):
                messages.error(request, 'Esta transacción ya fue pagada.')
            elif transaccion.tasa_vencida:
                messages.error(
                    request,
                    'La tasa fijada al confirmar este cambio ya venció. Debe recalcularlo.',
                )
            else:
                messages.error(request, 'Esta transacción no está en condiciones de pagarse.')
            return redirect('divisas:detalle_transaccion_cambio', pk=transaccion.pk)

        if request.POST.get('accion') == 'cancelar':
            transaccion.estado = CalculoTriangulacion.ESTADO_CANCELADA
            transaccion.save(update_fields=['estado'])
            messages.success(request, 'El cambio fue cancelado.')
            return redirect('divisas:detalle_transaccion_cambio', pk=transaccion.pk)

        form = PagarTransaccionForm(request.POST, cliente=transaccion.cliente, transaccion=transaccion)
        if not form.is_valid():
            return render(request, 'divisas/pagar_transaccion_cambio.html', {
                'transaccion': transaccion, 'form': form,
                'monto_a_pagar': monto_a_pagar(transaccion), 'moneda_a_pagar': moneda_a_pagar(transaccion),
                'monto_a_entregar': monto_a_entregar(transaccion), 'moneda_a_entregar': moneda_a_entregar(transaccion),
            })

        medio_origen = form.cleaned_data['medio_origen']
        transaccion.medio_destino = form.cleaned_data['medio_destino']
        transaccion.save(update_fields=['medio_destino'])

        if medio_origen.tipo_medio == MetodoPago.TIPO_TARJETA:
            # Ver PagarTransaccionOperacionView.post: un método de tipo
            # "tarjeta" se cobra vía Stripe, no de forma manual. En la
            # práctica esto nunca ocurre para un cambio (el filtro de
            # medio_origen del formulario ya excluye la tarjeta, porque
            # un cambio nunca se paga en PYG); se deja el chequeo igual,
            # por las dudas, en vez de asumirlo.
            url = reverse('divisas:pagar_transaccion_cambio_stripe', kwargs={'pk': transaccion.pk})
            return redirect(f'{url}?metodo_pago={medio_origen.pk}')
        # Ver PagarTransaccionOperacionView.post: transferencia o
        # billetera digital, ambas se pagan vía SIPAP.
        url = reverse('divisas:pagar_transaccion_cambio_sipap', kwargs={'pk': transaccion.pk})
        return redirect(f'{url}?metodo_pago={medio_origen.pk}')


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
            'vigencia_segundos': ConfiguracionVigencia.vigencia_calculo_segundos(),
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
        vence_en = ahora + timedelta(seconds=ConfiguracionVigencia.vigencia_calculo_segundos())
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
            'vigencia_segundos': ConfiguracionVigencia.vigencia_calculo_segundos(),
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
        vence_en = timezone.now() + timedelta(seconds=ConfiguracionVigencia.vigencia_calculo_segundos())
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


class ConfirmarTransaccionCambioView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Muestra el resumen de un cambio pendiente y permite confirmarlo o cancelarlo.

    Implementa la HU "Confirmación de operación cambiaria" para los cambios
    entre divisas: el cliente ve el resumen completo de una transacción en
    estado "Pendiente de confirmación" y decide si la confirma (si las tasas
    vigentes no cambiaron desde el cálculo inicial) o la cancela. Si al
    confirmar alguna tasa vigente ya cambió, el cambio se cancela
    automáticamente como "Cancelada por cambio de cotización" (ver
    ``CalculoTriangulacion.tasas_vigentes_cambiaron``) en vez de confirmarse.
    """

    def test_func(self):
        """Permite revisar el cambio solo a los roles que pueden operar."""
        roles = self.request.session.get('keycloak_roles', [])
        return (
            'cliente' in roles
            and not self.request.user.is_staff
            and self.request.user.clientes.filter(is_active=True).exists()
        )

    def get(self, request, *args, **kwargs):
        """Muestra el resumen completo del cambio pendiente.

        Si el tiempo para confirmarlo ya venció (por ejemplo, el cliente
        cerró la pestaña sin decidir nada), lo marca "Vencida" en este mismo
        acceso, antes de mostrarlo. Si el cliente activo cambió desde que se
        abrió esta pantalla, informa que el cambio no corresponde en vez de
        mostrarlo (ver ``_resolver_transaccion_propia``).
        """
        transaccion, redireccion = _resolver_transaccion_propia(request, CalculoTriangulacion, kwargs['pk'])
        if redireccion is not None:
            return redireccion
        transaccion.marcar_vencida_si_corresponde()
        return render(request, 'divisas/confirmar_transaccion_cambio.html', {'transaccion': transaccion})

    def post(self, request, *args, **kwargs):
        """Confirma o cancela el cambio según la acción elegida.

        Antes de procesar la acción, revisa si el tiempo para confirmar ya
        venció (ya sea recién ahora o desde una visita anterior) y, de ser
        así, bloquea la acción en vez de procesarla. Al confirmar, si alguna
        tasa vigente ya no coincide con la usada al calcular, el cambio se
        cancela automáticamente como "Cancelada por cambio de cotización" en
        vez de confirmarse. Si el cliente activo cambió desde que se abrió
        esta pantalla, informa que el cambio no corresponde en vez de
        procesar la acción.

        Args:
            request (HttpRequest): Solicitud POST con el campo ``accion``
                (``confirmar`` o ``cancelar``).

        Returns:
            HttpResponse: Redirección a la misma pantalla con el resultado.
        """
        transaccion, redireccion = _resolver_transaccion_propia(request, CalculoTriangulacion, kwargs['pk'])
        if redireccion is not None:
            return redireccion
        transaccion.marcar_vencida_si_corresponde()
        if transaccion.estado != CalculoTriangulacion.ESTADO_PENDIENTE:
            if transaccion.estado == CalculoTriangulacion.ESTADO_VENCIDA:
                messages.error(
                    request,
                    'El tiempo para confirmar este cambio venció. Debe recalcular la operación.',
                )
            else:
                messages.info(request, 'Este cambio ya fue procesado.')
            return redirect('divisas:confirmar_transaccion_cambio', pk=transaccion.pk)

        accion = request.POST.get('accion')
        if accion == 'cancelar':
            transaccion.estado = CalculoTriangulacion.ESTADO_CANCELADA
            transaccion.save(update_fields=['estado'])
            messages.success(request, 'El cambio fue cancelado.')
            return redirect('divisas:confirmar_transaccion_cambio', pk=transaccion.pk)

        if accion == 'confirmar':
            if transaccion.tasas_vigentes_cambiaron:
                transaccion.estado = CalculoTriangulacion.ESTADO_CANCELADA_COTIZACION
                transaccion.save(update_fields=['estado'])
                messages.error(
                    request,
                    'Las tasas vigentes cambiaron desde el cálculo inicial. El cambio fue cancelado;'
                    ' puede recalcularlo con las tasas nuevas.',
                )
                return redirect('divisas:confirmar_transaccion_cambio', pk=transaccion.pk)
            mensaje_saldo = _verificar_saldo_casa_de_cambio(transaccion)
            if mensaje_saldo is not None:
                transaccion.estado = CalculoTriangulacion.ESTADO_CANCELADA_SALDO_INSUFICIENTE
                transaccion.save(update_fields=['estado'])
                messages.error(request, mensaje_saldo)
                return redirect('divisas:confirmar_transaccion_cambio', pk=transaccion.pk)
            transaccion.estado = CalculoTriangulacion.ESTADO_CONFIRMADA
            transaccion.confirmado_en = timezone.now()
            transaccion.tasa_vence_en = transaccion.confirmado_en + timedelta(
                seconds=ConfiguracionVigencia.vigencia_pago_segundos()
            )
            transaccion.save(update_fields=['estado', 'confirmado_en', 'tasa_vence_en'])
            messages.success(request, 'El cambio fue confirmado.')
            return redirect('divisas:confirmar_transaccion_cambio', pk=transaccion.pk)

        messages.error(request, 'Acción no reconocida.')
        return redirect('divisas:confirmar_transaccion_cambio', pk=transaccion.pk)


@login_required
def confirmar_triangulacion_view(request):
    """Revalida el cálculo previo de un cambio y recién ahí crea la transacción.

    Comprueba que no haya vencido el tiempo de reserva y que ambas
    cotizaciones sigan siendo las usadas al calcular. Si es así, recalcula el
    importe con las tasas actuales (nunca confía en los montos que viajan
    desde el navegador) y registra el cambio en estado "Pendiente de
    confirmación", a nombre del cliente activo, para que el cliente lo revise
    y lo confirme o cancele en ``ConfirmarTransaccionCambioView``.

    Args:
        request (HttpRequest): Solicitud POST con los campos ocultos del cálculo.

    Returns:
        HttpResponse: Redirección a la pantalla de confirmación del cambio
        recién creado, o al inicio si algo falla antes de crearlo.
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
    transaccion = CalculoTriangulacion.objects.create(
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
        vence_en=ahora + timedelta(seconds=ConfiguracionVigencia.vigencia_confirmacion_segundos()),
    )
    messages.success(
        request,
        f'Cambio de {origen.codigo} a {destino.codigo} registrado. Revisá el resumen para confirmarlo.',
    )
    return redirect('divisas:confirmar_transaccion_cambio', pk=transaccion.pk)


class ConfirmarTransaccionOperacionView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Muestra el resumen de una compra o venta pendiente y permite confirmarla o cancelarla.

    Implementa la HU "Confirmación de operación cambiaria": el cliente ve el
    resumen completo (tipo de operación, divisa, monto, tasa aplicada,
    comisión y monto final) de una transacción en estado "Pendiente de
    confirmación" y decide si la confirma (si la tasa vigente no cambió desde
    el cálculo inicial, pasa a "Confirmada" y se registra la fecha y hora de
    confirmación) o la cancela manualmente (pasa a "Cancelada" y no se
    procesa más). Si al confirmar la tasa vigente ya cambió, la transacción
    se cancela automáticamente como "Cancelada por cambio de cotización" (ver
    ``CalculoOperacion.tasa_vigente_cambio``) en vez de confirmarse.
    """

    def test_func(self):
        """Permite revisar la transacción solo a los roles que pueden operar."""
        roles = self.request.session.get('keycloak_roles', [])
        return (
            'cliente' in roles
            and not self.request.user.is_staff
            and self.request.user.clientes.filter(is_active=True).exists()
        )

    def get(self, request, *args, **kwargs):
        """Muestra el resumen completo de la transacción pendiente.

        Si el tiempo para confirmarla ya venció (por ejemplo, el cliente
        cerró la pestaña sin decidir nada), la marca "Vencida" en este mismo
        acceso, antes de mostrarla. Si el cliente activo cambió desde que se
        abrió esta pantalla, informa que la transacción no corresponde en
        vez de mostrarla (ver ``_resolver_transaccion_propia``).
        """
        transaccion, redireccion = _resolver_transaccion_propia(request, CalculoOperacion, kwargs['pk'])
        if redireccion is not None:
            return redireccion
        transaccion.marcar_vencida_si_corresponde()
        return render(request, 'divisas/confirmar_transaccion.html', {'transaccion': transaccion})

    def post(self, request, *args, **kwargs):
        """Confirma o cancela la transacción según la acción elegida.

        Antes de procesar la acción, revisa si el tiempo para confirmar ya
        venció (ya sea recién ahora o desde una visita anterior) y, de ser
        así, bloquea la acción en vez de procesarla. Al confirmar, si la tasa
        vigente ya no coincide con la usada al calcular, la transacción se
        cancela automáticamente como "Cancelada por cambio de cotización" en
        vez de confirmarse. Si el cliente activo cambió desde que se abrió
        esta pantalla, informa que la transacción no corresponde en vez de
        procesar la acción.

        Args:
            request (HttpRequest): Solicitud POST con el campo ``accion``
                (``confirmar`` o ``cancelar``).

        Returns:
            HttpResponse: Redirección a la misma pantalla con el resultado.
        """
        transaccion, redireccion = _resolver_transaccion_propia(request, CalculoOperacion, kwargs['pk'])
        if redireccion is not None:
            return redireccion
        transaccion.marcar_vencida_si_corresponde()
        if transaccion.estado != CalculoOperacion.ESTADO_PENDIENTE:
            if transaccion.estado == CalculoOperacion.ESTADO_VENCIDA:
                messages.error(
                    request,
                    'El tiempo para confirmar esta operación venció. Debe recalcular la operación.',
                )
            else:
                messages.info(request, 'Esta transacción ya fue procesada.')
            return redirect('divisas:confirmar_transaccion', pk=transaccion.pk)

        accion = request.POST.get('accion')
        if accion == 'cancelar':
            transaccion.estado = CalculoOperacion.ESTADO_CANCELADA
            transaccion.save(update_fields=['estado'])
            messages.success(request, 'La operación fue cancelada.')
            return redirect('divisas:confirmar_transaccion', pk=transaccion.pk)

        if accion == 'confirmar':
            if transaccion.tasa_vigente_cambio:
                transaccion.estado = CalculoOperacion.ESTADO_CANCELADA_COTIZACION
                transaccion.save(update_fields=['estado'])
                messages.error(
                    request,
                    'La tasa vigente cambió desde el cálculo inicial. La operación fue cancelada;'
                    ' puede recalcularla con la tasa nueva.',
                )
                return redirect('divisas:confirmar_transaccion', pk=transaccion.pk)
            mensaje_saldo = _verificar_saldo_casa_de_cambio(transaccion)
            if mensaje_saldo is not None:
                transaccion.estado = CalculoOperacion.ESTADO_CANCELADA_SALDO_INSUFICIENTE
                transaccion.save(update_fields=['estado'])
                messages.error(request, mensaje_saldo)
                return redirect('divisas:confirmar_transaccion', pk=transaccion.pk)
            transaccion.estado = CalculoOperacion.ESTADO_CONFIRMADA
            transaccion.confirmado_en = timezone.now()
            transaccion.tasa_vence_en = transaccion.confirmado_en + timedelta(
                seconds=ConfiguracionVigencia.vigencia_pago_segundos()
            )
            transaccion.save(update_fields=['estado', 'confirmado_en', 'tasa_vence_en'])
            messages.success(request, 'La operación fue confirmada.')
            return redirect('divisas:confirmar_transaccion', pk=transaccion.pk)

        messages.error(request, 'Acción no reconocida.')
        return redirect('divisas:confirmar_transaccion', pk=transaccion.pk)


@login_required
def confirmar_calculo_operacion_view(request, tipo):
    """Revalida el cálculo previo (Paso 1) y recién ahí crea la transacción.

    El Paso 1 ("Calcular importe") no persiste nada: viaja como campos
    ocultos. Acá se revalida que la cotización usada siga siendo la vigente y
    que no haya pasado el tiempo de reserva antes de crear el registro, ya
    directamente en estado "Pendiente de confirmación". Sirve tanto para la
    compra como para la venta de divisas; la transacción queda registrada
    con el tipo de la ruta, el cliente activo, la divisa, el monto y la fecha
    de creación, para que el cliente la revise y la confirme o cancele en
    ``ConfirmarTransaccionOperacionView``.

    Args:
        request (HttpRequest): Solicitud POST con los campos ocultos del Paso 1.
        tipo (str): ``compra`` o ``venta``, según la ruta.

    Returns:
        HttpResponse: Redirección a la pantalla de confirmación de la
        transacción recién creada, o al inicio si algo falla antes de
        crearla.

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
    transaccion = CalculoOperacion.objects.create(
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
        vence_en=ahora + timedelta(seconds=ConfiguracionVigencia.vigencia_confirmacion_segundos()),
    )
    tipo_display = dict(CalculoOperacion.TIPO_CHOICES)[tipo]
    messages.success(
        request,
        f'{tipo_display} de {divisa.codigo} registrada. Revisá el resumen para confirmarla.',
    )
    return redirect('divisas:confirmar_transaccion', pk=transaccion.pk)


class AdminDivisasMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Control de acceso: solo administradores (rol 'admin' en Keycloak)."""
    def test_func(self):
        """Comprueba que el rol de administrador esté en la sesión."""
        roles = self.request.session.get('keycloak_roles', [])
        return 'admin' in roles


class ConfiguracionVigenciaUpdateView(AdminDivisasMixin, UpdateView):
    """Permite al administrador configurar los tiempos de espera de las operaciones.

    Edita el único registro de ``ConfiguracionVigencia`` (lo crea la primera
    vez, con los valores por defecto de ``settings``, si todavía no existe).
    """

    model = ConfiguracionVigencia
    form_class = ConfiguracionVigenciaForm
    template_name = 'divisas/configuracion_vigencia_form.html'
    success_url = reverse_lazy('divisas:configuracion_vigencia')

    def get_object(self, queryset=None):
        """Recupera la configuración existente o construye una con los valores por defecto."""
        return ConfiguracionVigencia.objects.first() or ConfiguracionVigencia(
            calculo_vigencia_segundos=settings.CALCULO_OPERACION_VIGENCIA_SEGUNDOS,
            confirmacion_vigencia_segundos=settings.CONFIRMACION_OPERACION_VIGENCIA_SEGUNDOS,
            pago_vigencia_segundos=settings.PAGO_OPERACION_VIGENCIA_SEGUNDOS,
        )

    def form_valid(self, form):
        """Registra quién actualizó la configuración y confirma el guardado."""
        form.instance.actualizado_por = self.request.user
        super().form_valid(form)
        messages.success(self.request, 'Los tiempos de espera se actualizaron correctamente.')
        return redirect('divisas:configuracion_vigencia')


class CuentaPropiaListView(AdminDivisasMixin, ListView):
    """Lista el saldo propio de Global Exchange en cada divisa, sincronizado con sipap-sim.

    La cuenta bancaria o billetera real se crea en sipap-sim (ver
    ``sipap_panel_url`` en el contexto), pero cuál de las cuentas de
    sipap-sim hace de "casa de cambio" para cada divisa se designa
    desde acá, no en sipap-sim (ver ``DesignarCuentaPropiaView``):
    sipap-sim solo refleja esa designación, nunca la decide por sí
    solo. Esta pantalla es de solo lectura sobre el saldo y la cuenta
    designada, y en cada visita vuelve a consultarlos para corregir
    cualquier diferencia con lo que tenía guardado (ver
    ``apps.divisas.casa_de_cambio``). Si sipap-sim no responde, se
    muestra el último valor conocido en vez de romper la pantalla.
    """
    model = CuentaPropia
    template_name = 'divisas/cuenta_propia_list.html'
    context_object_name = 'cuentas_propias'

    def get_queryset(self):
        """Sincroniza cada cuenta propia con sipap-sim antes de listarlas."""
        cuentas = list(
            CuentaPropia.objects.filter(divisa__activa=True).select_related('divisa').order_by('divisa__codigo')
        )
        self.sin_cuenta_en_sipap = []
        self.error_sincronizacion = False
        for cuenta in cuentas:
            try:
                saldo_real = consultar_saldo_casa_de_cambio(cuenta.divisa.codigo)
            except SipapComunicacionError:
                self.error_sincronizacion = True
                cuenta.cuenta_sipap = None
                continue
            if saldo_real is None:
                self.sin_cuenta_en_sipap.append(cuenta.divisa.codigo)
                cuenta.cuenta_sipap = None
                continue
            if saldo_real != cuenta.saldo:
                cuenta.saldo = saldo_real
                cuenta.save(update_fields=['saldo'])
            try:
                cuenta.cuenta_sipap = consultar_cuenta_casa_de_cambio(cuenta.divisa.codigo)
            except SipapComunicacionError:
                self.error_sincronizacion = True
                cuenta.cuenta_sipap = None
        return cuentas

    def get_context_data(self, **kwargs):
        """Agrega los avisos de sincronización, el enlace al panel de sipap-sim y el formulario de designación."""
        context = super().get_context_data(**kwargs)
        context['sin_cuenta_en_sipap'] = self.sin_cuenta_en_sipap
        context['error_sincronizacion'] = self.error_sincronizacion
        context['sipap_panel_url'] = f'{settings.SIPAP_BASE_URL}/panel/cuentas/'
        context['form_designar'] = DesignarCuentaPropiaForm()
        return context


class DesignarCuentaPropiaView(AdminDivisasMixin, View):
    """Designa, a pedido de un administrador, cuál cuenta de sipap-sim es la casa de cambio en una divisa.

    sipap-sim no decide esto por sí solo (ver ``core.forms.CuentaForm``
    del lado de sipap-sim, que ya no incluye ``es_cuenta_casa_de_cambio``):
    la cuenta se crea ahí como una más y Global Exchange, desde acá, le
    indica cuál puntual —identificada por número y documento, igual
    que al validar un método de pago— le corresponde a cada divisa.
    """

    def post(self, request, codigo):
        """Valida el formulario y le pide a sipap-sim que designe la cuenta indicada."""
        divisa = get_object_or_404(Divisa, codigo=codigo)
        form = DesignarCuentaPropiaForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Ingresá el número de cuenta y el CI o RUC del titular.')
            return redirect('divisas:lista_cuentas_propias')

        try:
            cuenta_designada = designar_cuenta_casa_de_cambio(
                divisa.codigo,
                form.cleaned_data['numero_cuenta'],
                form.cleaned_data['documento_titular'],
            )
        except DesignacionCuentaPropiaError as error:
            messages.error(request, str(error))
        except SipapComunicacionError:
            messages.error(
                request,
                'No se pudo conectar con sipap-sim para designar la cuenta. Intentá nuevamente en unos minutos.',
            )
        else:
            messages.success(
                request,
                f'{cuenta_designada["numero"]} ({cuenta_designada["proveedor"]}) queda designada como la '
                f'cuenta de la casa de cambio en {divisa.codigo}.',
            )
        return redirect('divisas:lista_cuentas_propias')


class HistorialCuentaPropiaView(AdminDivisasMixin, View):
    """Muestra el historial real de movimientos de la cuenta propia en una divisa.

    En vez de llevar un ledger propio (que duplicaría algo que
    sipap-sim ya guarda con más detalle) o linkear al admin de
    sipap-sim (otro estilo, otra sesión), trae los movimientos reales
    por API (``apps.divisas.casa_de_cambio.consultar_movimientos_casa_de_cambio``)
    y los muestra con el mismo diseño que el resto del sistema.
    """

    def get(self, request, codigo):
        """Busca la divisa por su código y consulta sus movimientos reales en sipap-sim."""
        divisa = get_object_or_404(Divisa, codigo=codigo)
        try:
            movimientos = consultar_movimientos_casa_de_cambio(divisa.codigo)
            error_sincronizacion = False
        except SipapComunicacionError:
            movimientos = []
            error_sincronizacion = True
        return render(request, 'divisas/historial_cuenta_propia.html', {
            'divisa': divisa,
            'movimientos': movimientos,
            'error_sincronizacion': error_sincronizacion,
        })


class EntregasPendientesListView(AdminDivisasMixin, ListView):
    """Lista las compras, ventas y cambios cuya entrega al cliente falló, para reintentarla a mano.

    Reúne, igual que ``HistorialTransaccionesView``, las dos clases de
    transacción (``CalculoOperacion``/``CalculoTriangulacion``) que
    quedaron en "Entrega fallida" (ver
    ``apps.divisas.entrega.realizar_entrega``): el pago del cliente ya
    se registró, pero la transferencia saliente a sipap-sim no se pudo
    completar (sin respuesta, rechazada, o sin saldo propio suficiente
    en ese momento). Reintentar desde acá (``ReintentarEntregaView``)
    es seguro: sipap-sim reconoce la misma referencia y no transfiere
    dos veces si la entrega anterior sí había llegado a procesarse.
    """
    template_name = 'divisas/entregas_pendientes.html'
    context_object_name = 'entregas'

    @staticmethod
    def _fila(transaccion, tipo_modelo, tipo_display, divisa_display, url_detalle, url_reintentar):
        return {
            'pk': transaccion.pk,
            'creado_en': transaccion.creado_en,
            'tipo': tipo_display,
            'cliente': transaccion.cliente,
            'divisa': divisa_display,
            'monto_a_entregar': monto_a_entregar(transaccion),
            'moneda_a_entregar': moneda_a_entregar(transaccion),
            'medio_destino': transaccion.medio_destino,
            'url_detalle': url_detalle,
            'url_reintentar': url_reintentar,
        }

    def get_queryset(self):
        """Devuelve las entregas fallidas de ambas transacciones, de la más reciente a la más antigua."""
        filas = [
            self._fila(
                operacion, 'operacion', operacion.get_tipo_display(), operacion.codigo_divisa,
                reverse('divisas:detalle_transaccion_operacion', kwargs={'pk': operacion.pk}),
                reverse('divisas:reintentar_entrega', kwargs={'tipo': 'operacion', 'pk': operacion.pk}),
            )
            for operacion in CalculoOperacion.objects.filter(
                estado=CalculoOperacion.ESTADO_ENTREGA_FALLIDA,
            ).select_related('cliente', 'medio_destino')
        ]
        filas.extend(
            self._fila(
                cambio, 'cambio', CalculoTriangulacion.TIPO_DISPLAY,
                f'{cambio.codigo_divisa_origen} → {cambio.codigo_divisa_destino}',
                reverse('divisas:detalle_transaccion_cambio', kwargs={'pk': cambio.pk}),
                reverse('divisas:reintentar_entrega', kwargs={'tipo': 'cambio', 'pk': cambio.pk}),
            )
            for cambio in CalculoTriangulacion.objects.filter(
                estado=CalculoTriangulacion.ESTADO_ENTREGA_FALLIDA,
            ).select_related('cliente', 'medio_destino')
        )
        return sorted(filas, key=lambda fila: fila['creado_en'], reverse=True)


class ReintentarEntregaView(AdminDivisasMixin, View):
    """Reintenta, a pedido de un administrador, la entrega de una transacción en 'Entrega fallida'."""

    def post(self, request, tipo, pk):
        """Vuelve a llamar a ``realizar_entrega`` (vía ``reintentar_entrega``); si falla, queda igual en la lista."""
        if tipo not in ('operacion', 'cambio'):
            raise Http404
        modelo = CalculoOperacion if tipo == 'operacion' else CalculoTriangulacion
        transaccion = get_object_or_404(modelo, pk=pk)

        resultado = reintentar_entrega(transaccion)
        if resultado is None:
            messages.info(request, 'Esta transacción ya no está en entrega fallida.')
        elif resultado:
            messages.success(request, 'La entrega se reintentó con éxito.')
        else:
            messages.error(
                request,
                'La entrega volvió a fallar. Revisá el medio de destino y el saldo propio antes de reintentar de nuevo.',
            )
        return redirect('divisas:entregas_pendientes')


class DocumentosElectronicosListView(AdminDivisasMixin, ListView):
    """Lista los documentos electrónicos emitidos ante SIFEN, el más reciente primero.

    Solo lectura: permite a un administrador ver de un vistazo el CDC
    y el estado de cada Factura Electrónica, y detectar cuáles quedaron
    en "Error al generar" (ver ``ReintentarEmisionDocumentoElectronicoView``)
    sin tener que abrir cada transacción una por una.
    """
    model = DocumentoElectronico
    template_name = 'divisas/documentos_electronicos.html'
    context_object_name = 'documentos'

    def get_queryset(self):
        """Trae de una sola vez el cliente de cada transacción facturada, para no repetir consultas."""
        return DocumentoElectronico.objects.select_related(
            'calculo_operacion__cliente', 'calculo_triangulacion__cliente',
        )


class ReintentarEmisionDocumentoElectronicoView(AdminDivisasMixin, View):
    """Reintenta, a pedido explícito de un administrador, un documento en 'Error al generar'.

    Antes de usar esta acción, el administrador debe haber verificado
    con soporte de Factura Segura que el documento no llegó a generarse
    con ese número la vez anterior (ver ``apps.divisas.
    factura_electronica.reintentar_emision``): esta vista no hace esa
    verificación por sí sola, solo dispara el reintento.
    """

    def post(self, request, pk):
        """Vuelve a llamar a ``generar_de`` reutilizando el mismo número de documento."""
        documento = get_object_or_404(DocumentoElectronico, pk=pk)
        if reintentar_emision(documento):
            messages.success(request, 'El documento electrónico se generó correctamente.')
        else:
            messages.error(
                request,
                'El documento electrónico volvió a fallar, o ya no estaba en condiciones de reintentarse.',
            )
        return redirect('divisas:documentos_electronicos')


class ConsultarEstadoSifenDocumentoElectronicoView(AdminDivisasMixin, View):
    """Dispara, a pedido de un administrador, la consulta de estado real ante SIFEN (``get_estado_sifen``).

    ``generar_de`` solo confirma que Factura Segura recibió y encoló la
    solicitud (criterio 1), nunca la aprobación de SIFEN en sí
    (criterio 2): esa aprobación/rechazo solo se conoce a través de
    esta consulta, que no se dispara sola en ningún lado (no hay cron
    ni tarea periódica en esta entrega) — esta vista es, por ahora, la
    única forma de completar los criterios 2 y 3 para un documento ya
    generado.
    """

    def post(self, request, pk):
        """Llama a ``consultar_estado_sifen`` y refleja el resultado en un mensaje."""
        documento = get_object_or_404(DocumentoElectronico, pk=pk)
        if not documento.cdc:
            messages.error(request, 'Este documento todavía no tiene un CDC: no se generó correctamente.')
        elif consultar_estado_sifen(documento):
            documento.refresh_from_db()
            messages.success(request, f'Estado consultado: {documento.get_estado_display()}.')
        else:
            messages.error(request, 'No se pudo consultar el estado ante SIFEN (sin respuesta de Factura Segura).')
        return redirect('divisas:documentos_electronicos')


class DescargarDocumentoElectronicoView(LoginRequiredMixin, View):
    """Descarga el KuDE (PDF) o el XML firmado de un documento, bajo demanda, sin guardar nada.

    Accesible para un administrador (cualquier documento) o para el
    propio cliente (solo el de sus transacciones) — mismo criterio de
    acceso que ``DocumentosElectronicosListView``/
    ``MisFacturasElectronicasListView``, las dos pantallas desde donde
    se linkea esta descarga. Cada clic vuelve a pedirle el archivo a
    Factura Segura (``descargar_kude``/``descargar_xml``): no se
    almacena ninguna copia en el servidor.
    """

    FORMATOS = {
        'kude': (descargar_kude, 'application/pdf', 'pdf'),
        'xml': (descargar_xml, 'application/xml', 'xml'),
    }

    def get(self, request, pk, formato):
        """Resuelve permisos y devuelve el archivo pedido, o un error claro si no se puede."""
        documento = get_object_or_404(DocumentoElectronico, pk=pk)
        if not self._puede_ver(request, documento):
            raise PermissionDenied
        if formato not in self.FORMATOS:
            raise Http404('Formato de descarga desconocido.')
        if not documento.cdc:
            return HttpResponseBadRequest('Este documento todavía no tiene un CDC.')

        funcion, content_type, extension = self.FORMATOS[formato]
        contenido = funcion(documento)
        if contenido is None:
            return HttpResponse('No se pudo descargar el archivo desde Factura Segura.', status=502)

        respuesta = HttpResponse(contenido, content_type=content_type)
        respuesta['Content-Disposition'] = f'attachment; filename="{documento.numero_documento}.{extension}"'
        return respuesta

    @staticmethod
    def _puede_ver(request, documento):
        """Un administrador ve cualquier documento; un cliente, solo el de sus propias transacciones."""
        roles = request.session.get('keycloak_roles', [])
        if 'admin' in roles:
            return True
        if 'cliente' in roles and not request.user.is_staff:
            return request.user.clientes.filter(pk=documento.transaccion.cliente_id, is_active=True).exists()
        return False


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
        """Marca como activa la divisa recién creada y le crea su cuenta propia en cero.

        Sin esto, ninguna operación en la divisa nueva podría
        confirmarse nunca: el chequeo de saldo, al no encontrar ninguna
        cuenta propia, la trataría siempre como "sin fondos" (ver
        ``apps.divisas.views._verificar_saldo_casa_de_cambio``).
        """
        form.instance.activa = True
        respuesta = super().form_valid(form)
        CuentaPropia.objects.get_or_create(divisa=self.object)
        return respuesta


class DivisaUpdateView(AdminDivisasMixin, UpdateView):
    """Permite editar los datos de una divisa existente.

    PYG queda afuera: es la moneda base del sistema, implícita en
    cualquier operación, y no algo que un administrador pueda editar
    desde este catálogo (ver ``apps.divisas.forms.DivisaForm``). Se
    bloquea también acá —en ``get``/``post``, después de que
    ``AdminDivisasMixin`` ya comprobó el rol— para no mostrarle siquiera
    la pantalla de edición, en vez de confiar solo en que el formulario
    la rechace al guardar.
    """
    model = Divisa
    form_class = DivisaForm
    template_name = 'divisas/divisa_form.html'
    success_url = reverse_lazy('divisas:lista_divisas')

    def _bloquear_si_es_pyg(self, request):
        """Devuelve una redirección si la divisa objetivo es PYG, o ``None`` si no."""
        if self.get_object().es_base:
            messages.error(request, 'PYG es la divisa base del sistema: no se puede editar.')
            return redirect('divisas:lista_divisas')
        return None

    def get(self, request, *args, **kwargs):
        """Bloquea el acceso a la pantalla de edición de PYG."""
        return self._bloquear_si_es_pyg(request) or super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """Bloquea el guardado directo (sin pasar por el formulario) sobre PYG."""
        return self._bloquear_si_es_pyg(request) or super().post(request, *args, **kwargs)


class DivisaSoftDeleteView(AdminDivisasMixin, View):
    """Confirma y ejecuta la baja lógica de una divisa.

    PYG no se puede dar de baja: es la divisa base del sistema y tiene
    que seguir siempre activa (otros módulos, como la apertura de caja,
    dependen de eso).
    """

    def get(self, request, pk, *args, **kwargs):
        """Muestra el formulario de confirmación de baja."""
        divisa = get_object_or_404(Divisa, pk=pk)
        if divisa.es_base:
            messages.error(request, 'PYG es la divisa base del sistema: no se puede dar de baja.')
            return redirect('divisas:lista_divisas')
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
        if divisa.es_base:
            messages.error(request, 'PYG es la divisa base del sistema: no se puede dar de baja.')
            return redirect('divisas:lista_divisas')
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


class NotificacionesClienteMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Restringe las pantallas de notificaciones de tasas a usuarios clientes.

    Las notificaciones de cambio de tasa (HU GE-51) están dirigidas a
    usuarios clientes, así que se exige el rol ``cliente`` en la sesión de
    Keycloak, el mismo criterio con el que se muestra el indicador de no
    leídas (ver ``apps.divisas.context_processors.notificaciones_context``).
    Además, cada vista filtra siempre por ``request.user``: nadie puede ver
    ni modificar notificaciones ajenas.
    """

    def test_func(self):
        """Comprueba que el usuario tenga el rol de cliente."""
        roles = self.request.session.get('keycloak_roles', [])
        return 'cliente' in roles


class MisNotificacionesView(NotificacionesClienteMixin, ListView):
    """Lista las notificaciones de cambio de tasa del usuario autenticado.

    Criterio de aceptación 4 de GE-51: las notificaciones se muestran
    ordenadas de la más reciente a la más antigua. Cada una muestra la
    divisa, el tipo de tasa, la tasa anterior, la nueva y si ya fue leída;
    las no leídas ofrecen la acción de marcarlas como leídas (ver
    ``MarcarNotificacionLeidaView``).
    """

    template_name = 'divisas/mis_notificaciones.html'
    context_object_name = 'notificaciones'
    paginate_by = 20

    def get_queryset(self):
        """Devuelve solo las notificaciones propias, de la más nueva a la más vieja."""
        return (
            NotificacionTasa.objects.filter(usuario=self.request.user)
            .select_related('divisa')
            .order_by('-creada_en', '-pk')
        )


class MarcarNotificacionLeidaView(NotificacionesClienteMixin, View):
    """Marca como leída una notificación de cambio de tasa propia.

    Criterio de aceptación 6 de GE-51: al marcarla, su estado cambia a
    leída y deja de contarse en el indicador de no leídas. Solo acepta
    POST (es una acción que modifica datos, protegida por CSRF) y responde
    404 si la notificación no existe o pertenece a otro usuario, sin
    revelar cuál de los dos casos es.
    """

    http_method_names = ['post']

    def post(self, request, pk):
        """Marca la notificación como leída y vuelve a la página de origen.

        Args:
            request (HttpRequest): La request actual.
            pk (int): Identificador de la notificación.

        Returns:
            HttpResponseRedirect: A la URL indicada en ``next`` si es segura
            (por ejemplo, para conservar la página del listado), o al
            listado de notificaciones en caso contrario.
        """
        notificacion = get_object_or_404(NotificacionTasa, pk=pk, usuario=request.user)
        notificacion.marcar_como_leida()

        destino = request.POST.get('next')
        if destino and url_has_allowed_host_and_scheme(
            destino,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(destino)
        return redirect('divisas:mis_notificaciones')
