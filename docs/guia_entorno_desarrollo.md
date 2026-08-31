# Guía del Entorno de Desarrollo — Global Exchange

Esta guía tiene tres partes:

- **Parte 1 — Preparar tu entorno paso a paso:** seguila en orden si sos nuevo en el proyecto, de punta a punta, sin saltar secciones.
- **Parte 2 — Referencia de conceptos:** para volver a consultar el "qué es y por qué" de cada herramienta cuando lo necesites, sin tener que releer todo.
- **Parte 3 — Solución de problemas comunes:** errores típicos que ya nos pasaron, con su causa y solución.

---

# PARTE 1 — Preparar tu entorno paso a paso

> **Antes de empezar:** no todos los integrantes necesitan instalar todo. Java solo hace falta si vas a trabajar en el **Epic 1** (autenticación) — y aun así, **Keycloak en sí NO hay que instalarlo en cada máquina**, el equipo decidió correrlo en una sola computadora que actúa como servidor compartido (ver Paso 3). Nginx solo hace falta si vas a validar específicamente el ambiente de producción. Para el día a día de programar, con Python + Git + VSCode + PostgreSQL alcanza.

## Paso 1 — Instalar las herramientas base

| Herramienta | Dónde bajarla | Detalle |
|---|---|---|
| **Python** | python.org (misma versión que usa el equipo) | En el instalador de Windows, tildar **"Add python.exe to PATH"** — si no lo tildás, después nada de esto funciona desde la terminal |
| **Git** | git-scm.com | Instalación con las opciones por defecto está bien |
| **VSCode** | code.visualstudio.com | Ver Paso 2 para las extensiones |
| **git-flow** (herramienta de línea de comandos, distinta de la extensión de VSCode) | Suele venir incluida con Git for Windows. Si no, `choco install git-flow-avh` con Chocolatey | Es lo que te permite usar `git flow feature start/finish` |
| **PostgreSQL** | postgresql.org/download (incluye pgAdmin) | Durante la instalación te va a pedir una contraseña para el usuario `postgres` — **anotala en un lugar seguro**, la vas a necesitar en tu `.env` (Paso 5). Ver nota importante en el Paso 1.1 |

### Paso 1.1 — Agregar PostgreSQL al PATH

El instalador de Windows no siempre agrega Postgres al PATH automáticamente, y sin esto, comandos como `createdb` o `psql` no funcionan desde la terminal.

1. Menú Inicio → "Variables de entorno" → "Editar las variables de entorno del sistema" → botón "Variables de entorno...".
2. En "Variables del sistema", seleccioná `Path` → "Editar..." → "Nuevo" → agregá la ruta a la carpeta `bin` de tu instalación, típicamente `C:\Program Files\PostgreSQL\<versión>\bin` (fijate qué número de versión te quedó instalado).
3. **Cerrá todas las terminales abiertas y abrí una nueva** (las ya abiertas no ven el PATH actualizado).
4. Verificar: `createdb --version` debería mostrar la versión en vez de "no se reconoce el comando".

## Paso 2 — Instalar las extensiones de VSCode

Abrí VSCode → pestaña Extensions (ícono de cuadraditos en la barra lateral) → buscá e instalá cada una:

| Extensión | Para qué sirve |
|---|---|
| **Python** (Microsoft) | Soporte base: resaltado de sintaxis, selección de intérprete/venv, debug |
| **Pylance** | Se instala junto con Python; autocompletado y detección de errores en tiempo real |
| **Django** | Resaltado de sintaxis para templates y autocompletado de tags/filtros |
| **Gitflow** | Corré comandos `git flow` desde la paleta de comandos de VSCode |
| **autoDocstring** | Genera automáticamente la plantilla de un docstring al escribir `"""` — ver Parte 2, sección "Docstrings" |
| **GitLens** / **GitHub Pull Requests** | Ver historial de cambios línea por línea y gestionar Pull Requests desde el editor |

**Confirmar el intérprete correcto:** una vez que tengas el proyecto clonado (Paso 4), fijate abajo a la derecha de VSCode que diga `Python (...): ('.venv': venv)`. Si dice otra cosa, hacé clic ahí (o `Ctrl+Shift+P` → "Python: Select Interpreter") y elegí el de `.venv`.

