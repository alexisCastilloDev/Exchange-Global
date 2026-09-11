from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('authentication', '0004_eliminar_recurso_protegido'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='HistorialBaja',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo_recurso', models.CharField(choices=[('USUARIO', 'Usuario'), ('DIVISA', 'Divisa'), ('CLIENTE', 'Cliente')], max_length=10)),
                ('recurso_id', models.PositiveBigIntegerField()),
                ('recurso_nombre', models.CharField(max_length=255)),
                ('causa', models.TextField()),
                ('fecha', models.DateTimeField(auto_now_add=True)),
                ('realizado_por', models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name='bajas_realizadas', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Historial de baja',
                'verbose_name_plural': 'Historial de bajas',
                'ordering': ['-fecha'],
            },
        ),
    ]
