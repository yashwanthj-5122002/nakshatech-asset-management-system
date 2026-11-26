#!/usr/bin/env bash
# Native cPanel production release activation.
#
# Usage (on the server, from an extracted release):
#   PRODUCTION_DEPLOY_ENABLED=true \
#   APPROVED_SCHEMA_SHA=<sha> \
#   APPROVE_EMPTY_INSTALL=false \
#   bash releases/<sha>/scripts/deploy-production.sh <sha>
#
# No Docker, Docker Compose, container or container volume is involved.
set -Eeuo pipefail
source "$(dirname "$0")/production-common.sh"

gate
lock
require_account
require_cmd rsync curl tar sha256sum pg_dump pg_restore flock
ensure_layout

sha="${1:?exact release SHA required}"
release_path "$sha"
[[ "${APPROVED_SCHEMA_SHA:-}" == "$sha" ]] \
  || fail "An administrator must review startup schema compatibility and set APPROVED_SCHEMA_SHA to $sha"

[[ -f "$ENV_FILE" && ! -L "$ENV_FILE" ]] || fail "Missing private production environment $ENV_FILE"
[[ "$(stat -c %a "$ENV_FILE")" == "600" ]] || fail "$ENV_FILE must have mode 600"
[[ "$(stat -c %u "$ENV_FILE")" == "$(id -u)" ]] || fail "$ENV_FILE owner mismatch"
! grep -q 'REPLACE_ME' "$ENV_FILE" || fail "Replace every REPLACE_ME placeholder in $ENV_FILE"
for key in DATABASE_URL JWT_SECRET TOTP_ENCRYPTION_KEY PRODUCTION_PUBLIC_URL CORS_ORIGINS; do
  [[ -n "$(env_value "$key")" ]] || fail "Missing $key in $ENV_FILE"
done
require_sha "$APPROVED_SCHEMA_SHA"
[[ "$(df -Pk "$HOME_ROOT" | awk 'END {print $4}')" -ge 2097152 ]] || fail "At least 2 GiB free space is required"

previous="$(cat "$SHARED/current" 2>/dev/null || true)"
if [[ -z "$previous" ]]; then
  [[ "${APPROVE_EMPTY_INSTALL:-false}" == true ]] \
    || fail "Initial native installation requires APPROVE_EMPTY_INSTALL=true"
fi

trap 'echo "Deployment of $sha failed. No database restore was attempted. The release directory $RELEASES/$sha and any verified backup in $BACKUPS are retained; review logs before running scripts/rollback-production.sh." >&2' ERR

# A verified database backup always precedes the restart that may apply
# idempotent startup schema compatibility routines.
if [[ -n "$previous" ]]; then
  log "Creating a verified pre-deployment backup of the current release $previous"
  PRODUCTION_LOCK_HELD=true bash "$release/scripts/backup-production.sh" "$previous"
else
  log "Initial installation: no previous release exists, database backup skipped by administrator approval"
fi

# Dependencies are installed before any source is replaced so a failed install
# leaves the running release untouched.
install_python_deps "$release"

sync_backend "$release"
sync_frontend "$release" "$previous"

bash "$release/scripts/restart-production.sh"
bash "$release/scripts/verify-production.sh" "$sha"

if [[ -n "$previous" ]]; then
  printf '%s\n' "$previous" > "$SHARED/previous"
fi
printf '%s\n' "$sha" > "$SHARED/current.tmp"
mv "$SHARED/current.tmp" "$SHARED/current"
log "Deployed and verified $sha (previous: ${previous:-none})"
