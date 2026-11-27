#!/bin/sh
# Builds the compiled frontend for native cPanel static hosting.
# Produces frontend/dist (index.html, assets/, .htaccess) for public_html.
set -eu
cd "$(dirname "$0")"
rm -rf dist
npm install --no-audit --no-fund
VITE_API_URL=/api npm run build
cp -p public/.htaccess dist/.htaccess
test -f dist/index.html
printf 'Built native cPanel frontend in %s/dist\n' "$(pwd)"
printf 'Publish only dist/ contents to /home/crmnakshatech/public_html\n'
