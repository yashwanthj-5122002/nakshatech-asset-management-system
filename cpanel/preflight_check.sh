#!/bin/bash
# Read-only native cPanel preflight. Makes no change to the server.
set -u
printf 'NakshaTech native cPanel deployment preflight\n'
printf '=============================================\n'

for command in python3.12 python3.11 pg_dump pg_restore rsync flock curl tar sha256sum git; do
  if command -v "$command" >/dev/null 2>&1; then
    printf '[OK] %-14s %s\n' "$command" "$(command -v "$command")"
  else
    printf '[MISSING] %s\n' "$command"
  fi
done

printf '\nHome: %s\n' "$HOME"
printf 'Backend: %s\n' "$HOME/crm_backend"
printf 'Frontend: %s\n' "$HOME/public_html"
printf 'Releases: %s\n' "$HOME/erp-releases"
printf 'Virtualenv: %s\n' "${NAKSHA_VENV:-$HOME/crm_venv}"
printf 'Backups: %s\n' "$HOME/erp-backups"

for dir in "$HOME/crm_backend" "$HOME/public_html" "$HOME/erp-releases" "${NAKSHA_VENV:-$HOME/crm_venv}"; do
  if [ -d "$dir" ]; then
    [ -w "$dir" ] && printf '[OK] writable  %s\n' "$dir" || printf '[WARN] not writable %s\n' "$dir"
  else
    printf '[INFO] missing   %s\n' "$dir"
  fi
done

if [ -f "$HOME/crm_backend/.env" ]; then
  mode=$(stat -c %a "$HOME/crm_backend/.env" 2>/dev/null)
  printf '[INFO] .env mode %s (must be 600)\n' "$mode"
  grep -q 'REPLACE_ME' "$HOME/crm_backend/.env" && printf '[WARN] .env still contains REPLACE_ME placeholders\n'
else
  printf '[INFO] .env not created yet\n'
fi

printf '\nRestart mechanism:\n'
if command -v sudo >/dev/null 2>&1 && sudo -n /usr/bin/systemctl is-active --quiet nakshatech-crm.service 2>/dev/null; then
  printf '[OK] approved systemd restart available\n'
elif [ -f "$HOME/crm_backend/passenger_wsgi.py" ]; then
  printf '[INFO] Passenger alternative: touch crm_backend/tmp/restart.txt\n'
else
  printf '[WARN] no restart mechanism detected yet\n'
fi

printf '\nHosting administrator must enable/confirm in cPanel:\n'
printf '  - Shell/SSH access for crmnakshatech (deploy key only)\n'
printf '  - Python 3.12 (Application Manager or Setup Python App)\n'
printf '  - PostgreSQL database + user, Redis, MinIO/S3 endpoint\n'
printf '  - Cron Jobs, AutoSSL for crm.nakshatech.com\n'
printf '  - systemd unit, sudoers rule and /api reverse proxy (see deploy/)\n'
printf '  - NMaps files in public_html must remain untouched\n'
