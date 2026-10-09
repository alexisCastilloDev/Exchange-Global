"""Formularios para la apertura de caja."""

from decimal import Decimal

from django import forms

from apps.divisas.models import Divisa


class AperturaCajaForm(forms.Form):
    """Pide el saldo inicial de cada divisa activa para abrir una caja.

    Genera dinámicamente un campo ``saldo_<divisa.pk>`` por cada divisa
    activa del sistema (incluido PYG, si existe como divisa activa), para
    que el cajero registre cuánto tiene de cada una al empezar su turno
    (Criterio 1). Un saldo en cero es válido para una divisa que el cajero
    no va a manejar en este turno (Criterio 3); lo que se rechaza es un
    monto negativo o que no sea un número.
    """

    def __init__(self, *args, **kwargs):
        """Agrega un campo de saldo inicial por cada divisa activa."""
        super().__init__(*args, **kwargs)
        self.divisas = list(Divisa.objects.filter(activa=True).order_by('codigo'))
        for divisa in self.divisas:
            self.fields[self.nombre_campo(divisa)] = forms.DecimalField(
                label=f'Saldo inicial en {divisa.codigo}',
                min_value=Decimal('0'),
                max_digits=18,
                decimal_places=2,
                initial=Decimal('0.00'),
                error_messages={
                    'required': 'El saldo inicial es obligatorio.',
                    'invalid': 'Ingresá un monto válido.',
                    'min_value': 'El saldo inicial no puede ser negativo.',
                },
            )

    @staticmethod
    def nombre_campo(divisa):
        """Nombre del campo del formulario para el saldo inicial de una divisa."""
        return f'saldo_{divisa.pk}'

    def saldos_por_divisa(self):
        """Devuelve ``{Divisa: Decimal}`` con los montos ya validados.

        Solo debe llamarse después de confirmar ``is_valid()``.
        """
        return {
            divisa: self.cleaned_data[self.nombre_campo(divisa)]
            for divisa in self.divisas
        }