## Paso 3 — Keycloak (servidor compartido, NO se instala en cada máquina)

**Decisión del equipo:** Keycloak corre en **una sola computadora** designada como servidor, no en la máquina de cada integrante. Si no sos quien administra esa computadora, saltá directo al Paso 4 — solo vas a necesitar la URL, Realm y credenciales que te pase quien lo armó (ver variables `KEYCLOAK_*` en el Paso 5).

**Si sos quien administra el servidor de Keycloak:**

1. Instalar un **JDK 17 o superior** (recomendado: Eclipse Temurin desde adoptium.net).
2. Configurar la variable de entorno `JAVA_HOME` apuntando a la carpeta de instalación del JDK (Panel de Control → Variables de entorno).
3. **Cerrar todas las terminales abiertas y abrir una nueva** — las terminales ya abiertas no ven variables de entorno agregadas después de abrirlas, es la causa más común de que "no funcione" cuando en realidad sí quedó bien configurado.
4. Verificar: `java -version` debería mostrar la versión del JDK que instalaste (si te sigue mostrando una versión vieja como 1.8, revisá que no haya una instalación anterior de Java compitiendo en el PATH del sistema).
5. Descargar Keycloak desde keycloak.org/downloads (versión standalone, sin Docker) y descomprimir en una carpeta simple, ej. `C:\Herramientas_IS2\keycloak`.
6. Levantarlo: parado en la carpeta `bin` de Keycloak, `.\kc.bat start-dev`. Queda escuchando en `http://localhost:8080` de esa máquina.
7. **Crear el usuario administrador** (solo la primera vez que se levanta Keycloak): la propia consola web en `http://localhost:8080` te va a pedir crear un usuario admin la primera vez que entrás — completá usuario y contraseña y guardalo en un lugar seguro, es el que usás para entrar a administrar Keycloak en sí (no tiene nada que ver con los usuarios del sistema Django).
8. **Crear el Realm del proyecto:**
   - Iniciá sesión en la consola con el admin que acabás de crear.
   - Arriba a la izquierda, donde dice "master" (o el nombre del Realm actual), desplegá y elegí "Create Realm".
   - Nombre: `global-exchange`. El campo "Resource file" se deja vacío (solo sirve para importar un Realm ya existente desde un JSON). Crear.
   - Confirmá que el selector de arriba a la izquierda ahora muestre `global-exchange` en vez de `master` — todo lo que sigue se hace parado en ese Realm, no en `master`.
9. **Crear el Client para Django**, dentro del Realm `global-exchange`:
   - Menú lateral → "Clients" → "Create client".
   - Client type: dejar "OpenID Connect" (por defecto). Client ID: `global-exchange-django`. El campo "Name" es solo descriptivo, opcional. Siguiente.
   - Activar el switch "Client authentication" → ON (lo hace confidencial, con secret propio — correcto para una app backend). Dejar tildado "Standard flow" y "Direct access grants". Siguiente.
   - Valid redirect URIs: `http://localhost:8000/*` y `http://127.0.0.1:8000/*`. Web origins: los mismos dos valores, o `+` para que tome las mismas que las redirect URIs. Guardar.
   - Entrar a la pestaña "Credentials" del Client recién creado y copiar el **Client Secret** generado — este es el valor que va al `.env` de todo el equipo (variable `KEYCLOAK_CLIENT_SECRET`), nunca en el código ni en el repo.
10. **Crear los roles**, dentro del Realm:
    - Menú lateral → "Realm roles" → "Create role".
    - Crear al menos dos: `admin` y `cliente` (los roles básicos usados en las HU de autorización del Epic 1).
11. **Crear un usuario de prueba**, dentro del Realm:
    - Menú lateral → "Users" → "Add user". Completar username y email (ej. `usuario.prueba` / `prueba@test.com`). Guardar.
    - Entrar a la pestaña "Credentials" de ese usuario y ponerle una contraseña — destildar "Temporary" si no querés que pida cambiarla en el primer login.
    - Entrar a la pestaña "Role mapping" del usuario, "Assign role", y asignarle uno de los roles creados (ej. `cliente`).
    - Esto es evidencia/entregable del alcance del sprint ("demostración de creación de usuario y roles") — sacar una captura del Realm con los roles y del usuario con su rol asignado, y guardarla en `docs/` (por ejemplo `docs/evidencia-keycloak-roles.png`).
