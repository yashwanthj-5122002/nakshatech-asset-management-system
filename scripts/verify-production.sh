#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/production-common.sh"
release_path "${1:?release SHA required}"
compose ps --format json >/dev/null
for service in db redis minio backend frontend nginx; do
  id="$(compose ps -q "$service")"
  [[ -n "$id" ]] || fail "Missing service $service"
  [[ "$(docker inspect -f '{{.State.Health.Status}}' "$id")" == healthy ]] || fail "Unhealthy service $service"
done
[[ "$(docker inspect -f '{{.Config.Image}}' "$(compose ps -q backend)")" == "nakshatech-backend:$RELEASE_SHA" ]] || fail "Backend release mismatch"
[[ "$(docker inspect -f '{{.Config.Image}}' "$(compose ps -q frontend)")" == "nakshatech-frontend:$RELEASE_SHA" ]] || fail "Frontend release mismatch"
compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1"' >/dev/null
compose exec -T redis redis-cli ping | grep -qx PONG
compose exec -T minio curl -fsS http://localhost:9000/minio/health/ready >/dev/null
port="$(env_value PRODUCTION_HTTP_PORT)"
curl -fsS -H 'Host: crm.nakshatech.com' "http://127.0.0.1:$port/api/health" >/dev/null
curl -fsS -H 'Host: crm.nakshatech.com' "http://127.0.0.1:$port/" >/dev/null
curl -fsS "$(env_value PRODUCTION_PUBLIC_URL)/api/health" >/dev/null
curl -fsS "$(env_value PRODUCTION_PUBLIC_URL)/" >/dev/null
curl -fsS "$(env_value ISOLATION_CHECK_URL)" >/dev/null
echo "Verified release $RELEASE_SHA and website availability"
