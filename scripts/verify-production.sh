#!/usr/bin/env bash
# Post-deployment health verification for the native cPanel runtime.
#
# Usage: PRODUCTION_DEPLOY_ENABLED=true bash verify-production.sh <sha>
set -Eeuo pipefail
source "$(dirname "$0")/production-common.sh"

release_path "${1:?release SHA required}"
require_account
[[ -x "$VENV/bin/python" ]] || fail "Virtual environment $VENV is missing"

public_url="$(env_value PRODUCTION_PUBLIC_URL)"
[[ -n "$public_url" ]] || fail "PRODUCTION_PUBLIC_URL is not configured"
public_url="${public_url%/}"
mode="$(backend_runtime)"
port="$(backend_port)"

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

log "Verified release $RELEASE_SHA, public API, frontend and infrastructure connectivity"