12. Para que el resto del equipo se conecte, necesitan la **IP local de tu máquina** en la red (no `localhost`, que en la máquina de cada uno apunta a sí misma). Verla con `ipconfig` → buscar "Dirección IPv4".
13. Pasarle al equipo, por un canal privado (nunca por el repo): la IP, el Realm, el Client ID y el Client Secret.

## Paso 4 — Clonar el proyecto y armar el entorno virtual

```bash
# Clonar el repositorio
git clone <url-del-repo>
cd IS2_REPO

# Crear tu propio entorno virtual (aislado, solo para este proyecto)
python -m venv .venv

# Activarlo
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Mac/Linux

# Vas a saber que está activo porque el prompt de tu terminal
# empieza con (.venv)

# Instalar todas las librerías que el proyecto necesita
pip install -r requirements.txt
```

**Por qué cada uno crea su propio `.venv` y no se comparte:** el `.venv` no se sube a Git (está en `.gitignore`) porque depende del sistema operativo de cada uno y puede pesar cientos de MB. En cambio, `requirements.txt` sí se sube — es la "receta" con la lista exacta de qué instalar, y cada integrante la usa para generar su propio entorno idéntico en resultado, aunque el archivo físico sea distinto en cada máquina.

## Paso 5 — Configurar tu propio archivo `.env`

Este es el paso donde más dudas suelen surgir, así que vamos con calma.

### 5.1 — Qué es y por qué existe

El `.env` guarda datos que son **sensibles** (contraseñas, claves secretas) o que **cambian según la máquina** de cada uno (por ejemplo, la contraseña que VOS elegiste para tu Postgres local, que no tiene por qué ser la misma que la de un compañero). Por eso nunca se sube a Git — está en `.gitignore`, y si lo abrís vas a ver que Git ni te lo muestra como archivo para commitear.

Lo que sí está en el repo es `.env.example`: una plantilla con las mismas claves pero sin los valores reales, para que cada uno sepa qué variables tiene que definir.

> ⚠️ **Cuidado al editar el `.env`:** no dejes espacios alrededor del `=` ni al final de cada línea (`DB_NAME= global_exchange` o `DB_NAME=global_exchange ` con espacio invisible al final rompen la conexión de forma silenciosa y confusa — ya nos pasó, ver Parte 3).

### 5.2 — Copiar la plantilla

```bash
copy .env.example .env          # Windows
cp .env.example .env            # Mac/Linux
```

### 5.3 — Completar cada variable

Abrí tu `.env` recién creado y completalo variable por variable:

**`DJANGO_SETTINGS_MODULE`**
```
DJANGO_SETTINGS_MODULE=global_exchange.settings.dev
```
Igual para todos — así arrancás siempre en modo desarrollo por defecto. (Los scripts de la Parte 1, Paso 8 cambian esta línea automáticamente al alternar entre dev y prod, no hace falta editarla a mano en el día a día.)

**`SECRET_KEY` — generá la tuya propia, nunca copies la de otro integrante**

Esta es la clave que Django usa internamente para firmar cosas como cookies de sesión y tokens. Que cada integrante tenga la suya (en vez de compartir una sola) es una práctica de seguridad básica: si en algún momento la clave de uno se filtra o queda expuesta, solo compromete el entorno de esa persona, no el de todo el equipo. Además, técnicamente no hay ningún motivo para que coincidan — cada `.env` es completamente local a la máquina de cada uno, así que compartirla no aporta nada, solo agrega riesgo innecesario.

