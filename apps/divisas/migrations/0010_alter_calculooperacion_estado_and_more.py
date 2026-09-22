"""Agrega el estado 'Vencida' y marca como tal a las transacciones que ya vencieron.

Antes de esta migración no existía ningún chequeo de vigencia sobre una
transacción ya creada en "Pendiente de confirmación": si el cliente cerraba
la pestaña de la pantalla de confirmación sin confirmar ni cancelar, quedaba
"pendiente" para siempre. Además de agregar la opción de estado, esta
migración hace un backfill único de los registros que en la base de datos
actual ya superaron su ``vence_en`` sin resolverse.
"""

from django.db import migrations, models
from django.utils import timezone


def marcar_pendientes_vencidas(apps, schema_editor):
    """Pasa a 'VENCIDA' las transacciones pendientes cuyo vence_en ya pasó."""
    CalculoOperacion = apps.get_model('divisas', 'CalculoOperacion')
    CalculoTriangulacion = apps.get_model('divisas', 'CalculoTriangulacion')
    ahora = timezone.now()

    CalculoOperacion.objects.filter(
        estado='PENDIENTE_CONFIRMACION', vence_en__lt=ahora
    ).update(estado='VENCIDA')
    CalculoTriangulacion.objects.filter(
        estado='PENDIENTE_CONFIRMACION', vence_en__lt=ahora
    ).update(estado='VENCIDA')


def revertir_marcado(apps, schema_editor):
    """No-op: no hace falta deshacer el backfill al revertir esta migración."""


class Migration(migrations.Migration):
    """Agrega 'Vencida' a los estados y marca los registros ya vencidos."""

    dependencies = [
        ('divisas', '0009_alter_calculooperacion_estado_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='calculooperacion',
            name='estado',
            field=models.CharField(choices=[('PENDIENTE_CONFIRMACION', 'Pendiente de confirmación'), ('CONFIRMADA', 'Confirmada'), ('CANCELADA', 'Cancelada'), ('VENCIDA', 'Vencida')], default='PENDIENTE_CONFIRMACION', max_length=25),
        ),
        migrations.AlterField(
            model_name='calculotriangulacion',
            name='estado',
            field=models.CharField(choices=[('PENDIENTE_CONFIRMACION', 'Pendiente de confirmación'), ('CONFIRMADA', 'Confirmada'), ('CANCELADA', 'Cancelada'), ('VENCIDA', 'Vencida')], default='PENDIENTE_CONFIRMACION', max_length=25),
        ),
        migrations.RunPython(marcar_pendientes_vencidas, revertir_marcado),
    ]
