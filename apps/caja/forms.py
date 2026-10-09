"""Formularios para la apertura de caja."""

from decimal import Decimal

from django import forms

from apps.divisas.models import Divisa


class AperturaCajaForm(forms.Form):
    """Pide el saldo inicial de cada divisa cotizada para abrir una caja.

    Genera dinámicamente un campo ``saldo_<divisa.pk>`` por cada divisa
    activa que tiene una cotización vigente (PYG siempre cuenta como
    cotizada, con tasa 1:1, igual que en el resto del sistema), para que el
    cajero registre cuánto tiene de cada una al empezar su turno
    (Criterio 1). Un saldo en cero es válido para una divisa que el cajero
    no va a manejar en este turno (Criterio 3); lo que se rechaza es un
    monto negativo o que no sea un número.

    Las divisas activas que todavía no tienen ninguna cotización cargada no
    reciben un campo: no tiene sentido contar un saldo inicial en una
    moneda que el sistema no puede valuar todavía. Quedan disponibles en
    ``self.divisas_sin_cotizar`` para que la vista/plantilla avise que hace
    falta que un analista cambiario o un administrador las cotice antes de
    poder manejarlas en una caja.
    """

    def __init__(self, *args, **kwargs):
        """Agrega un campo de saldo por cada divisa activa ya cotizada."""
        super().__init__(*args, **kwargs)
        self.divisas = []
        self.divisas_sin_cotizar = []
        for divisa in Divisa.objects.filter(activa=True).order_by('codigo'):
            if divisa.codigo != 'PYG' and divisa.ultima_cotizacion is None:
                self.divisas_sin_cotizar.append(divisa)
                continue
            self.divisas.append(divisa)
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