Para generar la tuya, con el venv activado:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```
Esto te va a imprimir una cadena larga de caracteres — copiala tal cual (con backslashes, símbolos, etc., no la alteres) y pegala, sin espacios antes ni después del `=`:
```
SECRET_KEY=lo-que-te-generó-el-comando-de-arriba
```

**`ALLOWED_HOSTS`**
```
ALLOWED_HOSTS=localhost,127.0.0.1
```
Igual para todos.

**Datos de PostgreSQL — bases separadas para dev y prod, tu propia contraseña**

El proyecto usa PostgreSQL tanto en desarrollo como en producción, pero con **bases separadas** para no mezclar datos de prueba con datos "reales": `global_exchange_dev` y `global_exchange`.

```
DB_NAME_DEV=global_exchange_dev
DB_NAME_PROD=global_exchange
DB_USER=postgres
DB_PASSWORD=la-contraseña-que-VOS-elegiste-al-instalar-postgres-en-el-paso-1
DB_HOST=localhost
DB_PORT=5432
```

`DB_NAME_DEV`, `DB_NAME_PROD`, `DB_USER`, `DB_HOST` y `DB_PORT` pueden coincidir entre todos sin problema (son solo convenciones de nombre, no datos secretos). Pero `DB_PASSWORD` **tiene que ser la que vos definiste** al instalar tu propio PostgreSQL en el Paso 1 — cada Postgres es una instalación independiente en cada máquina, con su propia contraseña, así que usar la de otro compañero directamente no te va a funcionar.

**Variables de Keycloak — las mismas para todo el equipo (servidor compartido)**

Como Keycloak corre en una sola máquina servidor (Paso 3), estas variables **son iguales para todos**, no cada uno genera las suyas. Pedíselas a quien administra el servidor, por un canal privado:

```
KEYCLOAK_SERVER_URL=http://<ip-de-la-máquina-servidor>:8080
KEYCLOAK_REALM=global-exchange
KEYCLOAK_CLIENT_ID=global-exchange-django
KEYCLOAK_CLIENT_SECRET=<el-secret-que-te-pasaron>
```

Si no te toca trabajar en Epic 1 todavía, podés dejar estas variables vacías por ahora.

## Paso 6 — Crear tu base de datos de desarrollo y aplicar migraciones

```bash
# Crear la base de datos de DESARROLLO (cada integrante crea la suya local):
createdb -U postgres --encoding UTF8 --template template0 global_exchange_dev
# Te va a pedir la contraseña que definiste al instalar Postgres

# Aplicar las migraciones del proyecto a tu base recién creada
python manage.py migrate
```

> **Por qué `--encoding UTF8 --template template0`:** en instalaciones de Postgres con configuración regional en español, la base puede crearse por defecto con una codificación distinta a UTF-8, lo que después rompe la conexión con un error críptico de `UnicodeDecodeError`. Especificarlo explícitamente al crear la base evita ese problema de raíz (ver Parte 3 si ya te pasó).

La base `global_exchange` (prod) normalmente no la creás vos — la administra quien gestione el ambiente de producción del equipo.

## Paso 7 — Verificar que todo funciona

```bash
python manage.py runserver
```
Entrá a `http://127.0.0.1:8000` en el navegador y confirmá que carga la página de bienvenida de Django.

```bash
pytest
```
Debería mostrarte `1 passed` (o más, a medida que se sumen tests).

Si ambos comandos funcionan sin errores, tu entorno quedó configurado correctamente y ya podés empezar a trabajar en tu HU asignada.

## Paso 8 — (Opcional) Instalar los scripts de atajo

Para no tener que escribir todos los comandos a mano cada vez que cambiás de ambiente o levantás Keycloak, el proyecto incluye cuatro scripts de PowerShell y una configuración de tareas de VSCode.

**8.1 — Copiar los scripts:**

Creá una carpeta `scripts/` en la raíz del repo (si no existe) y poné ahí `keycloak-start.ps1`, `run-dev.ps1`, `run-prod.ps1` y `run-tests.ps1`. Ajustá las rutas (`$keycloakBin`, `$nginxPath`) al principio de cada script si tu instalación está en otro lado.

**8.2 — Crear `.vscode/tasks.json`:**

La carpeta `.vscode/` ya existe en el repo (ahí vive `settings.json` con la config de pytest). Si no tenés `tasks.json` todavía:
- Desde el explorador de VSCode: clic derecho sobre `.vscode` → "New File..." → `tasks.json` → pegar el contenido.
- O desde la terminal: `New-Item -Path ".vscode\tasks.json" -ItemType File -Force` y después `code .vscode\tasks.json` para abrirlo y pegar el contenido.

