"""Crea el registro persistente de cálculos de triangulación entre divisas."""

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Agrega la triangulación con tasa cruzada, comisión y vencimiento."""

    dependencies = [
        ('divisas', '0003_calculooperacion'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CalculoTriangulacion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('codigo_divisa_origen', models.CharField(max_length=3)),
                ('codigo_divisa_destino', models.CharField(max_length=3)),
                ('monto_origen', models.DecimalField(decimal_places=2, max_digits=18)),
                ('tasa_compra_aplicada', models.DecimalField(decimal_places=6, max_digits=18)),
                ('tasa_venta_aplicada', models.DecimalField(decimal_places=6, max_digits=18)),
                ('tasa_cruzada', models.DecimalField(decimal_places=6, max_digits=18)),
                ('monto_equivalente_pyg', models.DecimalField(decimal_places=2, max_digits=18)),
                ('comision_porcentaje', models.DecimalField(decimal_places=3, max_digits=6)),
                ('comision', models.DecimalField(decimal_places=2, max_digits=18)),
                ('monto_final', models.DecimalField(decimal_places=2, max_digits=18)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('vence_en', models.DateTimeField()),
                ('confirmado_en', models.DateTimeField(blank=True, null=True)),
                ('divisa_destino', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='triangulaciones_destino', to='divisas.divisa')),
                ('divisa_origen', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='triangulaciones_origen', to='divisas.divisa')),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='triangulaciones', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Cálculo de triangulación',
                'verbose_name_plural': 'Cálculos de triangulación',
                'ordering': ['-creado_en'],
            },
        ),
    ]
