NakshaTech Light Enterprise Theme Patch

Target project:
E:\BEST_ASSEST_MANAGEMENT_SYSTEM\BEST_COMPLTEED_FILE\asset-management-system

Run:
APPLY_LIGHT_ENTERPRISE_THEME_WINDOWS.cmd

This patch changes only:
- frontend\src\styles.css
- frontend\src\components\Layout.tsx

It backs up the existing files, builds/recreates only the frontend service, and restarts Nginx.
It does not recreate backend, PostgreSQL, Redis or MinIO.
