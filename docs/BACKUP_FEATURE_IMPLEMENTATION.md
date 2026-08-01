# NakshaTech Backup & Historical Reporting Feature

## Purpose

This release adds a separate backup layer around the existing IT and Drone modules. Existing asset, project, work-record, replacement, authentication and role workflows are not rewritten.

## What was added

- Role-aware Backup & Historical Excel page at `/backups`.
- Day-wise, month-wise, current-month, calendar-year, financial-year and full-current Excel exports.
- Protected server-side backup creation for Admin.
- PostgreSQL custom-format database dumps through `pg_dump`.
- Optional MinIO bucket archive when explicitly enabled.
- Backup history, checksums, manifests, file sizes and row counts.
- External backup storage through `BACKUP_ROOT`.
- cPanel/Linux cron runner that does not require a browser.
- Manual database restore helper with an explicit confirmation phrase.
- Additive `backup_runs` table.

## Permission model

| Role | Excel scope | Create server backup | Database/MinIO download |
|---|---|---:|---:|
| Admin | Complete, IT or Drone | Yes | Yes |
| Management | Complete, IT or Drone | No | No |
| IT | IT only | No | No |
| Drone | Drone only | No | No |

## Excel period semantics

- Master-register sheets show the current state for recovery.
- For a selected past IT month, a finalized system snapshot or original historical workbook is used when available.
- Work, movement, replacement, audit and transaction sheets are filtered to the selected period.
- Excel is a readable operational/audit copy. The database dump is the authoritative disaster-recovery file.

## Backup folders

The path is controlled by `BACKUP_ROOT`.

Recommended cPanel value:

```text
/home/<cpanel-user>/nakshatech_backups
```

The folder must remain outside `public_html`.

Docker/local development maps a host directory to `/backups`:

```text
BACKUP_HOST_PATH=../NAKSHA_BACKUPS
BACKUP_ROOT=/backups
```

## Automatic schedule

Run this once per day using cPanel Cron Jobs or Linux cron:

```bash
python backend/scripts/run_backup.py --scheduled
```

Scheduled mode creates:

- A daily complete Excel backup.
- A daily PostgreSQL database dump.
- A current-month live Excel backup.
- Previous-month Excel on the first day of a new month.
- Previous calendar-year Excel on January 1.
- Previous financial-year Excel on April 1.

## Retention

- Daily Excel/manifests: `BACKUP_DAILY_RETENTION_DAYS`, default 90.
- Daily database dumps: `BACKUP_DATABASE_RETENTION_DAYS`, default 30.
- Monthly, yearly and financial-year files are not automatically deleted.

## Safety controls

- Backup lock prevents overlapping jobs.
- Stale locks can be recovered after a configurable timeout.
- Files are written to temporary names and atomically renamed.
- SHA-256 checksums are written to a JSON manifest.
- Stored-file downloads resolve only paths inside `BACKUP_ROOT`.
- Database restore is not exposed through the browser.
- Restore requires the exact CLI confirmation phrase `RESTORE-NAKSHATECH`.
