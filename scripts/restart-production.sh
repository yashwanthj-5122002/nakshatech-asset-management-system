#!/usr/bin/env bash
# Restarts the native backend using an administrator-approved mechanism only.
#
# systemd (preferred): requires the sudoers drop-in in
# deploy/sudoers/nakshatech-crm-deploy, which permits exactly the restart,
# status and is-active commands for nakshatech-crm.service. Unrestricted sudo is
# never assumed.
#
# Passenger (alternative): touching tmp/restart.txt is the documented cPanel
# restart signal and needs no elevated privileges.
set -Eeuo pipefail
source "$(dirname "$0")/production-common.sh"

require_account
mode="$(backend_runtime)"
service="nakshatech-crm.service"

case "$mode" in
  systemd)
    command -v sudo >/dev/null 2>&1 || fail "sudo is required for the systemd runtime"
    log "Restarting $service through the approved sudoers rule"
    if ! sudo -n /usr/bin/systemctl restart "$service" 2>/dev/null; then
      fail "Administrator-approved restart unavailable. Install deploy/sudoers/nakshatech-crm-deploy and deploy/systemd/nakshatech-crm.service, then retry."
    fi
    sleep 2
    sudo -n /usr/bin/systemctl is-active --quiet "$service" \
      || fail "$service is not active after restart; inspect journalctl -u $service"
    wait_for_backend
    ;;
  passenger)
    log "Signalling Passenger with tmp/restart.txt"
    mkdir -p "$BACKEND_DIR/tmp"
    touch "$BACKEND_DIR/tmp/restart.txt"
    sleep 3
    ;;
  *)
    fail "Unknown BACKEND_RUNTIME '$mode' (expected systemd or passenger)"
    ;;
esac

log "Backend restart completed ($mode)"
