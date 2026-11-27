NAKSHATECH CRM BACKEND - NATIVE CPANEL (NO DOCKER)
==================================================

Target account: crmnakshatech
  Backend directory: /home/crmnakshatech/crm_backend
  Virtual env:       /home/crmnakshatech/crm_venv
  Private env file:  /home/crmnakshatech/crm_backend/.env   (mode 600)
  Application URL:   https://crm.nakshatech.com/api
  Python:            3.12 (3.11 supported)

Two supported native runtimes
-----------------------------
1. systemd + Uvicorn (preferred)
   Install deploy/systemd/nakshatech-crm.service and the narrowly scoped
   deploy/sudoers/nakshatech-crm-deploy rule as the hosting administrator, then
   let the web server proxy /api/ to 127.0.0.1:8010 (deploy/apache or deploy/nginx
   snippets).
   ASGI prefix handling: API_PREFIX=/api, ROOT_PATH= (empty).
   Entry point: app.batch4_main:app

2. Passenger WSGI (alternative, no proxy or privileged service required)
   Startup file: passenger_wsgi.py
   WSGI callable: application
   ASGI prefix handling: passenger_wsgi.py forces API_PREFIX="" and
   ROOT_PATH="/api" in the Passenger process, so a .env configured for the
   native /api ASGI runtime never double-prefixes under this mount.
   Passenger supplies the /api mount as SCRIPT_NAME and
   passenger_wsgi.py calls initialize_application() before import-time serving.
   Restart signal: touch /home/crmnakshatech/crm_backend/tmp/restart.txt

Install dependencies inside the virtual environment only:
  /home/crmnakshatech/crm_venv/bin/python -m pip install -r requirements-cpanel.txt

Copy ../.env.production.example to .env and replace every REPLACE_ME value.
Never place .env inside public_html and never commit it.

Initialize/check:
  /home/crmnakshatech/crm_venv/bin/python scripts/cpanel_initialize.py
  /home/crmnakshatech/crm_venv/bin/python scripts/cpanel_route_check.py
  /home/crmnakshatech/crm_venv/bin/python scripts/cpanel_route_check.py --no-initialize

After deployment, test:
  https://crm.nakshatech.com/api/health
  https://crm.nakshatech.com/

Production startup uses app.main.initialize_application(), which skips every
development seeder when ENVIRONMENT=production. Existing employee passwords,
Authenticator/MFA secrets and database records are therefore never reset by a
deployment. Only idempotent schema compatibility routines and the default branch
backfill run.

Shared cPanel Passenger is WSGI. Normal HTTP features work. The existing raw
WebSocket endpoint is retained in source but is not available through WSGI; the
native systemd/Uvicorn runtime keeps it available when the proxy forwards
Upgrade headers. The current frontend does not depend on that socket for its
normal pages.

Full instructions: docs/PRODUCTION_DEPLOYMENT_GUIDE.md
