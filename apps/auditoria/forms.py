"""Formulario de filtros del registro de actividades."""
from django import forms
from django.contrib.auth import get_user_model

from apps.auditoria.models import RegistroActividad


class UsuarioChoiceField(forms.ModelChoiceField):
    """Lista los usuarios por su nombre completo, o su nombre de usuario si no lo tienen."""

    def label_from_instance(self, obj):
        """Texto con el que se muestra cada usuario en el selector."""
        return obj.get_full_name().strip() or obj.get_username()


class FiltroRegistroActividadForm(forms.Form):
    """Filtra el registro por usuario, tipo de acción, tipo de registro y rango de fechas.

    Todos los campos son opcionales: un filtro vacío no restringe el
    listado. El rango de fechas incluye ambos extremos.
    """

    usuario = UsuarioChoiceField(queryset=get_user_model().objects.none(), required=False, empty_label='Todos')
    accion = forms.ChoiceField(
        choices=[('', 'Todas')] + RegistroActividad.ACCION_CHOICES, required=False, label='Acción',
    )
    tipo_recurso = forms.ChoiceField(
        choices=[('', 'Todos')] + RegistroActividad.RECURSO_CHOICES, required=False, label='Registro',
    )
    fecha_desde = forms.DateField(required=False, label='Desde', widget=forms.DateInput(attrs={'type': 'date'}))
    fecha_hasta = forms.DateField(required=False, label='Hasta', widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, *args, **kwargs):
        """Ofrece como opciones de usuario solo a quienes tienen alguna actividad registrada."""
        super().__init__(*args, **kwargs)
        self.fields['usuario'].queryset = (
            get_user_model().objects
            .filter(actividades_registradas__isnull=False)
            .distinct()
            .order_by('first_name', 'last_name', 'username')
        )

    def clean(self):
        """Valida que el rango de fechas no termine antes de empezar."""
        datos = super().clean()
        desde, hasta = datos.get('fecha_desde'), datos.get('fecha_hasta')
        if desde and hasta and desde > hasta:
            raise forms.ValidationError('La fecha "Desde" no puede ser posterior a la fecha "Hasta".')
        return datos

    def filtrar(self, queryset):
        """Aplica al ``queryset`` los filtros válidos del formulario.

        Debe llamarse después de ``is_valid()``. Las fechas se comparan
        contra el día local de ``fecha`` (``TIME_ZONE``), no en UTC.
        """
        datos = self.cleaned_data
        if datos.get('usuario'):
            queryset = queryset.filter(usuario=datos['usuario'])
        if datos.get('accion'):
            queryset = queryset.filter(accion=datos['accion'])
        if datos.get('tipo_recurso'):
            queryset = queryset.filter(tipo_recurso=datos['tipo_recurso'])
        if datos.get('fecha_desde'):
            queryset = queryset.filter(fecha__date__gte=datos['fecha_desde'])
        if datos.get('fecha_hasta'):
            queryset = queryset.filter(fecha__date__lte=datos['fecha_hasta'])
        return queryset
