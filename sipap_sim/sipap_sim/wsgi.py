"""Configuración WSGI de sipap-sim."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sipap_sim.settings')

application = get_wsgi_application()
