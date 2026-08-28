# Cambia el .env a modo produccion, recolecta estaticos, y levanta
# Nginx (en una ventana nueva) + Uvicorn (en esta misma terminal).
# Correr desde la raiz del repo (donde esta manage.py).

$envFile = ".\.env"
$venvActivate = ".\.venv\Scripts\Activate.ps1"

# Ajusta esta ruta a donde tengas instalado Nginx
$nginxPath = "C:\Herramientas_IS2\nginx"

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

(Get-Content $envFile) -replace '^DJANGO_SETTINGS_MODULE=.*', 'DJANGO_SETTINGS_MODULE=global_exchange.settings.prod' | Set-Content $envFile

Write-Host "Modo PRODUCCION activado (DEBUG=False, PostgreSQL)." -ForegroundColor Yellow
Write-Host ""

Write-Host "Recolectando archivos estaticos..." -ForegroundColor Cyan
python manage.py collectstatic --noinput

# Levantar Nginx en una ventana nueva, si no esta corriendo ya
Write-Host ""
if (Test-Path "$nginxPath\nginx.exe") {
    Write-Host "Levantando Nginx en una ventana nueva..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$nginxPath'; .\nginx.exe; Write-Host 'Nginx corriendo en http://localhost' -ForegroundColor Green"
} else {
    Write-Host "No se encontro nginx.exe en $nginxPath - ajusta la variable `$nginxPath al principio del script." -ForegroundColor Red
    Write-Host "Vas a tener que levantarlo manualmente." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Levantando Uvicorn en http://127.0.0.1:8000 (esta terminal)" -ForegroundColor Cyan
Write-Host "Accede por Nginx en http://localhost (sin puerto)" -ForegroundColor Cyan
Write-Host ""

uvicorn global_exchange.asgi:application --host 127.0.0.1 --port 8000
