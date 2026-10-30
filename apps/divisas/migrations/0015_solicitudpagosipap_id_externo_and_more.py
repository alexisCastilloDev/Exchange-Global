
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('divisas', '0014_pago_diferencia_pago_observado_solicitudpagosipap'),
    ]

    operations = [
        migrations.AddField(
            model_name='solicitudpagosipap',
            name='id_externo',
            field=models.CharField(blank=True, help_text='El id que devuelve sipap-sim al crear la solicitud de cobro.', max_length=60, null=True, verbose_name='ID de la transferencia en SIPAP'),
        ),
        migrations.AddField(
            model_name='solicitudpagosipap',
            name='link_pago',
            field=models.URLField(blank=True, help_text='La "banca en línea" de sipap-sim a la que se redirige al cliente para completar la transferencia.', max_length=500, verbose_name='Link de pago'),
        ),
        migrations.AddField(
            model_name='solicitudpagosipap',
            name='medio_pago',
            field=models.CharField(choices=[('TRANSFERENCIA', 'Transferencia Bancaria'), ('BILLETERA', 'Billetera Digital')], default='TRANSFERENCIA', help_text='Transferencia bancaria o billetera digital: ambas se resuelven con sipap-sim, pero se muestran distinto en el historial de pagos.', max_length=20, verbose_name='Medio de pago'),
        ),
    ]
