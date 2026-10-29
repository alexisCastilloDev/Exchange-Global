"""
Módulo de vistas para la aplicación de clientes.
"""
from decimal import Decimal
from urllib.parse import urlparse

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.template.response import TemplateResponse
from django.urls import Resolver404, resolve, reverse, reverse_lazy
from django.views import View
from django.views.decorators.http import require_POST  # Agregado para Metodos de Pago
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.authentication.decorators import requiere_rol
from apps.authentication.forms import CausaBajaForm
from apps.authentication.models import HistorialBaja
from apps.divisas.models import (
    CalculoOperacion,
    CalculoTriangulacion,
    Divisa,
    moneda_a_entregar,
    moneda_a_pagar,
    monto_a_entregar,
)
from .forms import AsociarUsuarioClienteForm, ClienteForm, MetodoPagoForm
from .models import Cliente, MetodoPago
from .validacion_sipap import SipapComunicacionError, validar_cuenta
from apps.users.services import sincronizar_usuarios_desde_keycloak

User = get_user_model()


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


# Pantallas de detalle de un registro ligado al cliente activo (por ejemplo,
# el detalle de una transacción del historial de un cliente): si el usuario
# cambia de cliente activo estando en una de estas pantallas, el registro de
# la URL (identificado por su pk) pertenece al cliente anterior y puede no
# existir para el nuevo, lo que rompería el "volver al referer" con un 404.
# En su lugar, cambiar de cliente desde ahí redirige al listado indicado.
DESTINO_AL_CAMBIAR_CLIENTE_DESDE_DETALLE = {
    'divisas:detalle_transaccion_operacion': 'divisas:mis_transacciones',
    'divisas:detalle_transaccion_cambio': 'divisas:mis_transacciones',
}


def _redireccion_tras_cambiar_cliente(referer):
    """Resuelve a dónde volver después de cambiar de cliente activo.

    Por defecto vuelve al ``referer`` tal cual. Si el ``referer`` es una
    pantalla de detalle de un registro del cliente anterior (ver
    ``DESTINO_AL_CAMBIAR_CLIENTE_DESDE_DETALLE``), vuelve al listado
    correspondiente en su lugar, porque ese registro puede no pertenecer al
    cliente nuevo.

    Args:
        referer (str): Valor de la cabecera ``HTTP_REFERER``, o ``None``.

    Returns:
        str: La URL a la que redirigir.
    """
    if not referer:
        return reverse('home')
    try:
        coincidencia = resolve(urlparse(referer).path)
    except Resolver404:
        return referer
    nombre_vista = (
        f'{coincidencia.namespace}:{coincidencia.url_name}'
        if coincidencia.namespace
        else coincidencia.url_name
    )
    destino = DESTINO_AL_CAMBIAR_CLIENTE_DESDE_DETALLE.get(nombre_vista)
    return reverse(destino) if destino else referer


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

    referer = request.META.get('HTTP_REFERER')
    return redirect(_redireccion_tras_cambiar_cliente(referer))


class PanelAdminView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """Lista y filtra clientes activos para el panel administrativo."""
    model = Cliente
    template_name = 'panel_admin.html'
    context_object_name = 'clientes'
    paginate_by = 10

    def get_queryset(self):
        """Obtiene clientes filtrados y usuarios activos precargados."""
        queryset = Cliente.activos.all()

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

        usuarios_activos = Prefetch(
            'usuarios',
            queryset=get_user_model().objects.filter(is_active=True),
        )
        return queryset.order_by('pk').prefetch_related(usuarios_activos)

    def get_context_data(self, **kwargs):
        """Agrega filtros y segmentos disponibles al contexto."""
        context = super().get_context_data(**kwargs)
        context['segmentos'] = Cliente.SEGMENTO_CHOICES
        context['segmento_actual'] = self.request.GET.get('segmento', '')
        context['busqueda'] = self.request.GET.get('q', '').strip()
        return context

    def test_func(self):
        """Permite el panel a personal administrativo autorizado."""
        user = self.request.user
        return user.is_staff or user.is_superuser

    def handle_no_permission(self):
        """Informa el rechazo y redirige al inicio."""
        messages.error(
            self.request,
            "No tienes los permisos necesarios para acceder a este panel.",
        )
        return redirect('home')


class ClienteDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """Muestra el detalle de un cliente y sus usuarios activos."""
    model = Cliente
    template_name = 'clientes/cliente_detail.html'
    context_object_name = 'cliente'

    def get_context_data(self, **kwargs):
        """Agrega los usuarios activos asociados al cliente."""
        context = super().get_context_data(**kwargs)
        context['usuarios_activos'] = self.object.usuarios.filter(is_active=True)
        return context

    def test_func(self):
        """Comprueba que el usuario tenga permisos administrativos."""
        return self.request.user.is_staff or self.request.user.is_superuser

    def handle_no_permission(self):
        """Informa el rechazo de acceso al detalle del cliente."""
        messages.error(
            self.request,
            "No tienes los permisos necesarios para acceder a esta ficha.",
        )
        return redirect('home')


class ClienteCreateView(
    LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, CreateView
):
    """Crea clientes desde el formulario administrativo."""
    model = Cliente
    form_class = ClienteForm
    template_name = 'clientes/cliente_form.html'
    success_url = reverse_lazy('home')

    def get_success_message(self, cleaned_data):
        """Construye el mensaje de alta con el nombre del cliente."""
        nombre_display = (
            self.object.razon_social
            if self.object.tipo_cliente == Cliente.TIPO_JURIDICA
            else f"{self.object.nombre} {self.object.apellido}"
        )
        return f"¡El cliente {nombre_display} ha sido registrado exitosamente!"

    def test_func(self):
        """Comprueba que el usuario pueda crear clientes."""
        return self.request.user.is_staff or self.request.user.is_superuser


class ClienteUpdateView(
    LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, UpdateView
):
    """Actualiza los datos de un cliente existente."""
    model = Cliente
    form_class = ClienteForm
    template_name = 'clientes/cliente_form.html'
    success_url = reverse_lazy('home')

    def get_success_message(self, cleaned_data):
        """Construye el mensaje de actualización del cliente."""
        nombre_display = (
            self.object.razon_social
            if self.object.tipo_cliente == Cliente.TIPO_JURIDICA
            else f"{self.object.nombre} {self.object.apellido}"
        )
        return f"¡Los datos de {nombre_display} se han actualizado correctamente!"

    def test_func(self):
        """Comprueba que el usuario pueda editar clientes."""
        return self.request.user.is_staff or self.request.user.is_superuser


class AsociarUsuariosClienteView(
    LoginRequiredMixin, UserPassesTestMixin, View
):
    """
    Módulo independiente para asociar/desasociar usuarios del sistema a un cliente.
    """

    template_name = 'clientes/asociar_usuarios.html'

    def test_func(self):
        """Comprueba que el usuario pueda administrar asociaciones."""
        return self.request.user.is_staff or self.request.user.is_superuser

    def _usuarios_cliente_ids(self):
        """Obtiene los usuarios activos que Keycloak identifica como clientes.

        Si la sincronización no está disponible, se devuelve una lista vacía:
        así nunca se habilita accidentalmente asociar a un usuario sin el rol
        requerido.
        """
        try:
            roles_por_usuario = sincronizar_usuarios_desde_keycloak()
        except Exception:
            messages.error(
                self.request,
                'No fue posible verificar los roles en Keycloak. '
                'No se modificaron las vinculaciones.',
            )
            return []
        return [
            user_id
            for user_id, roles in roles_por_usuario.items()
            if 'cliente' in roles
        ]

    def get(self, request, pk, *args, **kwargs):
        """Muestra usuarios elegibles y asociaciones actuales."""
        cliente = get_object_or_404(Cliente, pk=pk)
        usuarios_cliente = self._usuarios_cliente_ids()
        # Pre-seleccionar los usuarios que ya están vinculados
        form = AsociarUsuarioClienteForm(
            initial={'usuarios': cliente.usuarios.filter(pk__in=usuarios_cliente)},
            usuarios_cliente=usuarios_cliente,
        )
        return render(
            request, self.template_name, {'form': form, 'cliente': cliente}
        )

    def post(self, request, pk, *args, **kwargs):
        """Actualiza la relación de usuarios asociados al cliente."""
        cliente = get_object_or_404(Cliente, pk=pk)
        usuarios_cliente = self._usuarios_cliente_ids()
        form = AsociarUsuarioClienteForm(
            request.POST,
            usuarios_cliente=usuarios_cliente,
        )
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
    """Gestiona la confirmación y baja lógica de un cliente."""

    def test_func(self):
        """Comprueba que el usuario pueda dar de baja clientes."""
        return self.request.user.is_staff or self.request.user.is_superuser

    def get(self, request, pk, *args, **kwargs):
        """Muestra el formulario para confirmar la baja."""
        cliente = get_object_or_404(Cliente, pk=pk)
        return render(
            request,
            'bajas/confirmar_baja.html',
            {
                'form': CausaBajaForm(),
                'recurso_tipo': 'cliente',
                'recurso_nombre': cliente,
                'cancelar_url': reverse('panel_admin'),
            },
        )

    def post(self, request, pk, *args, **kwargs):
        """Valida la causa y registra la baja lógica del cliente."""
        cliente = get_object_or_404(Cliente, pk=pk)
        form = CausaBajaForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                'bajas/confirmar_baja.html',
                {
                    'form': form,
                    'recurso_tipo': 'cliente',
                    'recurso_nombre': cliente,
                    'cancelar_url': reverse('panel_admin'),
                },
            )
        if not cliente.is_active:
            messages.info(request, 'El cliente ya se encontraba inactivo.')
            return redirect('panel_admin')
        cliente.soft_delete()
        HistorialBaja.objects.create(
            tipo_recurso=HistorialBaja.TIPO_CLIENTE,
            recurso_id=cliente.pk,
            recurso_nombre=str(cliente),
            causa=form.cleaned_data['causa'],
            realizado_por=request.user,
        )
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


