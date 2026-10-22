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
    """Alta de una cuenta bancaria o de billetera, de un cliente o de la casa de cambio.

    ``clean()`` evita a propósito un caso que el modelo no impide por sí
    solo: dos cuentas marcadas como "de la casa de cambio" en la misma
    moneda. ``crear_solicitud_cobro``/``crear_transferencia_saliente``
    (``core/views.py``) usan ``.first()`` sobre ese filtro, así que una
    segunda cuenta así quedaría cargada pero invisible para el sistema,
    sin ningún aviso.
    """

    class Meta:
        model = Cuenta
        fields = [
            'proveedor', 'numero', 'titular', 'documento', 'moneda', 'saldo',
            'es_cuenta_casa_de_cambio',
        ]

    def clean(self):
        datos = super().clean()
        moneda = datos.get('moneda')
        es_casa_de_cambio = datos.get('es_cuenta_casa_de_cambio')
        if es_casa_de_cambio and moneda:
            if Cuenta.objects.filter(es_cuenta_casa_de_cambio=True, moneda=moneda).exists():
                self.add_error(
                    'es_cuenta_casa_de_cambio',
                    f'Ya existe una cuenta de la casa de cambio en {moneda}; '
                    'solo puede haber una por moneda.',
                )
        return datos
