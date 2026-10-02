"""Asocia cada cotización con el usuario que la registró."""
from django.conf import settings
"""Asocia cada cotización con el usuario que la registró."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Agrega la auditoría del usuario actualizador de cotizaciones."""
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('divisas', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='cotizacion',
            name='usuario',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name='cotizaciones_actualizadas',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Usuario actualizador',
            ),
        ),
    ]
