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

if 'test' in sys.argv or 'pytest' in sys.modules:
    # mozilla_django_oidc.middleware.SessionRefresh (ver MIDDLEWARE en
    # base.py) solo deja pasar una request autenticada si la sesión tiene
    # 'oidc_id_token_expiration' vigente — un valor que solo pone un login
    # real contra Keycloak. client.force_login()/client.login() (los que
    # usan los tests) nunca lo setean, así que sin esto cualquier test que
    # haga un GET después de loguearse quedaría redirigido a Keycloak en
    # vez de recibir la respuesta esperada. 'pytest' in sys.modules cubre
    # también a pytest (tests/test_auth.py y compañía), que 'test' in
    # sys.argv no detecta.
    MIDDLEWARE = [m for m in MIDDLEWARE if m != 'mozilla_django_oidc.middleware.SessionRefresh']

    # PBKDF2 (el hasher por defecto) es lento a propósito, incluso para los
    # tests: con cientos de tests que crean usuarios (User.objects.create_user),
    # ese costo se repite una enormidad de veces y es puro tiempo de
    # ejecución, sin ningún valor de seguridad real (nunca se expone nada
    # de esta base de test). MD5 es inseguro, pero acá no importa.
    PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

    # apps.divisas.views._verificar_saldo_casa_de_cambio y
    # apps.divisas.entrega.realizar_entrega consultan el saldo real a
    # sipap-sim (apps.divisas.casa_de_cambio.consultar_saldo_casa_de_cambio)
    # antes de confirmar o entregar. Ningún test de confirmación/entrega
    # mockea esa llamada puntual (solo entrega.requests.post, el envío de
    # la transferencia en sí); sin esto, apuntarían al SIPAP_BASE_URL real
    # del .env, que durante una corrida local puede incluso estar
    # arriba (ver sipap_sim/, "runserver 8001"), mezclando datos de la
    # base de desarrollo con los tests. Un puerto cerrado hace que la
    # consulta falle rápido (SipapComunicacionError) y caiga al espejo
    # local (CuentaPropia), el mismo valor que ya usaban estas dos
    # funciones antes de este chequeo en vivo — ningún test existente
    # cambia de comportamiento.
    SIPAP_BASE_URL = 'http://127.0.0.1:1'