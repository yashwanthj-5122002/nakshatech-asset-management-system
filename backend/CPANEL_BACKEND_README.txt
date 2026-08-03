NAKSHATECH CRM BACKEND - CPANEL/PASSENGER
=========================================

Target:
  Application root: /home/nakshatechws/crm_backend
  Application URL: https://crm.nakshatech.com/api
  Startup file: passenger_wsgi.py
  Entry point: application
  Python: 3.12 preferred, 3.11 supported

Install dependencies inside the cPanel virtual environment:
  pip install -r requirements-cpanel.txt

Copy .env.production.example to .env and replace all CHANGE_ME values.
The API_PREFIX must remain empty because Passenger mounts the app at /api.

Initialize/check:
  python scripts/cpanel_initialize.py
  python scripts/cpanel_route_check.py

After deployment, test:
  https://crm.nakshatech.com/api/health
  https://crm.nakshatech.com/api/docs

Shared cPanel Passenger is WSGI. Normal HTTP features work. The existing raw
WebSocket endpoint is retained in source but is not available through WSGI.
The current visible frontend does not depend on that socket for its normal pages.
