"""Vistas para la apertura, consulta y operaciones de ventanilla de la caja de un cajero."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.views import View

from apps.caja.forms import AperturaCajaForm, OperacionVentanillaForm
from apps.caja.models import Caja, OperacionVentanilla, SaldoInicialCaja
from apps.divisas.models import CalculoOperacion, Divisa
from apps.divisas.views import _calcular_importe_operacion


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

    @staticmethod
    def _avisar_divisas_sin_cotizar(request, form):
        """Informa qué divisas activas no se pueden incluir por falta de cotización.

        No es un criterio de aceptación de esta HU en sí, pero una divisa
        sin ninguna cotización vigente no se puede valuar: dejar que el
        cajero le cuente un saldo inicial igual sería un dato que ningún
        otro cálculo del sistema (cambio, arqueo futuro) podría usar.
        """
        if not form.divisas_sin_cotizar:
            return
        codigos = ', '.join(divisa.codigo for divisa in form.divisas_sin_cotizar)
        messages.warning(
            request,
            f'Hace falta cotizar {codigos} antes de poder manejarla en una caja. '
            'Contactate con un analista cambiario o un administrador.',
        )

    def get(self, request, *args, **kwargs):
        """Muestra el formulario de apertura, o por qué no se puede abrir otra."""
        caja_abierta = Caja.objects.filter(usuario=request.user, estado=Caja.ESTADO_ABIERTA).first()
        if caja_abierta is not None:
            messages.error(request, 'Ya tenés una caja abierta. Cerrala antes de abrir otra.')
            return redirect('caja:panel')
        form = AperturaCajaForm()
        self._avisar_divisas_sin_cotizar(request, form)
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
        self._avisar_divisas_sin_cotizar(request, form)
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
        if caja is not None:
            divisas = Divisa.objects.filter(activa=True).order_by('codigo')
            saldos_actuales = [(divisa, caja.saldo_actual(divisa)) for divisa in divisas]
            operaciones = caja.operaciones.select_related('divisa')[:20]
        return render(
            request,
            'caja/panel_caja.html',
            {'caja': caja, 'saldos_actuales': saldos_actuales, 'operaciones': operaciones},
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
