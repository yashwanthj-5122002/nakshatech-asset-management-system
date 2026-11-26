#!/usr/bin/env bash
# Rolls the running backend and frontend back to a previously deployed,
# schema-compatible release.
#
# Usage:
#   PRODUCTION_DEPLOY_ENABLED=true \
#   ROLLBACK_SCHEMA_COMPATIBLE_SHA=<previous-sha> \
#   bash releases/<current-sha>/scripts/rollback-production.sh [previous-sha]
#
# Only application files and Python dependencies are restored. Database and
# object storage are NEVER restored automatically: a database restore is a
# separate, explicitly reviewed operation.
set -Eeuo pipefail
source "$(dirname "$0")/production-common.sh"

gate
lock
require_account
ensure_layout

sha="${1:-$(cat "$SHARED/previous" 2>/dev/null || true)}"
require_sha "$sha"
[[ "${ROLLBACK_SCHEMA_COMPATIBLE_SHA:-}" == "$sha" ]] \
  || fail "An administrator must confirm schema compatibility and set ROLLBACK_SCHEMA_COMPATIBLE_SHA=$sha"
release_path "$sha"

current="$(cat "$SHARED/current" 2>/dev/null || true)"

log "Rolling backend ($BACKEND_DIR) and frontend ($FRONTEND_DIR) back to $sha"
install_python_deps "$release"
sync_backend "$release" "$sha"
sync_frontend "$release" "$sha" "$current"
bash "$release/scripts/restart-production.sh"
bash "$release/scripts/verify-production.sh" "$sha"

# Keep a pointer deeper than the new target; pointing at the same release would
# make a second bare rollback a no-op that still restarts the service.
if [[ -n "$current" && "$current" != "$sha" ]]; then
  printf '%s\n' "$current" > "$SHARED/previous"
fi
printf '%s\n' "$sha" > "$SHARED/current.tmp"
mv "$SHARED/current.tmp" "$SHARED/current"
write_release_markers "$sha"
log "Application rolled back to $sha; database and object storage were left untouched"
