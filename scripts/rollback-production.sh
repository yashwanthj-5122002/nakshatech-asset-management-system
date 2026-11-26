#!/usr/bin/env bash
# Rolls production back to a previously deployed, schema-compatible release.
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

log "Rolling application back to $sha"
install_python_deps "$release"
sync_backend "$release"
sync_frontend "$release" "$current"
bash "$release/scripts/restart-production.sh"
bash "$release/scripts/verify-production.sh" "$sha"

[[ -z "$current" ]] || printf '%s\n' "$current" > "$SHARED/previous"
printf '%s\n' "$sha" > "$SHARED/current.tmp"
mv "$SHARED/current.tmp" "$SHARED/current"
log "Application rolled back to $sha; database and object storage were left untouched"
