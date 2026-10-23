"""Configuración de sipap-sim.

Proyecto Django chico e independiente que simula la red bancaria (y de
billeteras digitales) para que Global Exchange pueda probar la HU "Pago
por transferencia bancaria vía SIPAP" sin acceso a la API real de SIPAP
(que no existe un sandbox público al que conectarse). No comparte código,
base de datos ni proceso con Global Exchange: se comunican solo por HTTP,
como lo harían con un proveedor real.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'sipap-sim-no-es-secreto-de-verdad')
DEBUG = os.environ.get('DEBUG', 'True') == 'True'
ALLOWED_HOSTS = [h.strip() for h in os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

ROOT_URLCONF = 'sipap_sim.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'sipap_sim.wsgi.application'

# Base propia: SQLite en desarrollo (no hace falta nada más para que
# levante); en el servidor, Postgres en la misma instancia RDS que usa
# Global Exchange (una base aparte, "sipap_sim", igual que se hizo con
# Keycloak), configurada por variables de entorno.
if os.environ.get('DB_HOST'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME', 'sipap_sim'),
            'USER': os.environ.get('DB_USER', ''),
            'PASSWORD': os.environ.get('DB_PASSWORD', ''),
            'HOST': os.environ.get('DB_HOST', ''),
            'PORT': os.environ.get('DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

LANGUAGE_CODE = 'es'
TIME_ZONE = 'America/Asuncion'
USE_I18N = True
USE_TZ = True

# Separador de miles en todos los montos que se muestran en pantalla
# (saldos, montos solicitados/acreditados): "." para miles y "," para
# decimales, igual que en Paraguay/Argentina. El locale "es" de Django
# ya usa "," de decimales, pero separa los miles con un espacio fino en
# vez de un punto, así que se sobreescribe puntualmente con un módulo de
# formato propio en sipap_sim/formats/es/formats.py, sin tocar
# LANGUAGE_CODE. Mismo patrón que global_exchange/settings/base.py.
USE_THOUSAND_SEPARATOR = True
FORMAT_MODULE_PATH = ['sipap_sim.formats']

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# En el servidor, Nginx expone este servicio bajo "/sipap/" y le quita el
# prefijo antes de reenviar la petición (ver deploy/aws/nginx/nginx.conf);
# esto le avisa a Django que lo vuelva a agregar al generar URLs (los
# "link_pago" que recibe Global Exchange, los redirect a url_retorno). En
# desarrollo, vacío: corre en su propio puerto, sin prefijo.
FORCE_SCRIPT_NAME = os.environ.get('SIPAP_SCRIPT_NAME') or None

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# El panel administrativo (alta de proveedores de pago y cuentas, ver
# core/views.py) requiere iniciar sesión con un usuario de staff
# (``python manage.py createsuperuser``, o cualquier usuario con
# ``is_staff=True``); no hay autoregistro.
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'panel'
LOGOUT_REDIRECT_URL = 'login'

# Nombres de cookie propios, distintos de los de Global Exchange
# ("sessionid"/"csrftoken", los mismos por defecto que usaría este
# proyecto si no se los cambiara). Son dos proyectos Django
# independientes, pero comparten navegador en quien los prueba a los
# dos (y, en producción, el mismo dominio): sin nombres distintos, la
# cookie de uno pisa la del otro y rompe el login o la verificación
# CSRF del que se haya visitado más recientemente, aunque corran en
# puertos distintos (el navegador no separa cookies por puerto).
SESSION_COOKIE_NAME = 'sipap_sessionid'
CSRF_COOKIE_NAME = 'sipap_csrftoken'

# En producción (DEBUG=False), las cookies de sesión y de CSRF del panel
# solo viajan por HTTPS. SECURE_PROXY_SSL_HEADER le avisa a Django que la
# conexión original es HTTPS aunque Gunicorn la reciba en texto plano
# detrás de Nginx, que termina TLS y reenvía con
# "X-Forwarded-Proto https" (ver deploy/aws/nginx/nginx.conf).
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# --- Específico de sipap-sim ---

# El token que Global Exchange tiene que mandar en
# "Authorization: Bearer <SIPAP_API_KEY>" para usar la API. Un valor de
# relleno en desarrollo porque, a diferencia de un secreto de verdad,
# ambos lados necesitan configurar el mismo valor para poder hablarse.
SIPAP_API_KEY = os.environ.get('SIPAP_API_KEY', 'sipap-sim-api-key-de-desarrollo')

# El secreto con el que se firman (HMAC-SHA256) los webhooks que este
# simulador le manda a Global Exchange. Tiene que coincidir con
# SIPAP_WEBHOOK_SECRET del lado de Global Exchange.
SIPAP_WEBHOOK_SECRET = os.environ.get('SIPAP_WEBHOOK_SECRET', 'sipap-sim-webhook-secret-de-desarrollo')

# A dónde mandar la confirmación de cada transferencia resuelta.
GLOBAL_EXCHANGE_WEBHOOK_URL = os.environ.get(
    'GLOBAL_EXCHANGE_WEBHOOK_URL', 'http://localhost:8000/webhooks/sipap/',
)

# Vacío (comportamiento normal) | "error" (la API de solicitudes-cobro
# responde 500) | "lento" (tarda más que cualquier timeout razonable).
# Permite probar, desde Global Exchange, el criterio "SIPAP no responde o
# la conexión falla" sin tener que apagar este servicio.
SIM_MODO_FALLA = os.environ.get('SIM_MODO_FALLA', '')
