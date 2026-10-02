"""Crea la configuración editable de los tiempos de espera de las operaciones."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Agrega el registro único donde el administrador configura ambas vigencias."""

    dependencies = [
        ('divisas', '0010_alter_calculooperacion_estado_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ConfiguracionVigencia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('calculo_vigencia_segundos', models.IntegerField(help_text='Tiempo entre calcular el importe y confirmarlo, antes de que la cotización venza.', verbose_name='Tiempo de espera para confirmar el importe (segundos)')),
                ('confirmacion_vigencia_segundos', models.IntegerField(help_text='Tiempo entre confirmar el importe y confirmar o cancelar la operación, antes de que la transacción venza.', verbose_name='Tiempo de espera para confirmar la operación (segundos)')),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                ('actualizado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='vigencias_actualizadas', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Configuración de vigencia',
                'verbose_name_plural': 'Configuración de vigencia',
            },
        ),
    ]
