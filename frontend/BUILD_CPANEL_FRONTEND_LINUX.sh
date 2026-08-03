#!/bin/sh
set -eu
cd "$(dirname "$0")"
rm -rf CPANEL_UPLOAD
npm install --no-audit --no-fund
VITE_API_URL=/api npm run build
mkdir -p CPANEL_UPLOAD
cp -a dist/. CPANEL_UPLOAD/
printf 'Built frontend in %s/CPANEL_UPLOAD\n' "$(pwd)"
