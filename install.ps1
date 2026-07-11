# rensi-claude-dashboard installer (Windows).
#   irm https://raw.githubusercontent.com/breisnerlopez/rensi-claude-dashboard/main/install.ps1 | iex
# No admin required. Installs Python via winget if missing, bootstraps pipx,
# installs the package, registers autostart, starts the server.

$ErrorActionPreference = "Stop"
$Repo = "breisnerlopez/rensi-claude-dashboard"
$Tag = "v0.1.0"
$PkgSpec = "git+https://github.com/$Repo.git@$Tag"

function Log($msg)  { Write-Host "==> $msg" -ForegroundColor Cyan }
function Warn($msg) { Write-Host "!! $msg" -ForegroundColor Yellow }
function Die($msg)  { Write-Host "ERROR: $msg" -ForegroundColor Red; exit 1 }

# ---- 1. find/install Python via the `py` launcher ----
$havePy = $false
try {
    $null = & py -3 --version 2>$null
    if ($LASTEXITCODE -eq 0) { $havePy = $true }
} catch { $havePy = $false }

if (-not $havePy) {
    Log "Python no encontrado, intentando instalar via winget..."
    $wingetOk = $false
    try {
        $null = Get-Command winget -ErrorAction Stop
        winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements --silent
        $wingetOk = ($LASTEXITCODE -eq 0)
    } catch { $wingetOk = $false }

    if (-not $wingetOk) {
        Warn "No se pudo instalar Python automaticamente (winget ausente o fallo)."
        Warn "Instala Python 3.9+ manualmente desde https://python.org/downloads/ (marca 'Add to PATH') y vuelve a correr este script."
        exit 0
    }
    Log "Python instalado. Puede que necesites abrir una terminal NUEVA para que PATH se actualice."
    try {
        $null = & py -3 --version 2>$null
        if ($LASTEXITCODE -ne 0) {
            Warn "Python se instalo pero no esta disponible en esta sesion todavia. Abre una terminal nueva y vuelve a correr este script."
            exit 0
        }
    } catch {
        Warn "Abre una terminal nueva y vuelve a correr este script."
        exit 0
    }
}
Log "Python listo: $(& py -3 --version)"

# ---- 2. ensure pipx (module form throughout -- PATH from ensurepath doesn't
#         refresh in this already-running process) ----
$localBin = Join-Path $env:USERPROFILE ".local\bin"
$env:PATH = "$localBin;$env:PATH"

$havePipx = $false
try { $null = & py -3 -m pipx --version 2>$null; $havePipx = ($LASTEXITCODE -eq 0) } catch { $havePipx = $false }

if (-not $havePipx) {
    Log "instalando pipx..."
    & py -3 -m pip install --user pipx
    if ($LASTEXITCODE -ne 0) { Die "no se pudo instalar pipx" }
    & py -3 -m pipx ensurepath | Out-Null
}

# ---- 3. install the package ----
Log "instalando rensi-claude-dashboard..."
& py -3 -m pipx install --force $PkgSpec
if ($LASTEXITCODE -ne 0) { Die "fallo la instalacion via pipx" }

$rd = Join-Path $localBin "rensi-dashboard.exe"
if (-not (Test-Path $rd)) { Die "rensi-dashboard no aparecio en $localBin tras la instalacion" }

# ---- 4. first-run setup: token, Task Scheduler autostart, start now ----
Log "configurando (token, autostart, arranque)..."
& $rd setup

Log "listo. La URL de arriba ya deberia estar abierta en tu navegador."
Log "Comandos utiles: rensi-dashboard status | stop | restart"
