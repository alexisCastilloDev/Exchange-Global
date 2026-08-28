# Guía del Entorno de Desarrollo — Global Exchange

Esta guía tiene dos partes:

- **Parte 1 — Preparar tu entorno paso a paso:** seguila en orden si sos nuevo en el proyecto, de punta a punta, sin saltar secciones.
- **Parte 2 — Referencia de conceptos:** para volver a consultar el "qué es y por qué" de cada herramienta cuando lo necesites, sin tener que releer todo.

---

# PARTE 1 — Preparar tu entorno paso a paso

> **Antes de empezar:** no todos los integrantes necesitan instalar todo. Java + Keycloak solo hace falta si vas a trabajar en el **Epic 1** (autenticación). Nginx solo hace falta si vas a validar específicamente el ambiente de producción. Para el día a día de programar, con Python + Git + VSCode + PostgreSQL alcanza. Si no sabés si te toca, preguntale a quien reparte las HU.

## Paso 1 — Instalar las herramientas base

| Herramienta | Dónde bajarla | Detalle |
|---|---|---|
| **Python** | python.org (misma versión que usa el equipo) | En el instalador de Windows, tildar **"Add python.exe to PATH"** — si no lo tildás, después nada de esto funciona desde la terminal |
| **Git** | git-scm.com | Instalación con las opciones por defecto está bien |
| **VSCode** | code.visualstudio.com | Ver Paso 2 para las extensiones |
| **git-flow** (herramienta de línea de comandos, distinta de la extensión de VSCode) | Suele venir incluida con Git for Windows. Si no, `choco install git-flow-avh` con Chocolatey | Es lo que te permite usar `git flow feature start/finish` |
| **PostgreSQL** | postgresql.org/download (incluye pgAdmin) | Durante la instalación te va a pedir una contraseña para el usuario `postgres` — **anotala en un lugar seguro**, la vas a necesitar en tu `.env` (Paso 5) |

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

## Paso 3 — Instalar Java + Keycloak (SOLO si trabajás en Epic 1)

Si no te toca esta parte, saltá directo al Paso 4.

1. Instalar un **JDK 17 o superior** (recomendado: Eclipse Temurin desde adoptium.net).
2. Configurar la variable de entorno `JAVA_HOME` apuntando a la carpeta de instalación del JDK (Panel de Control → Variables de entorno).
3. **Cerrar todas las terminales abiertas y abrir una nueva** — las terminales ya abiertas no ven variables de entorno agregadas después de abrirlas, es la causa más común de que "no funcione" cuando en realidad sí quedó bien configurado.
4. Verificar: `java -version` debería mostrar la versión del JDK que instalaste (si te sigue mostrando una versión vieja como 1.8, revisá que no haya una instalación anterior de Java compitiendo en el PATH del sistema).
5. Descargar Keycloak desde keycloak.org/downloads (versión standalone, sin Docker) y descomprimir en una carpeta simple, ej. `C:\Herramientas\keycloak`.
6. Levantarlo: parado en la carpeta `bin` de Keycloak, `.\kc.bat start-dev`. Queda escuchando en `http://localhost:8080`.
7. **Definir con el equipo si van a compartir una sola instancia de Keycloak o si cada uno levanta la suya** (ver el detalle de esta decisión en el Paso 5, variables `KEYCLOAK_*`).

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
Igual para todos — así arrancás siempre en modo desarrollo por defecto.

**`SECRET_KEY` — generá la tuya propia, nunca copies la de otro integrante**

Esta es la clave que Django usa internamente para firmar cosas como cookies de sesión y tokens. Que cada integrante tenga la suya (en vez de compartir una sola) es una práctica de seguridad básica: si en algún momento la clave de uno se filtra o queda expuesta, solo compromete el entorno de esa persona, no el de todo el equipo. Además, técnicamente no hay ningún motivo para que coincidan — cada `.env` es completamente local a la máquina de cada uno, así que compartirla no aporta nada, solo agrega riesgo innecesario.

