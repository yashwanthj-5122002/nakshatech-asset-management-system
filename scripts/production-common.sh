#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
fail() { echo "ERROR: $*" >&2; exit 1; }
root="${PRODUCTION_ROOT:-/home/crmnakshatech/erp-production}"
[[ "$root" == /home/crmnakshatech/erp-production ]] || fail "Unapproved deployment root"
[[ ! -L "$root" && "$(realpath -m "$root")" == "$root" ]] || fail "Deployment root must be canonical"
export PRODUCTION_ENV_FILE="$root/shared/production.env"
[[ -f "$PRODUCTION_ENV_FILE" && ! -L "$PRODUCTION_ENV_FILE" ]] || fail "Missing private production environment"
[[ "$(stat -c %a "$PRODUCTION_ENV_FILE")" == 600 ]] || fail "Environment requires mode 600"
[[ "$(stat -c %u "$PRODUCTION_ENV_FILE")" == "$(id -u)" ]] || fail "Environment owner mismatch"
env_value() { sed -n "s/^$1=//p" "$PRODUCTION_ENV_FILE"; }
gate() {
  [[ "${PRODUCTION_DEPLOY_ENABLED:-false}" == true && "$(env_value PRODUCTION_DEPLOY_ENABLED)" == true ]] || fail "Production gate is disabled"
}
compose() {
  docker compose --project-name nakshatech_crm_production --env-file "$PRODUCTION_ENV_FILE" -f "$release/docker-compose.production.yml" "$@"
}
require_sha() { [[ "$1" =~ ^[0-9a-f]{40}$ ]] || fail "Expected exact commit SHA"; }
release_path() {
  require_sha "$1"
  release="$root/releases/$1"
  [[ -d "$release" && ! -L "$release" && "$(realpath "$release")" == "$release" ]] || fail "Missing canonical release"
  export RELEASE_SHA="$1"
}
lock() {
  mkdir -p "$root/shared"
  exec 9>"$root/shared/deploy.lock"
  flock -n 9 || fail "Another operation holds the production lock"
}
