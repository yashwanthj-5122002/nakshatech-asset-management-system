#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/production-common.sh"
gate
# Deployment already owns the lock when invoking this script.
[[ "${PRODUCTION_LOCK_HELD:-false}" == true ]] || lock
release_path "${1:?release SHA required}"
destination="$root/backups/$(date -u +%Y%m%dT%H%M%SZ)-$(cat /proc/sys/kernel/random/uuid)"
mkdir -p "$destination"
# A cold snapshot keeps database, object store and uploads consistent.
compose stop backend minio redis
trap 'compose start redis minio backend >/dev/null' EXIT
compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$destination/database.dump"
compose exec -T db pg_restore --list < "$destination/database.dump" > "$destination/database.contents"
for volume in minio_data uploads redis_data; do
  docker volume inspect "nakshatech_crm_production_$volume" >/dev/null
  docker run --rm --network none --mount "type=volume,src=nakshatech_crm_production_$volume,dst=/data,readonly" alpine:3.21 tar czf - -C /data . > "$destination/$volume.tar.gz"
  gzip -t "$destination/$volume.tar.gz"
done
cp "$PRODUCTION_ENV_FILE" "$destination/production.env"
[[ ! -f "$root/shared/current" ]] || cp "$root/shared/current" "$destination/previous-release"
(cd "$destination"; sha256sum database.dump *.tar.gz production.env > SHA256SUMS; sha256sum -c SHA256SUMS >/dev/null)
touch "$destination/VERIFIED"
echo "$destination"