Para generar la tuya, con el venv activado:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```
Esto te va a imprimir una cadena larga de caracteres — copiala tal cual (con backslashes, símbolos, etc., no la alteres) y pegala:
```
SECRET_KEY=lo-que-te-generó-el-comando-de-arriba
```

**`DEBUG` y `ALLOWED_HOSTS`**
```
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```
Igual para todos, mientras trabajen en modo desarrollo.

**Datos de PostgreSQL — usá TU propia contraseña, no la de un compañero**

```
DB_NAME=global_exchange
DB_USER=postgres
DB_PASSWORD=la-contraseña-que-VOS-elegiste-al-instalar-postgres-en-el-paso-1
DB_HOST=localhost
DB_PORT=5432
```

`DB_NAME`, `DB_USER`, `DB_HOST` y `DB_PORT` pueden coincidir entre todos sin problema (son solo convenciones de nombre, no datos secretos). Pero `DB_PASSWORD` **tiene que ser la que vos definiste** al instalar tu propio PostgreSQL en el Paso 1 — cada Postgres es una instalación independiente en cada máquina, con su propia contraseña, así que usar la de otro compañero directamente no te va a funcionar (le vas a estar apuntando a la base de datos de OTRA persona, que ni siquiera es accesible desde tu máquina).

**Variables de Keycloak — depende de una decisión de equipo**

Antes de completar esto, el equipo tiene que definir una de estas dos opciones:

| Opción | Cómo se completa el `.env` |
|---|---|
| **A) Un solo Keycloak compartido** (corre en la máquina de quien lo armó, en la misma red) | `KEYCLOAK_SERVER_URL` apunta a la IP local de esa máquina (ej. `http://192.168.1.15:8080`, NO `localhost`, porque `localhost` en tu máquina no es la máquina del otro). `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID` y `KEYCLOAK_CLIENT_SECRET` son **los mismos para todo el equipo** — quien armó el Client se los pasa por un canal privado (Slack, WhatsApp), **nunca por el repositorio ni por chat público** |
| **B) Cada uno levanta su propio Keycloak** | Cada integrante sigue los pasos del Paso 3 en su propia máquina, crea su propio Realm/Client, y usa `KEYCLOAK_SERVER_URL=http://localhost:8080` con SU PROPIO `KEYCLOAK_CLIENT_SECRET` (van a ser todos distintos entre sí, y eso está bien) |

```
KEYCLOAK_SERVER_URL=...
KEYCLOAK_REALM=...
KEYCLOAK_CLIENT_ID=...
KEYCLOAK_CLIENT_SECRET=...
```

Si no te toca trabajar en Epic 1, podés dejar estas variables vacías por ahora.

## Paso 6 — Crear la base de datos y aplicar migraciones

```bash
# Crear la base de datos (con pgAdmin, gráficamente, o por comando):
createdb -U postgres global_exchange
# Te va a pedir la contraseña que definiste al instalar Postgres

# Aplicar las migraciones del proyecto a tu base recién creada
python manage.py migrate
```

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

Para no tener que escribir todos los comandos a mano cada vez que cambiás de ambiente o levantás Keycloak, el proyecto incluye tres scripts de PowerShell y una configuración de tareas de VSCode.

**8.1 — Copiar los scripts:**

Creá una carpeta `scripts/` en la raíz del repo (si no existe) y poné ahí `keycloak-start.ps1`, `run-dev.ps1` y `run-prod.ps1`. Abrí `keycloak-start.ps1` y ajustá la ruta `$keycloakBin` si tu instalación de Keycloak está en otro lado.

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

Desde VSCode: `Ctrl+Shift+P` → escribir "Run Task" → Enter → elegir una de las cuatro tareas disponibles:

| Tarea | Qué hace |
|---|---|
| **Modo Desarrollo (runserver)** | Cambia el `.env` a `dev`, levanta `runserver` |
| **Modo Producción (Uvicorn)** | Cambia el `.env` a `prod`, corre `collectstatic`, levanta Uvicorn |
| **Levantar Keycloak** | Corre `kc.bat start-dev` sin que tengas que recordar la ruta |
| **Correr tests (pytest)** | Corre `pytest` directo |

