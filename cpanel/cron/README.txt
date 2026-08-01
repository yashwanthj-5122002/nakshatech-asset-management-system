NakshaTech cPanel Cron Backup
============================

1. Keep backups outside public_html, for example:
   /home/CPANEL_USER/nakshatech_backups

2. Make the runner executable:
   chmod 700 /home/CPANEL_USER/APP_ROOT/cpanel/cron/run_scheduled_backup.sh

3. Add this in cPanel -> Advanced -> Cron Jobs (11:55 PM daily):

55 23 * * * NAKSHA_APP_ROOT=/home/CPANEL_USER/APP_ROOT NAKSHA_PYTHON_BIN=/home/CPANEL_USER/virtualenv/APP_NAME/3.12/bin/python BACKUP_ROOT=/home/CPANEL_USER/nakshatech_backups /home/CPANEL_USER/APP_ROOT/cpanel/cron/run_scheduled_backup.sh

Replace CPANEL_USER, APP_ROOT, APP_NAME and Python version with the exact values from the hosting account.

4. Review logs at:
   /home/CPANEL_USER/nakshatech_backups/Logs/backup-cron.log

The cron job does not require a browser or the frontend to be open. PostgreSQL and pg_dump must remain reachable.
