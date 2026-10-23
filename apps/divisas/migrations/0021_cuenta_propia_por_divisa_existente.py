"""Crea la cuenta propia (saldo 0) de cada divisa que ya existía.

``CuentaPropia`` es el saldo propio de Global Exchange en una moneda:
sin esta fila, ninguna operación en esa moneda podría confirmarse nunca
(el chequeo de saldo, al no encontrar ninguna cuenta, la trataría como
"sin fondos" — ver ``apps.divisas.views._verificar_saldo_casa_de_cambio``).
Para cualquier divisa nueva dada de alta después de esta migración, la
crea sola ``DivisaCreateView.form_valid``; esto cubre las que ya
existían antes de que ``CuentaPropia`` existiera, incluida PYG.
"""

from decimal import Decimal

from django.db import migrations


def crear_cuentas_propias(apps, schema_editor):
    Divisa = apps.get_model('divisas', 'Divisa')
    CuentaPropia = apps.get_model('divisas', 'CuentaPropia')
    for divisa in Divisa.objects.all():
        CuentaPropia.objects.get_or_create(divisa=divisa, defaults={'saldo': Decimal('0.00')})


def borrar_cuentas_propias(apps, schema_editor):
    apps.get_model('divisas', 'CuentaPropia').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('divisas', '0020_cuentapropia'),
    ]

    operations = [
        migrations.RunPython(crear_cuentas_propias, borrar_cuentas_propias),
    ]
