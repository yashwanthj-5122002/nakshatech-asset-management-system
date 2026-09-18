# Nakshatech Asset Management — Local Master

This is the clean local development source assembled from the current secure frontend and verified backend. Use this folder as the single source for future local development.

## Start on Windows

1. Start Docker Desktop.
2. Extract the package to `E:\NakshaTech_Asset_Management_Local_Master`.
3. Double-click `SETUP_AND_START_LOCAL_WINDOWS.cmd`.
4. Enter a local Admin email and password.
5. Open `http://localhost:3100`.

The first setup generates a private `.env` and `LOCAL_LOGIN_CREDENTIALS.txt`. Both are ignored by Git and must not be uploaded to cPanel or GitHub.

## Daily commands

- `START_LOCAL_WINDOWS.cmd` — start/rebuild the complete project while preserving data.
- `STOP_LOCAL_WINDOWS.cmd` — stop containers without deleting data.
- `REBUILD_LOCAL_WINDOWS.cmd` — recreate frontend/backend after source changes.
- `LOCAL_STATUS_WINDOWS.cmd` — show container and backend health.
- `CHANGE_LOCAL_USER_PASSWORD_WINDOWS.cmd` — securely change a local application password.
- `RESET_FRESH_LOCAL_DATA_WINDOWS.cmd` — delete only this package's Docker volumes and create a fresh database.

## Services

| Service | URL / Port |
|---|---|
| React frontend | http://localhost:3100 |
| Nginx unified app | http://localhost:8088 |
| FastAPI backend | http://localhost:8100 |
| Swagger docs | http://localhost:8100/docs |
| PostgreSQL/PostGIS | localhost:5434 |
| Redis | localhost:6380 |
| MinIO API | http://localhost:9004 |
| MinIO console | http://localhost:9005 |

## Main code locations

- `frontend/src` — React/TypeScript UI.
- `backend/app` — FastAPI, database, authentication, dashboards, backups, IT and Drone modules.
- `backend/app/services/seed.py` — first-run local users and seed data.
- `docker-compose.yml` — local PostGIS, Redis, MinIO, backend, frontend and Nginx.

## Current login behavior

The login page starts with blank fields. It does not reveal credentials or automatically log in by role. The backend reads the authenticated account's role and sends the user to the allowed dashboard.

## Local vs cPanel

This package is for local Docker development. It does not modify or automatically synchronize the live cPanel database at `crm.nakshatech.com`. Deploy future changes only after local testing and a controlled cPanel backup.

## Authoritative BD → Finance → Ortho workflow (V8)

This source package now uses the V8 project-operations workflow as the authoritative path for BD, Finance, Ortho Project Managers, Team Leads, Production, QC and QA.

Core flow:

`BD client/project setup → Finance approval/return → BD PM assignment → PM team setup → Team Lead work allocation → Production → QC → QA → Delivery → PM operational completion → Finance closure → CLOSED`

Key controls:

- Client ID and Project ID are manually entered and uniqueness-validated.
- Finance must approve a project before BD can assign an Ortho Project Manager.
- Each project has exactly one Team Lead and may have multiple Production, QC and QA employees.
- Team Leads can allocate work only to employees selected by the Project Manager for the matching role.
- Operational users see Client ID + Project ID, never Client Name or commercial information.
- Normal employees see only work packages directly assigned to them.
- Daily cumulative progress is system-calculated from activity records.
- QC and QA rejections return the work to Production with review history preserved.
- PM operational completion requires every work package to be delivered.
- Finance performs the final closure after operational completion.
- Existing Expense approval, IT, Asset, Drone, Travel/KM and Support/Ticket workflows are not replaced by this integration.
- Employee expense-project choices are restricted to projects to which the employee is assigned.

Implementation notes and endpoint details are in `docs/PROJECT_WORKFLOW_V8_INTEGRATION.md`.
