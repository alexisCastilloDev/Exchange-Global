"""
Módulo de formularios para la aplicación de Clientes.
"""

from django import forms
from django.contrib.auth import get_user_model
# Se agregó MetodoPago a la importación existente
from apps.clientes.models import Cliente, MetodoPago

User = get_user_model()


class ClienteForm(forms.ModelForm):
    # Campo legado: se conserva para aceptar datos históricos, pero no se
    # muestra en la interfaz; el correo operativo pertenece al usuario.
    email = forms.EmailField(required=False, widget=forms.HiddenInput())
    class SegmentoChoiceField(forms.ChoiceField):
        """Lista los segmentos vigentes y mantiene compatibilidad con datos previos."""

        _alias_historicos = {'ESTANDAR': 'MINORISTA', 'PREMIUM': 'VIP'}

        def clean(self, value):
            return super().clean(self._alias_historicos.get(value, value))

        def valid_value(self, value):
            return (
                value in self._alias_historicos
                or super().valid_value(value)
            )

    segmento = SegmentoChoiceField(
        choices=Cliente.SEGMENTO_CHOICES,
        label='Segmento / Categoría',
    )

    class Meta:
        model = Cliente
        fields = [
            'tipo_cliente',
            'identificador',
            'nombre',
            'apellido',
            'razon_social',
            'segmento',
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
        def label_from_instance(self, obj):
            nombre_completo = f"{obj.first_name} {obj.last_name}".strip()
            return nombre_completo if nombre_completo else obj.username

    usuarios = UsuarioModelMultipleChoiceField(
        queryset=None,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Usuarios del Sistema",
    )

    def __init__(self, *args, usuarios_cliente=None, **kwargs):
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

class MetodoPagoForm(forms.ModelForm):
    """
    Formulario para la creación y edición de métodos de pago del cliente.
    Realiza validaciones condicionales de acuerdo al tipo de medio de pago seleccionado.
    """

    class Meta:
        model = MetodoPago
        fields = [
            'tipo_medio',
            'nombre_titular',
            'entidad_financiera',
            'numero_cuenta',
            'tipo_cuenta',
            'ultimos_4_digitos',
            'es_predeterminado'
        ]
        widgets = {
            'tipo_medio': forms.Select(attrs={'class': 'form-select', 'id': 'id_tipo_medio'}),
            'nombre_titular': forms.TextInput(attrs={'class': 'form-control'}),
            'entidad_financiera': forms.TextInput(attrs={'class': 'form-control'}),
            'numero_cuenta': forms.TextInput(attrs={'class': 'form-control'}),
            'tipo_cuenta': forms.Select(attrs={'class': 'form-select'}),
            'ultimos_4_digitos': forms.TextInput(attrs={'class': 'form-control', 'maxlength': '4'}),
            'es_predeterminado': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        """
        Valida que se ingresen los campos obligatorios correspondientes a cada tipo de pago (Criterio 2).
        """
        cleaned_data = super().clean()
        tipo_medio = cleaned_data.get('tipo_medio')
        numero_cuenta = cleaned_data.get('numero_cuenta')
        tipo_cuenta = cleaned_data.get('tipo_cuenta')
        ultimos_4_digitos = cleaned_data.get('ultimos_4_digitos')

        if tipo_medio == MetodoPago.TIPO_TRANSFERENCIA:
            if not numero_cuenta:
                self.add_error('numero_cuenta', 'El número de cuenta es obligatorio para transferencias bancarias.')
            if not tipo_cuenta:
                self.add_error('tipo_cuenta', 'Debe seleccionar el tipo de cuenta.')

        elif tipo_medio == MetodoPago.TIPO_TARJETA:
            if not ultimos_4_digitos:
                self.add_error('ultimos_4_digitos', 'Debe ingresar los últimos 4 dígitos de la tarjeta.')
            elif not ultimos_4_digitos.isdigit() or len(ultimos_4_digitos) != 4:
                self.add_error('ultimos_4_digitos', 'Debe ingresar exactamente 4 dígitos numéricos.')

        return cleaned_data
