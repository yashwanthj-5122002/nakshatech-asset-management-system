#!/usr/bin/env bash
# Shared helpers for the native cPanel production deployment.
#
# Production runs directly on the cPanel account with Python 3.12, a dedicated
# virtual environment, PostgreSQL, Redis, MinIO/S3 and a cPanel-managed web
# server. Docker, Docker Compose, containers and container volumes are NOT used
# here. The Docker configuration files in this repository remain for local
# development and the isolated GitHub Actions QA runner only.
#
# The running application lives in two directories that are separate copies of
# this repository:
#   backend  -> PRODUCTION_BACKEND_PATH   (default /home/crmnakshatech/crm_backend)
#   frontend -> PRODUCTION_FRONTEND_PATH  (default /home/crmnakshatech/public_html)
# The cPanel Git checkout (PRODUCTION_REPOSITORY_PATH) is only deployment
# metadata: updating it never updates the running application.
set -Eeuo pipefail
umask 077

fail() { echo "ERROR: $*" >&2; exit 1; }
log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

ACCOUNT="crmnakshatech"
HOME_ROOT="/home/crmnakshatech"

# Live application directories. Both are configurable through the documented
# PRODUCTION_* environment variables supplied by the PRODUCTION GitHub
# environment; the defaults match the current Contabo cPanel account.
FRONTEND_DIR="${PRODUCTION_FRONTEND_PATH:-$HOME_ROOT/public_html}"
BACKEND_DIR="${PRODUCTION_BACKEND_PATH:-$HOME_ROOT/crm_backend}"
REPOSITORY_DIR="${PRODUCTION_REPOSITORY_PATH:-$HOME_ROOT/repositories/nakshatech-asset-management-system}"

# Deployment workspace (outside public_html, private to the account).
DEPLOY_ROOT="$HOME_ROOT/erp-releases"
RELEASES="$DEPLOY_ROOT/releases"
INCOMING="$DEPLOY_ROOT/incoming"
SHARED="$DEPLOY_ROOT/shared"

ENV_FILE="$BACKEND_DIR/.env"
VENV="${NAKSHA_VENV:-$HOME_ROOT/crm_venv}"
BACKUPS="$HOME_ROOT/erp-backups"
LOCK_FILE="$DEPLOY_ROOT/deploy.lock"

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

