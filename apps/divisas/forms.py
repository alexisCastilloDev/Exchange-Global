"""Formularios para registrar, actualizar y simular cotizaciones."""

from django import forms
from django.core.validators import RegexValidator
from .models import CalculoOperacion, ConfiguracionComision, ConfiguracionVigencia, Cotizacion, Divisa


class DivisaSelect(forms.Select):
    """Select de divisas que expone el símbolo de cada opción en ``data-simbolo``."""

    def __init__(self, *args, **kwargs):
        """Inicializa el select sin símbolos asignados todavía."""
        super().__init__(*args, **kwargs)
        self.simbolos = {}

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        """Agrega el símbolo de la divisa como atributo de datos de la opción."""
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        simbolo = self.simbolos.get(str(value))
        if simbolo:
            option['attrs']['data-simbolo'] = simbolo
        return option


class CalculoOperacionForm(forms.Form):
    """Valida el tipo, monto y divisa de una operación de compra o venta.

    Rechaza montos negativos, en cero o no numéricos, y divisas inactivas o
    inexistentes, con mensajes en español. La divisa PYG queda fuera porque es
    la moneda contra la que siempre se opera.
    """

    tipo = forms.ChoiceField(
        choices=CalculoOperacion.TIPO_CHOICES,
        widget=forms.HiddenInput(),
    )
    monto = forms.DecimalField(
        label='Monto de la operación',
        min_value=0.01,
        max_digits=18,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'step': '0.01', 'min': '0.01', 'class': 'form-control ge-form-control'}),
        error_messages={
            'required': 'Debe ingresar un monto.',
            'invalid': 'El monto debe ser un número válido.',
            'min_value': 'El monto debe ser mayor que cero.',
            'max_digits': 'El monto supera la cantidad de dígitos permitida.',
            'max_decimal_places': 'El monto admite como máximo 2 decimales.',
            'max_whole_digits': 'El monto supera la cantidad de dígitos permitida.',
        },
    )
    divisa = forms.ChoiceField(
        label='Divisa',
        choices=[],
        widget=DivisaSelect(attrs={'class': 'form-select ge-form-control'}),
        error_messages={
            'required': 'Debe seleccionar una divisa.',
            'invalid_choice': 'La divisa seleccionada está inactiva o no está disponible para operar.',
        },
    )

    def __init__(self, *args, tipo=None, **kwargs):
        """Carga divisas activas y fija el tipo de operación solicitado."""
        super().__init__(*args, **kwargs)
        tipo_inicial = tipo or self.data.get('tipo') or CalculoOperacion.TIPO_COMPRA
        self.fields['tipo'].initial = tipo_inicial
        self.fields['tipo'].disabled = True
        divisas = list(Divisa.objects.filter(activa=True).order_by('codigo').exclude(codigo='PYG'))
        self.fields['divisa'].choices = [('', 'Seleccionar divisa')] + [
            (str(divisa.pk), f'{divisa.nombre} ({divisa.codigo})') for divisa in divisas
        ]
        self.fields['divisa'].widget.simbolos = {
            str(divisa.pk): divisa.simbolo or divisa.codigo for divisa in divisas
        }

    def clean_tipo(self):
        """Valida que el tipo sea compra o venta."""
        tipo = self.cleaned_data['tipo']
        if tipo not in {CalculoOperacion.TIPO_COMPRA, CalculoOperacion.TIPO_VENTA}:
            raise forms.ValidationError('El tipo de operación no es válido.')
        return tipo

    def clean_divisa(self):
        """Resuelve una divisa activa distinta del guaraní base."""
        valor = self.cleaned_data['divisa']
        if not valor:
            raise forms.ValidationError('Debe seleccionar una divisa.')
        divisa = Divisa.objects.filter(pk=valor, activa=True).exclude(codigo='PYG').first()
        if not divisa:
            raise forms.ValidationError('Debe elegir una divisa válida.')
        return divisa


