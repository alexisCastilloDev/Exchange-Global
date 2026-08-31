from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from .models import Cliente

User = get_user_model()

class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ['tipo_cliente', 'identificador', 'nombre', 'apellido', 'razon_social', 'email']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # El número de documento es estrictamente obligatorio para la verificación
        self.fields['identificador'].required = True

    def clean(self):
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
                if self.instance and self.instance.pk:
                    cliente_existente = cliente_existente.exclude(pk=self.instance.pk)

                if cliente_existente.exists():
                    self.add_error(
                        'identificador', 
                        'El usuario con este número de documento ya tiene un perfil de cliente registrado.'
                    )
                else:
                    cleaned_data['user_obj'] = usuario

        return cleaned_data

    def save(self, commit=True):
        cliente = super().save(commit=False)
        user_obj = self.cleaned_data.get('user_obj')
        if user_obj:
            cliente.user = user_obj
        if commit:
            cliente.save()
        return cliente