**8.3 — Permitir la ejecución de scripts (una sola vez por máquina):**

PowerShell bloquea por defecto la ejecución de scripts `.ps1` no firmados. Abrí PowerShell **como administrador** una única vez y corré:
```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```
Esto permite correr scripts locales (como los nuestros) sin comprometer la seguridad frente a scripts descargados de internet.

**8.4 — Usarlos:**

Desde VSCode: `Ctrl+Shift+P` → escribir "Run Task" → Enter → elegir una de las tareas disponibles:

| Tarea | Qué hace |
|---|---|
| **Modo Desarrollo (runserver)** | Activa el venv, cambia el `.env` a `dev`, levanta `runserver` |
| **Modo Produccion (Uvicorn)** | Activa el venv, cambia el `.env` a `prod`, corre `collectstatic`, levanta Nginx (en ventana nueva) + Uvicorn |
| **Levantar Keycloak** | Corre `kc.bat start-dev` sin que tengas que recordar la ruta (solo en la máquina servidor) |
| **Correr tests (pytest)** | Activa el venv y corre `pytest` |

También podés correrlos manualmente sin pasar por VSCode:
```powershell
.\scripts\run-dev.ps1
.\scripts\run-prod.ps1
.\scripts\run-tests.ps1
.\scripts\keycloak-start.ps1
```

---

# PARTE 2 — Referencia de conceptos

## 2.1 — Entorno virtual (`.venv`)

Una copia aislada de Python solo para este proyecto. Las librerías que instalás quedan encerradas ahí, sin mezclarse con otros proyectos ni con el Python del sistema. Regla de oro: todo comando de Python/Django/pip que corras debe ser con el venv activado (vas a ver `(.venv)` al inicio del prompt de tu terminal).

## 2.2 — `requirements.txt`

La lista exacta de todas las librerías (y sus versiones) que el proyecto necesita. Cuando instalás algo nuevo:
```bash
pip install <libreria>
pip freeze > requirements.txt
```
Y tus compañeros instalan todo con `pip install -r requirements.txt`.

## 2.3 — Git y Gitflow

**Ramas principales:**
- `main` → código en producción. Solo recibe merges de `develop` al cerrar un sprint, con un tag de versión (ej. `v1.0-sprint1`).
- `develop` → rama de integración, donde se juntan todas las funcionalidades ya terminadas.
- `feature/<id-HU>` → una rama por cada historia de usuario, sale de `develop` y vuelve a `develop` al terminar.

**Flujo típico usando la extensión `git flow`:**
```bash
git checkout develop
git pull
git flow feature start GE-XX
# ... trabajás, commits normales ...
git push origin feature/GE-XX
git flow feature finish GE-XX
git push origin develop
```

**Al cerrar el sprint:**
```bash
git flow release start v1.0-sprint1
git flow release finish v1.0-sprint1
git push origin main develop --tags
```

## 2.4 — Estructura del proyecto Django

```
IS2_REPO/
├── global_exchange/          ← el "proyecto" (config general)
│   ├── settings/
│   │   ├── base.py           ← configuración compartida (SECRET_KEY, apps, middleware, etc.)
│   │   ├── dev.py            ← hereda de base, DEBUG=True, Postgres (global_exchange_dev)
│   │   └── prod.py           ← hereda de base, DEBUG=False, Postgres (global_exchange), seguridad extra
│   ├── urls.py
│   ├── wsgi.py / asgi.py
├── clientes/, usuarios/, etc.  ← una "app" por cada dominio de negocio
├── scripts/                    ← scripts de atajo (Paso 8)
├── tests/
├── manage.py
└── requirements.txt
```

**Proyecto vs. App:** el proyecto (`global_exchange`) es el contenedor general. Las apps son módulos independientes (uno por dominio: clientes, usuarios, etc.) registrados en `INSTALLED_APPS` dentro de `base.py`.

