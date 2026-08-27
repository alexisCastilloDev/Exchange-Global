# Guía del Entorno de Desarrollo — Global Exchange

## 1. Entorno virtual (`.venv`)

**Qué es:** una copia aislada de Python solo para este proyecto. Las librerías que instalás (Django, pytest, etc.) quedan encerradas ahí, sin mezclarse con otros proyectos ni con el Python del sistema operativo.

**Cómo se usa:**
```bash
# Crear (solo una vez, ya lo hicieron)
python -m venv .venv

# Activar (cada vez que abrís una terminal nueva para trabajar)
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Mac/Linux

# Vas a saber que está activo porque el prompt muestra (.venv) al inicio
```

**Regla de oro:** todo comando de Python/Django/pip que corras debe ser con el venv activado. Si no lo está, podés estar instalando cosas en el lugar equivocado.

---

## 2. `requirements.txt`

**Qué es:** la lista exacta de todas las librerías (y sus versiones) que el proyecto necesita para funcionar.

**Por qué existe:** vos no le pasás tu carpeta `.venv` a tus compañeros (nunca se sube a Git). En cambio, les pasás este archivo, y cada uno genera su propio `.venv` idéntico al tuyo.

**Cómo se usa:**
```bash
# Cuando instalás algo nuevo, actualizás el archivo:
pip install <libreria>
pip freeze > requirements.txt

# Tus compañeros, para instalar todo lo que vos ya tenés:
pip install -r requirements.txt
```

---

## 3. Git y Gitflow

**Qué es:** el sistema de control de versiones (Git) con una convención de ramas (Gitflow) para organizar el trabajo en equipo.

**Ramas principales:**
- `main` → código en producción, solo recibe merges de `develop` al cerrar un sprint, marcado con un tag de versión (ej. `v1.0-sprint1`).
- `develop` → rama de integración, donde se juntan todas las funcionalidades ya terminadas.
- `feature/<id-HU>` → una rama por cada historia de usuario en desarrollo, sale de `develop` y vuelve a `develop` cuando termina.

**Usando la extensión `git-flow` (la que ya tienen instalada):** en vez de crear y mergear ramas a mano, la herramienta `git flow` automatiza los pasos y sigue la convención de nombres por vos.

**Flujo típico de trabajo en una HU:**
```bash
git checkout develop
git pull                                  # traer los últimos cambios de tus compañeros

# Iniciar el trabajo de una HU (crea y te cambia a feature/GE-XX automáticamente)
git flow feature start GE-XX

# ... trabajás, hacés commits normales ...
git add .
git commit -m "mensaje descriptivo"
git push origin feature/GE-XX             # subir la rama para que otros la vean/revisen

# Al terminar la HU: mergea a develop, borra la rama local y te devuelve a develop
git flow feature finish GE-XX
git push origin develop
```

**Al cerrar el sprint (release):**
```bash
git flow release start v1.0-sprint1
# ... ajustes finales si hicieran falta ...
git flow release finish v1.0-sprint1
# Esto mergea a main Y a develop, y crea el tag automáticamente
git push origin main develop --tags
```

> Nota: si prefieren no usar la extensión y hacerlo a mano, el equivalente sin `git flow` sería `git checkout -b feature/GE-XX` para empezar y `git checkout develop && git merge feature/GE-XX` para terminar — mismo resultado, más pasos manuales.

---

## 4. Extensiones necesarias de VSCode

Para que el entorno funcione igual en todas las máquinas del equipo, instalen estas extensiones (buscarlas por nombre en la pestaña Extensions de VSCode):

| Extensión | Para qué sirve |
|---|---|
| **Python** (Microsoft) | Soporte base de Python: resaltado de sintaxis, selección de intérprete/venv, ejecución y debug. |
| **Pylance** (Microsoft) | Se instala junto con Python; da autocompletado inteligente y detección de errores en tiempo real (los errores que vimos antes con los backticks salieron de acá). |
| **Django** (Baptiste Darthenay o similar) | Resaltado de sintaxis para templates de Django y autocompletado de tags/filtros. |
| **Gitflow** (vector-of-bool o similar) | Te permite correr los comandos `git flow` (feature start/finish, release, etc.) desde la paleta de comandos de VSCode, sin memorizar la sintaxis de la terminal. |
| **autoDocstring** | Genera automáticamente la plantilla de un docstring al escribir `"""` debajo de una función/clase — acelera PDO. |
| **GitLens** o **GitHub Pull Requests** | Para ver el historial de cambios línea por línea y gestionar Pull Requests directo desde el editor (lo que ya tenían como "GitPullRequest"). |

