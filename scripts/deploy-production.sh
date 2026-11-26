#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/production-common.sh"
gate
for command in docker flock curl tar sha256sum; do command -v "$command" >/dev/null || fail "Missing $command"; done
docker info >/dev/null 2>&1 || fail "Docker permission unavailable"
docker compose version >/dev/null
lock
sha="${1:?exact SHA required}"
release_path "$sha"
[[ "$(cat "$release/RELEASE_SHA")" == "$sha" ]] || fail "Artifact SHA mismatch"
[[ "${APPROVED_SCHEMA_SHA:-}" == "$sha" ]] || fail "Administrator must approve startup schema changes for this exact SHA"
[[ "$(df -Pk "$root" | awk 'END {print $4}')" -ge 5242880 ]] || fail "At least 5 GiB free space required"
! grep -q REPLACE_ME "$PRODUCTION_ENV_FILE" || fail "Replace environment placeholders"
for key in DATABASE_URL JWT_SECRET TOTP_ENCRYPTION_KEY POSTGRES_PASSWORD MINIO_ROOT_PASSWORD SMTP_HOST PRODUCTION_HTTP_PORT PRODUCTION_PUBLIC_URL ISOLATION_CHECK_URL; do
  [[ -n "$(env_value "$key")" ]] || fail "Missing $key"
done
previous="$(cat "$root/shared/current" 2>/dev/null || true)"
if [[ -z "$previous" ]]; then
  [[ "${APPROVE_EMPTY_INSTALL:-false}" == true ]] || fail "Initial install requires explicit empty database approval"
  if docker volume ls --format '{{.Name}}' | grep -q '^nakshatech_crm_production_'; then
    fail "Existing production volumes require reviewed adoption and a verified backup"
  fi
fi
compose config --quiet
compose build --pull backend frontend
compose run --rm --no-deps backend python -c 'from app.core.config import settings; settings.validate_production_settings()'
previous="$(cat "$root/shared/current" 2>/dev/null || true)"
if [[ -n "$previous" ]]; then
  PRODUCTION_LOCK_HELD=true bash "$release/scripts/backup-production.sh" "$previous"
  compose stop backend
else
  [[ "${APPROVE_EMPTY_INSTALL:-false}" == true ]] || fail "Initial install requires explicit empty database approval"
fi
trap 'echo "Deployment failed. Data retained. Inspect health and migration compatibility before rollback." >&2' ERR
# Startup runs the existing idempotent schema compatibility routines.
compose up -d --wait --wait-timeout 300
bash "$release/scripts/verify-production.sh" "$sha"
[[ -z "$previous" ]] || printf '%s\n' "$previous" > "$root/shared/previous"
printf '%s\n' "$sha" > "$root/shared/current.tmp"
mv "$root/shared/current.tmp" "$root/shared/current"
echo "Deployed and verified $sha"
