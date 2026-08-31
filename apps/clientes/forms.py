from django import forms
from django.contrib.auth import get_user_model
from .models import Cliente

User = get_user_model()

class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ['user', 'tipo_cliente', 'identificador', 'nombre', 'apellido', 'razon_social', 'email']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filtra para mostrar únicamente usuarios que aún no tienen perfil de Cliente
        usuarios_asignados = Cliente.objects.filter(user__isnull=False)
        
        # Si se está editando un cliente existente, permite conservar su usuario actual en la lista
        if self.instance and self.instance.pk and self.instance.user_id:
            usuarios_asignados = usuarios_asignados.exclude(pk=self.instance.pk)

        self.fields['user'].queryset = User.objects.exclude(id__in=usuarios_asignados.values_list('user_id', flat=True))
        self.fields['user'].required = True
        self.fields['user'].label = "Usuario del Sistema"
        self.fields['user'].empty_label = "-- Seleccione un usuario --"

    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo_cliente')
        nombre = cleaned_data.get('nombre')
        apellido = cleaned_data.get('apellido')
        razon_social = cleaned_data.get('razon_social')

        # Validación dinámica según tipo de cliente
        if tipo == Cliente.TIPO_FISICA:
            if not nombre:
                self.add_error('nombre', 'El nombre es obligatorio para Persona Física.')
            if not apellido:
                self.add_error('apellido', 'El apellido es obligatorio para Persona Física.')
        elif tipo == Cliente.TIPO_JURIDICA:
            if not razon_social:
                self.add_error('razon_social', 'La razón social es obligatoria para Persona Jurídica.')

        return cleaned_data