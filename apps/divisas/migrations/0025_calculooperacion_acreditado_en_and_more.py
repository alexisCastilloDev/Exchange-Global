from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('divisas', '0024_calculooperacion_tasa_vence_en_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='calculooperacion',
            name='acreditado_en',
            field=models.DateTimeField(blank=True, help_text='Fecha y hora en que la entrega de una compra (o de un cambio entre divisas) se completó con éxito (ver ``apps.divisas.entrega.realizar_entrega``). Una venta no usa este campo: "retirar" lo que deja una venta es una HU aparte ("Retiro de fondos") todavía no implementada.', null=True, verbose_name='Acreditado en'),
        ),
        migrations.AddField(
            model_name='calculooperacion',
            name='referencia_acreditacion',
            field=models.CharField(blank=True, help_text='La misma referencia con la que se le pidió la transferencia a sipap-sim.', max_length=60, verbose_name='Referencia de la acreditación'),
        ),
        migrations.AddField(
            model_name='calculotriangulacion',
            name='acreditado_en',
            field=models.DateTimeField(blank=True, help_text='Ver CalculoOperacion.acreditado_en: mismo criterio, aplicado al cambio entre divisas.', null=True, verbose_name='Acreditado en'),
        ),
        migrations.AddField(
            model_name='calculotriangulacion',
            name='referencia_acreditacion',
            field=models.CharField(blank=True, help_text='La misma referencia con la que se le pidió la transferencia a sipap-sim.', max_length=60, verbose_name='Referencia de la acreditación'),
        ),
        migrations.AlterField(
            model_name='calculooperacion',
            name='estado',
            field=models.CharField(choices=[('PENDIENTE_CONFIRMACION', 'Pendiente de confirmación'), ('CONFIRMADA', 'Confirmada'), ('CANCELADA', 'Cancelada'), ('VENCIDA', 'Vencida'), ('CANCELADA_COTIZACION', 'Cancelada por cambio de cotización'), ('CANCELADA_SALDO_INSUFICIENTE', 'Cancelada por saldo insuficiente de Global Exchange'), ('CANCELADA_FONDOS_CLIENTE', 'Cancelada por fondos insuficientes del cliente'), ('PAGADA', 'Pagada'), ('ENTREGA_FALLIDA', 'Pagada, pero la entrega al cliente falló'), ('PAGO_EXPIRADO', 'Pago fuera de plazo'), ('ACREDITADA', 'Acreditada')], default='PENDIENTE_CONFIRMACION', max_length=30),
        ),
        migrations.AlterField(
            model_name='calculotriangulacion',
            name='estado',
            field=models.CharField(choices=[('PENDIENTE_CONFIRMACION', 'Pendiente de confirmación'), ('CONFIRMADA', 'Confirmada'), ('CANCELADA', 'Cancelada'), ('VENCIDA', 'Vencida'), ('CANCELADA_COTIZACION', 'Cancelada por cambio de cotización'), ('CANCELADA_SALDO_INSUFICIENTE', 'Cancelada por saldo insuficiente de Global Exchange'), ('CANCELADA_FONDOS_CLIENTE', 'Cancelada por fondos insuficientes del cliente'), ('PAGADA', 'Pagada'), ('ENTREGA_FALLIDA', 'Pagada, pero la entrega al cliente falló'), ('PAGO_EXPIRADO', 'Pago fuera de plazo'), ('ACREDITADA', 'Acreditada')], default='PENDIENTE_CONFIRMACION', max_length=30),
        ),
    ]
