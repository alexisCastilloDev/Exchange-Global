"""Crea la configuración de comisión editable por segmento de cliente."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Agrega el porcentaje de comisión por segmento y su auditoría de cambios."""

    dependencies = [
        ('divisas', '0004_calculotriangulacion'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ConfiguracionComision',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('segmento', models.CharField(choices=[('MINORISTA', 'Minorista'), ('VIP', 'VIP'), ('CORPORATIVO', 'Corporativo')], max_length=20, unique=True, verbose_name='Segmento / Categoría')),
                ('porcentaje', models.DecimalField(decimal_places=3, max_digits=6, verbose_name='Porcentaje de comisión (%)')),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                ('actualizado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='comisiones_actualizadas', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Configuración de comisión',
                'verbose_name_plural': 'Configuraciones de comisión',
                'ordering': ['segmento'],
            },
        ),
    ]
