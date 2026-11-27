#!/usr/bin/env bash
# Offline validation of an extracted native production release.
#
# Usage: bash scripts/validate-release-layout.sh /path/to/extracted/release [expected-sha]
#
# Checks that the release contains everything the native cPanel deployment
# publishes - backend sources, compiled frontend, geospatial data, routing rules
# and the public release marker - without connecting to any server.
set -Eeuo pipefail

release="${1:?usage: validate-release-layout.sh <release-dir> [sha]}"
expected="${2:-}"

fail() { echo "ERROR: $*" >&2; exit 1; }
ok() { printf '  ok  %s\n' "$*"; }

[[ -d "$release" ]] || fail "Missing release directory $release"
release="$(cd "$release" && pwd)"

for path in \
  backend/app/main.py \
  backend/requirements-cpanel.txt \
  backend/migrations \
  scripts/deploy-production.sh \
  scripts/production-common.sh \
  scripts/verify-production.sh \
  scripts/rollback-production.sh \
  deploy/systemd/nakshatech-crm.service \
  deploy/sudoers/nakshatech-crm-deploy \
  frontend/index.html \
  frontend/.htaccess \
  frontend/release-version.json \
  frontend/assets \
  frontend/data \
  RELEASE_SHA; do
  [[ -e "$release/$path" ]] || fail "Release is missing $path"
done
ok "backend sources, scripts, deploy assets and frontend present"

sha="$(tr -d '[:space:]' < "$release/RELEASE_SHA")"
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || fail "RELEASE_SHA is not a 40-character commit SHA"
if [[ -n "$expected" && "$expected" != "$sha" ]]; then
  fail "RELEASE_SHA is $sha but $expected was expected"
fi
ok "release SHA $sha"

marker="$(tr -d '[:space:]' < "$release/frontend/release-version.json")"
[[ "$marker" == "{\"commit\":\"$sha\"}" ]] \
  || fail "frontend/release-version.json does not describe release $sha"
ok "public release marker matches the release SHA"

ls "$release"/frontend/assets/*.js >/dev/null 2>&1 || fail "Compiled frontend has no JavaScript bundles"
ls "$release"/frontend/assets/*.css >/dev/null 2>&1 || fail "Compiled frontend has no CSS bundles"
ok "compiled JavaScript and CSS assets present"

ls "$release"/frontend/data/* >/dev/null 2>&1 || fail "Compiled frontend is missing the geographic data directory"
ok "geographic data present"

grep -q '/api' "$release"/frontend/assets/*.js || fail "Compiled frontend does not reference the /api base URL"
ok "production API base URL (/api) is referenced by the bundle"

grep -q 'RewriteRule ^ index.html' "$release/frontend/.htaccess" \
  || fail "frontend/.htaccess lost the SPA history fallback"
grep -q '\^/api' "$release/frontend/.htaccess" \
  || fail "frontend/.htaccess must exclude /api from the SPA fallback"
grep -q 'Options -Indexes' "$release/frontend/.htaccess" || fail "frontend/.htaccess must disable directory listings"
ok "SPA routing keeps /api out of the frontend rewrite"

# A release must never ship production secrets or container configuration.
for forbidden in .env .env.production docker-compose.yml docker-compose.production.yml; do
  [[ ! -e "$release/$forbidden" ]] || fail "Release must not contain $forbidden"
done
if find "$release" -type f \( -name '.env' -o -name '.env.*' \) -print -quit | grep -q .; then
  fail "Release must not contain environment files"
fi
ok "no secrets or container configuration inside the release"

echo "Release layout validation passed for $sha"
