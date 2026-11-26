#!/usr/bin/env bash
set -Eeuo pipefail
for file in scripts/*production*.sh; do bash -n "$file"; done
# Parse with dummy values in a temporary private environment file.
temporary="$(mktemp)"
trap 'rm -f "$temporary"' EXIT
cp .env.production.example "$temporary"
export PRODUCTION_ENV_FILE="$temporary"
export RELEASE_SHA=0000000000000000000000000000000000000000
docker compose --env-file "$temporary" -f docker-compose.production.yml config --quiet
python scripts/validate-production.py
