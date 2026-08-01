# Multi-Component Change and Month-Wise Reporting Enhancement

## Operational hierarchy

The IT team identifies a system using the physical operational pair:

```text
CPU / Asset Tag + Workstation Number
```

The internal `NT-PC`, `NT-LAP`, or `NT-MOB` code remains a secondary database reference.

All current information is linked to the selected system: employee, department, monitor, mouse, keyboard, processor, RAM, SSD, HDD, GPU, network type, IP, MAC, OS, antivirus, price, approval, performer and remarks.

## Searchable system selector

Work Records → Upgrade / Replacement now provides a type-ahead search. Users can search by:

- CPU / Physical Asset Tag
- Workstation Number
- Employee
- Department
- System Name
- Internal system code

Results display the CPU tag and workstation first so the correct system can be selected quickly.

## Change types

The user selects one overall work activity:

- **Upgrade** — a working component or configuration is improved.
- **Replacement** — a failed/damaged item is replaced.
- **Upgrade + Replacement** — one work activity contains both types, or a failed item is replaced with a higher specification.

When `Upgrade + Replacement` is chosen, each item can be individually classified.

## Multiple components in one work activity

Use **+ Add Component** to add several change rows under one selected system. For example:

```text
CPU Tag 3953 / Workstation NW045
Batch CHG-0001 / Work ITW-0045

Mouse: 7349 → 8201                Replacement
Keyboard: 6120 → 8250             Replacement
Memory: 8 GB → 16 GB              Upgrade
SSD: 256 GB → 512 GB              Upgrade + Replacement
```

One batch ID and one work record group the activity. Each changed item receives its own history row.

## Live Asset Register behavior

After saving, the current Asset Register is updated atomically. It shows only the latest active values.

```text
Before: 3953 / NW045 / Mouse 7349 / RAM 8 GB
After:  3953 / NW045 / Mouse 8201 / RAM 16 GB
```

Old values are never shown as current values, but remain in history.

## Excel separation

### Monthly Asset Register

Shows the selected month's current/closing values in the familiar NakshaTech 25-column layout.

### Monthly Upgrade & Replacement History

Shows every old-to-new item separately, grouped by batch and work record, plus complete computer/laptop replacements.

### Monthly Asset Summary

Shows:

- Opening/imported baseline
- New manually added assets
- Component upgrades
- Component replacements
- Upgrade + replacement items
- Complete asset replacements
- Returns
- Retired/archived assets
- Closing inventory

## Month continuity

At a month boundary, the backend creates a finalized snapshot of the previous month within one hour. The next month continues from the previous closing state.

```text
July closing: Mouse 8201
August opening/live: Mouse 8201
```

If the mouse changes in August to 9305:

- July remains 8201.
- August current/closing becomes 9305.
- August history shows 8201 → 9305.

Past snapshots are frozen. Admin can manually finalize a live month from Excel & Reports when required.

## Database compatibility

The update adds columns non-destructively to existing `component_replacements` records and creates new monthly snapshot tables. Existing PostgreSQL volumes and data are preserved.
