"""Vistas para la apertura, consulta, operaciones de ventanilla, movimientos extraordinarios y arqueo de la caja de un cajero."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.caja.forms import (
    AperturaCajaForm,
    ArqueoCajaForm,
    MovimientoExtraordinarioForm,
    OperacionVentanillaForm,
)
from apps.caja.models import (
    ArqueoCaja,
    Caja,
    DetalleArqueoCaja,
    MovimientoExtraordinario,
    OperacionVentanilla,
    SaldoInicialCaja,
)
from apps.divisas.models import CalculoOperacion, Divisa
from apps.divisas.views import _calcular_importe_operacion


def _avisar_divisas_sin_cotizar(request, form):
    """Informa qué divisas activas no se pueden incluir por falta de cotización.

    Usada tanto por ``AperturaCajaForm`` (saldo inicial) como por
    ``ArqueoCajaForm`` (monto contado): ninguna de las dos HU es, en sí
    misma, sobre cotizaciones, pero una divisa sin ninguna cotización
    vigente no se puede valuar — dejar que el cajero le cuente un monto
    igual sería un dato que ningún otro cálculo del sistema (cambio,
    saldo actual, arqueo) podría usar de forma confiable.
    """
    if not form.divisas_sin_cotizar:
        return
    codigos = ', '.join(divisa.codigo for divisa in form.divisas_sin_cotizar)
    messages.warning(
        request,
        f'Hace falta cotizar {codigos} antes de poder manejarla en una caja. '
        'Contactate con un analista cambiario o un administrador.',
    )


class AbrirCajaView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Permite a un cajero abrir su caja registrando el saldo inicial por moneda.

    Implementa la HU "Apertura de Caja". Si el cajero ya tiene una caja en
    estado "Abierta", rechaza la acción y lo manda a su panel en vez de
    mostrar el formulario (Criterio 2); la vista solo construye la
    transacción con los datos ya validados por ``AperturaCajaForm``
    (Criterio 3: un monto negativo o no numérico no llega a crear nada).
    """

    def test_func(self):
        """Solo el rol cajero puede abrir una caja (Criterio 5)."""
        roles = self.request.session.get('keycloak_roles', [])
        return 'cajero' in roles

    def get(self, request, *args, **kwargs):
        """Muestra el formulario de apertura, o por qué no se puede abrir otra."""
        caja_abierta = Caja.objects.filter(usuario=request.user, estado=Caja.ESTADO_ABIERTA).first()
        if caja_abierta is not None:
            messages.error(request, 'Ya tenés una caja abierta. Cerrala antes de abrir otra.')
            return redirect('caja:panel')
        form = AperturaCajaForm()
        _avisar_divisas_sin_cotizar(request, form)
        return render(request, 'caja/abrir_caja.html', {'form': form})

    def post(self, request, *args, **kwargs):
        """Valida el saldo inicial de cada divisa y crea la caja "Abierta".

        Args:
            request (HttpRequest): Solicitud POST con un campo
                ``saldo_<divisa.pk>`` por cada divisa activa.

        Returns:
            HttpResponse: Redirección al panel de caja, con la caja recién
            creada, o el mismo formulario con los errores de validación.
        """
        caja_abierta = Caja.objects.filter(usuario=request.user, estado=Caja.ESTADO_ABIERTA).first()
        if caja_abierta is not None:
            messages.error(request, 'Ya tenés una caja abierta. Cerrala antes de abrir otra.')
            return redirect('caja:panel')

        form = AperturaCajaForm(request.POST)
        _avisar_divisas_sin_cotizar(request, form)
        if not form.is_valid():
            return render(request, 'caja/abrir_caja.html', {'form': form})

        try:
            with transaction.atomic():
                caja = Caja.objects.create(usuario=request.user)
                SaldoInicialCaja.objects.bulk_create([
                    SaldoInicialCaja(caja=caja, divisa=divisa, monto=monto)
                    for divisa, monto in form.saldos_por_divisa().items()
                ])
        except IntegrityError:
            # Carrera entre dos pestañas abriendo caja casi al mismo tiempo:
            # la otra ganó y ya existe una "Abierta" (restricción de base
            # en Caja.Meta.constraints), así que no es un error real.
            messages.error(request, 'Ya tenés una caja abierta. Cerrala antes de abrir otra.')
            return redirect('caja:panel')

        messages.success(request, 'La caja fue abierta correctamente.')
        return redirect('caja:panel')


