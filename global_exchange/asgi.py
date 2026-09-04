"""
Configuración ASGI para el proyecto global_exchange.

Este módulo expone el objeto ASGI llamado `application`.

Para más información sobre ASGI y su despliegue, ver:
https://docs.djangoproject.com/en/6.1/howto/deployment/asgi/
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    os.environ.get('DJANGO_SETTINGS_MODULE', 'global_exchange.settings.dev')
)

application = get_asgi_application()