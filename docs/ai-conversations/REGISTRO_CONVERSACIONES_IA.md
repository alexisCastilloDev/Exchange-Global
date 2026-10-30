# Registro consolidado de conversaciones con IA — Global Exchange

Este documento reúne, en un único archivo y ordenadas cronológicamente, todas las
conversaciones con asistentes de IA documentadas durante el desarrollo de Global
Exchange. Cada sesión de trabajo es una **Sesión** independiente (numerada e
identificada por fecha y HU); dentro de algunas sesiones, el propio registro
original ya dividía el trabajo en **Bloques** internos, que se conservan tal cual.

Los exports completos sin resumir (`.json` de Copilot y los `.md` de volcado
íntegro de Claude Code) no están incluidos en este archivo por su tamaño — se
agruparon en [`exports-completos/`](exports-completos/). El archivo `ia-CONVERSATION.TXT`
original (enlaces a conversaciones completas en claude.ai) se resume en el
[bloque de enlaces](#enlaces-externos-conversaciones-completas) al final de este documento.

## Índice de sesiones

1. [Sesión 1 — 28/08/2026 — GE-3 — Login SSO con Keycloak](#sesión-1--28082026--ge-3--implementación-de-login-sso-con-keycloak)
2. [Sesión 2 — 30/08/2026 — GE-7 — Roles, permisos y control de acceso](#sesión-2--30082026--ge-7--gestión-de-roles-permisos-y-control-de-acceso)
3. [Sesión 3 — 15/09/2026 — GE-72 (Copilot) — Registro consolidado del día](#sesión-3--15092026--ge-72-copilot--registro-consolidado-de-trabajo-con-ia)
4. [Sesión 4 — 15/09/2026 — GE-72 (Claude) — Cálculo del importe de la operación](#sesión-4--15092026--ge-72-claude--cálculo-del-importe-de-la-operación-triangulación-comisiones-y-ui)
5. [Sesión 5 — 17/09/2026 — GE-30 — Compra de divisas](#sesión-5--17092026--ge-30--hito-5sprint-3-diagnóstico-y-compra-de-divisas)
6. [Sesión 6 — 21/09/2026 — GE-31 — Venta de divisas](#sesión-6--21092026--ge-31--sprint-3-venta-de-divisas-y-corrección-del-cambio-de-divisas)
7. [Sesión 7 — 22/09/2026 — GE-73 — Confirmación de operación cambiaria](#sesión-7--22092026--ge-73--sprint-3-confirmación-de-operación-cambiaria)
8. [Sesión 8 — 24/09/2026 — GE-37 — Consultar el historial de transacciones](#sesión-8--24092026--ge-37--consultar-el-historial-de-transacciones)
9. [Sesión 9 — 08/10/2026 — GE-25 — Asociación de pagos a transacciones](#sesión-9--08102026--ge-25--asociación-de-pagos-a-transacciones)
10. [Sesión 10 — 09/10/2026 — Apertura de Caja](#sesión-10--09102026--apertura-de-caja)
11. [Sesión 11 — 09/10/2026 — GE-22 — Pago con tarjeta vía Stripe](#sesión-11--09102026--ge-22--pago-con-tarjeta-vía-stripe)
12. [Sesión 12 — 11/10/2026 — Pago por transferencia bancaria vía SIPAP](#sesión-12--11102026--pago-por-transferencia-bancaria-vía-sipap)
13. [Sesión 13 — 11/10/2026 — sipap-sim y billeteras digitales](#sesión-13--11102026--sipap-sim-y-billeteras-digitales)
14. [Sesión 14 — 11/10/2026 — GE-19 — Validación real de cuentas en "Métodos de pago"](#sesión-14--11102026--validación-real-de-cuentas-en-métodos-de-pago-ge-19)
15. [Sesión 15 — 12/10/2026 — sipap-sim reconoce la cuenta del método de pago elegido](#sesión-15--12102026--sipap-sim-reconoce-la-cuenta-del-método-de-pago-elegido)
16. [Sesión 16 — 12/10/2026 — sipap-sim deja de pedir el monto a transferir](#sesión-16--12102026--sipap-sim-deja-de-pedir-el-monto-a-transferir)
17. [Sesión 17 — 11/10/2026 — Gestión de operaciones en ventanilla](#sesión-17--11102026--gestión-de-operaciones-en-ventanilla)
18. [Sesión 18 — 11/10/2026 — Arqueo de Caja](#sesión-18--11102026--arqueo-de-caja)
19. [Sesión 19 — 12/10/2026 — GE-54 — Movimientos extraordinarios de Caja](#sesión-19--12102026--ge-54--gestión-de-movimientos-extraordinarios-de-caja)
20. [Sesión 20 — 12/10/2026 — GE-56 — Cierre de Caja](#sesión-20--12102026--ge-56--cierre-de-caja)
21. [Sesión 21 — 26/10/2026 — GE-23 — Acreditación de fondos](#sesión-21--26102026--ge-23--acreditación-de-fondos)
22. [Sesión 22 — 26/10/2026 — GE-19 — Movimientos y saldo de los métodos de pago](#sesión-22--26102026--ge-19--movimientos-y-saldo-de-los-métodos-de-pago)
23. [Sesión 23 — 27/10/2026 — GE-24 — Retiro de fondos](#sesión-23--27102026--ge-24--retiro-de-fondos)
23. [Enlaces externos (conversaciones completas)](#enlaces-externos-conversaciones-completas)

---

## Sesión 1 — 28/08/2026 — GE-3 — Implementación de Login SSO con Keycloak

**Herramienta:** Claude (Anthropic)
**HU relacionada:** GE-3 — Inicio de sesión mediante Keycloak SSO (Epic 1: Autenticación, Autorización y Gestión de Usuarios)
**Participantes:** Rodrigo Mereles. Desarrollador del equipo Global Exchange

### Contexto

Historia de usuario a implementar:

> **Como** usuario registrado
> **quiero** iniciar sesión mediante Red Hat Keycloak
> **para** acceder de forma segura a las funcionalidades del sistema.

**Criterios de aceptación:**
1. Dado que soy un usuario registrado, cuando ingreso mis credenciales correctas mediante Keycloak, entonces el sistema me autentica y me redirige a la pantalla principal según mi rol.
2. Dado que ingreso credenciales incorrectas, cuando intento iniciar sesión, entonces el sistema muestra un mensaje de error sin revelar si el dato incorrecto fue el usuario o la contraseña.
3. Dado que Keycloak me devuelve un token de acceso, cuando intento acceder a una funcionalidad protegida, entonces el sistema valida la firma y vigencia del token antes de permitir el acceso.
4. Dado que mi token expiró o fue manipulado, cuando intento acceder a una funcionalidad protegida, entonces el sistema rechaza la solicitud y me redirige al login.
5. Dado que cierro sesión, cuando confirmo el logout, entonces el sistema invalida mi sesión y me redirige a la pantalla de login.

### Referencias

- Playlist de YouTube usada como base para la configuración inicial de Keycloak: https://www.youtube.com/playlist?list=PLRFOqDrY-6nuCMk2gORw-jSKtcnJX7Yam

### Desarrollo

Esta conversación cubrió la implementación de la HU **de principio a fin**, partiendo de cero: no había ningún código de autenticación previo. Se instaló `mozilla-django-oidc`, se creó desde cero la app `apps/authentication` con su backend y vistas personalizadas, se armó el template `home.html`, y se configuraron las URLs correspondientes — todo dentro de este chat.

**Resultado de la implementación inicial:** de los 5 criterios de aceptación, 3 quedaron cubiertos en la primera vuelta (2 — error genérico de Keycloak, y 5 — logout). Faltaban:
- **Criterio 1**: la redirección post-login no dependía del rol del usuario, siempre iba al mismo home.
- **Criterios 3 y 4**: no existía ninguna vista protegida más allá del home para demostrar que el acceso realmente se validaba contra el token.

### Código implementado

#### `apps/authentication/backends.py`

Backend de autenticación que sincroniza los datos del usuario (nombre, apellido, rol) desde las claims que devuelve Keycloak:

```python
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

class KeycloakOIDCAuthenticationBackend(OIDCAuthenticationBackend):
    def filter_users_by_claims(self, claims):
        email = claims.get('email')
        if not email:
            return self.UserModel.objects.none()
        return self.UserModel.objects.filter(email__iexact=email)

    def create_user(self, claims):
        user = super().create_user(claims)
        self.update_user_claims(user, claims)
        return user

    def update_user(self, user, claims):
        self.update_user_claims(user, claims)
        return user

    def update_user_claims(self, user, claims):
        user.first_name = claims.get('given_name', '')
        user.last_name = claims.get('family_name', '')
        # Extraer roles del realm de Keycloak (si vienen en las claims)
        realm_access = claims.get('realm_access', {})
        roles = realm_access.get('roles', [])

        # Guardar roles en un atributo o sincronizar superusuario/staff si corresponde
        if 'admin' in roles:
            user.is_staff = True
            user.is_superuser = True
        else:
            user.is_staff = False
            user.is_superuser = False

        user.save()
```

#### `apps/authentication/views.py`

Vista de logout personalizada (invalida sesión local y redirige al logout de Keycloak) y vista de callback personalizada (redirige según el rol del usuario tras un login exitoso — resuelve el criterio 1):

```python
from urllib.parse import urlencode
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from mozilla_django_oidc.views import OIDCLogoutView, OIDCAuthenticationCallbackView


class CustomOIDCLogoutView(OIDCLogoutView):
    def get(self, request):
        return self.post(request)

    def post(self, request):
        # Extraer el id_token_id guardado por mozilla-django-oidc en la sesión
        id_token = request.session.get('oidc_id_token')

        # Ejecuta el logout de Django (destruye la sesión local)
        super().post(request)

        # Construye el endpoint de logout de Keycloak
        keycloak_logout_url = f"{settings.OIDC_OP_AUTHORIZATION_ENDPOINT.replace('/auth', '/logout')}"

        params = {
            'client_id': settings.OIDC_RP_CLIENT_ID,
            'post_logout_redirect_uri': 'http://localhost:8000/',
        }

        if id_token:
            params['id_token_hint'] = id_token

        return redirect(f"{keycloak_logout_url}?{urlencode(params)}")


class CustomOIDCCallbackView(OIDCAuthenticationCallbackView):
    """
    Sobreescribe el callback de login para redirigir según el rol
    del usuario autenticado.
    """
    def login_success(self):
        response = super().login_success()
        user = self.request.user
        if user.is_staff:
            return redirect(reverse('panel_admin'))
        return redirect(reverse('home'))
```

#### `global_exchange/views.py`

Vista pública (`home`) y dos vistas protegidas con `@login_required` — una genérica para demostrar los criterios 3 y 4, y una específica para usuarios con rol admin:

```python
from django.shortcuts import render
from django.contrib.auth.decorators import login_required


def home(request):
    return render(request, 'home.html')


@login_required
def panel_protegido(request):
    """
    Vista de prueba para demostrar que el acceso está protegido
    por sesión/token válido (HU 1.2, criterios 3 y 4).
    """
    return render(request, 'panel.html')


@login_required
def panel_admin(request):
    """
    Vista a la que se redirige a los usuarios con rol admin
    tras el login (HU 1.2, criterio 1).
    """
    return render(request, 'panel_admin.html')
```

#### `global_exchange/urls.py`

```python
from django.contrib import admin
from django.urls import path, include
from global_exchange.views import home, panel_protegido, panel_admin
from apps.authentication.views import CustomOIDCLogoutView, CustomOIDCCallbackView

urlpatterns = [
    path('', home, name='home'),
    path('panel/', panel_protegido, name='panel_protegido'),
    path('panel-admin/', panel_admin, name='panel_admin'),
    path('admin/', admin.site.urls),
    path('oidc/logout/', CustomOIDCLogoutView.as_view(), name='oidc_logout'),
    path('oidc/callback/', CustomOIDCCallbackView.as_view(), name='oidc_authentication_callback'),
    path('oidc/', include('mozilla_django_oidc.urls')),
]
```

> **Nota de orden:** la ruta custom de callback debe declararse *antes* del `include('mozilla_django_oidc.urls')`, ya que Django resuelve URLs entrantes por la primera coincidencia en la lista.

#### `global_exchange/settings/base.py` (fragmento agregado)

```python
LOGIN_URL = 'oidc_authentication_init'
```

#### `templates/panel.html` y `templates/panel_admin.html`

Templates mínimos, cada uno mostrando el nombre del usuario autenticado y un link de vuelta al home.

#### `tests/test_auth.py`

```python
import pytest
from django.urls import reverse


def test_home_page_unauthenticated(client):
    """CA1 / CA5: El usuario no autenticado ve la opción de login."""
    response = client.get(reverse('home'))
    assert response.status_code == 200
    assert 'Iniciar Sesión con Keycloak SSO' in response.content.decode('utf-8')


def test_oidc_urls_resolved():
    """CA1 / CA5: Las rutas críticas de autenticación y logout están disponibles."""
    assert reverse('oidc_authentication_init') == '/oidc/authenticate/'
    assert reverse('oidc_logout') == '/oidc/logout/'


def test_custom_logout_redirects_to_keycloak(client):
    """CA5: El logout invalida y redirige a Keycloak."""
    response = client.get(reverse('oidc_logout'))
    assert response.status_code == 302
    assert 'post_logout_redirect_uri' in response.url


@pytest.mark.django_db
def test_protected_route_redirects_unauthenticated_user(client):
    """CA3 / CA4: Si no hay token o sesión válida, redirige al login."""
    response = client.get(reverse('panel_protegido'))
    assert response.status_code == 302
```

### Problemas encontrados y resueltos durante la implementación

#### 1. La redirección por rol no funcionaba — siempre iba al home

**Síntoma:** un usuario con el rol `admin` asignado en Keycloak, tras loguearse, terminaba en `home` en vez de `panel-admin`.

**Diagnóstico:** se agregaron prints temporales en `update_user_claims` para inspeccionar las claims recibidas desde Keycloak. Resultado:

```
>>> CLAIMS RECIBIDAS: {'sub': '...', 'email_verified': True, 'name': 'usuario prueba', ...}
>>> REALM_ACCESS: None
>>> ROLES ENCONTRADOS: []
```

La clave `realm_access` no llegaba en absoluto en las claims.

**Causa raíz:** `mozilla-django-oidc` obtiene las claims consultando el endpoint **userinfo** de Keycloak, no decodificando el token JWT directamente. Por defecto, aunque el rol viaje en el `access_token`, el endpoint `userinfo` no incluye los roles del realm salvo que se configure explícitamente un mapper para eso.

**Solución:** en Keycloak, dentro del Client (`global-exchange-django` → pestaña "Client scopes" → scope dedicado `global-exchange-django-dedicated`), se agregó un mapper de tipo **"User Realm Role"** con:
- Token Claim Name: `realm_access.roles`
- Multivalued: ON
- Add to ID token / access token / **userinfo**: los tres ON (el de `userinfo` es el que resolvía el problema puntual)

Tras esto, el login con un usuario con rol `admin` redirigió correctamente a `panel-admin`.

#### 2. `Page not found (404)` en `/accounts/login/?next=/panel/`

**Síntoma:** al entrar a `/panel/` sin sesión iniciada, Django devolvía un 404 en vez de redirigir a Keycloak.

**Causa raíz:** el decorador `@login_required` usa por defecto la URL `LOGIN_URL` de Django, que apunta a `/accounts/login/` — una ruta que nunca existió en este proyecto porque el login lo maneja Keycloak, no el sistema de auth nativo de Django.

**Solución:** se agregó en `base.py`:
```python
LOGIN_URL = 'oidc_authentication_init'
```

#### 3. Otros ajustes menores
- Se limpiaron los `print()` de diagnóstico antes del commit final.
- Se agregó `@pytest.mark.django_db` al test de la vista protegida.
- Se corrigió el orden de `urlpatterns` para que la vista de callback personalizada tuviera prioridad sobre la que trae `mozilla_django_oidc.urls` por defecto.

### Resultado final

Los 5 criterios de aceptación quedaron cubiertos y verificados manualmente (login con y sin rol admin, logout, acceso sin sesión, expiración de token bajando el "Access Token Lifespan" en Keycloak) y con tests automatizados:

```
collected 5 items
tests\test_auth.py ....                                                     [ 80%]
tests\test_setup.py .                                                       [100%]
========================= 5 passed, 1 warning in 2.80s =========================
```

HU cerrada y mergeada a `develop` vía `git flow feature finish GE-3`.

---

## Sesión 2 — 30/08/2026 — GE-7 — Gestión de roles, permisos y control de acceso

**Herramienta:** Claude (Anthropic)
**HU relacionada:** GE-7 — Gestión de roles, permisos y control de acceso (Epic 1)
**Rama:** `feature/GE-7`
**Autor:** Rodrigo Mereles

### Contexto previo

GE-3 (Inicio de sesión mediante Keycloak SSO) ya estaba cerrada y demostrada con pytest. Con el backlog del equipo repartido, correspondía continuar con GE-7 mientras un compañero de equipo tomaba GE-6 (Gestión de usuarios), reutilizando como base el mismo `backends.py` que se termina de corregir en esta conversación.

### Criterios de aceptación de la HU

- Dado que soy administrador, cuando defino los permisos asociados a un rol, entonces el sistema los guarda y los aplica a todos los usuarios con ese rol.
- Dado que soy un usuario autenticado, cuando intento acceder a una funcionalidad no autorizada para mi rol, entonces el sistema deniega el acceso y muestra un mensaje correspondiente.
- Dado que un administrador modifica los permisos de un rol, cuando un usuario con ese rol vuelve a operar en el sistema, entonces los nuevos permisos se aplican sin que el usuario deba volver a registrarse.
- Dado que intento acceder directamente por URL a una funcionalidad restringida sin pasar por el menú, cuando el sistema valida mi rol, entonces igual se me deniega el acceso si no corresponde.

### Decisión de diseño

Se evaluó armar un sistema de roles/permisos propio desde cero, pero se optó por **reutilizar el sistema de permisos nativo de Django** (`django.contrib.auth.models.Group` y `Permission`), mapeando:

- **Rol de Keycloak** → **Django Group** (`admin`, `cliente`, y luego se sumaron `analista_cambiario`, `cajero`)
- **Funcionalidad protegida del sistema** → un `Permission` de Django, generado a partir de un modelo propio `RecursoProtegido`

La razón principal: `user.has_perm(...)` consulta la base de datos en cada request, sin ningún tipo de caché en la sesión ni en el token JWT — eso resuelve de forma natural el criterio de aceptación más exigente de la HU ("los nuevos permisos se aplican sin que el usuario deba volver a registrarse").

### Bug encontrado y corregido #1 — `is_superuser` anulaba el propósito de la HU

El `backends.py` existente (heredado de GE-3) marcaba a los usuarios con rol `admin` como `is_superuser = True`. En Django, `is_superuser` hace que **todos** los chequeos de `has_perm()` devuelvan `True` automáticamente, sin importar qué permisos tenga asignado el usuario o su grupo. De mantenerse así, GE-7 no tendría ningún efecto real sobre los usuarios admin — el criterio de "definir permisos por rol" quedaría roto de raíz para ese rol en particular.

**Corrección:** se eliminó `is_superuser = True` del backend, se mantuvo `is_staff` solo con su significado real en Django (acceso al panel `/admin/`), y se agregó sincronización activa hacia `Group`:

```python
def update_user_claims(self, user, claims):
    user.first_name = claims.get('given_name', '')
    user.last_name = claims.get('family_name', '')

    realm_access = claims.get('realm_access', {})
    roles_keycloak = set(realm_access.get('roles', []))
    roles_negocio = roles_keycloak & ROLES_DE_NEGOCIO

    user.is_staff = 'admin' in roles_negocio
    user.is_superuser = False  # nunca superuser: los permisos deben pasar por Groups
    user.save()

    self._sincronizar_grupos(user, roles_negocio)

def _sincronizar_grupos(self, user, roles_negocio):
    grupos_actuales = set(user.groups.values_list('name', flat=True))
    if grupos_actuales == roles_negocio:
        return
    for nombre_rol in roles_negocio - grupos_actuales:
        grupo, _ = Group.objects.get_or_create(name=nombre_rol)
        user.groups.add(grupo)
    for nombre_rol in grupos_actuales - roles_negocio:
        grupo = Group.objects.filter(name=nombre_rol).first()
        if grupo:
            user.groups.remove(grupo)
```

Este fix también resultó necesario para que el chequeo `user.groups.filter(name='admin').exists()` que el compañero ya había usado en el código de GE-6 funcionara correctamente — sin `Groups` sincronizados, esa condición nunca era verdadera.

### Bug encontrado y corregido #2 — permisos por modelo, no por instancia

Primer intento de `RecursoProtegido`:
```python
class Meta:
    permissions = [('acceder', 'Puede acceder a este recurso')]
```
Django genera permisos **por modelo**, no por fila/instancia. Con esta definición, **todos** los `RecursoProtegido` (panel_admin, gestion_roles, etc.) hubieran compartido el mismo único permiso `acceder`, imposibilitando dar/quitar acceso a cada funcionalidad de forma independiente.

**Corrección:** generar un `Permission` distinto por cada instancia, dinámicamente en `save()`:

```python
class RecursoProtegido(models.Model):
    codigo = models.SlugField(max_length=50, unique=True)
    nombre = models.CharField(max_length=100)

    def save(self, *args, **kwargs):
        es_nuevo = self._state.adding
        super().save(*args, **kwargs)
        if es_nuevo:
            content_type = ContentType.objects.get_for_model(RecursoProtegido)
            Permission.objects.get_or_create(
                codename=f'acceder_{self.codigo}',
                content_type=content_type,
                defaults={'name': f'Puede acceder a {self.nombre}'},
            )

    def __str__(self):
        return self.nombre
```

### Decorador de autorización

```python
def requiere_permiso(codigo_recurso):
    permiso_completo = f'authentication.acceder_{codigo_recurso}'

    def decorador(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.has_perm(permiso_completo):
                messages.error(request, 'No tenés permiso para acceder a esta funcionalidad.')
                return redirect('home')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorador
```

Aplicado directamente sobre las vistas (`panel_admin`, `gestion_roles`) en vez de solo ocultar el link del menú — así cubre también el criterio de "acceso directo por URL sin pasar por el menú".

### Problema de reproducibilidad y solución — data migration

Los primeros `RecursoProtegido` y la asignación de permisos al grupo `admin` se cargaron manualmente desde `python manage.py shell`. Esto generó una duda válida del equipo: **¿ese estado se comparte con el resto del equipo al hacer `git pull`?** No — el shell solo modifica la base de datos local de quien lo corre. Para evitar que cada integrante tuviera que repetir esos mismos comandos a mano, se migró esa carga a una **data migration**:

```python
# apps/authentication/migrations/0002_cargar_recursos_iniciales.py
RECURSOS_INICIALES = [
    ('panel_admin', 'Panel de administración'),
    ('gestion_roles', 'Gestión de roles'),
]

def cargar_recursos(apps, schema_editor):
    RecursoProtegido = apps.get_model('authentication', 'RecursoProtegido')
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')

    content_type = ContentType.objects.get_for_model(RecursoProtegido)
    grupo_admin, _ = Group.objects.get_or_create(name='admin')

    for codigo, nombre in RECURSOS_INICIALES:
        recurso, _ = RecursoProtegido.objects.get_or_create(codigo=codigo, defaults={'nombre': nombre})
        permiso, _ = Permission.objects.get_or_create(
            codename=f'acceder_{codigo}', content_type=content_type,
            defaults={'name': f'Puede acceder a {nombre}'},
        )
        grupo_admin.permissions.add(permiso)
```

Con esto, cualquier integrante que clone el repo y corra `python manage.py migrate` obtiene automáticamente el mismo estado base, sin pasos manuales.

**Nota técnica registrada:** dentro de una migración, `apps.get_model(...)` devuelve una versión "histórica" del modelo que **no ejecuta** el `save()` custom — por eso el `Permission` se crea explícitamente en la función de la migración, en vez de depender del `save()` de `RecursoProtegido`.

### Vista de gestión de roles

```python
@requiere_permiso('gestion_roles')
def gestion_roles(request):
    grupos = Group.objects.all()
    recursos = RecursoProtegido.objects.all()

    if request.method == 'POST':
        grupo = Group.objects.get(id=request.POST.get('grupo_id'))
        codigos_marcados = request.POST.getlist('recursos')
        grupo.permissions.clear()
        for recurso in recursos:
            if recurso.codigo in codigos_marcados:
                permiso = Permission.objects.get(
                    codename=f'acceder_{recurso.codigo}',
                    content_type__app_label='authentication',
                )
                grupo.permissions.add(permiso)
        messages.success(request, f'Permisos de "{grupo.name}" actualizados.')
        return redirect('gestion_roles')

    codenames_por_recurso = {r.codigo: f'acceder_{r.codigo}' for r in recursos}
    for grupo in grupos:
        codenames_del_grupo = set(grupo.permissions.values_list('codename', flat=True))
        grupo.permisos_codigos = [
            codigo for codigo, codename in codenames_por_recurso.items()
            if codename in codenames_del_grupo
        ]

    return render(request, 'gestion_roles.html', {'grupos': grupos, 'recursos': recursos})
```

### Template `templates/gestion_roles.html`

Formulario por grupo con checkboxes por cada `RecursoProtegido`, reutilizando el mismo estilo plano (sin layout base) que ya tenían `home.html`, `panel.html` y `panel_admin.html` del proyecto.

### Verificación manual

Se probó con el usuario admin real (autenticado contra el Keycloak centralizado del equipo):
- El panel `/roles/` renderizó correctamente el grupo `admin` con los dos permisos ya tildados (por la data migration).
- Al destildar "Gestión de roles" y guardar, el propio admin perdió el acceso a `/roles/` de inmediato, sin haberse deslogueado — confirmando en la práctica el criterio de "aplica sin volver a registrarse".
- Se identificó una limitación práctica para probar el escenario con dos roles distintos en simultáneo: el navegador comparte una sola sesión por pestaña/ventana normal. Se resolvió para pruebas futuras usando ventanas de incógnito o navegadores distintos para simular dos usuarios logueados al mismo tiempo.

### Tests automatizados — `tests/test_roles.py`

Se decidió un archivo separado de `test_auth.py` (GE-3), ya que corresponden a HU distintas con criterios de aceptación propios. Los tests usan `client.force_login()` para aislar la lógica de autorización del flujo OIDC real (ya cubierto en los tests de GE-3).

Cobertura de los 4 criterios de aceptación:
```python
def test_admin_asigna_permiso_a_grupo_y_aplica_a_todos_sus_miembros(...): ...
def test_usuario_sin_permiso_es_denegado(...): ...
def test_usuario_con_permiso_accede(...): ...
def test_cambio_de_permiso_aplica_sin_relogin(...): ...
def test_acceso_directo_por_url_se_bloquea_igual(...): ...
def test_usuario_no_autenticado_es_redirigido_al_login(...): ...
```

#### Troubleshooting — `UniqueViolation` en el fixture

Primer intento del fixture `recurso_panel_admin` usaba `.create()`, lo cual falló con `IntegrityError: llave duplicada` porque la base de datos de test **también corre la data migration** `0002_cargar_recursos_iniciales` al crearse — por lo tanto `panel_admin` ya existía de entrada. Se corrigió usando `get_or_create`:

```python
@pytest.fixture
def recurso_panel_admin(db):
    return RecursoProtegido.objects.get_or_create(
        codigo='panel_admin', defaults={'nombre': 'Panel de administración'}
    )[0]
```

#### Resultado final

```
tests/test_roles.py::test_admin_asigna_permiso_a_grupo_y_aplica_a_todos_sus_miembros PASSED
tests/test_roles.py::test_usuario_sin_permiso_es_denegado PASSED
tests/test_roles.py::test_usuario_con_permiso_accede PASSED
tests/test_roles.py::test_cambio_de_permiso_aplica_sin_relogin PASSED
tests/test_roles.py::test_acceso_directo_por_url_se_bloquea_igual PASSED
tests/test_roles.py::test_usuario_no_autenticado_es_redirigido_al_login PASSED

6 passed, 1 warning in 2.17s
```

### Pendiente / notas para el equipo

- Avisar al compañero a cargo de GE-6 que `backends.py` ya sincroniza roles a `Group` — su chequeo `user.groups.filter(name='admin')` pasa a funcionar correctamente con este fix.
- Warning detectado en la corrida de tests (`RemovedInDjango70Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 7.0`) — no bloquea nada hoy, pero queda anotado para revisar cuando se actualice la versión de Django del proyecto, dado que contradice el fix de `MAILERS` → `EMAIL_BACKEND` aplicado anteriormente en `base.py`.
- Falta correr la suite completa de tests (`pytest`, sin filtrar archivo) antes de abrir el Pull Request de `feature/GE-7` hacia `develop`.

---

## Sesión 3 — 15/09/2026 — GE-72 (Copilot) — Registro consolidado de trabajo con IA

**Herramienta:** GitHub Copilot
**Proyecto:** Global Exchange

Este archivo consolida toda la documentación de trabajo realizada durante el 15/09/2026.

### 1. Normalización de docstrings

Se revisó todo el código Python del proyecto mediante AST y se agregaron o corrigieron docstrings en español para módulos, clases y funciones. Se incluyeron aplicaciones, modelos, vistas, formularios, servicios, migraciones, scripts y pruebas.

La validación final confirmó que todos los archivos Python tienen docstrings y la suite de pruebas pasó correctamente.

### 2. Documentación con Sphinx

Se corrigió la configuración de Sphinx para que la documentación se lea y navegue correctamente:

- Se habilitó `sphinx_rtd_theme`.
- Se agregó una portada más clara y una guía de arquitectura.
- Se configuró `autodoc` para mostrar tipos y firmas de forma legible.
- Se agregó `custom.css` para mejorar tipografía, tablas, admoniciones y código.
- Se corrigió la advertencia causada por la carpeta `_static` inexistente.
- La compilación estricta con `-W` terminó sin errores ni advertencias.

### 3. Base de datos y roles

La base activa utiliza PostgreSQL. Las tablas de negocio principales son:

- `auth_user`: representación local de usuarios.
- `clientes_cliente`: perfil comercial del cliente.
- `clientes_cliente_usuarios`: asociaciones muchos a muchos entre clientes y usuarios.
- `clientes_metodopago`: métodos de pago.
- `divisas_divisa`: catálogo de divisas.
- `divisas_cotizacion`: historial de tasas de compra y venta.
- `divisas_calculooperacion`: cálculos previos con comisión y vencimiento.
- `authentication_historialbaja`: auditoría de bajas lógicas.

También existen las tablas técnicas de Django para sesiones, migraciones, permisos, grupos, tipos de contenido y administración.

Keycloak es la fuente de verdad para roles. Django recibe las claims OIDC, filtra roles técnicos y guarda los roles de negocio en `request.session['keycloak_roles']`. Las vistas usan esa sesión mediante mixins y decoradores.

Los roles funcionales vigentes son:

- `admin`: administración general.
- `analista_cambiario`: cotizaciones y operación cambiaria operativa.
- `usuarios`: gestión de usuarios.
- `gestion_roles`: administración de roles en Keycloak.
- `cliente`: operaciones propias del cliente y métodos de pago.

Se eliminó el rol duplicado anterior mediante una migración idempotente, sin modificar usuarios, clientes ni asociaciones.

### 4. Cálculo de importes

Se implementó el flujo de compra y venta de divisas:

- Compra: usa la tasa de venta y suma la comisión.
- Venta: usa la tasa de compra y descuenta la comisión.
- La comisión actual es `1.00%` y queda configurable.
- Cada cálculo se guarda con tasa, comisión, monto final y vencimiento.
- La confirmación rechaza cálculos vencidos y obliga a recalcular.
- La divisa base es PYG; no se ofrece como opción seleccionable en compra/venta.

La interfaz incluye los accesos de Comprar divisas y Vender divisas, con un desglose ordenado de operación, monto, tasa, comisión e importe final, usando dos decimales.

### 5. Correcciones de interfaz y permisos

Se corrigió el menú lateral para que:

- "Tasas actuales" solo quede activo en su propia ruta.
- Comprar y Vender divisas solo sean visibles para usuarios con rol `cliente` y una asociación activa a un cliente.
- Administradores y analistas no vean esos accesos ni puedan usar sus URLs.
- Los clientes sigan viendo las tasas, pero sin fecha ni usuario de la última actualización.
- Administradores y analistas conserven la información de auditoría de tasas.

La restricción se aplica tanto en la interfaz como en las vistas y en la confirmación de la operación; ocultar enlaces no es la única protección.

### 6. Verificación final

- Suite completa: `104 passed, 0 failed`.
- Pruebas específicas de compra/venta, visibilidad y auditoría: `7 passed`.
- `manage.py check`: sin problemas.
- Migraciones sincronizadas.
- Documentación Sphinx compilada con `-W` sin advertencias.

### 7. Documentación de templates

Se documentaron los 25 templates Django con comentarios iniciales tipo docstring. Cada encabezado indica el propósito del template, su template padre, los bloques que expone y las variables que espera recibir desde la vista.

También se agregó `docs/source/templates.rst`, que incorpora esos encabezados mediante `literalinclude` y los organiza por páginas generales, clientes, bajas, divisas y parciales. De esta forma Sphinx muestra la documentación de templates junto con la referencia Python.

### 8. Ajustes visuales finales

Se corrigió el detalle del importe de compra y venta para separar claramente cada etiqueta de su valor mediante una cuadrícula responsive. En pantallas pequeñas los datos se apilan para evitar textos pegados o desbordados.

El selector de cliente ahora informa si cada perfil corresponde a una persona física o jurídica, además de mostrar su CI/RUC, segmento y estado.

---

## Sesión 4 — 15/09/2026 — GE-72 (Claude) — Cálculo del importe de la operación (triangulación, comisiones y UI)

**Herramienta:** Claude Code (Anthropic, modelo Sonnet 5)
**HU relacionada:** GE-72 — Cálculo del importe de la operación (Epic de operaciones cambiarias)
**Participantes:** Rodrigo Mereles, desarrollador del equipo Global Exchange

### Contexto

Historia de usuario a verificar e implementar:

> **Como** usuario cliente **quiero** conocer el importe resultante de una operación **para** saber
> cuánto debo pagar o cuánto recibiré antes de confirmarla.

**Criterios de aceptación:**
1. Al ingresar un monto y una divisa para comprar o vender y solicitar el cálculo, el sistema muestra el importe resultante usando la tasa vigente correspondiente y la comisión aplicable.
2. El resultado desglosa por separado: monto origen, tasa aplicada, comisión y monto final.
3. Si la divisa no tiene tasa vigente, el sistema muestra un error y no permite continuar.
4. Si pasa el tiempo definido sin confirmar, el cálculo se considera "vencido" y debe recalcularse.
5. **Triangulación**: para operaciones entre dos divisas que no sean guaraní, la conversión debe pasar por PYG (tasa de compra origen → PYG → tasa de venta destino), calculando la tasa cruzada implícita y aplicando una comisión dinámica configurable por administrador/analista.

La conversación se dividió en tres bloques de trabajo dentro de la misma sesión.

### Bloque 1 — Verificación inicial y triangulación

Se auditó el estado real del código (no lo que sugerían archivos `.pyc` huérfanos de un intento previo no comiteado) y se encontró:

- Criterios 1-4: **completamente implementados y testeados** para el caso divisa↔PYG (`CalculoOperacionView`, modelo `CalculoOperacion` con `esta_vencido`).
- Criterio 5: solo existía una vista de "simulación" (`SimulacionDivisasView`) con la fórmula de tasa cruzada **invertida** (usaba `tasa_venta` origen / `tasa_compra` destino, en vez de `tasa_compra` origen / `tasa_venta` destino), sin comisión, sin desglose completo y sin persistencia/vencimiento.

#### Implementación

- **Modelo nuevo** `CalculoTriangulacion` (mismo patrón que `CalculoOperacion`: UUID, `vence_en`, `esta_vencido`), con los 7 campos pedidos por el criterio 5: monto origen, tasa compra aplicada, tasa venta aplicada, tasa cruzada implícita, monto equivalente en PYG, comisión y monto final neto.
- **`_calcular_triangulacion()`** en `apps/divisas/views.py`:

  ```python
  def _calcular_triangulacion(monto, tasa_compra_origen, tasa_venta_destino, cliente=None):
      monto_equivalente_pyg = (monto * tasa_compra_origen).quantize(Decimal('0.01'), ROUND_HALF_UP)
      tasa_cruzada = (tasa_compra_origen / tasa_venta_destino).quantize(Decimal('0.000001'), ROUND_HALF_UP)
      bruto = ((monto * tasa_compra_origen) / tasa_venta_destino).quantize(Decimal('0.01'), ROUND_HALF_UP)
      porcentaje = ConfiguracionComision.porcentaje_para(cliente)
      comision = (bruto * porcentaje / Decimal('100')).quantize(Decimal('0.01'), ROUND_HALF_UP)
      monto_final = bruto - comision
      return monto_equivalente_pyg, tasa_cruzada, porcentaje, comision, monto_final
  ```

- Nueva vista `TriangulacionOperacionView` + `confirmar_triangulacion_view`, con el mismo patrón de bloqueo por cotización faltante y vencimiento que `CalculoOperacionView`.
- Se corrigió la fórmula invertida en `SimulacionDivisasView` de paso.
- Todo con `Decimal` + `ROUND_HALF_UP`, nunca `float`.

**Resultado:** 4 tests nuevos para triangulación, 108/108 tests pasando.

### Bloque 2 — Ajustes de interfaz

Pedido: pantallas de inicio completas por rol, ícono duplicado, placeholder de divisa, símbolo de divisa junto al monto, y simulador con 3 modos.

- `home.html`: se agregaron las tarjetas que faltaban por rol (Registrar cliente, Comprar/Vender/Cambiar divisas, Simulador, Métodos de pago), replicando las condiciones de visibilidad del sidebar en `base.html`.
- Ícono de "Cambiar entre divisas" cambiado de `bi-arrow-left-right` (duplicado con "Cambiar de cliente") a `bi-shuffle`.
- Placeholder `"Seleccionar divisa"` agregado a los selects de divisa en Triangulación y Simulación, para que nunca arranquen con la misma divisa preseleccionada en ambos campos.
- Widget `DivisaSelect` (subclase de `forms.Select`) que expone el símbolo de cada divisa como `data-simbolo` en cada `<option>`, más un JS mínimo sin dependencias en cada template que actualiza un badge junto al campo de monto según la divisa seleccionada.
- **Simulador de conversión rediseñado**: selector de tipo (Comprar / Vender / Cambiar) que reutiliza exactamente `_calcular_importe_operacion` y `_calcular_triangulacion` (con comisión incluida), mostrando el mismo desglose que las operaciones reales, pero sin persistir ni exigir confirmación.

**Aclaración de una decisión de diseño:** se preguntó explícitamente si el símbolo "₲" junto al campo de "Comprar divisas" implicaba invertir la semántica del monto (pasar de "cantidad de divisa extranjera" a "guaraníes a gastar"). La respuesta fue que era un error de redacción: el símbolo debía ser el de la divisa seleccionada en los tres flujos (compra, venta, cambio), sin tocar el cálculo ya implementado y testeado.

**Resultado:** 110/110 tests pasando.

### Bloque 3 — Comisión configurable, corrección de métodos de pago y documentación

#### Comisión por categoría y por cliente

- Modelo nuevo `ConfiguracionComision` (`apps/divisas/models.py`): un registro por segmento de cliente (Minorista / VIP / Corporativo), editable por `admin` y `analista_cambiario` desde `/divisas/comisiones/`.
- Campo opcional `Cliente.comision_personalizada`, visible en la ficha de edición de cliente (`ClienteForm`), para dar trato preferencial único sin afectar el resto del segmento.
- Resolución de prioridad centralizada en `ConfiguracionComision.porcentaje_para(cliente)`: comisión personalizada del cliente → comisión de su segmento → valor por defecto de `settings.COMISION_OPERACION_PORCENTAJE`.
- `_calcular_importe_operacion` y `_calcular_triangulacion` pasaron a recibir el cliente activo (`request.cliente_activo`) en vez de leer `settings` directamente.

#### Corrección: métodos de pago anclados al usuario, no al cliente

**Bug encontrado:** `MetodoPago.cliente` era en realidad un `ForeignKey` a `User` (a pesar del nombre del campo), no a `Cliente`. Esto significaba que un operador con varios clientes asociados veía siempre los mismos métodos de pago sin importar cuál tuviera seleccionado como activo — el propio middleware (`ClienteActivoMiddleware`) tenía un parche explícito ("se toma el más reciente como contexto operativo") para evitar bloquear el acceso, precisamente por esta limitación.

**Solución:**
- Se cambió el FK de `MetodoPago.cliente` a apuntar a `Cliente`.
- Migración en 3 pasos (`0013_cliente_comision_personalizada_and_more.py`) para no perder datos: campo temporal `cliente_nuevo` → `RunPython` que resuelve el `Cliente` real a partir del usuario histórico (por `user` o por la M2M `usuarios`) → se elimina el campo viejo → se renombra el nuevo.
- Se quitó el parche del middleware: ahora la gestión de métodos de pago sigue el mismo flujo de selección de cliente activo que el resto del sistema.
- Las vistas de métodos de pago (`create/update/delete/reveal/set_default`) pasaron de filtrar por `request.user` a filtrar por `request.cliente_activo`.

**Resultado:** cada cliente tiene sus propios métodos de pago; cambiar de cliente activo cambia los métodos visibles (verificado con un test nuevo dedicado).

#### Otros ajustes de esta vuelta

- Placeholder "Seleccionar divisa" agregado también al select único de Comprar/Vender (faltaba desde el bloque 2).
- `home.html`: el ticker de tasas para visitantes sin sesión iniciada dejó de mostrar valores de ejemplo hardcodeados y ahora lista las divisas activas con cotización vigente real del sistema.

### Verificación final

- Suite completa: pasando en su totalidad (compra/venta, triangulación, simulación, clientes, métodos de pago, comisiones, autenticación).
- `manage.py check`: sin problemas.
- Migraciones aplicadas y sincronizadas contra PostgreSQL de desarrollo, incluyendo el remapeo de datos existentes de métodos de pago.
- Documentación Sphinx actualizada (`guia.rst`, `templates.rst`) y recompilada.

---

## Sesión 5 — 17/09/2026 — GE-30 — Hito 5/Sprint 3: diagnóstico y "Compra de divisas"

**Herramienta:** Claude Code (Anthropic, modelo Sonnet 5)
**HU relacionada:** GE-30 — Compra de divisas
**Participantes:** Rodrigo Mereles, desarrollador del equipo Global Exchange

### Bloque 1: Implementación de "Compra de divisas" (GE-30)

Criterios de aceptación cubiertos:

1. Cliente activo + monto/divisa válidos → se calcula el importe (reutilizando la lógica ya implementada de `_calcular_importe_operacion`) y se crea la transacción en estado **"Pendiente de confirmación"**.
2. Monto inválido (negativo, cero, no numérico) → error de validación, sin crear la transacción.
3. Divisa inactiva o sin tasa vigente → rechazo con mensaje claro, sin crear la transacción.
4. La transacción creada registra tipo, **cliente activo**, divisa, monto y fecha de creación.

La mayor parte de la lógica de cálculo y validación ya existía de sesiones anteriores; lo que faltaba para cumplir la HU tal como está redactada:

- `CalculoOperacion` no tenía una referencia directa al `Cliente` activo (solo al `usuario`, el mismo defecto que ya se había corregido en `MetodoPago` en una sesión previa). Se agregó el campo `cliente` (FK a `Cliente`, `on_delete=PROTECT`).
- No existía un estado explícito de la transacción — el "pendiente de confirmación" era implícito (`confirmado_en is None`). Se agregó `estado` con choices `PENDIENTE_CONFIRMACION` / `CONFIRMADA`.

#### Migración con backfill

`apps/divisas/migrations/0006_calculooperacion_cliente_estado.py` agrega ambos campos y resuelve los datos ya existentes (13 registros en la base de desarrollo, 3 ya confirmados): el `cliente` se resuelve a partir del `usuario` (por titularidad directa o por asociación como operador, igual que la migración `0013` de `clientes` hizo para `MetodoPago`), y el `estado` se infiere de `confirmado_en`. Se verificó manualmente contra la base de desarrollo que el backfill asignó correctamente el cliente y el estado a los 13 registros preexistentes antes de dar la migración por buena.

#### Vistas

- `CalculoOperacionView.post()`: ahora exige `request.cliente_activo` (si no hay uno seleccionado, error y no crea nada) y persiste `cliente=cliente_activo`, `estado=ESTADO_PENDIENTE`.
- `confirmar_calculo_operacion_view`: al confirmar, además de `confirmado_en`, actualiza `estado=ESTADO_CONFIRMADA`.
- `templates/divisas/calculo_operacion.html`: el badge fijo "Tasa reservada" ahora muestra el estado real (`calculo.get_estado_display`).

#### Tests nuevos

`CompraDeDivisasTest` en `tests/test_operaciones.py`, uno por criterio de aceptación: creación en estado pendiente, monto negativo/cero/no numérico, divisa inactiva, divisa sin cotización, y verificación de que la transacción guarda tipo/cliente/divisa/monto/fecha.

### Bloque 2 — Bug visual: mensajes duplicados

El usuario reportó que, por ejemplo al confirmar un cálculo, el mensaje "El cálculo fue confirmado con la tasa vigente" aparecía dos veces. Causa: `templates/base.html` ya incluye `partials/mensajes.html` una sola vez para todo el contenido autenticado (`<main>`), pero `calculo_operacion.html`, `triangulacion.html` y `simulacion_divisas.html` volvían a incluirlo dentro de su propio bloque `content` — duplicando cualquier mensaje en esas tres pantallas. Se quitó el include redundante de los tres templates (`home.html` no tenía el problema: su include vive en `content_publico`, un bloque mutuamente excluyente con el `<main>` autenticado).

### Bloque 3 — Historial de transacciones para administración y análisis

Pedido de seguimiento: que los roles `admin` y `analista_cambiario` puedan ver las transacciones realizadas por los clientes (qué usuario operó en nombre de qué cliente), con tipo, estado, cliente activo, divisa, monto y fecha de creación.

- Nueva vista `HistorialTransaccionesView` (`ListView` sobre `CalculoOperacion`, paginada de a 20), con el mismo `test_func` que ya usan `HistorialCotizacionesView` y `ConfiguracionComisionListView` (`{'admin', 'analista_cambiario'}`), a diferencia de las vistas del cliente que solo muestran sus propias transacciones, esta lista todas las de todos los clientes.
- Template nuevo `templates/divisas/historial_transacciones.html`, tabla con columnas Fecha, Tipo, Estado, Usuario, Cliente, Divisa y Monto, con paginación siguiendo el mismo patrón visual que `panel_admin.html`.
- Ruta `divisas:historial_transacciones` (`/divisas/transacciones/`), enlace nuevo en el sidebar y en el inicio (reutilizando el flag `puede_configurar_comisiones`, que ya representa exactamente al mismo público admin/analista).
- 5 tests nuevos en `HistorialTransaccionesTest`: acceso permitido a admin y analista, acceso denegado (403) a rol cliente, verificación de que se muestran todos los campos pedidos, y que el historial no se limita a un único cliente.

**Bug propio introducido y corregido en el camino:** al agregar el nuevo `<li>` del menú dentro del bloque `{% if puede_configurar_comisiones %}` de `base.html`, quedó un `{% endif %}` duplicado que rompía el parseo de todo el template (`TemplateSyntaxError: Invalid block tag... 'else'`, más abajo en el archivo). Se detectó de inmediato al correr los tests nuevos y se corrigió eliminando el `{% endif %}` sobrante.

### Bloque 4 — Corrección del momento en que se crea la transacción

El usuario notó, probando la app, que algunas transacciones quedaban en la base con estado "Confirmada" y otras en "Pendiente de confirmación", y preguntó por qué no todas nacían pendientes. Verificando los datos reales (`CalculoOperacion.objects.all()`), se confirmó que el comportamiento del Bloque 1 era consistente con lo implementado ahí: **crear** (Paso 1, "Calcular importe") siempre dejaba `estado=PENDIENTE_CONFIRMACION`, y solo pasaban a `CONFIRMADA` las que el propio usuario había confirmado manualmente después (Paso 2, "Confirmar importe") durante sus pruebas — no era un bug.

Sin embargo, al preguntarle qué comportamiento quería en realidad, pidió cambiar el diseño: el Paso 1 ("Calcular importe") **no debe crear ninguna fila todavía** — es una previsualización pura, como el simulador. La transacción recién se crea cuando el cliente aprieta "Confirmar importe" (Paso 2), y en ese momento nace directamente en `PENDIENTE_CONFIRMACION` (no hay más un estado `CONFIRMADA` separado; ese ciclo de vida completo — pago, aprobación, cancelación — queda para un futuro sprint).

Esto invirtió el diseño del Bloque 1:

- `CalculoOperacionView.post()` (Paso 1) ya no persiste nada: calcula tasa, comisión y monto final igual que antes, pero arma un diccionario `resultado` (no un objeto de modelo) con los datos necesarios para confirmar después: `divisa`, `monto_origen`, `cotizacion_id` (la cotización vigente usada) y `vence_en_timestamp` (cuándo deja de ser válido ese cálculo).
- El template pasa esos datos como campos ocultos en el formulario de "Confirmar importe".
- `confirmar_calculo_operacion_view` cambió de firma: ya no recibe un `calculo_id` (no hay nada que buscar), recibe el `tipo` por URL y valida los campos ocultos con el formulario nuevo `ConfirmarCalculoOperacionForm`. Revalida ahí mismo, contra la base, que: (a) no pasó el tiempo de vigencia (`vence_en_timestamp`) y (b) la cotización de la divisa sigue siendo la misma que se usó para calcular (compara el `pk` de `divisa.ultima_cotizacion` contra el `cotizacion_id` oculto — una verificación extra más precisa que solo el tiempo, útil también de cara a la futura HU de cancelación por cambio de cotización). Si ambas validaciones pasan, recalcula tasa/comisión/monto con la cotización *actual* (nunca confía en los montos que vinieron del cliente) y recién ahí crea el `CalculoOperacion`.
- Se quitó `ESTADO_CONFIRMADA` de `CalculoOperacion.ESTADO_CHOICES` (migración `0007_alter_calculooperacion_estado.py`, solo de metadata — no migra datos): ahora `PENDIENTE_CONFIRMACION` es el único estado posible al crear.
- Los tests de `CalculoOperacionTest`, `CompraDeDivisasTest` y `ComisionEnCalculoOperacionTest` se reescribieron para reflejar el flujo en dos pasos reales (calcular vía POST, leer `response.context['resultado']`, y recién confirmar con esos datos como POST separado), y se agregó un test nuevo para el caso de cambio de cotización entre calcular y confirmar.

### Problemas encontrados durante la sesión

**Desincronización con un cambio ya commiteado.** Al escribir los tests, `MetodoPago.objects.create(..., ultimos_4_digitos=...)` falló con `TypeError: MetodoPago() got unexpected keyword arguments`. El campo ya no existía: entre la sesión anterior y esta, se había mergeado a `develop` un commit (`68f1036`) que —además de incorporar el trabajo de comisiones y el fix de métodos de pago de la sesión anterior— renombró `ultimos_4_digitos` a `numero_tarjeta` (migración `0014`), pasando a guardar el número completo de tarjeta (enmascarado en la vista) en vez de solo los últimos 4 dígitos. `tests/test_metodos_pago.py` había quedado con el nombre de campo viejo. Se actualizaron las 5 referencias en el test file a `numero_tarjeta` con valores de 16 dígitos, validando además contra `apps/clientes/forms.py` (exige entre 13 y 19 dígitos numéricos).

### Resultado final

- Suite completa: **136 passed**.
- `manage.py check` y `makemigrations --check --dry-run`: sin problemas.
- Sphinx recompilado en modo estricto (`-W`): sin advertencias.
- Bug de mensajes duplicados corregido en las 3 pantallas afectadas.
- Historial de transacciones disponible para `admin` y `analista_cambiario`.
- La transacción de compra/venta ahora se crea únicamente al confirmar, siempre en "Pendiente de confirmación".

---

## Sesión 6 — 21/09/2026 — GE-31 — Sprint 3: "Venta de divisas" y corrección del cambio de divisas

**Herramienta:** Claude Code (Anthropic, modelo Sonnet 5)
**HU relacionada:** GE-31 — Venta de divisas
**Participantes:** Ruth, integrante del equipo Global Exchange

### Bloque 1 — Pedido: venta de divisas

Implementar la HU "Venta de divisas" cumpliendo todos sus criterios de aceptación, siguiendo la estructura del proyecto, con tests, docstrings, Sphinx actualizado y la documentación del chat con la IA al día.

> Como usuario cliente quiero vender divisas para convertir una moneda y recibir el importe correspondiente en mi cuenta o billetera.

Criterios de aceptación:

1. Cliente activo seleccionado + monto y divisa válidos → se calcula el importe con la HU "Cálculo del importe de la operación" y se crea una transacción en estado **"Pendiente de confirmación"**.
2. Monto inválido (negativo, cero o no numérico) → error de validación, sin crear la transacción.
3. Divisa inactiva o sin tasa vigente → rechazo con un mensaje claro.
4. La transacción queda registrada con tipo **"Venta"**, cliente activo, divisa, monto y fecha de creación.

#### Diagnóstico inicial

Antes de escribir código se revisó `apps/divisas` y `tests/test_operaciones.py`. La venta ya compartía con la compra casi toda la infraestructura de la HU GE-30 (`CalculoOperacionView`, `confirmar_calculo_operacion_view`, `CalculoOperacion` con `tipo=VENTA`, `cliente` y `estado=PENDIENTE_CONFIRMACION`, y `_calcular_importe_operacion`, que ya usa la tasa de compra y resta la comisión). Por eso **no hizo falta un modelo ni una migración nuevos**: el trabajo consistió en verificar cada criterio para la venta, cerrar los huecos encontrados y cubrirla con tests propios, que hasta entonces solo existían para la compra (`CompraDeDivisasTest`).

Huecos detectados:

- **Criterios 2 y 3 sin mensaje claro.** Con `LANGUAGE_CODE = 'en-us'`, un monto como `abc` mostraba "Enter a number." y una divisa inactiva "Select a valid choice. ... is not one of the available choices." (el test de compra existente incluso afirmaba ese texto en inglés). Se agregaron `error_messages` en español a `CalculoOperacionForm` (monto: requerido, no numérico, menor o igual a cero, dígitos y decimales; divisa: requerida e inactiva/no disponible).
- **Tipo de operación sin validar en la confirmación.** `confirmar_calculo_operacion_view` tomaba el `tipo` de la URL con `.upper()` sin comprobar que fuera compra o venta, por lo que un POST a `/divisas/operar/canje/confirmar/` habría creado una transacción con tipo `CANJE`, rompiendo el criterio 4. Se agregó el helper `_normalizar_tipo_operacion` (responde 404 si el tipo no es `COMPRA` ni `VENTA`) y se usa tanto en la vista de cálculo como en la de confirmación.
- **Divisa sin tasa al confirmar.** Si la cotización desaparecía entre el cálculo y la confirmación, se mostraba el mensaje genérico de "el cálculo venció". Ahora se informa que la divisa no tiene cotización disponible, igual que en el Paso 1.
- **Mensaje de éxito de la venta.** Decía siempre "Importe: X PYG"; ahora dice "Importe a recibir" en la venta e "Importe a pagar" en la compra.

#### Cambios realizados

- `apps/divisas/forms.py`: mensajes de validación en español en `CalculoOperacionForm`; docstring de clase ampliado.
- `apps/divisas/views.py`: `_normalizar_tipo_operacion`, uso en `CalculoOperacionView._tipo` y en `confirmar_calculo_operacion_view`, mensaje específico ante falta de cotización al confirmar, mensaje de éxito según el tipo. Docstrings con `Args`/`Returns`/`Raises` en `_calcular_importe_operacion`, `CalculoOperacionView.post` y `confirmar_calculo_operacion_view`.
- `tests/test_operaciones.py`: nueva clase `VentaDeDivisasTest` (17 tests) y ajuste del test de compra que afirmaba el mensaje en inglés.

##### Tests nuevos (`VentaDeDivisasTest`)

| Criterio | Cobertura |
|---|---|
| 1 | Cálculo con tasa de compra y comisión descontada; creación en "Pendiente de confirmación" al confirmar (el Paso 1 no crea nada); uso de la comisión del cliente activo |
| 2 | Monto negativo, cero y no numérico con mensaje de error y sin transacción; montos manipulados en los campos ocultos de la confirmación |
| 3 | Divisa inactiva; divisa desactivada entre el cálculo y la confirmación; divisa sin cotización (en el cálculo y en la confirmación) |
| 4 | Registro de tipo "Venta", cliente, usuario, divisa, código, monto y fecha; con varios clientes asociados queda a nombre del cliente activo seleccionado |
| Seguridad | Usuario con varios clientes sin elegir uno es redirigido a la selección; staff recibe 403; confirmación por GET no crea nada; tipo desconocido responde 404 |
| Integración | La venta confirmada aparece como "Venta" en el historial de transacciones de admin/analista |

Durante la escritura de los tests, dos escenarios de varios clientes fallaron por un error del propio test (`IntegrityError`): `Cliente.user` es un `OneToOne` (titular) y se estaba intentando crear un segundo cliente con el mismo titular. Se corrigió creando los clientes adicionales sin titular y asociándolos al usuario con `usuario.clientes.add(...)`, que es cómo ya lo hacen los tests de `test_seleccion_cliente.py`.

#### Documentación Sphinx

- `docs/source/guia.rst`: sección nueva "Venta de divisas" con el flujo en dos pasos y los casos de rechazo. Además se corrigió un texto desactualizado de "Flujo operativo de divisas": decía que compra/venta se persistían con vencimiento hasta confirmarse, cuando desde GE-30 el cálculo previo no persiste nada y la transacción se crea recién al confirmar.
- `docs/source/reference/apps.divisas.{forms,models,views}.rst`: estas páginas solo listaban una parte de las clases. Se incorporaron `CalculoOperacionForm`, `ConfirmarCalculoOperacionForm`, `TriangulacionForm`, `ConfiguracionComisionForm`, `CalculoOperacion`, `CalculoTriangulacion`, `ConfiguracionComision`, `CalculoOperacionView`, `confirmar_calculo_operacion_view`, `TriangulacionOperacionView`, `confirmar_triangulacion_view`, `HistorialTransaccionesView`, `ConfiguracionComisionListView` y `ActualizarComisionView`.
- No cambió ninguna plantilla, por lo que `templates.rst` no requirió cambios.
- `docs/build/` se regeneró con `sphinx-build -W --keep-going -b html docs/source docs/build`.

#### Resultado del Bloque 1

- Suite completa: **153 passed** (136 previos + 17 nuevos).
- `manage.py check`: sin problemas. `makemigrations --check --dry-run`: sin cambios (no se tocaron modelos).
- Sphinx en modo estricto (`-W`): compilación sin advertencias.

### Bloque 2 — Corrección de la lógica de cambio entre divisas

**Pedido:** "corregí la lógica de cambio de divisa, ya que en el historial de transacciones no se está guardando la transacción con sus datos".

#### Diagnóstico

El cambio entre dos divisas extranjeras (triangulación por PYG) tenía tres problemas, todos derivados de que nunca se había alineado con el flujo de compra/venta que se corrigió en GE-30:

1. **No aparecía en el historial.** `HistorialTransaccionesView` solo leía `CalculoOperacion` (compras y ventas); los cambios viven en otro modelo, `CalculoTriangulacion`, que el historial ignoraba por completo.
2. **Sin cliente activo ni estado.** `CalculoTriangulacion` solo guardaba el `usuario`, no el cliente en nombre del cual se operó (el mismo defecto que ya se había corregido en `CalculoOperacion` y `MetodoPago`), y no tenía un estado de transacción.
3. **Se persistía en el Paso 1.** `TriangulacionOperacionView.post` creaba la fila al *calcular*, no al confirmar. Aunque el cliente nunca confirmara, quedaba un registro; "Confirmar" solo llenaba `confirmado_en`. Compra y venta ya habían cambiado a "calcular = previsualización, confirmar = crea la transacción" (Bloque 4 de GE-30), pero el cambio quedó con el diseño anterior. Llevarlo al historial tal cual habría mostrado como transacciones a simples previsualizaciones.

#### Solución

- **Modelo y migración.** `CalculoTriangulacion` incorpora `cliente` (FK `PROTECT`) y `estado` (único valor: "Pendiente de confirmación"), más la constante `TIPO_DISPLAY = 'Cambio'`. La migración `0008_calculotriangulacion_cliente_estado.py` sigue el mismo patrón que `0006`: agrega los campos, resuelve el cliente de los registros existentes a partir del usuario (titularidad directa o asociación como operador) y recién después vuelve el campo obligatorio.
- **Cálculo sin persistir.** `TriangulacionOperacionView.post` ahora exige un cliente activo seleccionado, calcula con `_calcular_triangulacion` y devuelve un diccionario `resultado` con las tasas, el cruce, la comisión, el importe, el vencimiento y los ids de las dos cotizaciones usadas; no crea nada.
- **Confirmación que crea la transacción.** `confirmar_triangulacion_view` ya no recibe un `calculo_id` (la ruta pasó de `triangulacion/<uuid>/confirmar/` a `triangulacion/confirmar/`). Valida los campos ocultos con el nuevo `ConfirmarTriangulacionForm`, revalida que no haya vencido el tiempo de reserva y que **ambas** cotizaciones sigan siendo las usadas, recalcula el importe con las tasas actuales (no confía en los montos del navegador) y crea el `CalculoTriangulacion` con `cliente=cliente_activo` y `estado=PENDIENTE_CONFIRMACION`. Si una divisa quedó sin cotización o inactiva, informa el motivo y no registra nada.
- **Historial unificado.** `HistorialTransaccionesView` combina compras, ventas y cambios en una sola lista ordenada del más reciente al más antiguo (`_fila_operacion` / `_fila_cambio` normalizan cada modelo). La tabla ahora muestra tipo, estado, usuario, cliente, divisa (los cambios como `USD → EUR`), monto origen, **tasa aplicada** (la tasa cruzada, con 6 decimales, en los cambios), **comisión** e **importe final** en la moneda que corresponde (PYG o la divisa destino).
- **Plantillas.** `triangulacion.html` pasa del contexto `calculo` a `resultado` y envía los campos ocultos al confirmar; `historial_transacciones.html` suma las columnas nuevas.

#### Verificación de la migración contra datos reales

La base de desarrollo tenía una triangulación (USD → EUR, confirmada). Antes de dar la migración por buena se ejecutó `migrate divisas` dentro de una transacción que luego se revirtió (Postgres admite DDL transaccional): el backfill asignó correctamente el cliente al registro existente y, tras el rollback, la base quedó sin cambios (la `0008` sigue pendiente hasta ejecutar `manage.py migrate`).

#### Tests

- `TriangulacionOperacionTest` se reescribió para el flujo en dos pasos (13 tests, en reemplazo de 4): el cálculo no persiste; la confirmación registra todos los datos (cliente, estado, divisas, monto, tasas, cruce, equivalente en PYG, comisión, importe); los importes se recalculan en el servidor aunque se manipulen los campos ocultos; cálculo vencido; cambio de cotización de cualquiera de las dos divisas; divisa sin cotización o inactiva al confirmar; montos inválidos; cliente activo elegido entre varios; confirmación por GET; staff rechazado.
- `HistorialTransaccionesTest` suma 3 tests: el cambio aparece con todos sus datos, el flujo completo (el cliente calcula y confirma, el analista lo ve) y el orden por fecha entre tipos.

#### Problemas encontrados durante la sesión

- **Sphinx en modo estricto falló** con "duplicate object description" para `TIPO_DISPLAY`, `cliente` y `estado`: listar atributos de modelo en una sección `Attributes:` del docstring choca con los que `autodoc` ya documenta (`undoc-members`). Se pasó a prosa.
- **Herramienta de edición.** Un heredoc de shell con triples comillas simples dentro rompió el parseo del comando; los scripts auxiliares de edición se escribieron a archivos temporales.

#### Resultado del Bloque 2

- Suite completa: **165 passed** (153 previos + 9 netos en triangulación + 3 nuevos en historial).
- `manage.py check`: sin problemas. `makemigrations --check --dry-run`: sin cambios.
- Sphinx recompilado con `-E -a -W`: sin advertencias. `guia.rst` documenta el cambio en dos pasos y el historial; `apps.divisas.forms.rst` incluye `ConfirmarTriangulacionForm`.
- Acción pendiente para quien reciba estos cambios: ejecutar `python manage.py migrate` (aplica `divisas.0008`).

### Pendiente / fuera de alcance

- La HU dice "recibir el importe en mi cuenta o billetera": la acreditación efectiva (método de pago o billetera de destino, aprobación y cancelación de la transacción) corresponde a un sprint posterior; los criterios de aceptación de esta HU terminan en el registro de la transacción en "Pendiente de confirmación".
- La exportación completa de esta conversación está en [`exports-completos/chat_entero_claude_GE-31.md`](exports-completos/chat_entero_claude_GE-31.md) (generada a partir del registro de la sesión de Claude Code). `chat_entero_claude.md` y `.cc-history/` corresponden a la sesión de GE-30.
- El historial de transacciones combina los dos modelos en memoria; si el volumen de transacciones crece mucho convendrá unificarlas en una sola tabla o paginar con una consulta `UNION`.

---

## Sesión 7 — 22/09/2026 — GE-73 — Sprint 3: "Confirmación de operación cambiaria"

**Herramienta:** Claude Code (Anthropic, modelo Sonnet 5)
**HU relacionada:** GE-73
**Participantes:** Rodrigo Mereles, integrante del equipo Global Exchange

### Pedido

Implementar la HU "Confirmación de operación cambiaria", con tests, docstrings, Sphinx actualizado y esta documentación de la conversación.

> Como usuario cliente quiero confirmar la operación antes de finalizarla para verificar los datos ingresados.

Criterios de aceptación:

1. Con una transacción en estado "Pendiente de confirmación", al acceder a la pantalla de confirmación, se ve el resumen completo (tipo de operación, divisa, monto, tasa aplicada, comisión, monto final).
2. Al revisar el resumen y confirmar, si la tasa vigente no cambió desde el cálculo inicial, el sistema marca la transacción como "Confirmada".
3. Al revisar el resumen y cancelar manualmente, la transacción pasa a "Cancelada" y no se procesa.
4. Al confirmarse, se registra la fecha y hora de confirmación.

### Diagnóstico inicial

Esta sesión arrancó después de un salto de contexto grande: entre la última vez que se tocó el código y este pedido, se habían mergeado a `develop` dos ramas más (`feature/GE-30` y `feature/GE-31`, ver las Sesiones 5 y 6 de este documento). El estado del código no coincidía con lo recordado de la sesión anterior, así que antes de tocar nada se releyeron por completo `apps/divisas/models.py`, `views.py`, `urls.py`, `forms.py`, los templates de compra/venta y triangulación, y `tests/test_operaciones.py` (1040 líneas a esa altura).

Eso confirmó que el flujo de "Compra"/"Venta de divisas" (GE-30/GE-31) ya tenía el patrón de dos pasos (Calcular → Confirmar, sin persistir hasta el Paso 2) extendido simétricamente también a `CalculoTriangulacion` (cambio entre divisas), con `estado` limitado a un único valor posible, `PENDIENTE_CONFIRMACION`. La nota de "pendiente / fuera de alcance" del documento de GE-31 ya anticipaba esto: *"la acreditación efectiva..., aprobación y cancelación de la transacción corresponde a un sprint posterior"*. Esta HU es exactamente ese sprint posterior: agrega un tercer paso ("pantalla de confirmación") sobre la transacción ya creada en el Paso 2, con dos acciones posibles — confirmar (si la tasa no cambió) o cancelar.

### Diseño

- **Estados nuevos.** Se reincorporaron `CONFIRMADA` y `CANCELADA` a `ESTADO_CHOICES` en `CalculoOperacion` y `CalculoTriangulacion` (migración `0009`, solo metadata).
- **Verificación de tasa vigente como propiedad del modelo**, no de la vista, para que sea testeable por separado: `CalculoOperacion.tasa_vigente_cambio` (compara la tasa que correspondería aplicar ahora — venta para una compra, compra para una venta — contra `tasa_aplicada`) y `CalculoTriangulacion.tasas_vigentes_cambiaron` (compara ambas cotizaciones, origen y destino).
- **Vistas nuevas** `ConfirmarTransaccionOperacionView` y `ConfirmarTransaccionCambioView` (ambas `View` con `LoginRequiredMixin`/`UserPassesTestMixin`, mismo patrón que `DivisaSoftDeleteView`): GET muestra el resumen; POST con `accion=confirmar` o `accion=cancelar` procesa la transición. Ambas resuelven el objeto por `pk` y `usuario=request.user` (404 si no es el dueño), y rechazan reprocesar una transacción que ya no está `PENDIENTE_CONFIRMACION`.
- **`confirmado_en` se movió de "cuándo se creó" a "cuándo se confirmó".** Antes, `confirmar_calculo_operacion_view`/`confirmar_triangulacion_view` (Paso 2, el que crea la fila) seteaban `confirmado_en=ahora` en el mismo `create()`. Eso ya no tiene sentido con esta HU: ahora esas vistas dejan `confirmado_en=None` al crear, y son las vistas nuevas las que lo completan recién cuando el cliente aprieta "Confirmar operación" — así el criterio 4 ("se registra la fecha y hora de confirmación") se cumple literalmente, no de forma adelantada.
- **El Paso 2 ahora redirige al Paso 3** (a la pantalla de confirmación de la transacción recién creada) en lugar de volver al formulario en blanco, para que el flujo completo (calcular → crear pendiente → revisar y confirmar/cancelar) sea navegable de punta a punta sin que el cliente tenga que buscar la transacción por otro lado.
- Templates nuevos `divisas/confirmar_transaccion.html` y `divisas/confirmar_transaccion_cambio.html`, con el mismo desglose (`operation-summary`) que ya usan las pantallas de cálculo, más dos botones ("Confirmar operación" / "Cancelar") cuando el estado es pendiente, o un aviso de cuándo se confirmó o que se canceló, en caso contrario.

### Tests

`ConfirmacionOperacionCambiariaTest` (compra/venta) y `ConfirmacionCambioDivisasTest` (cambio entre divisas) en `tests/test_operaciones.py`, uno por criterio de aceptación más casos de borde: resumen completo, confirmar con tasa sin cambios, confirmar rechazado si la tasa cambió, cancelar, fecha de confirmación registrada, no se puede reprocesar una transacción ya resuelta, otro cliente no puede ver ni accionar la transacción ajena (404), y un rol `admin` no puede acceder a la pantalla (403).

### Problemas encontrados durante la sesión

- **Tres tests existentes rotos por el nuevo redirect**, no por errores de lógica: al confirmar, la respuesta ya no vuelve al formulario en blanco sino a la nueva pantalla de resumen, así que un texto plano como `'Importe a recibir: 722700.00 PYG'` dejó de aparecer contiguo (el HTML separa la etiqueta y el valor con una etiqueta `<strong>` de por medio). Se dividieron esas aserciones en dos (`'Importe a recibir'` y `'722700.00'` por separado).
- **Un test con fecha comparada mal, no relacionado con este cambio.** `HistorialTransaccionesTest.test_historial_muestra_tipo_estado_cliente_divisa_monto_y_fecha` comparaba `self.transaccion.creado_en.strftime('%d/%m/%Y')` (el datetime crudo, en UTC) contra lo que el template renderiza con el filtro `|date` de Django (en `TIME_ZONE = 'America/Asuncion'`). Cerca de la medianoche UTC ambas fechas difieren un día. Se corrigió usando `timezone.localtime(...)` antes de comparar — bug latente preexistente, no introducido en esta sesión, que se aprovechó a corregir de paso porque hizo fallar la suite.
- **Identificadores de `Cliente` demasiado largos.** `identificador` tiene `max_length=20`; un valor de prueba como `'CONFIRMACION-CAMBIO-001'` (23 caracteres) rompía la inserción en PostgreSQL con "el valor es demasiado largo". Se acortaron a `'CONF-CAMBIO-001'`/`'-002'`.

### Resultado final

- Suite completa: **179 passed** (163 previos + 16 nuevos de esta HU).
- `manage.py check`: sin problemas. `makemigrations --check --dry-run`: sin cambios pendientes.
- Sphinx recompilado con `-W`: sin advertencias. `guia.rst` documenta el flujo en tres pasos (calcular → confirmar creación → confirmar/cancelar operación); `templates.rst` incluye los dos templates nuevos.

### Bloque 2 — Vencimiento de transacciones pendientes sin resolver

Pregunta del usuario: ¿qué pasa si el cliente llega a la pantalla de confirmación y cierra la pestaña sin confirmar ni cancelar? Con lo implementado en el Bloque 1, esa transacción quedaba "Pendiente de confirmación" en la base de datos para siempre — nadie la iba a tocar de nuevo. El usuario propuso un estado de expiración que se dispare al superar el límite de tiempo (de confirmar el importe, o de confirmar la operación), y pidió implementarlo siguiendo la lógica ya establecida.

#### Diseño

- **Nuevo estado `VENCIDA`** en ambos modelos (migración `0010`).
- **Configuración separada** `settings.CONFIRMACION_OPERACION_VIGENCIA_SEGUNDOS` (300s por defecto, igual que `CALCULO_OPERACION_VIGENCIA_SEGUNDOS`, pero como constante propia para poder ajustarla sin afectar el otro límite). El campo `vence_en` que ya existía en el modelo — y que, tras el rediseño del Bloque 1 de GE-30/31, había quedado sin ningún chequeo real una vez creada la fila — se repropone para este uso: en vez de "hasta cuándo vale la tasa calculada" (eso ahora lo maneja el campo oculto efímero `vence_en_timestamp` entre calcular y confirmar), pasa a significar "hasta cuándo tiene el cliente para confirmar o cancelar esta transacción ya creada".
- **El problema de fondo**: nada garantiza que el cliente vuelva a visitar la pantalla de confirmación si cierra la pestaña, y solo esa vista tiene permiso de escritura sobre la transacción. Si el vencimiento se resolviera *solo* de forma perezosa al visitarla (como `esta_vencido` ya hace en el resto del sistema), una transacción abandonada seguiría mostrando "Pendiente de confirmación" en el historial de administración indefinidamente, aunque ya no se pueda hacer nada con ella. Se resolvió separando dos conceptos:
  - `estado` (persistido): el hecho oficial, que se actualiza la próxima vez que *alguien con permiso* (el propio cliente) abre esa transacción — mismo patrón perezoso que ya usa `esta_vencido`, sin tareas en segundo plano.
  - `estado_efectivo` (calculado al vuelo, propiedad de solo lectura, sin efectos secundarios): si `estado` sigue "Pendiente" pero ya pasó `vence_en`, devuelve "Vencida" sin escribir nada. Lo usa el historial de administración (`HistorialTransaccionesView`, vía `get_estado_efectivo_display()`) para mostrar siempre la verdad, la haya persistido alguien o no.
  - `marcar_vencida_si_corresponde()`: el único punto de escritura real, llamado al principio de `get()` y `post()` en ambas vistas de confirmación. Si la transacción vencida, la persiste antes de seguir.
- **Efecto en `post()`**: si tras el chequeo la transacción quedó (o ya estaba) "Vencida", se bloquean tanto `confirmar` como `cancelar` con un mensaje específico ("El tiempo para confirmar... venció. Debe recalcular la operación"), distinto del genérico "ya fue procesada" que se usa para Confirmada/Cancelada.
- **Templates**: nueva rama `{% elif transaccion.estado == 'VENCIDA' %}` en `confirmar_transaccion.html` y `confirmar_transaccion_cambio.html`, con un botón "Recalcular" que lleva de vuelta al Paso 1 correspondiente.
- **Migración de datos**: al revisar la base de desarrollo aparecieron 4 `CalculoOperacion` y 3 `CalculoTriangulacion` ya "Pendiente de confirmación" con `vence_en` pasado — exactamente el caso que preocupaba al usuario, ya presente en los datos reales. La migración `0010` además de agregar la opción de estado hace un `RunPython` que las pasa a "Vencida" de una vez.

#### Tests

10 tests nuevos (5 por cada tipo de transacción, compra/venta y cambio): la pantalla marca vencida una transacción abandonada al visitarla; confirmar una vencida no la confirma; cancelar una vencida no la cancela; `estado_efectivo` no persiste nada por sí solo (se vuelve a leer de la base para comprobarlo); y el historial de administración muestra "Vencida" sin que nadie haya visitado esa transacción todavía.

#### Resultado del Bloque 2

- Suite completa: **188 passed** (179 anteriores + 9 netos de esta vuelta).
- `manage.py check` y `makemigrations --check --dry-run`: sin problemas.
- Sphinx recompilado con `-W`: sin advertencias. `guia.rst` documenta el vencimiento y la distinción entre estado persistido y estado efectivo.
- Se verificó contra la base de desarrollo que el backfill de la migración `0010` marcó correctamente como "Vencida" las 7 transacciones que ya estaban en ese estado de facto.

### Bloque 3 — Configuración de los tiempos de espera para el administrador

Pedido: agregar un apartado de configuración para que el administrador pueda modificar, en segundos, los dos tiempos de espera que hasta ahora estaban fijos en `settings.py` (`CALCULO_OPERACION_VIGENCIA_SEGUNDOS` y `CONFIRMACION_OPERACION_VIGENCIA_SEGUNDOS`, agregada en el Bloque 2).

#### Diseño

Se replicó el patrón ya usado para `ConfiguracionComision` (modelo editable con fallback a `settings`), pero como registro único en vez de uno por categoría, ya que acá solo hay dos valores globales, no una lista:

- **`ConfiguracionVigencia`** (modelo nuevo, migración `0011`): dos campos (`calculo_vigencia_segundos`, `confirmacion_vigencia_segundos`), `actualizado_en`/`actualizado_por` para auditoría, y dos classmethods (`vigencia_calculo_segundos`, `vigencia_confirmacion_segundos`) que devuelven la configuración guardada o, si no existe ninguna todavía, los valores de `settings`. Los 6 lugares de `views.py` que antes leían `settings.CALCULO_OPERACION_VIGENCIA_SEGUNDOS` / `CONFIRMACION_OPERACION_VIGENCIA_SEGUNDOS` directamente ahora pasan por estos classmethods.
- **`ConfiguracionVigenciaUpdateView`** (`AdminDivisasMixin`, exclusiva de `admin` — a diferencia de comisiones, la HU pidió esto solo "para el administrador", sin mencionar `analista_cambiario`, así que no se reusó el mismo permiso). `get_object` recupera el único registro existente o construye uno con los valores por defecto, para que el formulario siempre tenga algo que editar.
- Template `divisas/configuracion_vigencia_form.html`, un único formulario con ambos campos y su explicación de a qué paso del flujo corresponde cada uno.
- Enlace nuevo en el sidebar y en el inicio, dentro de la sección "Administración" (visible con `es_admin`, igual que "Clientes"/"Registrar cliente").

#### Problema encontrado

Los campos se definieron primero como `PositiveIntegerField`, que Django valida automáticamente con su propio mensaje en inglés ("Ensure this value is greater than or equal to 0") *antes* de que el `clean_<campo>` del formulario llegue a ejecutarse — pasaba silenciosamente para `0` (que si cumple "mayor o igual a cero") pero pisaba el mensaje en español para negativos. Se cambió a `IntegerField` simple, dejando toda la validación (">0", en español) del lado del formulario — mismo criterio que ya usa `ConfiguracionComisionForm.clean_porcentaje` para no depender de mensajes de Django sin traducir.

#### Tests

`tests/test_configuracion_vigencia.py` (nuevo archivo, 9 tests): resolución con y sin configuración guardada, el administrador ve el formulario prellenado con los valores por defecto, guarda ambos tiempos, editar una segunda vez actualiza el mismo registro sin duplicarlo, `analista_cambiario` y `cliente` no pueden acceder (403), y se rechaza cada campo en cero o negativo. Además, un test de integración en `CalculoOperacionTest` que configura ambos tiempos y verifica que se reflejen tanto en el `vence_en_timestamp` del cálculo (Paso 1) como en el `vence_en` de la transacción ya creada (Paso 2), no solo que la vista de configuración guarde el valor.

#### Resultado del Bloque 3

- Suite completa: **198 passed** (188 anteriores + 10 nuevos).
- `manage.py check` y `makemigrations --check --dry-run`: sin problemas.
- Sphinx recompilado con `-W`: sin advertencias. `guia.rst` documenta de dónde sale cada tiempo de espera y quién puede configurarlo.

### Pendiente / fuera de alcance

- La exportación del transcript completo de la sesión (equivalente a `chat_entero_claude_GE-31.md` de la sesión anterior) no se generó acá: ese archivo se produjo por fuera de las herramientas disponibles en esta sesión de Claude Code (aparentemente un export manual desde el editor). Este documento es el registro narrativo de la conversación, con el mismo nivel de detalle que los anteriores de esta carpeta.
- Sigue sin existir un paso de "pago" real después de confirmar: la transacción "Confirmada" queda ahí, sin acreditación ni comprobante — coherente con que ese alcance quedó fuera de GE-30/GE-31 y tampoco lo pide esta HU.

---

## Sesión 8 — 24/09/2026 — GE-37 — Consultar el historial de transacciones

**Herramienta:** Claude Code (Anthropic, modelo Sonnet 5)
**HU relacionada:** GE-37
**Participantes:** Adriana Benítez, integrante del equipo Global Exchange

### Pedido

Implementar la HU "Consultar el historial de transacciones", con tests, docstrings, Sphinx actualizado y esta documentación de la conversación.

> Como usuario cliente quiero consultar el historial de transacciones para revisar las operaciones realizadas en nombre del cliente activo.

Criterios de aceptación:

1. Con un cliente activo seleccionado, al acceder al historial, se ve un listado paginado de las transacciones de ese cliente (compras, ventas, confirmadas, canceladas).
2. Cada transacción del listado muestra: tipo de operación, divisa, monto, tasa aplicada, estado y fecha.
3. Al filtrar por rango de fechas y/o estado, el listado se actualiza mostrando solo las que coinciden.
4. Al seleccionar una transacción del listado, se accede al detalle completo de esa operación.
5. Si el cliente activo no tiene transacciones registradas, el sistema muestra un mensaje indicando que no hay operaciones, sin error.
6. Es una HU de solo consulta: no permite editar, eliminar ni reprocesar transacciones desde esta pantalla.

### Diagnóstico inicial

Antes de tocar código se releyeron `apps/divisas/models.py`, `views.py` y `urls.py`, `apps/clientes/middleware.py` (selección del cliente activo), `apps/authentication/context_processors.py` (flags de UI), `templates/base.html` (sidebar), `templates/divisas/historial_transacciones.html` y `tests/test_operaciones.py`, en particular `HistorialTransaccionesView` y su `HistorialTransaccionesTest`.

Esa vista ya resuelve un problema parecido — normaliza `CalculoOperacion` (compra/venta) y `CalculoTriangulacion` (cambio) a un mismo formato de fila y las mezcla en una sola lista ordenada por fecha —, pero es exclusiva de administración y análisis cambiario (`{'admin', 'analista_cambiario'}` en `test_func`) y muestra las transacciones de **todos** los clientes; un test existente lo deja explícito: *"El historial no se limita a un único cliente, a diferencia de las vistas del cliente"*. No existía ninguna vista que mostrara únicamente las transacciones del `cliente_activo` de la sesión (concepto ya resuelto por `ClienteActivoMiddleware`, reusado tal cual del resto de vistas de operación). Tampoco había precedente de un listado con filtros por `GET` combinados con paginación en `apps.divisas` — sí en `apps.users.views.PanelAdminView`, que filtra manualmente con `request.GET.get(...)` sin `django-filter` (no está instalado en el proyecto).

### Diseño

- **`MiHistorialTransaccionesView`** (`apps/divisas/views.py`, junto a `HistorialTransaccionesView`): mismo patrón de normalización a filas (`_fila_operacion`/`_fila_cambio`), pero filtrando `CalculoOperacion`/`CalculoTriangulacion` por `cliente=self.cliente_activo` en vez de traer todas. `test_func` reutiliza el criterio ya establecido para pantallas de cliente (rol `cliente`, no staff, con al menos un cliente asociado activo, igual que `ConfirmarTransaccionOperacionView`); el `get()` exige además que haya un `cliente_activo` concreto en la sesión (mismo mensaje de error y redirección a `home` que usan `CalculoOperacionView`/`TriangulacionOperacionView` cuando falta).
- **Filtros por `fecha_desde`, `fecha_hasta` y `estado`, aplicados en Python sobre las filas ya normalizadas**, no con `queryset.filter(...)`. La razón: el estado que se muestra es el *efectivo* (`estado_efectivo`, que puede valer "Vencida" aunque el campo `estado` en la base de datos todavía diga "Pendiente de confirmación" porque nadie volvió a visitar esa transacción — ver el diseño de vencimiento perezoso ya documentado en la Sesión 7 de este documento). Filtrar contra la base con `.filter(estado=...)` habría dejado pasar transacciones vencidas de hecho bajo el filtro "Pendiente de confirmación", inconsistente con lo que la fila muestra. Al filtrar sobre las filas ya resueltas, la fecha también se compara ya convertida a hora local (`timezone.localtime(...).date()`, `TIME_ZONE = 'America/Asuncion'`), evitando el mismo error de comparación en UTC que tuvo que corregirse en GE-73.
- **Distinción entre "sin transacciones" (criterio 5) y "sin resultados para el filtro"**: el contexto agrega `tiene_transacciones` (un `.exists()` aparte, sin filtros) para que la plantilla muestre "Todavía no tenés transacciones registradas." solo cuando el cliente realmente no operó nunca, y "No se encontraron transacciones para el filtro seleccionado." cuando sí tiene pero el filtro no coincide con ninguna — mismo criterio que ya usa `panel_admin.html` para "sin resultados de búsqueda".
- **Paginación con filtros preservados en los enlaces "Anterior"/"Siguiente"**: no había precedente de esto en el proyecto (`historial_transacciones.html` pagina pero no filtra; `panel_admin.html` filtra pero no combina el filtro con `?page=N` en los enlaces). Se agregó `context['querystring']` (los parámetros `GET` actuales sin `page`, vía `request.GET.copy(); pop('page'); urlencode()`) y se concatena en la plantilla.
- **Detalle de solo lectura, separado de las pantallas de confirmación existentes**: la HU prohíbe explícitamente ofrecer acciones de confirmar/cancelar/reprocesar desde esta pantalla (criterio 6), así que no se reutilizaron `ConfirmarTransaccionOperacionView`/`ConfirmarTransaccionCambioView` (que sí las tienen). Se agregaron `DetalleTransaccionOperacionView` y `DetalleTransaccionCambioView`, mismo patrón de `View` + `get_object_or_404(pk=..., cliente=cliente_activo)` para que una transacción ajena responda 404, pero con una plantilla nueva sin ningún `<form>` de acción. Al ser dos modelos distintos (`CalculoOperacion`/`CalculoTriangulacion`) se resolvieron como dos vistas y dos rutas, igual que ya lo hace el resto del flujo de operación (`operar/transaccion/<uuid:pk>/` vs. `triangulacion/transaccion/<uuid:pk>/`); cada fila del listado enlaza a una u otra según `fila['tipo_modelo']` (`'operacion'`/`'cambio'`, dato nuevo agregado a las filas normalizadas, que `HistorialTransaccionesView` no necesitaba porque sus filas no enlazan a ningún lado).
- **Rutas nuevas**, agrupadas bajo el mismo prefijo que ya usa el historial administrativo: `divisas/transacciones/mias/`, `divisas/transacciones/mias/operacion/<uuid:pk>/` y `divisas/transacciones/mias/cambio/<uuid:pk>/`.
- **Nuevo flag de UI `puede_ver_historial_propio`** en `permisos_ui_context` (`apps/authentication/context_processors.py`), con el mismo criterio que `puede_operar_divisas` (cliente, con cliente asociado, no admin) — se separó como flag propio en vez de reutilizar `puede_operar_divisas` directamente en el template para no acoplar la visibilidad del enlace del historial a la de "Comprar"/"Vender"/"Cambiar" si el criterio de alguna de esas cambiara a futuro. Enlace nuevo "Mi historial de transacciones" en el sidebar (`templates/base.html`), dentro de la sección "Operaciones", junto a "Cambiar entre divisas".

### Tests

`MiHistorialTransaccionesTest` (nueva clase en `tests/test_operaciones.py`, junto a `HistorialTransaccionesTest`): listado paginado con compras/ventas confirmadas y canceladas propias, paginación real con 27 transacciones (20 en la página 1, resto en la página 2), exclusión de transacciones de otro cliente, cada fila expone tipo/divisa/monto/tasa/estado/fecha, filtro por estado, filtro por rango de fechas (excluye una transacción de hace 30 días), clic en una fila lleva al detalle completo (compra) y al detalle de un cambio entre divisas, 404 al intentar ver el detalle de una transacción ajena, mensaje sin error cuando el cliente no tiene transacciones, ausencia de cualquier acción de confirmar/cancelar/reprocesar en listado y detalle, y 403 para el rol `admin` (sin cliente propio).

### Problemas encontrados durante la sesión

- **`Cliente.objects.create(user=otro_usuario, ...)` no asocia automáticamente al usuario como operador.** El primer intento del test de "otro cliente no puede ver el detalle ajeno" dejaba a `otro_usuario` sin ningún cliente en `otro_usuario.clientes` (la relación M2M `usuarios`, distinta del `OneToOneField` `user`/`cliente_perfil`), así que `test_func` lo rechazaba con 403 antes de llegar al chequeo de propiedad que se quería probar (404). Se corrigió agregando `otro_usuario.clientes.add(otro_cliente)` explícitamente, igual que ya lo hacen los tests existentes de `ConfirmacionOperacionCambiariaTest`.
- **Aserción `assertNotContains(response, '<form')` demasiado amplia.** Todas las páginas heredan de `base.html`, que ya trae un `<form method="post">` para cerrar sesión en la barra superior; esa aserción fallaba siempre, sin relación con la HU. Se acotó a lo que realmente importa: ausencia de `name="accion"` (el campo que usan los formularios de confirmar/cancelar) y de los textos "Confirmar"/"Cancelar" en la pantalla de detalle.
- **`rm -rf docs/build` borró archivos versionados.** Al recompilar la documentación Sphinx para verificar que no hubiera advertencias, se intentó limpiar el directorio de salida asumiendo que era un artefacto de build sin versionar; `git status` reveló que `docs/build/` está commiteado en este repositorio. Se restauró con `git restore docs/build` antes de continuar, sin volver a recompilar sobre ese directorio para no dejarlo desactualizado a medias.

### Resultado final

- Suite completa: **218 passed** (206 previos + 12 nuevos de esta HU).
- `manage.py check`: sin problemas. `makemigrations --check --dry-run`: sin cambios pendientes (esta HU no agrega ni modifica modelos).
- Sphinx recompilado con `-W`: sin advertencias. `guia.rst` documenta el nuevo historial propio con filtros y detalle de solo lectura; `templates.rst` incluye los tres templates nuevos; `reference/apps.divisas.views.rst` documenta `MiHistorialTransaccionesView`, `DetalleTransaccionOperacionView` y `DetalleTransaccionCambioView`.

### Bloque 2 — Dos bugs reportados al usar la pantalla nueva

El usuario probó la pantalla recién implementada y reportó dos problemas, ambos en el flujo de cambio de cliente activo (`apps/clientes/views.py`), no en el código nuevo de esta HU en sí:

1. Parado en el detalle de una transacción (`DetalleTransaccionOperacionView`/`DetalleTransaccionCambioView`) y cambiando de cliente activo desde el selector del header, la página respondía "page not found" en vez de llevar al historial del cliente nuevo.
2. En ese mismo selector ("Cambiar de cliente"), un cliente de tipo jurídico se mostraba con la palabra "None" antes de su nombre.

#### Diagnóstico

- **Bug 1**: `cambiar_cliente_view` (`apps/clientes/views.py`) redirige, tras cambiar el cliente activo en la sesión, al `HTTP_REFERER` de la petición — es decir, a la misma URL en la que estaba el usuario. Eso funciona para pantallas genéricas, pero el detalle de una transacción lleva el `pk` del registro en la URL (`.../transacciones/mias/operacion/<uuid:pk>/`), y ese registro pertenece al cliente *anterior*; `DetalleTransaccionOperacionView.get()` filtra `get_object_or_404(..., cliente=cliente_activo)`, así que al volver ahí con el cliente ya cambiado, el mismo `pk` casi nunca pertenece al cliente nuevo y responde 404. El "page not found" no era un bug de la pantalla de detalle en sí (que sigue siendo correcta: no debe mostrar transacciones ajenas), sino de a dónde redirige el cambio de cliente.
- **Bug 2**: en `templates/base.html`, el bloque que arma "Operando como" (línea ~196) ya resolvía bien el tipo jurídico con un `{% if cliente_activo.tipo_cliente == 'JURIDICA' %}`, pero el `{% for c in mis_clientes %}` de debajo (línea 208, la lista de "Cambiar de cliente") no tenía ese mismo chequeo: renderizaba `{{ c.nombre }} {{ c.apellido|default:c.razon_social }}` sin condicionar por tipo. Un cliente jurídico tiene `nombre`/`apellido` en blanco (usa `razon_social` en cambio); en una plantilla Django, una variable que resuelve a `None` se imprime literalmente como el texto `"None"` (a diferencia de una variable que no existe, que se imprime vacía), así que `{{ c.nombre }}` producía `"None"` antes del nombre. El filtro `default` en `c.apellido` sí disparaba correctamente hacia `razon_social` (por eso el nombre completo terminaba apareciendo), pero arrastraba el "None" del campo anterior.

#### Corrección

- **Bug 1**: en vez de redirigir siempre al `referer` tal cual, `cambiar_cliente_view` ahora resuelve ese `referer` con `django.urls.resolve` y lo compara contra un diccionario nuevo, `DESTINO_AL_CAMBIAR_CLIENTE_DESDE_DETALLE` (`apps/clientes/views.py`), que mapea las pantallas de detalle de un registro del cliente anterior a su listado de origen — por ahora, `divisas:detalle_transaccion_operacion` y `divisas:detalle_transaccion_cambio`, ambas hacia `divisas:mis_transacciones`. Si el referer no está en ese mapeo (el caso normal), el comportamiento no cambia: se vuelve ahí igual que antes. Se armó como un mapeo explícito, no una regla genérica automática, para no adivinar sobre pantallas que no se probaron; queda documentado en el docstring de `_redireccion_tras_cambiar_cliente` como el lugar a extender si aparece otra pantalla de detalle con el mismo problema (por ejemplo, editar un método de pago tiene la misma forma — `get_object_or_404(MetodoPago, pk=pk, cliente=cliente_activo)` —, pero no fue parte de lo reportado, así que no se tocó).
- **Bug 2**: se replicó en el `{% for c in mis_clientes %}` de `templates/base.html` el mismo condicional por `tipo_cliente` que ya usaba el "Operando como" de arriba, en vez de depender de `default` para disimular el campo vacío.

#### Tests

Dos tests nuevos en `tests/test_seleccion_cliente.py` (estilo pytest, junto a los ya existentes de `TestSeleccionClienteActivo`):

- `test_cambiar_cliente_desde_el_detalle_de_una_transaccion_vuelve_al_historial`: reproduce el bug 1 exacto — cliente activo A con una transacción propia, cambia a cliente B con `HTTP_REFERER` apuntando al detalle de esa transacción, y verifica que la redirección es al historial (`divisas:mis_transacciones`), no al mismo detalle.
- `test_cambiar_cliente_desde_una_pantalla_sin_registro_propio_vuelve_ahi`: confirma que el comportamiento por defecto (volver al referer) sigue intacto para una pantalla que no está en el mapeo especial.
- `test_dropdown_de_cambio_de_cliente_muestra_la_razon_social_sin_none`: reproduce el bug 2 — un cliente jurídico con `razon_social` pero sin `nombre`/`apellido`, y verifica que el HTML del selector no contiene el `"None"` pegado a la razón social.

#### Resultado del Bloque 2

- Suite completa: **221 passed** (218 anteriores + 3 nuevos de esta corrección).
- `manage.py check`: sin problemas.
- Sphinx recompilado con `-W` sobre un directorio temporal (sin tocar `docs/build/`, que está versionado): sin advertencias. No hizo falta actualizar `.rst` a mano porque `apps.clientes.views.rst` usa `automodule` con `:members:`, así que documenta el nuevo diccionario y la nueva función helper automáticamente a partir de sus docstrings.

### Pendiente / fuera de alcance

- No se agregó exportación (CSV/PDF) del historial ni de una transacción individual: la HU pide solo consulta en pantalla.
- El filtro por estado usa una lista fija (`CalculoOperacion.ESTADO_CHOICES`, idéntica a la de `CalculoTriangulacion`); si algún día los estados de ambos modelos divergen, el combo debería construirse a partir de la unión de ambos en vez de asumir que son iguales.

---

## Sesión 9 — 08/10/2026 — GE-25 — Asociación de pagos a transacciones

**Herramienta:** Claude Code (Anthropic, modelo Sonnet 5)
**HU relacionada:** GE-25
**Rama:** `feature/GE-25`
**Participantes:** Rodrigo Mereles, integrante del equipo Global Exchange

### Pedido

Implementar la HU "Asociación de pagos a transacciones" en la rama en la que ya se estaba
trabajando (`feature/GE-25`), con tests, docstrings, Sphinx actualizado y esta documentación de
la conversación. El pedido aclaraba además que la producción en AWS ya estaba levantada, así que
el desarrollo tenía que funcionar tanto en desarrollo como en producción sin romper nada.

> Como usuario cliente quiero que los pagos realizados queden asociados a mis transacciones para
> poder identificar correctamente cada operación.

Criterios de aceptación:

1. Al confirmarse un pago, queda asociado a una única transacción, con el medio de pago, el
   proveedor, el identificador externo, el monto y la fecha. Un pago no puede registrarse sin una
   transacción válida.
2. Un pago exitoso sobre una transacción "Confirmada" la pasa a "Pagada".
3. Una transacción con un pago exitoso rechaza cualquier otro intento de pago, sea cual sea el
   medio.
4. Una confirmación duplicada del mismo pago (mismo proveedor e identificador externo) no registra
   un segundo pago ni altera la transacción.
5. El cliente ve, en el detalle de su transacción, el pago asociado (medio, monto, fecha,
   identificador) o que todavía no tiene uno registrado.
6. Un cliente no puede ver el pago ni la transacción de otro cliente.

### Diagnóstico inicial y una pregunta que cambió el alcance

Antes de diseñar nada se preguntó explícitamente cómo debía "registrarse"/"confirmarse" un pago,
dado que el proyecto no tiene ninguna pasarela de pago real integrada ni webhooks existentes: la
opción propuesta por defecto era un flujo simulado y síncrono, iniciado por el propio cliente desde
la pantalla de una transacción "Confirmada", eligiendo uno de sus métodos de pago ya guardados
(`apps.clientes.models.MetodoPago`, de GE-19).

La respuesta cambió el enfoque del diseño: esta HU es explícitamente la base de dos HU futuras que
todavía no existen en el código — "Pago con tarjeta vía Stripe" y "Pago por transferencia bancaria
vía SIPAP" —, ambas con webhooks propios (verificación de firma de Stripe, verificación de origen
de SIPAP, y en el caso de SIPAP un estado "observado" para montos que no coinciden). Con ese dato,
se decidió separar claramente dos capas:

- Un punto de entrada único e idempotente, `Pago.registrar_pago`, que no sabe nada de Stripe ni de
  SIPAP: solo recibe medio, proveedor, identificador externo y monto ya resueltos, valida y persiste.
- El flujo *manual* de esta HU (el cliente elige un método guardado y paga) es, para
  `registrar_pago`, un proveedor más (`Pago.PROVEEDOR_MANUAL`), exactamente como lo serán Stripe y
  SIPAP el día que se implementen — sin necesitar tocar `registrar_pago` ni `Pago` para agregarlos.

Se resolvió explícitamente no modelar ahora un estado "observado" ni verificación de firma: son
responsabilidad de las HU de Stripe/SIPAP cuando existan, y adelantarlas sin esas HU implementadas
habría sido especular sobre un diseño que todavía no está pedido.

### Diseño

- **Modelo nuevo `Pago`** (`apps/divisas/models.py`): dos `OneToOneField` nulos,
  `calculo_operacion` y `calculo_triangulacion` (exactamente uno de los dos, nunca ambos ni
  ninguno, validado en `clean()`), siguiendo el mismo patrón que el resto del código usa para los
  dos tipos de transacción (vistas y templates paralelos) en vez de una `GenericForeignKey`, que no
  tiene precedente en este proyecto. Además `medio_pago` (reusa
  `MetodoPago.TIPO_MEDIO_CHOICES`), `proveedor` y `identificador_externo` (como texto libre, para
  no tener que migrar cuando se agregue Stripe/SIPAP), `monto`, `creado_en` y un `metodo_pago`
  opcional (FK a `MetodoPago`, para trazabilidad cuando el pago vino de un método guardado).
- **`Pago.registrar_pago`** (classmethod): el único punto de escritura. Si ya existe un pago con el
  mismo `(proveedor, identificador_externo)`, lo devuelve sin tocar nada (criterio 4). Si la
  transacción no está "Confirmada" (incluido el caso de que ya esté "Pagada"), levanta
  `PagoRechazadoError`. Si pasa ambas validaciones, crea el `Pago` y marca la transacción "Pagada"
  dentro de una única transacción de base de datos.
- **Idempotencia bajo concurrencia real, no solo "a simple vista".** Entre el chequeo inicial y el
  `create()` hay una ventana de carrera (dos confirmaciones casi simultáneas del mismo pago, o dos
  intentos de pago distintos sobre la misma transacción). Se resolvió capturando `IntegrityError`
  del `create()` y, recién ahí, distinguiendo los dos casos posibles: si ya existe un pago con ese
  mismo `(proveedor, identificador_externo)`, era la otra llamada ganando la carrera del mismo pago
  (se devuelve esa fila, caso idempotente); si no, la colisión fue el propio `OneToOneField` de la
  transacción (alguien más ya le registró un pago distinto), y se informa "ya fue pagada" — así el
  criterio 3 ("por cualquier medio") queda garantizado por la base de datos, no solo por un chequeo
  previo en Python que una carrera podría saltarse.
- **Estado nuevo `PAGADA`** agregado a `ESTADO_CHOICES` de `CalculoOperacion` y
  `CalculoTriangulacion` (migración `0013`, solo metadata).
- **Vistas nuevas** `PagarTransaccionOperacionView` y `PagarTransaccionCambioView` (mismo patrón
  `LoginRequiredMixin`/`UserPassesTestMixin` que el resto de pantallas de cliente, ownership por
  `cliente=cliente_activo` — no por `usuario`, a propósito, porque el criterio 6 habla
  explícitamente de "otro cliente"): GET muestra el formulario de pago (o por qué todavía no se
  puede pagar) y POST registra el pago con `monto_final` de la transacción, que el cliente no puede
  modificar. El identificador externo del flujo manual es el propio `pk` de la transacción, lo que
  de paso lo hace naturalmente idempotente ante un doble clic en "Pagar".
- **Formulario `PagarTransaccionForm`**: un único campo `metodo_pago`, acotado por `__init__` a los
  métodos de pago del cliente activo (mismo patrón que ya usan `ConfirmarCalculoOperacionForm` y
  `ConfirmarTriangulacionForm` para acotar choices dinámicamente).
- **Templates**: dos pantallas nuevas (`pagar_transaccion.html`/`pagar_transaccion_cambio.html`,
  siguiendo la misma duplicación por tipo que ya usan `confirmar_transaccion*.html`); un botón
  "Pagar" nuevo en la rama "Confirmada" de `confirmar_transaccion*.html`; y una sección "Pago" nueva
  en `detalle_transaccion_operacion.html`/`detalle_transaccion_cambio.html` que muestra el pago
  asociado o, si no hay ninguno, un aviso explícito con un acceso directo para pagar (criterio 5).

### Tests

- `PagoRegistrarPagoTest` (7 tests): ejercita `Pago.registrar_pago` directamente, sin pasar por
  vistas — los 4 criterios centrales (asociación completa, paso a "Pagada", rechazo del segundo pago
  "por cualquier medio", idempotencia ante una confirmación duplicada), el rechazo por falta de
  transacción válida, el rechazo si la transacción no está "Confirmada", y que el mismo método
  funciona igual para un cambio entre divisas (`CalculoTriangulacion`), no solo para compra/venta.
- `PagarTransaccionOperacionTest` (8 tests) y `PagarTransaccionCambioTest` (3 tests): el flujo
  completo vía HTTP — la pantalla ofrece los métodos de pago guardados, pagar marca la transacción
  "Pagada" con todos los datos del pago, no se ofrece el formulario si la transacción no está
  confirmada, se rechaza pagar una transacción ya pagada, un reenvío del mismo pago no duplica nada,
  el detalle muestra el pago o la ausencia de uno, y otro cliente recibe 404 tanto al intentar ver
  como al intentar pagar la transacción ajena (criterio 6).

### Resultado final

- Suite completa: **250 passed**, sin fallas (18 tests nuevos en `tests/test_operaciones.py` para
  esta HU).
- `manage.py check` y `makemigrations --check --dry-run`: sin problemas.
- Sphinx recompilado en modo estricto (`-W`): sin advertencias. `guia.rst` documenta el flujo de
  pago, el rol de `Pago.registrar_pago` y por qué está pensado como base de Stripe/SIPAP;
  `templates.rst` incluye las dos pantallas nuevas; las páginas de referencia de `models`, `forms` y
  `views` de `apps.divisas` incluyen `Pago`, `PagoRechazadoError`, `PagarTransaccionForm`,
  `PagarTransaccionOperacionView` y `PagarTransaccionCambioView`.
- No fue necesario tocar nada de la infraestructura de producción (Dockerfile, `docker-compose.yml`,
  Nginx, ni el workflow de GitHub Actions): la migración `0013` se aplica sola en el próximo
  despliegue, porque `deploy/aws/entrypoint.sh` ya corre `migrate` al arrancar el contenedor de la
  app, y esta HU no agrega variables de entorno ni servicios nuevos.

### Pendiente / fuera de alcance

- No se implementó ningún proveedor real de pago: ni Stripe ni SIPAP existen todavía en este
  código. Esta HU deja `Pago` y `registrar_pago` listos para que esas dos HU futuras los reutilicen
  desde sus propios webhooks, sin tener que rediseñar nada de lo construido acá.
- No se modeló un estado "observado" (pago con monto distinto al esperado, mencionado en la futura
  HU de SIPAP): no lo pide esta HU y se prefirió no especular sobre un diseño que todavía no está
  definido.
- El pago manual de esta HU no tiene ninguna verificación de firma ni de autenticidad: es, a
  propósito, el mismo flujo simulado que ya usaban las operaciones de compra/venta/cambio antes de
  tener un gateway real.

## Sesión 10 — 09/10/2026 — Apertura de Caja

**Herramienta:** Claude Code (Anthropic, modelo Sonnet 5)
**HU relacionada:** Apertura de Caja
**Rama:** `feature/GE-25`
**Participantes:** Rodrigo Mereles, integrante del equipo Global Exchange

### Pedido

Implementar la HU "Apertura de Caja", con tests, docstrings, Sphinx actualizado y esta
documentación de la conversación.

> Como cajero quiero abrir una caja registrando el inventario inicial por moneda para comenzar mi
> turno operativo.

Criterios de aceptación:

1. Sin una caja abierta, al ingresar el saldo inicial de cada moneda que va a manejar, el sistema
   crea una caja en estado "Abierta", asociada al cajero y a la fecha y hora de apertura.
2. Con una caja ya abierta, intentar abrir otra se rechaza, indicando que hay que cerrar la actual
   primero.
3. Un saldo inicial negativo o con formato inválido en alguna moneda muestra el error de validación
   sin crear la caja; un saldo inicial de cero es válido.
4. Al acceder a su panel tras abrir la caja correctamente, el cajero ve el saldo inicial por moneda
   tal como lo registró.
5. Un usuario sin rol de cajero no puede acceder a ninguna función de caja (apertura, operaciones,
   arqueo, movimientos o cierre).

### Diagnóstico inicial

El rol `cajero` ya existía como string reconocido en el flujo de autenticación desde las primeras
sesiones de este proyecto (GE-7), pero no estaba conectado a ninguna lógica de autorización ni vista
real: `apps.authentication.backends` no filtra roles contra una lista fija del lado de Django (todo
rol no técnico que llega de Keycloak pasa directo a `session['keycloak_roles']`), así que no hizo
falta tocar nada ahí — solo empezar a *usar* `'cajero' in roles` en las vistas nuevas, igual que ya
se hace con `'cliente'`/`'admin'`/`'analista_cambiario'`.

No existía ningún modelo de caja en el proyecto. Se evaluó dónde ubicarlo: dado que el resto del
código separa dominios en apps propias (`apps.authentication`, `apps.clientes`, `apps.divisas`,
`apps.users`), se creó una app nueva, `apps.caja`, en vez de forzarlo dentro de `apps.divisas` solo
porque maneja montos — la caja es un dominio propio (apertura, y a futuro operaciones, arqueo,
movimientos y cierre), no una extensión del catálogo de divisas.

### Diseño

- **`apps.caja.models.Caja`**: UUID, `usuario` (el cajero), `estado` (`ABIERTA`/`CERRADA`),
  `abierta_en` (automático), `cerrada_en` (nulo por ahora). El cierre, las operaciones, el arqueo y
  los movimientos son HU futuras que no existen todavía en este código; `estado` ya contempla
  "Cerrada" desde ahora para no migrar el modelo de nuevo cuando se implementen, siguiendo el mismo
  criterio que ya se usó en GE-25 (`Pago` como base de Stripe/SIPAP).
- **`apps.caja.models.SaldoInicialCaja`**: una fila por divisa activa con el monto contado al abrir,
  asociada a la `Caja`.
- **Restricción única parcial en la base** (`UniqueConstraint` con `condition=Q(estado='ABIERTA')`
  sobre `usuario`): el Criterio 2 no depende solo de que la vista chequee si ya hay una caja abierta
  antes de crear otra — la propia base de datos lo impide, así que una carrera entre dos pestañas
  abriendo caja casi al mismo tiempo no puede crear dos filas "Abierta" para el mismo cajero. La
  vista captura el `IntegrityError` de esa carrera y lo convierte en el mismo mensaje de rechazo, en
  vez de dejarlo explotar como error 500 (mismo patrón que `Pago.registrar_pago` en GE-25).
- **`apps.caja.forms.AperturaCajaForm`**: en vez de pedirle al cajero que elija qué monedas va a
  manejar y después el monto de cada una (dos pasos), genera dinámicamente un campo
  `saldo_<divisa.pk>` por cada divisa activa del sistema (incluido PYG, si existe como divisa
  activa) en un único paso. Un saldo en cero simplemente significa "no manejo esta moneda en este
  turno", que es exactamente lo que pide el Criterio 3 al declarar válido un saldo en cero.
  `DecimalField(min_value=0)` con mensajes de error en español (mismo criterio que
  `CalculoOperacionForm.monto` en `apps.divisas`) cubre tanto el monto negativo como el no numérico.
- **`apps.caja.views.AbrirCajaView`** y **`PanelCajaView`**: ambas restringen `test_func` a
  `'cajero' in roles`, sin excepción para `admin` ni `analista_cambiario` (a diferencia de otras
  pantallas del sistema) porque el Criterio 5 no menciona ninguna excepción. El panel
  (`/caja/`) muestra la caja abierta del cajero con su saldo inicial por moneda, o invita a abrir
  una si todavía no tiene ninguna.
- Se agregó el enlace "Mi caja" al sidebar (sección nueva "Caja") y una tarjeta en `home.html`,
  ambos condicionados al flag de UI `puede_ver_caja`, siguiendo el mismo patrón que el resto de
  accesos — con la corrección reciente (misma sesión anterior) de que ningún acceso del sidebar
  quede sin su tarjeta correspondiente en el inicio.

### Tests

`tests/test_caja.py` (14 tests nuevos): uno por cada criterio de aceptación (apertura con el saldo
de cada moneda, rechazo de una segunda caja abierta tanto por POST como por no ofrecer el formulario
en el GET, monto negativo, formato inválido, saldo en cero válido, el panel muestra el saldo
registrado, acceso denegado sin rol cajero —en apertura y en panel, por GET y por POST— y sin ningún
rol, redirección al login sin sesión), más una clase aparte (`CajaModeloTest`) que prueba la
restricción de base de datos directamente contra el modelo, sin pasar por la vista: ni una segunda
`Caja.objects.create()` para el mismo cajero con estado "Abierta", ni un `SaldoInicialCaja`
duplicado para la misma divisa en la misma caja, pasan la restricción.

### Problema encontrado durante la sesión (no introducido por esta HU)

Al correr la suite completa antes de cerrar, falló `test_home_page_unauthenticated`: el botón de
login en `home.html` decía "Iniciar Sesión" en vez de "Iniciar Sesión con Keycloak SSO". El archivo
había cambiado por fuera de esta sesión de Claude Code (el sistema lo señaló explícitamente al
empezar esta conversación) antes de tocar nada de Caja; no pareció un cambio intencional —acorta el
texto del botón sin ningún motivo aparente y rompía un test que no tiene relación con esta HU—, así
que se restauró el texto completo y se avisó explícitamente en la respuesta, en vez de corregirlo en
silencio.

### Resultado final

- Suite completa: **253 passed** (239 anteriores + 14 nuevos de esta HU), sin fallas tras restaurar
  el texto del botón de login.
- `manage.py check` y `makemigrations --check --dry-run`: sin problemas. Migración `apps.caja.0001`
  verificada contra la base de desarrollo (PostgreSQL), incluida la restricción única parcial.
- Sphinx recompilado con `-W`: sin advertencias. `guia.rst` documenta el flujo de apertura y por qué
  el resto de las funciones de caja quedan fuera de esta HU; `templates.rst` incluye las dos
  pantallas nuevas; se agregó `reference/apps.caja.rst` (y sus submódulos) a la referencia, enlazado
  desde `reference/apps.rst`.

### Pendiente / fuera de alcance

- El cierre de caja, las operaciones de caja, el arqueo y los movimientos son HU futuras: no existe
  ninguna vista para ellas todavía, solo el modelo ya preparado (`Caja.estado` contempla "Cerrada")
  para no tener que migrar de nuevo cuando se implementen.
- No se ofrece elegir qué monedas manejar antes de ingresar los montos: se pidió el saldo de todas
  las divisas activas de una vez, usando cero como "no manejo esta moneda", que es más simple y
  cumple el criterio igual.

## Sesión 11 — 09/10/2026 — GE-22 — Pago con tarjeta vía Stripe

**Herramienta:** Claude Code (Anthropic, modelo Sonnet 5)
**HU relacionada:** Pago con tarjeta vía Stripe
**Rama:** `feature/GE-22`
**Participantes:** Rodrigo Mereles, integrante del equipo Global Exchange

### Pedido

Implementar la HU "Pago con tarjeta vía Stripe", con tests, docstrings, Sphinx actualizado y esta
documentación de la conversación.

> Como usuario cliente quiero pagar mis operaciones cambiarias con tarjeta de crédito o débito para
> completar el pago de forma inmediata, sin salir del proceso en línea.

Criterios de aceptación:

1. Con una transacción "Confirmada", elegir pagar con tarjeta redirige a la página de pago de
   Stripe con el monto exacto de la transacción, calculado por el sistema y no modificable por el
   usuario.
2. Cuando Stripe confirma el pago exitoso mediante webhook, el sistema registra el pago como
   exitoso con el identificador de Stripe y el medio "tarjeta".
3. Una notificación al webhook con firma inválida se rechaza sin modificar el estado de ninguna
   transacción.
4. Si Stripe informa que el pago fue rechazado, la transacción permanece "Confirmada" y se muestra
   un mensaje de error claro, con opción de reintentar.
5. Si el cliente abandona o cancela el pago en Stripe, al volver al sistema la transacción sigue
   "Confirmada" y puede reintentarse.
6. Si Stripe no responde o la conexión falla, el sistema no marca la transacción como pagada y
   muestra un mensaje de problema de comunicación, sin perder el estado de la transacción.

También se preguntó si la documentación Sphinx servida en producción se actualiza
automáticamente al hacer merge a `main`, igual que el resto de la app.

### Diagnóstico y diseño

Esta HU es, explícitamente, una de las dos continuaciones previstas para GE-25 ("Asociación de
pagos a transacciones", Sesión 9): esa HU dejó `apps.divisas.models.Pago.registrar_pago` como el
único punto de escritura para marcar una transacción como pagada, pensado para que los webhooks de
Stripe y SIPAP armen sus propios datos (medio, proveedor, identificador externo, monto) y llamen
ahí, sin duplicar lógica. Por eso casi todo el trabajo de esta sesión fue de integración: no hizo
falta tocar `Pago` ni su modelo de datos.

Se instaló el SDK oficial de Stripe (`stripe==16.0.0`) y se agregaron `STRIPE_SECRET_KEY`/
`STRIPE_WEBHOOK_SECRET` a la configuración (`global_exchange/settings/base.py`, `.env.example`,
`.env.prod.example`) con `default=''`: sin cuenta de Stripe configurada, iniciar un pago con
tarjeta falla igual que un corte de comunicación real (criterio 6), en vez de necesitar una clave
de mentira para poder arrancar el proyecto.

Decisiones de diseño, una por cada criterio de aceptación:

- **Criterio 1.** Se usó Stripe *Checkout* (una página de pago hospedada por Stripe), no la API de
  tarjetas en bruto: la sesión se crea en el servidor con `transaccion.monto_final`, así que el
  cliente nunca tiene un campo editable. La moneda de liquidación reutiliza el mismo criterio que
  ya usa el pago manual de GE-25 (PYG para una compra/venta, la divisa de destino para un cambio).
  Como Stripe espera enteros y PYG es una de sus monedas "sin decimales" (a diferencia de la
  mayoría), se agregó `_monto_en_unidad_minima_stripe` para no cobrar, por error, 100 veces el
  monto real en un pago en guaraníes.
- **Criterio 2.** El webhook (`stripe_webhook_view`) escucha `checkout.session.completed` con
  `payment_status == "paid"` y llama a `Pago.registrar_pago` con el `payment_intent` de Stripe como
  identificador externo y `MetodoPago.TIPO_TARJETA` como medio. El `pk` de la transacción y si es
  una compra/venta o un cambio viajan en los metadatos de la sesión de Checkout, porque es lo único
  que el webhook recibe de vuelta para saber a qué transacción corresponde.
- **Criterio 3.** La firma se valida con `stripe.Webhook.construct_event` antes de mirar el
  contenido del evento; si falla, se responde 400 sin tocar nada.
- **Criterio 4.** Con Stripe Checkout, un rechazo de tarjeta ocurre *dentro* de la página hospedada
  por Stripe, que ya le muestra al cliente el motivo y lo deja reintentar sin salir de ahí ni
  generar ningún webhook (a diferencia de implementar la API de tarjetas a mano, donde el rechazo
  habría que manejarlo del lado de Global Exchange). Se documentó esta decisión explícitamente en
  el docstring del módulo en vez de dejarla implícita, porque es la razón por la que no hay código
  para ese caso.
- **Criterio 5.** `cancel_url` vuelve a la pantalla de detalle de la transacción con
  `?pago=cancelado`; como el webhook nunca se disparó, la transacción sigue "Confirmada". Se agregó
  `_avisar_resultado_pago_stripe` para mostrar el aviso correspondiente ahí.
- **Criterio 6.** La creación de la sesión está envuelta en `try/except stripe.error.StripeError`
  (cubre, entre otros, `APIConnectionError`); si falla, se informa el problema sin tocar la
  transacción.

El webhook se expuso en `/webhooks/stripe/`, fuera del namespace `divisas:` y en
`global_exchange/urls.py` en vez de `apps/divisas/urls.py`: es una URL fija que se configura una
sola vez en el dashboard de Stripe, no una pantalla de la aplicación.

### Tests

`tests/test_pagos_stripe.py` (17 tests nuevos), mockeando `stripe.checkout.Session.create` y
`stripe.Webhook.construct_event` para no depender de la red: conversión de monto y moneda
(PYG sin centavos vs. una moneda común), creación de la sesión con el monto y los metadatos
correctos para una compra/venta y para un cambio, rechazo de una transacción que no está
"Confirmada", error de comunicación con Stripe sin modificar la transacción (criterio 6), acceso
restringido al rol `cliente`, aviso de cancelación sin tocar la transacción (criterio 5), aviso de
confirmación pendiente al volver con el pago iniciado, firma inválida sin modificar nada
(criterio 3), registro del pago con el identificador y medio correctos ante una sesión completada y
pagada (criterio 2), sesión completada pero no pagada y evento no relevante sin modificar nada
(criterio 4), reenvío del mismo evento sin duplicar el pago, y el webhook rechazando cualquier
método que no sea POST.

### Resultado final

- Suite completa: pasa sin fallas (ver el run de esta misma sesión).
- `manage.py check`: sin problemas.
- Sphinx recompilado con `-W` (a un directorio temporal, sin tocar `docs/build/` directamente):
  sin advertencias. Se agregó `reference/apps.divisas.pagos_stripe.rst` (enlazado desde
  `reference/apps.divisas.rst`) y una sección nueva "Pago con tarjeta vía Stripe" en `guia.rst`,
  justo después de la sección de GE-25 que esta HU continúa.
- Se agregó el botón "Pagar con tarjeta (Stripe)" a `pagar_transaccion.html` y
  `pagar_transaccion_cambio.html`, junto al pago manual ya existente (ver la corrección del mismo
  día más abajo: este botón se terminó eliminando a favor de una redirección automática).

### Respuesta a la pregunta sobre despliegue y documentación

El pipeline de GitHub Actions (`deploy.yml`) despliega automáticamente a producción en cada push a
`main`: vía SSM se conecta a la instancia EC2, hace `git pull` y reconstruye la imagen con
`docker compose up -d --build`, cuyo `entrypoint.sh` corre `migrate`, `collectstatic` y levanta
Gunicorn. Eso sí se actualiza solo.

La documentación Sphinx **no** se actualizaba solo: `docs/build/`, lo que sirve
`global_exchange.views.documentacion` en producción, es un directorio versionado en git —
una foto fija de la última vez que alguien corrió `sphinx-build` a mano y comiteó el resultado—, y
ni `deploy.yml` ni `entrypoint.sh` ejecutaban `sphinx-build` en ningún momento. Mergear a `main`
actualizaba el código y, con él, `docs/source/`, pero la versión HTML servida seguía siendo la
vieja hasta el próximo commit manual de `docs/build/`.

Se corrigió como parte de esta sesión: `deploy/aws/entrypoint.sh` ahora reconstruye la
documentación (`python -m sphinx -b html docs/source docs/build`) en cada despliegue, antes de
levantar Gunicorn, sin `-W` y con un `|| echo ...` de respaldo para que un warning o error de
Sphinx nunca impida que la aplicación arranque. Con este cambio ya mergeado, la documentación en
producción también queda al día con cada `push` a `main`, igual que el resto de la app.

### Pendiente / fuera de alcance

- El pago por transferencia vía SIPAP, la segunda continuación prevista para GE-25, sigue sin
  implementar.
- No se implementó un reintento automático ni un reenvío manual del webhook desde la UI de Global
  Exchange: si Stripe no logra entregar la notificación, depende de los reintentos automáticos que
  ya hace Stripe por su cuenta.

### Corrección posterior (mismo día): error real al probar en desarrollo

Al configurar las claves reales de una cuenta de Stripe de prueba y probar el flujo en desarrollo,
iniciar un pago fallaba con "No se pudo conectar con Stripe". El error real (reproducido llamando
directamente a `stripe.checkout.Session.create` con la clave del `.env`) era
`InvalidRequestError: The payment_method_types parameter is no longer supported when creating a
Checkout Session` — Stripe retiró ese parámetro; los métodos de pago aceptados se configuran ahora
desde el Dashboard, no desde el código. Se quitó `payment_method_types=['card']` de la llamada en
`apps.divisas.pagos_stripe` y se volvió a probar en vivo contra la cuenta de test: la sesión se
crea correctamente.

De paso, se simplificó la UI a pedido del usuario: en vez de un botón separado "Pagar con tarjeta
(Stripe)" junto al botón "Pagar" manual, queda un único botón "Pagar". `PagarTransaccionOperacionView`/
`PagarTransaccionCambioView` ahora miran el `tipo_medio` del método de pago elegido: si es
"tarjeta" (`MetodoPago.TIPO_TARJETA`), redirigen a iniciar el cobro con Stripe en vez de registrar
el pago ahí mismo; para transferencia o billetera, el registro sigue siendo manual e inmediato,
como ya hacía GE-25. Se actualizaron tres tests de GE-25 en `tests/test_operaciones.py` que usaban
un método de tipo "tarjeta" para probar el flujo manual (pasaron a usar transferencia, ya que ese
camino ya no aplica a tarjetas) y se agregaron dos tests nuevos que verifican la redirección
automática a Stripe. Suite completa: sigue sin fallas tras el cambio.

### Ampliación posterior (mismo día): tarjeta guardada con cobro directo

El usuario preguntó si el número de tarjeta que ya tiene guardado un cliente en
`apps.clientes.models.MetodoPago` (GE-19) se podía usar para precargar el pago en Stripe, y si era
obligatorio pasar por una ventana de Stripe o se podía cobrar solo por API. La respuesta fue que no:
Stripe no acepta (ni conviene) mandarle un número de tarjeta crudo desde el backend — es
justamente lo que PCI-DSS prohíbe — pero sí se puede lograr el mismo efecto (no volver a pedir la
tarjeta) guardándola del lado de Stripe la primera vez y reutilizando esa referencia después. El
usuario pidió esa opción completa.

Se implementó:

- **`apps.clientes.models.Cliente.stripe_customer_id`** (migración `0015`): el id del `Customer`
  de Stripe de cada cliente, separado a propósito de `MetodoPago` — la tarjeta nunca se guarda en
  esta base, solo la referencia que da Stripe.
- **`_obtener_o_crear_cliente_stripe`**: crea el `Customer` la primera vez (`stripe.Customer.create`)
  y lo reutiliza después.
- **`_tarjeta_guardada`**: consulta (`stripe.PaymentMethod.list`) si ese `Customer` ya tiene una
  tarjeta guardada.
- **`_IniciarPagoStripeBaseView.get`** ahora resuelve estos dos datos antes de decidir el camino:
  sin tarjeta guardada, crea la sesión de Checkout de siempre, pero con `customer=...` y
  `payment_intent_data.setup_future_usage = "off_session"` para que Stripe la guarde si el pago
  sale bien; con una tarjeta ya guardada, cobra directo con un `PaymentIntent`
  (`off_session=True, confirm=True`) sin mostrar ninguna página de Stripe, usando una
  `idempotency_key` fija por transacción (`ge22-pago-directo-<pk>`) para que un doble clic no cobre
  la tarjeta dos veces. Si ese cobro directo es rechazado (`stripe.error.CardError`, criterio 4) o
  el banco exige 3-D Secure/SCA (`status == "requires_action"`), cae al camino de Checkout para que
  el cliente confirme ahí, con la misma tarjeta preseleccionada.

Tests nuevos en `tests/test_pagos_stripe.py` (25 en total en el archivo): creación/reutilización
del `Customer`, consulta de la tarjeta guardada, cobro directo exitoso (sin llamar a Checkout),
caída a Checkout ante un rechazo y ante una autenticación adicional exigida, y que ninguno de estos
caminos toca la transacción salvo el que efectivamente la cobra. `manage.py makemigrations
--check`: sin cambios pendientes. Sphinx recompilado con `-W`: sin advertencias, con una sección
nueva "Tarjeta guardada: cobro directo sin pasar por Stripe" en `guia.rst`.

### Segunda ampliación (mismo día): integrar la tarjeta con los métodos de pago guardados (GE-19)

El usuario pidió respetar el sistema de métodos de pago guardados ya existente (GE-19): que una
tarjeta se pueda agregar y elegir desde ese mismo menú, en vez de depender solo de "la primera
tarjeta que Stripe encuentre" para el cliente (el diseño de la ampliación anterior), y que el mismo
esquema sirva a futuro para mostrar cuentas bancarias de SIPAP en ese menú.

Se rediseñó la integración para que una tarjeta sea, en los hechos, un `MetodoPago` más:

- **Modelo.** `MetodoPago` ganó dos campos genéricos (no específicos de Stripe, migración `0016`):
  `proveedor_externo` (`STRIPE`/`SIPAP`, pensado para que SIPAP identifique cuentas bancarias del
  mismo modo el día que se implemente) y `referencia_externa` (el id que da ese proveedor — para
  Stripe, un `PaymentMethod` — nunca el número real).
- **Alta de una tarjeta.** `apps.clientes.forms.MetodoPagoForm` (el formulario manual de GE-19) deja
  de ofrecer "Tarjeta" como opción al crear: una tarjeta ahora se agrega exclusivamente vía
  `IniciarAgregarTarjetaStripeView`/`confirmar_tarjeta_stripe_view` (nuevas, en
  `apps.divisas.pagos_stripe`), que piden solo el nombre del titular, abren una sesión de Stripe
  Checkout en modo `"setup"` (guarda una tarjeta sin cobrar nada) y, al volver, crean el
  `MetodoPago` con la marca y los últimos 4 dígitos que devuelve Stripe — nunca el número completo,
  que Stripe no entrega. Al editar una tarjeta ya vinculada a Stripe, el formulario bloquea tipo,
  entidad financiera y número (vienen de Stripe), dejando editable solo el nombre del titular y si
  es la predeterminada.
- **Pago.** El cliente sigue eligiendo un `MetodoPago` cualquiera en la pantalla de pago de siempre;
  si es de tipo tarjeta, la vista de Stripe ya no adivina "la tarjeta guardada del cliente"
  (`_tarjeta_guardada`, eliminada): recibe el `pk` del método elegido por `?metodo_pago=` y resuelve
  esa tarjeta puntual (`_resolver_metodo_pago_tarjeta`), cobrando con su `referencia_externa`. Esto
  también deja al cliente tener varias tarjetas guardadas y elegir cuál usar, algo que el diseño
  anterior no permitía.
- **UI.** El listado de métodos de pago (`metodo_pago_list.html`) agregó el botón "Agregar tarjeta"
  (lleva al flujo de Stripe) junto al de transferencia/billetera, muestra "•••• •••• •••• <últimos
  4>" para una tarjeta de Stripe sin el botón "Ver datos" (no hay nada más que revelar), y conserva
  el comportamiento anterior para los métodos manuales.

Tests nuevos: `MetodoPagoFormStripeTest` en `tests/test_metodos_pago.py` (el formulario no ofrece
"Tarjeta" al crear, la rechaza si se la fuerza a mano, y bloquea los datos de Stripe al editar sin
impedir cambiar el titular); `test_pagos_stripe.py` se reescribió para reflejar el nuevo diseño
(40 tests: resolución del método de pago elegido —propio, ajeno, sin vínculo a Stripe, de otro
tipo—, cobro directo con sus kwargs exactos, caída a Checkout, alta y confirmación de una tarjeta
nueva —incluida una sesión de Stripe que no corresponde al cliente, que responde 404—). Se
actualizaron además los dos tests de GE-25 que verificaban la redirección a Stripe, para esperar el
`?metodo_pago=` en la URL. Sphinx recompilado con `-W`: sin advertencias, con la sección de
`guia.rst` reescrita para describir el alta vía Stripe y el cobro por `MetodoPago` elegido.

### Tercera corrección (mismo día): bug real al probar el alta de una tarjeta

Al probar el alta de una tarjeta contra la cuenta de test real, `confirmar_tarjeta_stripe_view`
tiraba `AttributeError: 'get' is a dict method, but a StripeObject is not a dict` justo en la
línea que leía `metadata.get('nombre_titular')`. La causa: el SDK de Stripe devuelve objetos
`StripeObject` (una sesión, un `SetupIntent`, el evento de un webhook), que en esta versión del SDK
no heredan de `dict` — no tienen `.get()` ni son iterables, solo soportan `objeto['clave']` y
`objeto.atributo`. Los tests no lo habían detectado porque mockeaban esas respuestas con dicts
planos o `SimpleNamespace`, que sí tienen `.get()` y por lo tanto no reproducían el problema.

El mismo bug existía también, sin haber llegado todavía a probarse, en `_procesar_sesion_completada`
(el webhook de confirmación de pago), que hacía `session.get(...)` sobre el mismo tipo de objeto.

Se agregó `_a_dict` (convierte un `StripeObject` a dict plano con `.to_dict()`, recursivo; un dict
ya plano o `None` se devuelve sin tocar) y se aplicó en ambos puntos antes de cualquier `.get()`.
Para que los tests mismos detecten esta clase de bug en el futuro, se reescribieron los mocks más
sensibles (la sesión de `confirmar_tarjeta_stripe_view`, el evento del webhook) para construir
`StripeObject` reales (`stripe._stripe_object.StripeObject.construct_from`) en vez de dicts o
`SimpleNamespace`, y se agregó `ADictTest` con pruebas unitarias dedicadas.

De paso, el usuario pidió que el nombre precargado al agregar una tarjeta fuera solo el nombre del
cliente, sin su identificador ni su estado (`Cliente.__str__` agrega ambos entre paréntesis, pensado
para listados administrativos). Se agregó `Cliente.nombre_completo` (solo nombre + apellido, o la
razón social para una persona jurídica) y se usó en el valor inicial del formulario y como
alternativa cuando Stripe no devuelve el nombre en los metadatos.

Tests nuevos: `ADictTest` (conversión de un `StripeObject` real, de un dict plano, y de `None`),
`TestClienteNombreCompleto` en `tests/test_clientes.py` (persona física y jurídica), y un test de
regresión en `test_pagos_stripe.py` que registra un pago a partir de un evento de webhook armado
como `StripeObject` real. Suite completa: sin fallas tras el fix.

### Cuarta corrección (mismo día): Stripe ofrecía "Link" en vez de pedir una tarjeta

Al probar el alta de una tarjeta contra la cuenta de test real por segunda vez, apareció otro error
real: `AttributeError: card` al leer `metodo_stripe.card.brand`. La causa, distinta de la anterior:
sin `payment_method_types` (Stripe lo retiró de la API, ver la corrección anterior), Checkout ofrece
cualquier medio habilitado en la cuenta — y por defecto eso incluye "Link", el autocompletado propio
de Stripe, mostrado de forma muy prominente en la página. Si el cliente elegía Link en vez de
ingresar una tarjeta, el `PaymentMethod` que devolvía Stripe era de tipo `"link"`, sin el atributo
`card` que la vista necesitaba leer.

Se investigó si existía algún parámetro vigente para restringir los medios de pago de una sesión
(ya que `payment_method_types` está retirado) y se encontró `payment_method_configuration`: permite
referenciar una `PaymentMethodConfiguration` propia de la cuenta. Se agregó
`_configuracion_solo_tarjeta` (crea, o reutiliza si ya existe por nombre, una configuración con
tarjeta prendida y Link apagado — verificado contra la cuenta de test real, con
`link.available: False` confirmado en la respuesta de Stripe) y se la referenció en las dos sesiones
de Checkout que crea el módulo (el alta de una tarjeta y el fallback de pago cuando el cobro directo
no alcanza). Como defensa adicional, `confirmar_tarjeta_stripe_view` ahora revisa que el
`PaymentMethod` devuelto tenga de verdad el atributo `card` antes de leerlo; si no, informa el
problema sin crear nada en vez de romper.

De paso, el usuario pidió confirmar que las tarjetas agregadas vía Stripe se puedan ver en el
listado de métodos de pago: ya estaba implementado desde la ampliación anterior (el bug impedía
llegar a probarlo), así que se reforzó el test de confirmación existente para verificar
explícitamente que, tras agregar una tarjeta, el listado la muestra enmascarada
("•••• •••• •••• 4242").

Tests nuevos: `ConfiguracionSoloTarjetaTest` (reutiliza una configuración existente, crea una nueva
con los valores correctos si no existe, y cachea el resultado sin volver a llamar a la API) y un
test de regresión que simula un `PaymentMethod` de tipo `"link"` para confirmar que no rompe ni crea
nada. Suite completa: sin fallas tras el fix.

### Ajuste final (mismo día): solo eliminar métodos de pago, sin editar

El usuario pidió sacar la opción de editar un método de pago (quedando solo "eliminar"), y adaptar
sus criterios de aceptación de la HU "Pago con tarjeta vía Stripe" —sobre todo el primero— para que
reflejen lo que realmente se construyó (el diseño original asumía que pagar con tarjeta siempre
redirige a una página de Stripe; la implementación final cobra directo la mayoría de las veces).

Se eliminó `apps.clientes.views.metodo_pago_update` y su URL (en `apps/clientes/urls.py` y en el
alias de `global_exchange/urls.py`), el botón "Editar" de `metodo_pago_list.html`, y la lógica ahora
muerta de `MetodoPagoForm` que bloqueaba los campos de una tarjeta de Stripe al editarla (ya no hay
ninguna vista que la instancie con `instance=`). `MetodoPagoForm` quedó exclusivamente para crear una
transferencia o billetera; se le sacó el campo `numero_tarjeta` (ya no se usa ahí) y a
`metodo_pago_form.html` el bloque y el JS que mostraban ese campo. El criterio 4 de GE-19
("Modificar datos de un método existente") quedó reemplazado por una prueba que confirma que esa
URL ya no existe y que el listado no ofrece "Editar": para cambiar algo, el flujo es eliminar y
volver a crear.

Los 6 criterios de aceptación de "Pago con tarjeta vía Stripe" se reescribieron (ver la respuesta
completa en el chat) para reflejar el diseño final: el criterio 1 pasó de "redirige siempre a
Stripe" a "cobra directo, sin redirigir, salvo que haga falta confirmar un rechazo o una
autenticación adicional"; se agregó un criterio 7 nuevo para el alta de la tarjeta (prerequisito que
el texto original no contemplaba, porque esa HU se escribió asumiendo que cada pago pediría la
tarjeta de nuevo). El resto de los criterios se mantuvieron o se ajustaron mínimamente.

También se explicó, sin cambios de código, cómo verificar que el pago con tarjeta realmente se
comunica con Stripe (aunque en modo test el dinero no sea real): comparando el
`identificador_externo` guardado en cada `Pago` contra el Dashboard de Stripe en modo test
(`https://dashboard.stripe.com/test/payments`) y contra el log de Developers → Events, que muestran
la petición y la respuesta real de la API. Más adelante, el mismo día, se explicó también cómo
habilitar Stripe en producción (webhook con la URL real, secretos propios del `.env` del servidor,
reinicio del contenedor) y que `STRIPE_SECRET_KEY` sí se puede compartir entre entornos pero
`STRIPE_WEBHOOK_SECRET` no (es propio de cada endpoint configurado en el Dashboard).

### Corrección de fondo: qué divisa y qué monto paga de verdad un cambio

El usuario pegó el resumen de un cambio real (500,00 EUR a USD, con tasas, comisión e "Importe a
recibir" de 559,16 USD) y preguntó, con razón, qué iba a figurar en Stripe. Al explicar el cálculo
completo (`_calcular_triangulacion`) quedó claro un problema de fondo heredado de GE-25: el sistema
cobraba siempre `monto_final` —que para un cambio es el "Importe a **recibir**"— en la divisa
**destino**. Es decir: para este ejemplo, Stripe le habría cobrado a la tarjeta 559,16 **USD**, el
mismo valor (y la misma moneda) que el cliente iba a recibir a cambio, sin que sus 500 EUR entraran
en la ecuación para nada.

Se le preguntó al usuario qué debía cobrarse (el equivalente en PYG, el monto de la divisa de
origen, o dejarlo como estaba) y eligió **el monto de la divisa de origen**: lo que el cliente
entrega, no lo que recibe. Se implementó de forma consistente para los dos medios de pago, no solo
Stripe:

- `apps.divisas.models.monto_a_pagar`/`moneda_a_pagar` (funciones nuevas, compartidas): para una
  compra/venta siguen siendo `monto_final`/PYG; para un cambio son `monto_origen`/
  `codigo_divisa_origen`.
- `apps.divisas.pagos_stripe._moneda_de_liquidacion` pasó a delegar en `moneda_a_pagar`, y los tres
  lugares que usaban `transaccion.monto_final` como monto a cobrar (el cobro directo, el fallback de
  Checkout y el webhook) pasaron a usar `monto_a_pagar`.
- El pago manual de GE-25 (`PagarTransaccionCambioView.post`, transferencia/billetera) se actualizó
  igual, para que un cambio registre el mismo monto sin importar el medio con el que se pagó.
- `detalle_transaccion_cambio.html` dejó de etiquetar el monto del pago con la divisa destino
  (ahora muestra la de origen, que es la que realmente corresponde); `pagar_transaccion_cambio.html`
  agregó una fila "Importe a pagar" junto a "Importe a recibir", para que la distinción quede clara
  en la propia pantalla y no dependa de que alguien lo explique.

Se agregó `MontoAPagarTest` en `tests/test_operaciones.py` (una compra/venta paga `monto_final` en
PYG; un cambio paga `monto_origen` en su divisa de origen) y se actualizaron las aserciones que
asumían lo contrario en `test_operaciones.py` y `test_pagos_stripe.py`. Suite completa: sin fallas
tras el fix.

## Sesión 12 — 11/10/2026 — Pago por transferencia bancaria vía SIPAP

**Herramienta:** Claude Code (Anthropic, modelo Sonnet 5)
**HU relacionada:** Pago por transferencia bancaria vía SIPAP
**Rama:** `feature/GE-22`
**Participantes:** Rodrigo Mereles, integrante del equipo Global Exchange

### Pedido

Implementar la HU "Pago por transferencia bancaria vía SIPAP", con tests, docstrings, Sphinx
actualizado y esta documentación de la conversación.

> Como usuario cliente quiero pagar mis operaciones cambiarias mediante transferencia desde mi
> cuenta bancaria, a través de SIPAP, para completar el pago sin necesidad de usar una tarjeta.

Criterios de aceptación:

1. Con una transacción "Confirmada", elegir pagar por transferencia SIPAP genera una solicitud de
   pago por el monto exacto, calculado por el sistema y no modificable, e indica cómo completar la
   transferencia con una referencia única.
2. Cuando SIPAP confirma que la transferencia fue acreditada, el sistema registra el pago como
   exitoso con el identificador de la operación SIPAP, el banco de origen y el medio
   "transferencia".
3. Si el monto transferido no coincide con el de la transacción, la transacción no pasa a "Pagada"
   y el pago queda registrado como observado, con la diferencia, para su revisión.
4. Una confirmación que no puede verificarse como emitida por SIPAP se rechaza sin modificar el
   estado de ninguna transacción.
5. Si la transferencia es rechazada o no se completa dentro del plazo de vigencia, la transacción
   permanece "Confirmada" y se informa al usuario, con opción de reintentar o de elegir otro medio.
6. Si SIPAP no responde o la conexión falla, el sistema no marca la transacción como pagada y
   muestra un mensaje de problema de comunicación, sin perder el estado de la transacción.

### Diagnóstico y diseño

SIPAP es el sistema de pagos interbancario del Banco Central del Paraguay: a diferencia de Stripe,
no tiene un sandbox público al que un proyecto académico pueda conectarse. En vez de bloquearse en
eso, se diseñó `apps.divisas.pagos_sipap` con su propio esquema de webhook (firma HMAC-SHA256 con
un secreto propio, `SIPAP_WEBHOOK_SECRET`) en vez de un SDK oficial — documentado explícitamente
como el punto a reemplazar si algún día se integra con el sistema real.

A diferencia de Stripe (cobro inmediato, por API o en una página de pago), una transferencia
bancaria real no es instantánea: el cliente sale del sistema, transfiere desde su banco, y la
confirmación llega después. Eso exigió dos piezas que GE-25/Stripe no necesitaron:

- **`apps.divisas.models.SolicitudPagoSipap`** (migración `0014`, junto con los dos campos de
  `Pago` de abajo): un registro de "pago pendiente" por transacción (`OneToOneField`, nunca dos
  solicitudes para la misma), con referencia única, monto/moneda esperados, estado (Pendiente /
  Acreditada / Observada / Rechazada / Vencida) y vencimiento. Reintentar después de una solicitud
  "Rechazada" o "Vencida" reutiliza la misma fila con una referencia nueva en vez de crear una
  segunda; una "Observada" no se reinicia sola, porque ya hay un pago real con un monto que no
  coincide, y eso necesita revisión humana antes de intentar de nuevo.
- **`Pago.observado`/`Pago.diferencia`** + **`Pago.registrar_pago_observado`** (classmethod
  nuevo, misma idempotencia por `(proveedor, identificador_externo)` que `registrar_pago`, pero sin
  marcar la transacción como "Pagada"): el criterio 3 exige un desenlace que ni Stripe ni el flujo
  manual necesitaban — un pago real, confirmado por el proveedor, pero por un monto que no es el
  esperado. Tiene sentido solo para SIPAP porque ahí el monto lo escribe el cliente a mano al
  transferir; Stripe, en cambio, siempre cobra exactamente lo que el propio sistema le pidió.

Como con Stripe/tarjeta, elegir un método guardado de tipo "transferencia" en la pantalla de pago
de siempre ahora redirige a SIPAP en vez de registrar el pago manualmente
(`PagarTransaccionOperacionView.post`/`PagarTransaccionCambioView.post`). Esto dejó "billetera"
como el único tipo sin una integración real todavía, y rompió varios tests de GE-25 que usaban
justamente un método de tipo "transferencia" para probar el registro manual inmediato: se
adaptaron para usar "billetera" en su lugar (el mismo ajuste que ya le había tocado a "tarjeta" en
la Sesión 11), y se agregó un test nuevo por pantalla confirmando la redirección a SIPAP.

El monto que se le pide al cliente transferir usa `apps.divisas.models.monto_a_pagar`/
`moneda_a_pagar` (los mismos agregados en la corrección de la Sesión 11): PYG para una
compra/venta, la divisa de **origen** para un cambio — la misma fuente de verdad que ya usa
Stripe, sin duplicar el cálculo.

### Tests

`tests/test_pagos_sipap.py` (31 tests nuevos): generación de referencias únicas, verificación de
firma HMAC (válida/inválida/ausente), `_registrar_solicitud_en_sipap` (sin URL configurada no
llama a nadie; con URL y éxito no rompe nada; con URL y fallo de red levanta
`SipapComunicacionError`), vencimiento perezoso de una solicitud (vigente, vencida, ya resuelta no
se toca), `Pago.registrar_pago_observado` (crea con `observado=True` y la diferencia sin marcar
pagada, idempotente, rechaza si no está "Confirmada" o ya está "Pagada"), inicio del pago para
compra/venta y para cambio (monto y moneda correctos, reutiliza la solicitud pendiente al
revisitar, no permite pagar si no está confirmada, problema de comunicación no crea nada, una
vencida se reinicia con referencia nueva, una observada no se reinicia sola, control de rol) y el
webhook completo (firma inválida, acreditada con monto exacto marca pagada, acreditada con monto
distinto queda observada sin marcar pagada, rechazada no crea nada, referencia desconocida no
rompe, reenvío del mismo evento no duplica, payload no-JSON, método distinto de POST). Se
actualizaron además los tests de GE-25 afectados por la redirección nueva en
`tests/test_operaciones.py`.

### Resultado final

- Suite completa: sin fallas tras agregar la HU.
- `manage.py check` y `makemigrations --check`: sin problemas.
- Sphinx recompilado con `-W` (a un directorio temporal): sin advertencias. Se agregó
  `reference/apps.divisas.pagos_sipap.rst` (enlazado desde `reference/apps.divisas.rst`), se
  documentó `SolicitudPagoSipap` en `reference/apps.divisas.models.rst`, y se agregó la sección
  "Pago por transferencia bancaria vía SIPAP" en `guia.rst`, corrigiendo de paso varias menciones
  desactualizadas ("para transferencia o billetera, el registro sigue siendo inmediato") que había
  dejado la Sesión 11.
- Nueva plantilla `templates/divisas/pagar_transaccion_sipap.html` con las instrucciones de
  transferencia (banco destino, cuenta, referencia, monto, vencimiento).
- Variables de entorno nuevas (todas opcionales, con default vacío o un valor de relleno):
  `SIPAP_API_URL`, `SIPAP_WEBHOOK_SECRET`, `SIPAP_BANCO_DESTINO`, `SIPAP_CUENTA_DESTINO`, agregadas
  a `.env.example` y `.env.prod.example`.

### Pendiente / fuera de alcance

- No hay integración real con el BCP: `SIPAP_API_URL` queda vacía por defecto y
  `sipap_webhook_view` espera un payload con el formato propio de este módulo, no el de un sistema
  real (que esta sesión no tuvo forma de conocer).
- No se construyó ninguna pantalla para que un analista/administrador revise y resuelva un pago
  "Observado" manualmente; la HU pide que quede registrado para revisión, no que exista un flujo de
  resolución.
- Igual que con una tarjeta, no hay forma de simular un evento `"ACREDITADA"`/`"RECHAZADA"` real
  desde la UI en desarrollo (no hay un "SIPAP CLI" como el de Stripe): probar el webhook a mano
  requiere armar y firmar el payload por fuera del sistema (ver los tests para el formato exacto).

## Sesión 13 — 11/10/2026 — sipap-sim y billeteras digitales

**Herramienta:** Claude Code (Anthropic, modelo Sonnet 5)
**HU relacionada:** Pago por transferencia bancaria vía SIPAP (continuación de la Sesión 12) +
simulación de billeteras digitales
**Rama:** `feature/GE-77`
**Participantes:** Rodrigo Mereles, integrante del equipo Global Exchange

### Pedido

> no voy a tener un acceso a la api de sipap al parecer asi que simulalo y tambien simula
> billeteras digitales

seguido de la especificación completa de "sipap-sim": un proyecto Django independiente que
representa la red bancaria (bancos, cuentas de 16 dígitos, transferencias con estado), con su
propia API (`solicitudes-cobro`, `transferencias`, `cuentas/validar`, todas con
`Authorization: Bearer <SIPAP_API_KEY>`), una "banca en línea" simulada donde el cliente elige una
cuenta y aprueba o rechaza (pudiendo cambiar el monto, para el caso del monto que no coincide),
webhooks firmados con HMAC-SHA256 hacia Global Exchange, una variable `SIM_MODO_FALLA` para probar
errores de comunicación, y un despliegue como contenedor aparte (desarrollo: `runserver` en el
puerto 8001; producción: un servicio más en `deploy/aws/docker-compose.yml`, servido por Nginx en
`/sipap/`, con su propia base en el mismo RDS). Pedido explícito: el lado de Global Exchange "casi
no cambia" — el adaptador deja de simular internamente y pasa a ser un cliente HTTP real. Y, en la
misma línea, agregar billeteras digitales al mismo simulador.

### Diagnóstico y diseño

La Sesión 12 había implementado `apps.divisas.pagos_sipap` simulando SIPAP *por dentro* (sin
llamar a nadie si `SIPAP_API_URL` estaba vacía, el caso por defecto). Esta sesión construyó el
simulador real como proyecto aparte y reemplazó esa simulación interna por un cliente HTTP.

**`sipap_sim/`** (proyecto Django nuevo, independiente, con su propio `manage.py`, `settings.py` y
`pytest.ini`): tres modelos en la app `core` —

- `ProveedorPago` (bancos y billeteras bajo la misma clase, a propósito: para la "banca en línea" y
  para Global Exchange, pagar desde un banco o desde una billetera es el mismo flujo — elegir una
  cuenta propia y aprobar — así que no hacía falta duplicar nada para "agregar billeteras").
- `Cuenta` (número, proveedor, titular, documento, moneda, saldo, y un flag
  `es_cuenta_casa_de_cambio` para la cuenta destino de cualquier solicitud).
- `Transferencia` (nace "Pendiente" sin `cuenta_origen`, que se completa solo cuando el cliente
  elige una cuenta en la "banca en línea"; vencimiento perezoso con el mismo patrón que
  `CalculoOperacion.marcar_vencida_si_corresponde`).

La API (`core/views.py`) implementa los cuatro endpoints de la especificación, con
`SIM_MODO_FALLA` (`"error"` → 500; `"lento"` → `time.sleep(15)`, más que cualquier timeout
razonable del lado de Global Exchange) revisado antes de procesar nada. La "banca en línea"
(`elegir_cuenta_view`, sin autenticación: la usa el cliente desde su navegador, no Global Exchange)
deja elegir cualquier cuenta de prueba en la moneda solicitada y, a propósito, cambiar el monto
antes de aprobar — el mecanismo para probar el caso del monto que no coincide. Al resolverse
(aprobada o rechazada), `core/webhooks.enviar_confirmacion` firma y manda la confirmación a Global
Exchange, y redirige al cliente a la `url_retorno` que mandó la solicitud original. Una migración
de datos (`0002_datos_iniciales`) carga los cuatro bancos de la especificación (Itaú, Continental,
Ueno, Familiar), tres billeteras inventadas (Tigo Money, Billetera Personal, Zimple), las cuentas
de la casa de cambio (una por moneda) y varias cuentas de clientes de prueba.

**Del lado de Global Exchange**, `apps.divisas.pagos_sipap._registrar_solicitud_en_sipap` se
reemplazó por `_crear_solicitud_cobro_en_sipap`: un `POST` real a
`{SIPAP_BASE_URL}/api/solicitudes-cobro/` con `Authorization: Bearer {SIPAP_API_KEY}`, que guarda
en la solicitud el `id_externo`/`link_pago` que devuelve sipap-sim (dos campos nuevos en
`SolicitudPagoSipap`, migración `0015`); `IniciarPagoSipapOperacionView`/`...CambioView.get` ya no
renderiza una página local con instrucciones de transferencia — redirige directo a ese
`link_pago`, igual que un Checkout externo. `_procesar_confirmacion_sipap` se adaptó al formato
exacto del payload de la especificación: `estado` en minúsculas (`"acreditada"`/`"rechazada"`, no
`"ACREDITADA"`/`"RECHAZADA"`) y `monto` como número JSON, no como string.

Para las billeteras digitales, en vez de un segundo adaptador se decidió que
`MetodoPago.TIPO_BILLETERA` comparta el mismo flujo que `TIPO_TRANSFERENCIA`: sipap-sim ya simula
ambas con la misma `Cuenta`/`Transferencia`. Esto requirió un tercer campo nuevo en
`SolicitudPagoSipap`, `medio_pago` (para que el `Pago` resultante muestre "Billetera Digital" y no
siempre "Transferencia Bancaria"), que la vista fija a partir de un `?tipo_medio=` que ahora manda
`PagarTransaccionOperacionView.post`/`...CambioView.post` al redirigir a SIPAP — y que
`_procesar_confirmacion_sipap` usa en vez del tipo hardcodeado. Con esto, el branching de esas dos
vistas quedó en dos casos (tarjeta → Stripe; transferencia o billetera → SIPAP), sin ningún caso
restante que registrara el pago "a mano": se eliminó esa rama muerta y los imports que quedaron sin
uso (`Pago`, `PagoRechazadoError`, `monto_a_pagar` en `apps.divisas.views`).

### Tests

`sipap_sim/tests/` (24 tests nuevos, suite independiente): los cuatro endpoints de la API
(autenticación, creación de solicitud, consulta de estado, validación de cuenta, transferencia
saliente, `SIM_MODO_FALLA` en sus dos variantes), la "banca en línea" (aprobar mueve saldo y
redirige, aprobar con un monto distinto simula el caso de monto que no coincide, rechazar no mueve
saldo, saldo insuficiente no se permite, una transferencia ya resuelta o vencida no se puede volver
a aprobar) y el webhook (formato del cuerpo, firma HMAC válida, una falla de red no rompe al
llamador). Se usan los datos de la migración de siembra en vez de crear proveedores/cuentas
propios, para no chocar con las restricciones de unicidad que esa migración ya carga en la base de
test.

`tests/test_pagos_sipap.py`: se reescribió `RegistrarSolicitudEnSipapTest` como
`CrearSolicitudCobroEnSipapTest` (URL y encabezado correctos, guarda `id`/`link_pago`, una
respuesta de error o no-JSON también cuenta como falla de comunicación); las pruebas de
`IniciarPagoSipap*View` ahora mockean `_crear_solicitud_cobro_en_sipap` (en vez de hacer una
llamada real) y verifican la redirección al `link_pago`, además de un caso nuevo para
`?tipo_medio=BILLETERA`; el webhook se probó con `estado` en minúsculas y `monto` numérico, más un
caso nuevo confirmando que una confirmación de billetera registra el pago como billetera, no como
transferencia.

`tests/test_operaciones.py`: los tests de GE-25 que usaban "billetera" como el único tipo que
registraba manualmente (de la Sesión 12) ya no aplican — ahora billetera también redirige a SIPAP.
Se agregó un test de redirección para billetera (simétrico al de transferencia, con
`?tipo_medio=BILLETERA`), se adaptaron las aserciones de redirección existentes para incluir ese
query string, se eliminó el test de "doble envío no duplica" (la premisa, un registro manual
inmediato, ya no existe para ningún medio) y las pruebas de "el detalle muestra el pago" pasaron a
registrar el pago directamente (simulando la confirmación asíncrona) en vez de esperar que el POST
lo registrara.

### Resultado final

- Suite principal: 350 tests, sin fallas. Suite de sipap-sim (independiente): 24 tests, sin
  fallas. `manage.py check` y `makemigrations --check`: sin problemas en ambos proyectos.
- Sphinx recompilado con `-W`: sin advertencias (`docs/build/` regenerado). Se actualizó la sección
  "Pago por transferencia bancaria o billetera digital vía SIPAP" en `guia.rst`, el `.rst` de
  referencia de `pagos_sipap` (la función renombrada) y `sipap_sim/README.md` documenta la API y el
  simulador por separado (no se integró al árbol de Sphinx de Global Exchange: es un proyecto
  Django aparte, igual que Keycloak).
- `pytest.ini` de la raíz acotado a `testpaths = tests` para que no intente correr los tests de
  `sipap_sim/` contra el `DJANGO_SETTINGS_MODULE` equivocado.
- `global_exchange/settings/base.py`: `SIPAP_API_URL`/`SIPAP_BANCO_DESTINO`/`SIPAP_CUENTA_DESTINO`
  reemplazadas por `SIPAP_BASE_URL`/`SIPAP_API_KEY` (la cuenta destino ahora la decide sipap-sim,
  no Global Exchange); `.env.example`/`.env.prod.example` actualizados.
- `deploy/aws/docker-compose.yml`: servicio `sipap-sim` nuevo (mismo patrón que `keycloak`: su
  propio contenedor, su propia base `sipap_sim` en el mismo RDS); `deploy/aws/nginx/nginx.conf`:
  `location /sipap/` que le quita el prefijo antes de reenviar (`FORCE_SCRIPT_NAME` del lado de
  sipap-sim se lo vuelve a agregar al generar URLs).
- Se eliminó `templates/divisas/pagar_transaccion_sipap.html`: la vista ya no renderiza
  instrucciones locales, redirige directo a la "banca en línea" de sipap-sim.

### Pendiente / fuera de alcance

- `POST /api/transferencias/` (que la casa de cambio le pague a un cliente) está implementado en
  sipap-sim según la especificación, pero Global Exchange todavía no lo llama: es la HU de
  acreditación/retiro de fondos de Sprint 5, fuera de alcance de esta sesión.
- No se armó ningún `docker-compose.yml` de desarrollo para levantar sipap-sim junto a Global
  Exchange con un solo comando; en desarrollo se corre a mano (`runserver 8001`), como permite la
  especificación.
- Los nombres de las billeteras digitales (Tigo Money, Billetera Personal, Zimple) y los datos de
  los clientes de prueba son de relleno: la especificación solo fijaba los bancos y la forma de las
  cuentas, no qué billeteras ni qué clientes simular.

## Sesión 14 — 11/10/2026 — Validación real de cuentas en "Métodos de pago" (GE-19)

**Herramienta:** Claude Code (Anthropic, modelo Sonnet 5)
**HU relacionada:** Métodos de pago (GE-19), apoyándose en sipap-sim (Sesión 13)
**Rama:** `feature/GE-77`
**Participantes:** Rodrigo Mereles, integrante del equipo Global Exchange

### Pedido

> modifica la pantalla de metodos de pago para que quede todo bien implementado y puedas ingresar
> bien los datos de tu cuenta bancaria o billetera digital y que tenga concordancia con el mundo
> real

### Diagnóstico y diseño

La pantalla de alta de un método de transferencia o billetera (`apps.clientes.forms.MetodoPagoForm`)
dejaba escribir cualquier cosa: el cliente tipeaba un "banco" de relleno y un número de cuenta sin
que nada los verificara, y una billetera digital no pedía ningún dato de cuenta en absoluto (ni
siquiera un número) — el formulario solo mostraba "Billetera digital" genérico en el listado. Con
sipap-sim ya funcionando (Sesión 13), esto tenía arreglo real: su especificación ya incluía
`GET /api/cuentas/validar/?numero=...&documento=...` "para verificar que una cuenta exista y sea del
titular indicado, antes de registrarla en Global Exchange" — un endpoint que quedó construido pero
nunca llamado por nadie. Esta sesión lo conectó.

Diseño elegido: el cliente ya no escribe el nombre del titular ni el banco/billetera — los completa
`clean()` a partir de lo que confirma sipap-sim, igual que un alta real de cuenta bancaria (no se le
cree al usuario que una cuenta es suya solo porque lo escribió). Lo que el cliente sí ingresa es el
número de cuenta/billetera y su CI o RUC (campo `documento_titular`, nuevo en `MetodoPago`, migración
`0017`); con esos dos datos, `apps.clientes.validacion_sipap.validar_cuenta` (módulo nuevo) consulta a
sipap-sim y, si la cuenta existe y el documento coincide, devuelve el titular real y el proveedor
(banco o billetera) — datos con los que `MetodoPagoForm.clean()` completa `self.instance` antes de
guardar. Si sipap-sim dice que la cuenta no existe, o no responde, no se guarda nada: se rechaza el
alta con un mensaje, en vez de confiar en datos sin verificar.

Este módulo se puso en `apps.clientes` (no en `apps.divisas.pagos_sipap`, que ya habla con
sipap-sim) a propósito: la dirección de dependencia entre esas dos apps ya era
`apps.divisas → apps.clientes` (`pagos_sipap`/`pagos_stripe` importan de `apps.clientes.models`), y
hacerla depender al revés para esto habría invertido esa capa sin necesidad — es una verificación de
datos al registrar el método (GE-19), no parte de cobrar una transacción.

Para que la respuesta de `validar_cuenta` tuviera algo más que ofrecer que un simple `true`/`false`,
se extendió el endpoint correspondiente de **sipap-sim** (`sipap_sim/core/views.py`) para devolver
también `titular`, `proveedor`, `tipo_proveedor` y `moneda` cuando la cuenta es válida — en vez de
limitarse a lo mínimo que pedía la especificación original.

`tipo_cuenta` (caja de ahorro / cuenta corriente) se mantuvo exclusivo de transferencia: una
billetera digital no tiene ese concepto en el mundo real, así que ni el formulario lo exige ni la
pantalla lo muestra para ese tipo.

### Verificación de punta a punta

Antes de dar por terminado, se corrieron ambos servidores de desarrollo de verdad (sipap-sim en el
8001, Global Exchange en el 8000, sin mockear nada) y se probaron tres casos reales: una cuenta
bancaria existente (se guardó con el titular y el banco reales, tomados de sipap-sim, no de lo que
se mandó en el POST), una billetera digital existente (mismo resultado, con "Tigo Money" como
proveedor) y una cuenta inexistente (no se guardó ningún `MetodoPago`). Los tres se comportaron como
se esperaba.

### Tests

`tests/test_metodos_pago.py`: se adaptó `test_registro_metodo_pago_exitoso` para mockear
`validar_cuenta` y verificar que el titular y la entidad financiera queden tomados de esa respuesta,
no del POST; se actualizó el mensaje de `test_validacion_campos_incompletos` y se agregó la
validación de `documento_titular`; se agregaron `test_rechaza_una_cuenta_que_no_existe_en_sipap`
(`valida: False` → rechaza sin guardar), `test_no_guarda_nada_si_sipap_sim_no_responde`
(`SipapComunicacionError` → rechaza con un error no asociado a ningún campo) y
`test_billetera_no_exige_tipo_de_cuenta`. Los tests que crean un `MetodoPago` directo con
`objects.create(...)` (sin pasar por el formulario) no necesitaron cambios: `documento_titular` es
opcional a nivel de modelo, igual que ya lo eran `numero_cuenta`/`tipo_cuenta`.

`sipap_sim/tests/test_api.py`: se actualizó `ValidarCuentaTest` para el nuevo cuerpo de respuesta
(titular, proveedor, tipo de proveedor y moneda cuando la cuenta es válida).

### Resultado final

- Suite principal: 353 tests, sin fallas (subía de 350 a 353 con los tres tests nuevos). Suite de
  sipap-sim: 24 tests, sin fallas. `manage.py check`/`makemigrations --check` limpios en ambos
  proyectos.
- Sphinx recompilado con `-W`: sin advertencias (`docs/build/` regenerado); se agregó
  `reference/apps.clientes.validacion_sipap.rst` al árbol de referencia de `apps.clientes`.
- Plantillas actualizadas: `metodo_pago_form.html` ya no pide "Entidad Financiera" ni "Nombre del
  Titular" (se completan solos), agrega "CI o RUC del Titular", y el tipo de cuenta se oculta por JS
  cuando el medio elegido es billetera; `metodo_pago_list.html` muestra el CI/RUC enmascarado (mismo
  patrón que el número de cuenta) y ya no tiene una rama "Billetera digital" genérica e inalcanzable.
- Se le dio al usuario, en el chat, una guía paso a paso para levantar y configurar los tres
  servicios (Global Exchange, sipap-sim, y Keycloak si aplica) en desarrollo y en el servidor de AWS.

### Pendiente / fuera de alcance

- La lista de proveedores (bancos y billeteras) que puede devolver sipap-sim sigue siendo la que
  carga su migración de datos de siembra; si se agregan más proveedores ahí, el formulario de Global
  Exchange los acepta sin ningún cambio (no depende de una lista propia).
- No se agregó un selector de moneda en el método de pago: la moneda de la cuenta la informa
  sipap-sim en la validación pero no se persiste en `MetodoPago` — no hace falta hoy porque el flujo
  de pago (vía la "banca en línea" de sipap-sim) no usa el método de pago registrado para decidir con
  qué cuenta se paga, el cliente la elige ahí en el momento.

  > **Nota de la Sesión 15:** esta última limitación se cerró en la sesión siguiente — el método de
  > pago registrado pasó a ser justamente lo que decide con qué cuenta se paga.

## Sesión 15 — 12/10/2026 — sipap-sim reconoce la cuenta del método de pago elegido

**Herramienta:** Claude Code (Anthropic, modelo Sonnet 5)
**HU relacionada:** Pago por transferencia bancaria vía SIPAP / Métodos de pago (GE-19), continuación
de las Sesiones 13 y 14
**Rama:** `feature/GE-77`
**Participantes:** Rodrigo Mereles, integrante del equipo Global Exchange

### Pedido

> el sipap simulado tiene que cargar automaticamente los datos seleccionados en el menu de pago del
> sistema, si se elegio tal metodo de pago, tiene que reconocerlo y tambien el monto ya tiene que
> estar seleccionado sin poder cambiar, tambien tiene que mostrarte cuando saldo disponible tenes en
> ese metodo de pago seleccionado y dar un mensaje de fondos insuficientes en tal caso, el sistema de
> sipap simulado tiene que reconocer solo los metodos de pago que estan registrados en el cliente de
> un usuario, y no mostrar todos los metodos de pago del sistema

### Diagnóstico y diseño

Hasta esta sesión, `IniciarPagoSipapOperacionView`/`...CambioView` solo le mandaban a sipap-sim
`monto`, `moneda`, `referencia` y `url_retorno` — nunca le decían con qué cuenta puntual iba a pagar
el cliente, pese a que el cliente ya había elegido un `MetodoPago` específico en el formulario de
pago de siempre (`PagarTransaccionForm.metodo_pago`, un `ModelChoiceField`, no solo un tipo). La
consecuencia: la "banca en línea" de sipap-sim (`elegir_cuenta_view`) mostraba un `<select>` con
**todas** las cuentas de prueba del sistema, de cualquier cliente — justo lo que el pedido señala
como incorrecto.

La solución, mirando cómo ya resuelve esto `apps.divisas.pagos_stripe` (que sí sabe, desde el
principio, con qué tarjeta puntual se cobra): replicar el mismo patrón para SIPAP.

- **Del lado de Global Exchange**: `apps.divisas.views.PagarTransaccionOperacionView.post`/
  `...CambioView.post` pasan a redirigir con `?metodo_pago={pk}` (antes `?tipo_medio=`, que solo
  decía "transferencia" o "billetera" sin decir cuál). `apps.divisas.pagos_sipap` ganó
  `_resolver_metodo_pago_sipap` (mismo patrón que `_resolver_metodo_pago_tarjeta` de Stripe): busca
  el `MetodoPago` del cliente, de tipo transferencia o billetera, con número de cuenta y CI/RUC
  completos — que siempre los tiene, porque `apps.clientes.forms.MetodoPagoForm` ya los validó
  contra sipap-sim al registrarlo (Sesión 14). `SolicitudPagoSipap` ganó un campo `metodo_pago`
  (FK, migración `0016`), y `_crear_solicitud_cobro_en_sipap` manda ese número de cuenta y documento
  a sipap-sim junto con el resto de la solicitud.
- **Del lado de sipap-sim**: `Transferencia` ganó `cuenta_sugerida` (FK, migración `0004`):
  `crear_solicitud_cobro` la resuelve a partir de `cuenta_origen_numero`/`cuenta_origen_documento`,
  si vienen en el body (400 si vienen pero no corresponden a ninguna cuenta real — una solicitud sin
  una cuenta válida no es un estado que debería poder crearse). `elegir_cuenta_view` se reescribió
  por completo: ya no filtra `Cuenta.objects.filter(moneda=...)` para armar un selector — usa
  directamente `transferencia.cuenta_sugerida`, muestra su saldo disponible, y si no hay ninguna
  cuenta sugerida (una solicitud armada sin esos datos, p. ej. a mano contra la API), no ofrece
  ninguna lista como respaldo: devuelve un error (plantilla `sin_cuenta.html`, 409) en vez de filtrar
  datos de otros clientes de prueba.

Sobre "el monto ya tiene que estar seleccionado sin poder cambiar": esto entra en tensión directa
con un criterio de aceptación de la propia especificación de sipap-sim pasada en una sesión anterior
("también puede elegir un monto distinto, para probar el caso del monto que no coincide" — Sesión 13,
criterio 3). La resolución elegida, sin pedirle al usuario que decidiera entre las dos: el monto
queda fijo y de solo lectura por defecto (lo que pide este pedido), con un checkbox explícito
("simular un monto distinto, para pruebas") que, marcado, lo habilita — así la capacidad de probar el
criterio 3 sigue existiendo, pero ya no es el comportamiento por defecto ni algo que un cliente real
activaría sin querer. Si el usuario prefiere que se quite del todo, es un cambio de una línea en
`elegir_cuenta_view`/la plantilla.

El mensaje de "fondos insuficientes" ya existía desde la Sesión 13 (comparaba el saldo de la cuenta
elegida por el `<select>` contra el monto); con el rediseño, se comparó directamente contra
`cuenta_sugerida.saldo`, sin otro cambio funcional.

### Verificación de punta a punta

Se levantaron los dos servidores reales (Global Exchange en 8000, sipap-sim en 8001) y se corrió el
flujo completo sin mockear nada: crear un `MetodoPago` de transferencia con una cuenta real
(`2000000000000101`, Juan Pérez), iniciar el pago de una compra "Confirmada", confirmar que la
"banca en línea" de sipap-sim muestra esa cuenta puntual (sin ningún `<select>` de por medio),
aprobar la transferencia ahí, y confirmar que el webhook de vuelta marcó la transacción como
"Pagada" en Global Exchange, con el `Pago` resultante vinculado al `MetodoPago` correcto
(`pago.metodo_pago_id` coincide con el elegido).

### Tests

`sipap_sim/tests/test_api.py`: `ValidarCuentaTest` sin cambios; se agregaron
`test_con_cuenta_de_origen_la_identifica_como_cuenta_sugerida` y
`test_rechaza_si_la_cuenta_de_origen_indicada_no_existe` a `CrearSolicitudCobroTest`.

`sipap_sim/tests/test_banca_en_linea.py`: reescrito para el nuevo flujo sin selector —
`test_muestra_la_cuenta_identificada_y_su_saldo` (ya no un listado), `test_aprobar_sin_marcar_el_checkbox_ignora_un_monto_distinto_en_el_pedido`
(nuevo, confirma que el monto queda fijo por defecto), `test_aprobar_con_monto_distinto_simula_el_caso_de_monto_que_no_coincide`
(ahora requiere marcar el checkbox), y `test_sin_cuenta_sugerida_no_muestra_ninguna_cuenta_del_sistema`
(nuevo: confirma el 409 en vez de una lista de respaldo).

`tests/test_pagos_sipap.py`: se agregó un `MetodoPago` de prueba (con cuenta y documento) a cada
fixture que antes solo pasaba `?tipo_medio=`; se agregó `test_sin_metodo_de_pago_valido_no_crea_ninguna_solicitud`
y se renombró/ajustó `test_tipo_medio_billetera_se_guarda_en_la_solicitud` a
`test_billetera_se_guarda_en_la_solicitud` (ahora con un segundo `MetodoPago` de billetera real). El
test del webhook ahora verifica también que `pago.metodo_pago` quede vinculado a la solicitud.

`tests/test_operaciones.py`: las aserciones de redirección (`?tipo_medio=...`) de
`PagarTransaccionOperacionTest`/`PagarTransaccionCambioTest` pasaron a esperar `?metodo_pago={pk}`.

### Resultado final

- Suite principal: sin fallas. Suite de sipap-sim: 28 tests (4 nuevos), sin fallas. `manage.py check`
  y `makemigrations --check` limpios en ambos proyectos.
- Sphinx recompilado con `-W`: sin advertencias (`docs/build/` regenerado). Se actualizó la sección
  de SIPAP en `guia.rst` y el `.rst` de referencia de `pagos_sipap` (nueva función), y
  `sipap_sim/README.md` describe el nuevo comportamiento de la API y de la "banca en línea".

### Pendiente / fuera de alcance

- `crear_solicitud_cobro` responde 400 si le mandan una cuenta de origen que no existe, en vez de
  crear la solicitud sin `cuenta_sugerida` como respaldo — una decisión deliberada (ver diagnóstico),
  pero significa que un error de sincronización entre las dos bases (poco probable, dado que Global
  Exchange ya valida la cuenta al registrar el método) bloquearía el pago en vez de degradarlo.
- El checkbox "simular un monto distinto" queda expuesto en la propia pantalla de "banca en línea",
  visible para cualquiera que la abra — aceptable en un simulador de desarrollo, pero es justo el
  tipo de control que en un entorno real no debería existir ahí.

  > **Nota de la Sesión 16:** ese checkbox se quitó en la sesión siguiente, a pedido explícito.

## Sesión 16 — 12/10/2026 — sipap-sim deja de pedir el monto a transferir

**Herramienta:** Claude Code (Anthropic, modelo Sonnet 5)
**HU relacionada:** Pago por transferencia bancaria vía SIPAP, continuación directa de la Sesión 15
**Rama:** `feature/GE-77`
**Participantes:** Rodrigo Mereles, integrante del equipo Global Exchange

### Pedido

> que no pida monto a transferir, que directo cargue el monto solicitado si es que la tarjeta tiene
> los fondos suficientes y tu solo aceptes si es que quieres realizar el pago con la cuenta
> bancaria/billetera digital

Resuelve, en el sentido que pedía que se eligiera, la tensión que había quedado anotada al cierre de
la Sesión 15 entre "el monto no se debería poder cambiar" y el criterio 3 de la especificación
original de sipap-sim ("también puede elegir un monto distinto, para probar ese caso"): esta sesión
quita esa capacidad de la "banca en línea" por completo, sin que el usuario tuviera que decidir entre
las dos — ya lo pidió explícitamente.

### Diagnóstico y diseño

Cambio acotado sobre lo que dejó armado la Sesión 15: `core.views.elegir_cuenta_view` ya no lee
``monto``/``simular_monto_distinto`` del `POST` — al aprobar, usa siempre
`transferencia.monto_solicitado` directamente, sin ninguna rama condicional. La plantilla
`elegir_cuenta.html` perdió el `<input type="number">` y el checkbox: el monto se muestra como texto
de solo lectura, junto a la cuenta reconocida y su saldo disponible (sin cambios en esa parte,
Sesión 15), y el formulario quedó reducido a dos botones, "Aprobar" y "Rechazar".

El mensaje de "fondos insuficientes" no cambió en su lógica (compara `cuenta_origen.saldo` contra el
monto a acreditar), solo que ese monto ya no puede ser otra cosa que `monto_solicitado`.

Esto significa que la "banca en línea" ya no tiene ninguna forma de producir, desde su propia
pantalla, un evento ``"acreditada"`` con un monto que no coincide (criterio 3 de la HU de pago por
SIPAP) — pero esa pieza del lado de Global Exchange (`apps.divisas.pagos_sipap._procesar_confirmacion_sipap`)
sigue intacta y sigue probada: `tests/test_pagos_sipap.py::SipapWebhookTest.test_acreditada_con_monto_distinto_queda_observada_sin_marcar_pagada`
le manda el webhook directamente con un monto distinto, sin pasar por la UI de sipap-sim en absoluto.
Es decir, el comportamiento que importa (qué hace Global Exchange si alguna vez recibe una
confirmación con un monto que no coincide, sea por el motivo que sea) sigue cubierto; lo que se quitó
es solo el botón para fabricar esa situación a mano desde el simulador.

### Tests

`sipap_sim/tests/test_banca_en_linea.py`: `test_aprobar_sin_marcar_el_checkbox_ignora_un_monto_distinto_en_el_pedido`
se renombró a `test_aprobar_ignora_cualquier_monto_que_mande_el_cliente` (ya no depende de ningún
checkbox: cualquier `monto` que venga en el `POST` se ignora igual). Se eliminó
`test_aprobar_con_monto_distinto_simula_el_caso_de_monto_que_no_coincide` (el escenario que probaba
ya no existe). `test_no_permite_aprobar_con_saldo_insuficiente` se reescribió para armar una
transferencia cuyo `monto_solicitado` ya supera el saldo de la cuenta, en vez de simular un monto
inflado por `POST` (que ya no es posible).

### Resultado final

- Suite de sipap-sim: 27 tests (uno menos que la Sesión 15, por el test eliminado), sin fallas.
  Suite principal sin cambios de comportamiento esperados (no dependía de este detalle de UI).
  `manage.py check`/`makemigrations --check` limpios en ambos proyectos; nueva migración
  `core.0005_alter_transferencia_monto_acreditado` (solo un `help_text` actualizado).
- Verificado a mano contra el sipap-sim real: la pantalla de "banca en línea" muestra el monto
  solicitado como texto fijo (sin ningún campo editable), la cuenta reconocida con su saldo, y
  únicamente los botones "Aprobar"/"Rechazar".
- Se actualizaron los docstrings de `Transferencia`/`monto_acreditado` en `sipap_sim/core/models.py`,
  `sipap_sim/README.md`, `docs/source/guia.rst` y el docstring de módulo de `apps.divisas.pagos_sipap`
  para reflejar que el monto ya no es editable desde la "banca en línea". Sphinx recompilado con
  `-W`, sin advertencias (`docs/build/` regenerado).

### Pendiente / fuera de alcance

- No queda, dentro de este repositorio, ninguna forma de disparar el caso "monto que no coincide" de
  punta a punta (UI de sipap-sim → webhook → `Pago` observado): solo a nivel del webhook directamente
  (que es donde ya estaba probado). Si en algún momento hiciera falta una demostración de punta a
  punta para QA manual, haría falta un mecanismo separado (p. ej. un comando de gestión o un endpoint
  de sipap-sim pensado explícitamente para pruebas, distinto de la pantalla que ve el cliente).

## Sesión 17 — 11/10/2026 — Gestión de operaciones en ventanilla

**Herramienta:** Claude Code (Anthropic, modelo Sonnet 5)
**HU relacionada:** Gestión de operaciones en ventanilla
**Rama:** `develop`
**Participantes:** Ruth, integrante del equipo Global Exchange

### Pedido

Implementar la HU "Gestión de operaciones en ventanilla", con tests, docstrings, Sphinx
actualizado y esta documentación de la conversación.

> Como cajero quiero registrar las operaciones de compra y venta de divisas realizadas en
> efectivo para mantener actualizado el saldo de la caja.

Criterios de aceptación:

1. Dado que tengo una caja abierta, cuando registro una operación de compra o venta en
   efectivo (reutilizando el cálculo de cotización ya existente), entonces el saldo de la
   caja se actualiza según la divisa y el sentido de la operación: ingresa lo que el cliente
   entrega y egresa lo que el cajero entrega.
2. Dado que no tengo una caja abierta, cuando intento registrar una operación de ventanilla,
   entonces el sistema rechaza la acción e indica que debo abrir una caja primero.
3. Dado que el saldo de la moneda que el cajero debe entregar es insuficiente (la divisa en
   una venta, guaraníes en una compra), cuando intento registrar la operación, entonces el
   sistema la rechaza e informa el motivo.
4. Dado que registro una operación en ventanilla, cuando se guarda, entonces queda vinculada
   a la caja activa y al cajero, con la tasa y la comisión aplicadas y los montos de ambas
   monedas.

### Diagnóstico inicial

El proyecto ya tenía todo lo necesario para reutilizar en vez de duplicar: `apps.caja.models.Caja`
y `SaldoInicialCaja` (HU "Apertura de Caja", Sesión 10) para el saldo inicial por moneda, y
`apps.divisas.views._calcular_importe_operacion` para el cálculo de tasa y comisión que ya usa el
flujo online del cliente (`CalculoOperacionView`). No existía, en cambio, ningún concepto de "saldo
actual" de una caja (solo el saldo inicial contado al abrir) ni ningún modelo de operación de
ventanilla — había que diseñar ambos desde cero.

Una decisión de nombres resultó más sutil de lo esperado: el Criterio 3 describe "la divisa en una
venta, guaraníes en una compra" como lo que el cajero debe entregar. Eso implica que, en esta HU,
"Compra" significa que **la casa le compra divisa al cliente** (perspectiva del cajero/casa de
cambio) — exactamente lo opuesto a `apps.divisas.models.CalculoOperacion.TIPO_COMPRA`, que significa
que el cliente compra divisa (perspectiva del cliente, usada en el flujo online). Confundir ambas
convenciones habría invertido silenciosamente qué moneda entra y cuál sale en cada caso, así que la
inversión quedó documentada explícitamente en el docstring del modelo nuevo en vez de dejarla
implícita.

### Diseño

- **`apps.caja.models.OperacionVentanilla`** (nuevo): UUID, `caja` y `cajero` (vínculo explícito a
  ambos, tal como pide el Criterio 4, aunque `caja.usuario` ya identifica al cajero), `tipo`
  (`COMPRA`/`VENTA`, con el significado invertido respecto de `CalculoOperacion` explicado arriba),
  `divisa`, `monto_divisa`, `tasa_aplicada`, `comision_porcentaje`, `comision` y `monto_pyg` (el
  monto final en guaraníes, equivalente a `CalculoOperacion.monto_final`).
- **`Caja.saldo_actual(divisa)`** (nuevo): en vez de agregar un campo mutable que haya que
  mantener sincronizado en cada operación, el saldo se deriva de forma perezosa —mismo patrón que
  `CalculoOperacion.estado_efectivo`/`Divisa.ultima_cotizacion` ya usan en este proyecto— como el
  saldo inicial (`SaldoInicialCaja`) más los ingresos y menos los egresos de esa moneda en las
  `OperacionVentanilla` ya registradas. Para PYG, una "Venta" ingresa y una "Compra" egresa
  `monto_pyg`; para la divisa extranjera, una "Compra" ingresa y una "Venta" egresa `monto_divisa`
  — el espejo exacto de a quién le entrega qué cada tipo de operación.
- **`apps.caja.views.RegistrarOperacionVentanillaView`**: sigue el mismo patrón que
  `CalculoOperacionView` (tipo normalizado desde la URL, `/caja/operaciones/<tipo>/`). Antes de
  calcular nada, resuelve la caja abierta del cajero (Criterio 2) devolviendo la misma redirección a
  `caja:abrir` que ya usa `AbrirCajaView`. Para calcular, invierte el `tipo` antes de llamar a
  `_calcular_importe_operacion` (ver el diagnóstico) y nunca duplica esa función. Antes de guardar,
  compara `caja.saldo_actual(...)` contra lo que el cajero debe entregar según el Criterio 3 y
  rechaza con el motivo si no alcanza, sin crear nada.
- **`apps.caja.forms.OperacionVentanillaForm`**: mismo criterio de validación que
  `apps.divisas.forms.CalculoOperacionForm` (monto mayor que cero, numérico, con mensajes en
  español) y mismo filtro de divisas operables (activas, cotizadas, nunca PYG).
- El panel del cajero (`apps.caja.views.PanelCajaView`, `templates/caja/panel_caja.html`) pasó de
  mostrar solo el saldo inicial a mostrar el **saldo actual** por moneda, dos accesos directos
  ("Comprar divisas" / "Vender divisas") y el historial de las últimas operaciones del turno, para
  poder verificar visualmente el Criterio 1 sin tener que ir a la base de datos.

### Tests

`tests/test_operaciones_ventanilla.py` (21 tests nuevos): uno o más por cada criterio (compra
ingresa divisa y egresa guaraníes, venta al revés, la comisión configurada se descuenta
correctamente, sin caja abierta se rechaza tanto el GET como el POST, saldo insuficiente de
guaraníes rechaza una compra, saldo insuficiente de la divisa rechaza una venta, el límite exacto es
suficiente, la operación guardada referencia caja/cajero/tasa/comisión/ambos montos), más
validaciones de formulario (monto negativo, no numérico, PYG no ofrecido, divisa sin cotización no
ofrecida, tipo de URL desconocido responde 404) y permisos (sin rol cajero, sin sesión). Se agregó
además `CajaSaldoActualTest`, una clase aparte que prueba `Caja.saldo_actual` directamente contra el
modelo (sin saldo inicial registrado parte de cero, no de un error; una operación de otra caja nunca
se mezcla con el saldo de esta).

### Resultado final

- Suite completa: sin fallas tras agregar los 21 tests nuevos (ver el resultado de esta misma
  sesión), sin ninguna regresión sobre `tests/test_caja.py` ni el resto del proyecto.
- `manage.py check` y `makemigrations --check --dry-run`: sin problemas. Migración
  `apps.caja.0002_operacionventanilla` generada y verificada.
- Sphinx recompilado con `-W`: sin advertencias. `guia.rst` agregó la sección "Operaciones en
  ventanilla" (con la explicación de la inversión de nombres respecto del flujo online, enlazada
  desde "Flujo operativo de divisas"); `reference/apps.caja.models.rst`,
  `reference/apps.caja.forms.rst` y `reference/apps.caja.views.rst` incluyen los símbolos nuevos;
  `templates.rst` incluye la plantilla nueva (`operacion_ventanilla.html`) y el encabezado actualizado
  de `panel_caja.html`.

### Pendiente / fuera de alcance

- No se modela un cliente de mostrador: ninguno de los 4 criterios de aceptación pide identificar
  con qué cliente se hizo la operación, así que no se agregó ese campo para no construir algo que no
  se pidió.
- El cierre de caja y el arqueo siguen siendo HU futuras, igual que antes de esta sesión.

### Corrección posterior (mismo día): compra rota por falta de la Divisa PYG en el catálogo

Al probar una compra en el entorno real (no en los tests, que sí la creaban explícitamente), el
sistema devolvía un error 500 (`Divisa.DoesNotExist: Divisa matching query does not exist.`) al
intentar resolver la Divisa de código `PYG` para comprobar el saldo disponible (Criterio 3). La
causa: en este proyecto, a diferencia de lo que esta sesión asumió, `PYG` **no** es una fila
garantizada del catálogo de divisas — `AperturaCajaForm` ya trata su saldo inicial como opcional por
el mismo motivo ("PYG, si existe como divisa activa"), y en la base real todavía no se había creado
esa fila.

Como una venta de ventanilla nunca necesita resolver la Divisa PYG (solo entrega la divisa
extranjera), el problema era exclusivo de la rama de compra. Se corrigió reemplazando
`Divisa.objects.get(codigo='PYG')` por una consulta que no rompe si no existe
(`Divisa.objects.filter(codigo='PYG').first()`), informando el problema con un mensaje accionable
("Divisas → Nueva divisa, código PYG") en vez de un error de servidor — mismo criterio que ya usa
`AbrirCajaView._avisar_divisas_sin_cotizar` para una divisa extranjera sin cotizar.

Se agregó `RegistrarOperacionVentanillaSinDivisaPygTest` (2 tests nuevos) que reproduce el escenario
real, sin crear la Divisa PYG en el `setUp` (a diferencia del resto de la suite): confirma que una
compra informa el problema sin romper y que una venta sigue funcionando igual sin esa fila. Suite
completa: sin fallas tras el fix.

### Segunda corrección (mismo día): el mensaje seguía siendo conceptualmente incorrecto

El usuario señaló que el mensaje de la corrección anterior ("un administrador debe crearla desde
Divisas → Nueva divisa") estaba mal planteado: PYG es la divisa **local/base** del sistema —contra
la que se cotizan y liquidan todas las operaciones—, no una divisa extranjera más que alguien deba
dar de alta manualmente desde el catálogo de divisas operables. Tratarla como un dato de catálogo
opcional, a cargo de un administrador, contradice cómo el resto del sistema ya la trata: `DivisaSelect`,
`CalculoOperacionForm`, `TriangulacionForm` y `OperacionVentanillaForm` la excluyen explícitamente de
cualquier selector de "divisa a operar", precisamente porque nunca es algo que se compre o venda
directamente.

La corrección real no era mejorar el mensaje, sino eliminar la dependencia de que alguien la creara
a mano: se agregó la migración de datos `apps.divisas.0014_crear_divisa_pyg` (`get_or_create`,
reversible como no-op) que garantiza la fila `Divisa(codigo='PYG')` desde el primer `migrate` en
cualquier base, nueva o existente. Con esa garantía, se revirtió el mensaje defensivo de la corrección
anterior: la vista vuelve a `Divisa.objects.get(codigo='PYG')` sin ninguna rama de error, porque su
ausencia ya no es un escenario posible en el flujo normal del sistema (coherente con la guía del
proyecto de no agregar manejo de errores para casos que no pueden ocurrir).

Efecto colateral detectado y corregido de paso: al garantizar PYG en el catálogo, empezaba a
aparecer también en la pantalla de "tasas vigentes" (`TasasVigentesListView`), mostrando "sin
cotización" junto a USD/EUR — exactamente la inconsistencia que el usuario señaló, porque PYG nunca
tiene una cotización propia que mostrar ahí. Se la excluyó de esa vista con el mismo criterio que ya
usan los selectores de divisa operable.

Se actualizaron los tests que antes creaban `Divisa(codigo='PYG', ...)` a mano
(`tests/test_caja.py`, `tests/test_operaciones_ventanilla.py`) para usar `Divisa.objects.get(...)` en
su lugar (la migración ya la crea; volver a crearla ahora chocaría con la unicidad del código ISO), y
se cambió el ejemplo de `test_admin_registra_divisa_activa_con_datos_obligatorios` de PYG a JPY por el
mismo motivo. `RegistrarOperacionVentanillaSinDivisaPygTest` se reescribió: ya no se puede simular la
ausencia de PYG (la migración la garantiza), así que ahora confirma lo contrario — que una compra
funciona de punta a punta sin que nadie la haya dado de alta manualmente. `manage.py makemigrations
--check` y `manage.py check`: sin problemas. Sphinx recompilado con `-W`: sin advertencias. Suite
completa: sin fallas tras este segundo fix.

## Sesión 18 — 11/10/2026 — Arqueo de Caja

**Herramienta:** Claude Code (Anthropic, modelo Sonnet 5)
**HU relacionada:** Arqueo de Caja
**Rama:** `develop`
**Participantes:** Ruth, integrante del equipo Global Exchange

### Pedido

Implementar la HU "Arqueo de Caja", con tests, docstrings, Sphinx actualizado y esta
documentación de la conversación.

> Como cajero quiero realizar un arqueo de caja para comparar el saldo registrado por el
> sistema con los valores disponibles en la caja.

Criterios de aceptación:

1. Dado que tengo una caja abierta, cuando inicio un arqueo e ingreso el monto físico contado
   por cada moneda, entonces el sistema lo compara contra el saldo registrado y muestra la
   diferencia (sobrante o faltante) por divisa.
2. Dado que el arqueo arroja una diferencia distinta de cero en alguna divisa, cuando se
   registra, entonces el sistema deja constancia de esa diferencia sin bloquear la operación
   de la caja.
3. Dado que realizo un arqueo, cuando se completa, entonces queda registrado con fecha, hora,
   cajero y los montos contados frente a los del sistema, disponible para consulta posterior.

### Diagnóstico inicial

El terreno ya estaba preparado por las dos HU anteriores de `apps.caja` (Sesión 10 "Apertura de
Caja" y Sesión 17 "Gestión de operaciones en ventanilla"): `Caja.saldo_actual(divisa)` ya existía
como el saldo "según el sistema" (saldo inicial + movimientos de `OperacionVentanilla`), así que
esta HU no necesitaba ningún cálculo nuevo de saldo — solo comparar ese valor ya disponible contra
lo que el cajero cuenta a mano. El propio docstring de `Caja` (Sesión 10) ya anticipaba esta HU:
"el arqueo... son HU futuras que todavía no existen en este código".

Una decisión de diseño central: el saldo "según el sistema" en el momento del arqueo tiene que
quedar **congelado** en el historial. `Caja.saldo_actual` es un valor derivado que cambia con cada
operación nueva; si el registro del arqueo solo guardara una referencia a la caja y volviera a
calcular `saldo_actual` cada vez que se consulta, un arqueo de hace una semana mostraría el saldo
de *hoy*, no el que realmente se comparó ese día — contradiciendo el Criterio 3 ("disponible para
consulta posterior"). Por eso `DetalleArqueoCaja` guarda ambos montos (`saldo_sistema` y
`monto_contado`) como valores fijos en el momento de crearse, no como referencias a recalcular.

### Diseño

- **`apps.caja.models.ArqueoCaja`** (nuevo): UUID, `caja`, `cajero`, `creado_en` (fecha y hora,
  automática). Una propiedad `tiene_diferencias` (True si algún detalle tiene una diferencia
  distinta de cero) resume el resultado sin necesidad de iterar manualmente en cada plantilla.
- **`apps.caja.models.DetalleArqueoCaja`** (nuevo): una fila por divisa dentro de un arqueo, con
  `saldo_sistema` y `monto_contado` congelados, y una propiedad `diferencia` (`monto_contado -
  saldo_sistema`: positiva es sobrante, negativa es faltante) derivada de esos dos valores en vez
  de guardarse por separado — mismo criterio que el resto del proyecto usa para evitar datos
  redundantes que puedan desincronizarse. Restricción única por `(arqueo, divisa)`.
- **`apps.caja.forms.ArqueoCajaForm`**: mismo patrón que `AperturaCajaForm` (Sesión 10) — genera un
  campo `contado_<divisa.pk>` por cada divisa activa, incluido PYG, con cero como valor válido (el
  cajero no tiene nada físico de esa moneda) y rechazo de negativos/no numéricos.
- **`apps.caja.views.IniciarArqueoCajaView`**: sin una caja abierta, redirige a abrirla primero
  (mismo criterio que `RegistrarOperacionVentanillaView`, Sesión 17). Al validar el formulario, por
  cada divisa llama a `caja.saldo_actual(divisa)` una sola vez y la congela junto con lo contado en
  un `DetalleArqueoCaja`, dentro de una transacción atómica junto con la creación del `ArqueoCaja`.
  No existe ninguna validación que rechace una diferencia distinta de cero (Criterio 2): la única
  validación de `ArqueoCajaForm` es sobre el formato del monto, no sobre el resultado de la
  comparación.
- **`apps.caja.views.DetalleArqueoCajaView`** y **`HistorialArqueosCajaView`** (Criterio 3): el
  detalle de un arqueo (fecha, hora, cajero, y la tabla de saldo del sistema/contado/diferencia por
  divisa) y el listado de arqueos ya registrados, ambos restringidos al cajero que lo generó
  (`cajero=request.user` en la consulta, no solo en el `test_func`) — mismo alcance que el resto de
  las pantallas de caja, donde cada cajero ve únicamente lo suyo.
- El panel del cajero (`panel_caja.html`) agregó los accesos "Arqueo de caja" e "Historial de
  arqueos" junto a los de comprar/vender divisas.

### Tests

`tests/test_arqueo_caja.py` (22 tests nuevos): uno o más por cada criterio (la comparación calcula
sobrante y faltante correctamente por divisa, la pantalla de detalle los muestra explícitamente, un
arqueo sin diferencias lo indica; una diferencia distinta de cero no bloquea el registro ni impide
que la caja siga operando después —se verificó registrando una venta de ventanilla tras un arqueo
con diferencias—; el arqueo guardado tiene fecha, hora, cajero y ambos montos, el detalle y el
historial permiten consultarlo después, y el saldo del sistema queda congelado aunque
`Caja.saldo_actual` cambie más tarde), más validaciones de formulario (monto negativo, no numérico,
cero válido), prerequisito de caja abierta (GET y POST), permisos (sin rol cajero, sin sesión, y que
un cajero no pueda ver el detalle de un arqueo ajeno), y una clase aparte (`ArqueoCajaModeloTest`)
que prueba `diferencia`/`tiene_diferencias` y la restricción única directamente contra el modelo.

### Problema de entorno encontrado (no introducido por esta HU)

Al correr `manage.py makemigrations`/`check` por primera vez en esta sesión, falló con
`ModuleNotFoundError: No module named 'stripe'`: el código real de la HU "Pago con tarjeta vía
Stripe" ya está mergeado en este `develop` (confirmado al ver aparecer
`apps.divisas.pagos_stripe` en la recompilación de Sphinx), pero el venv local de esta sesión
nunca había instalado esa dependencia nueva de `requirements.txt`. Se corrigió con
`pip install -r requirements.txt`, una instalación de dependencias ya declaradas, no un cambio de
código.

### Resultado final

- Suite completa: sin fallas tras agregar los 22 tests nuevos, sin ninguna regresión sobre
  `tests/test_caja.py` ni `tests/test_operaciones_ventanilla.py`.
- `manage.py check` y `makemigrations --check --dry-run`: sin problemas. Migración
  `apps.caja.0003_arqueocaja_detallearqueocaja` generada y verificada.
- Sphinx recompilado con `-W`: sin advertencias. `guia.rst` agregó la sección "Arqueo de caja" (y
  corrigió una frase de la sección "Apertura de caja" que todavía decía que el arqueo era una HU
  futura); `reference/apps.caja.models.rst`, `reference/apps.caja.forms.rst` y
  `reference/apps.caja.views.rst` incluyen los símbolos nuevos; `templates.rst` incluye las tres
  plantillas nuevas (`arqueo_form.html`, `arqueo_detalle.html`, `arqueo_historial.html`).

### Pendiente / fuera de alcance

- El cierre de caja sigue siendo una HU futura: ninguno de los 3 criterios de esta HU lo menciona.
- No se limita la cantidad de arqueos por turno: un cajero puede arquear varias veces mientras su
  caja esté abierta, ya que ningún criterio pide restringirlo a uno solo.

### Corrección posterior (mismo día): no ofrecer una divisa sin tasa para arquear

El usuario pidió que, si existe alguna divisa activa sin tasa, el arqueo no permita ingresar datos
para ella. El diseño original de `ArqueoCajaForm` generaba un campo `contado_<divisa.pk>` para
*cualquier* divisa activa, sin mirar si tenía cotización — copiando solo la mitad del patrón de
`AperturaCajaForm` (Sesión 10), que sí la mira.

Se corrigió `ArqueoCajaForm.__init__` para excluir del arqueo cualquier divisa activa sin ninguna
cotización vigente (PYG, con su tasa 1:1 implícita, sigue contando siempre como cotizada), dejándola
en `self.divisas_sin_cotizar` para avisar por qué no se ofrece — exactamente el mismo criterio que
`AperturaCajaForm` ya usa. Como ese aviso (`messages.warning` con el mismo texto) ya existía
duplicado en `AbrirCajaView` como método privado, se extrajo a una función de módulo
`apps.caja.views._avisar_divisas_sin_cotizar` y ambas vistas (`AbrirCajaView` e
`IniciarArqueoCajaView`) pasaron a llamarla, en vez de mantener dos copias de la misma lógica.
`arqueo_form.html` ganó el mismo bloque de aviso que ya tiene `abrir_caja.html`.

Como `ArqueoCajaForm` nunca valida campos que no declaró, forzar a mano un `contado_<pk>` de una
divisa sin cotizar en el POST tampoco cuela: Django simplemente lo ignora porque ese campo no existe
en el formulario, así que no hace falta ninguna limpieza adicional del lado del servidor para ese
caso.

Efecto colateral en los tests existentes: como ahora `ArqueoCajaForm` exige cotización para toda
divisa que no sea PYG, el `setUp` de `IniciarArqueoCajaTest` (que usaba USD sin ninguna `Cotizacion`
desde que esta HU se escribió) necesitó agregarle una, igual que ya hacía
`test_operaciones_ventanilla.py`. Se agregaron 3 tests nuevos: una divisa sin cotizar no aparece en
el formulario (con el mensaje de aviso), el arqueo se puede registrar igual sin esa divisa, y un
`contado_<pk>` forzado a mano para ella se ignora sin crear su detalle. Sphinx recompilado con `-W`:
sin advertencias (se agregó `apps.caja.views._avisar_divisas_sin_cotizar` a la referencia). Suite
completa: sin fallas tras este fix.

## Sesión 19 — 12/10/2026 — GE-54 — Gestión de movimientos extraordinarios de Caja

**Herramienta:** Claude Code (Anthropic, modelo Sonnet 5)
**HU relacionada:** GE-54
**Rama:** `feature/GE-54`
**Participantes:** Adriana Benítez, integrante del equipo Global Exchange

### Pedido

Implementar la HU "Gestión de movimientos extraordinarios de Caja", con tests, docstrings, Sphinx
actualizado y esta documentación de la conversación.

> Como cajero quiero registrar movimientos extraordinarios de caja para reflejar ingresos o
> egresos que no provienen directamente de operaciones cambiarias.

Criterios de aceptación:

1. Dado que tengo una caja abierta, cuando registro un movimiento extraordinario (ingreso o
   egreso) indicando monto, moneda y motivo, entonces el saldo de la caja se actualiza en
   consecuencia.
2. Dado que intento registrar un egreso extraordinario mayor al saldo disponible de esa divisa,
   cuando lo intento, entonces el sistema rechaza el movimiento e informa el motivo.
3. Dado que no ingreso un motivo, cuando intento guardar el movimiento, entonces el sistema exige
   ese campo antes de permitir el registro.
4. Dado que se registra un movimiento extraordinario, cuando se guarda, entonces queda
   identificado como distinto de una operación cambiaria en cualquier listado o reporte de la
   caja.

### Diagnóstico inicial

Esta sesión arrancó después de un salto de contexto grande: la última vez que se tocó este código
fue la Sesión 8 (GE-37, "Consultar el historial de transacciones"), pero `develop` había avanzado
mucho desde entonces sin que esta sesión lo supiera — un `Pago` asociado a transacciones (Sesión 9),
pagos con tarjeta vía Stripe (dos sesiones, con una corrección), y toda una app `apps.caja` nueva
construida en tres HU sucesivas (Sesión 10 "Apertura de Caja", Sesión 17 "Gestión de operaciones en
ventanilla", Sesión 18 "Arqueo de Caja"). Antes de tocar nada se investigó a fondo el estado actual:
`apps/caja/models.py`, `views.py`, `forms.py`, `urls.py`, los templates de caja, y
`tests/test_operaciones_ventanilla.py`/`test_arqueo_caja.py`, además de confirmar que la convención
de esta misma documentación cambió (de un archivo `.md` nuevo por sesión a este único archivo
consolidado, `REGISTRO_CONVERSACIONES_IA.md`, con una sección "Sesión N" por sesión).

Esa investigación confirmó que "caja abierta" ya es un concepto resuelto (``Caja``, per cajero, con
una restricción única en base para que nunca haya dos "Abierta" a la vez) y que el único saldo por
moneda que existe en todo el sistema es ``Caja.saldo_actual(divisa)`` — un valor derivado
perezosamente del saldo inicial más los ingresos y egresos de ``OperacionVentanilla`` ya registrada,
sin ningún campo mutable que mantener sincronizado. Esta HU es, en esencia, una segunda fuente de
ingresos/egresos para ese mismo saldo, que no pasa por ningún cálculo de tasa ni comisión. El propio
docstring de ``Caja`` (Sesión 10) decía literalmente que "los movimientos" de una caja eran una HU
futura que todavía no existía en el código — exactamente lo que esta sesión vino a resolver.

### Diseño

- **`apps.caja.models.MovimientoExtraordinario`** (nuevo, junto a `OperacionVentanilla`): UUID,
  `caja` y `cajero` (mismo vínculo explícito que `OperacionVentanilla`), `tipo`
  (`INGRESO`/`EGRESO`), `divisa`, `monto` y `motivo` (`TextField`, obligatorio a nivel de modelo,
  igual que `HistorialBaja.causa`). Migración `apps.caja.0004_movimientoextraordinario`.
- **`Caja.saldo_actual(divisa)` extendido, no reemplazado**: se agregó, al final del cálculo
  existente, la suma de ingresos y resta de egresos de `MovimientoExtraordinario` para esa misma
  divisa, exactamente con el mismo patrón de agregación (`aggregate(Sum(...))` con `or Decimal('0.00')`
  para el caso sin movimientos) que ya usa para `OperacionVentanilla`. Así ambas fuentes conviven en
  un mismo saldo derivado, sin que `ArqueoCaja`/`DetalleArqueoCaja` (Sesión 18) necesiten ningún
  cambio: siguen llamando a `caja.saldo_actual(divisa)` tal cual, y automáticamente comparan contra
  un saldo que ya incluye los movimientos extraordinarios.
- **`apps.caja.forms.MovimientoExtraordinarioForm`** (nuevo): a propósito **no** reutiliza el mismo
  filtro de divisas que `OperacionVentanillaForm` (que excluye PYG y cualquier divisa sin
  cotización vigente). Un movimiento extraordinario no calcula ninguna tasa, así que esas dos
  exclusiones no tienen sentido acá: ofrece todas las divisas activas del sistema, PYG incluido. El
  campo `motivo` usa el mismo criterio de validación que
  `apps.authentication.forms.CausaBajaForm.clean_causa` (rechaza vacío o solo espacios, con mensaje
  en español) en vez de inventar uno nuevo para "motivo".
- **`apps.caja.views.RegistrarMovimientoExtraordinarioView`** (nuevo, junto a
  `RegistrarOperacionVentanillaView`): mismo patrón de tipo normalizado desde la URL
  (`/caja/movimientos/<tipo>/`) y de resolución de la caja abierta (Criterio 1). A diferencia de
  `RegistrarOperacionVentanillaView`, no hay ningún cálculo de tasa/comisión antes de guardar; la
  única validación de negocio es, para un egreso, comparar `caja.saldo_actual(divisa)` contra el
  monto y rechazar con el mismo estilo de mensaje ("Saldo insuficiente de ...: hay ... y se
  necesitan ...") que ya usa la ventanilla (Criterio 2). Un ingreso nunca se valida contra el saldo.
- **Criterio 4 (distinguible de una operación cambiaria)**: se resolvió con la misma estrategia que
  ya separa "Operaciones de ventanilla" de "Arqueos" en este mismo panel — una sección y una tabla
  propias ("Últimos movimientos extraordinarios"), nunca mezclada con la de "Últimas operaciones de
  ventanilla". No se diseñó ningún listado unificado de "todos los movimientos de caja" porque
  ningún criterio lo pide, y mezclar dos modelos distintos en una sola tabla habría requerido
  normalizarlos a un formato común como ya hace `HistorialTransaccionesView` en `apps.divisas` para
  compras/ventas/cambios — una complejidad que esta HU no necesita.
- **`PanelCajaView`/`panel_caja.html`**: dos accesos nuevos ("Ingreso extraordinario" / "Egreso
  extraordinario") junto a los de comprar/vender divisas y arqueo, y la nueva tabla de movimientos
  extraordinarios (últimos 20 de la caja abierta), con su propio mensaje de "todavía no registraste
  ninguno" cuando está vacía.

### Problema de entorno encontrado (no introducido por esta HU)

Al correr `manage.py makemigrations caja` por primera vez en esta sesión, falló con
`ModuleNotFoundError: No module named 'stripe'` — el mismo problema que ya quedó documentado en la
Sesión 18: el código real de los pagos con tarjeta vía Stripe ya está mergeado en `develop`, pero el
entorno local de esta sesión nunca había instalado esa dependencia nueva de `requirements.txt`. Se
corrigió con `pip install -r requirements.txt` (instalación de dependencias ya declaradas, no un
cambio de código) y recién ahí se pudo generar la migración.

### Tests

`tests/test_movimientos_extraordinarios.py` (nuevo, 23 tests): uno o más por cada criterio (un
ingreso suma al saldo actual, un egreso resta, un movimiento puede registrarse en PYG —a diferencia
de ventanilla—, sin caja abierta se rechaza tanto el GET como el POST, un egreso mayor al saldo
disponible se rechaza informando el motivo, el límite exacto es suficiente, un ingreso nunca se
rechaza por saldo, un motivo vacío o solo de espacios se rechaza, el movimiento guardado referencia
caja/cajero/tipo/divisa/monto/motivo, y el panel muestra la tabla de movimientos extraordinarios
separada de la de operaciones de ventanilla), más validaciones de formulario (monto negativo, no
numérico, PYG sí se ofrece, una divisa sin cotizar también se ofrece, tipo de URL desconocido
responde 404) y permisos (sin rol cajero, sin sesión). Se agregó además
`CajaSaldoActualConMovimientosExtraordinariosTest`, una clase aparte que prueba `Caja.saldo_actual`
directamente contra el modelo con movimientos extraordinarios (solos, combinados con
`OperacionVentanilla`, y aislados entre cajas distintas), siguiendo el mismo patrón que
`CajaSaldoActualTest` ya usa en `test_operaciones_ventanilla.py` (Sesión 17).

### Resultado final

- Suite completa: **386 passed** (363 previos + 23 nuevos de esta HU).
- `manage.py check`: sin problemas. `makemigrations --check --dry-run`: sin cambios pendientes
  (ya generada y aplicada la migración `apps.caja.0004_movimientoextraordinario`).
- Sphinx recompilado con `-W` sobre un directorio temporal (sin tocar `docs/build/`, que está
  versionado): sin advertencias. `guia.rst` agregó la sección "Movimientos extraordinarios de
  caja" entre "Operaciones en ventanilla" y "Arqueo de caja"; `reference/apps.caja.models.rst`,
  `reference/apps.caja.forms.rst` y `reference/apps.caja.views.rst` incluyen los símbolos nuevos;
  `templates.rst` incluye `movimiento_extraordinario.html` y actualiza el rango de líneas de
  `panel_caja.html` (su comentario de encabezado creció de 7 a 9 líneas de contenido).

### Pendiente / fuera de alcance

- No existe ningún listado unificado de "todos los movimientos de caja" (ventanilla + extraordinarios
  + arqueos en una sola vista): cada uno tiene su propia tabla en el panel, que es lo que pide el
  Criterio 4 (distinguibles entre sí), no un reporte combinado.
- No se agregó ninguna categoría/clasificación del motivo (por ejemplo, "gasto de oficina", "refuerzo
  de caja"): el criterio solo pide que el campo exista y sea obligatorio, como texto libre.

## Sesión 20 — 12/10/2026 — GE-56 — Cierre de Caja

**Herramienta:** Claude Code (Anthropic, modelo Sonnet 5)
**HU relacionada:** GE-56
**Rama:** `feature/GE-56`
**Participantes:** Adriana Benítez, integrante del equipo Global Exchange

### Pedido

Implementar la HU "Cierre de Caja", con tests, docstrings, Sphinx actualizado y esta
documentación de la conversación.

> Como cajero quiero cerrar mi caja al finalizar el turno para registrar el balance final y
> consolidar las operaciones realizadas.

Criterios de aceptación:

1. Dado que tengo una caja abierta, cuando inicio el cierre, entonces el sistema muestra un
   resumen del turno: saldo inicial, operaciones realizadas, movimientos extraordinarios y saldo
   final por moneda.
2. Dado que confirmo el cierre, cuando se procesa, entonces la caja pasa a estado "Cerrada" y deja
   de aceptar operaciones de ventanilla, arqueos y movimientos extraordinarios.
3. Dado que la caja no tiene ningún arqueo registrado en el turno, cuando inicio el cierre,
   entonces el sistema muestra una advertencia y permite continuar solo si confirmo
   explícitamente.
4. Dado que mi caja se cerró, cuando accedo al historial de cajas, entonces aparece con su balance
   final y el período en que estuvo abierta, sin posibilidad de modificar sus operaciones.

### Diagnóstico inicial

Esta sesión siguió directamente a la Sesión 19 (GE-54, "Gestión de movimientos extraordinarios de
Caja"), ya mergeada a `develop`, así que el contexto de `apps.caja` seguía fresco. El propio
docstring de ``Caja`` (desde la Sesión 10, "Apertura de Caja") venía anticipando exactamente esta
HU: *"El cierre... son HU futuras que todavía no existen en este código; por eso `estado` ya
contempla 'Cerrada' y `cerrada_en` desde ahora... para no tener que migrar el modelo de nuevo más
adelante"*. Confirmado: ambos campos ya existían sin usarse, así que esta HU no necesitó ninguna
migración nueva.

El punto central del diagnóstico fue notar que las tres vistas de registro (ventanilla,
movimientos extraordinarios, arqueo) **ya resuelven la caja abierta del cajero filtrando por
`estado=Caja.ESTADO_ABIERTA`** desde que cada una se escribió. Eso significa que el Criterio 2 ("la
caja... deja de aceptar operaciones") no requiere ningún cambio en esas tres vistas: en el momento
en que una caja pasa a "Cerrada", esa misma consulta deja de encontrarla, y cada vista redirige con
su mensaje habitual de "Necesitás abrir una caja...". La única pieza que faltaba era, literalmente,
la transición de estado en sí.

Segunda observación relevante: como ninguna vista puede escribir sobre una caja ya cerrada, su
`Caja.saldo_actual(divisa)` —que siempre fue un valor derivado, nunca un campo mutable— deja de
poder cambiar desde el momento del cierre. A diferencia de `DetalleArqueoCaja` (Sesión 18), que
necesitó congelar `saldo_sistema` en un campo propio porque la caja seguía operando después de cada
arqueo, el "saldo final" de esta HU no necesita ningún campo nuevo: `saldo_actual` ya es,
de hecho, el balance final definitivo en cuanto la caja se cierra.

### Diseño

- **`Caja.cerrar()`** (nuevo método, sin migración): pasa `estado` a `ESTADO_CERRADA` y fija
  `cerrada_en = timezone.now()`, con `save(update_fields=[...])`. No valida nada por sí solo —esa
  responsabilidad es de la vista, incluida la confirmación explícita sin arqueo (Criterio 3)— para
  mantenerlo como la única pieza que persiste la transición, testeable por separado del flujo HTTP.
- **`apps.caja.views.CerrarCajaView`** (nueva, junto a `AbrirCajaView`): GET construye el resumen
  del turno (Criterio 1) — por cada `SaldoInicialCaja` de la caja, su `monto` (saldo inicial) junto
  a `caja.saldo_actual(esa_divisa)` (saldo final), más las `OperacionVentanilla`,
  `MovimientoExtraordinario` y `ArqueoCaja` completos del turno (no solo las últimas 20, a
  diferencia del panel: acá es un cierre de turno, tiene que verse todo) — y lo muestra sin cerrar
  nada todavía. POST repite la misma resolución de caja abierta que ya usan
  `RegistrarOperacionVentanillaView`/`IniciarArqueoCajaView`, y agrega la única validación de
  negocio nueva: si `caja.arqueos.exists()` es falso y el campo `confirmar_sin_arqueo` no llegó
  marcado (`'on'`), rechaza con un mensaje y vuelve a mostrar el mismo resumen con la advertencia
  (Criterio 3); en cualquier otro caso, llama a `caja.cerrar()` y redirige al panel.
- **Sin cambios en `AbrirCajaView`/`RegistrarOperacionVentanillaView`/
  `RegistrarMovimientoExtraordinarioView`/`IniciarArqueoCajaView`** (Criterio 2): todas ya
  resolvían "la caja abierta" filtrando por estado, así que cerrar una caja alcanza para que dejen
  de encontrarla. La restricción única de `Caja.Meta.constraints` tampoco necesitó ningún cambio:
  solo exige unicidad entre cajas "Abierta", así que el cajero puede abrir un turno nuevo
  inmediatamente después de cerrar el anterior.
- **`apps.caja.views.HistorialCajasView`** (nueva, al final de `views.py`): lista todas las cajas
  del cajero (abiertas y cerradas) con su balance por moneda (``caja.saldo_actual(divisa)`` para
  cada divisa que esa caja contó al abrir) y su período (`abierta_en`/`cerrada_en`, mostrando
  "— (en curso)" si todavía está abierta) (Criterio 4). Es de solo lectura: no se diseñó ninguna
  acción de edición ni eliminación para ninguno de los modelos de `apps.caja` desde que existen
  (ni siquiera para la caja ya abierta), así que "sin posibilidad de modificar sus operaciones" ya
  estaba garantizado por lo que el resto del código *no* ofrece, no por un chequeo nuevo.
- **`templates/caja/panel_caja.html`**: accesos nuevos "Cerrar caja" (solo con una caja abierta) e
  "Historial de cajas" (siempre visible, a diferencia de "Historial de arqueos", que solo aparece
  con una caja abierta — el historial de cajas tiene sentido consultarlo incluso sin ninguna
  abierta en este momento).

### Tests

`tests/test_cierre_caja.py` (nuevo, 19 tests): uno o más por cada criterio (el resumen muestra
saldo inicial/final por moneda, operaciones y movimientos del turno; sin caja abierta no hay nada
que cerrar; confirmar el cierre pasa la caja a "Cerrada" con fecha y hora; una caja cerrada
rechaza una operación de ventanilla, un movimiento extraordinario y un arqueo nuevos con el mismo
mensaje de "Necesitás abrir una caja..."; tras cerrar se puede abrir una caja nueva sin que la
restricción única lo bloquee; sin arqueos el resumen avisa y el cierre se rechaza sin la
confirmación explícita, se acepta marcándola, y no se pide ninguna confirmación si ya hay al menos
un arqueo; una caja cerrada aparece en el historial con balance y período, una que sigue abierta
también aparece pero sin fecha de cierre, y el historial no ofrece ninguna acción de edición), más
permisos (sin rol cajero, sin sesión). Se agregó además `CajaCerrarModeloTest`, una clase aparte
que prueba `Caja.cerrar()` directamente contra el modelo.

### Problema encontrado: formato numérico localizado en las aserciones

Los primeros tres tests que verificaban un monto renderizado como texto (`assertContains(response,
'200.00')`) fallaron: el proyecto sobreescribe el formato numérico del locale `en-us` con uno propio
(`global_exchange/formats/en_US/formats.py`, `THOUSAND_SEPARATOR = '.'`, `DECIMAL_SEPARATOR = ','`,
convención paraguaya/argentina), así que `floatformat` renderiza `200,00` y `1.000.000,00`, no
`200.00` ni `1000000.00`. Ninguno de los tests de las HU anteriores de `apps.caja` había chequeado
un monto renderizado como texto literal (siempre comparaban contra el `Decimal` directamente), así
que esta sesión fue la primera en tropezar con eso. Se corrigieron las tres aserciones para usar el
formato localizado correcto.

### Resultado final

- Suite completa: **405 passed** (386 previos + 19 nuevos de esta HU).
- `manage.py check`: sin problemas. `makemigrations --check --dry-run`: sin cambios pendientes
  (esta HU no agrega ni modifica campos; `estado`/`cerrada_en` ya existían en `Caja` desde la
  Sesión 10).
- Sphinx recompilado con `-W` sobre un directorio temporal (sin tocar `docs/build/`, que está
  versionado): sin advertencias. `guia.rst` agregó la sección "Cierre de caja" entre "Arqueo de
  caja" y "Acceso a esta documentación desde el sistema", y corrigió la nota de "Apertura de caja"
  que todavía decía que el cierre era una HU futura; `reference/apps.caja.views.rst` incluye
  `CerrarCajaView` y `HistorialCajasView` (``Caja.cerrar`` se documenta solo, sin tocar ningún
  `.rst`, porque `apps.caja.models.rst` ya usa `:members:` sobre la clase `Caja`); `templates.rst`
  incluye `cerrar_caja.html` e `historial_cajas.html`.

### Pendiente / fuera de alcance

- No existe ninguna pantalla de detalle por caja en el historial (solo el listado, con el balance
  final inline por moneda): ningún criterio pide un detalle separado, y el resumen completo de
  operaciones/movimientos/arqueos de una caja ya es visible una sola vez, en la propia pantalla de
  cierre, antes de confirmarlo.
- No se agregó ninguna restricción sobre cuántas veces puede abrir y cerrar cajas un cajero en un
  mismo día: cada apertura y cierre es independiente, igual que ya permite "Apertura de Caja".

## Sesión 21 — 26/10/2026 — GE-23 — Acreditación de fondos

**Herramienta:** Claude Code (Anthropic, modelo Sonnet 5)
**HU relacionada:** GE-23
**Rama:** `feature/GE-23`
**Participantes:** Rodrigo Mereles, integrante del equipo Global Exchange

### Pedido

Implementar la HU "Acreditación de fondos" (GE-23), con tests, docstrings, Sphinx actualizado y
esta documentación de la conversación.

> Como usuario cliente quiero recibir los fondos de una operación de compra en mi cuenta bancaria
> o billetera electrónica para disponer de las divisas adquiridas.

Criterios de aceptación:

1. Dado que tengo una transacción de compra en estado "Pagada", cuando el sistema procesa la
   acreditación, entonces transfiere el monto correspondiente a la cuenta bancaria o billetera
   registrada como destino, usando el medio seleccionado (Stripe o SIPAP, según corresponda).
2. Dado que la acreditación se confirma exitosamente, cuando se completa, entonces la transacción
   pasa a estado "Acreditada" y queda registrada con fecha, hora y referencia externa de la
   acreditación.
3. Dado que la acreditación falla (cuenta inválida, servicio no disponible, etc.), cuando ocurre,
   entonces la transacción permanece en estado "Pagada" (no pasa a "Acreditada"), se notifica el
   error al usuario y se habilita un reintento.
4. Dado que una transacción ya fue acreditada, cuando se intenta acreditar de nuevo, entonces el
   sistema rechaza la operación e informa que los fondos ya fueron acreditados.
5. Dado que no tengo un medio de acreditación configurado, cuando intento recibir la acreditación,
   entonces el sistema me solicita completar esos datos antes de continuar.

### Diagnóstico inicial

Antes de escribir código se evaluó, criterio por criterio, qué parte de esta HU ya estaba resuelta
por trabajo de sprints anteriores (``apps.divisas.entrega.realizar_entrega``, construido para la
entrega automática de compra/venta/cambio apenas se confirma el pago):

- **Criterios 1, 4 y 5 ya estaban cubiertos**: la entrega a la cuenta/billetera de destino ya
  ocurre automáticamente al pagar (criterio 1, con una precisión: siempre sale por SIPAP, nunca
  por Stripe, porque Stripe no puede depositarle a una cuenta arbitraria); la entrega es idempotente
  por referencia, así que un segundo intento nunca duplica nada (criterio 4); y
  ``PagarTransaccionForm`` ya exige elegir el medio de destino antes de poder pagar (criterio 5).
- **Criterios 2 y 3 eran el trabajo real pendiente**: no existía ningún estado "Acreditada" (una
  entrega exitosa dejaba la transacción en "Pagada" sin más, sin fecha ni referencia propia de la
  acreditación), y el reintento ante una falla solo lo podía hacer un administrador desde "Entregas
  pendientes" — el cliente no tenía ninguna visibilidad ni manera de reintentarlo él mismo.

### Diseño

- **Nuevo estado `ESTADO_ACREDITADA`** (con los campos `acreditado_en` y `referencia_acreditacion`)
  en `CalculoOperacion` y `CalculoTriangulacion` (espejado en los dos modelos, mismo patrón que el
  resto de los estados de esta app).
- **`apps.divisas.entrega._es_acreditable(transaccion)`** (nueva): decide si, al entregarse con
  éxito, corresponde pasar a "Acreditada". Una compra o un cambio entre divisas sí (reciben algo a
  cambio); una venta, por ahora, no — "retirar" lo obtenido por una venta es la HU "Retiro de
  fondos" (GE-24), todavía sin implementar, así que una venta exitosa se sigue quedando en "Pagada"
  exactamente como antes de esta HU.
- **`realizar_entrega()` modificado**: en el camino de éxito, si `_es_acreditable()` es verdadero,
  pasa a "Acreditada" con `timezone.now()` y la misma referencia que ya se usó para pedirle la
  transferencia a sipap-sim (no se inventa una nueva).
- **`reintentar_entrega()` (nueva, extraída de la vista administrativa)**: devuelve la transacción
  a "Pagada" y vuelve a llamar a `realizar_entrega()`, devolviendo `None` si no había nada que
  reintentar. La reutilizan tanto `ReintentarEntregaView` (administrador, refactorizada para usar
  este helper en vez de repetir la lógica) como el nuevo `post()` de
  `DetalleTransaccionOperacionView`/`DetalleTransaccionCambioView` (criterio 3: ahora el propio
  cliente ve el error en el detalle de su transacción y puede reintentarla él mismo, no solo un
  administrador).
- **Plantillas**: sección "Acreditación" (fecha y referencia) cuando corresponde, botón "Reintentar
  entrega" para el cliente cuando quedó "Entrega fallida", y los mensajes de "esta transacción ya
  fue pagada" (en las pantallas de pago y de inicio de cobro por Stripe/SIPAP) ahora también
  reconocen "Acreditada" como ya pagada (criterio 4).
- **Migración** `0025_calculooperacion_acreditado_en_and_more.py` (sin datos que migrar: los campos
  nacen vacíos).

### Tests

`tests/test_entrega.py`: se corrigieron 2 tests existentes que asumían que una entrega exitosa
dejaba la transacción en "Pagada" (ahora es "Acreditada" para una compra), y se agregaron: una
compra exitosa queda "Acreditada" con fecha y referencia; una venta exitosa se sigue quedando en
"Pagada" (todavía no hay HU de retiro); un cambio entre divisas también queda "Acreditada";
`reintentar_entrega()` devuelve `None` sin tocar nada si no hay ninguna entrega fallida; y una clase
nueva (`ReintentarEntregaClienteTest`) para el reintento desde el detalle del propio cliente (éxito,
vuelve a fallar, y no puede reintentar ni ver una transacción de otro cliente).

### Problema encontrado: `User.clientes` es una relación M2M explícita

Los primeros tres tests de reintento desde el detalle del cliente fallaban con 403 en vez del
código esperado. La causa: a diferencia de los tests administrativos de este mismo archivo (que
nunca necesitaron la relación cliente-usuario), `DetalleTransaccionOperacionView.test_func()` y
`_resolver_transaccion_propia()` dependen de `request.user.clientes` — una relación M2M explícita
que hay que poblar con `usuario.clientes.add(cliente)`, no una simple FK inversa de
`Cliente.objects.create(user=usuario, ...)`. Los fixtures de este archivo nunca habían necesitado
hacer ese `.add()` porque las dos clases de test anteriores (`EntregasPendientesListViewTest`,
`ReintentarEntregaViewTest`) solo probaban la vista administrativa, que no depende de esa relación.

### Resultado final

- `tests/test_entrega.py`: **22/22** verde.
- Regresión dirigida (`test_operaciones`, `test_pagos_stripe`, `test_pagos_sipap`, `test_divisas`):
  **273/273** verde.
- `makemigrations --check --dry-run`: sin cambios pendientes.
- Sphinx: se encontró que `apps.divisas.entrega` y `apps.divisas.casa_de_cambio` (creados en una
  sesión anterior) nunca habían tenido su propio `.rst` — se agregaron ambos al `toctree` de
  `apps.divisas.rst`, más la entrada de `ReintentarEntregaView` (modificada en esta sesión) en
  `apps.divisas.views.rst`. La única advertencia que queda con `-W` es preexistente y ajena a esta
  HU (un resaltado de sintaxis en `templates.rst` sobre `metodo_pago_list.html`, de la sesión de
  rediseño de métodos de pago).

### Pendiente / fuera de alcance

- "Retiro de fondos" (GE-24): una venta exitosa sigue quedando en "Pagada", sin un estado
  "Retirada" propio ni reintento visible para el cliente en ese caso — es una HU aparte, todavía no
  implementada.
- La advertencia preexistente de Sphinx sobre `metodo_pago_list.html` no se corrigió: es ajena a
  esta HU y no impide que la documentación se genere (solo aparece con `-W`, no en la generación
  normal que usa `entrypoint.sh` en producción).

## Sesión 22 — 26/10/2026 — GE-19 — Movimientos y saldo de los métodos de pago

**Herramienta:** Claude Code (Anthropic, modelo Sonnet 5)
**HU relacionada:** GE-19 (Gestión de métodos de pago del cliente) — mejora pedida directamente,
sin un ticket de Jira propio todavía.
**Rama:** `feature/GE-23` (continuación de la sesión anterior, sin cambiar de rama)
**Participantes:** Rodrigo Mereles, integrante del equipo Global Exchange

### Pedido

> - En cada cuenta bancaria, billetera digital o tarjeta de crédito/débito, se puedan ver los
>   movimientos que se hicieron con ella en el sistema (para la tarjeta, se entendía que había que
>   extraer la información de Stripe).
> - En el sistema se pueda ver la información de saldo de las cuentas bancarias, billeteras
>   digitales y tarjetas de crédito/débito.

### Diagnóstico inicial

Dos decisiones de diseño importantes antes de escribir código, ambas explicadas en la respuesta
antes de implementar:

- **"Movimientos" no necesita llamar a Stripe.** Global Exchange ya registra, en su propia base,
  cada pago (`Pago.metodo_pago`) y cada entrega recibida
  (`CalculoOperacion`/`CalculoTriangulacion.medio_destino`). Volver a pedirle esos mismos datos a
  Stripe duplicaría información que ya es exacta de este lado. Al revisar esto se encontró que
  `Pago.metodo_pago` **no se estaba completando para los pagos con tarjeta** (sí para SIPAP): los
  dos puntos de `apps.divisas.pagos_stripe` que llaman a `Pago.registrar_pago` (cobro directo y el
  webhook de Checkout) nunca pasaban `metodo_pago=...`. Sin corregir eso, "movimientos de una
  tarjeta" habría quedado siempre vacío.
- **"Saldo" de una tarjeta no es algo que Stripe pueda dar.** Stripe procesa cobros; no es el
  banco emisor de la tarjeta, así que no tiene (ni expone) su saldo disponible ni su límite de
  crédito. Se decidió no inventar ese número: para una tarjeta se muestran los movimientos, y en
  el lugar del saldo se explica por qué no hay ninguno. Para una cuenta bancaria o billetera, en
  cambio, el saldo real sí existe del otro lado (sipap-sim), así que se consulta en vivo.

### Diseño

- **`GET /api/cuentas/validar/` (sipap-sim)** ahora devuelve también `saldo`, además de lo que ya
  devolvía (`titular`, `proveedor`, `tipo_proveedor`, `moneda`). Es el mismo endpoint que ya se usa
  al registrar una cuenta o billetera; se reutiliza para consultar el saldo actual de una ya
  guardada, en vez de sumar un endpoint nuevo.
- **Atribución de `Pago.metodo_pago` para tarjeta (corrección, no pedida explícitamente pero
  necesaria):**
  - `_cobrar_con_tarjeta_guardada` ahora recibe el `MetodoPago` completo (antes solo
    `referencia_externa`) y lo pasa a `Pago.registrar_pago`.
  - La sesión de Stripe Checkout (cobro que necesita confirmarse en la página de Stripe) ahora
    manda `metodo_pago_id` en sus `metadata`, igual que ya hace con `transaccion_id`; el webhook
    (`_procesar_sesion_completada`) lo usa para resolver el `MetodoPago` y pasarlo también. Si ese
    dato faltara (sesiones viejas), el pago se registra igual, sin tarjeta asociada, en vez de
    romper.
- **`apps.clientes.views._movimientos_de_metodo_pago(metodo)`** (nueva, privada): junta, de más
  reciente a más antiguo, los pagos hechos con ese medio (`metodo.pagos`) y, solo para cuenta o
  billetera (nunca tarjeta), las entregas recibidas en él
  (`CalculoOperacion`/`CalculoTriangulacion.filter(medio_destino=metodo)`). Cada ítem lleva ya
  resuelta la URL de detalle correspondiente (compra/venta o cambio), para no tener que distinguir
  el tipo en el template.
- **`apps.clientes.views.metodo_pago_movimientos`** (nueva vista, con el mismo patrón de
  verificación de rol y dueño que el resto de las vistas de `MetodoPago` en este módulo): además
  de los movimientos, resuelve el saldo (consultando sipap-sim para cuenta/billetera, u omitiéndolo
  con una explicación para tarjeta).
- **`templates/clientes/metodo_pago_movimientos.html`** (nueva) y un botón "Movimientos y saldo"
  agregado a `_metodo_pago_card.html`, visible en cada tarjeta de la lista de métodos de pago.

### Tests

`tests/test_metodos_pago.py` (clase nueva `MetodoPagoMovimientosTest`, 8 tests): una billetera que
se usó para pagar y para recibir muestra ambos movimientos junto con el saldo real consultado a
sipap-sim; si sipap-sim no responde, se avisa sin romper; una tarjeta solo muestra sus pagos, nunca
consulta a sipap-sim y explica por qué no hay saldo; una tarjeta nunca aparece como medio de
destino; un cambio entre divisas (no solo una compra/venta) también cuenta como movimiento recibido
y enlaza al detalle correcto; sin ningún movimiento se avisa sin error; no se puede ver el método de
otro cliente; sin rol cliente, redirige. `tests/test_pagos_stripe.py`: se agregaron aserciones de
`pago.metodo_pago` a los dos tests existentes de pago con tarjeta (cobro directo y webhook), más un
test nuevo para el caso sin `metodo_pago_id` en los metadatos. `sipap_sim/tests/test_api.py`: se
agregó la aserción de `saldo` al test existente de `validar_cuenta`.

### Resultado final

- `tests/test_metodos_pago.py`: **37/37** verde.
- `tests/test_pagos_stripe.py`: **52/52** verde.
- `sipap_sim/tests/`: **71/71** verde.
- `makemigrations --check --dry-run`: sin cambios pendientes (esta mejora no agrega ni modifica
  ningún campo).
- Sphinx: sin advertencias nuevas (`apps.clientes.views.rst` ya documenta el módulo entero con
  `automodule`, así que la vista nueva se incluye sola; se agregó
  `metodo_pago_movimientos.html` a `templates.rst`, junto a los demás templates de esta app). La
  única advertencia que sigue apareciendo con `-W` es la misma preexistente y ajena, ya señalada en
  la Sesión 21.
- Queda pendiente la verificación completa de `tests/` (corriendo en segundo plano al cerrar esta
  sesión).

### Pendiente / fuera de alcance

- El saldo de una tarjeta sigue sin mostrarse, a propósito: no hay ninguna fuente real (ni Stripe
  ni ningún otro sistema de este proyecto) de la que obtenerlo sin inventarlo.
- No se creó ningún ticket de Jira para esta mejora; si corresponde, habría que darla de alta bajo
  GE-19 (Gestión de métodos de pago del cliente), la epic más cercana a lo que pide.

## Sesión 23 — 27/10/2026 — GE-24 — Retiro de fondos

**Herramienta:** Claude Code (Anthropic, modelo Sonnet 5)
**HU relacionada:** GE-24
**Rama:** `develop`
**Participantes:** Rodrigo Mereles, integrante del equipo Global Exchange

### Pedido

Implementar la HU "Retiro de fondos" (GE-24), con tests, docstrings, Sphinx actualizado y esta
documentación de la conversación.

> Como usuario cliente quiero retirar los fondos obtenidos mediante una operación de venta para
> recibirlos en mi cuenta bancaria o billetera electrónica.

Criterios de aceptación:

1. Dado que tengo una transacción de venta pagada/confirmada con fondos disponibles, cuando
   solicito el retiro, entonces el sistema procesa la transferencia hacia la cuenta bancaria o
   billetera que indico, usando Stripe o SIPAP según el medio elegido.
2. Dado que el retiro se confirma exitosamente, cuando se completa, entonces la transacción pasa a
   estado "Retirada" y queda registrada con fecha, hora y referencia externa.
3. Dado que el retiro falla, cuando ocurre, entonces la transacción no cambia a "Retirada", se
   notifica el error al usuario y se permite reintentar.
4. Dado que intento retirar fondos de una transacción ya retirada, cuando lo intento, entonces el
   sistema rechaza la operación e informa que ya fue procesada.
5. Dado que el monto a retirar excede el disponible de esa operación, cuando se valida, entonces el
   sistema rechaza el retiro antes de iniciar cualquier transferencia externa.

### Diagnóstico inicial

GE-24 es la mitad que le faltaba a GE-23: desde que existe `apps.divisas.entrega.realizar_entrega`,
una venta exitosa se entrega automáticamente apenas se confirma el pago, igual que una compra o un
cambio, pero se queda en "Pagada" sin más (``_es_acreditable`` devolvía `False` para una venta a
propósito, dejando esto anotado como "HU aparte, todavía no implementada").

El criterio 1 dice "cuando solicito el retiro", lo que en una primera lectura sugiere un pedido
explícito y aparte del cliente, distinto de cómo ya funciona una compra (automático, sin ninguna
acción extra). Esa lectura se intentó primero y se corrigió dos veces durante esta sesión (ver "Dos
correcciones de diseño" más abajo): el diseño final, confirmado con el usuario, es que **el retiro
de una venta es tan automático como la acreditación de una compra** — se paga y se recibe, al mismo
momento, sin ningún paso aparte. Lo único que GE-24 agrega de verdad sobre lo que ya hacía GE-23 es
el **nombre** del estado final ("Retirada" en vez de "Acreditada", para que el cliente distinga de
un vistazo si fue Global Exchange quien le entregó algo o si fue él quien retiró lo suyo).

Sobre "Stripe o SIPAP según el medio elegido" del criterio 1: en la práctica, el destino de un
retiro siempre es una cuenta o billetera (nunca una tarjeta, Stripe no puede depositarle a una), así
que siempre sale por SIPAP — la misma precisión que ya se había hecho notar para GE-23.

Sobre el criterio 5 ("antes de iniciar cualquier transferencia externa"): se cubre con el mismo
chequeo que ya existía para una compra, sin agregar nada — `_verificar_saldo_casa_de_cambio` ya se
llama, para los dos tipos de `CalculoOperacion` por igual, en el momento de "Confirmar" (antes de
que exista ningún pago), y vuelve a confirmarse de forma pesimista dentro de la misma
`realizar_entrega` (vía `CuentaPropia.ajustar_saldos`) antes de tocar el saldo. Nada de esto es
nuevo de GE-24: ya estaba ahí desde GE-23.

### Diseño (versión final)

- **Nuevo estado `ESTADO_RETIRADA`**, con `retirado_en` y `referencia_retiro`, agregado **solo** a
  `CalculoOperacion` — a diferencia de todos los estados anteriores, deliberadamente no se espeja en
  `CalculoTriangulacion` (un cambio entre divisas nunca es una venta, así que nunca podría llegar a
  "Retirada"; espejarlo ahí solo agregaría una columna y una opción muertas).
- **`apps.divisas.entrega._es_acreditable` renombrada a `_es_retiro`**, con el sentido invertido
  (antes decía si correspondía "Acreditada"; ahora dice si corresponde "Retirada", solo para una
  venta). `realizar_entrega()` elige entre `acreditado_en`/`referencia_acreditacion` o
  `retirado_en`/`referencia_retiro` según el resultado, pero el resto de la función —cuándo se
  llama, en qué orden, cómo falla— es exactamente el mismo mecanismo que ya tenía GE-23, sin ninguna
  rama nueva por tipo de transacción.
- **`estados_con_pago_ya_registrado(modelo)` (nueva, en `models.py`)**: los mensajes de "esta
  transacción ya fue pagada" (en pago con tarjeta, por SIPAP, y al intentar pagar de nuevo) ahora
  también reconocen "Retirada" como ya pagada, sin que ese chequeo rompa para
  `CalculoTriangulacion` (que no tiene ese estado) — encapsula el `hasattr` necesario en un solo
  lugar en vez de repetirlo en los cuatro puntos que lo usan.
- **Plantilla `detalle_transaccion_operacion.html`**: sección "Retiro" (fecha y referencia), paralela
  a la sección "Acreditación" que ya existía; el bloque de "Entrega fallida" distingue "reintentar
  retiro" de "reintentar entrega" solo en el texto, usando el mismo botón y el mismo `post()` que ya
  existían para GE-23 — ninguna acción nueva, ninguna pantalla nueva.
- **Migración** `0026_calculooperacion_retirada_and_more.py` (sin datos que migrar: los campos
  nacen vacíos).

### Dos correcciones de diseño, hasta llegar a "se paga y se recibe"

La primera versión trató el retiro como un pedido explícito y aparte: agregaba una vista/acción
nueva (`_retirar_fondos`, con `accion="retirar"` en `DetalleTransaccionOperacionView`), una función
`es_entrega_automatica()` para que una venta pagada se quedara en "Pagada" en vez de entregarse
sola, y un formulario nuevo (`RetirarFondosForm`) para elegir la cuenta de destino en ese momento,
sacando ese mismo campo de `PagarTransaccionForm` para no pedirlo dos veces.

El usuario señaló dos problemas reales de esa primera versión: rompía la simetría con una compra
(donde el medio de destino se elige al pagar, no después) y, además, `_movimientos_de_metodo_pago`
(HU "Movimientos y saldo de los métodos de pago") mostraba la cuenta de destino como "Recibiste" en
cuanto `medio_destino` quedaba asignado, sin importar si la transacción ya estaba "Acreditada"/
"Retirada" de verdad.

Primera corrección (todavía con retiro explícito): `PagarTransaccionForm` vuelve a pedir
`medio_destino` siempre, para los tres tipos de transacción por igual; se elimina `RetirarFondosForm`
y `_retirar_fondos` pasa a ser un botón de confirmación simple que usa la cuenta ya guardada al
pagar, sin volver a pedirla.

Segunda corrección (la definitiva): el usuario aclaró que el retiro no debería ser un paso aparte en
absoluto — "se paga y se recibe", igual que una compra. Se eliminó por completo la noción de un
pedido explícito: `es_entrega_automatica()` desaparece (y con ella, la condición que agregaba en los
tres puntos donde se llama a `realizar_entrega()` tras un pago), y `DetalleTransaccionOperacionView`
vuelve a tener una sola acción por `POST` ("Reintentar", igual que en GE-23) — ninguna "Retirar
fondos" aparte. Una venta pagada ahora se entrega sola, en el mismo instante que una compra o un
cambio, y queda "Retirada" en vez de "Pagada" sin que el cliente haga nada más.

En las dos correcciones, `_movimientos_de_metodo_pago` quedó igual: filtra por `estado` en
`ACREDITADA`/`RETIRADA`, nunca solo por `medio_destino`, así que un "Recibiste" nunca aparece antes
de que la transferencia se haya resuelto de verdad — esa parte era correcta independientemente de
cuándo se elige la cuenta o de si el retiro es automático o explícito.

### Tests

`tests/test_entrega.py`: se corrigió el test que asumía que una venta exitosa se quedaba en
"Pagada" (ahora pasa a "Retirada", con una cuenta de destino en PYG propia del escenario, ya elegida
al pagar). La clase `RetirarFondosVentaTest` (de la primera versión, con retiro explícito) se
eliminó por completo al no existir más esa acción. `tests/test_operaciones.py`: un test confirma que
pagar una venta pide y guarda `medio_destino` igual que una compra. `tests/test_pagos_sipap.py`: un
test confirma que una venta pagada por SIPAP dispara `realizar_entrega` automáticamente, igual que
una compra (antes de la segunda corrección, probaba lo contrario). `tests/test_metodos_pago.py`: un
test confirma que una venta "Pagada" (con `medio_destino` ya asignado) todavía no aparece como
"Recibiste" en movimientos, y que sí aparece apenas pasa a "Retirada".

### Resultado final

- Suite completa (`tests/`, incluido el cluster de caja consolidado en la sesión de reducción de
  tests): **383/383** verde.
- `makemigrations --check --dry-run`: sin cambios pendientes.
- Sphinx (`-W`): se agregó `_es_retiro` a `apps.divisas.entrega.rst` (en lugar de `_es_acreditable`)
  y `estados_con_pago_ya_registrado` a `apps.divisas.models.rst`. `es_entrega_automatica` y
  `RetirarFondosForm` se agregaron y se volvieron a sacar de sus `.rst` al eliminarse ambos. Sin
  advertencias nuevas; sigue la única preexistente y ajena a esta HU ya señalada en la Sesión 21
  (`templates.rst`/`metodo_pago_list.html`).
- De paso, se encontró y corrigió un bug preexistente y ajeno a esta HU en
  `tests/test_cierre_caja.py` (de la sesión de reducción de tests): comparaba
  `Caja.abierta_en`/`cerrada_en` (en UTC) con `.strftime()` directo contra lo que el template
  muestra en hora local, así que fallaba cerca de medianoche. Se corrigió con
  `timezone.localtime(...)` antes de formatear.

### Pendiente / fuera de alcance

- No se creó ningún ticket de verificación en Jira para cerrar GE-24 como "Listo"; queda a criterio
  del equipo actualizar su estado ahí.
- El criterio 5 se sigue cubriendo con el mismo chequeo optimista que ya usa el paso de "Confirmar"
  (verificar antes de intentar, sin reservar el saldo): dos operaciones que compitieran por el mismo
  saldo escaso podrían, en teoría, pasar los dos ese chequeo antes de que `realizar_entrega` ajuste
  el saldo real. Es la misma limitación ya aceptada para GE-23, no algo nuevo de esta HU.

## Sesión 24 — 29/10/2026 — Integración con API de facturación electrónica (SIFEN / Factura Segura)

**Herramienta:** Claude Code (Anthropic, modelo Sonnet 5)
**HU relacionada:** (sin número de Jira asignado en el pedido original)
**Rama:** `feature/GE-41`
**Participantes:** Rodrigo Mereles, integrante del equipo Global Exchange

### Pedido

Implementar la HU "Integración con API de facturación electrónica", con tests, docstrings, Sphinx
actualizado y esta documentación de la conversación.

> Como administrador quiero que las operaciones realizadas se emitan ante SIFEN mediante su API
> para cumplir con la normativa de facturación electrónica y contar con comprobantes válidos.

Criterios de aceptación (de partida; ver "Ajustes a los criterios" más abajo):

1. Cuando una operación pasa a "Pagada", el sistema la emite ante SIFEN con los datos completos de
   la operación.
2. Cuando SIFEN confirma la emisión, se guarda el CDC y la operación queda "Aprobada".
3. Cuando SIFEN rechaza la emisión, se registra el error y queda "Pendiente/Rechazada", sin
   bloquear la transacción ya confirmada y pagada.
4. Ante un timeout, el sistema reintenta automáticamente o encola el reintento, sin duplicar la
   emisión.
5. Si la operación ya fue emitida con éxito, no se vuelve a emitir: se devuelve el documento
   existente.

Junto con el pedido, el usuario adjuntó el PDF completo de la "API de Factura Segura para ESI" (39
páginas) y los datos reales de habilitación en el ambiente de **TEST** de Factura Segura para
Global Exchange (RUC, timbrado, actividades económicas, establecimiento/punto de expedición, y los
rangos de numeración habilitados: Facturas `0000623`-`0000634`, Notas de crédito `0000241`-
`0000252`), junto con una advertencia explícita y determinante para todo el diseño de esta sesión:

> Ten en cuenta que solo puedo generar 11 facturas, si se puede no generes ninguno o genera 1 solo
> para probar que todo esté bien.

### Dos preguntas antes de escribir código

A diferencia de otras HU de esta bitácora, acá se decidió preguntar **antes** de implementar nada,
en vez de construir sobre una interpretación propia y corregirla después (la lección de la sesión
anterior, GE-24, donde una lectura demasiado literal de los criterios tuvo que corregirse dos veces
ya construida). Dos preguntas, con sus respuestas:

- **¿Para qué tipos de transacción se debe emitir la Factura Electrónica?** El criterio 1 solo
  menciona "operaciones", sin precisar si incluye una venta o un cambio entre divisas. Se preguntó
  explícitamente; el usuario eligió **"los tres tipos (compra, venta y cambio)"**, descartando la
  alternativa más conservadora ("solo compra") que se había sugerido como recomendada.
- **¿Hacemos ya una llamada real a la API de TEST, o primero todo con mocks?** Dado que solo quedan
  11 números reales disponibles, se preguntó antes de escribir una sola línea de cliente HTTP. El
  usuario eligió **"primero todo con mocks, prueba en vivo después"**. Esta sesión se atuvo a esa
  respuesta de forma estricta: **no se hizo ninguna llamada real a Factura Segura**, ni para
  probar, ni para depurar; toda la suite de pruebas nuevas mockea `requests.post` sin excepción (ver
  "Tests").

### Diseño

- **Numeración (recurso real y finito) — `ContadorDocumentoElectronico`** (`apps/divisas/models.py`):
  una fila por tipo de documento (Factura / Nota de crédito), con `desde`/`hasta` (el rango que
  Factura Segura habilitó) y `ultimo_asignado`. El método `siguiente_numero` reserva el próximo
  número bajo `select_for_update()` (mismo patrón de bloqueo que ya usa
  `CuentaPropia.ajustar_saldos`, HU "Acreditación de fondos"), y lo deja "quemado" apenas se reserva
  — nunca se libera, ni siquiera si la emisión después falla —, porque perder un número del rango es
  preferible a arriesgar un `dNumDoc` duplicado. Se agota con `RangoDocumentosAgotadoError`.
  Migración de datos `0028_seed_contador_documento_electronico.py`: siembra el rango real tal como
  lo comunicó el usuario (`0000623`-`0000634` para Facturas), sin asignar ningún número — la
  migración deja una nota explícita para que, antes de cualquier emisión real, un administrador
  confirme con Factura Segura si `0000623` ya está consumido (el usuario avisó 11 disponibles sobre
  un rango nominal de 12) y ajuste `ultimo_asignado` a mano si corresponde, en vez de confiar a
  ciegas en que el rango está intacto.
- **`DocumentoElectronico`** (mismo archivo): una fila por transacción facturada, con el mismo
  patrón que `Pago` (`OneToOneField` a `CalculoOperacion`/`CalculoTriangulacion`, exactamente una de
  las dos — ver su `clean()` — lo que además garantiza por diseño de base de datos la idempotencia
  del criterio 5, no solo por un chequeo en código). Guarda `numero_documento`, `estado` (Generado /
  Aprobado / Aprobado con observación / Rechazado / Error de SIFEN / Error al generar), `cdc`,
  `estado_sifen`/`desc_sifen` (la respuesta cruda de SIFEN) y `error_generacion`.
- **`apps/divisas/factura_electronica.py`** (módulo nuevo, mismo rol que `apps.divisas.entrega` pero
  para la factura, no para la entrega de dinero):
  - `emitir_documento_electronico(transaccion)`: punto de entrada idempotente (criterio 5) — si ya
    existe un documento para la transacción, lo devuelve sin llamar a la API. Si no, reserva un
    número y llama a `generar_de`.
  - `intentar_emitir_documento_electronico(transaccion)`: el wrapper que de verdad se llama desde
    los puntos de pago — nunca deja escapar ninguna excepción (criterio 3: una falla al facturar
    jamás debe poder revertir ni bloquear un pago ya confirmado).
  - `consultar_estado_sifen(documento)`: `get_estado_sifen`, de solo lectura, para pasar de
    "Generado" a "Aprobado"/"Aprobado con observación"/"Rechazado"/"Error de SIFEN" (criterios 2 y
    3). Se puede repetir sin ningún riesgo.
  - `reintentar_emision(documento)`: reintento manual, solo para un documento en "Error al generar",
    que reutiliza el mismo número ya reservado.
- **Reinterpretación deliberada del criterio 4 ("reintenta automáticamente... sin duplicar")**: la
  propia documentación de Factura Segura advierte textualmente que la petición es síncrona y que,
  ante un timeout, "el resultado queda sin confirmar, ya que el servidor pudo haber procesado la
  solicitud" y que hay que "verificar su resultado... o solicitar asistencia a soporte" antes de
  reenviarla — y no hay, a diferencia de sipap-sim, ningún mecanismo documentado para consultar un
  documento por número antes de tener su CDC. Por eso se decidió que **no hay ningún reintento
  automático de `generar_de`**, ni ante un timeout ni ante un rechazo: ambos casos dejan el
  documento en "Error al generar", visible para un administrador, que debe confirmar con soporte si
  el documento ya se generó del otro lado antes de pedir un reintento explícito. Reintentar sin esa
  verificación sería, con los datos disponibles, más arriesgado que simplemente esperar.
- **Puntos de enganche**: `intentar_emitir_documento_electronico` se llama exactamente en los mismos
  3 lugares que ya disparan `apps.divisas.entrega.realizar_entrega` tras un pago confirmado
  (`apps/divisas/pagos_stripe.py`: cobro directo con tarjeta y webhook de Checkout;
  `apps/divisas/pagos_sipap.py`: webhook de confirmación), siempre justo después, nunca en su lugar
  — son dos procesos independientes (facturar y entregar), cada uno aislado de las fallas del otro.
- **Pantalla administrativa "Documentos electrónicos"** (`DocumentosElectronicosListView`, admin-only
  igual que "Entregas pendientes"): lista cada documento con su número, cliente, estado y CDC, con
  un botón de reintentar visible solo para los que están en "Error al generar"
  (`ReintentarEmisionDocumentoElectronicoView`). Bloque de solo lectura (número/estado/CDC) agregado
  también en el detalle de cada transacción (`detalle_transaccion_operacion.html` y
  `detalle_transaccion_cambio.html`).
- **Modelado del comprobante** (decisiones razonadas, a revalidar antes de cualquier emisión real —
  ver "Ajustes a los criterios y limitaciones conocidas"):
  - El receptor se modela siempre como "No Contribuyente"/consumidor final, identificado por el CI
    genérico que ya guarda `Cliente.identificador`. `Cliente` no tiene, hoy, ningún dígito
    verificador (DV) de RUC separado: implementar el algoritmo de verificación paraguayo sin poder
    probarlo contra un caso real es más riesgoso que facturar a consumidor final, que la propia API
    admite y que es fiscalmente válido para cualquier cliente que no pida factura con RUC.
  - La moneda de la operación (`cMoneOpe`) es siempre la que Global Exchange **entrega** al cliente
    (`moneda_a_entregar`, la misma función ya usada por `apps.divisas.entrega`): modela las tres
    operaciones de forma uniforme como "Global Exchange le entrega una divisa al cliente", que es lo
    que el usuario pidió al elegir facturar los tres tipos con el mismo documento.
  - Un único ítem (`gCamItem`), por el monto a entregar, exento de IVA (`iAfecIVA='3'`): no hay IVA
    sobre el tipo de cambio de divisas.
  - El medio de pago (`gPaConEIni`) se mapea desde `Pago.medio_pago`, ya registrado por GE-25/Stripe/
    SIPAP: tarjeta → `iTiPago='3'`; transferencia o billetera → `iTiPago='5'`.

### Ajustes a los criterios y limitaciones conocidas

El propio pedido invitó a corregir los criterios si no cuadraban con una implementación sólida
("los criterios pueden no estar muy de acuerdo a la implementación real... si ve que algo no cuadra
tanto, modificamos los criterios"). El ajuste principal es al criterio 4: en vez de "reintenta
automáticamente", queda **"encola para reintento manual, nunca automático"**, por el motivo ya
explicado (sin forma segura y documentada de confirmar qué pasó tras un timeout). El resto de los
criterios se mantienen tal como se pidieron.

Limitación conocida, documentada en el propio código (`apps/divisas/factura_electronica.py`,
función `_armar_de`): el armado exacto del JSON de `generar_de` reúne los campos ya decididos con el
usuario, pero su agrupación jerárquica no quedó verificada campo por campo contra el manual completo
de SIFEN — antes de la primera emisión real hay que recorrerlo contra ese manual y ajustarlo si no
calza, exactamente como el propio criterio invita a hacer.

### Tests

**Ninguna prueba de esta sesión llama a la API real de Factura Segura**: la única función que le
habla por HTTP (`_solicitar`) está siempre mockeada, y el rango de numeración de las pruebas es
siempre uno chico y separado (`900`-`901`), nunca el rango real sembrado para TEST. Nuevo
`tests/test_factura_electronica.py` (15 pruebas): emisión exitosa con guardado de CDC (criterios 1 y
2); rechazo claro de Factura Segura y timeout de comunicación, ambos sin reintento automático
(criterios 3 y 4); una segunda llamada a `emitir_documento_electronico` para la misma transacción no
vuelve a llamar a la API (criterio 5); agotamiento del rango de numeración sin romper el flujo de
pago; `consultar_estado_sifen` (aprobado, rechazado, sin respuesta, sin CDC); `reintentar_emision`
(reutiliza el mismo número, rechaza reintentar un documento que no está en error); la pantalla
administrativa y su acceso restringido a `admin`.

### Resultado final

- Suite completa (`tests/`): **392/392** verde (377 preexistentes + 15 nuevas).
- `makemigrations --check --dry-run`: sin cambios pendientes.
- Sphinx (`-W`): nuevo `apps.divisas.factura_electronica.rst`, entradas nuevas en
  `apps.divisas.models.rst` (`RangoDocumentosAgotadoError`, `ContadorDocumentoElectronico`,
  `DocumentoElectronico`) y en `apps.divisas.views.rst` (`DocumentosElectronicosListView`,
  `ReintentarEmisionDocumentoElectronicoView`). Sin advertencias nuevas; sigue la única preexistente
  y ajena a esta HU ya señalada en sesiones anteriores (`templates.rst`/`metodo_pago_list.html`).

### Pendiente / fuera de alcance

- **No se hizo ninguna llamada real a Factura Segura en esta sesión**, ni siquiera la única prueba
  en vivo que el usuario había autorizado condicionalmente ("genera 1 solo para probar"): queda para
  un pedido explícito y separado, una vez que el usuario revise esta implementación.
- Falta cargar `FACTURASEGURA_AUTH_TOKEN` en el `.env` real (obtenido una sola vez contra
  `POST /login?include_auth_token` con las credenciales de Factura Segura) — no se tocó el `.env`
  del usuario en esta sesión.
- El manual de uso del sistema que el usuario mencionó como "te lo paso también" no llegó a
  adjuntarse en esta sesión; el diseño se basó únicamente en el PDF de la API y en los datos de
  habilitación ya proporcionados.
- Antes de la primera emisión real: confirmar con soporte de Factura Segura si `0000623` ya está
  consumido (ver la nota en la migración `0028`), y revalidar `_armar_de` contra el manual completo
  de SIFEN (ver "Ajustes a los criterios y limitaciones conocidas").
- `consultar_estado_sifen` no se llama todavía desde ningún punto automático (cron o tarea
  periódica): hoy es una función disponible para que un administrador la dispare a mano o para una
  futura vista/comando. Agregar ese disparo periódico queda fuera de esta entrega.

### Corrección post-sesión — protocolo real de Factura Segura

El usuario compartió, en un mensaje posterior a cerrar la implementación, la documentación oficial
del protocolo petición-respuesta de Factura Segura (generación de token, estructura `operation`/
`params`, estructura `code`/`description`/`operation_info`/`results`). Al compararla contra
`apps/divisas/factura_electronica.py`, aparecieron dos desajustes reales, no cosméticos:

- **`results` está documentado como un ARRAY** de objetos JSON (incluso con un solo registro), pero
  `_generar`/`consultar_estado_sifen` lo trataban como un dict (`cuerpo.get('results') or {}` y
  después `.get('CDC', ...)`), lo que habría roto con `AttributeError` ante la primera respuesta real
  no vacía. Los tests propios no lo detectaron porque mockeaban `results` igual de mal (como dict).
  **Corrección**: nuevo helper `_primer_resultado(cuerpo)` que toma `results[0]` si la lista no está
  vacía, usado en ambos lugares; los mocks de `tests/test_factura_electronica.py` ahora envían
  `results` como lista.
- **`operation_info` solo garantiza la clave `"id"`**, no `"operation_id"` como se había asumido.
  Corregido a `cuerpo.get('operation_info', {}).get('id', '')` (el campo del modelo,
  `DocumentoElectronico.operation_id`, no cambia: sigue siendo donde se guarda ese valor, solo
  cambió la clave con la que se lee del JSON de respuesta).

Verificado: `tests/test_factura_electronica.py` (15/15) y la suite completa vuelven a pasar después
del cambio. Esto refuerza, una vez más, que `_armar_de` (el armado del propio `generar_de`) sigue
sin revalidarse campo por campo contra el manual completo — este hallazgo es evidencia de que vale
la pena hacerlo antes de cualquier emisión real, no solo una formalidad.

### Segunda corrección post-sesión — operaciones del API (`generar_de`/`get_estado_sifen`)

El usuario compartió un extracto adicional de la guía de Factura Segura (descripción de las
operaciones `calcular_de`, `generar_de`, `get_estado_sifen`, `sol_cancelacion`, `sol_inutilizacion`,
`dwn_kude`, `dwn_xml`, con ejemplos completos de petición/respuesta). Comparado contra el código,
aparecieron más desajustes:

- **`generar_de` envía los campos del documento sueltos en `params`, no envueltos en `{"DE": {...}}`**
  como exige el contrato (`"params":{"DE":<JSON_DE>}`). Esto habría hecho fallar cualquier llamada
  real con un payload mal formado. **Corregido**: `_generar` ahora llama a
  `_solicitar('generar_de', {'DE': _armar_de(documento, transaccion)})`.
- **`get_estado_sifen` leía mal los nombres de los campos del resultado**: usaba `desc_estado_sifen`
  (no existe en la respuesta real) en vez de `desc_sifen`, y reutilizaba esa misma descripción como
  `error_sifen` en vez de leer el campo `error_sifen` real y separado que documenta la API.
  **Corregido** en `consultar_estado_sifen`.
- **La interpretación de `estado_sifen` no cubría los valores intermedios documentados**
  (`SOL.APROBACION`, `ENVIADO_A_SIFEN`): cualquiera de los dos caía al `else` y se marcaba como
  `ESTADO_ERROR_SIFEN`, cuando en realidad significan "todavía sin resolución definitiva, hay que
  volver a consultar". Tampoco se manejaba `REINGRESADO` (el CDC quedó inválido porque el documento
  se reingresó con otro). **Corregido**: la función ahora distingue explícitamente los estados
  terminales (`APROBADO`, `APROBADO CON OBSERVACIÓN`, `RECHAZADO`), el caso `REINGRESADO`, los
  intermedios (`SOL.APROBACION`, `ENVIADO_A_SIFEN`, vacío) y los de error
  (`ERROR_SIFEN`/`ERROR_ENVIO_LOTE`/`REINTENTAR_LOTE`/`ERROR_CONSULTA_LOTE`), tal como los define el
  manual, en vez de un `if`/`else` genérico.
- Se agregó `test_estado_intermedio_no_se_marca_como_error` para blindar justamente el bug real que
  se encontró (un estado intermedio no debe tratarse como error). Los tests existentes que mockeaban
  `desc_estado_sifen`/`dNumDoc` sin el envoltorio `DE` se corrigieron para reflejar el protocolo real.

**No implementado, fuera de alcance de esta HU** (documentado para no sorprender a futuro): las
operaciones `calcular_de`, `sol_cancelacion`, `sol_inutilizacion`, `dwn_kude` y `dwn_xml`. En
particular, el manual separa `calcular_de` (recibe un `JSON_RESUMIDO_DE` y devuelve el `JSON_DE`
completo con los campos calculados por SIFEN, "listo para enviarse en `generar_de`") de `generar_de`
en sí — este módulo construye el `JSON_DE` a mano en `_armar_de` sin pasar primero por
`calcular_de`, lo cual es una fuente real de riesgo: si SIFEN exige campos calculados (totales,
desglose de IVA, etc.) que `_armar_de` no está poniendo, `generar_de` podría rechazar la solicitud
incluso con el resto de los datos correctos. La especificación completa de `JSON_RESUMIDO_DE`/
`JSON_DE` ("al final del documento", según la guía) todavía no se compartió — es el dato que más
falta para cerrar esta verificación antes de una emisión real. Tampoco se implementó el chequeo de
prioridad `estado_inu` → `estado_can` → `estado_sifen` que documenta el manual para
`get_estado_sifen`, porque esta HU no genera cancelaciones ni inutilizaciones (esos dos campos
siempre vienen vacíos para los documentos que emite este módulo).

### Tercera corrección post-sesión — esquema completo del `DE` y decisión sobre la moneda de la factura

El usuario compartió la especificación completa y real del JSON `DE` de Factura Electrónica (con
comentarios campo por campo, valores hardcodeados específicos de Factura Segura y las fórmulas de
cada campo calculado). Comparado contra `_armar_de`, aparecieron hallazgos mucho más profundos que
las dos correcciones anteriores:

- **Restricción de moneda no contemplada**: la guía aclara que `cMoneOpe` solo admite `"PYG"` o
  `"USD"` ("Factura Segura no soporta otras monedas"), pero `_armar_de` usaba
  `cMoneOpe = moneda_a_entregar(transaccion)`, que para un cambio (triangulación) puede ser
  cualquier divisa activa (EUR, BRL, ARS, etc.) — eso hubiera hecho rechazar cualquier operación que
  no involucrara USD. **Se consultó al usuario** cómo resolverlo (facturar siempre en PYG vs. usar
  USD solo cuando la divisa entregada es USD) y eligió **facturar siempre en PYG**, usando el
  equivalente en Guaraníes de cada operación. Nuevo helper `_monto_en_pyg(transaccion)`: para una
  compra o venta usa `transaccion.monto_final` (en ambos casos ya es PYG, ver `monto_a_pagar`/
  `monto_a_entregar`), y para un cambio usa `transaccion.monto_equivalente_pyg` (el valor ya
  triangulado por PYG). El monto se redondea a entero con `to_integral_value(ROUND_HALF_UP)`, el
  mismo criterio que `apps.divisas.pagos_stripe` ya usa para cobrar en PYG (moneda sin subunidad).
- **Al documento le faltaban campos obligatorios completos**: `dFeEmiDE` (fecha/hora de emisión),
  `dNomEmi`/`dNumCas`/`cDepEmi`/`dDesDepEmi`/`cCiuEmi`/`dDesCiuEmi`/`dEmailE` del emisor (ya existían
  como settings desde una sesión anterior, pero nunca se habían conectado a `_armar_de`),
  `cPaisRec`, `dEmailRec` ("obligatorio para Factura Segura" según la guía — se usa `cliente.email`),
  `iIndPres`, `iCondOpe`, `iCondCred`, `dPlazoCre`, `iTipEmi`, `iTImp`. Todos agregados.
- **`iTiOpe` estaba en `'1'` (B2B), inconsistente con `iNatRec='2'` (No Contribuyente)**: un
  receptor "No Contribuyente"/consumidor final nunca puede ser la contraparte de una operación B2B.
  Corregido a `'2'` (B2C), coherente con la propia decisión de modelar siempre al cliente como
  consumidor final.
- **Cada ítem (`gCamItem`) y el documento completo necesitan sus propios totales calculados**
  (`dTotBruOpeItem`, `dTotOpeItem`, `dBasGravIVA`, `dLiqIVAItem`, `dBasExe` por ítem; `dSubExe`,
  `dTotOpe`, `dTotGralOpe`, `dTotIVA`, etc. a nivel documento) que `_armar_de` no calculaba en
  absoluto. Como esta HU siempre factura un único ítem "Exento" (`iAfecIVA='3'`), casi todos esos
  campos son triviales (cero, salvo el propio monto en PYG): se agregaron explícitamente en vez de
  omitirlos, siguiendo las fórmulas que documenta la guía para el caso exento.
- **`gPaConEIni` (el pago) también necesita su propio monto**: `dMonTiPag`/`cMoneTiPag`/
  `dTiCamTiPag`, que no se enviaban. Agregados (el monto del único pago es el total en PYG).
- Se reescribieron `_armar_de`, `_grupo_item` y `_grupo_pago` por completo (ahora `_grupo_item`/
  `_grupo_pago` reciben el monto ya calculado, en vez de recalcularlo cada uno por su lado).
  `tests/test_factura_electronica.py` sigue pasando sin cambios (los mocks no dependían de la forma
  exacta del `DE` enviado, solo de la respuesta simulada), 16/16, y `manage.py check` sin errores.

**Sigue pendiente, ahora más acotado**: la guía confirma que `calcular_de` existe para calcular
estos mismos totales por el lado de SIFEN antes de `generar_de` — como el ítem siempre es exento,
los cálculos manuales debieran coincidir (todo cero salvo el monto), pero no se verificó contra una
respuesta real de `calcular_de`. Tampoco se verificaron contra el Manual Técnico de SIFEN 150
completo los códigos de clasificación que la guía solo describe como "ver Manual SIFEN": `iTipEmi`,
`iTipTra`, `iTImp`, `iIndPres` (quedaron con el valor más plausible, no una certeza).

### Esquema de la Nota de Crédito electrónica — guardado como referencia, sin implementar

El usuario compartió también la especificación completa del `DE` de una Nota de Crédito electrónica
(`iTiDE='5'`, el mismo tipo que `ContadorDocumentoElectronico.TIPO_NOTA_CREDITO` ya tiene sembrado
con su rango real 241-252 desde la migración `0028`, pero que ningún código emite todavía). Se le
preguntó al usuario si correspondía implementar su emisión en esta misma sesión y eligió **guardarla
solo como referencia para una futura HU**, porque:

- Ninguno de los 5 criterios de esta HU pide emitir una Nota de Crédito — son para "pago confirmado
  → facturar", no "factura ya aprobada → anular/corregir".
- Ningún flujo actual del sistema (reversión de saldo en `apps.divisas.entrega`, reintentos,
  cancelaciones) dispara ninguna anulación de una factura ya emitida; agregar la emisión ahora sería
  alcance nuevo sin un disparador real todavía definido (¿una reversión de entrega? ¿una cancelación
  manual de un administrador?).

Diferencias de esquema respecto a la Factura ya implementada (para cuando haga falta): agrega
`iMotEmi` (motivo de emisión) y `gCamDEAsoc` (un array de un único elemento, el límite de Factura
Segura, que referencia el documento que se anula — por CDC si es electrónico, o por
timbrado/establecimiento/punto de expedición/número si es un documento impreso); **no tiene**
`gPaConEIni`/`iCondOpe` (una nota de crédito no registra ningún pago). El resto (ítems, totales
calculados, datos del emisor, datos del receptor) es estructuralmente idéntico al `DE` de Factura.

### Cuarta corrección post-sesión — flujo real `calcular_de` + `generar_de` (reemplaza el cálculo manual)

El usuario compartió además el `JSON_RESUMIDO_DE` (la entrada real de `calcular_de`, antes no vista),
que confirmó algo que ya se había dejado como riesgo pendiente: hay una separación real entre la
entrada resumida (sin ningún campo calculado) y el `DE` completo con los totales, que SIFEN/Factura
Segura calcula por su cuenta en `calcular_de` — "este DE ya está listo para ser enviado en la
operación `generar_de`".

En vez de seguir calculando a mano los totales en `_armar_de` (aun siendo triviales por tratarse
siempre de un único ítem exento), se **reemplazó ese cálculo manual por el flujo real de dos pasos**:

- Nuevo `_armar_resumido_de` (reemplaza a `_armar_de`): arma solo el `JSON_RESUMIDO_DE` mínimo —
  mismos datos de cabecera/emisor/receptor/pago, pero sin ningún campo derivado (`dTotBruOpeItem`,
  `dTotOpeItem`, `dBasGravIVA`, `dSubExe`, `dTotGralOpe`, etc. desaparecen por completo).
  `_grupo_item_resumido` (reemplaza a `_grupo_item`) es el ítem recortado a sus campos base.
  `_grupo_pago` no cambia (sus campos ya eran de entrada directa, no calculados).
- Nuevo `_calcular(documento, transaccion, monto)`: llama a `calcular_de` con ese resumido y devuelve,
  tal cual, el `DE` completo que viene en `results[0]['DE']`.
- `_generar` ahora hace `_calcular(...)` y manda ese resultado directo a `generar_de`, sin tocar
  ningún total por su cuenta. Una falla en cualquiera de los dos pasos (`calcular_de` o `generar_de`)
  se trata igual: `ESTADO_ERROR_GENERACION`, mismo número ya reservado, mismo criterio de "nunca
  reintentar solo" (criterio 4) — `calcular_de` en sí no genera ningún documento real, así que sería
  seguro reintentarla sola, pero como siempre se llama junto con `generar_de` dentro de la misma
  `_generar`, el criterio de no reintentar automáticamente sigue aplicando igual al conjunto.

Esto elimina por completo el riesgo que había quedado señalado ("si SIFEN exige campos calculados
que `_armar_de` no está poniendo, `generar_de` podría rechazar la solicitud"): ya no hay ninguna
fórmula propia que pueda estar mal — los totales los calcula siempre Factura Segura/SIFEN.

Tests actualizados: los que ejercitan el camino feliz completo (`emitir_documento_electronico`,
`reintentar_emision`, la vista de reintento) ahora mockean las **dos** llamadas a `requests.post` en
orden (`calcular_de` seguido de `generar_de`), con un nuevo helper `_respuesta_calculo`, en vez de un
único `mock_post.return_value` reutilizado para ambas — así se verifica de verdad que el `DE` que
llega a `generar_de` es el que devolvió `calcular_de`, no solo que el resultado final no se rompe.
16/16 en el módulo, suite completa, `manage.py check` y Sphinx (sin advertencias nuevas) verificados
después del cambio.

### Incidente — los tests hicieron llamadas reales a Factura Segura y consumieron un número real

El usuario reportó haber recibido 17 correos de error de Factura Segura (3 con motivo
`NUMDOC_SOL_APROBACION`, 14 con `NUMDOC_APROBACION`/`NUMDOC_APROBADO`), pese a que en ningún momento
de esta sesión se pidió ni se hizo ninguna llamada real a propósito.

**Causa raíz identificada**: `intentar_emitir_documento_electronico` está conectado a los 3 mismos
puntos de confirmación de pago (`_procesar_sesion_completada`/`_cobrar_con_tarjeta_guardada` en
`pagos_stripe.py`, `_procesar_confirmacion_sipap` en `pagos_sipap.py`) desde que se implementó esta
HU. Ningún archivo de test fuera de `tests/test_factura_electronica.py` mockea
`apps.divisas.factura_electronica.requests.post` (confirmado con `grep` sobre todo `tests/`). El
usuario había agregado credenciales reales (`FACTURASEGURA_AUTH_TOKEN`, etc.) a su `.env` durante
esta misma sesión, y `manage.py test` usa el mismo módulo de settings (`global_exchange.settings.dev`,
ver `DJANGO_SETTINGS_MODULE` en `.env`) que `manage.py runserver` — sin ningún override para tests.
Resultado: cada vez que corrí la suite completa (`python manage.py test tests`) después de que esas
credenciales quedaran cargadas, al menos 5 tests confirmados en `tests/test_pagos_stripe.py`/
`tests/test_pagos_sipap.py` (los que efectivamente llevan una transacción a "Pagada" a través del
webhook/cobro real) dispararon una llamada real a `calcular_de`+`generar_de` contra el ambiente de
TEST real de Factura Segura. Corrí la suite completa 3 veces después de que las credenciales
quedaran activas en esta sesión — coincide con el orden de magnitud de los 17 correos.

**Por qué probablemente solo se vio afectado un único número real**: `ContadorDocumentoElectronico`
vive en la base de datos de TEST de Django (`test_global_exchange_dev`), que `TestCase` envuelve en
una transacción por test y descarta al final de cada uno — así que el `ultimo_asignado` nunca quedó
realmente persistido entre corridas, y cada intento (en cualquier test, en cualquier corrida) volvía
a calcular el mismo "próximo número": el primero del rango real sembrado por la migración `0028`
(`0000623`). Se verificó con `manage.py shell` que la fila real de `ContadorDocumentoElectronico` en
la base de datos de **desarrollo** (no la de test) sigue con `ultimo_asignado=None` para ambos tipos
— la aplicación real nunca quedó con su propio estado corrupto, solo el sistema remoto de Factura
Segura vio intentos repetidos sobre el mismo número. El patrón de los 17 correos (siempre rechazos
por "ya usado", nunca por otro motivo) es consistente con que el primer intento real haya sido
aceptado por Factura Segura (consumiendo `0000623` de verdad) y los 17 restantes hayan sido
rechazados por reintentar ese mismo número — es decir, lo más probable es que **solo se haya
consumido el número `0000623`**, no los 11-12 completos, pero esto no está confirmado y debe
verificarse con soporte de Factura Segura antes de asumir nada.

**Corrección aplicada** (`global_exchange/settings/dev.py`): se agregó un bloque que detecta
`'test' in sys.argv` (el mismo módulo de settings se usa para `runserver` y para `test`, así que no
hay otra forma de distinguirlos sin tocar `DJANGO_SETTINGS_MODULE`) y, solo en ese caso, fuerza
`FACTURASEGURA_AUTH_TOKEN=''` y `FACTURASEGURA_BASE_URL='http://127.0.0.1:1/'` (un puerto cerrado:
cualquier llamada real falla al instante con un error de conexión, contenido por
`intentar_emitir_documento_electronico`, que nunca relanza nada). Esto protege **cualquier test
futuro** que termine pagando una transacción, no solo los que ya existen hoy. Verificado:
`tests/test_factura_electronica.py` (que mockea `requests.post` directamente) sigue funcionando
igual, sin verse afectado por el override.

**Bug adicional que este mismo fix destapó**: al apuntar a un puerto cerrado, el mensaje de
`ConnectionError` real (con toda la cadena de reintentos de `urllib3` interpolada) superaba los 255
caracteres de `DocumentoElectronico.error_generacion`, lo que rompía el propio `save()` con un error
de Postgres (`StringDataRightTruncation`) y dejaba la transacción de test abortada, haciendo fallar
en cascada el resto de esos mismos tests (4 failures + 6 errors en `test_pagos_stripe`/
`test_pagos_sipap`). **Corregido**: tanto en `_generar` como en `consultar_estado_sifen`, todo texto
de error se recorta siempre al `max_length` real del campo (leído desde
`DocumentoElectronico._meta.get_field(...)`, no un número mágico repetido) antes de guardarlo — un
mensaje de error nunca puede volver a romper el guardado del propio error. Esto es una corrección de
fondo, no solo para los tests: un timeout real contra la API, en producción, también podría generar
un mensaje de excepción largo.

Verificado: `tests/test_factura_electronica.py` + `tests/test_pagos_stripe.py` +
`tests/test_pagos_sipap.py` juntos, 77/77 OK (antes de ambos fixes, 4 failures + 6 errors en estos
mismos archivos). Suite completa corrida de nuevo para confirmar.

**Pendiente de parte del usuario**: contactar a soporte de Factura Segura para confirmar el estado
real del número `0000623` (¿"Sol.Aprobación" pendiente o ya "Aprobado"?) antes de que la aplicación
real intente usarlo — la fila real de `ContadorDocumentoElectronico` sigue en `ultimo_asignado=None`
y deliberadamente no se tocó, para no asumir por mi cuenta algo que solo soporte puede confirmar.

### Revisión de cumplimiento contra el texto formal de los 5 criterios (Jira)

El usuario pegó el texto formal de la historia (con el formato Dado/Cuando/Entonces de Jira) y
preguntó directamente si se estaban cumpliendo todos los criterios. Revisando el código real (no de
memoria) contra cada criterio aparecieron dos brechas concretas, ya corregidas:

- **Criterio 1** ("...envía la información completa de la operación: cliente, monto, divisa, tasa,
  fecha..."): cliente/monto/fecha ya viajaban en el `DE`, pero la **tasa aplicada nunca se enviaba en
  ningún campo** (`grep` sobre el módulo no encontró ninguna referencia a `tasa_aplicada`/
  `tasa_cruzada`). Como el esquema de Factura Segura no tiene un campo estructurado para "la tasa de
  cambio del negocio" (`dTiCam` es la tasa de la propia factura cuando `cMoneOpe≠PYG`, que acá
  siempre es PYG), se agregó un nuevo `_info_adicional(transaccion)` que la escribe en `dInfAdic`
  (texto libre impreso en el KuDE, fuera del XML firmado, exactamente el campo que la guía describe
  para esto).
- **Criterios 2 y 3** (recibir la aprobación/rechazo real de SIFEN): `consultar_estado_sifen` existía
  desde la implementación original pero **no se llamaba desde ningún lado de la aplicación** —
  `grep` sobre `apps/`/`templates/` solo la encontró en el propio módulo y en los tests. Sin cron ni
  botón, un documento quedaba para siempre en "Generado" (ni aprobado ni rechazado) salvo que alguien
  la invocara a mano por shell. Se agregó `ConsultarEstadoSifenDocumentoElectronicoView` (mismo patrón
  que `ReintentarEmisionDocumentoElectronicoView`) + su URL + un botón "Consultar estado SIFEN" en
  `documentos_electronicos.html`, visible cuando el documento tiene CDC y todavía no es definitivo
  (`not documento.es_definitivo`) — ahora un administrador sí puede completar estos dos criterios
  para un documento ya generado, aunque sigue siendo una acción manual, no automática.

**Criterio 4 sigue con la reinterpretación ya documentada** (sesión anterior): no hay reintento
automático de `generar_de` ante un timeout, por la propia advertencia de Factura Segura sobre
peticiones síncronas sin confirmar. Se encola para un administrador (lista + botón "Reintentar"), lo
que satisface la lectura de "encola el reintento" del criterio, pero no la de "reintenta
automáticamente" — desviación deliberada, acordada con el usuario, no un descuido.

Tests nuevos: la vista de consulta (éxito y sin CDC) y que `dInfAdic` lleve la tasa. 19/19 en el
módulo, `manage.py check` y Sphinx limpios, suite completa verificada de nuevo.

### Primera prueba en vivo real — hallazgo y corrección: email del cliente obligatorio

Con la decisión informada del usuario de probar directamente con el número `0000623` (sin confirmar
antes con soporte), se ejecutó un primer llamado controlado por shell a `emitir_documento_electronico`
contra una transacción real "Pagada" ya existente. Resultado: rechazo real con
`code=-10101`/`"NUMDOC_APROBADO"`, confirmando en los hechos (ya no solo por teoría) que `0000623`
había quedado aprobado por el incidente de los tests de sesiones anteriores. Se actualizó el
`ContadorDocumentoElectronico` real (`ultimo_asignado=623`) para que cualquier emisión futura use
`0000624` en adelante, y se dejó sin tocar el `DocumentoElectronico` fallido que quedó asociado a esa
transacción de prueba (por el `OneToOneField`, esa transacción en particular ya no puede reintentarse
con éxito, al estar pegada al número `623`).

El usuario pidió después probar él mismo desde la aplicación real (creando una compra y pagándola),
para validar `0000624`. El intento real falló con `code=-10009`:
`"El parametro dEmailRec: es obligatorio. Corrija el dato en el origen."` — el `Cliente` de prueba
(Rodrigo Mereles) no tenía ningún email cargado (`Cliente.email` es `null=True, blank=True`, y no hay
ningún lugar en el alta de un cliente que lo complete automáticamente, confirmado revisando
`apps/clientes/forms.py`/`models.py`). A diferencia de `NUMDOC_APROBADO`, este es un rechazo de
**validación de datos**, no de numeración: no se generó nada del otro lado, así que el mismo número
seguía disponible. Se cargó el email real del usuario (`remm2003@gmail.com`) en el `Cliente` y se usó
el botón **"Reintentar"** (que reutiliza el mismo número) — la segunda vez, con el dato corregido,
Factura Segura aceptó la emisión real. **Primera emisión real exitosa de esta HU**, con el número
`0000624`.

**Corrección aplicada** para que esto no vuelva a pasar con otro cliente: `_generar` ahora valida que
`transaccion.cliente.email` esté cargado **antes** de llamar a la API en absoluto. Si falta, el
documento queda directamente en `ESTADO_ERROR_GENERACION` con un mensaje claro, sin gastar ningún
intento real contra Factura Segura (ni generar el correo de error que le llega a soporte). El número
ya reservado sigue "quemándose" igual que con cualquier otra falla (mismo criterio ya documentado:
preferible a arriesgar un `dNumDoc` duplicado), pero al menos la falla se detecta sin tocar la red.
Nuevo test `test_cliente_sin_email_no_llama_a_la_api`. Se le señaló al usuario, como mejora aparte no
implementada todavía, hacer `Cliente.email` obligatorio en el alta — a definir si se quiere encarar
como una HU separada.

Verificado: 20/20 en el módulo, `manage.py check` y Sphinx limpios, suite completa corrida de nuevo.

### Pantalla propia para el cliente + fix del link roto en la lista de administración

El usuario pidió dos cosas: que en "Documentos electrónicos" (administración) el cliente se vea bien
en vez de como un link que da error, y una pantalla nueva donde el propio cliente pueda ver sus
facturas electrónicas.

- **El link roto**: `documentos_electronicos.html` enlazaba el nombre del cliente a
  `detalle_transaccion_operacion`/`detalle_transaccion_cambio`, pero el `test_func` de esas dos vistas
  exige explícitamente `'cliente' in roles and not request.user.is_staff` — un administrador nunca
  puede entrar ahí, para ninguna transacción, ni siquiera la suya. Se quitó el enlace: el cliente
  ahora se muestra como texto simple.
- **Nueva pantalla del cliente**: `MisFacturasElectronicasListView` (``apps/divisas/views.py``),
  simétrica a `MiHistorialTransaccionesView` (mismo `test_func`, mismo patrón de `cliente_activo` vía
  el middleware de `apps.clientes`), filtrando `DocumentoElectronico` por
  `calculo_operacion__cliente`/`calculo_triangulacion__cliente` igual al cliente activo. Nueva URL
  `divisas:mis_facturas_electronicas`, template `mis_facturas_electronicas.html` (solo lectura, sin
  botones de administrador), enlace nuevo en el sidebar y en el home, ambos bajo el mismo
  `puede_ver_historial_propio` que ya gatea "Mi historial de transacciones".
- Al escribir los tests apareció un detalle real del modelo: el `test_func` usa
  `request.user.clientes` (el `ManyToManyField` `usuarios` de `Cliente`, `related_name='clientes'`),
  **no** el `OneToOneField user` (`related_name='cliente_perfil'`) que ya fijaba el fixture base de
  este archivo — sin `cliente.usuarios.add(cliente.user)`, el propio cliente quedaba afuera con 403.
  Mismo patrón que ya usa el helper `_crear_cliente` de `tests/test_operaciones.py`.

Tests nuevos: el cliente ve su propia factura, no ve la de otro cliente (aislamiento), un admin no
puede entrar a esta pantalla; más una verificación de que el admin ya no ve ningún link roto. 23/23 en
el módulo, `manage.py check` y Sphinx limpios, suite completa corrida de nuevo.

### Corrección: ``dEmailRec`` debía usar el email de Keycloak, no el campo legado de ``Cliente``

El usuario preguntó si el email con el que un cliente se registra (Keycloak) es el mismo que se
termina usando para Factura Segura. Revisando el código, la respuesta real era **no**: tanto el
chequeo previo agregado en la sesión anterior como `_armar_resumido_de` leían directamente
`cliente.email`, el campo que `ClienteForm` marca explícitamente como legado:

```python
# Campo legado: se conserva para aceptar datos históricos, pero no se
# muestra en la interfaz; el correo operativo pertenece al usuario.
email = forms.EmailField(required=False, widget=forms.HiddenInput())
```

Es decir, el propio diseño de la app ya había decidido que el email real y vigente de un cliente es
el de su usuario (`Cliente.user`, `OneToOneField` al usuario titular, sincronizado desde Keycloak vía
`apps.authentication.backends`), y que `Cliente.email` solo se conserva por compatibilidad con datos
viejos — nada en el alta real lo completa. El email que se cargó a mano durante la prueba en vivo de
la sesión anterior fue justamente ese campo legado, porque era el único que `_armar_resumido_de` leía.

**Corrección**: nuevo helper `_email_receptor(cliente)` que prioriza `cliente.user.email` (el titular,
real y verificado por Keycloak) y solo cae al campo legado `cliente.email` si no hay usuario titular o
no tiene email. Usado tanto en `_armar_resumido_de` (`dEmailRec`) como en el chequeo previo de
`_generar` que ya existía. Nuevo test
`test_el_email_del_usuario_titular_tiene_prioridad_sobre_el_campo_legado`. Se verificó en la base de
desarrollo real que el `Cliente` de prueba usado para la emisión real (`Rodrigo Mereles`) no tiene
`user` asignado (`None`) — por eso, para ese cliente en particular, el comportamiento no cambia: sigue
cayendo al campo legado que ya se cargó a mano. Para cualquier cliente real con su `user` de Keycloak
bien vinculado, a partir de ahora se usa automáticamente ese email, sin necesitar ninguna carga manual.

24/24 en el módulo, `manage.py check` y Sphinx limpios, suite completa corrida de nuevo.

### Descarga del KuDE (PDF) y el XML firmado, bajo demanda

El usuario notó que el sistema no permite ver la factura generada en sí (solo metadatos: número,
estado, CDC) — depende por completo de que llegue el correo de Factura Segura. Se implementó la
descarga directa, usando las operaciones `dwn_kude`/`dwn_xml` de la guía (GET, no el endpoint único
de operaciones POST), consultando antes con el usuario quién puede descargar y cómo:

- **Quién**: tanto el administrador (cualquier documento, desde "Documentos electrónicos") como el
  propio cliente (solo los suyos, desde "Mis facturas electrónicas").
- **Cómo**: bajo demanda, sin guardar nada en el servidor — cada clic vuelve a pedirle el archivo a
  Factura Segura.

Nuevo en `apps/divisas/factura_electronica.py`: `_descargar_archivo(operation, documento)` (GET
genérico a `{BASE_URL}/{operation}/{dRucEm}/{CDC}` con el `Authentication-Token`, devuelve el cuerpo
binario tal cual, o `None` si falla o no hay CDC) y los dos wrappers `descargar_kude`/`descargar_xml`.
Nueva vista compartida `DescargarDocumentoElectronicoView` (`apps/divisas/views.py`): resuelve permiso
(admin siempre; cliente solo si la transacción es suya) y devuelve el archivo con
`Content-Disposition: attachment`, o un error claro (400 sin CDC, 502 si Factura Segura no responde,
404 formato desconocido). Nueva URL `divisas:descargar_documento_electronico` (no vive bajo
`administrar/`, porque la usan ambos roles). Botones "KuDE"/"XML" agregados en
`documentos_electronicos.html` y `mis_facturas_electronicas.html`, visibles cuando el documento ya
tiene CDC.

Se verificó contra el documento real ya aprobado (`0000624`, `estado_sifen='APROBADO'`) que esta es
una operación de solo lectura segura de probar en vivo (no consume ningún número), aunque la
implementación en sí se probó solo con mocks en esta sesión.

34/34 en el módulo, `manage.py check` y Sphinx limpios, suite completa corrida de nuevo.

### Segunda prueba en vivo (Jorge Ferreira) — dos problemas distintos mezclados en un solo reporte

El usuario creó un segundo cliente de prueba real (Jorge Ferreira) y reportó un correo de error
`NUMDOC_APROBADO` más "no llega la factura... me da error en el sistema, dice que no se pudo
generar". Investigando los datos reales (`ContadorDocumentoElectronico`, los tres
`DocumentoElectronico` existentes y sus timestamps), se separaron en dos hechos distintos:

- **El correo `NUMDOC_APROBADO` no es un problema nuevo**: corresponde a un reintento sobre el
  `DocumentoElectronico` viejo y permanentemente atascado de `0000623` (de la primera prueba en vivo,
  sesión anterior) — su `actualizado_en` coincide con ese momento. Ese número nunca puede
  reutilizarse (ver la sesión del incidente); el botón "Reintentar" sigue mostrándose igual para esa
  fila porque el código no distingue "falló por un dato corregible" de "falló porque el número está
  permanentemente quemado" — queda anotado como mejora posible, no resuelto en esta sesión.
- **El "no se pudo generar" de Jorge sí era un bug real, nuevo**: `_email_receptor` (agregado en la
  corrección anterior) solo miraba `cliente.user.email` (el ``OneToOneField`` "titular"), pero el
  `Cliente` de Jorge, igual que el de Rodrigo, tiene `user=None` — el único lugar con su email real
  (`jorge.adan.ferreira02@gmail.com`, el mismo de Keycloak) es `Cliente.usuarios` (el `ManyToManyField`
  que de hecho es la relación que usa `test_func` en las vistas propias del cliente vía
  `request.user.clientes`, no `Cliente.user`). El documento `0000625` de Jorge quedó en
  `ESTADO_ERROR_GENERACION` con el mensaje "cliente no tiene email cargado" — correcto en el
  diagnóstico, pero el fix anterior no cubría este caso real tan común (ningún cliente de prueba
  tiene `Cliente.user` asignado; todos dependen de `Cliente.usuarios`).

**Corrección**: `_email_receptor` ahora prueba, en orden, `cliente.user.email` → el email de
cualquier usuario en `cliente.usuarios` que tenga uno cargado (`cliente.usuarios.exclude(email='')
.first()`) → el campo legado `cliente.email`. Nuevo test
`test_sin_titular_usa_el_email_de_un_usuario_asociado`, que reproduce exactamente el caso real
encontrado (sin `user`, sin campo legado, con el email solo en `usuarios`). Con este fix, el
documento `0000625` de Jorge puede reintentarse ahora y debería generarse correctamente sin tocar
nada más a mano (su email ya está en el lugar correcto, `usuarios`).

35/35 en el módulo, `manage.py check` y Sphinx limpios, suite completa corrida de nuevo.

## Sesión 25 — 30/10/2026 — Autoservicio de alta: "Solicitud de cliente"

### Pedido

Tras las pruebas en vivo de la HU de facturación electrónica, el usuario pidió, aparte, un ajuste al
flujo de alta de clientes: hoy un administrador tiene que crear el `Cliente` a mano
(`ClienteCreateView`) y asociarlo después a un usuario existente (`AsociarUsuariosClienteView`), sin
que el usuario mismo inicie nada. Pidió que un usuario nuevo pueda solicitar ser cliente (nombre,
apellido, cédula/RUC), que un administrador la gestione, y que, mientras no tenga cliente asociado,
lo único que vea sea esa pantalla (o el aviso de que ya la envió) y un vistazo de las tasas.

También pidió, como parte del mismo pedido, cambiar el formulario de registro de usuarios (quitar la
contraseña, pedirla recién después de verificar el email).

### Hallazgo que redefinió el alcance

Investigando antes de planificar (con dos agentes de exploración en paralelo), se confirmó que **el
registro de usuarios está 100% delegado a Keycloak**: no existe ningún `RegisterView`/formulario
propio dentro de este Django, ni verificación de email en el código (`apps/authentication/views.py`
solo tiene `CustomOIDCLogoutView`/`CustomOIDCCallbackView`; `LOGIN_URL` apunta directo a
`oidc_authentication_init`; no hay `send_mail` en ningún lugar del proyecto). El formulario de
registro con el que se queja el usuario es la pantalla hospedada por Keycloak, fuera de este
repositorio. Se le preguntó al usuario cómo manejar esto, y eligió configurarlo él mismo en Keycloak
(que ya soporta nativamente ese patrón vía Required Actions) — esta sesión se limitó a la parte que
sí vive en el código: la solicitud de cliente.

### Diseño e implementación

- **Modelo `SolicitudCliente`** (`apps/clientes/models.py`): `usuario` (FK), `nombre`, `apellido`,
  `identificador`, `estado` (`PENDIENTE`/`APROBADA`/`RECHAZADA`, mismo patrón que el resto del
  proyecto), `motivo_rechazo`, `creado_en`, `revisado_en`/`revisado_por`, `cliente_creado`
  (`OneToOneField` a `Cliente`, se completa al aprobar). Una `UniqueConstraint` condicional
  (`estado='PENDIENTE'`) garantiza a nivel de base de datos que un usuario no tenga dos solicitudes
  pendientes a la vez — mismo criterio de "la base de datos lo impide" que ya usa `DocumentoElectronico`.
  Solo cubre clientes físicos; uno jurídico sigue dándose de alta por un administrador, sin cambios.
- **`SolicitudClienteForm`** (`apps/clientes/forms.py`): pide solo nombre/apellido/identificador (el
  usuario lo fija siempre la vista, nunca el formulario). Se extrajo `_error_identificador_en_uso`
  (función compartida) de la lógica que ya tenía `ClienteForm.clean_identificador`, y se le agregó
  también el chequeo contra una `SolicitudCliente` pendiente de otro usuario — beneficio colateral:
  ahora tampoco un administrador puede crear a mano un `Cliente` con un identificador que ya está
  pendiente de aprobación por autoservicio.
- **Vistas nuevas** (`apps/clientes/views.py`): `SolicitarClienteView` (el propio usuario; redirige si
  ya tiene cliente, muestra el aviso de "en gestión" si hay una pendiente, el motivo + formulario si
  la última fue rechazada), `SolicitudesClienteListView`/`AprobarSolicitudClienteView`/
  `RechazarSolicitudClienteView` (admin, mismo criterio `is_staff`/`is_superuser` que
  `ClienteCreateView`). Aprobar crea el `Cliente` y hace `cliente.usuarios.add(solicitud.usuario)`
  (la relación real que usan los permisos, no el `OneToOneField user`, casi sin uso en la práctica).
- **UI**: nuevo booleano `puede_solicitar_cliente` en `apps.authentication.context_processors`
  (`'cliente' in roles and not es_admin and not tiene_clientes_asociados`), tarjeta en `home.html` y
  link en el sidebar de `base.html`, visibles solo para quien corresponde. No hizo falta tocar nada de
  "tasas vigentes": `puede_ver_tasas` ya no exige tener un `Cliente` asociado, solo el rol Keycloak.
- **Templates nuevos**: `solicitar_cliente.html`, `solicitudes_cliente.html` (lista admin con
  aprobar/rechazar inline, el rechazo con un `motivo` obligatorio en un `<textarea>` colapsable).

### Hallazgo adicional durante la verificación

Al correr los tests nuevos con `manage.py test`, aparecía "NO TESTS RAN": se descubrió que
`tests/test_clientes.py` (y otros 6 archivos: `test_auth.py`, `test_divisas.py`,
`test_notificaciones_tasas.py`, `test_roles.py`, `test_seleccion_cliente.py`, `test_users.py`) están
escritos en estilo `pytest` (`@pytest.mark.django_db`), no `django.test.TestCase` — el runner de
Django nunca los descubre. Hay un `pytest.ini` en la raíz del proyecto preparado exactamente para
correr estos archivos vía `pytest`, separado de `manage.py test`. Esto significa que **ninguna de las
"suites completas" corridas en sesiones anteriores de este proyecto (incluidas todas las de esta
misma sesión, antes de este hallazgo) incluyó estos 7 archivos** — no es un problema introducido
ahora, es una laguna de verificación preexistente que convendría tener en cuenta de acá en adelante:
el chequeo completo de este proyecto requiere correr tanto `manage.py test tests` como
`pytest tests/test_auth.py tests/test_clientes.py tests/test_divisas.py
tests/test_notificaciones_tasas.py tests/test_roles.py tests/test_seleccion_cliente.py
tests/test_users.py` (o `pytest tests/` entero, con cuidado de no correrlo en paralelo con
`manage.py test`, porque ambos compiten por la misma base de datos de test).

### Verificación

`manage.py makemigrations --check --dry-run` limpio, `manage.py check` limpio, Sphinx sin
advertencias nuevas (los tres `.rst` de `apps.clientes` usan `automodule` genérico, documentan lo
nuevo sin tocar ningún archivo). 27/27 tests nuevos y existentes en `test_clientes.py` (pytest),
131/131 en los 7 archivos pytest en conjunto (sin regresión), suite completa de `manage.py test`
corrida de nuevo para la confirmación final.

### Ajustes al registro: tema de Keycloak, bug del username, y redirección directa

Tras implementar "Solicitud de cliente", el usuario probó el registro completo contra su Keycloak
local (`C:\herramientas_IS2\keycloak`, instalación standalone, realm `global-exchange`) y aparecieron
varios problemas reales, cada uno investigado con evidencia concreta (logs de Keycloak, la API de
administración, el jar de Keycloak) antes de corregir:

- **El registro seguía pidiendo nombre/apellido**: `register.ftl` (el tema propio
  `keycloak/themes/global-exchange`) usaba `userProfileCommons.userProfileFormFields`, que renderiza
  todos los atributos de User Profile sin excepción. Se reemplazó por un loop propio que excluye
  `firstName`/`lastName` explícitamente. **Primer intento fallido**: se copió el patrón de macro del
  tema `keycloak.v2` (que depende de `field.ftl`), pero la cadena de herencia real de este tema es
  `global-exchange → keycloak → base` (confirmado leyendo `theme.properties` de cada uno dentro del
  jar `keycloak-themes-26.7.2.jar`) — nunca pasa por `keycloak.v2`, así que `field.ftl` no existía en
  esa cadena (`TemplateNotFoundException`). Se corrigió usando el patrón real de `base`
  (autocontenido, sin `field.ftl`), extraído del jar con Python/zipfile para no adivinar.
- **La contraseña diferida no funcionaba**: `keycloak/instalar-tema.ps1` (ya existente en el repo)
  fijaba `always_set_password_on_register_form=true`, anulando a propósito el comportamiento nativo
  de Keycloak 26 (diferir la contraseña hasta verificar el email). Se invirtió a `false`.
- **El correo de verificación no se enviaba**: `535-5.7.8 Username and Password not accepted` de
  Gmail — la contraseña SMTP configurada era la contraseña normal de la cuenta, no una "contraseña de
  aplicación" (obligatoria para SMTP con 2FA activo). Se le indicó al usuario generar una en
  `myaccount.google.com/apppasswords` y cargarla en `Realm settings → Email`.
- **El rol `cliente` no se asigna a cuentas nuevas**: confirmado por la API de administración de
  Keycloak que `default-roles-global-exchange` (el rol que se asigna solo a cualquier cuenta nueva)
  no incluye el rol de negocio `cliente` como componente — es config de Keycloak, no bug de código. Un
  intento de arreglarlo vía API (POST a `.../composites`) quedó bloqueado por el modo de permisos de
  la sesión; se le dieron los pasos para hacerlo a mano en la consola.
- **Bug real encontrado y corregido**: `apps/authentication/backends.py` nunca sobrescribía
  `get_username`, así que `mozilla_django_oidc` usaba su algoritmo por defecto — un hash SHA1 en
  base64 del email — como `User.username` local, en vez del username real de Keycloak. Se confirmó
  consultando la base real (`'U4Qc8ATyulSxHM7b6ZFlivqu_DI'` para la cuenta nueva de prueba, vs.
  usernames limpios para cuentas más viejas). Esto afectaba la UI (mostraba un hash/el email en vez
  de un nombre) y, potencialmente, `ClienteForm.save()` (que busca
  `User.objects.filter(username=identificador)` asumiendo que el username es real). Se agregó
  `get_username` (usa `preferred_username` del token), se corrigió a mano el registro ya afectado, y
  se sumó `test_get_username_usa_preferred_username_no_un_hash_del_email`.
- **Nombre mostrado en la UI**: `home.html`/`base.html`/`perfil.html` caían a `user.email` cuando no
  había `first_name` (ahora el caso normal, al no pedirse en el registro). Se corrigió la prioridad a
  `cliente_activo.nombre_completo` (el nombre real del `Cliente`, cuando lo tiene) → `user.first_name`
  (cuentas viejas/admin) → `user.username` (último recurso, nunca el email).
- **Redirección directa a "Solicitar cliente"**: un usuario con rol `cliente` sin ningún `Cliente`
  asociado ahora es redirigido desde `home` directo a `clientes:solicitar_cliente`
  (`global_exchange/views.py`), en vez de aterrizar en un panel general casi vacío con solo un link
  para hacer clic. Mismo criterio exacto que `puede_solicitar_cliente`, sin crear loops (un usuario ya
  con cliente nunca cumple la condición de redirección). Se actualizó
  `test_el_link_para_solicitar_aparece_solo_para_quien_corresponde` (ya no se prueba en `home`, que
  ahora redirige, sino en `tasas_vigentes`) y se agregaron
  `test_home_redirige_directo_a_solicitar_cliente_si_no_tiene_ninguno` y
  `test_home_no_redirige_a_un_admin_ni_a_quien_ya_tiene_cliente`.

Toda esta investigación se hizo con evidencia real en cada paso: lectura directa del jar de temas de
Keycloak, consultas a su API de administración (autenticado con las credenciales que compartió el
usuario — se le señaló explícitamente el riesgo de reusar la misma contraseña que su base de datos
Postgres), y los stack traces reales de la consola de Keycloak para cada error, nunca suposiciones.

29/29 en `test_clientes.py`, 12/12 en `test_auth.py`, Sphinx y `manage.py check` limpios, suite
completa de Django corrida de nuevo para la confirmación final.

### Ampliación de "Solicitud de cliente": jurídica, rol en Keycloak, aviso por email

Tres pedidos más sobre la misma feature, cada uno investigado antes de tocar código:

- **Soporte para persona jurídica**: `SolicitudCliente` ganó `tipo_cliente` y `razon_social` (mismos
  campos/validación condicional que `Cliente`/`ClienteForm`, con el mismo toggle JS en el formulario).
  `AprobarSolicitudClienteView` crea el `Cliente` del tipo correspondiente.
- **Bug real: el rol `cliente` nunca se asignaba en Keycloak al aprobar**. La aprobación asociaba el
  usuario al `Cliente` en Django (`cliente.usuarios.add(...)`), pero casi todos los permisos del
  sistema exigen además el rol `'cliente'` de Keycloak en la sesión — sin ese rol, el usuario queda
  con un `Cliente` asociado pero sin poder operar nada. Se reusó
  `apps.users.services.obtener_roles_de_usuario`/`actualizar_roles_de_usuario` (ya existente, usado
  por la pantalla de gestión de roles) para agregarle el rol al aprobar, contenido en un
  `try/except` que nunca rompe la aprobación si Keycloak falla o el usuario no tiene email — mismo
  criterio que `AsociarUsuariosClienteView._usuarios_cliente_ids`.
- **Pregunta sobre cierre de sesión**: los roles de Keycloak solo se sincronizan a la sesión de
  Django en el login (no hay `mozilla_django_oidc.middleware.SessionRefresh` instalado) — confirmado
  revisando `MIDDLEWARE` en `settings/base.py`. Se le explicó la opción real
  (`SessionRefresh` + `OIDC_RENEW_ID_TOKEN_EXPIRY_SECONDS`, revalidación periódica silenciosa) y el
  usuario eligió **no** agregarla por ahora — el fix del rol ya resuelve lo más importante.
- **Email de aviso al aprobar/rechazar**: se activó (el usuario pidió implementarlo). Nuevo
  `EMAIL_BACKEND` configurable vía `.env` en `global_exchange/settings/base.py` (sigue en "console"
  por defecto, igual que antes — nunca se completa una credencial real en el repo, mismo criterio que
  `FACTURASEGURA_*`). Nuevo `_notificar_resultado_solicitud` en `apps/clientes/views.py`, llamado
  desde ambas vistas, con el mismo criterio de contención de errores que el resto de esta HU. Django
  reemplaza el backend por uno en memoria durante los tests automáticamente, así que nunca se manda
  un correo real al correr la suite, sin importar la configuración real.

**Dos regresiones propias, encontradas y corregidas por la propia suite de tests** (no reportadas
por el usuario): la condición `puede_solicitar_cliente`, al ampliarla para no depender del rol
`'cliente'`, quedó dos veces mal calibrada en el camino — primero excluyendo solo a `admin` (lo que
mandaba erróneamente a "Solicitar cliente" a un `analista_cambiario` sin cliente, rol de personal, no
de cliente en potencia; detectado por `test_divisas.py`), después un ajuste intermedio que exigía
"ningún rol en absoluto" (lo que rompía el caso original: alguien con el rol `'cliente'` pero sin
`Cliente` todavía). La condición final, correcta: califica quien no tiene **ningún rol de negocio
distinto de `'cliente'`** (`not (set(roles) - {'cliente'}) and not es_admin and not tiene_cliente`) —
cubre tanto a quien no tiene ningún rol todavía como a quien ya tiene `'cliente'` sin `Cliente`
asociado, sin capturar a ningún otro rol de personal. También se ajustó `test_metodos_pago.py`
(`fetch_redirect_response=False`) porque el nuevo redirect de `home` hace que un "redirige a home"
ya no implique "home devuelve 200" para un usuario sin cliente.

Verificado en capas: 37/37 en `test_clientes.py`, 142/142 en los 7 archivos pytest, 137/137 en
`test_metodos_pago`/`test_operaciones` (los más expuestos a la regresión), `manage.py check` y
Sphinx limpios, suite completa de Django corrida de nuevo para la confirmación final.

## Sesión 26 — 30/10/2026 — La comisión se factura gravada al 10% de IVA (no exenta)

**Herramienta:** Claude Code (Anthropic, modelo Sonnet 5)
**HU relacionada:** Integración con API de facturación electrónica (ver Sesión 24)
**Rama:** `feature/GE-41`
**Participantes:** Rodrigo Mereles, integrante del equipo Global Exchange

### Pedido

Durante una revisión posterior a la Sesión 24, el usuario preguntó si la comisión de Global Exchange
se estaba incluyendo en el total facturado en compra, venta y cambio, y si esa comisión debía ir
gravada al 10% de IVA en vez de exenta. Antes de tocar código se investigó `_grupo_item_resumido`
original (un único ítem exento, `_monto_en_pyg`) y las funciones de cálculo de comisión en
`apps/divisas/views.py` (`_calcular_importe_operacion`, `_calcular_triangulacion`), y se reportaron
dos hallazgos, dejando la decisión tributaria (una cuestión real de legislación paraguaya, con
consecuencias fiscales) al usuario, no a una suposición propia:

1. En compra y venta, `monto_final` (lo ya facturado) **sí** incluye el efecto de la comisión (sumada
   en una compra, restada en una venta) — no había bug ahí.
2. En un cambio, sí había un bug real: se facturaba `monto_equivalente_pyg` (el bruto triangulado del
   Paso A, calculado en `_calcular_triangulacion`, **antes** de restar la comisión), en vez del monto
   ya neto de comisión — un cambio se facturaba de más, por el valor íntegro de la comisión.

El usuario confirmó ambos puntos: corregir el bug del cambio, y facturar la comisión como ítem
separado gravado al 10% de IVA (no exenta) en los tres tipos de operación.

### Diseño e implementación

`apps/divisas/factura_electronica.py`:

- `_monto_en_pyg` → renombrada `_total_en_pyg` y corregida para un cambio: ahora convierte
  `monto_final` (divisa de destino, ya neto de comisión) a PYG con `tasa_venta_aplicada` — la misma
  tasa del Paso B de `_calcular_triangulacion` — en vez de usar `monto_equivalente_pyg`.
- `_comision_en_pyg` (nueva): la comisión en PYG. En compra/venta ya está en PYG directamente
  (`comision`); en un cambio, `comision` está en la divisa de **destino** (Paso B), así que se
  convierte con la misma `tasa_venta_aplicada`.
- `_grupo_item_resumido` (un único ítem) → `_grupo_item` (un ítem genérico, exento o gravado al 10%
  según `afecta_iva`) + `_grupos_item_resumido` (arma la lista: comisión gravada + el resto exento,
  `base = total - comisión`, nunca el bruto calculado aparte, para que ambos ítems sumen exactamente
  el total ya corregido sin descuadres de redondeo). Si la comisión del cliente es 0% queda un único
  ítem exento, igual que antes de este cambio. El precio de un ítem gravado se manda tal cual
  (`dPUniProSer` = comisión, IVA incluido): es `calcular_de` quien calcula cuánto de ese precio es
  base y cuánto es IVA (`dBasGravIVA`/`dLiqIVAItem`), no hay que sumarle nada encima.
- `_armar_resumido_de` actualizada para usar `_grupos_item_resumido` (ahora una lista de ítems, no
  uno solo) en `gCamItem`.

`tests/test_factura_electronica.py`: nueva clase `ComisionGravadaAl10PorCientoTest` (4 casos) — compra
y venta separan correctamente la comisión del resto exento; el cambio usa el monto neto de comisión,
no el bruto triangulado (se verifica explícitamente que el total ya **no** coincide con
`monto_equivalente_pyg`); sin comisión (0%) sigue quedando un único ítem exento, sin romper ese caso
ya existente.

Sphinx (`docs/source/reference/apps.divisas.factura_electronica.rst`) actualizado con los símbolos
nuevos/renombrados. Verificado con `tests.test_factura_electronica` (39/39), `manage.py check` y la
suite completa de Django.

## Enlaces externos (conversaciones completas)

Extraído de `ia-CONVERSATION.TXT`. Son enlaces a conversaciones completas alojadas en claude.ai (no narrativas resumidas como las sesiones anteriores):

- https://claude.ai/share/1e0b2284-8306-4784-b3fc-59958b9b3521
- https://claude.ai/share/0833ff88-e361-47fd-b995-4de75e42967e
- https://claude.ai/share/ba4ccb60-e442-45dd-8dd0-432c0dabbbb6
- https://claude.ai/share/d8cc13fb-73f2-4e33-aa44-b2b2d49469a9
- https://claude.ai/share/bbeaa0dc-7e9b-49a2-83ef-91b1490745ca
- https://claude.ai/share/94ee15a3-3c2d-4ef3-9438-62394f576485

El mismo archivo incluía, junto a esos enlaces, un resumen pegado de una de esas conversaciones (sobre la resolución de un conflicto entre las suites de Pytest y Unittest del modelo `Cliente`), reproducido aquí por completitud:

> **Diagnóstico del conflicto inicial.** Se analizó el fallo entre Pytest (`TestClienteForm`, `TestClienteView`) y Unittest (`AsociacionUsuarioClienteTest`), identificando tres causas: (1) el modelo `Cliente` exige un usuario titular (`user`), pero el test de unittest creaba instancias de `Cliente` sin asignarlo, generando un `IntegrityError`; (2) el test accedía a una constante inexistente `Cliente.TIPO_FISICA` en vez de usar directamente la cadena `'FISICA'`; (3) el modelo en realidad combina dos relaciones distintas: un usuario titular obligatorio (`user`, vía CI/RUC) y una lista de operadores/usuarios asociados (`usuarios`, M2M).
>
> **Solución aplicada** en `AsociacionUsuarioClienteTest`: se agregó la creación de `user_titular` (`username='1234567'`) para pasarlo explícitamente a `Cliente.objects.create(...)`; se reemplazó `Cliente.TIPO_FISICA` por `'FISICA'`; se actualizaron las redirecciones y rutas (`reverse('panel_admin')`) para validar la visualización de usuarios asociados en el panel; se mantuvieron los 4 criterios de prueba intactos (asociación, listado en panel, revocación y seguridad/permisos).