**Sobre `base.py`/`dev.py`/`prod.py` y `django-environ`:** los tres usan **exclusivamente** `django-environ` (`import environ`) para leer el `.env` — se sacó `python-decouple`, que se había usado en un momento y quedó generando código duplicado/confuso. `env = environ.Env()` se define una sola vez en `base.py`, y como `dev.py`/`prod.py` hacen `from .base import *`, pueden usar `env(...)` directamente sin volver a inicializarlo. `SECRET_KEY` vive en `base.py` (es la misma para toda la máquina); `DEBUG`, `ALLOWED_HOSTS` y `DATABASES` viven en `dev.py`/`prod.py` porque difieren entre ambientes.

## 2.5 — Ambientes: desarrollo vs. producción

El mismo código corre distinto según el contexto:

| | `dev.py` | `prod.py` |
|---|---|---|
| `DEBUG` | `True` (errores detallados) | `False` (oculta detalles internos) |
| Base de datos | PostgreSQL — `global_exchange_dev` | PostgreSQL — `global_exchange` |
| Servidor | `runserver` | Nginx + Uvicorn |

**Por qué Postgres en ambos y no SQLite en dev:** se decidió usar el mismo motor de base de datos en los dos ambientes (con bases separadas) para evitar diferencias de comportamiento entre SQLite y Postgres que solo aparecerían recién en producción.

**Cadena en producción:**
```
navegador → Nginx (puerto 80) → Uvicorn (puerto 8000) → Django (asgi.py) → PostgreSQL
```
Nginx recibe la petición primero y se la reenvía a Uvicorn por detrás; también sirve los archivos estáticos directamente. Ni `base.py`, `dev.py`, `prod.py`, `wsgi.py` ni `asgi.py` se tocan para esto — Django ya genera `asgi.py` automáticamente. Nginx no vive dentro del repo (se instala aparte en el sistema); sí conviene guardar el `nginx.conf` usado en `docs/` como referencia.

**Nota sobre Nginx:** cuando lo levantás (manualmente o vía script), la ventana queda "en negro" sin mostrar texto después del mensaje inicial — es normal, Nginx en Windows no imprime logs en consola por defecto, simplemente queda escuchando en segundo plano. Para ver actividad en tiempo real: `Get-Content <ruta-nginx>\logs\access.log -Tail 10 -Wait` desde otra terminal.

En el día a día siempre estás en modo desarrollo. El de producción se prueba puntualmente para confirmar que el sistema también funciona con `DEBUG=False`, Postgres, y la stack Nginx+Uvicorn.

## 2.6 — Keycloak

El servidor externo que maneja usuarios, login y roles — Django no tiene su propia tabla de usuarios con contraseñas, todo vive en Keycloak. **El equipo decidió correr una sola instancia compartida**, en una máquina designada como servidor, no una por integrante. El paso a paso completo de instalación y configuración (Realm, usuario admin, Client, roles, usuario de prueba) está en la **Parte 1, Paso 3** — acá solo quedan los conceptos de referencia rápida.

**Conceptos:**
- **Realm**: el espacio aislado del proyecto (`global-exchange`), separado del Realm `master` que es solo para administrar Keycloak en sí.
- **Usuario admin de Keycloak**: se crea una única vez, la primera vez que se levanta el servidor — administra Keycloak en sí, no tiene relación con los usuarios del sistema Django.
- **Client**: la "aplicación" registrada dentro del Realm (en este caso, Django: `global-exchange-django`), con su propio Client ID y Client Secret.
- **Roles**: permisos asignables a usuarios (`admin`, `cliente`).
- **Usuario de prueba**: un usuario creado dentro del Realm con un rol asignado, usado como evidencia de que la configuración funciona.

**Qué es config de entorno y qué es HU real:** levantar el servidor y crear Realm/Client/roles/usuario de prueba es preparación de infraestructura (como instalar Postgres) — no se testea con pytest ni se mergea como código, es evidencia/entregable del alcance del sprint. Conectar Django con esto (`mozilla-django-oidc`, vistas de login/callback/registro) sí es desarrollo real de las HU del Epic 1, con sus tests correspondientes.

## 2.7 — `.env` y `django-environ`

