"""Asegura que exista la divisa base PYG, siempre activa.

Hay módulos que dependen de que haya una fila ``Divisa`` con
``codigo='PYG'`` y ``activa=True`` (p. ej. ``apps.caja.forms.AperturaCajaForm``,
que genera un campo "Saldo inicial en PYG" a partir de
``Divisa.objects.filter(activa=True)``), pero PYG no se gestiona desde el
catálogo administrable de divisas (``apps.divisas.forms.DivisaForm`` la
rechaza explícitamente): es la moneda base del sistema, no una divisa que
un administrador dé de alta o edite. Esta migración es idempotente
(``update_or_create``) para que no importe si la fila ya existe con otro
nombre o símbolo.
"""

from django.db import migrations


def asegurar_pyg(apps, schema_editor):
    Divisa = apps.get_model('divisas', 'Divisa')
    Divisa.objects.update_or_create(
        codigo='PYG',
        defaults={'nombre': 'Guaraní', 'simbolo': 'Gs.', 'activa': True},
    )


def revertir(apps, schema_editor):
    """No borra la fila: otros datos (cotizaciones, cajas) pueden depender de ella."""


class Migration(migrations.Migration):

    dependencies = [
        ('divisas', '0016_solicitudpagosipap_metodo_pago'),
    ]

    operations = [
        migrations.RunPython(asegurar_pyg, revertir),
    ]
