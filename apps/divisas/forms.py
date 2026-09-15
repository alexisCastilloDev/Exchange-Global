"""Formularios para registrar, actualizar y simular cotizaciones."""

from django import forms
from django.core.validators import RegexValidator
from .models import Cotizacion, Divisa


class SimulacionDivisasForm(forms.Form):
    """Valida los datos necesarios para convertir un monto entre divisas."""

    monto = forms.DecimalField(
        label='Monto a convertir',
        min_value=0,
        max_digits=18,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'step': '0.01', 'min': '0.01', 'class': 'form-control ge-form-control'}),
    )
    divisa_origen = forms.ChoiceField(
        label='Divisa origen',
        choices=[],
        widget=forms.Select(attrs={'class': 'form-select ge-form-control'}),
    )
    divisa_destino = forms.ChoiceField(
        label='Divisa destino',
        choices=[],
        widget=forms.Select(attrs={'class': 'form-select ge-form-control'}),
    )

    @staticmethod
    def _divisa_guarani_implicit():
        """Construye la divisa PYG implícita cuando no existe en la base."""
        return Divisa(codigo='PYG', nombre='Guaraní', simbolo='₲', activa=True)

    @classmethod
    def opciones_divisas(cls):
        """Devuelve las divisas activas más la opción implícita de guaraní."""
        divisas_activas = list(Divisa.objects.filter(activa=True).order_by('codigo'))
        opciones = []

        for divisa in divisas_activas:
            if divisa.codigo == 'PYG':
                opciones.append(('PYG', f'{divisa.nombre} ({divisa.codigo})'))
            else:
                opciones.append((str(divisa.pk), f'{divisa.nombre} ({divisa.codigo})'))

        if not any(opt[0] == 'PYG' for opt in opciones):
            opciones.insert(0, ('PYG', 'Guaraní (PYG)'))

        return opciones

    def __init__(self, *args, **kwargs):
        """Inicializa el formulario con las opciones vigentes de divisas."""
        super().__init__(*args, **kwargs)
        self.fields['divisa_origen'].choices = self.opciones_divisas()
        self.fields['divisa_destino'].choices = self.opciones_divisas()

    def clean_divisa_origen(self):
        """Convierte y valida la divisa seleccionada como origen."""
        valor = self.cleaned_data['divisa_origen']
        if valor == 'PYG':
            return self._divisa_guarani_implicit()
        divisa = Divisa.objects.filter(pk=valor, activa=True).first()
        if not divisa:
            raise forms.ValidationError('Debe elegir una divisa válida.')
        return divisa

    def clean_divisa_destino(self):
        """Convierte y valida la divisa seleccionada como destino."""
        valor = self.cleaned_data['divisa_destino']
        if valor == 'PYG':
            return self._divisa_guarani_implicit()
        divisa = Divisa.objects.filter(pk=valor, activa=True).first()
        if not divisa:
            raise forms.ValidationError('Debe elegir una divisa válida.')
        return divisa

    def clean_monto(self):
        """Verifica que el monto de conversión sea positivo."""
        monto = self.cleaned_data['monto']
        if monto <= 0:
            raise forms.ValidationError('El monto debe ser mayor que cero.')
        return monto

    def clean(self):
        """Evita que la conversión use la misma divisa en ambos extremos."""
        cleaned_data = super().clean()
        origen = cleaned_data.get('divisa_origen')
        destino = cleaned_data.get('divisa_destino')

        if origen and destino:
            if getattr(origen, 'codigo', None) == getattr(destino, 'codigo', None):
                raise forms.ValidationError('Debe seleccionar dos divisas distintas.')

        return cleaned_data


class DivisaForm(forms.ModelForm):
    """Valida los datos básicos de una divisa administrable."""
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
        """Define el modelo y los campos editables de la divisa."""
        model = Divisa
        fields = ['codigo', 'nombre', 'simbolo']

    def clean_codigo(self):
        """Normaliza el código ISO y controla que no esté duplicado."""
        codigo = self.cleaned_data['codigo'].strip().upper()
        duplicado = Divisa.objects.filter(codigo__iexact=codigo)
        if self.instance.pk:
            duplicado = duplicado.exclude(pk=self.instance.pk)
        if duplicado.exists():
            raise forms.ValidationError('Ya existe una divisa con este código ISO.')
        return codigo

    def clean_nombre(self):
        """Rechaza nombres de divisa vacíos."""
        nombre = self.cleaned_data['nombre'].strip()
        if not nombre:
            raise forms.ValidationError('El nombre de la divisa es obligatorio.')
        return nombre

    def clean_simbolo(self):
        """Rechaza símbolos de divisa vacíos."""
        simbolo = self.cleaned_data['simbolo'].strip()
        if not simbolo:
            raise forms.ValidationError('El símbolo de la divisa es obligatorio.')
        return simbolo


class CotizacionForm(forms.ModelForm):
    """Valida las tasas de compra y venta de una cotización."""
    class Meta:
        """Define los campos y etiquetas editables de la cotización."""
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
        """Comprueba que ambas tasas sean positivas y estén ordenadas."""
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
