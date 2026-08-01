#!/bin/bash
set -u
printf 'NakshaTech cPanel deployment preflight\n'
printf '====================================\n'
for command in python3 pg_dump pg_restore; do
  if command -v "$command" >/dev/null 2>&1; then
    printf '[OK] %-12s %s\n' "$command" "$(command -v "$command")"
  else
    printf '[MISSING] %s\n' "$command"
  fi
done
printf '\nHome: %s\n' "$HOME"
printf 'Backup target: %s\n' "$HOME/nakshatech_backups"
mkdir -p "$HOME/nakshatech_backups" && touch "$HOME/nakshatech_backups/.write-test" && rm "$HOME/nakshatech_backups/.write-test" && echo '[OK] Backup folder writable' || echo '[FAIL] Backup folder not writable'
printf '\nCheck cPanel UI for: Application Manager, PostgreSQL Databases, Cron Jobs, Terminal/SSH, and SSL.\n'
