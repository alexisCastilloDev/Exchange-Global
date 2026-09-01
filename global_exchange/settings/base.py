"""
Configuración base compartida entre dev y prod.
"""
from pathlib import Path
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
    
    'apps.authentication', 
    'apps.clientes',
    'apps.users',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
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

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

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

OIDC_RP_SIGN_ALGO = 'RS256'
OIDC_RP_SCOPES = 'openid email profile roles'

# A dónde redirige después de login/logout exitoso
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'