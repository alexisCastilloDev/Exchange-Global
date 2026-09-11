from django import forms
from django.core.validators import RegexValidator
from .models import Cotizacion, Divisa


class SimulacionDivisasForm(forms.Form):
    monto = forms.DecimalField(
        label='Monto a convertir',
        min_value=0,
        max_digits=18,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
    )
    divisa_origen = forms.ModelChoiceField(
        label='Divisa origen',
        queryset=Divisa.objects.none(),
    )
    divisa_destino = forms.ModelChoiceField(
        label='Divisa destino',
        queryset=Divisa.objects.none(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        divisas_activas = Divisa.objects.filter(activa=True).order_by('codigo')
        self.fields['divisa_origen'].queryset = divisas_activas
        self.fields['divisa_destino'].queryset = divisas_activas

    def clean_monto(self):
        monto = self.cleaned_data['monto']
        if monto <= 0:
            raise forms.ValidationError('El monto debe ser mayor que cero.')
        return monto

    def clean(self):
        cleaned_data = super().clean()
        origen = cleaned_data.get('divisa_origen')
        destino = cleaned_data.get('divisa_destino')

        if origen and destino and origen.pk == destino.pk:
            raise forms.ValidationError('Debe seleccionar dos divisas distintas.')

        return cleaned_data


class DivisaForm(forms.ModelForm):
    codigo = forms.CharField(
        label='Código ISO (Ej. USD, EUR, PYG)',
        max_length=3,
        validators=[
            RegexValidator(
                regex=r'^[A-Z]{3}$',
                message='El código debe tener exactamente 3 letras mayúsculas (ISO 4217).',
            )
        ],
    )
    nombre = forms.CharField(label='Nombre de la divisa', max_length=50)
    simbolo = forms.CharField(label='Símbolo (Ej. $, €)', max_length=5)
    class Meta:
        model = Divisa
        fields = ['codigo', 'nombre', 'simbolo']

    def clean_codigo(self):
        codigo = self.cleaned_data['codigo'].strip().upper()
        duplicado = Divisa.objects.filter(codigo__iexact=codigo)
        if self.instance.pk:
            duplicado = duplicado.exclude(pk=self.instance.pk)
        if duplicado.exists():
            raise forms.ValidationError('Ya existe una divisa con este código ISO.')
        return codigo

    def clean_nombre(self):
        nombre = self.cleaned_data['nombre'].strip()
        if not nombre:
            raise forms.ValidationError('El nombre de la divisa es obligatorio.')
        return nombre

    def clean_simbolo(self):
        simbolo = self.cleaned_data['simbolo'].strip()
        if not simbolo:
            raise forms.ValidationError('El símbolo de la divisa es obligatorio.')
        return simbolo


class CotizacionForm(forms.ModelForm):
    class Meta:
        model = Cotizacion
        fields = ['tasa_compra', 'tasa_venta']
        labels = {
            'tasa_compra': 'Precio de compra',
            'tasa_venta': 'Precio de venta',
        }
        widgets = {
            'tasa_compra': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'tasa_venta': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        compra = cleaned_data.get('tasa_compra')
        venta = cleaned_data.get('tasa_venta')

        if compra is not None and compra <= 0:
            self.add_error('tasa_compra', 'El precio de compra debe ser mayor que cero.')
        if venta is not None and venta <= 0:
            self.add_error('tasa_venta', 'El precio de venta debe ser mayor que cero.')
        if compra is not None and venta is not None and compra > venta:
            raise forms.ValidationError(
                'El precio de compra no puede ser mayor que el precio de venta.'
            )
        return cleaned_data
