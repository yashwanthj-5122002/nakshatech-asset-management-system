# Backup Feature Manual Test

## 1. Start the application

Rebuild the backend and frontend without deleting volumes:

```powershell
docker compose up -d --build backend frontend nginx
```

Never use `docker compose down -v` during this test.

## 2. Admin test

1. Login as Admin.
2. Open **Backups & History**.
3. Confirm Storage shows `Ready`.
4. Select **Current month live** and **Complete system**.
5. Click **Download Excel**.
6. Confirm the workbook contains `Backup Summary`, IT sheets and Drone sheets.
7. Select **Selected day**.
8. Keep **Include PostgreSQL recovery dump** enabled.
9. Click **Save Backup on Server**.
10. Confirm a successful or completed-with-warnings history record appears.
11. Download the Excel, database dump and manifest from the history row.

## 3. Role tests

### Management

- Can download Complete, IT and Drone Excel.
- Cannot create server backups.
- Cannot download database or MinIO archives.

### IT

- Can download IT Excel only.
- Complete and Drone scopes are rejected by the API.

### Drone

- Can download Drone Excel only.
- Complete and IT scopes are rejected by the API.

## 4. External folder test

Verify backups are outside the public application folder.

Docker default:

```text
<project-parent>/NAKSHA_BACKUPS
```

cPanel recommended:

```text
/home/<cpanel-user>/nakshatech_backups
```

## 5. Crash-resilience test

1. Create a successful backup.
2. Stop the frontend container only.
3. Confirm the backup files still exist in the external folder.
4. Start the frontend again.
5. Confirm history can download the files.

## 6. Cron test

Run manually using the same Python used by production:

```bash
python backend/scripts/run_backup.py --scheduled --created-by "Manual cron verification"
```

Confirm the log contains backup codes and the external folder contains Daily and Current_Month files.
