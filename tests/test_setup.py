"""Pruebas mínimas de carga de configuración Django."""

from django.conf import settings

def test_django_settings_loaded():
    """Confirma que el entorno de pruebas cargó la configuración."""
    assert settings.configured is True