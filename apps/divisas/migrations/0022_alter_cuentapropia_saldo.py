
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('divisas', '0021_cuenta_propia_por_divisa_existente'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cuentapropia',
            name='saldo',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=30),
        ),
    ]
