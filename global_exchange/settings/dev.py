"""Configuración de desarrollo con base de datos PostgreSQL."""

import sys

from .base import *

DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1', 'testserver']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('DB_NAME_DEV'),
        'USER': env('DB_USER'),
        'PASSWORD': env('DB_PASSWORD'),
        'HOST': env('DB_HOST'),
        'PORT': env('DB_PORT', default='5432'),
    }
}

if 'test' in sys.argv:
    # `manage.py test` usa este mismo módulo de settings (ver .env:
    # DJANGO_SETTINGS_MODULE), así que cualquier credencial real queda
    # activa durante los tests salvo que se anule explícitamente acá.
    # Ningún test fuera de tests/test_factura_electronica.py mockea
    # apps.divisas.factura_electronica.requests.post, y los hooks de
    # pago (_procesar_sesion_completada/_cobrar_con_tarjeta_guardada/
    # _procesar_confirmacion_sipap) llaman a
    # intentar_emitir_documento_electronico apenas una transacción
    # queda "Pagada" en CUALQUIER test que llegue a ese estado — con un
    # FACTURASEGURA_AUTH_TOKEN real, eso dispara una llamada real a
    # generar_de y consume un número real del rango escaso habilitado.
    # Apuntar a un puerto cerrado hace que esa llamada falle rápido con
    # un error de conexión (contenido por
    # intentar_emitir_documento_electronico, que nunca relanza nada) en
    # vez de alcanzar la API real; los tests que sí quieren probar el
    # módulo mockean requests.post directamente, así que nunca llegan a
    # usar esta URL.
    FACTURASEGURA_BASE_URL = 'http://127.0.0.1:1/'
    FACTURASEGURA_AUTH_TOKEN = ''