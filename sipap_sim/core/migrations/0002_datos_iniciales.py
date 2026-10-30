"""Ajusta el largo de ``codigo`` en ``ProveedorPago``.

Hasta acá, esta migración también cargaba datos de prueba (bancos,
billeteras, la cuenta de la casa de cambio y cuentas de clientes) con
``RunPython``. Esa carga se eliminó: ahora todo eso se da de alta desde
el panel administrativo (``core.views.panel_view`` y siguientes, detrás
de login con un usuario de staff), para que funcione igual en
desarrollo, en los tests y en producción, sin depender de datos fijos
versionados en el código. El nombre del archivo se conserva (en vez de
borrarlo) porque ``0004`` ya depende de él en cualquier base que lo
tenga aplicado.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='proveedorpago',
            name='codigo',
            field=models.CharField(max_length=20, unique=True),
        ),
    ]
