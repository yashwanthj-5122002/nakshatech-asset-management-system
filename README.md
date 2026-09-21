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

## Running manually (without the .cmd scripts)

The `.cmd` wrappers are thin conveniences around standard `docker compose` commands.
You can run everything manually from a terminal in the project root.

### First-time `.env` setup

The `.cmd` scripts generate a `.env` with strong random secrets. To do it manually, copy the example and edit the highlighted values:

```powershell
copy .env.example .env
notepad .env
```

At minimum set these to strong random values (32+ characters):

- `POSTGRES_PASSWORD`
- `JWT_SECRET`
- `MINIO_ROOT_PASSWORD`
- `LOCAL_BACKUP_AGENT_TOKEN`
- `TOTP_ENCRYPTION_KEY`
- All `SEED_*_PASSWORD` values

`git pull` will **never** overwrite your local `.env` (it is gitignored), so your secrets stay intact across updates.

### Start the project

```powershell
docker compose up -d --build
```

This builds the backend and frontend images (cached after the first run) and starts all 6 services: **db**, **redis**, **minio**, **backend**, **frontend**, **nginx**.

### Wait for readiness

```powershell
docker compose ps          # view container status and health
```

The backend healthcheck polls `http://localhost:8100/api/health` and reports `healthy` when the database migrations and seed users are ready. The first boot can take 1–2 minutes.

### Rebuild after code changes

```powershell
docker compose up -d --build
```

Because the backend and frontend mount source code live (`./backend` and `./frontend`), `uvicorn --reload` and `vite --host` auto-restart on file changes — the `--build` step is only needed when `requirements.txt` or `package.json` changes.

### Stop the project (keeps data)

```powershell
docker compose down
```

### Full reset (wipes all local data)

```powershell
docker compose down -v          # removes containers AND named volumes
docker compose up -d --build    # fresh database, re-seeds users
```

### View logs

```powershell
docker compose logs -f backend   # live follow backend logs
docker compose logs -f frontend  # live follow frontend logs
```

### Check health

```powershell
# Backend (returns JSON)
Invoke-WebRequest http://localhost:8100/api/health | Select-Object -Expand Content

# Or just visit in a browser:
#   Frontend:    http://localhost:3100
#   API docs:    http://localhost:8100/docs
#   MinIO UI:    http://localhost:9005
```

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
