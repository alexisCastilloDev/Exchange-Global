# Levanta Keycloak en modo desarrollo con un solo comando.
# Ajusta la ruta de abajo a donde tengas instalado Keycloak.

$keycloakBin = "C:\Herramientas_IS2\keycloak\bin"

if (-not (Test-Path $keycloakBin)) {
    Write-Host "No se encontro la carpeta de Keycloak en: $keycloakBin" -ForegroundColor Red
    Write-Host "Edita la variable `$keycloakBin` al principio de este script." -ForegroundColor Yellow
    exit 1
}

Write-Host "Levantando Keycloak en modo desarrollo..." -ForegroundColor Cyan
Write-Host "Va a quedar escuchando en http://localhost:8080" -ForegroundColor Cyan
Write-Host ""

Push-Location $keycloakBin
.\kc.bat start-dev
Pop-Location
