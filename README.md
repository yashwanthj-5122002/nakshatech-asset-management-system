# NakshaTech Asset Management System

A runnable role-based Asset Management System with the supplied NakshaTech navy-and-white visual theme, company logo, welcome page, login page, IT asset operations, drone operations, management monitoring and admin control.

The current IT inventory is seeded from `!NakshaTech Asset Details.xlsx` and loads **183 records** from the July 2026 sheet:

- 153 computers
- 28 laptops
- 2 smartphones

## Included working modules

### Welcome and login
- Premium NakshaTech welcome page based on the supplied reference design
- One login screen with Admin, Management, IT and Drone role selection
- Role validation and JWT authentication
- Responsive desktop, tablet and mobile layouts

### IT department
- Clean IT dashboard with KPI cards, charts, alerts and recent work
- Searchable asset register using asset ID, employee, department, CPU tag, monitor tag, system name, IP or MAC
- Asset detail profile and status history
- Add new IT asset
- Work-start, progress, completion, approval and closure records
- Replacement workflow for failed, destroyed or worn-out assets
- Old asset to new asset linkage
- Repair, returned, damaged, retired, for-parts and disposal statuses
- Data-quality alerts for missing employee, MAC/IP and duplicate IP values

### Excel
- Download the current asset register in the same NakshaTech workbook structure and column order as the supplied Excel
- Preserve the historical monthly sheets
- Download dashboard Excel with Dashboard Summary, Asset Register, Asset Status, Department Summary, Work Records, Replacement Records and Data Quality sheets
- Download a blank upload template
- Admin-only validated Excel import

### Drone
- Drone fleet dashboard
- Project, pilot, battery and status records
- MapLibre map using current or last-known coordinates
- Telemetry REST endpoint and WebSocket-ready structure
- Manual or manufacturer/GPS integration path

### Management and admin
- Management view of IT, drone, work, replacements and reports
- Replacement approval and new-asset assignment
- Completed-work approval and closure
- Admin overview, development credentials and future-module structure

## UI preview

The corrected implementation preview is included at `docs/UI_PREVIEW.png`. Separate 1680px and 1366px screenshots are also available in `docs/WELCOME_UI_FIXED*.png` and `docs/LOGIN_UI_FIXED*.png`. The pages use the NakshaTech navy, white and cyan design language with viewport-safe desktop alignment.

## Ports

| Service | Address |
|---|---|
| Frontend | http://localhost:3100 |
| Unified Nginx application | http://localhost:8088 |
| Backend API | http://localhost:8100 |
| Swagger API documentation | http://localhost:8100/docs |
| PostgreSQL/PostGIS | localhost:5434 |
| Redis | localhost:6380 |
| MinIO API | http://localhost:9004 |
| MinIO Console | http://localhost:9005 |

Port **3000 is not used**.

## Windows start

1. Install and start Docker Desktop.
2. Extract this project.
3. Double-click `START_WINDOWS.cmd`.
4. Open http://localhost:3100.

When replacing an older copy that is already running, double-click `REBUILD_UI_WINDOWS.cmd` and press `Ctrl+F5` in Chrome after it finishes.

PowerShell alternative:

```powershell
Copy-Item .env.example .env
Docker compose up --build
```

The correct command is lowercase on most systems:

```powershell
docker compose up --build
```

Run in the foreground for the first start so errors remain visible. Initial image downloads and package installation can take several minutes.

## Stop

Double-click `STOP_WINDOWS.cmd`, or run:

```powershell
docker compose down
```

## Clean reset

Use this only when you deliberately want to delete the local development database, imported records and Docker volumes:

```powershell
docker compose down -v
docker compose up --build
```

You can also double-click `RESET_AND_START_WINDOWS.cmd`.

## Development credentials

| Role | Email | Password | Access |
|---|---|---|---|
| Admin | `admin@nakshatech.com` | `Admin@123` | All dashboards, users, imports, approvals and reports |
| Management | `management@nakshatech.com` | `Manager@123` | Management, IT/drone monitoring, approvals and reports |
| IT | `it@nakshatech.com` | `IT@123456` | IT dashboard, assets, work, replacement requests and reports |
| Drone | `drone@nakshatech.com` | `Drone@123` | Drone dashboard and drone work records |

