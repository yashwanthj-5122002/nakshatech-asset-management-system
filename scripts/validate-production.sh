#!/usr/bin/env bash
# Offline validation of the native cPanel production deployment.
# Runs on GitHub Actions and any developer machine. It never connects to the
# production server and never requires Docker.
set -Eeuo pipefail
cd "$(dirname "$0")/.."

for file in \
  scripts/deploy-production.sh \
  scripts/backup-production.sh \
  scripts/verify-production.sh \
  scripts/rollback-production.sh \
  scripts/restart-production.sh \
  scripts/production-common.sh \
  scripts/validate-production.sh \
  cpanel/preflight_check.sh; do
  bash -n "$file"
done

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi
[[ -n "$PYTHON_BIN" ]] || { echo "ERROR: Python 3 is required for deployment validation" >&2; exit 1; }
exec "$PYTHON_BIN" scripts/validate-production.py
