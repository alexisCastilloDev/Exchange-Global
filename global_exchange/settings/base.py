"""
Configuración base compartida entre dev y prod.
"""
from pathlib import Path
from decimal import Decimal
import environ

# BASE_DIR: sube 3 niveles porque settings/base.py está en settings/, dentro de global_exchange/
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Inicializa django-environ y lee el .env desde la raíz del proyecto
env = environ.Env()
environ.Env.read_env(BASE_DIR / '.env')

SECRET_KEY = env('SECRET_KEY')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'mozilla_django_oidc',
    
    'apps.divisas',
    'apps.users',
    'apps.authentication', 
    'apps.clientes',       
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    'apps.clientes.middleware.ClienteActivoMiddleware',
]

ROOT_URLCONF = 'global_exchange.urls'

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
                'apps.clientes.context_processors.cliente_activo_context',
                'apps.authentication.context_processors.permisos_ui_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'global_exchange.wsgi.application'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = 'oidc_authentication_init'

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'America/Asuncion'
USE_I18N = True
USE_TZ = True

# Separador de miles en todos los números que se muestran en pantalla
# (montos, tasas, comisiones, etc.): "." para miles y "," para decimales,
# igual que en Paraguay/Argentina. Django no trae ese formato para el
# locale "en-us" (usa "," de miles y "." de decimales), así que se
# sobreescribe puntualmente con un módulo de formato propio en
# global_exchange/formats/en_US/formats.py, sin tocar LANGUAGE_CODE ni,
# por lo tanto, los mensajes de validación en inglés que el resto del
# proyecto ya reemplaza a mano por mensajes en español.
USE_THOUSAND_SEPARATOR = True
FORMAT_MODULE_PATH = ['global_exchange.formats']

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
# El directorio static/ vivía en la raíz del proyecto pero nunca estaba
# declarado acá, por lo que el finder de staticfiles no lo encontraba y
# {% static %} devolvía rutas rotas en desarrollo.
STATICFILES_DIRS = [BASE_DIR / 'static']

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Alinea los tags de django.contrib.messages con las clases de alerta
# de Bootstrap (por defecto usa "error", Bootstrap espera "danger").
from django.contrib.messages import constants as messages_constants
MESSAGE_TAGS = {
    messages_constants.ERROR: 'danger',
}

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

AUTHENTICATION_BACKENDS = (
    'apps.authentication.backends.KeycloakOIDCAuthenticationBackend',
    'django.contrib.auth.backends.ModelBackend',
)

# --- Keycloak / OIDC ---
KEYCLOAK_SERVER_URL = env('KEYCLOAK_SERVER_URL')
KEYCLOAK_REALM = env('KEYCLOAK_REALM')
KEYCLOAK_CLIENT_ID = env('KEYCLOAK_CLIENT_ID')
KEYCLOAK_CLIENT_SECRET = env('KEYCLOAK_CLIENT_SECRET')

# Configuración de OIDC consumiendo las variables base de Keycloak
OIDC_RP_CLIENT_ID = KEYCLOAK_CLIENT_ID
OIDC_RP_CLIENT_SECRET = KEYCLOAK_CLIENT_SECRET

_keycloak_realm_url = f'{KEYCLOAK_SERVER_URL}/realms/{KEYCLOAK_REALM}'

OIDC_OP_AUTHORIZATION_ENDPOINT = f'{_keycloak_realm_url}/protocol/openid-connect/auth'
OIDC_OP_TOKEN_ENDPOINT = f'{_keycloak_realm_url}/protocol/openid-connect/token'
OIDC_OP_USER_ENDPOINT = f'{_keycloak_realm_url}/protocol/openid-connect/userinfo'
OIDC_OP_JWKS_ENDPOINT = f'{_keycloak_realm_url}/protocol/openid-connect/certs'
OIDC_OP_LOGOUT_ENDPOINT = f'{_keycloak_realm_url}/protocol/openid-connect/logout'

OIDC_RP_SIGN_ALGO = 'RS256'
OIDC_RP_SCOPES = 'openid email profile roles'
# Guarda el id_token en la sesión para mandarlo como id_token_hint al
# cerrar sesión: así Keycloak termina también su sesión SSO.
OIDC_STORE_ID_TOKEN = True
# Sin la opción "Mantener la sesión iniciada", la sesión de Django termina al
# cerrar el navegador, igual que la de Keycloak.
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# A dónde redirige después de login/logout exitoso
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

# Parámetros del cálculo previo de operaciones cambiarias.
COMISION_OPERACION_PORCENTAJE = Decimal('1.00')
CALCULO_OPERACION_VIGENCIA_SEGUNDOS = 300

# Tiempo que una transacción recién creada (estado "Pendiente de
# confirmación") espera a que el cliente la confirme o cancele en la
# pantalla de confirmación, antes de considerarse "Vencida".
CONFIRMACION_OPERACION_VIGENCIA_SEGUNDOS = 300