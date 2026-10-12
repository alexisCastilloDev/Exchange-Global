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
11. [Sesión 11 — 11/10/2026 — Gestión de operaciones en ventanilla](#sesión-11--11102026--gestión-de-operaciones-en-ventanilla)
12. [Sesión 12 — 11/10/2026 — Arqueo de Caja](#sesión-12--11102026--arqueo-de-caja)
13. [Enlaces externos (conversaciones completas)](#enlaces-externos-conversaciones-completas)

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

## Sesión 11 — 11/10/2026 — Gestión de operaciones en ventanilla

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

## Sesión 12 — 11/10/2026 — Arqueo de Caja

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
Caja" y Sesión 11 "Gestión de operaciones en ventanilla"): `Caja.saldo_actual(divisa)` ya existía
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
  (mismo criterio que `RegistrarOperacionVentanillaView`, Sesión 11). Al validar el formulario, por
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

## Sesión 13 — 12/10/2026 — GE-54 — Gestión de movimientos extraordinarios de Caja

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
construida en tres HU sucesivas (Sesión 10 "Apertura de Caja", Sesión 11 "Gestión de operaciones en
ventanilla", Sesión 12 "Arqueo de Caja"). Antes de tocar nada se investigó a fondo el estado actual:
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
  un mismo saldo derivado, sin que `ArqueoCaja`/`DetalleArqueoCaja` (Sesión 12) necesiten ningún
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
Sesión 12: el código real de los pagos con tarjeta vía Stripe ya está mergeado en `develop`, pero el
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
`CajaSaldoActualTest` ya usa en `test_operaciones_ventanilla.py` (Sesión 11).

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

## Sesión 14 — 12/10/2026 — GE-56 — Cierre de Caja

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

Esta sesión siguió directamente a la Sesión 13 (GE-54, "Gestión de movimientos extraordinarios de
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
poder cambiar desde el momento del cierre. A diferencia de `DetalleArqueoCaja` (Sesión 12), que
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
