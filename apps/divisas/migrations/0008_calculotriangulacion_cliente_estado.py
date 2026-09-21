"""Agrega el cliente activo y el estado de la transacción a CalculoTriangulacion.

El cliente se resuelve a partir del usuario que ya tenía cada cambio (por
titularidad directa o por asociación como operador), igual que en
``0006_calculooperacion_cliente_estado``. Todos los registros existentes
quedan en "Pendiente de confirmación", único estado posible.
"""

import django.db.models.deletion
from django.db import migrations, models


def poblar_cliente(apps, schema_editor):
    """Resuelve el cliente de cada cambio existente a partir de su usuario."""
    CalculoTriangulacion = apps.get_model('divisas', 'CalculoTriangulacion')
    Cliente = apps.get_model('clientes', 'Cliente')

    for calculo in CalculoTriangulacion.objects.all():
        cliente = Cliente.objects.filter(user_id=calculo.usuario_id).first()
        if cliente is None:
            cliente = Cliente.objects.filter(usuarios__id=calculo.usuario_id).first()
        if cliente is not None:
            calculo.cliente_id = cliente.pk
            calculo.save(update_fields=['cliente'])


def revertir_cliente(apps, schema_editor):
    """No-op: no hace falta deshacer datos al revertir esta migración."""


class Migration(migrations.Migration):
    """Agrega ``cliente`` (FK) y ``estado`` a CalculoTriangulacion con backfill."""

    dependencies = [
        ('clientes', '0014_remove_metodopago_ultimos_4_digitos_and_more'),
        ('divisas', '0007_alter_calculooperacion_estado'),
    ]

    operations = [
        migrations.AddField(
            model_name='calculotriangulacion',
            name='cliente',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='calculos_triangulacion',
                to='clientes.cliente',
                verbose_name='Cliente',
            ),
        ),
        migrations.AddField(
            model_name='calculotriangulacion',
            name='estado',
            field=models.CharField(
                choices=[('PENDIENTE_CONFIRMACION', 'Pendiente de confirmación')],
                default='PENDIENTE_CONFIRMACION',
                max_length=25,
            ),
        ),
        migrations.RunPython(poblar_cliente, revertir_cliente),
        migrations.AlterField(
            model_name='calculotriangulacion',
            name='cliente',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='calculos_triangulacion',
                to='clientes.cliente',
                verbose_name='Cliente',
            ),
        ),
    ]