# ==============================================================================
# VISTAS PARA GE-19: Gestión de métodos de pago
# ==============================================================================

@requiere_rol('cliente')
def metodo_pago_list(request):
    """
    Muestra los métodos del cliente activo, con datos censurados.
    Solo clientes con un cliente activo seleccionado pueden verlo.

    En vez de una sola lista plana, agrupa las cuentas y billeteras por
    divisa (``grupos_por_divisa``, uno por cada ``Divisa`` activa,
    incluida una fila aunque esté vacía) y deja las tarjetas en su
    propia sección (``tarjetas``), ya que siempre son en PYG y no tiene
    sentido subdividirlas por divisa. Un grupo sin ningún medio marca
    de entrada que falta agregar uno: sin eso, el cliente no puede
    elegir nada para pagar ni para recibir una operación en esa divisa
    (ver ``apps.divisas.forms.PagarTransaccionForm``), así que conviene
    avisarlo antes de que lo descubra recién al intentar pagar.

    Una cuenta o billetera registrada antes de que existiera el campo
    ``MetodoPago.moneda`` (la migración de datos que agregó este campo
    deja esas filas en ``moneda=NULL`` a propósito, sin adivinar)
    quedaría invisible en cualquier agrupación por divisa: en vez de
    eso, se muestra aparte (``metodos_sin_divisa``) para que el cliente
    la vea y sepa que tiene que volver a registrarla, en vez de que
    desaparezca sin ningún aviso.
    """
    roles = request.session.get('keycloak_roles', [])
    if 'admin' in roles or 'cliente' not in roles:
        messages.error(request, 'No tenés permiso para acceder a métodos de pago.')
        return redirect('home')

    cliente_activo = getattr(request, 'cliente_activo', None)
    if cliente_activo is None:
        messages.error(request, 'No tenés clientes asociados para gestionar métodos de pago.')
        return redirect('home')

    metodos = list(MetodoPago.objects.filter(cliente=cliente_activo).select_related('moneda'))
    metodos_revelados = request.session.get('metodos_pago_revelados', [])

    tarjetas = [metodo for metodo in metodos if metodo.tipo_medio == MetodoPago.TIPO_TARJETA]
    metodos_por_divisa = [metodo for metodo in metodos if metodo.tipo_medio != MetodoPago.TIPO_TARJETA]
    metodos_sin_divisa = [metodo for metodo in metodos_por_divisa if metodo.moneda_id is None]
    grupos_por_divisa = [
        {
            'divisa': divisa,
            'metodos': [metodo for metodo in metodos_por_divisa if metodo.moneda_id == divisa.pk],
        }
        for divisa in Divisa.objects.filter(activa=True).order_by('codigo')
    ]
    return render(
        request,
        'clientes/metodo_pago_list.html',
        {
            'metodos': metodos,
            'metodos_revelados': metodos_revelados,
            'grupos_por_divisa': grupos_por_divisa,
            'tarjetas': tarjetas,
            'metodos_sin_divisa': metodos_sin_divisa,
        },
    )


