# Month Dashboard and Asset Search Enhancement

## Implemented behavior

### IT Dashboard month selector

The IT Dashboard now includes a month selector containing every available live, finalized, and historical month.

Selecting a month updates:

- Total assets
- Computers, laptops, and smartphones
- Assigned, available, repair, and replacement-pending counts
- Device and department charts
- Selected-month work records
- Selected-month complete-asset replacement requests
- Monthly activity totals

Past months are clearly marked as read-only. **Return to Present** returns to the current live register.

### Dashboard-to-register continuity

When a historical month is selected and the user clicks **View Register** or **Open Assets**, the Asset Register opens using the same month.

Historical Asset Register rows are read-only. Edit, assign, return, retire, delete, and component-change actions are hidden.

### Work Records component-change entry paths

#### Entry from Asset Register

`Asset Register -> Open asset -> Change Component`

- The selected asset is locked.
- No search control is shown.
- CPU/Asset Tag and Workstation are displayed prominently.
- A **Change Selected Asset** button returns to the Asset Register.

#### Direct entry from Work Records

`Work Records -> Upgrade / Replacement`

- A searchable dropdown contains the complete live asset list.
- Search supports CPU/Asset Tag, Workstation, employee, department, system name, and internal ID.
- All matching assets are displayed in a scrollable dropdown; results are not limited to a small fixed subset.

### Historical workbook support

Historical company Excel sheets are parsed into read-only asset rows for dashboard and register display. These rows use synthetic internal IDs and cannot modify live data.
