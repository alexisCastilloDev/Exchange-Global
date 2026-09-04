"""
Módulo de formularios para la aplicación de Clientes.

Este módulo define el formulario principal para la creación y modificación
de clientes. Incluye validaciones condicionales según el tipo de persona 
(Física o Jurídica), verifica la correspondencia del documento con los 
usuarios registrados en el sistema, y permite la categorización mediante segmentos.
"""

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from .models import Cliente

User = get_user_model()


class AsociarUsuarioForm(forms.Form):
    """
    Formulario simple para que un administrador busque un usuario
    existente por email y lo asocie a un Cliente (HU: gestión de
    usuarios habilitados a operar en representación de un cliente).
    """
    email = forms.EmailField(
        label="Email del usuario a asociar",
        widget=forms.EmailInput(attrs={'placeholder': 'usuario@ejemplo.com', 'class': 'form-control'})
    )

    def clean_email(self):
        email = self.cleaned_data['email'].strip()
        usuario = User.objects.filter(email__iexact=email).first()
        if not usuario:
            raise forms.ValidationError(
                "No existe ningún usuario registrado en el sistema con ese email."
            )
        self.usuario = usuario
        return email


class ClienteForm(forms.ModelForm):
    """
    Formulario basado en modelo para la gestión de datos de un Cliente.

    Permite capturar y validar la información esencial, asegurando que 
    los datos requeridos coincidan con la naturaleza del cliente y que 
    exista un usuario subyacente válido para vincular.
    
    Historia de Usuario GE-8: Se incluye el campo 'segmento' para permitir 
    a los administradores clasificar a los clientes en categorías.
    """

    class Meta:
        model = Cliente
        # Se agrega 'segmento' a la lista de campos
        fields = [
            'tipo_cliente', 
            'identificador', 
            'nombre', 
            'apellido', 
            'razon_social', 
            'email',
            'segmento'
        ]
        
        # Opcional: Mejorar la apariencia del selector de segmentos en el HTML
        widgets = {
            'segmento': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        """
        Inicializa el formulario de cliente.

        Aplica configuraciones adicionales a los campos al momento de 
        instanciar el formulario, como forzar la obligatoriedad del 
        número de documento (identificador).
        """
        super().__init__(*args, **kwargs)
        # El número de documento es estrictamente obligatorio para la verificación
        self.fields['identificador'].required = True

    def clean(self):
        """
        Realiza la validación cruzada de los datos del formulario.

        Valida que los campos (nombre/apellido o razón social) estén
        presentes según el 'tipo_cliente' seleccionado.

        Nota: el alta/edición de un Cliente ya NO requiere que exista un
        Usuario del sistema vinculado por documento. La asociación de
        usuarios habilitados a operar en representación del cliente se
        gestiona aparte, por email, desde la ficha del cliente
        (ver ClienteAsociarUsuarioView en views.py).

        Returns:
            dict: Diccionario con los datos limpios y validados.
        """
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo_cliente')
        nombre = cleaned_data.get('nombre')
        apellido = cleaned_data.get('apellido')
        razon_social = cleaned_data.get('razon_social')

        # Validación de campos requeridos según el tipo de cliente
        if tipo == Cliente.TIPO_FISICA:
            if not nombre:
                self.add_error('nombre', 'El nombre es obligatorio para Persona Física.')
            if not apellido:
                self.add_error('apellido', 'El apellido es obligatorio para Persona Física.')
        elif tipo == Cliente.TIPO_JURIDICA:
            if not razon_social:
                self.add_error('razon_social', 'La razón social es obligatoria para Persona Jurídica.')

        return cleaned_data