class ConfirmarCalculoOperacionForm(forms.Form):
    """Valida los datos ocultos que viajan del cálculo previo a la confirmación.

    El Paso 1 ("Calcular importe") no persiste nada; estos campos ocultos son
    la única forma en la que el Paso 2 ("Confirmar importe") conoce qué se
    calculó, para poder revalidar la cotización y el tiempo de vigencia antes
    de recién ahí crear la transacción.
    """

    tipo = forms.ChoiceField(choices=CalculoOperacion.TIPO_CHOICES, widget=forms.HiddenInput())
    divisa = forms.ChoiceField(choices=[], widget=forms.HiddenInput())
    monto = forms.DecimalField(
        min_value=0.01, max_digits=18, decimal_places=2, widget=forms.HiddenInput()
    )
    cotizacion_id = forms.IntegerField(widget=forms.HiddenInput())
    vence_en_timestamp = forms.FloatField(widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        """Acepta cualquier divisa activa distinta del guaraní base."""
        super().__init__(*args, **kwargs)
        self.fields['divisa'].choices = [
            (str(divisa.pk), divisa.codigo)
            for divisa in Divisa.objects.filter(activa=True).exclude(codigo='PYG')
        ]

    def clean_divisa(self):
        """Resuelve la divisa indicada, validando que siga activa."""
        valor = self.cleaned_data['divisa']
        divisa = Divisa.objects.filter(pk=valor, activa=True).exclude(codigo='PYG').first()
        if not divisa:
            raise forms.ValidationError('La divisa ya no está disponible. Recalculá la operación.')
        return divisa


class TriangulacionForm(forms.Form):
    """Valida el monto y las dos divisas extranjeras de un cambio triangulado."""

    monto = forms.DecimalField(
        label='Monto a cambiar',
        min_value=0.01,
        max_digits=18,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'step': '0.01', 'min': '0.01', 'class': 'form-control ge-form-control'}),
    )
    divisa_origen = forms.ChoiceField(
        label='Divisa origen',
        choices=[],
        widget=DivisaSelect(attrs={'class': 'form-select ge-form-control'}),
    )
    divisa_destino = forms.ChoiceField(
        label='Divisa destino',
        choices=[],
        widget=DivisaSelect(attrs={'class': 'form-select ge-form-control'}),
    )

    def __init__(self, *args, **kwargs):
        """Carga las divisas extranjeras activas en ambos selectores."""
        super().__init__(*args, **kwargs)
        divisas = list(Divisa.objects.filter(activa=True).order_by('codigo').exclude(codigo='PYG'))
        opciones = [('', 'Seleccionar divisa')] + [
            (str(divisa.pk), f'{divisa.nombre} ({divisa.codigo})') for divisa in divisas
        ]
        simbolos = {str(divisa.pk): divisa.simbolo or divisa.codigo for divisa in divisas}
        self.fields['divisa_origen'].choices = opciones
        self.fields['divisa_destino'].choices = opciones
        self.fields['divisa_origen'].widget.simbolos = simbolos
        self.fields['divisa_destino'].widget.simbolos = simbolos

    def _clean_divisa(self, campo):
        """Resuelve y valida una divisa extranjera activa."""
        valor = self.cleaned_data[campo]
        if not valor:
            raise forms.ValidationError('Debe seleccionar una divisa.')
        divisa = Divisa.objects.filter(pk=valor, activa=True).exclude(codigo='PYG').first()
        if not divisa:
            raise forms.ValidationError('Debe elegir una divisa válida.')
        return divisa

    def clean_divisa_origen(self):
        """Valida la divisa de origen de la triangulación."""
        return self._clean_divisa('divisa_origen')

    def clean_divisa_destino(self):
        """Valida la divisa de destino de la triangulación."""
        return self._clean_divisa('divisa_destino')

    def clean(self):
        """Evita triangular una divisa contra sí misma."""
        cleaned_data = super().clean()
        origen = cleaned_data.get('divisa_origen')
        destino = cleaned_data.get('divisa_destino')
        if origen and destino and origen.codigo == destino.codigo:
            raise forms.ValidationError('Debe seleccionar dos divisas distintas.')
        return cleaned_data


