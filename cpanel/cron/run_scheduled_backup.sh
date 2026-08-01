#!/bin/bash
set -euo pipefail

# This script is safe for cPanel Cron Jobs. It resolves the project root from
# its own location unless NAKSHA_APP_ROOT is explicitly supplied.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="${NAKSHA_APP_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
PYTHON_BIN="${NAKSHA_PYTHON_BIN:-python3}"
BACKUP_ROOT="${BACKUP_ROOT:-$HOME/nakshatech_backups}"

export BACKUP_ROOT
mkdir -p "$BACKUP_ROOT/Logs"
chmod 700 "$BACKUP_ROOT" 2>/dev/null || true

cd "$APP_ROOT/backend"
"$PYTHON_BIN" scripts/run_backup.py --scheduled --created-by "cPanel Cron" >> "$BACKUP_ROOT/Logs/backup-cron.log" 2>&1
