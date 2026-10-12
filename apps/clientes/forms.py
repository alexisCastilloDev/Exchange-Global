"""
Módulo de formularios para la aplicación de Clientes.
"""

from django import forms
from django.contrib.auth import get_user_model
# Se agregó MetodoPago a la importación existente
from apps.clientes.models import Cliente, MetodoPago
from apps.clientes.validacion_sipap import SipapComunicacionError, validar_cuenta

User = get_user_model()


class ClienteForm(forms.ModelForm):
    """Valida y persiste los datos principales de un cliente."""
    # Campo legado: se conserva para aceptar datos históricos, pero no se
    # muestra en la interfaz; el correo operativo pertenece al usuario.
    email = forms.EmailField(required=False, widget=forms.HiddenInput())
    class SegmentoChoiceField(forms.ChoiceField):
        """Lista los segmentos vigentes y mantiene compatibilidad con datos previos."""

        _alias_historicos = {'ESTANDAR': 'MINORISTA', 'PREMIUM': 'VIP'}

        def clean(self, value):
            """Normaliza nombres históricos de segmentos antes de validar."""
            return super().clean(self._alias_historicos.get(value, value))

        def valid_value(self, value):
            """Acepta valores vigentes y alias conservados por compatibilidad."""
            return (
                value in self._alias_historicos
                or super().valid_value(value)
            )

    segmento = SegmentoChoiceField(
        choices=Cliente.SEGMENTO_CHOICES,
        label='Segmento / Categoría',
    )
    comision_personalizada = forms.DecimalField(
        label='Comisión personalizada (%)',
        required=False,
        max_digits=6,
        decimal_places=3,
        min_value=0,
        help_text=(
            'Opcional. Si se define, sobrescribe la comisión de la categoría'
            ' solo para este cliente.'
        ),
        widget=forms.NumberInput(attrs={'step': '0.001', 'min': '0'}),
    )

    class Meta:
        """Define el modelo y los campos visibles del formulario de clientes."""
        model = Cliente
        fields = [
            'tipo_cliente',
            'identificador',
            'nombre',
            'apellido',
            'razon_social',
            'segmento',
            'comision_personalizada',
        ]

    def clean_identificador(self):
        """Valida únicamente que el identificador/documento no esté registrado

        en otro perfil de cliente. Ya no exige que el usuario exista previamente.
        """
        identificador = self.cleaned_data.get('identificador')

        if not identificador:
            return identificador

        # 1. Validar unicidad del identificador dentro de la tabla Cliente
        cliente_existente = Cliente.objects.filter(identificador=identificador)
        if self.instance and self.instance.pk:
            cliente_existente = cliente_existente.exclude(
                pk=self.instance.pk
            )

        if cliente_existente.exists():
            raise forms.ValidationError(
                'Ya existe un perfil de cliente registrado con este documento/identificador.'
            )

        return identificador

    def clean(self):
        """Validaciones condicionales según el tipo de cliente."""
        cleaned_data = super().clean()
        tipo_cliente = cleaned_data.get('tipo_cliente')
        nombre = cleaned_data.get('nombre')
        apellido = cleaned_data.get('apellido')
        razon_social = cleaned_data.get('razon_social')

        if tipo_cliente == Cliente.TIPO_FISICA:
            if not nombre:
                self.add_error(
                    'nombre', 'El nombre es obligatorio para personas físicas.'
                )
            if not apellido:
                self.add_error(
                    'apellido',
                    'El apellido es obligatorio para personas físicas.',
                )

        elif tipo_cliente == Cliente.TIPO_JURIDICA:
            if not razon_social:
                self.add_error(
                    'razon_social',
                    'La razón social es obligatoria para personas jurídicas.',
                )

        return cleaned_data

    def save(self, commit=True):
        """Asigna automáticamente el usuario si ya existe con ese identificador.

        Si no existe, se crea el cliente normalmente sin forzar la vinculación.
        """
        cliente = super().save(commit=False)
        identificador = self.cleaned_data.get('identificador')

        if identificador:
            usuario = User.objects.filter(username=identificador).first()
            if usuario:
                cliente.user = usuario

        if commit:
            cliente.save()
            self.save_m2m()

        return cliente


class AsociarUsuarioClienteForm(forms.Form):
    """Formulario independiente para asociar o desasociar Usuarios a un Cliente."""

    class UsuarioModelMultipleChoiceField(forms.ModelMultipleChoiceField):
        """Campo de selección múltiple que muestra el nombre del usuario."""

        def label_from_instance(self, obj):
            """Construye la etiqueta visible para un usuario asociado."""
            nombre_completo = f"{obj.first_name} {obj.last_name}".strip()
            return nombre_completo if nombre_completo else obj.username

    usuarios = UsuarioModelMultipleChoiceField(
        queryset=None,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Usuarios del Sistema",
    )

    def __init__(self, *args, usuarios_cliente=None, **kwargs):
        """Limita las opciones a usuarios activos habilitados por Keycloak."""
        super().__init__(*args, **kwargs)
        # Los roles son gestionados exclusivamente por Keycloak. La vista
        # entrega los IDs sincronizados que poseen el rol de negocio cliente.
        queryset = User.objects.filter(is_active=True)
        if usuarios_cliente is not None:
            queryset = queryset.filter(pk__in=usuarios_cliente)
        else:
            queryset = queryset.none()
        self.fields['usuarios'].queryset = queryset.order_by(
            'first_name', 'last_name'
        )


