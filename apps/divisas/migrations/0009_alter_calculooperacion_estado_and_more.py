"""Agrega los estados 'Confirmada' y 'Cancelada' a las transacciones.

Solo cambia las opciones válidas hacia adelante (metadata, no migra datos):
la pantalla de confirmación de la HU "Confirmación de operación cambiaria"
es la que ahora hace avanzar una transacción "Pendiente de confirmación"
hacia uno de esos dos estados finales.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Agrega 'Confirmada' y 'Cancelada' a los estados de ambos modelos."""

    dependencies = [
        ('divisas', '0008_calculotriangulacion_cliente_estado'),
    ]

    operations = [
        migrations.AlterField(
            model_name='calculooperacion',
            name='estado',
            field=models.CharField(choices=[('PENDIENTE_CONFIRMACION', 'Pendiente de confirmación'), ('CONFIRMADA', 'Confirmada'), ('CANCELADA', 'Cancelada')], default='PENDIENTE_CONFIRMACION', max_length=25),
        ),
        migrations.AlterField(
            model_name='calculotriangulacion',
            name='estado',
            field=models.CharField(choices=[('PENDIENTE_CONFIRMACION', 'Pendiente de confirmación'), ('CONFIRMADA', 'Confirmada'), ('CANCELADA', 'Cancelada')], default='PENDIENTE_CONFIRMACION', max_length=25),
        ),
    ]