def _movimientos_de_metodo_pago(metodo):
    """Reúne, de más reciente a más antiguo, todo lo que pasó por un método de pago en el sistema.

    No llama a Stripe ni a sipap-sim para esto: Global Exchange ya
    registra, en su propia base, cada pago (``Pago.metodo_pago``,
    poblado tanto para Stripe como para SIPAP — ver
    ``apps.divisas.pagos_stripe``/``pagos_sipap``) y cada entrega
    recibida (``CalculoOperacion``/``CalculoTriangulacion.medio_destino``,
    solo para cuentas y billeteras: una tarjeta nunca es un medio de
    destino). Reconstruir esto llamando a un proveedor externo
    duplicaría información que ya es exacta de este lado.

    Un "recibiste" solo cuenta si la entrega ya se completó
    (``ESTADO_ACREDITADA``/``ESTADO_RETIRADA``), nunca solo porque
    ``medio_destino`` ya quedó elegido: ese campo se fija al pagar, para
    los tres tipos de transacción por igual, un instante antes de que
    ``apps.divisas.entrega.realizar_entrega`` intente la transferencia
    de verdad — mostrarlo como recibido antes de que esa transferencia
    se resuelva sería un movimiento inventado.

    Returns:
        list[dict]: cada ítem con ``fecha``, ``direccion``
        (``'pagaste'`` o ``'recibiste'``), ``monto``, ``moneda``,
        ``estado`` (la etiqueta legible del estado efectivo de la
        transacción), ``transaccion`` y ``url_detalle`` (ya resuelta,
        para no tener que distinguir en el template si es una compra/venta
        o un cambio).
    """
    def _url_detalle(transaccion):
        if isinstance(transaccion, CalculoTriangulacion):
            return reverse('divisas:detalle_transaccion_cambio', kwargs={'pk': transaccion.pk})
        return reverse('divisas:detalle_transaccion_operacion', kwargs={'pk': transaccion.pk})

    movimientos = []
    pagos = metodo.pagos.select_related('calculo_operacion', 'calculo_triangulacion')
    for pago in pagos:
        transaccion = pago.transaccion
        movimientos.append({
            'fecha': pago.creado_en,
            'direccion': 'pagaste',
            'monto': pago.monto,
            'moneda': moneda_a_pagar(transaccion),
            'estado': transaccion.get_estado_efectivo_display(),
            'transaccion': transaccion,
            'url_detalle': _url_detalle(transaccion),
            'observado': pago.observado,
        })

    if metodo.tipo_medio != MetodoPago.TIPO_TARJETA:
        entregas = list(CalculoOperacion.objects.filter(
            medio_destino=metodo,
            estado__in=(CalculoOperacion.ESTADO_ACREDITADA, CalculoOperacion.ESTADO_RETIRADA),
        ))
        entregas += list(CalculoTriangulacion.objects.filter(
            medio_destino=metodo, estado=CalculoTriangulacion.ESTADO_ACREDITADA,
        ))
        for transaccion in entregas:
            # "retirado_en" solo existe en CalculoOperacion (una venta);
            # getattr con default evita el AttributeError en un cambio. Si
            # ninguna de las dos quedó registrada (fixtures de prueba
            # antiguas que fuerzan el estado a mano), cae a una fecha
            # igual de razonable en vez de dejar la ordenación sin fecha.
            fecha = (
                getattr(transaccion, 'retirado_en', None)
                or transaccion.acreditado_en
                or transaccion.confirmado_en
                or transaccion.creado_en
            )
            movimientos.append({
                'fecha': fecha,
                'direccion': 'recibiste',
                'monto': monto_a_entregar(transaccion),
                'moneda': moneda_a_entregar(transaccion),
                'estado': transaccion.get_estado_efectivo_display(),
                'transaccion': transaccion,
                'url_detalle': _url_detalle(transaccion),
                'observado': False,
            })

    movimientos.sort(key=lambda movimiento: movimiento['fecha'], reverse=True)
    return movimientos


