#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/production-common.sh"
gate
lock
sha="$(cat "$root/shared/previous")"
require_sha "$sha"
[[ "${ROLLBACK_SCHEMA_COMPATIBLE_SHA:-}" == "$sha" ]] || fail "Review schema compatibility and approve the exact rollback SHA"
release_path "$sha"
# Use retained images only. Never restore a database automatically.
for image in backend frontend; do docker image inspect "nakshatech-$image:$sha" >/dev/null; done
compose up -d --no-build --pull never --wait --wait-timeout 300
bash "$release/scripts/verify-production.sh" "$sha"
printf '%s\n' "$sha" > "$root/shared/current.tmp"
mv "$root/shared/current.tmp" "$root/shared/current"
echo "Application rolled back to $sha"
