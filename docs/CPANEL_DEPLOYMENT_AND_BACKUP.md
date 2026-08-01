# cPanel Subdomain Deployment and Backup Requirements

## Critical deployment distinction

Creating a subdomain in cPanel does not automatically provide the runtime required by this application.

This system currently uses:

- React/Vite frontend
- FastAPI ASGI backend
- PostgreSQL
- Redis
- MinIO
- WebSocket telemetry

### Recommended full-feature deployment

Use cPanel for the subdomain/DNS and point the subdomain to a VPS or server running the application stack. Run the scheduled backup on the same server that can reach PostgreSQL and MinIO.

This is the reliable route for all existing features, including WebSockets.

### Direct shared-cPanel deployment

Proceed only when the hosting provider confirms all of the following:

- cPanel Application Manager is enabled.
- Python 3.11 or 3.12 is available.
- PostgreSQL is available and remote/local connections are permitted.
- `pg_dump` and `pg_restore` are available.
- Cron Jobs are enabled.
- Redis and MinIO are available as external services or supported services.
- The provider supports an ASGI deployment method compatible with FastAPI and WebSockets.

cPanel's standard Python Passenger documentation describes WSGI applications. A normal Passenger WSGI deployment does not provide the existing Drone WebSocket telemetry path. Do not claim full feature parity on ordinary shared hosting without provider confirmation.

Official references:

- https://docs.cpanel.net/cpanel/software/application-manager/
- https://docs.cpanel.net/knowledge-base/web-services/how-to-install-a-python-wsgi-application/
- https://docs.cpanel.net/cpanel/advanced/cron-jobs/
- https://docs.cpanel.net/cpanel/domains/domains/create-a-new-domain/

## Backup storage on cPanel

Use a private directory under the account home, not the subdomain document root:

```text
/home/CPANEL_USER/nakshatech_backups
```

Set:

```text
BACKUP_ROOT=/home/CPANEL_USER/nakshatech_backups
BACKUP_TIMEZONE=Asia/Kolkata
PG_DUMP_BIN=/usr/bin/pg_dump
```

Recommended permissions:

```bash
chmod 700 /home/CPANEL_USER/nakshatech_backups
```

Do not store database dumps under `public_html`.

## cPanel Cron Jobs

In **cPanel → Advanced → Cron Jobs**, schedule once daily, for example at 11:55 PM:

```cron
55 23 * * * /home/CPANEL_USER/virtualenv/nakshatech_asset_management/3.12/bin/python /home/CPANEL_USER/nakshatech_asset_management/backend/scripts/run_backup.py --scheduled --created-by "cPanel Cron" >> /home/CPANEL_USER/nakshatech_backups/Logs/backup-cron.log 2>&1
```

Use the exact virtual-environment and application paths shown in your cPanel account.

## Subdomain and CORS

After the final subdomain is known, set:

```text
CORS_ORIGINS=https://assets.example.com
```

Use HTTPS and replace all development credentials and secrets before public access.

## Preflight

Upload and run:

```bash
bash cpanel/preflight_check.sh
```

The script checks Python, `pg_dump`, `pg_restore` and backup-folder write access. It does not change the server.
