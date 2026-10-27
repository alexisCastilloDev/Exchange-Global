
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('divisas', '0022_alter_cuentapropia_saldo'),
    ]

    operations = [
        migrations.AlterField(
            model_name='calculooperacion',
            name='estado',
            field=models.CharField(choices=[('PENDIENTE_CONFIRMACION', 'Pendiente de confirmación'), ('CONFIRMADA', 'Confirmada'), ('CANCELADA', 'Cancelada'), ('VENCIDA', 'Vencida'), ('CANCELADA_COTIZACION', 'Cancelada por cambio de cotización'), ('CANCELADA_SALDO_INSUFICIENTE', 'Cancelada por saldo insuficiente de Global Exchange'), ('CANCELADA_FONDOS_CLIENTE', 'Cancelada por fondos insuficientes del cliente'), ('PAGADA', 'Pagada'), ('ENTREGA_FALLIDA', 'Pagada, pero la entrega al cliente falló')], default='PENDIENTE_CONFIRMACION', max_length=30),
        ),
        migrations.AlterField(
            model_name='calculotriangulacion',
            name='estado',
            field=models.CharField(choices=[('PENDIENTE_CONFIRMACION', 'Pendiente de confirmación'), ('CONFIRMADA', 'Confirmada'), ('CANCELADA', 'Cancelada'), ('VENCIDA', 'Vencida'), ('CANCELADA_COTIZACION', 'Cancelada por cambio de cotización'), ('CANCELADA_SALDO_INSUFICIENTE', 'Cancelada por saldo insuficiente de Global Exchange'), ('CANCELADA_FONDOS_CLIENTE', 'Cancelada por fondos insuficientes del cliente'), ('PAGADA', 'Pagada'), ('ENTREGA_FALLIDA', 'Pagada, pero la entrega al cliente falló')], default='PENDIENTE_CONFIRMACION', max_length=30),
        ),
        migrations.AlterField(
            model_name='solicitudpagosipap',
            name='estado',
            field=models.CharField(choices=[('PENDIENTE', 'Pendiente'), ('ACREDITADA', 'Acreditada'), ('OBSERVADA', 'Observada'), ('RECHAZADA', 'Rechazada'), ('VENCIDA', 'Vencida'), ('SALDO_INSUFICIENTE', 'Saldo insuficiente del cliente')], default='PENDIENTE', max_length=20),
        ),
    ]