class CerrarCajaView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Muestra el resumen del turno y permite confirmar el cierre de la caja abierta del cajero.

    Implementa la HU "Cierre de Caja". El resumen (Criterio 1) incluye, por
    cada moneda contada al abrir, el saldo inicial y el saldo final
    (``Caja.saldo_actual``, que ya incluye lo registrado en ventanilla y en
    movimientos extraordinarios), más el detalle completo de ambos y de los
    arqueos del turno. Sin una caja abierta, no hay nada que cerrar y la
    vista redirige al panel. Si el turno no tiene ningún arqueo registrado,
    el resumen muestra una advertencia y el cierre solo se procesa si el
    cajero marca explícitamente que quiere continuar sin arquear
    (Criterio 3); al confirmarse, ``Caja.cerrar`` persiste la transición a
    "Cerrada" (Criterio 2).
    """

    def test_func(self):
        """Solo el rol cajero puede cerrar su caja (mismo criterio que el resto de caja)."""
        roles = self.request.session.get('keycloak_roles', [])
        return 'cajero' in roles

    @staticmethod
    def _caja_abierta_o_redireccion(request):
        """Resuelve la caja abierta del cajero, o la redirección a devolver si no tiene una."""
        caja = Caja.objects.filter(usuario=request.user, estado=Caja.ESTADO_ABIERTA).first()
        if caja is None:
            messages.error(request, 'No tenés una caja abierta para cerrar.')
            return None, redirect('caja:panel')
        return caja, None

    @staticmethod
    def _contexto_resumen(caja):
        """Construye el resumen del turno: saldo inicial y final por moneda, y lo registrado."""
        saldos = [
            (saldo_inicial.divisa, saldo_inicial.monto, caja.saldo_actual(saldo_inicial.divisa))
            for saldo_inicial in caja.saldos_iniciales.select_related('divisa').all()
        ]
        return {
            'caja': caja,
            'saldos': saldos,
            'operaciones': caja.operaciones.select_related('divisa'),
            'movimientos_extraordinarios': caja.movimientos_extraordinarios.select_related('divisa'),
            'arqueos': caja.arqueos.all(),
            'tiene_arqueos': caja.arqueos.exists(),
        }

    def get(self, request, *args, **kwargs):
        """Muestra el resumen del turno antes de confirmar el cierre."""
        caja, redireccion = self._caja_abierta_o_redireccion(request)
        if redireccion is not None:
            return redireccion
        return render(request, 'caja/cerrar_caja.html', self._contexto_resumen(caja))

    def post(self, request, *args, **kwargs):
        """Confirma el cierre, exigiendo confirmación explícita si el turno no tiene arqueos.

        Args:
            request (HttpRequest): Solicitud POST, con ``confirmar_sin_arqueo``
                (``'on'``) marcado si el turno no tiene ningún arqueo
                registrado y el cajero quiere cerrar igual.

        Returns:
            HttpResponse: Redirección al panel de caja si el cierre se
            procesa, o el mismo resumen con la advertencia si falta
            confirmar explícitamente.
        """
        caja, redireccion = self._caja_abierta_o_redireccion(request)
        if redireccion is not None:
            return redireccion

        contexto = self._contexto_resumen(caja)
        if not contexto['tiene_arqueos'] and request.POST.get('confirmar_sin_arqueo') != 'on':
            messages.error(
                request,
                'Esta caja no tiene ningún arqueo registrado en el turno. Marcá la '
                'confirmación si querés cerrarla igual.',
            )
            return render(request, 'caja/cerrar_caja.html', contexto)

        caja.cerrar()
        messages.success(request, 'La caja fue cerrada correctamente.')
        return redirect('caja:panel')


class PanelCajaView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Muestra la caja abierta del cajero, con el saldo inicial por moneda.

    Implementa el Criterio 4 de "Apertura de Caja": tras abrir la caja, el
    cajero ve en su panel el saldo inicial tal como lo registró. Si no
    tiene ninguna caja abierta, ofrece el acceso para abrir una.
    """

    def test_func(self):
        """Solo el rol cajero puede ver el panel de caja (Criterio 5)."""
        roles = self.request.session.get('keycloak_roles', [])
        return 'cajero' in roles

    def get(self, request, *args, **kwargs):
        """Muestra la caja abierta del cajero, con su saldo actual por moneda."""
        caja = (
            Caja.objects.filter(usuario=request.user, estado=Caja.ESTADO_ABIERTA)
            .prefetch_related('saldos_iniciales__divisa', 'operaciones__divisa')
            .first()
        )
        saldos_actuales = []
        operaciones = []
        movimientos_extraordinarios = []
        if caja is not None:
            divisas = Divisa.objects.filter(activa=True).order_by('codigo')
            saldos_actuales = [(divisa, caja.saldo_actual(divisa)) for divisa in divisas]
            operaciones = caja.operaciones.select_related('divisa')[:20]
            movimientos_extraordinarios = caja.movimientos_extraordinarios.select_related('divisa')[:20]
        return render(
            request,
            'caja/panel_caja.html',
            {
                'caja': caja,
                'saldos_actuales': saldos_actuales,
                'operaciones': operaciones,
                'movimientos_extraordinarios': movimientos_extraordinarios,
            },
        )


