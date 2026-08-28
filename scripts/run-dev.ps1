# Cambia el .env a modo desarrollo y levanta el servidor de Django.
# Correr desde la raiz del repo (donde esta manage.py).

$envFile = ".\.env"
$venvActivate = ".\.venv\Scripts\Activate.ps1"

if (-not (Test-Path $envFile)) {
    Write-Host "No se encontro .env en esta carpeta. Corre este script desde la raiz del repo." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $venvActivate)) {
    Write-Host "No se encontro .venv en esta carpeta. Corre este script desde la raiz del repo." -ForegroundColor Red
    exit 1
}

# Activar el entorno virtual (necesario porque las tareas de VSCode
# abren una PowerShell nueva, sin el venv activado)
& $venvActivate

# Reemplaza la linea DJANGO_SETTINGS_MODULE, sea cual sea su valor actual
(Get-Content $envFile) -replace '^DJANGO_SETTINGS_MODULE=.*', 'DJANGO_SETTINGS_MODULE=global_exchange.settings.dev' | Set-Content $envFile

Write-Host "Modo DESARROLLO activado (DEBUG=True, PostgreSQL, runserver)." -ForegroundColor Green
Write-Host ""

python manage.py runserver
