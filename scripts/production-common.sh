#!/usr/bin/env bash
# Shared helpers for the native cPanel production deployment.
#
# Production runs directly on the cPanel account with Python 3.12, a dedicated
# virtual environment, PostgreSQL, Redis, MinIO/S3 and a cPanel-managed web
# server. Docker, Docker Compose, containers and container volumes are NOT used
# here. The Docker configuration files in this repository remain for local
# development and the isolated GitHub Actions QA runner only.
set -Eeuo pipefail
umask 077

fail() { echo "ERROR: $*" >&2; exit 1; }
log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

ACCOUNT="crmnakshatech"
HOME_ROOT="/home/crmnakshatech"

# Deployment workspace (outside public_html, private to the account).
DEPLOY_ROOT="$HOME_ROOT/erp-releases"
RELEASES="$DEPLOY_ROOT/releases"
INCOMING="$DEPLOY_ROOT/incoming"
SHARED="$DEPLOY_ROOT/shared"

# Live application locations.
BACKEND_DIR="$HOME_ROOT/crm_backend"
FRONTEND_DIR="$HOME_ROOT/public_html"
ENV_FILE="$BACKEND_DIR/.env"
VENV="${NAKSHA_VENV:-$HOME_ROOT/crm_venv}"
BACKUPS="$HOME_ROOT/erp-backups"
LOCK_FILE="$DEPLOY_ROOT/deploy.lock"

require_account() {
  [[ "${HOME:-}" == "$HOME_ROOT" ]] || fail "Deployment must run inside the $ACCOUNT cPanel account (HOME=$HOME_ROOT)"
  [[ "$(id -un)" == "$ACCOUNT" ]] || fail "Deployment must run as $ACCOUNT, not $(id -un)"
  [[ -d "$HOME_ROOT" && ! -L "$HOME_ROOT" ]] || fail "Missing canonical account home $HOME_ROOT"
}

require_cmd() {
  local command
  for command in "$@"; do
    command -v "$command" >/dev/null 2>&1 || fail "Missing required command: $command"
  done
}

require_sha() { [[ "${1:-}" =~ ^[0-9a-f]{40}$ ]] || fail "Expected an exact 40-character commit SHA"; }

# Reads a single value from the private Pydantic .env file without executing it.
# The file is data, not shell code: it is never sourced.
env_value() {
  [[ -f "$ENV_FILE" ]] || return 0
  sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$ENV_FILE" \
    | tail -n 1 \
    | sed -e 's/[[:space:]]*$//' -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/"
}

gate() {
  [[ "${PRODUCTION_DEPLOY_ENABLED:-false}" == true ]] \
    || fail "Production deployment gate is disabled (PRODUCTION_DEPLOY_ENABLED != true)"
  [[ "$(env_value PRODUCTION_DEPLOY_ENABLED)" == true ]] \
    || fail "Production gate must also be enabled in $ENV_FILE"
}

lock() {
  mkdir -p "$DEPLOY_ROOT"
  exec 9>"$LOCK_FILE"
  flock -n 9 || fail "Another production deployment or backup holds $LOCK_FILE"
}

ensure_layout() {
  mkdir -p "$RELEASES" "$INCOMING" "$SHARED" "$BACKUPS" "$BACKEND_DIR/tmp" "$BACKEND_DIR/uploads"
  chmod 700 "$DEPLOY_ROOT" "$RELEASES" "$INCOMING" "$SHARED" "$BACKUPS" "$BACKEND_DIR/tmp"
}

release_path() {
  require_sha "${1:-}"
  release="$RELEASES/$1"
  [[ -d "$release" && ! -L "$release" ]] || fail "Missing canonical release directory $release"
  [[ "$(realpath "$release")" == "$release" ]] || fail "Release path escapes $RELEASES"
  [[ -f "$release/RELEASE_SHA" ]] || fail "Release $1 has no RELEASE_SHA marker"
  [[ "$(tr -d '[:space:]' < "$release/RELEASE_SHA")" == "$1" ]] || fail "Release SHA marker mismatch in $release"
  export RELEASE_SHA="$1"
}

ensure_venv() {
  if [[ -x "$VENV/bin/python" ]]; then
    return
  fi
  local candidate interpreter=""
  for candidate in python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      interpreter="$candidate"
      break
    fi
  done
  [[ -n "$interpreter" ]] || fail "Python 3.11+ is required but was not found"
  "$interpreter" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 11) else 1)' \
    || fail "Python 3.11+ is required (found $interpreter)"
  log "Creating dedicated virtual environment at $VENV with $interpreter"
  "$interpreter" -m venv "$VENV" || fail "Could not create the virtual environment at $VENV"
}