class ConfirmarTriangulacionForm(forms.Form):
    """Valida los datos ocultos que viajan del cálculo de un cambio a su confirmación.

    El cálculo previo no persiste nada; estos campos ocultos son la única
    forma en la que la confirmación conoce qué se calculó, para poder
    revalidar ambas cotizaciones y el tiempo de vigencia antes de crear la
    transacción.
    """

    divisa_origen = forms.ChoiceField(choices=[], widget=forms.HiddenInput())
    divisa_destino = forms.ChoiceField(choices=[], widget=forms.HiddenInput())
    monto = forms.DecimalField(
        min_value=0.01, max_digits=18, decimal_places=2, widget=forms.HiddenInput()
    )
    cotizacion_origen_id = forms.IntegerField(widget=forms.HiddenInput())
    cotizacion_destino_id = forms.IntegerField(widget=forms.HiddenInput())
    vence_en_timestamp = forms.FloatField(widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        """Acepta cualquier divisa activa distinta del guaraní base."""
        super().__init__(*args, **kwargs)
        opciones = [
            (str(divisa.pk), divisa.codigo)
            for divisa in Divisa.objects.filter(activa=True).exclude(codigo='PYG')
        ]
        self.fields['divisa_origen'].choices = opciones
        self.fields['divisa_destino'].choices = opciones

    def _clean_divisa(self, campo):
        """Resuelve la divisa indicada, validando que siga activa."""
        divisa = Divisa.objects.filter(
            pk=self.cleaned_data[campo], activa=True
        ).exclude(codigo='PYG').first()
        if not divisa:
            raise forms.ValidationError('La divisa ya no está disponible. Recalculá la operación.')
        return divisa

    def clean_divisa_origen(self):
        """Resuelve la divisa de origen del cambio."""
        return self._clean_divisa('divisa_origen')

    def clean_divisa_destino(self):
        """Resuelve la divisa de destino del cambio."""
        return self._clean_divisa('divisa_destino')

    def clean(self):
        """Evita confirmar un cambio de una divisa contra sí misma."""
        cleaned_data = super().clean()
        origen = cleaned_data.get('divisa_origen')
        destino = cleaned_data.get('divisa_destino')
        if origen and destino and origen.pk == destino.pk:
            raise forms.ValidationError('Debe seleccionar dos divisas distintas.')
        return cleaned_data


class SimulacionDivisasForm(forms.Form):
    """Valida los datos de una simulación de compra, venta o cambio de divisas."""

    TIPO_COMPRA = CalculoOperacion.TIPO_COMPRA
    TIPO_VENTA = CalculoOperacion.TIPO_VENTA
    TIPO_CAMBIO = 'CAMBIO'
    TIPO_CHOICES = [
        (TIPO_COMPRA, 'Comprar una divisa'),
        (TIPO_VENTA, 'Vender una divisa'),
        (TIPO_CAMBIO, 'Cambiar entre dos divisas'),
    ]

    tipo = forms.ChoiceField(
        label='Tipo de simulación',
        choices=TIPO_CHOICES,
        initial=TIPO_COMPRA,
        widget=forms.RadioSelect(attrs={'class': 'ge-radio-group'}),
    )
    monto = forms.DecimalField(
        label='Monto',
        min_value=0.01,
        max_digits=18,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'step': '0.01', 'min': '0.01', 'class': 'form-control ge-form-control'}),
    )
    divisa = forms.ChoiceField(
        label='Divisa',
        choices=[],
        required=False,
        widget=DivisaSelect(attrs={'class': 'form-select ge-form-control'}),
    )
    divisa_origen = forms.ChoiceField(
        label='Divisa origen',
        choices=[],
        required=False,
        widget=DivisaSelect(attrs={'class': 'form-select ge-form-control'}),
    )
    divisa_destino = forms.ChoiceField(
        label='Divisa destino',
        choices=[],
        required=False,
        widget=DivisaSelect(attrs={'class': 'form-select ge-form-control'}),
    )

    def __init__(self, *args, **kwargs):
        """Inicializa el formulario con las opciones vigentes de divisas."""
        super().__init__(*args, **kwargs)
        divisas = list(Divisa.objects.filter(activa=True).order_by('codigo').exclude(codigo='PYG'))
        opciones = [('', 'Seleccionar divisa')] + [
            (str(divisa.pk), f'{divisa.nombre} ({divisa.codigo})') for divisa in divisas
        ]
        simbolos = {str(divisa.pk): divisa.simbolo or divisa.codigo for divisa in divisas}
        for campo in ('divisa', 'divisa_origen', 'divisa_destino'):
            self.fields[campo].choices = opciones
            self.fields[campo].widget.simbolos = simbolos

    def _resolver_divisa(self, campo):
        """Resuelve la divisa extranjera seleccionada en un campo opcional."""
        valor = self.cleaned_data.get(campo)
        if not valor:
            return None
        divisa = Divisa.objects.filter(pk=valor, activa=True).exclude(codigo='PYG').first()
        if not divisa:
            raise forms.ValidationError('Debe elegir una divisa válida.')
        return divisa

    def clean_divisa(self):
        """Resuelve la divisa a comprar o vender, si corresponde."""
        return self._resolver_divisa('divisa')

    def clean_divisa_origen(self):
        """Resuelve la divisa de origen del cambio, si corresponde."""
        return self._resolver_divisa('divisa_origen')

    def clean_divisa_destino(self):
        """Resuelve la divisa de destino del cambio, si corresponde."""
        return self._resolver_divisa('divisa_destino')

    def clean(self):
        """Exige las divisas correspondientes según el tipo de simulación."""
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo')

        if tipo in (self.TIPO_COMPRA, self.TIPO_VENTA):
            if not cleaned_data.get('divisa'):
                self.add_error('divisa', 'Debe elegir una divisa válida.')
        elif tipo == self.TIPO_CAMBIO:
            origen = cleaned_data.get('divisa_origen')
            destino = cleaned_data.get('divisa_destino')
            if not origen:
                self.add_error('divisa_origen', 'Debe elegir una divisa válida.')
            if not destino:
                self.add_error('divisa_destino', 'Debe elegir una divisa válida.')
            if origen and destino and origen.codigo == destino.codigo:
                raise forms.ValidationError('Debe seleccionar dos divisas distintas.')

        return cleaned_data


