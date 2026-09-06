"""
Módulo de formularios para la aplicación de Clientes.
"""

from django import forms
from django.contrib.auth import get_user_model
from apps.clientes.models import Cliente

User = get_user_model()


class ClienteForm(forms.ModelForm):

    class Meta:
        model = Cliente
        fields = [
            'tipo_cliente',
            'identificador',
            'nombre',
            'apellido',
            'razon_social',
            'email',
            'segmento',
        ]

    def clean_identificador(self):
        """Valida que exista un usuario en el sistema con el identificador ingresado

        y que dicho usuario no esté ya asociado a otro perfil de cliente.
        """
        identificador = self.cleaned_data.get('identificador')

        if not identificador:
            return identificador

        # 1. Validar que exista el usuario con ese documento/username
        usuario = User.objects.filter(username=identificador).first()
        if not usuario:
            raise forms.ValidationError(
                f'No existe ningún usuario registrado con el documento {identificador}.'
            )

        # 2. Validar que el usuario no esté ya vinculado a otro cliente
        cliente_existente = Cliente.objects.filter(user=usuario)
        if self.instance and self.instance.pk:
            cliente_existente = cliente_existente.exclude(
                pk=self.instance.pk
            )

        if cliente_existente.exists():
            raise forms.ValidationError(
                'El usuario con este documento ya posee un perfil de cliente asociado.'
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
        """Asigna automáticamente el usuario titular correspondiente al identificador."""
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

    usuarios = forms.ModelMultipleChoiceField(
        queryset=None,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Usuarios del Sistema",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['usuarios'].queryset = User.objects.filter(is_active=True)