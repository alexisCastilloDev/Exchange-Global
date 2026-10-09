"""Vistas para la apertura y consulta de la caja de un cajero."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.views import View

from apps.caja.forms import AperturaCajaForm
from apps.caja.models import Caja, SaldoInicialCaja


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
        """Muestra la caja abierta del cajero, si tiene una."""
        caja = (
            Caja.objects.filter(usuario=request.user, estado=Caja.ESTADO_ABIERTA)
            .prefetch_related('saldos_iniciales__divisa')
            .first()
        )
        return render(request, 'caja/panel_caja.html', {'caja': caja})