class ConfiguracionComisionForm(forms.ModelForm):
    """Valida el porcentaje de comisión configurado para un segmento de clientes."""

    class Meta:
        """Define el modelo y el campo editable de la comisión por segmento."""
        model = ConfiguracionComision
        fields = ['porcentaje']
        labels = {'porcentaje': 'Porcentaje de comisión (%)'}
        widgets = {
            'porcentaje': forms.NumberInput(attrs={'step': '0.001', 'min': '0', 'class': 'form-control ge-form-control'}),
        }

    def clean_porcentaje(self):
        """Rechaza porcentajes de comisión negativos."""
        porcentaje = self.cleaned_data['porcentaje']
        if porcentaje < 0:
            raise forms.ValidationError('El porcentaje de comisión no puede ser negativo.')
        return porcentaje


class ConfiguracionVigenciaForm(forms.ModelForm):
    """Valida los tiempos de espera configurados para confirmar el importe y la operación."""

    class Meta:
        """Define el modelo y los campos editables de la configuración de vigencia."""
        model = ConfiguracionVigencia
        fields = ['calculo_vigencia_segundos', 'confirmacion_vigencia_segundos']
        labels = {
            'calculo_vigencia_segundos': 'Tiempo de espera para confirmar el importe (segundos)',
            'confirmacion_vigencia_segundos': 'Tiempo de espera para confirmar la operación (segundos)',
        }
        widgets = {
            'calculo_vigencia_segundos': forms.NumberInput(
                attrs={'step': '1', 'min': '1', 'class': 'form-control ge-form-control'}
            ),
            'confirmacion_vigencia_segundos': forms.NumberInput(
                attrs={'step': '1', 'min': '1', 'class': 'form-control ge-form-control'}
            ),
        }

    def clean_calculo_vigencia_segundos(self):
        """Rechaza un tiempo de espera para el importe menor o igual a cero."""
        valor = self.cleaned_data['calculo_vigencia_segundos']
        if valor <= 0:
            raise forms.ValidationError('El tiempo de espera debe ser mayor que cero.')
        return valor

    def clean_confirmacion_vigencia_segundos(self):
        """Rechaza un tiempo de espera para la operación menor o igual a cero."""
        valor = self.cleaned_data['confirmacion_vigencia_segundos']
        if valor <= 0:
            raise forms.ValidationError('El tiempo de espera debe ser mayor que cero.')
        return valor


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
