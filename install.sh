#!/usr/bin/env bash
# rensi-claude-dashboard installer (Linux/macOS).
#   curl -fsSL https://github.com/breisnerlopez/rensi-claude-dashboard/releases/latest/download/install.sh | bash
# Installs the package via pipx (bootstrapping pipx if needed), registers
# best-effort autostart, starts the server, and prints the URL to open.
set -euo pipefail

REPO="breisnerlopez/rensi-claude-dashboard"
TAG="v0.2.0"
PKG_SPEC="git+https://github.com/${REPO}.git@${TAG}"

log() { printf '\033[1;36m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$1"; }
die() { printf '\033[1;31mERROR:\033[0m %s\n' "$1"; exit 1; }

# ---- 1. find a usable python3 ----
PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    ver="$("$cand" -c 'import sys; print(sys.version_info[0]*100+sys.version_info[1])' 2>/dev/null || echo 0)"
    if [ "$ver" -ge 309 ]; then PY="$cand"; break; fi
  fi
done
if [ -z "$PY" ]; then
  die "Python 3.9+ no encontrado. Instala Python (apt/dnf/brew install python3) y vuelve a correr este script."
fi
log "usando $($PY --version)"

# ---- 2. ensure pipx ----
if ! command -v pipx >/dev/null 2>&1; then
  log "pipx no encontrado, instalando en el usuario actual..."
  "$PY" -m pip install --user pipx >/dev/null 2>&1 || "$PY" -m ensurepip --user >/dev/null 2>&1 || true
  "$PY" -m pip install --user pipx || die "no se pudo instalar pipx. Instala pipx manualmente y vuelve a correr este script."
  "$PY" -m pipx ensurepath >/dev/null 2>&1 || true
  export PATH="$HOME/.local/bin:$PATH"
fi

# ---- 3. install the package (module form throughout -- don't rely on a bare
#         `pipx` resolving on PATH in this same shell right after ensurepath) ----
log "instalando rensi-claude-dashboard..."
"$PY" -m pipx install --force "$PKG_SPEC" || die "fallo la instalacion via pipx"

RD="$HOME/.local/bin/rensi-dashboard"
if ! command -v rensi-dashboard >/dev/null 2>&1 && [ -x "$RD" ]; then
  export PATH="$HOME/.local/bin:$PATH"
fi
command -v rensi-dashboard >/dev/null 2>&1 || die "rensi-dashboard se instalo pero no esta en PATH. Agrega ~/.local/bin a tu PATH y corre: rensi-dashboard setup"

# ---- 4. first-run setup: token, autostart, start now ----
log "configurando (token, autostart, arranque)..."
rensi-dashboard setup

log "listo. La URL de arriba ya deberia estar abierta en tu navegador."
log "Comandos utiles: rensi-dashboard status | stop | restart"
