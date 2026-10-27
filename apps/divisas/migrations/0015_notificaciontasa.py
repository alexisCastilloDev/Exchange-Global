
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('divisas', '0014_crear_divisa_pyg'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='NotificacionTasa',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo_tasa', models.CharField(choices=[('COMPRA', 'Compra'), ('VENTA', 'Venta')], max_length=6, verbose_name='Tipo de tasa')),
                ('tasa_anterior', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Tasa anterior')),
                ('tasa_nueva', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Tasa nueva')),
                ('creada_en', models.DateTimeField(auto_now_add=True, verbose_name='Fecha de notificación')),
                ('leida', models.BooleanField(default=False, verbose_name='Leída')),
                ('leida_en', models.DateTimeField(blank=True, null=True, verbose_name='Fecha de lectura')),
                ('cotizacion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notificaciones', to='divisas.cotizacion', verbose_name='Cotización que generó el cambio')),
                ('divisa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notificaciones_tasa', to='divisas.divisa', verbose_name='Divisa')),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notificaciones_tasa', to=settings.AUTH_USER_MODEL, verbose_name='Usuario destinatario')),
            ],
            options={
                'verbose_name': 'Notificación de tasa',
                'verbose_name_plural': 'Notificaciones de tasas',
                'ordering': ['-creada_en', '-pk'],
                'indexes': [models.Index(fields=['usuario', 'leida'], name='notif_tasa_usuario_leida_idx')],
            },
        ),
    ]
