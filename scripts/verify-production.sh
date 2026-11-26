#!/usr/bin/env bash
# Post-deployment health verification for the native cPanel runtime.
#
# Confirms that the running backend directory and public_html both come from the
# exact release being verified, then checks infrastructure and public health.
#
# Usage: PRODUCTION_DEPLOY_ENABLED=true bash verify-production.sh <sha>
set -Eeuo pipefail
source "$(dirname "$0")/production-common.sh"

release_path "${1:?release SHA required}"
require_account
[[ -x "$VENV/bin/python" ]] || fail "Virtual environment $VENV is missing"

# --- Same-commit guarantee across both running directories -------------------
read_marker() {
  local path="$1"
  [[ -f "$path" ]] || return 0
  tr -d '[:space:]' < "$path" 2>/dev/null || true
}

backend_marker="$(read_marker "$BACKEND_DIR/RELEASE_SHA")"
[[ "$backend_marker" == "$RELEASE_SHA" ]] \
  || fail "Backend directory $BACKEND_DIR is not running release $RELEASE_SHA (marker: ${backend_marker:-missing})"

frontend_marker="$(read_marker "$SHARED/frontend-sha")"
[[ "$frontend_marker" == "$RELEASE_SHA" ]] \
  || fail "Frontend directory $FRONTEND_DIR was not published from release $RELEASE_SHA (marker: ${frontend_marker:-missing})"

# The repository checkout only records the last successfully committed release,
# so during activation it may still name the release that is being replaced.
repo_marker="$(read_marker "$REPOSITORY_DIR/.deployment/release-sha")"
recorded_release="$(read_marker "$SHARED/current")"
if [[ -n "$repo_marker" && "$repo_marker" != "$RELEASE_SHA" && "$repo_marker" != "$recorded_release" ]]; then
  fail "Deployment metadata in $REPOSITORY_DIR records $repo_marker, expected $RELEASE_SHA or $recorded_release"
fi

for name in index.html .htaccess; do
  [[ -f "$FRONTEND_DIR/$name" ]] || fail "Published frontend is missing $name"
  [[ -f "$release/frontend/$name" ]] || fail "Release $RELEASE_SHA is missing frontend/$name"
  live_hash="$(sha256sum "$FRONTEND_DIR/$name" | cut -d' ' -f1)"
  release_hash="$(sha256sum "$release/frontend/$name" | cut -d' ' -f1)"
  [[ "$live_hash" == "$release_hash" ]] \
    || fail "Published $name does not match release $RELEASE_SHA (frontend was not updated)"
done
[[ -n "$(ls -A "$FRONTEND_DIR/assets" 2>/dev/null)" ]] || fail "Published frontend has no assets"

# --- Infrastructure ---------------------------------------------------------
public_url="$(env_value PRODUCTION_PUBLIC_URL)"
[[ -n "$public_url" ]] || fail "PRODUCTION_PUBLIC_URL is not configured"
public_url="${public_url%/}"
mode="$(backend_runtime)"

log "Checking database connectivity through the application configuration"
(
  cd "$BACKEND_DIR"
  "$VENV/bin/python" - <<'PY'
from sqlalchemy import text
from app.core.database import engine

with engine.connect() as connection:
    connection.execute(text("SELECT 1"))
print("database: ok")
PY
) || fail "Database connectivity check failed"

redis_url="$(env_value REDIS_URL)"
if [[ -n "$redis_url" ]]; then
  log "Checking Redis connectivity"
  (
    cd "$BACKEND_DIR"
    REDIS_URL="$redis_url" "$VENV/bin/python" - <<'PY'
import os
import redis

client = redis.Redis.from_url(os.environ["REDIS_URL"], socket_connect_timeout=10)
if client.ping() is not True:
    raise SystemExit("redis ping failed")
print("redis: ok")
PY
  ) || fail "Redis connectivity check failed"
fi

minio_endpoint="$(env_value MINIO_ENDPOINT)"
if [[ -n "$minio_endpoint" ]]; then
  scheme="http"
  [[ "$(env_value MINIO_SECURE)" == "true" ]] && scheme="https"
  log "Checking MinIO/S3 health endpoint"
  curl -fsS --max-time 15 "${scheme}://${minio_endpoint}/minio/health/live" >/dev/null \
    || fail "MinIO/S3 health check failed at ${scheme}://${minio_endpoint}"
fi

if [[ "$mode" == "systemd" ]]; then
  wait_for_backend
fi

log "Checking public API and frontend"
curl -fsS --max-time 30 "$public_url/api/health" | grep -q '"healthy"' \
  || fail "Public API health check failed: $public_url/api/health"
if curl -fsS --max-time 30 "$public_url/" | grep -qi '<html'; then
  log "Frontend index served from $public_url/"
else
  fail "Public frontend did not return HTML at $public_url/"
fi

isolation_url="$(env_value ISOLATION_CHECK_URL)"
if [[ -n "$isolation_url" && "$isolation_url" != "REPLACE_ME" ]]; then
  curl -fsS --max-time 20 "$isolation_url" >/dev/null \
    || fail "Unrelated website isolation check failed: $isolation_url"
fi

log "Verified release $RELEASE_SHA in backend ($BACKEND_DIR) and frontend ($FRONTEND_DIR)"
