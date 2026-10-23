"""Asigna moneda=PYG a los métodos de pago de tipo tarjeta que ya existían.

Una tarjeta siempre cobró (y siempre cobrará) en PYG — ver
``apps.divisas.models.moneda_a_pagar`` — así que es un dato que se puede
inferir con certeza para cualquier fila cargada antes de que
``MetodoPago.moneda`` existiera, sin volver a consultar nada. Las filas
de transferencia o billetera existentes quedan sin tocar: no hay forma
segura de saber en qué moneda está una cuenta ya registrada sin
volver a validarla contra sipap-sim.
"""

from django.db import migrations


def asignar_pyg_a_tarjetas(apps, schema_editor):
    MetodoPago = apps.get_model('clientes', 'MetodoPago')
    Divisa = apps.get_model('divisas', 'Divisa')
    pyg = Divisa.objects.filter(codigo='PYG').first()
    if pyg is None:
        return
    MetodoPago.objects.filter(tipo_medio='TARJETA', moneda__isnull=True).update(moneda=pyg)


def revertir(apps, schema_editor):
    """No hay nada que revertir: quitar la moneda no deshace ningún dato perdido."""


class Migration(migrations.Migration):

    dependencies = [
        ('clientes', '0018_metodopago_moneda'),
        ('divisas', '0018_merge_0015_notificaciontasa_0017_asegurar_divisa_pyg'),
    ]

    operations = [
        migrations.RunPython(asignar_pyg_a_tarjetas, revertir),
    ]