class RegistrarOperacionVentanillaView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Registra, para la caja abierta del cajero, una compra o venta de divisas en efectivo.

    Implementa la HU "Gestión de operaciones en ventanilla": reutiliza el
    cálculo de cotización ya existente para el flujo online del cliente
    (``apps.divisas.views._calcular_importe_operacion``) en vez de
    duplicarlo, pero invirtiendo el tipo que se le pasa — ver
    ``apps.caja.models.OperacionVentanilla`` para la explicación completa de
    por qué "Compra"/"Venta" significan lo opuesto en una y otra HU. Sin una
    caja abierta, rechaza la acción e indica abrir una primero (Criterio 2);
    con saldo insuficiente de la moneda que el cajero debe entregar, también
    la rechaza e informa el motivo (Criterio 3).

    Una compra necesita, además, poder valuar guaraníes contra una
    ``apps.divisas.models.Divisa`` de código ``PYG``: su existencia está
    garantizada por la migración de datos ``apps.divisas.0014_crear_divisa_pyg``
    (PYG es la moneda local/base del sistema, no una divisa extranjera que
    un administrador deba dar de alta manualmente), así que esta vista no
    necesita manejar su ausencia como un caso de error.
    """

    def test_func(self):
        """Solo el rol cajero puede registrar operaciones de ventanilla (mismo criterio que el resto de caja)."""
        roles = self.request.session.get('keycloak_roles', [])
        return 'cajero' in roles

    @staticmethod
    def _normalizar_tipo(tipo):
        """Normaliza el tipo recibido por URL y valida que sea 'compra' o 'venta'.

        Args:
            tipo (str): Tipo indicado en la ruta (por ejemplo ``compra``).

        Returns:
            str: El tipo en mayúsculas, ``COMPRA`` o ``VENTA``.

        Raises:
            Http404: Si el tipo no corresponde a una operación conocida.
        """
        tipo = tipo.upper()
        if tipo not in dict(OperacionVentanilla.TIPO_CHOICES):
            raise Http404('El tipo de operación de ventanilla solicitado no existe.')
        return tipo

    def _caja_abierta_o_redireccion(self, request):
        """Resuelve la caja abierta del cajero, o la redirección a devolver si no tiene una.

        Returns:
            tuple: ``(caja, None)`` si tiene una caja abierta, o
            ``(None, HttpResponse)`` con la redirección que corresponde
            devolver en su lugar (Criterio 2).
        """
        caja = Caja.objects.filter(usuario=request.user, estado=Caja.ESTADO_ABIERTA).first()
        if caja is None:
            messages.error(
                request,
                'Necesitás abrir una caja antes de registrar una operación de ventanilla.',
            )
            return None, redirect('caja:abrir')
        return caja, None

    def get(self, request, *args, **kwargs):
        """Muestra el formulario de registro, o por qué no se puede usar todavía."""
        tipo = self._normalizar_tipo(kwargs['tipo'])
        caja, redireccion = self._caja_abierta_o_redireccion(request)
        if redireccion is not None:
            return redireccion
        form = OperacionVentanillaForm()
        return render(request, 'caja/operacion_ventanilla.html', {'form': form, 'tipo': tipo, 'caja': caja})

    def post(self, request, *args, **kwargs):
        """Valida el monto, calcula con la cotización vigente y registra la operación.

        Args:
            request (HttpRequest): Solicitud POST con los campos ``divisa``
                y ``monto`` (ver ``OperacionVentanillaForm``).

        Returns:
            HttpResponse: Redirección al panel de caja si la operación se
            registra correctamente, o el mismo formulario con el error de
            validación o de saldo insuficiente.
        """
        tipo = self._normalizar_tipo(kwargs['tipo'])
        caja, redireccion = self._caja_abierta_o_redireccion(request)
        if redireccion is not None:
            return redireccion

        form = OperacionVentanillaForm(request.POST)
        if not form.is_valid():
            return render(request, 'caja/operacion_ventanilla.html', {'form': form, 'tipo': tipo, 'caja': caja})

        divisa = form.divisa_seleccionada()
        monto = form.cleaned_data['monto']
        cotizacion = divisa.ultima_cotizacion

        # Invertido a propósito: "Compra" en esta HU (la casa le compra
        # divisa al cliente) es lo mismo que "Venta" para
        # _calcular_importe_operacion (el cliente le vende divisa a la
        # casa), y viceversa. Ver OperacionVentanilla para el detalle.
        tipo_calculo = (
            CalculoOperacion.TIPO_VENTA if tipo == OperacionVentanilla.TIPO_COMPRA
            else CalculoOperacion.TIPO_COMPRA
        )
        tasa_aplicada, porcentaje, comision, monto_pyg = _calcular_importe_operacion(
            tipo_calculo, monto, cotizacion.tasa_compra, cotizacion.tasa_venta,
        )

        # Lo que el cajero debe entregar (Criterio 3): la divisa en una
        # venta, guaraníes en una compra. PYG es la divisa local/base del
        # sistema (ver la migración apps.divisas.0014_crear_divisa_pyg): no
        # es una divisa extranjera que un administrador deba dar de alta
        # manualmente, así que su fila en el catálogo está garantizada.
        if tipo == OperacionVentanilla.TIPO_VENTA:
            divisa_a_entregar, monto_a_entregar = divisa, monto
        else:
            divisa_a_entregar, monto_a_entregar = Divisa.objects.get(codigo='PYG'), monto_pyg

        saldo_disponible = caja.saldo_actual(divisa_a_entregar)
        if saldo_disponible < monto_a_entregar:
            messages.error(
                request,
                f'Saldo insuficiente de {divisa_a_entregar.codigo} en la caja: hay '
                f'{saldo_disponible} y se necesitan {monto_a_entregar} para completar la operación.',
            )
            return render(request, 'caja/operacion_ventanilla.html', {'form': form, 'tipo': tipo, 'caja': caja})

        OperacionVentanilla.objects.create(
            caja=caja,
            cajero=request.user,
            tipo=tipo,
            divisa=divisa,
            monto_divisa=monto,
            tasa_aplicada=tasa_aplicada,
            comision_porcentaje=porcentaje,
            comision=comision,
            monto_pyg=monto_pyg,
        )
        messages.success(request, 'La operación se registró correctamente y el saldo de la caja fue actualizado.')
        return redirect('caja:panel')


class RegistrarMovimientoExtraordinarioView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Registra, para la caja abierta del cajero, un ingreso o egreso extraordinario de efectivo.

    Implementa la HU "Gestión de movimientos extraordinarios de Caja": a
    diferencia de ``RegistrarOperacionVentanillaView``, no calcula ninguna
    tasa ni comisión — el cajero indica directamente la divisa, el monto y
    el motivo del movimiento (ver ``apps.caja.models.MovimientoExtraordinario``).
    Sin una caja abierta, rechaza la acción e indica abrir una primero
    (mismo criterio que el resto de las funciones de caja); con saldo
    insuficiente de la divisa para un egreso, también la rechaza e informa
    el motivo (Criterio 2).
    """

    def test_func(self):
        """Solo el rol cajero puede registrar movimientos extraordinarios (mismo criterio que el resto de caja)."""
        roles = self.request.session.get('keycloak_roles', [])
        return 'cajero' in roles

    @staticmethod
    def _normalizar_tipo(tipo):
        """Normaliza el tipo recibido por URL y valida que sea 'ingreso' o 'egreso'.

        Args:
            tipo (str): Tipo indicado en la ruta (por ejemplo ``ingreso``).

        Returns:
            str: El tipo en mayúsculas, ``INGRESO`` o ``EGRESO``.

        Raises:
            Http404: Si el tipo no corresponde a un movimiento conocido.
        """
        tipo = tipo.upper()
        if tipo not in dict(MovimientoExtraordinario.TIPO_CHOICES):
            raise Http404('El tipo de movimiento extraordinario solicitado no existe.')
        return tipo

    @staticmethod
    def _caja_abierta_o_redireccion(request):
        """Resuelve la caja abierta del cajero, o la redirección a devolver si no tiene una."""
        caja = Caja.objects.filter(usuario=request.user, estado=Caja.ESTADO_ABIERTA).first()
        if caja is None:
            messages.error(
                request,
                'Necesitás abrir una caja antes de registrar un movimiento extraordinario.',
            )
            return None, redirect('caja:abrir')
        return caja, None

    def get(self, request, *args, **kwargs):
        """Muestra el formulario de registro, o por qué no se puede usar todavía."""
        tipo = self._normalizar_tipo(kwargs['tipo'])
        caja, redireccion = self._caja_abierta_o_redireccion(request)
        if redireccion is not None:
            return redireccion
        form = MovimientoExtraordinarioForm()
        return render(
            request, 'caja/movimiento_extraordinario.html', {'form': form, 'tipo': tipo, 'caja': caja},
        )

    def post(self, request, *args, **kwargs):
        """Valida la divisa, el monto y el motivo, y registra el movimiento si hay saldo suficiente.

        Args:
            request (HttpRequest): Solicitud POST con los campos ``divisa``,
                ``monto`` y ``motivo`` (ver ``MovimientoExtraordinarioForm``).

        Returns:
            HttpResponse: Redirección al panel de caja si el movimiento se
            registra correctamente, o el mismo formulario con el error de
            validación o de saldo insuficiente.
        """
        tipo = self._normalizar_tipo(kwargs['tipo'])
        caja, redireccion = self._caja_abierta_o_redireccion(request)
        if redireccion is not None:
            return redireccion

        form = MovimientoExtraordinarioForm(request.POST)
        if not form.is_valid():
            return render(
                request, 'caja/movimiento_extraordinario.html', {'form': form, 'tipo': tipo, 'caja': caja},
            )

        divisa = form.divisa_seleccionada()
        monto = form.cleaned_data['monto']

        if tipo == MovimientoExtraordinario.TIPO_EGRESO:
            saldo_disponible = caja.saldo_actual(divisa)
            if saldo_disponible < monto:
                messages.error(
                    request,
                    f'Saldo insuficiente de {divisa.codigo} en la caja: hay '
                    f'{saldo_disponible} y se necesitan {monto} para registrar este egreso.',
                )
                return render(
                    request, 'caja/movimiento_extraordinario.html', {'form': form, 'tipo': tipo, 'caja': caja},
                )

        MovimientoExtraordinario.objects.create(
            caja=caja,
            cajero=request.user,
            tipo=tipo,
            divisa=divisa,
            monto=monto,
            motivo=form.cleaned_data['motivo'],
        )
        messages.success(request, 'El movimiento extraordinario se registró correctamente.')
        return redirect('caja:panel')


