"""Garantiza que el guaraní (PYG) exista como divisa base del sistema.

PYG es la moneda local contra la que se cotizan y operan todas las divisas
extranjeras (``Cotizacion.tasa_compra``/``tasa_venta`` ya están expresadas en
guaraníes por unidad de divisa extranjera, y ``CalculoOperacion``/
``CalculoTriangulacion`` liquidan siempre en PYG) — no es una divisa más que
un administrador deba dar de alta manualmente desde el catálogo de divisas
operables (``divisas:crear_divisa``, pensado para las divisas extranjeras que
sí se compran y venden). Antes de esta migración, el saldo en guaraníes de
una caja (``apps.caja.models.SaldoInicialCaja``/``OperacionVentanilla``)
dependía de que esa fila existiera "si existe" (ver
``apps.caja.forms.AperturaCajaForm``); en una base sin ella, comprar divisas
en ventanilla rompía con ``Divisa.DoesNotExist`` en vez de funcionar, porque
no había ninguna moneda local con la que calcular el saldo disponible.
"""
from django.db import migrations


def crear_divisa_pyg(apps, schema_editor):
    """Crea la divisa PYG si todavía no existe, sin duplicarla si ya está."""
    Divisa = apps.get_model('divisas', 'Divisa')
    Divisa.objects.get_or_create(
        codigo='PYG',
        defaults={'nombre': 'Guaraní', 'simbolo': 'Gs.', 'activa': True},
    )


class Migration(migrations.Migration):
    """Registra la carga de la divisa base PYG."""

    dependencies = [
        ('divisas', '0013_alter_calculooperacion_estado_and_more'),
    ]

    operations = [
        migrations.RunPython(crear_divisa_pyg, migrations.RunPython.noop),
    ]
