from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clientes', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='cliente',
            options={},
        ),
        migrations.RemoveField(
            model_name='cliente',
            name='apellidos',
        ),
        migrations.RemoveField(
            model_name='cliente',
            name='fecha_registro',
        ),
        migrations.RemoveField(
            model_name='cliente',
            name='identificador',
        ),
        migrations.RemoveField(
            model_name='cliente',
            name='nombres',
        ),
        migrations.RemoveField(
            model_name='cliente',
            name='razon_social',
        ),
        migrations.RemoveField(
            model_name='cliente',
            name='tipo_cliente',
        ),
        migrations.AddField(
            model_name='cliente',
            name='apellido',
            field=models.CharField(default='', max_length=100),
        ),
        migrations.AddField(
            model_name='cliente',
            name='email',
            field=models.EmailField(blank=True, max_length=254, null=True),
        ),
        migrations.AddField(
            model_name='cliente',
            name='nombre',
            field=models.CharField(default='Sin nombre', max_length=100),
            preserve_default=False,
        ),
    ]
