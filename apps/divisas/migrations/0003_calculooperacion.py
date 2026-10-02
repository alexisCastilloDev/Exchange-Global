"""Crea el registro persistente de cálculos de operaciones cambiarias."""

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Agrega cálculos con comisión, tasa aplicada y fecha de vencimiento."""

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('divisas', '0002_cotizacion_usuario'),
    ]

    operations = [
        migrations.CreateModel(
            name='CalculoOperacion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('tipo', models.CharField(choices=[('COMPRA', 'Compra'), ('VENTA', 'Venta')], max_length=7)),
                ('codigo_divisa', models.CharField(max_length=3)),
                ('monto_origen', models.DecimalField(decimal_places=2, max_digits=18)),
                ('tasa_aplicada', models.DecimalField(decimal_places=6, max_digits=18)),
                ('comision_porcentaje', models.DecimalField(decimal_places=3, max_digits=6)),
                ('comision', models.DecimalField(decimal_places=2, max_digits=18)),
                ('monto_final', models.DecimalField(decimal_places=2, max_digits=18)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('vence_en', models.DateTimeField()),
                ('confirmado_en', models.DateTimeField(blank=True, null=True)),
                ('divisa', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='calculos_operacion', to='divisas.divisa')),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='calculos_operacion', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Cálculo de operación',
                'verbose_name_plural': 'Cálculos de operaciones',
                'ordering': ['-creado_en'],
            },
        ),
    ]