is_under_home() {
  [[ "$1" == /* && "$1" == "$HOME_ROOT"/* && "$1" != *".."* ]]
}

validate_native_paths() {
  is_under_home "$BACKEND_DIR" || fail "PRODUCTION_BACKEND_PATH must be a canonical path under $HOME_ROOT (got '$BACKEND_DIR')"
  is_under_home "$REPOSITORY_DIR" || fail "PRODUCTION_REPOSITORY_PATH must be under $HOME_ROOT (got '$REPOSITORY_DIR')"
  is_under_home "$FRONTEND_DIR" || fail "Unexpected frontend document root $FRONTEND_DIR"
  [[ "$BACKEND_DIR" != "$FRONTEND_DIR" && "$BACKEND_DIR" != "$FRONTEND_DIR"/* ]] \
    || fail "The backend must never live inside the frontend document root (public_html)"
  [[ "$REPOSITORY_DIR" != "$FRONTEND_DIR" && "$REPOSITORY_DIR" != "$FRONTEND_DIR"/* ]] \
    || fail "The Git repository checkout must never live inside the frontend document root"
  [[ "$REPOSITORY_DIR" != "$BACKEND_DIR" ]] \
    || fail "PRODUCTION_REPOSITORY_PATH and PRODUCTION_BACKEND_PATH must be different directories"
  [[ ! -L "$BACKEND_DIR" ]] || fail "PRODUCTION_BACKEND_PATH must not be a symlink"
  [[ ! -L "$FRONTEND_DIR" ]] || fail "PRODUCTION_FRONTEND_PATH must not be a symlink"
  [[ -d "$FRONTEND_DIR" ]] || fail "Missing frontend document root $FRONTEND_DIR"
}

require_account() {
  [[ "${HOME:-}" == "$HOME_ROOT" ]] || fail "Deployment must run inside the $ACCOUNT cPanel account (HOME=$HOME_ROOT)"
  [[ "$(id -un)" == "$ACCOUNT" ]] || fail "Deployment must run as $ACCOUNT, not $(id -un)"
  [[ -d "$HOME_ROOT" && ! -L "$HOME_ROOT" ]] || fail "Missing canonical account home $HOME_ROOT"
  validate_native_paths
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
  mkdir -p "$RELEASES" "$INCOMING" "$SHARED" "$BACKUPS" \
    "$BACKEND_DIR/tmp" "$BACKEND_DIR/uploads" "$REPOSITORY_DIR/.deployment"
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

write_release_markers() {
  local sha="$1"
  mkdir -p "$REPOSITORY_DIR/.deployment"
  printf '%s\n' "$sha" > "$REPOSITORY_DIR/.deployment/release-sha"
  printf '%s\n' "$(date -u +%Y%m%dT%H%M%SZ)" > "$REPOSITORY_DIR/.deployment/deployed-at"
  printf '%s\n' "$BACKEND_DIR" > "$REPOSITORY_DIR/.deployment/backend-path"
  printf '%s\n' "$FRONTEND_DIR" > "$REPOSITORY_DIR/.deployment/frontend-path"
}

# Backend source is synchronised in place so the existing .env, virtual
# environment, uploads, tmp and logs are preserved. Excluded paths are protected
# from --delete, so this never removes production data or configuration.
sync_backend() {
  local release="$1" sha="$2"
  [[ -d "$release/backend" ]] || fail "Release is missing backend sources"
  log "Synchronising backend sources into $BACKEND_DIR"
  rsync -a --delete \
    --exclude '.env' \
    --exclude '.env.*' \
    --exclude 'RELEASE_SHA' \
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
  printf '%s\n' "$sha" > "$BACKEND_DIR/RELEASE_SHA"
  mkdir -p "$REPOSITORY_DIR/.deployment"
  printf '%s\n' "$sha" > "$REPOSITORY_DIR/.deployment/backend-sha"
}

# Only the compiled frontend is published. public_html may also host the
# existing NMaps application, so this never deletes anything outside
# public_html/assets. Hashed assets are the only directory replaced wholesale;
# index.html and .htaccess are swapped with an atomic rename.
sync_frontend() {
  local release="$1" sha="$2" previous="${3:-}" stage
  [[ -f "$release/frontend/index.html" ]] || fail "Release is missing the compiled frontend (frontend/index.html)"

  stage="$SHARED/frontend-stage/$sha"
  rm -rf "$stage"
  mkdir -p "$stage" "$FRONTEND_DIR/assets" "$SHARED/frontend-previous"
  rsync -a "$release/frontend/" "$stage/"

  if [[ -n "$previous" ]]; then
    mkdir -p "$SHARED/frontend-previous/$previous"
    local name
    for name in index.html .htaccess; do
      [[ ! -f "$FRONTEND_DIR/$name" ]] || cp -p "$FRONTEND_DIR/$name" "$SHARED/frontend-previous/$previous/$name"
    done
  fi

  log "Publishing compiled frontend into $FRONTEND_DIR"
  rsync -a --delete "$stage/assets/" "$FRONTEND_DIR/assets/"

  # The public release marker lets HTTPS verification prove which commit the
  # live frontend serves. It carries the commit hash and nothing else.
  [[ -f "$stage/release-version.json" ]] || fail "Release is missing frontend/release-version.json"
  [[ "$(tr -d '[:space:]' < "$stage/release-version.json")" == "{\"commit\":\"$sha\"}" ]] \
    || fail "frontend/release-version.json does not describe release $sha"

  local entry base temp
  for entry in "$stage"/*; do
    base="$(basename "$entry")"
    case "$base" in
      assets|index.html|.htaccess|release-version.json) continue ;;
    esac
    rsync -a "$entry" "$FRONTEND_DIR/"
  done
  if [[ -f "$stage/.htaccess" ]]; then
    temp="$FRONTEND_DIR/.htaccess.deploy.$$"
    install -m 644 "$stage/.htaccess" "$temp" && mv -f "$temp" "$FRONTEND_DIR/.htaccess"
  fi
  temp="$FRONTEND_DIR/.index.html.deploy.$$"
  install -m 644 "$stage/index.html" "$temp"
  mv -f "$temp" "$FRONTEND_DIR/index.html"

  temp="$FRONTEND_DIR/.release-version.json.deploy.$$"
  install -m 644 "$stage/release-version.json" "$temp"
  mv -f "$temp" "$FRONTEND_DIR/release-version.json"

  [[ -f "$FRONTEND_DIR/index.html" ]] || fail "Frontend publish did not produce index.html"
  [[ -f "$FRONTEND_DIR/release-version.json" ]] || fail "Frontend publish did not produce release-version.json"
  printf '%s\n' "$sha" > "$SHARED/frontend-sha"
  mkdir -p "$REPOSITORY_DIR/.deployment"
  printf '%s\n' "$sha" > "$REPOSITORY_DIR/.deployment/frontend-sha"
  rm -rf "$stage"
}

# Schema-sensitive sources: reviewed SQL migrations plus the startup schema
# compatibility modules that can alter tables. Comparing the fingerprint of the
# previous release with the new one decides whether an administrator must
# approve the release SHA before a restart may touch the database.
schema_fingerprint() {
  local release="$1" backend="$1/backend"
  [[ -d "$backend" ]] || { printf 'missing'; return 0; }
  (
    cd "$backend"
    {
      find app -type f \( \
        -name 'schema_migrations.py' -o \
        -name 'schema_compat*.py' -o \
        -name 'migrate.py' \
      \) -print 2>/dev/null || true
      find migrations -maxdepth 1 -type f -name '*.sql' -print 2>/dev/null || true
    } | LC_ALL=C sort | while IFS= read -r file; do
        printf '%s  %s\n' "$file" "$(sha256sum "$file" | cut -d' ' -f1)"
      done | sha256sum | cut -d' ' -f1
  )
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

# Startup runs idempotent schema compatibility routines, which can take several
# minutes on a first installation or a large database. Allow up to 300 seconds.
wait_for_backend() {
  local url="http://127.0.0.1:$(backend_port)/api/health" attempt attempts=300
  for attempt in $(seq 1 "$attempts"); do
    if curl -fsS --max-time 5 "$url" >/dev/null 2>&1; then
      log "Backend answered $url after ${attempt}s"
      return 0
    fi
    # A service that exited during startup (import error, bad migration) is
    # reported as inactive by systemd; stop waiting instead of burning the full
    # startup budget and leave the previous release active sooner.
    if (( attempt % 5 == 0 )) && [[ "$(backend_runtime)" == "systemd" ]]; then
      if ! sudo -n /usr/bin/systemctl is-active --quiet nakshatech-crm.service 2>/dev/null; then
        fail "nakshatech-crm.service is not active; inspect journalctl -u nakshatech-crm -n 100"
      fi
    fi
    if (( attempt % 30 == 0 )); then
      log "Waiting for backend startup (${attempt}s of ${attempts}s)"
    fi
    sleep 1
  done
  fail "Backend did not become healthy at $url within ${attempts} seconds"
}
