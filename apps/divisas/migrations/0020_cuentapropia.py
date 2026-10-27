
import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('divisas', '0019_calculooperacion_medio_destino_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='CuentaPropia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('saldo', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=20)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                ('divisa', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='cuenta_propia', to='divisas.divisa')),
            ],
            options={
                'verbose_name': 'Cuenta propia',
                'verbose_name_plural': 'Cuentas propias',
                'ordering': ['divisa__codigo'],
            },
        ),
    ]
