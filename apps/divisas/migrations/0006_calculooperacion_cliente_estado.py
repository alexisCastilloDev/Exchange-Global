"""Agrega el cliente activo y el estado de la transacción a CalculoOperacion.

El cliente se resuelve a partir del usuario que ya tenía cada cálculo
(por titularidad directa o por asociación como operador), igual que se
hizo para ``MetodoPago`` en ``apps.clientes.migrations.0013``. El estado
se infiere de ``confirmado_en`` para los registros existentes.
"""

import django.db.models.deletion
from django.db import migrations, models


def poblar_cliente_y_estado(apps, schema_editor):
    """Resuelve el cliente de cada cálculo existente y ajusta su estado."""
    CalculoOperacion = apps.get_model('divisas', 'CalculoOperacion')
    Cliente = apps.get_model('clientes', 'Cliente')

    for calculo in CalculoOperacion.objects.all():
        cliente = Cliente.objects.filter(user_id=calculo.usuario_id).first()
        if cliente is None:
            cliente = Cliente.objects.filter(usuarios__id=calculo.usuario_id).first()
        actualizar = ['estado']
        if cliente is not None:
            calculo.cliente_id = cliente.pk
            actualizar.append('cliente')
        calculo.estado = 'CONFIRMADA' if calculo.confirmado_en else 'PENDIENTE_CONFIRMACION'
        calculo.save(update_fields=actualizar)


def revertir_cliente_y_estado(apps, schema_editor):
    """No-op: no hace falta deshacer datos al revertir esta migración."""


class Migration(migrations.Migration):
    """Agrega ``cliente`` (FK) y ``estado`` a CalculoOperacion con backfill."""

    dependencies = [
        ('clientes', '0013_cliente_comision_personalizada_and_more'),
        ('divisas', '0005_configuracioncomision'),
    ]

    operations = [
        migrations.AddField(
            model_name='calculooperacion',
            name='cliente',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='calculos_operacion',
                to='clientes.cliente',
                verbose_name='Cliente',
            ),
        ),
        migrations.AddField(
            model_name='calculooperacion',
            name='estado',
            field=models.CharField(
                choices=[
                    ('PENDIENTE_CONFIRMACION', 'Pendiente de confirmación'),
                    ('CONFIRMADA', 'Confirmada'),
                ],
                default='PENDIENTE_CONFIRMACION',
                max_length=25,
            ),
        ),
        migrations.RunPython(poblar_cliente_y_estado, revertir_cliente_y_estado),
        migrations.AlterField(
            model_name='calculooperacion',
            name='cliente',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='calculos_operacion',
                to='clientes.cliente',
                verbose_name='Cliente',
            ),
        ),
    ]
