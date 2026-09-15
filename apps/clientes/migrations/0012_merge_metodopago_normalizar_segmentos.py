"""Unifica las ramas de migración de métodos y segmentos."""

from django.db import migrations


class Migration(migrations.Migration):
    """Marca como convergentes las dos migraciones paralelas."""

    dependencies = [
        ('clientes', '0011_metodopago'),
        ('clientes', '0011_normalizar_segmentos'),
    ]

    operations = []
