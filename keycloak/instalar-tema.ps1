<#
Instala el tema de login "global-exchange" en un Keycloak local (instalación
standalone, sin Docker) y lo deja activo en el realm.

  1. Copia keycloak/themes/global-exchange a <Keycloak>/themes/global-exchange
     (si ya existía una versión que no salió de este repo, la respalda antes).
  2. Si se pasan credenciales de admin (o se piden), configura el realm:
     loginTheme/emailTheme=global-exchange, registro de usuarios, "olvidé mi contraseña"
     e idioma español por defecto.

Uso:
  .\keycloak\instalar-tema.ps1                       # copia + configura el realm (pide credenciales)
  .\keycloak\instalar-tema.ps1 -SoloCopiar           # solo copia los archivos (lo usa keycloak-start.ps1)
  .\keycloak\instalar-tema.ps1 -AdminUser admin -AdminPassword ****

En modo start-dev Keycloak no cachea los temas: después de copiar alcanza con
recargar la página de login.
#>
param(
    [string]$KeycloakHome = "C:\herramientas_IS2\keycloak",
    [string]$Server = "http://localhost:8080",
    [string]$Realm = "global-exchange",
    [string]$AdminUser,
    [string]$AdminPassword,
    [switch]$SoloCopiar
)

$ErrorActionPreference = "Stop"
$temaNombre = "global-exchange"
$origen = Join-Path $PSScriptRoot "themes\$temaNombre"
$destinoThemes = Join-Path $KeycloakHome "themes"
$destino = Join-Path $destinoThemes $temaNombre
# Marca para reconocer copias que salieron de este repo y no respaldarlas cada vez.
$marca = ".instalado-desde-repo"

if (-not (Test-Path $origen)) {
    throw "No se encontró el tema en $origen"
}
if (-not (Test-Path $destinoThemes)) {
    throw "No se encontró la carpeta themes de Keycloak en $destinoThemes. Ajustá -KeycloakHome."
}

if ((Test-Path $destino) -and -not (Test-Path (Join-Path $destino $marca))) {
    $respaldo = Join-Path $KeycloakHome ("themes-respaldo\$temaNombre-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    Write-Host "Respaldando el tema existente en $respaldo" -ForegroundColor Yellow
    New-Item -ItemType Directory -Force (Split-Path $respaldo) | Out-Null
    Move-Item $destino $respaldo
}

Write-Host "Copiando tema $temaNombre a $destino..." -ForegroundColor Cyan
# /MIR deja el destino idéntico al repo (borra archivos que ya no existen acá).
robocopy $origen $destino /MIR /NJH /NJS /NFL /NDL /XF $marca | Out-Null
if ($LASTEXITCODE -ge 8) {
    throw "robocopy falló con código $LASTEXITCODE"
}
Set-Content -Path (Join-Path $destino $marca) -Value "Copiado por keycloak/instalar-tema.ps1. No editar acá: editar en el repo." -Encoding utf8
Write-Host "Tema copiado." -ForegroundColor Green

if ($SoloCopiar) {
    exit 0
}

$kcadm = Join-Path $KeycloakHome "bin\kcadm.bat"
if (-not (Test-Path $kcadm)) {
    throw "No se encontró kcadm.bat en $KeycloakHome\bin"
}
if ([string]::IsNullOrWhiteSpace($AdminUser)) {
    $AdminUser = Read-Host "Usuario administrador de Keycloak (master)"
}
if ([string]::IsNullOrWhiteSpace($AdminPassword)) {
    $seguro = Read-Host "Password administrador de Keycloak (master)" -AsSecureString
    $AdminPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($seguro)
    )
}

Write-Host "Autenticando contra $Server..." -ForegroundColor Cyan
& $kcadm config credentials --server $Server --realm master --user $AdminUser --password $AdminPassword
if ($LASTEXITCODE -ne 0) { throw "No se pudo autenticar contra Keycloak (¿está levantado?)." }

Write-Host "Activando el tema en el realm $Realm..." -ForegroundColor Cyan
& $kcadm update "realms/$Realm" `
    -s "loginTheme=$temaNombre" `
    -s "emailTheme=$temaNombre" `
    -s "registrationAllowed=true" `
    -s "resetPasswordAllowed=true" `
    -s "rememberMe=true" `
    -s "internationalizationEnabled=true" `
    -s "supportedLocales[0]=es" `
    -s "defaultLocale=es"
if ($LASTEXITCODE -ne 0) { throw "No se pudo actualizar el realm $Realm." }

Write-Host ""
Write-Host "Listo. Probalo en: $Server/realms/$Realm/account" -ForegroundColor Green
Write-Host "Nota: 'Olvidé mi contraseña' necesita SMTP configurado en Realm settings > Email." -ForegroundColor Yellow
