"""Datos base compartidos por los tests de sipap-sim.

Antes los cargaba la migración de datos ``core.migrations.0002_datos_iniciales``;
esa carga se eliminó (se reemplazó por el panel administrativo, ver
``core/views.py``: ``panel_view``, ``proveedores_view``, ``cuentas_view``),
así que cada test que necesita un banco o una cuenta ya cargados los crea
ahora con ``crear_banco_y_cuentas_pyg``, en su propio ``setUp``, en vez de
asumir que ya están en la base.
"""

from decimal import Decimal

from core.models import Cuenta, ProveedorPago

NUMERO_CUENTA_CLIENTE_PYG = '2000000000000101'
DOCUMENTO_CLIENTE_PYG = '3456789'
NOMBRE_BANCO = 'Banco Itaú Paraguay'


def crear_banco_y_cuentas_pyg():
    """Crea un banco, la cuenta de la casa de cambio en PYG y una cuenta de cliente en PYG.

    Returns:
        tuple[Cuenta, Cuenta]: ``(cuenta_casa_de_cambio, cuenta_cliente)``.
    """
    banco = ProveedorPago.objects.create(tipo=ProveedorPago.TIPO_BANCO, codigo='ITAU', nombre=NOMBRE_BANCO)
    casa = Cuenta.objects.create(
        numero='1000000000000001', proveedor=banco, titular='Global Exchange S.A.',
        documento='80012345-6', moneda='PYG', saldo=Decimal('500000000.00'), es_cuenta_casa_de_cambio=True,
    )
    cliente = Cuenta.objects.create(
        numero=NUMERO_CUENTA_CLIENTE_PYG, proveedor=banco, titular='Juan Pérez',
        documento=DOCUMENTO_CLIENTE_PYG, moneda='PYG', saldo=Decimal('15000000.00'),
    )
    return casa, cliente
