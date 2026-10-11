"""Formularios para la apertura de caja y las operaciones de ventanilla."""

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


class OperacionVentanillaForm(forms.Form):
    """Valida la divisa y el monto de una compra o venta de divisas en ventanilla.

    Mismo criterio de validación que ``apps.divisas.forms.CalculoOperacionForm``
    usa para el flujo online del cliente: rechaza un monto negativo, en cero
    o no numérico, con mensajes en español. PYG no se ofrece como divisa
    operable (es la moneda contra la que siempre se opera, nunca la que se
    compra o vende), y tampoco una divisa sin cotización vigente, porque no
    hay con qué calcular la tasa aplicada.
    """

    divisa = forms.ChoiceField(
        label='Divisa',
        choices=[],
        widget=forms.Select(attrs={'class': 'form-select'}),
        error_messages={
            'required': 'Debe seleccionar una divisa.',
            'invalid_choice': (
                'La divisa seleccionada está inactiva, no tiene cotización'
                ' vigente o no está disponible.'
            ),
        },
    )
    monto = forms.DecimalField(
        label='Monto en divisa',
        min_value=Decimal('0.01'),
        max_digits=18,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'step': '0.01', 'min': '0.01', 'class': 'form-control'}),
        error_messages={
            'required': 'Debe ingresar un monto.',
            'invalid': 'El monto debe ser un número válido.',
            'min_value': 'El monto debe ser mayor que cero.',
            'max_digits': 'El monto supera la cantidad de dígitos permitida.',
            'max_decimal_places': 'El monto admite como máximo 2 decimales.',
            'max_whole_digits': 'El monto supera la cantidad de dígitos permitida.',
        },
    )

    def __init__(self, *args, **kwargs):
        """Carga como opciones las divisas activas y con cotización vigente, sin PYG."""
        super().__init__(*args, **kwargs)
        self.divisas = [
            divisa
            for divisa in Divisa.objects.filter(activa=True).exclude(codigo='PYG').order_by('codigo')
            if divisa.ultima_cotizacion is not None
        ]
        self.fields['divisa'].choices = [('', 'Seleccionar divisa')] + [
            (str(divisa.pk), f'{divisa.nombre} ({divisa.codigo})') for divisa in self.divisas
        ]

    def divisa_seleccionada(self):
        """Devuelve la ``Divisa`` ya validada. Solo debe llamarse tras confirmar ``is_valid()``."""
        pk = self.cleaned_data['divisa']
        return next(divisa for divisa in self.divisas if str(divisa.pk) == pk)
