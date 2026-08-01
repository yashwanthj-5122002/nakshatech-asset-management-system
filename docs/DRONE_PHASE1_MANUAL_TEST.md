# Drone Phase 1 Manual Test

1. Back up the database and run `APPLY_DRONE_FOUNDATION_WINDOWS.cmd`.
2. Log in as Admin and open `/drone/import`.
3. Upload `Hardware-Inventory Sheets(1).xlsx` or use **Preview Bundled Source**.
4. Confirm the preview shows 135 parsed records and 52 named attributes.
5. Review warnings. Approve and commit the import.
6. Confirm `/drone/assets` shows 123 permanent assets.
7. Confirm `/drone/kits` shows Trinity Unit 1173 and Unit 1076.
8. Confirm `/drone/projects` contains ICON and allows additional projects.
9. Add one new Drone/Survey asset manually and verify a permanent asset tag is generated.
10. Log in as Drone and confirm Drone pages work but `/it` and `/api/dashboard/it` remain forbidden.
11. Log in as IT and confirm the IT dashboard still shows 183 assets and does not include Drone records.
12. Confirm the legacy `/api/drones` endpoint still responds.