The login role cards automatically fill the matching development credentials. Replace these accounts with branch/company email IDs before production.

## Important production changes

Before public or company-wide deployment:

- Change every development password.
- Replace `JWT_SECRET` with a private random secret.
- Replace default PostgreSQL and MinIO credentials.
- Disable automatic seed users.
- Add branch, employee and company-email masters.
- Add HTTPS and a real domain through Nginx or Cloudflare.
- Configure backups for PostgreSQL and MinIO.
- Connect a manufacturer SDK, controller gateway or GPS tracker for live drone telemetry.

## Backend tests

From the `backend` folder:

```powershell
$env:PYTHONPATH="."
pytest -q
```

The included tests verify all four logins, role permissions, the 183 seeded IT records, dashboard counts, company-format Excel export, dashboard export, work creation and replacement requests.

## Main folders

- `frontend/src/pages` — welcome, login and role dashboards
- `frontend/src/components` — shared UI, charts, layout and map components
- `backend/app/api` — REST and WebSocket endpoints
- `backend/app/models` — database entities
- `backend/app/services` — Excel import/export and seed processing
- `backend/app/data` — supplied NakshaTech workbook used for initial seed and export template
- `docs` — architecture and complete folder tree


## July 2026 Full-page and Component History Enhancement

- Add IT Asset is now a full-page single-scroll form at `/assets/new`.
- CPU / Physical Asset Tag and Workstation Number are the primary operational identifiers.
- Work Records includes a Component / Configuration Change mode.
- Current values update immediately in the Asset Register and monthly Asset Excel.
- Old-to-new values are preserved in a separate Replacement History Excel.
- Complete CPU/laptop replacement remains under the Replacements page.

Apply the update using `APPLY_FULLPAGE_ENHANCEMENT_WINDOWS.cmd`.

## Upgrade / Replacement and Monthly Reporting Enhancement

The current release adds:

- Searchable CPU / Asset Tag + Workstation selector
- Upgrade, Replacement and Upgrade + Replacement modes
- Multiple components/fields in one change batch
- One work record linked to all batch items
- Immediate live Asset Register updates
- Separate old-to-new history
- Month selector in Excel & Reports
- Monthly Asset Register, Change History and Movement Summary downloads
- Automatic previous-month snapshot after a month boundary
- Historical workbook month selection, including abbreviated sheet names

Apply this release with `APPLY_MULTI_CHANGE_MONTHLY_WINDOWS.cmd` after running `BACKUP_DATABASE_WINDOWS.cmd`.

## Month Dashboard and Full Asset Search

The IT Dashboard supports live and historical month selection. Historical dashboard and Asset Register views are read-only and retain the selected month through navigation. Use **Return to Present** to return to the current live register.

Component changes opened from Asset Details use the already selected asset with no extra search. Component changes opened directly from Work Records provide a searchable dropdown containing the complete live asset list, searchable by CPU/Asset Tag, Workstation, employee, department, system name, and internal asset ID.

Apply this update on Windows with:

```text
APPLY_MONTH_DASHBOARD_SEARCH_WINDOWS.cmd
```

## Disaster-safe backups and historical Excel

This release includes the role-aware **Backups & History** page at `/backups` and an independent scheduled backup runner.

- Excel periods: selected day, selected month, current month live, calendar year, financial year and full current backup.
- Admin can save protected Excel + PostgreSQL recovery files on the server.
- Management can download complete/department Excel reports.
- IT and Drone users can download only their department reports.
- cPanel cron entrypoint: `cpanel/cron/run_scheduled_backup.sh`.
- Windows/Docker installer: `APPLY_BACKUP_FEATURE_WINDOWS.cmd`.
- Full implementation and cPanel notes: `docs/BACKUP_FEATURE_IMPLEMENTATION.md` and `docs/CPANEL_DEPLOYMENT_AND_BACKUP.md`.

Backups must be stored outside the application and outside `public_html`. Excel is for readable audit/reporting; the PostgreSQL dump is the disaster-recovery source.
