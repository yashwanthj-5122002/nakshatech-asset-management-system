# cPanel subdomain deployment and backup requirements

## Native hosting status

Production for `https://crm.nakshatech.com` runs **natively** on the Contabo
Ubuntu 24.04 cPanel server, account `crmnakshatech`. Docker is not installed or
used there.

The runtime consists of:

- React/Vite frontend compiled on GitHub Actions and published to
  `/home/crmnakshatech/public_html`
- FastAPI backend at `/home/crmnakshatech/crm_backend`, served by Uvicorn under
  an administrator-installed systemd unit on `127.0.0.1:8010`, or by Passenger
  WSGI as the documented alternative
- Python 3.12 in a dedicated virtual environment
  (`/home/crmnakshatech/crm_venv`)
- PostgreSQL, Redis and MinIO/S3 through private production environment
  variables (cPanel-managed or approved external services)
- SMTP for email/OTP and Authenticator MFA for privileged accounts
- `deploy/apache` or `deploy/nginx` snippets for the `/api` proxy, installed for
  this domain only

Raw WebSocket telemetry is available on the systemd/Uvicorn runtime when the
proxy forwards Upgrade headers. Passenger's WSGI adapter supports normal HTTP
(uploads, Excel/PDF downloads) but not WebSocket upgrades.

Authoritative instructions, including the systemd unit, the scoped sudoers rule,
Passenger configuration, API prefix matrix and rollback procedure:
[PRODUCTION_DEPLOYMENT_GUIDE.md](PRODUCTION_DEPLOYMENT_GUIDE.md).

## Hosting prerequisites

The hosting administrator must confirm/enable:

- shell/SSH access for `crmnakshatech` with a dedicated deploy key
- Python 3.12 and the ability to create a virtual environment
- PostgreSQL database + user, `pg_dump` and `pg_restore`
- Redis and MinIO/S3 (local or approved external endpoints)
- Cron Jobs
- systemd unit installation, the restricted sudoers rule and the `/api` proxy
- DNS and AutoSSL for `crm.nakshatech.com`

## Backup storage

Use a private directory under the account home, never the subdomain document
root:

```text
/home/crmnakshatech/erp-backups
```

Set in the private environment:

```text
BACKUP_ROOT=/home/crmnakshatech/erp-backups
BACKUP_TIMEZONE=Asia/Kolkata
BACKUP_DATABASE_ENABLED=true
BACKUP_MINIO_ENABLED=false
PG_DUMP_BIN=/usr/bin/pg_dump
```

Recommended permissions:

```bash
chmod 700 /home/crmnakshatech/erp-backups
```

Deployment writes a verified backup (`database.dump`, `database.contents`,
`uploads.tar.gz`, optional `minio/`, `production.env`, `SHA256SUMS`, `VERIFIED`)
before any schema-affecting upgrade. Backups are never deleted automatically and
no database dump is ever stored under `public_html`.

## cPanel Cron Jobs

In **cPanel → Advanced → Cron Jobs**, schedule once daily, for example at 11:55 PM:

```cron
55 23 * * * /home/crmnakshatech/crm_venv/bin/python /home/crmnakshatech/crm_backend/scripts/run_backup.py --scheduled --created-by "cPanel Cron" >> /home/crmnakshatech/erp-backups/cron.log 2>&1
```

## Subdomain and CORS

Production is same-origin, so the browser calls `/api` on the same host. Set:

```text
CORS_ORIGINS=https://crm.nakshatech.com
TRUSTED_HOSTS=crm.nakshatech.com,127.0.0.1,localhost
```

Use HTTPS and replace every development credential and secret before public
access.

## Preflight

Run the read-only check on the server:

```bash
bash cpanel/preflight_check.sh
```

It reports Python, PostgreSQL client tools, `rsync`, `flock`, the native
directories, the private `.env` mode and the available restart mechanism. It does
not change the server.
