NAKSHATECH CRM FRONTEND - NATIVE CPANEL STATIC HOSTING
======================================================

Target document root:
  /home/crmnakshatech/public_html      (domain https://crm.nakshatech.com)

Only compiled build output is published. Source, node_modules and Docker files
are never uploaded to public_html.

Production publishing
---------------------
GitHub Actions compiles the frontend (npm ci && VITE_API_URL=/api npm run build)
and publishes only the required build files. The API is served from the same
origin under /api by the native backend, so the browser never needs a separate
API host.

Manual local build (optional, for a reviewed manual release)
------------------------------------------------------------
  Linux/macOS: sh BUILD_CPANEL_FRONTEND_LINUX.sh
  Windows:     BUILD_CPANEL_FRONTEND_WINDOWS.cmd  (Docker used locally only)

The result is frontend/dist with index.html, assets/ and .htaccess.

Publishing rules
----------------
- index.html, .htaccess and hashed assets/ are copied into public_html.
- public_html/assets/ is the only directory replaced wholesale; stale hashed
  assets are removed there.
- No rsync --delete is ever run against public_html as a whole.
- Existing NMaps files and directories in public_html are never overwritten or
  deleted by this deployment.
- Do not upload node_modules or the frontend source to the public folder.

Routing
-------
frontend/public/.htaccess keeps the React history fallback for real visitor
routes, excludes /api (owned by the backend mount) from the rewrite, and lets
existing files and directories (including NMaps) pass through unchanged.

After publishing, verify:
  https://crm.nakshatech.com/           -> CRM login page
  https://crm.nakshatech.com/api/health -> {"status": "healthy", ...}
  https://crm.nakshatech.com/<deep-link> -> serves the SPA, not a 404

Full instructions: docs/PRODUCTION_DEPLOYMENT_GUIDE.md