**Cómo confirmar que están usando el venv correcto:** abajo a la derecha de VSCode aparece el intérprete de Python activo. Tiene que decir algo como `Python 3.14.7 ('.venv': venv)`. Si dice otra cosa, hacer clic ahí (o `Ctrl+Shift+P` → "Python: Select Interpreter") y elegir el de `.venv`.

---

## 5. Estructura del proyecto Django

```
IS2_REPO/
├── global_exchange/          ← el "proyecto" (config general)
│   ├── settings/
│   │   ├── base.py           ← configuración compartida
│   │   ├── dev.py            ← hereda de base, para tu máquina
│   │   └── prod.py           ← hereda de base, para producción
│   ├── urls.py
│   ├── wsgi.py / asgi.py
├── clientes/ , usuarios/, etc.  ← una "app" por cada dominio (se van creando)
├── tests/                     ← tests generales del proyecto
├── manage.py                  ← punto de entrada para todos los comandos Django
└── requirements.txt
```

**Proyecto vs. App:** el proyecto (`global_exchange`) es el contenedor general. Las apps son módulos independientes (uno por dominio de negocio: clientes, usuarios, etc.) que se registran en `INSTALLED_APPS` dentro de `base.py`.

---

## 6. Ambientes: desarrollo vs. producción

**Por qué separarlos:** el mismo código corre distinto según el contexto. En tu compu querés ver errores detallados y usar una base liviana (sqlite). En "producción" no querés exponer errores internos, y usás una base más robusta (Postgres).

| | `dev.py` | `prod.py` |
|---|---|---|
| `DEBUG` | `True` (ves errores detallados) | `False` (oculta detalles internos) |
| Base de datos | sqlite (archivo local) | PostgreSQL |
| Servidor | `runserver` (liviano, solo dev) | `waitress` (servidor WSGI real) |

**Cómo se usa cada uno:**
```bash
# Desarrollo (uso diario)
python manage.py runserver
# manage.py ya está configurado para usar dev.py por defecto

# Producción (para probar que el ambiente "real" funciona)
# 1. En el .env, cambiar DJANGO_SETTINGS_MODULE a global_exchange.settings.prod
# 2. python manage.py collectstatic --noinput
# 3. waitress-serve --host=127.0.0.1 --port=8000 global_exchange.wsgi:application
# 4. Al terminar, volver el .env a .dev
```

En el día a día vas a estar siempre en modo desarrollo. El de producción se prueba puntualmente para demostrar que el sistema también funciona con `DEBUG=False` y Postgres.

---

## 7. `.env` y `python-decouple`

**Qué es `.env`:** un archivo con datos sensibles o que cambian según la máquina (contraseñas, claves secretas, hosts). **Nunca se sube a Git** (está en `.gitignore`).

**Qué es `.env.example`:** una copia del `.env` pero con los valores vacíos o de ejemplo, sin datos reales. **Este sí se sube a Git**, para que tus compañeros sepan qué variables necesitan crear en su propio `.env`.

**Qué es `python-decouple`:** la librería que lee el `.env` y lo convierte en variables que Django puede usar (`config('SECRET_KEY')`, etc.). Sin ella, Django no sabe que el `.env` existe.

---

## 8. `pytest` y `pytest.ini`

**Qué es pytest:** el framework que ejecuta tus pruebas unitarias (PUN).

**Qué es `pytest-django`:** un complemento que le enseña a pytest a entender un proyecto Django (cargar settings, usar la base de datos de test, etc.).

**Qué es `pytest.ini`:** el archivo de configuración que le dice a pytest **dónde está tu `settings.py`** y **qué archivos considerar como tests**. Sin este archivo, pytest no sabría que tu proyecto es Django y fallaría al importar cualquier cosa que dependa de Django.

**Cómo se usa:**
```bash
pytest                    # corre todos los tests del proyecto
pytest clientes/tests/    # corre solo los tests de una app
pytest -v                 # modo detallado, muestra cada test por nombre
```

**Cuándo escribís tests:** cada vez que programás una funcionalidad (un modelo, una vista), le sumás un test que verifique que funciona. No se escriben "de una sola vez al final" — van creciendo junto con el código.

---

## 9. `staticfiles/` y `collectstatic`

Django separa dos cosas: los archivos estáticos que cada app trae por defecto (como los estilos del panel de administración) y los que sumás vos. El comando `collectstatic` los junta a todos en una sola carpeta (`staticfiles/`) para que un servidor de producción los sirva eficientemente. Esta carpeta se regenera con el comando, por eso no se versiona en Git.

---

## 10. Docstrings y la extensión autoDocstring

**Qué es un docstring:** un comentario especial dentro de una función/clase que explica qué hace, qué recibe y qué devuelve. A diferencia de un comentario común (`# esto es un comentario`), el docstring queda "adjunto" al código, y herramientas como VSCode o Sphinx lo leen automáticamente.

