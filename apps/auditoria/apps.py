"""Configuración de la aplicación de auditoría."""

from django.apps import AppConfig


class AuditoriaConfig(AppConfig):
    """Registra la aplicación de auditoría y conecta sus señales al iniciar."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.auditoria'
    verbose_name = 'Auditoría'

    def ready(self):
        """Conecta los receptores que registran las altas, modificaciones y bajas.

        Se hace en ``ready`` (y no al importar ``models``) porque recién
        en este punto todos los modelos auditados, de otras aplicaciones,
        están cargados en el registro de Django.
        """
        from apps.auditoria.signals import conectar_senales
        conectar_senales()
