from django import forms
from .models import Divisa

class DivisaForm(forms.ModelForm):
    class Meta:
        model = Divisa
        fields = ['codigo', 'nombre', 'simbolo', 'activa']
        labels = {
            'codigo': 'Código ISO (Ej. USD, EUR)',
            'nombre': 'Nombre de la divisa',
            'simbolo': 'Símbolo (Ej. $, €)',
            'activa': 'Divisa Activa'
        }