`.env` guarda datos sensibles o específicos de cada máquina, nunca se sube a Git. `.env.example` es la plantilla sin valores reales, que sí se sube. `django-environ` es la librería que lee el `.env` y lo convierte en variables usables por Django (`env('SECRET_KEY')`); sin ella, Django no sabe que el `.env` existe. (El proyecto usó brevemente `python-decouple` también, pero se unificó todo a `django-environ` — ver 2.4.)

## 2.8 — `pytest` y `pytest.ini`

`pytest` ejecuta las pruebas unitarias. `pytest-django` le enseña a pytest a entender un proyecto Django. `pytest.ini` le dice a pytest dónde está tu `settings.py` y qué archivos considerar tests — sin él, pytest no sabría que el proyecto es Django.

```bash
pytest                    # corre todos los tests
pytest clientes/tests/    # solo una app
pytest -v                 # modo detallado
```

Los tests se escriben junto con el código, a medida que programás cada funcionalidad — no se dejan para "hacer al final".

## 2.9 — `staticfiles/` y `collectstatic`

Django separa los archivos estáticos que trae cada app por defecto (como el panel de admin) de los que suma el proyecto. `collectstatic` los junta a todos en una carpeta (`staticfiles/`) para que un servidor de producción los sirva eficientemente. Es contenido generado, no se versiona en Git.

## 2.10 — Docstrings y autoDocstring

Un docstring es un comentario especial que explica qué hace una función/clase, qué recibe y qué devuelve — a diferencia de un comentario común, herramientas como VSCode o Sphinx lo leen automáticamente.

```python
def registrar_cliente(nombre, documento, email):
    """
    Registra un nuevo cliente en el sistema.

    Args:
        nombre (str): Nombre o razón social del cliente.
        documento (str): Cédula o RUC del cliente.
        email (str): Correo electrónico de contacto.

    Returns:
        Cliente: la instancia del cliente recién creado.
    """
```

Con la extensión autoDocstring: escribís la función completa, te parás en la línea de abajo de la definición, escribís `"""` y apretás Enter (o `Ctrl+Shift+2`) — se genera la plantilla automáticamente con los parámetros detectados.

## 2.11 — Sphinx (documentación automática — PDO)

Lee los docstrings del código y genera un sitio HTML navegable con la documentación técnica del proyecto.

```bash
# Si agregaste una app NUEVA, regenerar los .rst primero (desde la raíz):
sphinx-apidoc -o docs/source .

# Generar/actualizar el sitio HTML (parado dentro de docs/):
.\make.bat html        # Windows
make html               # Mac/Linux
```

Ver el resultado en `docs/build/html/index.html`. Si solo agregaste docstrings a una app que ya existía, alcanza con `make html`, sin repetir `sphinx-apidoc`.

## 2.12 — Carpeta CHIA (`docs/ai-conversations/`)

Cada conversación relevante con una herramienta de IA que aportó a una decisión o solución del proyecto se guarda como un `.md` en esta carpeta, con nombre `AAAA-MM-DD-tema-breve.md`. No hace falta documentar cada pregunta chica, sí las que influyeron en decisiones concretas.

## 2.13 — Scripts de atajo y tareas de VSCode

Automatizan lo que antes había que hacer a mano cada vez que se cambiaba de ambiente:

- **`scripts/run-dev.ps1`**: activa el venv, reemplaza automáticamente la línea `DJANGO_SETTINGS_MODULE` del `.env` por `.dev` y levanta `runserver`.
- **`scripts/run-prod.ps1`**: activa el venv, la reemplaza por `.prod`, corre `collectstatic`, levanta Nginx en una ventana nueva y Uvicorn en la actual.
- **`scripts/run-tests.ps1`**: activa el venv y corre `pytest`.
- **`scripts/keycloak-start.ps1`**: evita tener que recordar la ruta de instalación y el comando `kc.bat start-dev` cada vez (solo lo usa quien administra el servidor de Keycloak).
- **`.vscode/tasks.json`**: expone estos cuatro scripts como tareas de VSCode, accesibles con `Ctrl+Shift+P` → "Run Task", sin pasar por la terminal manualmente.

Requieren una única configuración por máquina la primera vez: `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser` desde PowerShell como administrador, ya que Windows bloquea por defecto la ejecución de scripts `.ps1` no firmados.

