# Corre pytest con el entorno virtual activado.
# Correr desde la raiz del repo (donde esta manage.py).

$venvActivate = ".\.venv\Scripts\Activate.ps1"

if (-not (Test-Path $venvActivate)) {
    Write-Host "No se encontro .venv en esta carpeta. Corre este script desde la raiz del repo." -ForegroundColor Red
    exit 1
}

& $venvActivate

Write-Host "Corriendo tests..." -ForegroundColor Cyan
Write-Host ""

pytest
