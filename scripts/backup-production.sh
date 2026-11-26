#!/usr/bin/env bash
# Verified native production backup.
#
# Usage: PRODUCTION_DEPLOY_ENABLED=true bash backup-production.sh <current-sha>
#
# Produces a private, permission-restricted directory containing:
#   database.dump       custom-format pg_dump archive
#   database.contents   pg_restore table-of-contents listing (verification)
#   uploads.tar.gz      local upload directory, when present
#   minio/              object storage mirror, when enabled and mc is available
#   production.env      copy of the private environment (contains secrets)
#   SHA256SUMS          checksums of every captured artefact
#   VERIFIED            written only after every check passes
#
# No Docker or container volume is used: data is read through the native
# PostgreSQL client, the application upload directory and the S3/MinIO endpoint.
set -Eeuo pipefail
source "$(dirname "$0")/production-common.sh"

gate
require_account
require_cmd pg_dump pg_restore tar sha256sum date
[[ "${PRODUCTION_LOCK_HELD:-false}" == true ]] || lock
ensure_layout

sha="${1:-$(cat "$SHARED/current" 2>/dev/null || true)}"
require_sha "$sha"
[[ -f "$ENV_FILE" ]] || fail "Missing private production environment $ENV_FILE"

destination="$BACKUPS/$(date -u +%Y%m%dT%H%M%SZ)-$sha"
[[ ! -e "$destination" ]] || fail "Backup destination already exists: $destination"
mkdir -p "$destination/minio"
chmod 700 "$destination"

db_export() {
  [[ -x "$VENV/bin/python" ]] || fail "Virtual environment $VENV is required to read DATABASE_URL"
  "$VENV/bin/python" - "$(env_value DATABASE_URL)" <<'PY'
import shlex
import sys
from sqlalchemy.engine import make_url

url = make_url(sys.argv[1])
values = {
    "PGHOST": url.host or "127.0.0.1",
    "PGPORT": str(url.port or 5432),
    "PGUSER": url.username or "",
    "PGPASSWORD": url.password or "",
    "PGDATABASE": url.database or "",
}
for key, value in values.items():
    print(f"export {key}={shlex.quote(str(value))}")
PY
}

if [[ "$(env_value BACKUP_DATABASE_ENABLED)" == "false" ]]; then
  fail "BACKUP_DATABASE_ENABLED=false. A verified database backup is mandatory before schema changes."
fi

eval "$(db_export)"
export PGCONNECT_TIMEOUT=15
log "Dumping PostgreSQL database $PGDATABASE on $PGHOST:$PGPORT"
pg_dump --format=custom --no-owner --no-privileges --file "$destination/database.dump"
[[ -s "$destination/database.dump" ]] || fail "pg_dump produced an empty archive"
pg_restore --list "$destination/database.dump" > "$destination/database.contents"
[[ -s "$destination/database.contents" ]] || fail "pg_restore could not read the backup archive"
grep -qi 'users' "$destination/database.contents" \
  || fail "Verified archive does not list the users table; refusing to treat it as a valid CRM backup"

if [[ -d "$BACKEND_DIR/uploads" ]]; then
  log "Archiving application uploads"
  tar -czf "$destination/uploads.tar.gz" -C "$BACKEND_DIR" uploads
  gzip -t "$destination/uploads.tar.gz"
fi

minio_endpoint="$(env_value MINIO_ENDPOINT)"
if [[ "$(env_value BACKUP_MINIO_ENABLED)" == "true" ]]; then
  command -v mc >/dev/null 2>&1 || fail "BACKUP_MINIO_ENABLED=true but the MinIO client (mc) is not installed"
  scheme="http"
  [[ "$(env_value MINIO_SECURE)" == "true" ]] && scheme="https"
  log "Mirroring MinIO bucket to the backup directory"
  MC_HOST_backup="${scheme}://$(env_value MINIO_ROOT_USER):$(env_value MINIO_ROOT_PASSWORD)@${minio_endpoint}" \
    mc mirror --overwrite --quiet "backup/$(env_value MINIO_BUCKET)" "$destination/minio"
else
  log "Object storage backup disabled (BACKUP_MINIO_ENABLED != true); MinIO objects are untouched"
fi

cp -p "$ENV_FILE" "$destination/production.env"
chmod 600 "$destination/production.env"
printf '%s\n' "$sha" > "$destination/release-sha"
[[ ! -f "$SHARED/previous" ]] || cp -p "$SHARED/previous" "$destination/previous-release" 2>/dev/null || true

(
  cd "$destination"
  sha256sum database.dump database.contents production.env > SHA256SUMS
  [[ ! -f uploads.tar.gz ]] || sha256sum uploads.tar.gz >> SHA256SUMS
  sha256sum -c SHA256SUMS >/dev/null
)
touch "$destination/VERIFIED"

# Backups are never deleted automatically; retention is an administrator-reviewed
# operation (see docs/PRODUCTION_DEPLOYMENT_GUIDE.md).
echo "$destination"