**Por qué cada script activa el venv explícitamente:** las tareas de VSCode abren una PowerShell nueva que no hereda el venv activado en otra terminal — sin esa línea, comandos como `python` o `pytest` fallarían con "módulo no encontrado" o "comando no reconocido" aunque el venv esté bien instalado.

**Por qué los scripts no tienen acentos ni tildes en los textos:** PowerShell 5.1 (la versión clásica de Windows) espera los `.ps1` guardados en UTF-8 con BOM; si se guardan en UTF-8 sin BOM (algo común al copiar/pegar texto), los caracteres acentuados se corrompen y rompen la sintaxis del script. Para evitar ese problema de raíz, los scripts se escriben sin tildes.

---

# PARTE 3 — Solución de problemas comunes

Errores que ya nos aparecieron mientras armábamos el entorno, con su causa real (no siempre es la que parece a primera vista).

| Síntoma | Causa real | Solución |
|---|---|---|
| `ModuleNotFoundError: No module named 'environ'` (o cualquier otro módulo) al correr una tarea de VSCode | La tarea abrió una PowerShell nueva sin el venv activado | Usar los scripts de la Parte 1, Paso 8 (ya activan el venv), o activar manualmente antes de correr el comando |
| `pytest.ini: unexpected value continuation` | Una línea del archivo (a veces la primera) tiene un espacio o backtick de más, generalmente por copiar el bloque de código con ` ``` ` incluido | Reescribir el archivo a mano sin backticks ni espacios al inicio de línea |
| Errores de Pylance tipo "Expressions surrounded by backticks are not supported" en un `.py` | Se copió el bloque de código completo (con ` ```python ` y ` ``` `) en vez de solo el código | Dejar únicamente el código Python en el archivo, sin los backticks del formato Markdown |
| `Could not create the Java Virtual Machine` al correr `kc.bat` | Falta el JDK correcto o `JAVA_HOME` no está bien configurado, o la terminal es vieja y no ve la variable nueva | Instalar JDK 17+, configurar `JAVA_HOME`, y **abrir una terminal nueva** (las ya abiertas no ven variables de entorno agregadas después) |
| `$env:JAVA_HOME` da error de sintaxis rara | Se está usando CMD en vez de PowerShell (`$env:` es sintaxis de PowerShell) | Abrir específicamente una ventana de PowerShell, no CMD |
| `createdb`/`psql` no reconocidos como comando | Postgres no está en el PATH de Windows | Ver Paso 1.1 |
| `waitress`/`uvicorn` responde "conexión terminada" en `curl` pero funciona en el navegador | Antivirus o extensión del navegador (ej. Brave Shields en un perfil personal) interceptando la conexión | Probar en el navegador directamente, o en otro perfil/navegador |
| Conexión rechazada solo en un perfil de navegador, no en otro | Extensiones de privacidad (bloqueadores de ads/trackers) activas en ese perfil interfiriendo con `localhost` | Probar en el otro perfil, o desactivar la extensión para `localhost` |
| `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xab` al conectar a Postgres | Puede ser (a) la base se creó con una codificación distinta a UTF-8 por la configuración regional de Windows, y/o (b) valores del `.env` con espacios de más alrededor del `=` o al final de la línea | Recrear la base con `createdb --encoding UTF8 --template template0`, y revisar que ninguna línea del `.env` tenga espacios extra |
| Nginx muestra una ventana negra sin texto después de arrancar | Comportamiento normal — Nginx en Windows no imprime logs en consola por defecto | Confirmar que funciona probando `http://localhost` en el navegador, o mirando `logs\access.log` |
| Script `.ps1` tira error de sintaxis en una línea con acentos (ej. "Falta la cadena en el terminador") | El archivo se guardó en una codificación que no es UTF-8 con BOM, y los caracteres acentuados corrompen la cadena de texto | Guardar el archivo en UTF-8 con BOM, o evitar acentos/tildes en los textos del script |
| Error de `nginx.conf`: `"location" directive is not allowed here` | Llaves `{ }` mal cerradas — el bloque `server { }` se cerró antes de tiempo, dejando un `location` suelto fuera de cualquier `server` | Revisar que haya exactamente un `}` de cierre después de todo el contenido del bloque `server`, no en el medio |