**Para qué sirve:**
- VSCode te muestra esa descripción al pasar el mouse sobre la función en otro archivo.
- Sphinx (sección siguiente) lo usa para generar la documentación navegable del proyecto sin que tengas que escribir nada aparte — documentás una sola vez, en el código.

**Formato:**
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
    # ... código real de la función
```

**Cómo usar la extensión autoDocstring (para no escribir la plantilla a mano):**
1. Escribí la función completa, con sus parámetros ya definidos.
2. Parate en la línea de abajo de la definición (`def registrar_cliente(...):`).
3. Escribí `"""` y apretá Enter (o el atajo `Ctrl+Shift+2`).
4. La extensión genera automáticamente la plantilla con los parámetros detectados en `Args:`, lista para que completes solo el texto descriptivo de cada uno.

**Cuándo usarlo:** no hace falta en cada función (un método trivial de una línea no lo necesita). Priorizalo en modelos (qué representa la entidad), métodos de vistas/lógica de negocio (qué hacen, qué reciben, qué devuelven), y cualquier función que no sea obvia con solo leer su nombre.

---

## 11. Sphinx (documentación automática — PDO)

**Qué es:** una herramienta que lee los **docstrings** de tu código (ver sección de autoDocstring más abajo si no la tenés) y genera automáticamente un sitio HTML navegable con toda la documentación técnica del proyecto — sin que tengas que escribir esa documentación por separado.

**Estructura que genera:**
```
docs/
├── source/          ← configuración y archivos fuente (SÍ se sube a Git)
│   ├── conf.py
│   ├── index.rst
│   └── modules.rst  ← y un .rst por cada app/módulo
├── build/           ← el sitio HTML ya generado (NO se sube, va en .gitignore)
├── Makefile
└── make.bat
```

**Cuándo correrlo:**

No es algo que corras en cada commit — solo cuando quieras regenerar la documentación con los cambios más recientes (por ejemplo, al terminar una HU, o antes de una entrega).

```bash
# Si agregaste una app NUEVA (ej. clientes/), primero regenerá los .rst:
# (parado en la raíz del repo)
sphinx-apidoc -o docs/source .

# Para generar/actualizar el sitio HTML:
# (parado dentro de la carpeta docs/)
.\make.bat html        # Windows
make html               # Mac/Linux

# Ver el resultado: abrir en el navegador
docs/build/html/index.html
```

Si solo agregaste funciones o docstrings nuevos a una app que **ya existía**, no hace falta correr `sphinx-apidoc` de nuevo — con `make html` alcanza.

**Reglas para que la doc salga bien:**
- Todo modelo, vista o función no trivial debería tener su docstring (con autoDocstring te lleva segundos).
- Si `sphinx-quickstart` te generó `docs/source/index.rst` sin el link a `modules`, agregalo dentro del bloque `toctree` para que se pueda navegar desde la portada:
```rst
.. toctree::
   :maxdepth: 2
   :caption: Contents:

   modules
```
- Los warnings de docstrings mal formados (ej. en `urls.py`, generado automáticamente por Django) no rompen el build — podés ignorarlos o prolijarlos si te molestan.

---

## 12. Cómo preparan el entorno tus compañeros (paso a paso)

Esto es lo que cada compañero debe hacer la primera vez que clona el repo:

```bash
# 1. Clonar el repositorio
git clone <url-del-repo>
cd IS2_REPO

# 2. Crear y activar su propio entorno virtual
python -m venv .venv
.venv\Scripts\activate          # Windows

# 3. Instalar todas las dependencias del proyecto
pip install -r requirements.txt

# 4. Copiar el archivo de ejemplo y completarlo con sus propios datos
copy .env.example .env          # Windows (o "cp" en Mac/Linux)
# Editar .env: poner su propia SECRET_KEY, credenciales de su Postgres local, etc.

# 5. Aplicar las migraciones a su base de datos local
python manage.py migrate

# 6. Verificar que todo funciona
python manage.py runserver
pytest
```

Con esto, cada integrante tiene un entorno idéntico al tuyo en su propia máquina, sin pisarse datos ni configuraciones entre sí.

---

## 13. Resumen de comandos del día a día

```bash
# Al empezar a trabajar
.venv\Scripts\activate
git checkout develop && git pull
git flow feature start GE-XX

# Mientras desarrollás
python manage.py runserver          # levantar el server
pytest                              # correr tests
python manage.py makemigrations     # si cambiaste un modelo
python manage.py migrate            # aplicar esos cambios a la BD

# Al terminar la HU
git add .
git commit -m "mensaje"
git push origin feature/GE-XX
git flow feature finish GE-XX       # mergea a develop y limpia la rama
git push origin develop
```
