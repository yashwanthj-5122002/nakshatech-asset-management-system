# NakshaTech IT Asset Management — Team Usage Guide

## 1. What each menu is for

### IT Dashboard
Use this page to view totals, asset status, department distribution, alerts, recent work, and Excel downloads. The **Refresh** button reloads the latest database values and shows the last refresh time.

### Asset Register
Use this page to add, search, open, edit, assign, transfer, return, retire, and inspect the history of IT assets.

### Work Records
Use this page whenever the IT team performs a task on an existing asset: inspection, repair, software installation, upgrade, network configuration, or component replacement.

### Replacements
Use this page only when a complete computer, laptop, or smartphone must be replaced. A monitor, mouse, or keyboard replacement is recorded through a Work Record and an Asset Edit.

### Excel & Reports
Use this page for company-format Excel download, dashboard reports, upload templates, and controlled Excel import.

---

## 2. Register a new asset

1. Open **Asset Register**.
2. Click **Add IT Asset**.
3. Complete the tabs:
   - **Basic** — device type, status, physical tag, system name, location, work mode, date.
   - **Assignment** — employee, department, workstation. Leave these blank for an Available asset.
   - **Components** — monitor, mouse, and keyboard tags.
   - **Hardware** — processor, memory, SSD, HDD, graphics card.
   - **Network & Software** — DHCP/static, IP, MAC, OS, antivirus.
   - **Financial & Notes** — price, approver, remarks. Performed By is captured automatically from the logged-in user.
4. Click **Save Asset** once.
5. The system generates an ID such as `NT-PC-0156`.

### Valid Available asset
- Status: Available
- Used By: blank
- Workstation: blank

### Valid Assigned asset
- Status: Assigned
- Used By: required
- Department: required

The system rejects duplicate CPU/Asset Tags, duplicate MAC addresses, duplicate static IP addresses, invalid IP/MAC formats, and inconsistent Available/Assigned combinations.

---

## 3. Assign or transfer an asset

1. Open the asset row using the arrow.
2. Click **Assign / Transfer**.
3. Enter employee, department, workstation, location, work mode, and date.
4. Confirm Assignment.

Results:
- Office assignment → status becomes **Assigned**.
- Work From Home → status becomes **WFH**.
- Field use → status becomes **Field Deployment**.
- The old and new assignment details remain in the timeline.

---

## 4. Return an asset

1. Open an assigned asset.
2. Click **Return**.
3. Select the final condition:
   - Available after inspection
   - Under repair
   - Damaged
   - Returned, awaiting inspection
4. Confirm whether all components were returned.
5. Save.

The current employee and workstation are cleared, while the previous assignment remains in history.

---

## 5. Record an IT task

1. Open **Work Records**.
2. Select the asset.
3. Enter the work type, title, technician, priority, dates, issue, and initial condition.
4. Submit.
5. Change the record from Open → In Progress → Completed.
6. Management/Admin can approve and close work when approval is required.

Every linked work creation and status update is written into the asset timeline.

---

## 6. Replace a monitor, mouse, keyboard, RAM, SSD, or another component

1. Create a Work Record for the affected computer.
2. Record the failed component and inspection result.
3. Open the asset in Asset Register.
4. Click **Edit**.
5. Open **Components** or **Hardware**.
6. Replace the old tag/specification with the new value.
7. Save Changes.

The asset timeline stores the old value and new value. The complete computer remains active unless the whole system is being replaced.

---

## 7. Replace a complete computer or laptop

1. Create and complete an inspection Work Record.
2. Open **Replacements**.
3. Select the failed asset, damage category, reason, and finding.
4. Submit for approval.
5. Management/Admin selects an Available replacement and approves.

Results:
- Old asset → **Replaced**.
- New asset → **Assigned**.
- Employee, department, location, workstation, and work mode move to the new asset.
- Both assets retain the replacement relationship and history.

---

## 8. Retire or delete

### Real company asset
Use **Retire** or the disposal workflow. Real records must not be permanently deleted.

### QA test asset
A manually created asset whose CPU tag or system name begins with `QA-` shows **Delete QA Test Record**. This permanently removes only the test record and its linked test records.

---

## 9. Excel download

**Download Asset Excel** produces the familiar NakshaTech columns:

`SL, USED BY, WS No, DEPARTMENT, cpu, MONITOR, MOUSE, KB, SYSTEM NAME, DEVICE TYPE, PROCESSOR, MEMORY, SSD, HDD, IP ADDRESS, MAC ADDRESS, GC, OS, ANTIVIRUS, DHCP, PERFORMED BY, APPROVED BY, PRICE, REMARKS, date`

The database stores structured records; the Excel exporter combines them into the company layout.

---

## 10. Simple acceptance test

1. Create `QA-PC-TEST-001` as Available with no employee.
2. Confirm Total Assets, Computers, and Available each increase by one.
3. Try creating the same tag again. It must be rejected.
4. Assign it to a QA employee. Available decreases by one and Assigned increases by one.
5. Return it as Available. Employee and workstation clear.
6. Refresh the dashboard. Counts must match Asset Register.
7. Download Excel and confirm the QA record appears once.
8. Open the QA asset and click **Delete QA Test Record**.

The scenario passes only when every result matches.
