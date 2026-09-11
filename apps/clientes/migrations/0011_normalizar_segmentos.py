from django.db import migrations, models


def normalizar_segmentos(apps, schema_editor):
    Cliente = apps.get_model('clientes', 'Cliente')
    Cliente.objects.filter(segmento='ESTANDAR').update(segmento='MINORISTA')
    Cliente.objects.filter(segmento='PREMIUM').update(segmento='VIP')


class Migration(migrations.Migration):
    dependencies = [
        ('clientes', '0010_cliente_user'),
    ]

    operations = [
        migrations.RunPython(normalizar_segmentos, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='cliente',
            name='segmento',
            field=models.CharField(
                choices=[
                    ('MINORISTA', 'Minorista'),
                    ('VIP', 'VIP'),
                    ('CORPORATIVO', 'Corporativo'),
                ],
                default='MINORISTA',
                help_text='Permite clasificar al cliente.',
                max_length=20,
                verbose_name='Segmento / Categoría',
            ),
        ),
    ]
