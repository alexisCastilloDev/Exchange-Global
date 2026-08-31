from django import forms
from .models import Cliente

class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ['tipo_cliente', 'identificador', 'nombre', 'apellido', 'razon_social', 'email']

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