from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clientes', '0004_cliente_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='segmento',
            field=models.CharField(choices=[('ESTANDAR', 'Estándar'), ('PREMIUM', 'Premium'), ('VIP', 'VIP'), ('CORPORATIVO', 'Corporativo')], default='ESTANDAR', help_text='Permite clasificar al cliente para diferenciarlo según características de Global Exchange.', max_length=20, verbose_name='Segmento / Categoría'),
        ),
    ]
