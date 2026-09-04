from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Cliente',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo_cliente', models.CharField(choices=[('FISICA', 'Persona Física'), ('JURIDICA', 'Persona Jurídica')], help_text='Indica si el cliente es persona física o jurídica.', max_length=10)),
                ('nombres', models.CharField(blank=True, help_text='Nombres del cliente (obligatorio para persona física).', max_length=150, null=True)),
                ('apellidos', models.CharField(blank=True, help_text='Apellidos del cliente (obligatorio para persona física).', max_length=150, null=True)),
                ('razon_social', models.CharField(blank=True, help_text='Razón social (obligatorio para persona jurídica).', max_length=200, null=True)),
                ('identificador', models.CharField(help_text='Documento de identidad (CI) o RUC. Debe ser único en el sistema.', max_length=50, unique=True)),
                ('fecha_registro', models.DateTimeField(auto_now_add=True, help_text='Fecha y hora en la que se registró el cliente en la plataforma.')),
            ],
            options={
                'verbose_name': 'Cliente',
                'verbose_name_plural': 'Clientes',
            },
        ),
    ]
