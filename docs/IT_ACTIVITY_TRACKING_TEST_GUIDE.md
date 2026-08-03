# IT Activity Tracking Test Guide

Run these checks after the installer reports success.

## 1. Login regression

Confirm that all existing accounts can still log in:

- Software Team
- Admin
- Management
- IT Department
- Drone Department

Expected: existing passwords remain unchanged and each role retains its existing permissions.

## 2. Navigation

Log in as IT, Admin or Software Team and confirm these pages are visible:

- Handover & Return
- Purchase & Procurement
- Recent Changes
- Excel & Reports

Management should be able to view reports/activity but should not be able to create or import IT activity records.

## 3. Laptop handover test

1. Open **Handover & Return**.
2. Choose **Laptop**.
3. Search/select an existing laptop asset.
4. Enter employee, department, DC/workstation number, condition, accessories and remarks.
5. Choose **Handover**.
6. Enable **Update linked Asset Register** only for this test.
7. Save.

Expected:

- A success message appears.
- The handover record appears in the list.
- The linked asset shows the new employee/department/workstation/status.
- An Asset History entry is created with old and new values.
- Recent Changes includes the activity with the logged-in user and exact date/time.

## 4. Desktop return test

1. Open **Handover & Return**.
2. Choose **Desktop**.
3. Select an assigned desktop.
4. Choose **Return** and enter its returned condition and remarks.
5. Enable **Update linked Asset Register**.
6. Save.

Expected:

- The asset becomes returned and its previous assignment remains in history.
- The return appears in Recent Changes and the monthly workbook.

## 5. Purchase test

1. Open **Purchase & Procurement**.
2. Enter a unique PO number, supplier, item, quantity and unit price.
3. Enter received date, inspection status, approver and remarks.
4. Optionally link an existing asset.
5. Save.

Expected:

- Total price is calculated when not entered manually.
- The purchase appears in the page and Recent Changes.
- The monthly workbook contains it in Purchase Details.

## 6. Existing asset-edit test

1. Open Asset Register.
2. Search a test asset.
3. Full-edit two fields and provide a reason.
4. Save.

Expected:

- Last-updated details and old-to-new history remain correct.
- Recent Changes shows separate detailed rows for both changed fields.
- No duplicate component rows appear.

## 7. Component test

Create one batch containing two component changes, for example:

- RAM: 8 GB to 16 GB
- SSD: 256 GB to 512 GB

Expected:

- Existing component workflow completes normally.
- Both changes share their existing batch ID.
- Recent Changes and Component Changes Excel show two rows, not four.

## 8. Monthly Excel test

1. Open **Recent Changes** or **Excel & Reports**.
2. Select the current month.
3. Download **Complete Monthly IT Activity**.
4. Open the workbook.

Expected sheets:

- Monthly Summary
- Detailed Monthly Activity
- Asset Edit History
- Component Changes
- Laptop Handover Return
- Desktop Handover Return
- Purchase Details
- User Activity Summary

Confirm the test entries show the correct user, role, date, time, asset, old value, new value and reason.

## 9. Historical import check

After the first successful installation, expected totals from the supplied files are approximately:

- 59 laptop records
- 185 desktop records
- 19 purchase records

Rows with invalid or missing source dates are skipped. Historical records without a source time show **Not recorded**.

Re-running the import script should create zero duplicates:

```powershell
cd "E:\NakshaTech_Asset_Management_Local_Master\NakshaTech-Asset-Management-Local-Master"
docker compose exec -T -e PYTHONPATH=/app backend python scripts/import_it_activity_reference_data.py
```

## 10. Drone regression

Log in as Drone Department and verify:

- Drone Dashboard loads
- Drone Assets load
- Drone Kits load
- Drone Projects load
- Drone Operations and Work Records load
- Movement History remains accessible

No IT activity page should change the Drone workflow.

## Useful diagnostics

```powershell
cd "E:\NakshaTech_Asset_Management_Local_Master\NakshaTech-Asset-Management-Local-Master"
docker compose ps
docker compose logs backend --tail 150
docker compose logs frontend --tail 100
```

## Rollback

Run:

```powershell
.\ROLLBACK_IT_ACTIVITY_TRACKING_WINDOWS.cmd
```

The rollback restores source files from the latest integration backup. It does not automatically erase new database rows; this avoids deleting legitimate activity recorded after installation.
