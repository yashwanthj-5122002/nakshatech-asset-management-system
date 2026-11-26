# NakshaTech ERP production deployment (native cPanel, no Docker)

Production for **https://crm.nakshatech.com** runs completely natively on the
Contabo Ubuntu 24.04 cPanel server, account `crmnakshatech`:

- Python 3.12 inside a dedicated virtual environment.
- FastAPI served by Uvicorn under an administrator-installed **systemd** unit,
  with the existing **Passenger WSGI** deployment documented as the alternative.
- PostgreSQL, Redis and MinIO/S3 consumed through private production environment
  variables (cPanel-managed or administrator-approved external services).
- The React frontend compiled on GitHub Actions and published as static files.
- **No Docker, Docker Compose, image, container or container volume is used on
  the production server.** The repository's Docker files remain for local
  development and the isolated GitHub Actions QA runner only.

Production deployment has **not** been executed by this change. The hosting
manager has not yet enabled all required services; see
[Remaining server setup](#remaining-server-setup).

## Architecture

```text
Browser
  -> cPanel HTTPS (AutoSSL) / existing Apache (+ optional cPanel Nginx)
       -> /api/*  reverse proxy to 127.0.0.1:8010 (systemd Uvicorn)
       |          or Passenger WSGI mount at /api (alternative)
       -> /*      static files from /home/crmnakshatech/public_html
                     (React SPA; /api never rewritten to index.html)
  Uvicorn/Passenger -> PostgreSQL + Redis + MinIO/S3 + SMTP (private network)
  GitHub Actions (ubuntu-latest) -> SSH -> native deploy scripts on the server
```

The backend and the frontend share one origin, so no CORS exception is needed
for the production browser and API cookies keep working.

## Directory layout

| Purpose | Path |
| --- | --- |
| Frontend document root (compiled build only) | `/home/crmnakshatech/public_html` |
| Backend application (source, `.env`, `tmp`, `uploads`) | `/home/crmnakshatech/crm_backend` |
| Dedicated virtual environment | `/home/crmnakshatech/crm_venv` |
| Immutable releases | `/home/crmnakshatech/erp-releases/releases/<sha>` |
| Upload staging | `/home/crmnakshatech/erp-releases/incoming` |
| Deployment state (`current`, `previous`, lock) | `/home/crmnakshatech/erp-releases/shared` |
| Verified backups | `/home/crmnakshatech/erp-backups` |
| Git checkout used by cPanel Git Version Control | `/home/crmnakshatech/repositories/nakshatech-asset-management-system` |

`public_html` is never a deployment root for backend code, `erp-releases` is
never web-accessible, and no secret is stored under `public_html`.

## GitHub configuration

Reuse the existing **PRODUCTION** environment (restricted to `main`, reviewers
required) and the six existing repository/environment secrets:

| Secret | Required value |
| --- | --- |
| `CPANEL_HOST` | Server hostname or IPv4 address |
| `CPANEL_USERNAME` | `crmnakshatech` |
| `CPANEL_SSH_PORT` | SSH port (for example `22`) |
| `CPANEL_SSH_KEY` | Private deploy key, dedicated to this repository |
| `CPANEL_KNOWN_HOSTS` | Pinned `known_hosts` line(s) for that host and port |
| `CPANEL_DEPLOY_PATH` | `/home/crmnakshatech` (validated, not used as a shell path) |

PRODUCTION environment variables:

| Variable | Purpose |
| --- | --- |
| `PRODUCTION_DEPLOY_ENABLED` | `false` by default. `true` enables transfer and activation. |
| `APPROVED_SCHEMA_SHA` | Exact main SHA whose startup schema changes an administrator reviewed. Must equal the release SHA. |
| `APPROVE_EMPTY_INSTALL` | `true` only for the very first installation against an approved empty database. |

`PRODUCTION_DEPLOY_ENABLED=false` means the prepare job still builds, validates
and packages the release, but no SSH connection is opened and nothing on the
server changes. `.github/workflows/quality.yml` is unchanged: backend regression,
PostgreSQL tests, TypeScript, frontend checks, production build, Playwright and
dependency audits still gate every release. Docker may remain on that hosted
runner; it is not installed or used on the production server.

## Deployment pipeline

`.github/workflows/deploy-production.yml`:

1. **Prepare** – triggers on a completed `ERP quality checks` run for `main` or
   a manual dispatch. It resolves the current `main` SHA, rejects a stale quality
   run, requires the latest `push` quality run **for that exact SHA** to have
   succeeded, compiles the frontend with `VITE_API_URL=/api`, runs
   `scripts/validate-production.sh`, and packages a release archive containing:
   `backend/`, compiled `frontend/` (including `.htaccess`), `scripts/`,
   `deploy/`, `cpanel/` and `RELEASE_SHA`. A SHA-256 checksum is recorded.
2. **Deploy** – uses the `PRODUCTION` environment. The disabled gate short-circuits
   everything. When enabled it validates the account/path/secrets, re-checks that
   `main` still points at the release SHA, refuses to overwrite an existing
   immutable release directory, uploads the archive, verifies its checksum on the
   server, extracts it, and runs `scripts/deploy-production.sh`.
3. **Rollback** – a manual dispatch with `rollback_sha` runs
   `scripts/rollback-production.sh` for a previously deployed, schema-compatible
   release. It never restores a database automatically.

Concurrency and stale-deployment protection:

- Workflow `concurrency: nakshatech-production` with `cancel-in-progress: false`.
- Server-side `flock` lock at `erp-releases/shared/deploy.lock` for deploy,
  backup and rollback.
- `main` is re-checked immediately before transfer; releases are immutable and
  identified by full commit SHA.

What a deployment preserves:

- `crm_backend/.env` (excluded from synchronisation, never uploaded).
- `crm_backend/uploads/`, `crm_backend/tmp/` and logs (excluded, never deleted).
- The virtual environment, Python packages of other applications, and the
  PostgreSQL database, Redis data and MinIO objects.
- Every file in `public_html` except the CRM's own compiled `assets/` directory.
- Existing employee passwords, Authenticator/MFA secrets and records: production
  startup skips every development seeder (`app/main.py` guards each seeder with
  `if not settings.is_production`), so nothing is reset by a release.

## Native backend runtimes

### 1. systemd + Uvicorn (preferred)

Installed by the hosting administrator (a cPanel account cannot install system
units or grant itself sudo):

```bash
# As root, after a release exists at /home/crmnakshatech/erp-releases/releases/<sha>
install -m 0644 /home/crmnakshatech/erp-releases/releases/<sha>/deploy/systemd/nakshatech-crm.service \
  /etc/systemd/system/nakshatech-crm.service
install -m 0440 -o root -g root \
  /home/crmnakshatech/erp-releases/releases/<sha>/deploy/sudoers/nakshatech-crm-deploy \
  /etc/sudoers.d/nakshatech-crm-deploy
visudo -cf /etc/sudoers.d/nakshatech-crm-deploy
systemctl daemon-reload
systemctl enable --now nakshatech-crm.service
systemctl status nakshatech-crm.service
```

The unit runs `crm_venv/bin/uvicorn app.batch4_main:app --host 127.0.0.1
--port 8010` as `crmnakshatech`, reads `crm_backend/.env` through
pydantic-settings, and restarts automatically. The sudoers rule grants **only**
`restart`, `status` and `is-active` for this single unit — no shell, no package
management, no file editing, no unrestricted sudo. `scripts/restart-production.sh`
uses `sudo -n` and fails loudly if the rule is missing.

Environment for this runtime:

```dotenv
BACKEND_RUNTIME=systemd
BACKEND_PORT=8010
API_PREFIX=/api
ROOT_PATH=
```

### 2. Passenger WSGI (alternative)

No elevated service and no proxy configuration are required; cPanel's Application
Manager (or Setup Python App) mounts the application at `/api`:

```text
Application root:  /home/crmnakshatech/crm_backend
Application URL:   https://crm.nakshatech.com/api
Startup file:      passenger_wsgi.py
Entry point:       application
Python:            3.12 (virtually, /home/crmnakshatech/crm_venv)
```

Environment for this runtime:

```dotenv
BACKEND_RUNTIME=passenger
API_PREFIX=
ROOT_PATH=/api
```

`passenger_wsgi.py` loads `.env` before importing the app, calls
`initialize_application()` explicitly (Passenger does not reliably run ASGI
lifespan hooks) and wraps the ASGI application with `cpanel_wsgi_adapter.py`.
The entry point also **forces** `API_PREFIX=""` and `ROOT_PATH="/api"` in its
own process, so the same `.env` used by the native ASGI runtime (with
`API_PREFIX=/api`) is safe under the Passenger mount and never double-prefixes.
Switching runtimes therefore needs no `.env` edit.
`scripts/restart-production.sh` signals Passenger with
`crm_backend/tmp/restart.txt`.

Trade-off: WSGI supports normal HTTP, uploads and Excel/PDF downloads but not raw
WebSocket upgrades. The native systemd runtime forwards Upgrade headers when the
proxy does.

### API prefix matrix (do not mix)

| Runtime | `API_PREFIX` | `ROOT_PATH` | Application routes | Public URL |
| --- | --- | --- | --- | --- |
| systemd/Uvicorn | `/api` | empty | `/api/health`, `/api/auth/login` | `https://crm.nakshatech.com/api/...` |
| Passenger at `/api` | forced empty by `passenger_wsgi.py` | forced `/api` | `/health`, `/auth/login` | `https://crm.nakshatech.com/api/...` |

`backend/scripts/cpanel_route_check.py` validates the required routes for the
configured mode and fails if routes exist both with and without the prefix
(double mount). Use `--no-initialize` to inspect the imported route tree without
running startup initialisation again.

## Web server integration

Do not replace global cPanel/Apache/Nginx configuration and do not change the
existing NMaps site.

- **Apache (EA4)**, for the systemd runtime: install
  `deploy/apache/crm-api-proxy.conf` through the cPanel EA4 userdata include for
  `crm.nakshatech.com` only, then rebuild the vhost configuration:

  ```bash
  sudo mkdir -p /etc/apache2/conf.d/userdata/std/2_4/crmnakshatech/crm.nakshatech.com
  sudo cp deploy/apache/crm-api-proxy.conf \
    /etc/apache2/conf.d/userdata/std/2_4/crmnakshatech/crm.nakshatech.com/api-proxy.conf
  sudo /usr/local/cpanel/scripts/rebuildhttpdconf
  sudo /usr/local/cpanel/scripts/restartsrv_httpd
  ```

- **Nginx**, only if the administrator's Nginx fronts Apache: include
  `deploy/nginx/crm-api-proxy.conf` inside the existing
  `crm.nakshatech.com` server block, before `location /`. Never replace
  `nginx.conf`.

- **Passenger alternative**: no proxy is needed; the cPanel application mount
  handles `/api`.

Keep AutoSSL/HTTPS redirection, the 100 MiB upload allowance and the 300-second
API timeout. API responses are private (`Cache-Control: no-store`).

### Frontend `.htaccess` and the existing NMaps application

`frontend/public/.htaccess` is published to `public_html/.htaccess` and:

- disables directory listing,
- lets `/api` (and `/api/...`) pass through untouched, so the SPA rewrite can
  never intercept API routes,
- lets every existing file and directory pass through, so NMaps files and
  subdirectories in `public_html` keep working,
- rewrites only unknown visitor routes to `index.html`,
- sets `no-store` for `index.html` and long-lived immutable caching for
  fingerprinted assets.

Deployment never deletes anything in `public_html` outside
`public_html/assets/`, so NMaps files cannot be removed by a CRM release.

## Remaining server setup

Everything below must be done or approved by the hosting administrator before
`PRODUCTION_DEPLOY_ENABLED` is set to `true`. The application is prepared and
validated locally, but the server is not configured or deployed yet.

1. **Account access**
   - Enable shell/SSH access for `crmnakshatech` (the observed account currently
     has shell disabled) and authorise the deploy public key only.
   - Publish the server host key(s) so `CPANEL_KNOWN_HOSTS` can be pinned.
2. **Directories** (as `crmnakshatech`):

   ```bash
   mkdir -p /home/crmnakshatech/erp-releases/{incoming,releases,shared}
   mkdir -p /home/crmnakshatech/crm_backend/{tmp,uploads}
   mkdir -p /home/crmnakshatech/erp-backups
   chmod 700 /home/crmnakshatech/erp-releases /home/crmnakshatech/erp-releases/* \
             /home/crmnakshatech/erp-backups /home/crmnakshatech/crm_backend/tmp
   ```

3. **Python 3.12 and the virtual environment**

   ```bash
   /usr/bin/python3.12 -m venv /home/crmnakshatech/crm_venv
   /home/crmnakshatech/crm_venv/bin/python -m pip install --upgrade pip setuptools wheel
   ```

   Deployment installs `backend/requirements-cpanel.txt` into this environment
   on every release. If the provider uses cPanel's Python App virtualenv instead,
   set `NAKSHA_VENV` for manual runs and keep the systemd paths consistent.
4. **Database, Redis, MinIO/S3** — create the PostgreSQL database and user, the
   Redis instance and the MinIO/S3 bucket, and collect:
   - `DATABASE_URL` (`postgresql+psycopg://user:url-encoded-password@127.0.0.1:5432/db`),
   - `REDIS_URL`,
   - `MINIO_ENDPOINT`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `MINIO_BUCKET`,
     `MINIO_SECURE`.
   Keep every service on loopback or a private network; never publish the MinIO
   console or a raw upload directory.
5. **Private environment**

   ```bash
   install -m 600 /dev/null /home/crmnakshatech/crm_backend/.env
   # paste .env.production.example content, replace every REPLACE_ME
   ```

   Required for activation: `DATABASE_URL`, `JWT_SECRET` (>= 32 chars),
   `TOTP_ENCRYPTION_KEY` (>= 32 chars), `PRODUCTION_PUBLIC_URL`, `CORS_ORIGINS`,
   SMTP settings, `MINIO_*`, `REDIS_URL`. Deployment refuses `REPLACE_ME` and a
   non-600 mode.
6. **Backup tooling** — `pg_dump`/`pg_restore` from the PostgreSQL client package,
   `rsync`, `flock`, `curl`, `tar`; optionally `mc` for object-storage backups
   (`BACKUP_MINIO_ENABLED=true`).
7. **Service, sudoers and proxy** — install the systemd unit, the sudoers rule
   and the Apache or Nginx `/api` proxy snippet as described above.
8. **DNS/AutoSSL** — `crm.nakshatech.com` must resolve to the cPanel account with
   valid HTTPS before the first health check.
9. **First release** — merge a reviewed release to `main`, wait for
   `ERP quality checks`, set `APPROVED_SCHEMA_SHA` to that SHA, temporarily set
   `APPROVE_EMPTY_INSTALL=true` for the approved empty database, then set
   `PRODUCTION_DEPLOY_ENABLED=true` and dispatch **Production deployment**.
   Reset `APPROVE_EMPTY_INSTALL=false` immediately afterwards.
10. **Cron (optional)** — cPanel → Cron Jobs for the application's scheduled
    backup, using the project virtualenv:

    ```cron
    55 23 * * * /home/crmnakshatech/crm_venv/bin/python /home/crmnakshatech/crm_backend/scripts/run_backup.py --scheduled --created-by "cPanel Cron" >> /home/crmnakshatech/erp-backups/cron.log 2>&1
    ```

## Manual operations

Run from the release directory on the server (never from `public_html`):

```bash
# Deploy a release that is already extracted under erp-releases/releases/<sha>
PRODUCTION_DEPLOY_ENABLED=true APPROVED_SCHEMA_SHA=<sha> \
  bash erp-releases/releases/<sha>/scripts/deploy-production.sh <sha>

# Verified backup of the current release
PRODUCTION_DEPLOY_ENABLED=true bash erp-releases/releases/$(cat erp-releases/shared/current)/scripts/backup-production.sh \
  "$(cat erp-releases/shared/current)"

# Health verification
PRODUCTION_DEPLOY_ENABLED=true bash erp-releases/releases/<sha>/scripts/verify-production.sh <sha>

# Application rollback to the recorded previous release
PRODUCTION_DEPLOY_ENABLED=true ROLLBACK_SCHEMA_COMPATIBLE_SHA=<previous-sha> \
  bash erp-releases/releases/<current-sha>/scripts/rollback-production.sh <previous-sha>
```

## Backups, restore and rollback

Before every upgrade the deployment creates a verified backup in a unique
`/home/crmnakshatech/erp-backups/<UTC timestamp>-<sha>/` directory:

- `database.dump` — `pg_dump --format=custom`, plus `database.contents`
  (`pg_restore --list`, must list the `users` table),
- `uploads.tar.gz` — the application upload directory when present,
- `minio/` — object mirror when `BACKUP_MINIO_ENABLED=true` and `mc` is available,
- `production.env` — private configuration copy (mode 600),
- `SHA256SUMS` verified with `sha256sum -c`, and a `VERIFIED` marker written last.

Backups are never deleted automatically. Retain daily backups for 30 days and
monthly for 12 months, copy encrypted backups off-host and prune only through a
reviewed retention process. A failed backup aborts the deployment before any
source is replaced.

A database restore is always a separate, explicitly reviewed operation: stop
writers, verify `SHA256SUMS`, restore into a new empty database with
`pg_restore`, restore MinIO objects, then validate counts, logins and document
downloads before an approved cutover. Never overwrite live storage during a
trial restore.

Application rollback re-syncs the previous release's backend and frontend,
reinstalls that release's Python dependencies, restarts through the approved
mechanism and re-runs health checks. It requires
`ROLLBACK_SCHEMA_COMPATIBLE_SHA` to equal the target SHA, because startup schema
compatibility routines are forward-only. When compatibility is uncertain, stop
and arrange controlled recovery instead of rolling back.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| `Production deployment gate is disabled` | Set `PRODUCTION_DEPLOY_ENABLED=true` in GitHub variables **and** in `crm_backend/.env`. |
| `Administrator-approved restart unavailable` | Install `deploy/sudoers/nakshatech-crm-deploy` and the systemd unit, or set `BACKEND_RUNTIME=passenger`. |
| `Backend did not become healthy` | `journalctl -u nakshatech-crm -n 200`; check `.env` values and database reachability. |
| `Public API health check failed` | Confirm the Apache/Nginx `/api` proxy or Passenger mount; check that `public_html/.htaccess` excludes `/api`. |
| `Missing routes` in `cpanel_route_check.py` | Confirm `API_PREFIX` matches the runtime (table above) and restart the service. |
| `Release <sha> already exists` | Releases are immutable; deploy a new main SHA or roll back explicitly. |
| Backup refuses to run | `BACKUP_DATABASE_ENABLED` must not be `false`; `pg_dump`/`pg_restore` must be on `PATH`. |

Logs: `journalctl -u nakshatech-crm`, `crm_backend/tmp/passenger_startup_error.log`
(Passenger), and the web server's per-domain error log. Never print `.env`.

## Offline validation

`bash scripts/validate-production.sh` (also run by the deploy workflow) checks:

- all workflow and `.cpanel.yml` YAML parses,
- no Docker command remains in the production scripts or deploy workflow,
- `PRODUCTION` environment, disabled gate, concurrency and stale-SHA guard exist,
- all six `CPANEL_*` secrets are referenced and the account/path is
  `/home/crmnakshatech`,
- `.env.production.example` keys, safety switches and `API_PREFIX=/api`,
- LF line endings for shell scripts and deploy files,
- systemd unit, sudoers scope and loopback proxy targets,
- `.htaccess` keeps `/api` out of the SPA rewrite,
- Python sources compile.

See the validation record at the end of this document for the commands actually
executed for this change.

## Validation record (26 November 2026)

All checks below were executed for this change. No server connection, production
deployment, database reset or secret exposure took place.

Offline configuration and syntax validation

- `bash -n` on every deployment script and `cpanel/preflight_check.sh`: passed.
- `python scripts/validate-production.py` (Python 3.12, PyYAML): **Native cPanel
  production validation passed** — YAML parsing, no Docker command in the
  production scripts or deploy workflow, `PRODUCTION` environment, disabled gate,
  concurrency, stale-SHA guard, six `CPANEL_*` secrets, account paths, `.env`
  keys and safety switches, LF endings, systemd unit, sudoers scope, loopback
  proxy targets, `.htaccess` `/api` exclusion, Python syntax.
- `rhysd/actionlint:1.7.7` (Docker) against both workflows: no findings.
- CRLF scan of authored files: none (LF only).

End-to-end native deployment rehearsal in isolated containers

Environment: `python:3.12` container with a real `crmnakshatech` account, a real
PostgreSQL 16 database, Apache 2.4 serving `public_html` with the published
`.htaccess` and the provided `/api` proxy, and an administrator-approved
`sudo systemctl restart` stand-in.

- Initial native installation (`APPROVE_EMPTY_INSTALL=true`): created
  `crm_venv`, installed `requirements-cpanel.txt` (`pip check` clean),
  synchronised backend to `/home/crmnakshatech/crm_backend`, published
  `index.html`, `.htaccess` and `assets/`, restarted the service, and passed
  database, loopback API, public API and frontend health checks.
- Upgrade release: created a **verified** backup (`database.dump`,
  `database.contents`, `uploads.tar.gz`, `production.env`, `SHA256SUMS`,
  `VERIFIED`) before the restart that runs startup schema compatibility, then
  deployed the new release and recorded `previous`/`current`.
- Rollback: restored the previous release's backend source, Python dependencies
  and compiled frontend (including replacing hashed assets), re-ran health
  checks, and left the database and object storage untouched.
- Preservation: `crm_backend/.env` stayed mode 600 and unchanged across
  deployments; `tmp/` and `uploads/` survived `rsync`, which never uses
  `--delete` outside the exclusion list.
- Frontend hosting: `/` and a deep SPA route returned the CRM build, `/api/health`
  returned `{"status":"healthy"}`, and pre-existing `nmaps.html` and
  `nmaps/` stayed reachable and unmodified across three deployments.
- Negative gates: disabled `PRODUCTION_DEPLOY_ENABLED`, unapproved
  `APPROVED_SCHEMA_SHA`, missing `APPROVE_EMPTY_INSTALL` and the server-side lock
  all refused to proceed before changing anything.
- API prefix matrix: `cpanel_route_check.py` passed with `API_PREFIX=/api`
  (native ASGI) and with the Passenger mount; the WSGI adapter answered
  `200 OK` for `SCRIPT_NAME=/api` + `/health` and for `/api/health` with an empty
  `SCRIPT_NAME`, including when `.env` contained `API_PREFIX=/api`.
- `pytest tests/test_production_startup_safety.py` against the real PostgreSQL
  instance: **1 passed**, proving production startup preserves an existing
  password hash and never calls development seeders.

Not executed (external prerequisites)

- Real GitHub Actions run, SSH transfer to the Contabo server and production
  activation: the hosting manager has not enabled shell access, Python 3.12,
  PostgreSQL/Redis/MinIO, systemd, the sudoers rule or the `/api` proxy.
- `pg_restore` of a real backup into a recovery database (the archive was only
  verified with `pg_restore --list`, as documented).
- MinIO object backup (`BACKUP_MINIO_ENABLED=false`) and SMTP delivery.
- Full backend regression, Playwright and dependency audits: covered by the
  existing `ERP quality checks` workflow, which still gates every release.