@requiere_rol('cliente')
def metodo_pago_movimientos(request, pk):
    """Muestra los movimientos y, si corresponde, el saldo real de un método de pago propio.

    "Movimientos" se arma siempre con datos propios (ver
    ``_movimientos_de_metodo_pago``): nunca depende de que sipap-sim o
    Stripe respondan. El "saldo", en cambio, es información que solo
    existe del otro lado, así que si no se puede consultar no hay
    ningún valor local al que recurrir:

    - Cuenta bancaria o billetera: se le vuelve a preguntar a sipap-sim
      por esa cuenta puntual (``apps.clientes.validacion_sipap.validar_cuenta``,
      el mismo endpoint que ya se usa al registrarla), para mostrar el
      saldo real en este momento, no uno guardado que podría haber
      quedado desactualizado.
    - Tarjeta: no se muestra ningún saldo. Stripe es un procesador de
      pagos, no el banco emisor de la tarjeta: no tiene (ni expone) el
      saldo disponible o el límite de crédito de una tarjeta ajena, así
      que mostrar un número ahí sería inventado.
    """
    roles = request.session.get('keycloak_roles', [])
    if 'admin' in roles or 'cliente' not in roles:
        messages.error(request, 'No tenés permiso para acceder a métodos de pago.')
        return redirect('home')

    cliente_activo = getattr(request, 'cliente_activo', None)
    if cliente_activo is None:
        messages.error(request, 'No tenés clientes asociados para gestionar métodos de pago.')
        return redirect('home')

    metodo = get_object_or_404(MetodoPago, pk=pk)
    if metodo.cliente_id != cliente_activo.id:
        messages.error(request, 'Ese método de pago no te pertenece.')
        return redirect('clientes:metodo_pago_list')

    saldo = None
    error_saldo = None
    if metodo.tipo_medio != MetodoPago.TIPO_TARJETA:
        try:
            datos = validar_cuenta(metodo.numero_cuenta, metodo.documento_titular)
        except SipapComunicacionError:
            error_saldo = 'No se pudo conectar con sipap-sim para consultar el saldo. Intentá nuevamente en unos minutos.'
        else:
            if datos.get('valida'):
                saldo = {'monto': Decimal(str(datos['saldo'])), 'moneda': datos['moneda']}
            else:
                error_saldo = 'Esta cuenta ya no se pudo verificar en sipap-sim.'

    return render(request, 'clientes/metodo_pago_movimientos.html', {
        'metodo': metodo,
        'saldo': saldo,
        'error_saldo': error_saldo,
        'movimientos': _movimientos_de_metodo_pago(metodo),
    })


@requiere_rol('cliente')
@require_POST
def metodo_pago_reveal(request, pk):
    """Alterna la visualización completa para el cliente activo que lo registró."""
    roles = request.session.get('keycloak_roles', [])
    if 'admin' in roles or 'cliente' not in roles:
        return redirect('home')

    cliente_activo = getattr(request, 'cliente_activo', None)
    if cliente_activo is None:
        return redirect('home')

    metodo = get_object_or_404(MetodoPago, pk=pk)
    if metodo.cliente_id != cliente_activo.id:
        return redirect('clientes:metodo_pago_list')

    metodos_revelados = request.session.get('metodos_pago_revelados', [])
    if metodo.pk in metodos_revelados:
        metodos_revelados.remove(metodo.pk)
    else:
        metodos_revelados.append(metodo.pk)
    request.session['metodos_pago_revelados'] = metodos_revelados
    request.session.modified = True
    return redirect('clientes:metodo_pago_list')


