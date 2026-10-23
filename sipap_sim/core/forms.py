"""Formularios del panel administrativo de sipap-sim.

Reemplazan a la migración de datos como forma de cargar proveedores de
pago y cuentas: a diferencia de una migración, estos formularios corren
en cualquier entorno (incluida producción) detrás de la pantalla de
ingreso del panel (ver ``core.views``), y validan lo que escribe quien
los usa en vez de confiar en datos ya curados de antemano.
"""

from django import forms

from .models import Cuenta, ProveedorPago


class ProveedorPagoForm(forms.ModelForm):
    """Alta de un banco o una billetera digital nueva."""

    class Meta:
        model = ProveedorPago
        fields = ['tipo', 'codigo', 'nombre']
        widgets = {
            'codigo': forms.TextInput(attrs={'placeholder': 'Ej: ITAU, TIGO_MONEY'}),
            'nombre': forms.TextInput(attrs={'placeholder': 'Ej: Banco Itaú Paraguay'}),
        }


class CuentaForm(forms.ModelForm):
    """Alta o edición de una cuenta bancaria o de billetera, de un cliente o de la casa de cambio.

    El mismo formulario sirve para crear (``core.views.cuentas_view``) y
    para editar (``core.views.editar_cuenta_view``) una cuenta ya
    existente. No incluye ``es_cuenta_casa_de_cambio`` a propósito:
    sipap-sim no decide por sí solo cuál de sus cuentas hace ese papel,
    solo la muestra una vez que Global Exchange la designa desde su
    propio panel (ver ``core.views.designar_cuenta_casa_de_cambio`` y
    ``apps.divisas.views.DesignarCuentaPropiaView`` del lado de Global
    Exchange) — así se simula con más realismo que esa decisión la toma
    la casa de cambio, no el banco/billetera.
    """

    class Meta:
        model = Cuenta
        fields = ['proveedor', 'numero', 'titular', 'documento', 'moneda', 'saldo']
        widgets = {
            'moneda': forms.TextInput(attrs={'placeholder': 'USD, EUR, JPY...', 'maxlength': 3}),
        }

    def clean_moneda(self):
        """Normaliza a mayúsculas: no hay un select del que elegir, es texto libre."""
        return self.cleaned_data['moneda'].strip().upper()
