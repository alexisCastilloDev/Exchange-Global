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
    'apps.caja',
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
                'apps.divisas.context_processors.notificaciones_context',
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

# --- Stripe (pago con tarjeta) ---
# Con default='' el proyecto sigue arrancando en desarrollo sin tener
# cuenta de Stripe configurada; sin una clave real, iniciar un pago con
# tarjeta falla igual que un corte de comunicación real (ver
# apps.divisas.pagos_stripe), así que no hace falta un valor de mentira.
STRIPE_SECRET_KEY = env('STRIPE_SECRET_KEY', default='')
STRIPE_WEBHOOK_SECRET = env('STRIPE_WEBHOOK_SECRET', default='')

# --- SIPAP (pago por transferencia bancaria y billeteras digitales) ---
# SIPAP es el sistema de pagos interbancario del Banco Central del
# Paraguay: no tiene un sandbox público al que este proyecto académico
# pueda conectarse, así que lo simula "sipap-sim" (ver sipap_sim/), un
# proyecto Django independiente que corre en su propio contenedor y con
# su propia base. Global Exchange le habla solo por HTTP, sin compartir
# código: estas tres variables son todo lo que necesita conocer de él.
SIPAP_BASE_URL = env('SIPAP_BASE_URL', default='')
SIPAP_API_KEY = env('SIPAP_API_KEY', default='')
SIPAP_WEBHOOK_SECRET = env('SIPAP_WEBHOOK_SECRET', default='')
# Tiempo que el cliente tiene para completar la transferencia antes de
# que la solicitud se considere "Vencida" (criterio 5).
SIPAP_SOLICITUD_VIGENCIA_SEGUNDOS = 3600

# Parámetros del cálculo previo de operaciones cambiarias.
COMISION_OPERACION_PORCENTAJE = Decimal('1.00')
CALCULO_OPERACION_VIGENCIA_SEGUNDOS = 300

# Tiempo que una transacción recién creada (estado "Pendiente de
# confirmación") espera a que el cliente la confirme o cancele en la
# pantalla de confirmación, antes de considerarse "Vencida".
CONFIRMACION_OPERACION_VIGENCIA_SEGUNDOS = 300

# Tiempo que la tasa fijada al confirmar una operación sigue vigente
# para pagarla (ver CalculoOperacion.tasa_vencida). 1800s (30 min) es el
# mínimo real que admite "expires_at" en una sesión de Stripe Checkout
# (verificado contra https://docs.stripe.com/api/checkout/sessions/create),
# así que es el valor por defecto elegido para que la sesión de Stripe y
# la tasa fijada venzan juntas en el caso por defecto.
PAGO_OPERACION_VIGENCIA_SEGUNDOS = 1800

# --- Factura Segura (emisión de documentos electrónicos ante SIFEN) ---
# Factura Segura es un ESI (External Systems Interoperation) registrado
# ante el SIFEN del Paraguay: a diferencia de SIPAP, sí tiene un entorno
# de test real (ver apps.divisas.factura_electronica), pero con rangos
# de numeración de documento fijos y limitados por la habilitación del
# emisor, así que nunca se simula localmente — se usa directamente.
# FACTURASEGURA_AUTH_TOKEN se genera una sola vez (POST /login, ver
# manual) y queda vigente hasta que cambie la contraseña del usuario
# ESI: no hace falta volver a loguearse en cada llamada.
FACTURASEGURA_BASE_URL = env(
    'FACTURASEGURA_BASE_URL', default='https://apitest.facturasegura.com.py/misife00/v1/esi',
)
FACTURASEGURA_AUTH_TOKEN = env('FACTURASEGURA_AUTH_TOKEN', default='')

# Datos fijos del emisor habilitado (los mismos para cualquier documento
# que se emita): RUC, timbrado, domicilio y actividades económicas tal
# como quedaron registrados en Factura Segura. Configurables por entorno
# (cada integrante del equipo tiene su propia habilitación de prueba),
# nunca hardcodeados en apps.divisas.factura_electronica.
FACTURASEGURA_EMISOR_RUC = env('FACTURASEGURA_EMISOR_RUC', default='')
FACTURASEGURA_EMISOR_DV = env('FACTURASEGURA_EMISOR_DV', default='')
FACTURASEGURA_EMISOR_TIPO_CONTRIBUYENTE = env('FACTURASEGURA_EMISOR_TIPO_CONTRIBUYENTE', default='1')
FACTURASEGURA_EMISOR_NUM_TIMBRADO = env('FACTURASEGURA_EMISOR_NUM_TIMBRADO', default='')
FACTURASEGURA_EMISOR_FECHA_INICIO_TIMBRADO = env('FACTURASEGURA_EMISOR_FECHA_INICIO_TIMBRADO', default='')
FACTURASEGURA_EMISOR_NOMBRE = env('FACTURASEGURA_EMISOR_NOMBRE', default='Global Exchange S.A.')
FACTURASEGURA_EMISOR_DIRECCION = env('FACTURASEGURA_EMISOR_DIRECCION', default='')
FACTURASEGURA_EMISOR_NUMERO_CASA = env('FACTURASEGURA_EMISOR_NUMERO_CASA', default='0')
FACTURASEGURA_EMISOR_COD_DEPARTAMENTO = env('FACTURASEGURA_EMISOR_COD_DEPARTAMENTO', default='1')
FACTURASEGURA_EMISOR_DESC_DEPARTAMENTO = env('FACTURASEGURA_EMISOR_DESC_DEPARTAMENTO', default='CAPITAL')
FACTURASEGURA_EMISOR_COD_CIUDAD = env('FACTURASEGURA_EMISOR_COD_CIUDAD', default='1')
FACTURASEGURA_EMISOR_DESC_CIUDAD = env('FACTURASEGURA_EMISOR_DESC_CIUDAD', default='ASUNCION (DISTRITO)')
FACTURASEGURA_EMISOR_TELEFONO = env('FACTURASEGURA_EMISOR_TELEFONO', default='')
FACTURASEGURA_EMISOR_EMAIL = env('FACTURASEGURA_EMISOR_EMAIL', default='')
# Lista de {"cActEco", "dDesActEco"} tal como la exige el JSON de SIFEN.
# No hay forma razonable de que esto venga de una variable de entorno
# plana, así que queda fija acá (no en el módulo, para que un fork de
# este proyecto con otra habilitación solo tenga que tocar settings).
FACTURASEGURA_EMISOR_ACTIVIDADES_ECONOMICAS = [
    {'cActEco': '62010', 'dDesActEco': 'Actividades de programación informática'},
    {'cActEco': '74909', 'dDesActEco': 'Otras actividades profesionales, científicas y técnicas n.c.p.'},
]
# Establecimiento y punto de expedición habilitados para este ESI.
FACTURASEGURA_ESTABLECIMIENTO = env('FACTURASEGURA_ESTABLECIMIENTO', default='001')
FACTURASEGURA_PUNTO_EXPEDICION = env('FACTURASEGURA_PUNTO_EXPEDICION', default='003')