install_python_deps() {
  local release="$1" requirements
  requirements="$release/backend/requirements-cpanel.txt"
  [[ -f "$requirements" ]] || fail "Release is missing backend/requirements-cpanel.txt"
  ensure_venv
  log "Installing Python dependencies into $VENV"
  "$VENV/bin/python" -m pip install --quiet --upgrade pip setuptools wheel
  "$VENV/bin/python" -m pip install --no-input --disable-pip-version-check -r "$requirements"
  "$VENV/bin/python" -m pip check || fail "Python dependency conflicts detected in $VENV"
}

# Backend source is synchronised in place so the existing .env, virtual
# environment, uploads, tmp and logs are preserved. Excluded paths are protected
# from --delete, so this never removes production data or configuration.
sync_backend() {
  local release="$1"
  [[ -d "$release/backend" ]] || fail "Release is missing backend sources"
  log "Synchronising backend sources into $BACKEND_DIR"
  rsync -a --delete \
    --exclude '.env' \
    --exclude '.env.*' \
    --exclude 'tmp/' \
    --exclude 'uploads/' \
    --exclude 'logs/' \
    --exclude '*.log' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.pytest_cache/' \
    --exclude '.venv/' \
    --exclude 'venv/' \
    "$release/backend/" "$BACKEND_DIR/"
  mkdir -p "$BACKEND_DIR/tmp" "$BACKEND_DIR/uploads"
  chmod 700 "$BACKEND_DIR/tmp" "$BACKEND_DIR/uploads" 2>/dev/null || true
}

# Only the compiled frontend is published. public_html may also host the existing
# NMaps application, so this never deletes anything outside public_html/assets.
# Hashed build assets are the only directory replaced wholesale.
sync_frontend() {
  local release="$1" previous="${2:-}" staging
  [[ -f "$release/frontend/index.html" ]] || fail "Release is missing the compiled frontend (frontend/index.html)"
  mkdir -p "$FRONTEND_DIR/assets" "$SHARED/frontend-previous"
  if [[ -n "$previous" ]]; then
    staging="$SHARED/frontend-previous/$previous"
    mkdir -p "$staging"
    for name in index.html .htaccess; do
      [[ ! -f "$FRONTEND_DIR/$name" ]] || cp -p "$FRONTEND_DIR/$name" "$staging/$name"
    done
  fi
  log "Publishing compiled frontend into $FRONTEND_DIR"
  rsync -a --delete "$release/frontend/assets/" "$FRONTEND_DIR/assets/"
  local entry base
  for entry in "$release"/frontend/*; do
    base="$(basename "$entry")"
    [[ "$base" == "assets" ]] && continue
    rsync -a "$entry" "$FRONTEND_DIR/"
  done
  if [[ -f "$release/frontend/.htaccess" ]]; then
    rsync -a "$release/frontend/.htaccess" "$FRONTEND_DIR/.htaccess"
  fi
  [[ -f "$FRONTEND_DIR/index.html" ]] || fail "Frontend publish did not produce index.html"
  chmod 644 "$FRONTEND_DIR/index.html" "$FRONTEND_DIR/.htaccess" 2>/dev/null || true
}

backend_port() {
  local port
  port="$(env_value BACKEND_PORT)"
  printf '%s' "${port:-8010}"
}

backend_runtime() {
  local mode
  mode="$(env_value BACKEND_RUNTIME)"
  printf '%s' "${mode:-systemd}"
}

# Waits for the local backend to answer its health endpoint. Works for the
# systemd/uvicorn runtime; Passenger is validated through the public URL only.
# Startup runs idempotent schema compatibility routines, which can take several
# minutes on a first installation or a large database. Allow up to 300 seconds.
wait_for_backend() {
  local url="http://127.0.0.1:$(backend_port)/api/health" attempt attempts=300
  for attempt in $(seq 1 "$attempts"); do
    if curl -fsS --max-time 5 "$url" >/dev/null 2>&1; then
      log "Backend answered $url after ${attempt}s"
      return 0
    fi
    if (( attempt % 30 == 0 )); then
      log "Waiting for backend startup (${attempt}s of ${attempts}s)"
    fi
    sleep 1
  done
  fail "Backend did not become healthy at $url within ${attempts} seconds"
}
