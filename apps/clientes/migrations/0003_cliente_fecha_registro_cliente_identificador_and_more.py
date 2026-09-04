import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clientes', '0002_alter_cliente_options_remove_cliente_apellidos_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='fecha_registro',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name='cliente',
            name='identificador',
            field=models.CharField(blank=True, max_length=20, null=True, unique=True, verbose_name='Identificador (CI / RUC)'),
        ),
        migrations.AddField(
            model_name='cliente',
            name='razon_social',
            field=models.CharField(blank=True, max_length=150, null=True, verbose_name='Razón Social'),
        ),
        migrations.AddField(
            model_name='cliente',
            name='tipo_cliente',
            field=models.CharField(choices=[('FISICA', 'Persona Física'), ('JURIDICA', 'Persona Jurídica')], default='FISICA', max_length=10, verbose_name='Tipo de Cliente'),
        ),
        migrations.AlterField(
            model_name='cliente',
            name='apellido',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='Apellido'),
        ),
        migrations.AlterField(
            model_name='cliente',
            name='email',
            field=models.EmailField(blank=True, max_length=254, null=True, unique=True, verbose_name='Correo Electrónico'),
        ),
        migrations.AlterField(
            model_name='cliente',
            name='nombre',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='Nombre'),
        ),
    ]
