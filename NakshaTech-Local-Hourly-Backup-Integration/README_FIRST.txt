NAKSHATECH LOCAL HOURLY BACKUP INTEGRATION

Target project:
E:\BEST_ASSEST_MANAGEMENT_SYSTEM\BEST_COMPLTEED_FILE\asset-management-system

1. Extract this patch to a separate folder.
2. Double-click APPLY_LOCAL_HOURLY_BACKUP_WINDOWS.cmd.
3. The patch changes only backend/config/tests and adds the local Windows agent.
4. It does not modify frontend pages, routes, dashboards, charts or visualizations.
5. It does not delete or recreate PostgreSQL volumes.
6. The local E:\NakshaTech_Backups folders are prepared immediately.
7. The Windows agent is installed only after the final HTTPS subdomain and token are ready.

After deployment, follow:
patch\docs\LOCAL_BACKUP_DEPLOYMENT_AND_INSTALL.md
