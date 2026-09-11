"""
Módulo de formularios para la aplicación de Clientes.
"""

from django import forms
from django.contrib.auth import get_user_model
from apps.clientes.models import Cliente

User = get_user_model()


class ClienteForm(forms.ModelForm):
    # Campo legado: se conserva para aceptar datos históricos, pero no se
    # muestra en la interfaz; el correo operativo pertenece al usuario.
    email = forms.EmailField(required=False, widget=forms.HiddenInput())
    segmento = forms.CharField()

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

    def clean_segmento(self):
        segmento = self.cleaned_data.get('segmento')
        segmento = {'ESTANDAR': 'MINORISTA', 'PREMIUM': 'VIP'}.get(segmento, segmento)
        permitidos = {valor for valor, _ in Cliente.SEGMENTO_CHOICES}
        if segmento not in permitidos:
            raise forms.ValidationError('Seleccioná una categoría válida.')
        return segmento

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['usuarios'].queryset = User.objects.filter(
            is_active=True
        ).order_by('first_name', 'last_name')