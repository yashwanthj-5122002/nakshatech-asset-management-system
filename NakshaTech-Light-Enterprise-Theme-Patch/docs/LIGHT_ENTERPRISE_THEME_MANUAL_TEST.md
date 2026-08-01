# Light Enterprise Theme Manual Test

Use the canonical project path:

`E:\BEST_ASSEST_MANAGEMENT_SYSTEM\BEST_COMPLTEED_FILE\asset-management-system`

## Visual checks

1. Open `http://localhost:3100` and confirm the approved dark Welcome page is unchanged.
2. Open `/login` and confirm the approved dark Login page is unchanged.
3. Login as Admin, Management, IT and Drone.
4. Confirm every internal role uses a dark navy sidebar and light workspace.
5. Confirm page titles, KPI cards, forms, tables, filters and status badges are readable and aligned.
6. Resize to tablet and mobile widths; verify the sidebar becomes a drawer and tables scroll horizontally.

## Functional regression checks

- Login and logout
- Role-based routing
- Dashboard data loading
- Month selection and refresh
- Asset search, filters, add/edit and row navigation
- IT work records and replacement workflow
- Excel/report downloads
- Drone dashboard, assets, kits, projects, operations, work records and movement history
- Pagination, status display and form validation

## Safety

Do not run `docker compose down -v`. The apply script rebuilds and recreates only the frontend container, then restarts Nginx.