class IniciarArqueoCajaView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Registra un arqueo, comparando lo que el cajero contó contra el saldo que calcula el sistema.

    Implementa la HU "Arqueo de Caja". Sin una caja abierta, rechaza la
    acción e indica abrir una primero, igual que el resto de las funciones
    de caja. El registro nunca se bloquea por una diferencia: cualquier
    combinación de sobrantes o faltantes se guarda igual (Criterio 2); la
    comparación en sí (Criterio 1) y los datos que quedan disponibles para
    consulta posterior (Criterio 3) los resuelve ``apps.caja.models.ArqueoCaja``/
    ``DetalleArqueoCaja``. Una divisa activa sin cotización vigente no recibe
    campo en ``ArqueoCajaForm``, para no comparar el saldo del sistema contra
    un monto contado que no se puede valuar de forma confiable.
    """

    def test_func(self):
        """Solo el rol cajero puede iniciar un arqueo (mismo criterio que el resto de caja)."""
        roles = self.request.session.get('keycloak_roles', [])
        return 'cajero' in roles

    @staticmethod
    def _caja_abierta_o_redireccion(request):
        """Resuelve la caja abierta del cajero, o la redirección a devolver si no tiene una."""
        caja = Caja.objects.filter(usuario=request.user, estado=Caja.ESTADO_ABIERTA).first()
        if caja is None:
            messages.error(request, 'Necesitás abrir una caja antes de iniciar un arqueo.')
            return None, redirect('caja:abrir')
        return caja, None

    def get(self, request, *args, **kwargs):
        """Muestra el formulario de arqueo, o por qué no se puede usar todavía."""
        caja, redireccion = self._caja_abierta_o_redireccion(request)
        if redireccion is not None:
            return redireccion
        form = ArqueoCajaForm()
        _avisar_divisas_sin_cotizar(request, form)
        return render(request, 'caja/arqueo_form.html', {'form': form, 'caja': caja})

    def post(self, request, *args, **kwargs):
        """Valida los montos contados, compara contra el saldo actual y registra el arqueo.

        Args:
            request (HttpRequest): Solicitud POST con un campo
                ``contado_<divisa.pk>`` por cada divisa activa.

        Returns:
            HttpResponse: Redirección al detalle del arqueo recién creado,
            o el mismo formulario con los errores de validación.
        """
        caja, redireccion = self._caja_abierta_o_redireccion(request)
        if redireccion is not None:
            return redireccion

        form = ArqueoCajaForm(request.POST)
        _avisar_divisas_sin_cotizar(request, form)
        if not form.is_valid():
            return render(request, 'caja/arqueo_form.html', {'form': form, 'caja': caja})

        with transaction.atomic():
            arqueo = ArqueoCaja.objects.create(caja=caja, cajero=request.user)
            DetalleArqueoCaja.objects.bulk_create([
                DetalleArqueoCaja(
                    arqueo=arqueo,
                    divisa=divisa,
                    saldo_sistema=caja.saldo_actual(divisa),
                    monto_contado=monto_contado,
                )
                for divisa, monto_contado in form.montos_por_divisa().items()
            ])

        messages.success(request, 'El arqueo se registró correctamente.')
        return redirect('caja:detalle_arqueo', pk=arqueo.pk)


class DetalleArqueoCajaView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Muestra el detalle de un arqueo ya registrado, para consulta posterior (Criterio 3).

    Solo el cajero que lo registró puede consultarlo: mismo alcance que el
    resto de las funciones de caja, donde cada cajero ve únicamente lo suyo.
    """

    def test_func(self):
        """Solo el rol cajero puede consultar el detalle de un arqueo."""
        roles = self.request.session.get('keycloak_roles', [])
        return 'cajero' in roles

    def get(self, request, *args, **kwargs):
        """Muestra fecha, hora, cajero y los montos contados frente a los del sistema."""
        arqueo = get_object_or_404(
            ArqueoCaja.objects.select_related('caja', 'cajero').prefetch_related('detalles__divisa'),
            pk=kwargs['pk'], cajero=request.user,
        )
        return render(request, 'caja/arqueo_detalle.html', {'arqueo': arqueo})


