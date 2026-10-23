"""Admin de sipap-sim: para inspeccionar y ajustar los datos de prueba a mano."""

from django.contrib import admin

from .models import Cuenta, ProveedorPago, Transferencia


@admin.register(ProveedorPago)
class ProveedorPagoAdmin(admin.ModelAdmin):
    """Lista bancos y billeteras digitales."""

    list_display = ['nombre', 'tipo', 'codigo']
    list_filter = ['tipo']


@admin.register(Cuenta)
class CuentaAdmin(admin.ModelAdmin):
    """Lista cuentas de prueba, incluida la de la casa de cambio.

    ``es_cuenta_casa_de_cambio`` queda de solo lectura también acá: ni
    siquiera por este admin de Django se decide cuál cuenta hace ese
    papel. La designa Global Exchange por API (ver
    ``core.views.designar_cuenta_casa_de_cambio``); esta pantalla solo
    la refleja.
    """

    list_display = ['numero', 'proveedor', 'titular', 'documento', 'moneda', 'saldo', 'es_cuenta_casa_de_cambio']
    list_filter = ['proveedor', 'moneda', 'es_cuenta_casa_de_cambio']
    search_fields = ['numero', 'titular', 'documento']
    readonly_fields = ['es_cuenta_casa_de_cambio']


@admin.register(Transferencia)
class TransferenciaAdmin(admin.ModelAdmin):
    """Lista transferencias, para revisar a mano cómo se resolvió cada solicitud de cobro."""

    list_display = ['id', 'estado', 'cuenta_origen', 'cuenta_destino', 'monto_solicitado', 'monto_acreditado', 'moneda', 'creado_en']
    list_filter = ['estado', 'moneda']
    search_fields = ['id', 'referencia']
    readonly_fields = ['id', 'creado_en']
