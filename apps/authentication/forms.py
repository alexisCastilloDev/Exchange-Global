from django import forms


class CausaBajaForm(forms.Form):
    causa = forms.CharField(
        label='Causa de baja',
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Indicá el motivo de la baja.',
            }
        ),
    )

    def clean_causa(self):
        causa = self.cleaned_data['causa'].strip()
        if not causa:
            raise forms.ValidationError('La causa de baja es obligatoria.')
        return causa