@requiere_rol('cliente')
def metodo_pago_create(request):
    """
    Permite registrar un nuevo método de pago para el cliente activo (Criterio 1 y 2).
    Solo los clientes con un cliente activo seleccionado pueden gestionarlos.
    """
    roles = request.session.get('keycloak_roles', [])
    if 'admin' in roles or 'cliente' not in roles:
        messages.error(request, 'No tenés permiso para acceder a métodos de pago.')
        return redirect('home')

    cliente_activo = getattr(request, 'cliente_activo', None)
    if cliente_activo is None:
        messages.error(request, 'No tenés clientes asociados para gestionar métodos de pago.')
        return redirect('home')

    if request.method == 'POST':
        form = MetodoPagoForm(request.POST)
        if form.is_valid():
            metodo = form.save(commit=False)
            metodo.cliente = cliente_activo
            metodo.save()
            messages.success(request, 'Método de pago agregado exitosamente.')
            return redirect('clientes:metodo_pago_list')
        else:
            messages.error(request, 'Por favor, corrija los errores en el formulario.')
    else:
        form = MetodoPagoForm()

    response = TemplateResponse(
        request,
        'clientes/metodo_pago_form.html',
        {'form': form, 'titulo': 'Agregar Método de Pago'}
    )
    response.context_data = {'form': form, 'titulo': 'Agregar Método de Pago'}
    response.context = response.context_data
    response.render()
    return response


@requiere_rol('cliente')
def metodo_pago_delete(request, pk):
    """
    Confirma y elimina un método de pago del cliente activo (Criterio 5).
    Solo los clientes con un cliente activo seleccionado pueden gestionarlos.
    """
    roles = request.session.get('keycloak_roles', [])
    if 'admin' in roles or 'cliente' not in roles:
        messages.error(request, 'No tenés permiso para acceder a métodos de pago.')
        return redirect('home')

    cliente_activo = getattr(request, 'cliente_activo', None)
    if cliente_activo is None:
        messages.error(request, 'No tenés clientes asociados para gestionar métodos de pago.')
        return redirect('home')

    metodo = get_object_or_404(MetodoPago, pk=pk, cliente=cliente_activo)
    if request.method == 'POST':
        metodo.delete()
        messages.success(request, 'El método de pago fue removido exitosamente.')
        return redirect('clientes:metodo_pago_list')

    return render(request, 'clientes/metodo_pago_confirm_delete.html', {'metodo': metodo})


@requiere_rol('cliente')
@require_POST
def metodo_pago_set_default(request, pk):
    """
    Establece un método de pago específico como el predeterminado en su divisa
    (Criterio 6). El predeterminado es independiente por divisa (ver
    ``MetodoPago.save``): esto nunca le quita el flag a un método predeterminado
    en otra divisa distinta. Solo los clientes con un cliente activo
    seleccionado pueden gestionarlos.
    """
    roles = request.session.get('keycloak_roles', [])
    if 'admin' in roles or 'cliente' not in roles:
        messages.error(request, 'No tenés permiso para acceder a métodos de pago.')
        return redirect('home')

    cliente_activo = getattr(request, 'cliente_activo', None)
    if cliente_activo is None:
        messages.error(request, 'No tenés clientes asociados para gestionar métodos de pago.')
        return redirect('home')

    metodo = get_object_or_404(MetodoPago, pk=pk, cliente=cliente_activo)
    metodo.es_predeterminado = True
    metodo.save()
    divisa = metodo.moneda.codigo if metodo.moneda_id else 'sin divisa confirmada'
    messages.success(request, f'"{metodo}" ha sido establecido como método predeterminado ({divisa}).')
    return redirect('clientes:metodo_pago_list')


class ClienteHistorialBajasView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """Lista el historial de bajas lógicas de clientes."""
    model = HistorialBaja
    template_name = 'bajas/historial_bajas.html'
    context_object_name = 'registros'

    def test_func(self):
        """Comprueba que el usuario pueda consultar el historial."""
        return self.request.user.is_staff or self.request.user.is_superuser

    def get_queryset(self):
        """Devuelve bajas de clientes junto con el usuario que las realizó."""
        return HistorialBaja.objects.filter(
            tipo_recurso=HistorialBaja.TIPO_CLIENTE
        ).select_related('realizado_por')

    def get_context_data(self, **kwargs):
        """Agrega título y navegación de retorno al contexto."""
        context = super().get_context_data(**kwargs)
        context['titulo'] = 'Historial de bajas de clientes'
        context['volver_url'] = reverse('panel_admin')
        return context