También podés correrlos manualmente sin pasar por VSCode:
```powershell
.\scripts\run-dev.ps1
.\scripts\run-prod.ps1
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
│   │   ├── base.py           ← configuración compartida
│   │   ├── dev.py            ← hereda de base, para tu máquina
│   │   └── prod.py           ← hereda de base, para producción
│   ├── urls.py
│   ├── wsgi.py / asgi.py
├── clientes/, usuarios/, etc.  ← una "app" por cada dominio de negocio
├── tests/
├── manage.py
└── requirements.txt
```

**Proyecto vs. App:** el proyecto (`global_exchange`) es el contenedor general. Las apps son módulos independientes (uno por dominio: clientes, usuarios, etc.) registrados en `INSTALLED_APPS` dentro de `base.py`.

## 2.5 — Ambientes: desarrollo vs. producción

El mismo código corre distinto según el contexto:

| | `dev.py` | `prod.py` |
|---|---|---|
| `DEBUG` | `True` (errores detallados) | `False` (oculta detalles internos) |
| Base de datos | SQLite (archivo local) | PostgreSQL |
| Servidor | `runserver` | Nginx + Uvicorn |

**Cadena en producción:**
```
navegador → Nginx (puerto 80) → Uvicorn (puerto 8000) → Django (asgi.py) → PostgreSQL
```
Nginx recibe la petición primero y se la reenvía a Uvicorn por detrás; también sirve los archivos estáticos directamente. Ni `base.py`, `dev.py`, `prod.py`, `wsgi.py` ni `asgi.py` se tocan para esto — Django ya genera `asgi.py` automáticamente. Nginx no vive dentro del repo (se instala aparte en el sistema); sí conviene guardar el `nginx.conf` usado en `docs/` como referencia.

En el día a día siempre estás en modo desarrollo. El de producción se prueba puntualmente para confirmar que el sistema también funciona con `DEBUG=False`, Postgres, y la stack Nginx+Uvicorn.

## 2.6 — Keycloak

El servidor externo que maneja usuarios, login y roles — Django no tiene su propia tabla de usuarios con contraseñas, todo vive en Keycloak.

**Conceptos:**
- **Realm**: el espacio aislado del proyecto (ej. `global-exchange`), separado del Realm `master` que es solo para administrar Keycloak en sí.
- **Client**: la "aplicación" registrada dentro del Realm (en este caso, Django), con su propio Client ID y Client Secret.
- **Roles**: permisos asignables a usuarios (ej. `admin`, `cliente`).

**Qué es config de entorno y qué es HU real:** levantar el servidor y crear Realm/Client/roles/usuario de prueba es preparación de infraestructura (como instalar Postgres) — no se testea con pytest ni se mergea como código, es evidencia/entregable del alcance del sprint. Conectar Django con esto (`mozilla-django-oidc`, vistas de login/callback/registro) sí es desarrollo real de las HU del Epic 1, con sus tests correspondientes.

## 2.7 — `.env` y `python-decouple`

`.env` guarda datos sensibles o específicos de cada máquina, nunca se sube a Git. `.env.example` es la plantilla sin valores reales, que sí se sube. `python-decouple` es la librería que lee el `.env` y lo convierte en variables usables por Django (`config('SECRET_KEY')`); sin ella, Django no sabe que el `.env` existe.

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

- **`scripts/run-dev.ps1`**: reemplaza automáticamente la línea `DJANGO_SETTINGS_MODULE` del `.env` por `.dev` y levanta `runserver`.
- **`scripts/run-prod.ps1`**: la reemplaza por `.prod`, corre `collectstatic`, y levanta Uvicorn. Nginx queda aparte (proceso externo al proyecto) — puede quedar corriendo permanentemente, no hace falta reiniciarlo al cambiar de ambiente.
- **`scripts/keycloak-start.ps1`**: evita tener que recordar la ruta de instalación y el comando `kc.bat start-dev` cada vez.
- **`.vscode/tasks.json`**: expone estos tres scripts (más `pytest`) como tareas de VSCode, accesibles con `Ctrl+Shift+P` → "Run Task", sin pasar por la terminal manualmente.

Requieren una única configuración por máquina la primera vez: `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser` desde PowerShell como administrador, ya que Windows bloquea por defecto la ejecución de scripts `.ps1` no firmados.