class HistorialArqueosCajaView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Lista los arqueos ya registrados por el cajero, para consulta posterior (Criterio 3)."""

    def test_func(self):
        """Solo el rol cajero puede consultar su historial de arqueos."""
        roles = self.request.session.get('keycloak_roles', [])
        return 'cajero' in roles

    def get(self, request, *args, **kwargs):
        """Lista los arqueos del cajero, del más reciente al más antiguo."""
        arqueos = (
            ArqueoCaja.objects.filter(cajero=request.user)
            .select_related('caja')
            .prefetch_related('detalles__divisa')
        )
        return render(request, 'caja/arqueo_historial.html', {'arqueos': arqueos})


class HistorialCajasView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Lista las cajas del cajero, abiertas y cerradas, con su balance final por moneda.

    Implementa el Criterio 4 de "Cierre de Caja": una caja ya cerrada queda
    disponible para consulta posterior, con su período (``abierta_en``/
    ``cerrada_en``) y su balance final por moneda (``Caja.saldo_actual``,
    estable desde el cierre porque ninguna vista vuelve a escribir sobre una
    caja "Cerrada"). Esta pantalla es de solo lectura, igual que el resto
    del historial de caja: no ofrece ninguna acción para modificar las
    operaciones de una caja ya registrada.
    """

    def test_func(self):
        """Solo el rol cajero puede consultar su historial de cajas."""
        roles = self.request.session.get('keycloak_roles', [])
        return 'cajero' in roles

    def get(self, request, *args, **kwargs):
        """Lista las cajas del cajero, de la más reciente a la más antigua, con su saldo por moneda."""
        cajas = Caja.objects.filter(usuario=request.user).prefetch_related('saldos_iniciales__divisa')
        filas = [
            {
                'caja': caja,
                'saldos': [
                    (saldo_inicial.divisa, caja.saldo_actual(saldo_inicial.divisa))
                    for saldo_inicial in caja.saldos_iniciales.all()
                ],
            }
            for caja in cajas
        ]
        return render(request, 'caja/historial_cajas.html', {'filas': filas})
