"""
Configuración WSGI para el proyecto global_exchange.

Este módulo expone el objeto WSGI llamado `application`.

Para más información sobre WSGI y su despliegue, ver:
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    os.environ.get('DJANGO_SETTINGS_MODULE', 'global_exchange.settings.dev')
)

application = get_wsgi_application()