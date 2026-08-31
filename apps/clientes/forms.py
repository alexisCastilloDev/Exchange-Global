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

        1. Valida que los campos (nombre/apellido o razón social) estén
           presentes según el 'tipo_cliente' seleccionado.
        2. Verifica que el 'identificador' (CI/RUC) corresponda a un Usuario 
           existente en el sistema y que este no esté ya vinculado a otro 
           perfil de cliente diferente al que se está editando.

        Returns:
            dict: Diccionario con los datos limpios y validados, incluyendo 
                  el objeto de usuario validado ('user_obj').
        """
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo_cliente')
        nombre = cleaned_data.get('nombre')
        apellido = cleaned_data.get('apellido')
        razon_social = cleaned_data.get('razon_social')
        identificador = cleaned_data.get('identificador')

        # 1. Validación de campos requeridos según el tipo de cliente
        if tipo == Cliente.TIPO_FISICA:
            if not nombre:
                self.add_error('nombre', 'El nombre es obligatorio para Persona Física.')
            if not apellido:
                self.add_error('apellido', 'El apellido es obligatorio para Persona Física.')
        elif tipo == Cliente.TIPO_JURIDICA:
            if not razon_social:
                self.add_error('razon_social', 'La razón social es obligatoria para Persona Jurídica.')

        # 2. Verificación en segundo plano por número de documento (CI / RUC)
        if identificador:
            identificador_clean = identificador.strip()
            
            # Busca coincidencia por username o por atributo de documento en User
            filtro_usuario = Q(username__iexact=identificador_clean)
            if hasattr(User, 'identificador'):
                filtro_usuario |= Q(identificador__iexact=identificador_clean)
                
            usuario = User.objects.filter(filtro_usuario).first()

            if not usuario:
                self.add_error(
                    'identificador', 
                    'No existe ningún usuario registrado en el sistema con este número de documento (CI/RUC).'
                )
            else:
                cliente_existente = Cliente.objects.filter(user=usuario)
                
                # Excluir la instancia actual si estamos editando
                if self.instance and self.instance.pk:
                    cliente_existente = cliente_existente.exclude(pk=self.instance.pk)

                if cliente_existente.exists():
                    self.add_error(
                        'identificador', 
                        'El usuario con este número de documento ya tiene un perfil de cliente registrado.'
                    )
                else:
                    # Inyectar el objeto de usuario validado para usarlo en save()
                    cleaned_data['user_obj'] = usuario

        return cleaned_data

    def save(self, commit=True):
        """
        Guarda el formulario y vincula el usuario correspondiente.

        Intercepta el método de guardado estándar para asignar explícitamente 
        la relación uno a uno (user) utilizando el objeto validado en clean().

        Args:
            commit (bool): Si es True, guarda el modelo en la base de datos. 
                           Por defecto es True.

        Returns:
            Cliente: La instancia del cliente actualizada/creada.
        """
        cliente = super().save(commit=False)
        user_obj = self.cleaned_data.get('user_obj')
        
        if user_obj:
            cliente.user = user_obj
            
        if commit:
            cliente.save()
            
        return cliente