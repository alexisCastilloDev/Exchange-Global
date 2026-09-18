"""Retira el estado 'Confirmada': la transacción ya nace confirmada.

Con el nuevo flujo, el cálculo previo (Paso 1) no persiste nada y la
transacción se crea recién al confirmar (Paso 2), siempre en un único
estado posible: "Pendiente de confirmación". No hace falta migrar datos:
esto solo restringe las opciones válidas hacia adelante.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Deja 'Pendiente de confirmación' como única opción de estado."""

    dependencies = [
        ('divisas', '0006_calculooperacion_cliente_estado'),
    ]

    operations = [
        migrations.AlterField(
            model_name='calculooperacion',
            name='estado',
            field=models.CharField(choices=[('PENDIENTE_CONFIRMACION', 'Pendiente de confirmación')], default='PENDIENTE_CONFIRMACION', max_length=25),
        ),
    ]
