"""Configuración de la app 'core' de sipap-sim."""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Registra la app que modela bancos, billeteras, cuentas y transferencias."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = 'SIPAP (simulado)'