# ==============================================================================
# FORMULARIOS PARA GE-19: Gestión de métodos de pago
# ==============================================================================

class AgregarTarjetaStripeForm(forms.Form):
    """Pide el nombre del titular antes de ir a Stripe a capturar la tarjeta.

    Es deliberadamente mínimo: el número de tarjeta nunca pasa por este
    formulario ni por ningún campo de Global Exchange — lo captura Stripe
    directamente en su propia página (ver
    ``apps.divisas.pagos_stripe.IniciarAgregarTarjetaStripeView``). El
    nombre del titular es el único dato propio que hace falta pedir antes
    de salir hacia Stripe, porque la entidad financiera y los últimos 4
    dígitos los va a devolver Stripe recién al confirmar.
    """

    nombre_titular = forms.CharField(
        max_length=150,
        label='Nombre del Titular',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )


class MetodoPagoForm(forms.ModelForm):
    """
    Formulario para registrar un método de pago manual del cliente (transferencia o billetera).

    Solo se usa para crear: los métodos de pago ya no se editan, solo se
    eliminan y se vuelven a crear si hace falta cambiar algo (ver
    ``apps.clientes.views.metodo_pago_delete``). Tampoco ofrece "Tarjeta de
    Débito/Crédito" como opción: desde la HU "Pago con tarjeta vía Stripe",
    una tarjeta se agrega exclusivamente a través de Stripe (ver
    ``IniciarAgregarTarjetaStripeView`` en ``apps.divisas.pagos_stripe``),
    que es quien conoce el número real y nunca lo entrega a este
    formulario.

    El cliente no escribe el nombre del titular ni el banco/billetera: los
    completa ``clean()`` a partir de lo que confirma sipap-sim
    (``apps.clientes.validacion_sipap.validar_cuenta``), igual que
    cualquier flujo real de vinculación de cuenta (no le creemos al
    usuario que una cuenta es suya solo porque lo escribió). Por eso esos
    dos campos del modelo no están en ``Meta.fields``: no hay nada que el
    formulario le pida tipear al cliente para completarlos.
    """

    def __init__(self, *args, **kwargs):
        """Quita "Tarjeta" de las opciones: esa alta pasa siempre por Stripe."""
        super().__init__(*args, **kwargs)
        self.fields['tipo_medio'].choices = [
            choice for choice in MetodoPago.TIPO_MEDIO_CHOICES if choice[0] != MetodoPago.TIPO_TARJETA
        ]

    class Meta:
        """Define los campos, etiquetas y widgets del método de pago."""
        model = MetodoPago
        fields = [
            'tipo_medio',
            'numero_cuenta',
            'documento_titular',
            'tipo_cuenta',
            'es_predeterminado'
        ]
        widgets = {
            'tipo_medio': forms.Select(attrs={'class': 'form-select', 'id': 'id_tipo_medio'}),
            'numero_cuenta': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Número de cuenta o de billetera'}),
            'documento_titular': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'CI o RUC del titular'}),
            'tipo_cuenta': forms.Select(attrs={'class': 'form-select'}),
            'es_predeterminado': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        """Valida los datos obligatorios y confirma la cuenta contra sipap-sim (criterios 1 y 2).

        Una transferencia o billetera necesita número de cuenta y CI/RUC
        del titular (además, solo para transferencia, el tipo de cuenta);
        con esos dos datos, se consulta a sipap-sim
        (``validar_cuenta``) para confirmar que la cuenta exista y sea de
        ese titular — si no, se rechaza el alta, igual que lo haría un
        banco real con una cuenta inventada. Si sipap-sim no responde, se
        rechaza también (no hay forma de confirmar nada sin él), en vez
        de guardar un método de pago sin verificar.
        """
        cleaned_data = super().clean()
        tipo_medio = cleaned_data.get('tipo_medio')
        numero_cuenta = cleaned_data.get('numero_cuenta')
        documento_titular = cleaned_data.get('documento_titular')
        tipo_cuenta = cleaned_data.get('tipo_cuenta')

        if tipo_medio not in (MetodoPago.TIPO_TRANSFERENCIA, MetodoPago.TIPO_BILLETERA):
            return cleaned_data

        if not numero_cuenta:
            self.add_error('numero_cuenta', 'El número de cuenta es obligatorio.')
        if not documento_titular:
            self.add_error('documento_titular', 'El CI o RUC del titular es obligatorio.')
        if tipo_medio == MetodoPago.TIPO_TRANSFERENCIA and not tipo_cuenta:
            self.add_error('tipo_cuenta', 'Debe seleccionar el tipo de cuenta.')

        if not numero_cuenta or not documento_titular:
            return cleaned_data

        try:
            resultado = validar_cuenta(numero_cuenta, documento_titular)
        except SipapComunicacionError:
            self.add_error(
                None,
                'No se pudo verificar la cuenta en este momento. Intentá nuevamente en unos minutos.',
            )
        else:
            if not resultado.get('valida'):
                self.add_error(
                    'numero_cuenta',
                    'No encontramos ninguna cuenta con ese número y ese documento. Verificá los datos.',
                )
            else:
                # El titular y el banco/billetera los confirma sipap-sim,
                # no lo que haya escrito el cliente.
                self.instance.nombre_titular = resultado['titular']
                self.instance.entidad_financiera = resultado['proveedor']

        return cleaned_data
