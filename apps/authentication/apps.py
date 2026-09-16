"""Configuración de la aplicación de autenticación."""

from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    """Registra la aplicación de autenticación de Global Exchange."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.authentication'