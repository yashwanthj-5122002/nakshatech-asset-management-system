# Manual Test - Month Dashboard and Asset Search

## Test 1 - Present dashboard

1. Open `http://localhost:3100/it`.
2. Confirm the month selector shows the current month as Present.
3. Record Total Assets and Computers.
4. Click Refresh.

Expected: values remain correct and the refresh time updates.

## Test 2 - Historical dashboard

1. Select October 2025 or another past month.
2. Confirm the banner shows READ-ONLY HISTORY.
3. Confirm KPI cards and charts change to that month's data.
4. Confirm Work Records and Replacement Requests are limited to the selected month.

Expected: no Add/Edit controls appear for historical records.

## Test 3 - Dashboard-to-register continuity

1. While viewing a historical dashboard, click View Register.
2. Confirm the title contains the same month.
3. Search using a CPU/Asset Tag or Workstation.
4. Open one row.

Expected: the detail panel opens in read-only mode and no edit/change buttons appear.

## Test 4 - Return to present

1. Click Return to Present.
2. Confirm the live dashboard returns.
3. Open Asset Register.

Expected: current assets and editing controls are available again.

## Test 5 - Component change from Asset Register

1. Open the current Asset Register.
2. Open an asset using the arrow.
3. Click Change Component.

Expected:

- The exact asset is preselected.
- No asset search input is visible.
- CPU/Asset Tag and Workstation are locked.
- Change Selected Asset returns to the register.

## Test 6 - Direct component change from Work Records

1. Open Work Records.
2. Select Upgrade / Replacement.
3. Click inside the system search box without typing.
4. Scroll through the dropdown.
5. Search using a CPU tag, then a Workstation.

Expected:

- The dropdown reports the complete asset count.
- All live assets are available through scrolling/search.
- The correct CPU/Asset Tag and Workstation can be selected.
