
import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('divisas', '0013_alter_calculooperacion_estado_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='pago',
            name='diferencia',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Solo tiene valor cuando `observado` es verdadero.', max_digits=18, null=True, verbose_name='Diferencia (monto recibido − monto esperado)'),
        ),
        migrations.AddField(
            model_name='pago',
            name='observado',
            field=models.BooleanField(default=False, help_text='El proveedor confirmó un pago, pero por un monto distinto del esperado (ver `diferencia`): queda registrado para revisión manual, sin marcar la transacción como "Pagada".', verbose_name='Observado'),
        ),
        migrations.CreateModel(
            name='SolicitudPagoSipap',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('referencia', models.CharField(help_text='El cliente la usa como concepto/referencia al transferir; SIPAP la devuelve en la confirmación.', max_length=40, unique=True, verbose_name='Referencia única')),
                ('monto', models.DecimalField(decimal_places=2, max_digits=18, verbose_name='Monto esperado')),
                ('moneda', models.CharField(max_length=3, verbose_name='Moneda esperada')),
                ('estado', models.CharField(choices=[('PENDIENTE', 'Pendiente'), ('ACREDITADA', 'Acreditada'), ('OBSERVADA', 'Observada'), ('RECHAZADA', 'Rechazada'), ('VENCIDA', 'Vencida')], default='PENDIENTE', max_length=20)),
                ('banco_origen', models.CharField(blank=True, max_length=100, null=True, verbose_name='Banco de origen')),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('vence_en', models.DateTimeField()),
                ('calculo_operacion', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='solicitud_sipap', to='divisas.calculooperacion', verbose_name='Compra o venta a pagar')),
                ('calculo_triangulacion', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='solicitud_sipap', to='divisas.calculotriangulacion', verbose_name='Cambio de divisas a pagar')),
                ('pago', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='solicitud_sipap', to='divisas.pago', verbose_name='Pago resultante (exitoso u observado)')),
            ],
            options={
                'verbose_name': 'Solicitud de pago SIPAP',
                'verbose_name_plural': 'Solicitudes de pago SIPAP',
                'ordering': ['-creado_en'],
            },
        ),
    ]
