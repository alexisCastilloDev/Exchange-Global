"""Carga los datos de prueba: bancos, billeteras, cuenta de la casa de cambio y clientes.

Los bancos y la moneda de cada cuenta son los que pide la especificación
de la HU; los nombres de las billeteras digitales y los datos concretos
de los clientes de prueba (titular, CI/RUC, saldo) son de relleno, solo
para tener con qué probar la "banca en línea" simulada de punta a punta.
"""

from decimal import Decimal

from django.db import migrations, models


def cargar_datos(apps, schema_editor):
    ProveedorPago = apps.get_model('core', 'ProveedorPago')
    Cuenta = apps.get_model('core', 'Cuenta')

    bancos = [
        ProveedorPago.objects.create(tipo='BANCO', codigo='ITAU', nombre='Banco Itaú Paraguay'),
        ProveedorPago.objects.create(tipo='BANCO', codigo='CONTINENTAL', nombre='Banco Continental'),
        ProveedorPago.objects.create(tipo='BANCO', codigo='UENO', nombre='Banco Ueno'),
        ProveedorPago.objects.create(tipo='BANCO', codigo='FAMILIAR', nombre='Banco Familiar'),
    ]
    billeteras = [
        ProveedorPago.objects.create(tipo='BILLETERA', codigo='TIGO_MONEY', nombre='Tigo Money'),
        ProveedorPago.objects.create(tipo='BILLETERA', codigo='BILLETERA_PERSONAL', nombre='Billetera Personal'),
        ProveedorPago.objects.create(tipo='BILLETERA', codigo='ZIMPLE', nombre='Zimple'),
    ]

    casa_de_cambio_pyg = Cuenta.objects.create(
        numero='1000000000000001', proveedor=bancos[0], titular='Global Exchange S.A.',
        documento='80012345-6', moneda='PYG', saldo=Decimal('500000000.00'), es_cuenta_casa_de_cambio=True,
    )
    casa_de_cambio_usd = Cuenta.objects.create(
        numero='1000000000000002', proveedor=bancos[0], titular='Global Exchange S.A.',
        documento='80012345-6', moneda='USD', saldo=Decimal('100000.00'), es_cuenta_casa_de_cambio=True,
    )

    clientes = [
        # (proveedor, número, titular, documento, moneda, saldo)
        (bancos[0], '2000000000000101', 'Juan Pérez', '3456789', 'PYG', Decimal('15000000.00')),
        (bancos[0], '2000000000000102', 'Juan Pérez', '3456789', 'USD', Decimal('2000.00')),
        (bancos[1], '2000000000000201', 'María Gómez', '4567890', 'PYG', Decimal('8000000.00')),
        (bancos[2], '2000000000000301', 'Carlos Ruiz', '5678901', 'PYG', Decimal('500000.00')),
        (bancos[3], '2000000000000401', 'Ana Benítez', '6789012', 'USD', Decimal('500.00')),
        (bancos[0], '0000000000000000', 'Rodrigo Mereles', '5739794', 'PYG', Decimal('15000000.00')),
        (billeteras[0], '2000000000000501', 'Juan Pérez', '3456789', 'PYG', Decimal('1200000.00')),
        (billeteras[1], '2000000000000601', 'María Gómez', '4567890', 'PYG', Decimal('300000.00')),
        (billeteras[2], '2000000000000701', 'Carlos Ruiz', '5678901', 'USD', Decimal('150.00')),
    ]
    for proveedor, numero, titular, documento, moneda, saldo in clientes:
        Cuenta.objects.create(
            numero=numero, proveedor=proveedor, titular=titular,
            documento=documento, moneda=moneda, saldo=saldo,
        )


def borrar_datos(apps, schema_editor):
    apps.get_model('core', 'Cuenta').objects.all().delete()
    apps.get_model('core', 'ProveedorPago').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='proveedorpago',
            name='codigo',
            field=models.CharField(max_length=20, unique=True),
        ),
        migrations.RunPython(cargar_datos, borrar_datos),
    ]
