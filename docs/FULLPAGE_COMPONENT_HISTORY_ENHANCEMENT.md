# Full-page Asset Form and Replacement History Enhancement

## What changed

### Add IT Asset
- The tabbed popup was removed.
- Add Asset now opens at `/assets/new` as a full page.
- Edit Asset opens at `/assets/{id}/edit` as the same full page.
- All original Excel fields appear on one scrolling page.
- CPU / Physical Asset Tag and Workstation Number appear first.
- The form is grouped into identity, assignment, components, hardware, network/software, financial/approval and review sections.
- A sticky Save bar stays visible at the bottom.

### Operational hierarchy
The IT team identifies each system primarily by:

`CPU / Physical Asset Tag + Workstation Number`

All current fields remain linked beneath that identity:
- Used By and Department
- Monitor, Mouse and Keyboard tags
- Processor, Memory, SSD, HDD and Graphics Card
- Network Type, IP, MAC, OS and Antivirus
- Price, Approved By, Performed By and Remarks

The generated `NT-PC`, `NT-LAP` or `NT-MOB` code remains an internal database reference.

### Component and configuration change workflow
Work Records now has two modes:
1. Normal Work Record
2. Component / Configuration Change

The second mode supports:
- Monitor
- Mouse
- Keyboard
- Processor
- Memory/RAM
- SSD
- HDD
- Graphics Card/GPU
- Network Type
- IP Address
- MAC Address
- Operating System
- Antivirus
- Used By
- Department
- Workstation Number
- Price
- Approved By
- Remarks

When a change is saved:
1. The current Asset Register is updated to the new value.
2. A completed IT work record is created automatically.
3. The old and new values are stored in Component Replacement History.
4. The asset timeline records who changed it and when.
5. The next Asset Register Excel shows the new current value.
6. The separate Replacement History Excel shows old value -> new value.

Missing old tags are recorded as `Not Previously Recorded`; the user is never forced to invent an old tag.

### Full asset replacement
The Replacements page remains only for complete CPU, laptop or major asset replacement.
Dropdowns now display CPU / Physical Asset Tag and Workstation first, with the internal system ID shown secondarily.

### Excel separation
- `NakshaTech Asset Details - <Month Year>.xlsx` contains only current active values.
- `NakshaTech Replacement History - <Month Year>.xlsx` contains:
  - Replacement Summary
  - Component Replacements
  - Complete Asset Replacements
- Replacement history is not added as extra rows to the Asset Register.

## Installation
1. Back up the database with `BACKUP_DATABASE_WINDOWS.cmd`.
2. Extract the update over the current `asset-management-system` folder and choose Replace All.
3. Double-click `APPLY_FULLPAGE_ENHANCEMENT_WINDOWS.cmd`.
4. Open `http://localhost:3100`.
5. Press `Ctrl+Shift+R` once.

Do not run `RESET_AND_START_WINDOWS.cmd` and do not use `docker compose down -v` when preserving existing data.
