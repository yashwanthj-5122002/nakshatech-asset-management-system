# NakshaTech Asset Management CRM - Complete System Study

## Executive Summary

This is a **comprehensive Enterprise Resource Planning (ERP)** system built for NakshaTech, a geospatial services company. The system manages:
- IT Asset lifecycle (computers, laptops, printers, external HDDs, smartphones)
- Drone & Survey Asset operations
- Employee Portal & Support Ticketing
- Finance & Expense Management
- Operations (Business Development + Ortho/LiDAR Projects)
- Backup & Disaster Recovery

---

## 🏗️ SYSTEM ARCHITECTURE

### Technology Stack
```
Frontend:
├── React + TypeScript
├── Vite (build tool)
├── React Router (navigation)
└── TanStack Query (data fetching)

Backend:
├── FastAPI (Python 3.11+)
├── SQLAlchemy (ORM)
├── PostgreSQL (database)
├── Alembic (migrations)
└── Pydantic (validation)

Infrastructure:
├── Docker + Docker Compose
├── MinIO (S3-compatible object storage)
├── Nginx (reverse proxy)
└── PostgreSQL (database)
```

### File Structure
```
CRMM/
├── frontend/               # React TypeScript frontend
│   ├── src/
│   │   ├── pages/         # Route components
│   │   ├── components/    # Reusable UI components
│   │   ├── context/       # React contexts (Auth, etc.)
│   │   ├── lib/           # Utilities (API, dates, roles)
│   │   └── types.ts       # TypeScript definitions
│   └── package.json
│
├── backend/               # FastAPI Python backend
│   ├── app/
│   │   ├── main.py       # Application entry point
│   │   ├── core/         # Core configuration
│   │   │   ├── config.py        # Settings & env vars
│   │   │   ├── database.py      # DB connection
│   │   │   ├── security.py      # JWT, passwords
│   │   │   ├── roles.py         # Role definitions
│   │   │   └── management_access.py  # Special access
│   │   ├── api/          # API layer
│   │   │   ├── router.py        # Main router
│   │   │   └── dependencies.py  # Auth dependencies
│   │   ├── models/       # Database models
│   │   │   └── entities.py      # Main SQLAlchemy models
│   │   ├── modules/      # Feature modules
│   │   │   ├── it_activity/     # IT asset activities
│   │   │   ├── drone/           # Drone operations
│   │   │   ├── employee_portal/ # Employee features
│   │   │   ├── finance/         # Finance & expenses
│   │   │   ├── operations/      # BD + Ortho operations
│   │   │   └── backup/          # Backup & recovery
│   │   └── services/    # Business logic services
│   │       ├── asset_lifecycle_service.py
│   │       ├── approval_workflow_service.py
│   │       ├── monthly_snapshot_service.py
│   │       └── excel_import_service.py
│   └── requirements.txt
│
└── docker-compose.yml    # Infrastructure orchestration
```

---

## 🔐 AUTHENTICATION & AUTHORIZATION FLOW

### 1. Authentication Flow (Login → JWT → Access)

```
User Login Request
    ↓
[POST /api/auth/login]
    ↓
Backend validates:
  - Email format & domain
  - Password hash (bcrypt)
  - User is_active status
  - Account status
    ↓
Decision Point:
├─ First Login (Management/Admin) → Authenticator Setup Required
├─ Employee First Login → Authenticator Setup Required
└─ Normal Login → Issue JWT Token
    ↓
JWT Token Generated:
  {
    "sub": user.email,
    "uid": user.id,
    "role": user.role,
    "branch_id": selected_branch.id,
    "exp": expiry_timestamp
  }
    ↓
Frontend stores token:
  localStorage (remember=true) OR sessionStorage (remember=false)
    ↓
All subsequent requests include:
  Authorization: Bearer <jwt_token>
```

### 2. Authorization Hierarchy

```
Role-Based Access Control (RBAC):

admin (Highest)
├── Full system access
├── User management
├── All module access
└── Can impersonate other roles

management
├── View-only on most modules
├── Approval authority (Purchase Requests, Expense Claims)
├── Strategic reporting
└── No direct operational edits

software_team (Admin-equivalent)
├── Full technical access
├── Backup & recovery
├── System configuration
└── Development & maintenance

it
├── IT Asset management
├── IT Activity (Handover, Purchase, Repairs)
├── Limited employee portal access
└── Cannot approve purchases

drone
├── Drone Asset management
├── Project operations
├── Kits & equipment tracking
└── Import/export drone data

finance
├── Expense claim processing
├── Client & Project master
├── Approval workflows
└── Financial reporting

hr
├── Employee data
├── Ticket assignments (HR dept)
└── Basic reporting

bd (Business Development)
├── Opportunity tracking
├── Client relationship
├── Project proposals
└── BD dashboard

ortho
├── LiDAR/Ortho project management
├── Work package tracking
├── Quality control (QC/QA)
└── Delivery management

employee (Lowest)
├── Support tickets
├── Personal expense claims
├── Work package updates (if assigned)
└── Self-service portal
```

### 3. Branch-Based Access Control

After authentication, employees must select a branch:
```
User Login Success
    ↓
Branch Selection Required? (for employee role)
    ↓
[POST /api/auth/select-branch]
    ↓
New JWT issued with branch_id claim
    ↓
All data filtered by selected branch
```

### 4. Authorization Enforcement Points

**Route-level protection:**
```python
@router.get("/admin-only")
def admin_endpoint(
    user: User = Depends(require_roles("admin"))
):
    # Only admin can access
```

**Function-level checks:**
```python
def can_edit_asset(user: User, asset: Asset) -> bool:
    if user.role in ("admin", "it"):
        return True
    if user.role == "management":
        return False  # Read-only
    return False
```

**Data-level filtering:**
```python
# Finance claims visible based on role
if role == "employee":
    claims = claims.filter(ExpenseClaim.requester_id == user.id)
elif role == "finance":
    claims = claims  # See all claims
```

---

## 📊 COMPLETE DATA FLOW EXAMPLES

### Example 1: IT Asset Lifecycle (Creation → Assignment → Transfer → Return)

#### Step 1: Asset Creation
```
User navigates to: /assets/new
    ↓
Frontend Form Submission
    ↓
[POST /api/assets]
Request Body:
{
  "cpu_asset_tag": "NT-LAP-0042",
  "device_type": "Laptop",
  "brand": "Dell",
  "model": "Latitude 5420",
  "serial_number": "SN123456",
  "processor": "Intel i7-1165G7",
  "memory_gb": "16GB",
  "ssd": "512GB NVMe",
  "status": "available",
  "department": "IT",
  "location": "IT Store",
  ...
}
    ↓
Backend Validation (backend/app/modules/assets/router.py):
  ├── Check duplicate serial_number
  ├── Validate device_type
  ├── Generate asset_code (NT-LAP-0042)
  └── Check required fields
    ↓
Database Operations:
  1. Create Asset record
  2. Create AssetHistory entry (action="asset_created")
  3. Commit transaction
    ↓
Response:
{
  "id": 42,
  "asset_code": "NT-LAP-0042",
  "cpu_asset_tag": "NT-LAP-0042",
  "status": "available",
  "created_at": "2026-09-10T10:30:00Z",
  ...
}
    ↓
Frontend updates UI:
  ├── Navigate to /assets
  ├── Show success message
  └── Refresh asset list
```

#### Step 2: Asset Assignment
```
User selects asset and clicks "Assign"
    ↓
[POST /api/assets/42/assign]
Request Body:
{
  "used_by": "John Doe",
  "department": "Mapping",
  "workstation_no": "WS-MAP-05",
  "location": "Office - 2nd Floor",
  "work_mode": "office",
  "assigned_date": "2026-09-10",
  "remarks": "New employee onboarding",
  "reporting_month": "2026-09"
}
    ↓
Backend Processing (backend/app/services/asset_lifecycle_service.py):
  1. Load asset from database
  2. Validate assignment (asset must be available/returned)
  3. Create ITHandoverRecord:
     - activity_type: "handover"
     - action_type: "new_assign"
     - employee_name: "John Doe"
     - activity_date: "2026-09-10"
     - reporting_month: "2026-09"
  4. Update Asset:
     - used_by: "John Doe"
     - department: "Mapping"
     - workstation_no: "WS-MAP-05"
     - status: "assigned"
  5. Create AssetHistory:
     - action: "Asset assigned"
     - change_type: "assignment"
     - old_value: null
     - new_value: "John Doe"
     - reporting_month: "2026-09"
  6. Commit transaction
    ↓
Response: Updated Asset + Handover Record
    ↓
Frontend shows: "NT-LAP-0042 assigned to John Doe at WS-MAP-05"
```

#### Step 3: Asset Transfer
```
User selects assigned asset and clicks "Transfer"
    ↓
[POST /api/assets/42/assign]  # Same endpoint, different logic
Request Body:
{
  "used_by": "Jane Smith",
  "department": "Ortho / GIS",
  "workstation_no": "WS-ORTHO-12",
  "location": "Office - 3rd Floor",
  "work_mode": "office",
  "assigned_date": "2026-10-15",
  "remarks": "Project reassignment",
  "reporting_month": "2026-10"
}
    ↓
Backend detects transfer (previous_custodian exists):
  1. Create ITHandoverRecord:
     - activity_type: "handover"
     - action_type: "transfer"
     - employee_name: "Jane Smith"
     - previous_custodian: "John Doe"
     - activity_date: "2026-10-15"
  2. Update Asset:
     - used_by: "Jane Smith"
     - department: "Ortho / GIS"
     - workstation_no: "WS-ORTHO-12"
  3. Create AssetHistory:
     - action: "Asset transferred"
     - change_type: "custody_transfer"
     - old_value: "John Doe"
     - new_value: "Jane Smith"
  4. Commit
    ↓
Frontend shows: "NT-LAP-0042 transferred from John Doe to Jane Smith"
```

#### Step 4: Asset Return
```
User clicks "Return / Remove"
    ↓
[POST /api/assets/42/vendor-return]
Request Body:
{
  "return_mode": "complete_return",
  "return_date": "2026-12-20",
  "vendor_name": "Rental / Vendor Return",
  "reason": "Employee resignation",
  "remarks": "Laptop returned in good condition",
  "reporting_month": "2026-12",
  "spare_location": "IT Store",
  "confirm_vendor_return": true
}
    ↓
Backend Processing:
  1. Create ITHandoverRecord:
     - activity_type: "return"
     - action_type: "return"
     - employee_name: previous used_by
     - return_date: "2026-12-20"
  2. Update Asset:
     - status: "returned"
     - used_by: null
     - location: "IT Store"
  3. Create AssetHistory:
     - action: "Asset returned to IT Store"
     - change_type: "vendor_return"
  4. Decrement total asset count in dashboard
  5. Commit
    ↓
Frontend shows: "NT-LAP-0042 returned. Total IT Assets decreased by 1."
```

---

### Example 2: Drone Asset Operations (Import → Dispatch → Assignment → Return)

#### Step 1: Bulk Import from Excel
```
User uploads "Hardware-Inventory Sheets.xlsx"
    ↓
[POST /api/drone/import/preview]
File: Excel workbook with multiple sheets
    ↓
Backend Processing (backend/app/modules/drone/import_service.py):
  1. Read all sheets from workbook
  2. For each sheet (Drones, Cameras, GNSS, etc.):
     - Parse headers
     - Map columns to normalized fields
     - Validate data types
     - Check serial number duplicates
  3. Create DroneImportBatch (preview mode):
     - status: "preview"
     - original_filename: "Hardware-Inventory..."
     - sheet_count: 7
  4. Create DroneImportRow for each asset:
     - Validation status (valid/warning/error)
     - Reconciliation suggestions
  5. Return preview without committing
    ↓
Response: Preview with warnings/errors
    ↓
User reviews and confirms
    ↓
[POST /api/drone/import/{batch_id}/commit]
    ↓
Backend commits:
  1. Create DroneSurveyAsset records
  2. Generate asset_tag (DRN-CAM-001, etc.)
  3. Create DroneAuditLog entries
  4. Update batch status to "committed"
  5. Commit transaction
```

#### Step 2: Dispatch to Project
```
User creates dispatch operation
    ↓
[POST /api/drone/operations/dispatch]
Request Body:
{
  "project_id": 15,
  "asset_ids": [101, 102, 103],
  "kit_ids": [5],
  "dispatch_date": "2026-09-15",
  "dispatched_to": "Survey Team Alpha",
  "purpose": "LiDAR Data Collection - Highway Project",
  "expected_return_date": "2026-10-15"
}
    ↓
Backend Processing:
  1. Validate project exists and is active
  2. Check assets are available
  3. Create DroneOperation:
     - operation_type: "dispatch"
     - status: "active"
  4. For each asset:
     - Update current_project_id
     - Update current_status to "dispatched"
     - Create DroneAssetMovement record
  5. Create DroneAuditLog
  6. Commit
    ↓
Assets now linked to project
```

#### Step 3: Assign Within Project
```
[POST /api/drone/operations/assign]
Request Body:
{
  "project_id": 15,
  "asset_ids": [101],
  "assigned_to": "John Doe - LiDAR Operator",
  "assignment_date": "2026-09-16",
  "purpose": "Daily field operations"
}
    ↓
Backend:
  1. Create DroneOperation (type="assignment")
  2. Update asset current_custodian
  3. Create movement records
  4. Log audit trail
```

#### Step 4: Return from Project
```
[POST /api/drone/operations/return]
Request Body:
{
  "project_id": 15,
  "asset_ids": [101, 102, 103],
  "kit_ids": [5],
  "return_date": "2026-10-16",
  "condition": "good",
  "remarks": "All equipment functional"
}
    ↓
Backend:
  1. Create DroneOperation (type="return")
  2. Update assets:
     - current_project_id: null
     - current_status: "available"
     - current_custodian: null
  3. Update project asset counts
  4. Create movements and audit logs
  5. Close dispatch operation (status="completed")
```

---

### Example 3: Employee Portal Ticket Flow (Create → Assignment → Resolution)

#### Step 1: Ticket Creation
```
Employee navigates to: /support
    ↓
[POST /api/tickets]
Request Body:
{
  "department": "it",
  "component": "hardware",
  "problem_code": "laptop_not_starting",
  "title": "Laptop won't boot",
  "description": "My laptop shows black screen...",
  "priority": "high",
  "asset_id": 42,
  "impact": {
    "blocks_critical_work": true,
    "affects_multiple_people": false,
    "has_workaround": false
  }
}
    ↓
Backend Processing (backend/app/modules/employee_portal/service.py):
  1. Calculate priority from impact:
     - blocks_critical_work + no_workaround = HIGH
     - SLA target: 4 hours
  2. Generate ticket_code (TKT-2026-001234)
  3. Create SupportTicket:
     - requester_id: current_user.id
     - branch_id: user_branch
     - status: "open"
     - sla_target_at: now + 4 hours
  4. Create TicketNotification for IT department
  5. Send email to IT team
  6. Commit
    ↓
Response: Ticket details + SLA countdown
```

#### Step 2: IT Assignment
```
IT team member reviews tickets
    ↓
[PATCH /api/tickets/{ticket_id}]
Request Body:
{
  "assigned_to_id": 25,
  "status": "in_progress"
}
    ↓
Backend:
  1. Update SupportTicket
  2. Create TicketMessage:
     - message_type: "status_change"
     - content: "Assigned to Tech Support"
  3. Create notification for requester
  4. Send email notification
  5. Record audit event
```

#### Step 3: Resolution
```
IT completes work
    ↓
[POST /api/tickets/{ticket_id}/messages]
Request Body:
{
  "content": "Replaced faulty RAM module. System tested OK.",
  "is_department_response": true,
  "attachments": [...]
}
    ↓
[PATCH /api/tickets/{ticket_id}]
Request Body:
{
  "status": "resolved",
  "resolution_notes": "Hardware issue fixed"
}
    ↓
Backend:
  1. Add message
  2. Update status
  3. Set resolved_at timestamp
  4. Calculate SLA compliance
  5. Notify requester
  6. Close ticket after 24h if no reopen
```

---

### Example 4: Finance Expense Claim Flow (Draft → Submit → Admin → Finance → Payment)

#### Step 1: Create Draft Claim
```
Employee creates expense claim
    ↓
[POST /api/finance/claims]
Request Body:
{
  "project_id": 10,
  "claim_type": "travel",
  "work_start_date": "2026-09-01",
  "work_end_date": "2026-09-05",
  "line_items": [
    {
      "category": "transportation",
      "description": "Taxi to survey site",
      "date": "2026-09-01",
      "amount": 2500.00,
      "quantity": 1
    },
    {
      "category": "food",
      "description": "Lunch during field work",
      "date": "2026-09-02",
      "amount": 350.00,
      "quantity": 1
    }
  ],
  "total_claimed": 2850.00,
  "remarks": "Survey project travel expenses"
}
    ↓
Backend:
  1. Validate project exists and is active
  2. Validate requester is assigned to project
  3. Generate claim_code (EXP-2026-Q3-001)
  4. Create ExpenseClaim:
     - status: "draft"
     - requester_id: user.id
     - total_amount: 2850.00
  5. Create ExpenseClaimLineItem records
  6. Commit
    ↓
Claim saved as draft (can edit)
```

#### Step 2: Submit for Approval
```
[POST /api/finance/claims/{claim_id}/submit]
    ↓
Backend Validation:
  ├── All line items have receipts?
  ├── Total matches sum of line items?
  ├── Within project dates?
  └── All required fields complete?
    ↓
If valid:
  1. Update status to "pending_admin_review"
  2. Set submitted_at timestamp
  3. Create notifications for Admin
  4. Send email to Admin team
  5. Commit
```

#### Step 3: Admin Verification
```
Admin reviews claim
    ↓
[POST /api/finance/claims/{claim_id}/admin-decision]
Request Body:
{
  "action": "approve",
  "approved_work_start_date": "2026-09-01",
  "approved_work_end_date": "2026-09-05",
  "settlement_due_date": "2026-09-30",
  "comments": "Verified with project records"
}
    ↓
Backend:
  1. Update ExpenseClaim:
     - status: "pending_finance_review"
     - admin_reviewed_at: now
     - admin_reviewed_by_id: admin.id
  2. Record audit event
  3. Notify Finance department
  4. Send email to Finance team
  5. Commit
```

#### Step 4: Finance Approval
```
Finance reviews claim
    ↓
[POST /api/finance/claims/{claim_id}/finance-decision]
Request Body:
{
  "action": "approve",
  "approved_amount": 2850.00,
  "settlement_due_date": "2026-09-30",
  "comments": "Approved for full amount"
}
    ↓
Backend:
  1. Update ExpenseClaim:
     - status: "approved"
     - finance_approved_at: now
     - approved_amount: 2850.00
  2. Notify requester (email)
  3. Create settlement record
  4. Commit
```

#### Step 5: Payment Recording
```
Finance records payment
    ↓
[POST /api/finance/claims/{claim_id}/mark-paid]
Request Body:
{
  "payment_reference": "TXN-20260930-001",
  "paid_amount": 2850.00,
  "payment_mode": "bank_transfer",
  "payment_date": "2026-09-30",
  "comments": "Payment processed via NEFT"
}
    ↓
Backend:
  1. Update ExpenseClaim:
     - status: "paid"
     - paid_at: now
  2. Create ExpenseSettlement record
  3. Notify requester (payment complete)
  4. Update project financials
  5. Commit
    ↓
Claim lifecycle complete
```

---

## 🔄 BACKGROUND JOBS & SCHEDULED TASKS

### 1. Monthly Snapshot Service
```python
# backend/app/services/monthly_snapshot_service.py

Purpose: Create historical snapshots of all assets

Schedule: Automatic on month boundary

Flow:
1. Detect month change (2026-09-30 → 2026-10-01)
2. Query all Asset records
3. Create MonthlySnapshotRun:
   - month_start: 2026-09-01
   - status: "finalized"
   - opening_count: previous month's closing
   - closing_count: total assets now
4. For each asset:
   - Serialize to JSON
   - Create MonthlyAssetSnapshot record
5. Mark run as completed
6. Historical data now queryable by month
```

### 2. SLA Monitoring
```python
# Ticket SLA tracking

Every 5 minutes:
1. Query all open/in_progress tickets
2. For each ticket:
   - Calculate time remaining until SLA breach
   - If < 1 hour: Send warning notification
   - If breached: Mark as SLA_BREACHED
   - Update dashboard metrics
```

### 3. Backup Jobs
```python
# backend/app/modules/backup/service.py

Daily at 2:00 AM:
1. Create BackupRun record
2. Export all modules to Excel:
   - Assets sheet
   - IT Activity sheet
   - Drone Assets sheet
   - Finance Claims sheet
   - etc.
3. If backup_database_enabled:
   - Run pg_dump
   - Compress SQL dump
4. If backup_minio_enabled:
   - Export MinIO buckets
5. Save files to backup_root
6. Update BackupRun (status="completed")
7. Cleanup old backups (keep last 30 days)
```

---

## 📡 FRONTEND-BACKEND INTEGRATION PATTERNS

### Pattern 1: Simple CRUD
```typescript
// frontend/src/pages/AssetsPage.tsx

// List assets
const assets = await apiFetch<Asset[]>('/assets?limit=1000')

// Get single asset
const asset = await apiFetch<Asset>(`/assets/${id}`)

// Create asset
const created = await apiFetch<Asset>('/assets', {
  method: 'POST',
  body: JSON.stringify(formData)
})

// Update asset
const updated = await apiFetch<Asset>(`/assets/${id}`, {
  method: 'PATCH',
  body: JSON.stringify(changes)
})

// Delete asset
await apiFetch<void>(`/assets/${id}`, { method: 'DELETE' })
```

### Pattern 2: File Upload
```typescript
// Excel import
const formData = new FormData()
formData.append('file', selectedFile)

const response = await fetch('/api/assets/import.xlsx', {
  method: 'POST',
  headers: { Authorization: `Bearer ${token}` },
  body: formData  // Don't set Content-Type manually
})

const result = await response.json()
// { created: 50, updated: 10, errors: [] }
```

### Pattern 3: File Download
```typescript
// Excel export
async function downloadAssets() {
  const response = await fetch('/api/assets/export.xlsx', {
    headers: { Authorization: `Bearer ${token}` }
  })
  
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  
  const a = document.createElement('a')
  a.href = url
  a.download = 'Assets.xlsx'
  a.click()
  
  URL.revokeObjectURL(url)
}
```

### Pattern 4: Real-time Updates
```typescript
// Polling for ticket updates
useEffect(() => {
  const interval = setInterval(async () => {
    const tickets = await apiFetch<Ticket[]>('/tickets')
    setTickets(tickets)
  }, 30000)  // Poll every 30 seconds
  
  return () => clearInterval(interval)
}, [])
```

### Pattern 5: Optimistic Updates
```typescript
// Update asset optimistically
async function updateAsset(id: number, changes: Partial<Asset>) {
  // Update UI immediately
  setAssets(prev => 
    prev.map(a => a.id === id ? { ...a, ...changes } : a)
  )
  
  try {
    // Send to backend
    const updated = await apiFetch<Asset>(`/assets/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(changes)
    })
    
    // Sync with server response
    setAssets(prev => 
      prev.map(a => a.id === id ? updated : a)
    )
  } catch (error) {
    // Revert on error
    await loadAssets()
    showError('Update failed')
  }
}
```

---

## 🗄️ DATABASE SCHEMA OVERVIEW

### Core Tables

#### 1. users
```sql
CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  email VARCHAR UNIQUE NOT NULL,
  password_hash VARCHAR NOT NULL,
  full_name VARCHAR,
  role VARCHAR NOT NULL,  -- admin, it, drone, finance, etc.
  branch VARCHAR,
  employee_id VARCHAR,
  department VARCHAR,
  designation VARCHAR,
  phone_number VARCHAR,
  is_active BOOLEAN DEFAULT true,
  email_verified BOOLEAN DEFAULT false,
  account_status VARCHAR DEFAULT 'active',
  mfa_required BOOLEAN DEFAULT false,
  must_change_password BOOLEAN DEFAULT false,
  token_version INTEGER DEFAULT 0,
  last_login_at TIMESTAMP,
  last_logout_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

#### 2. assets (IT Asset Master)
```sql
CREATE TABLE assets (
  id SERIAL PRIMARY KEY,
  asset_code VARCHAR UNIQUE NOT NULL,  -- NT-LAP-0042
  source_sheet VARCHAR,
  source_row INTEGER,
  
  -- Identification
  cpu_asset_tag VARCHAR,
  serial_number VARCHAR,
  system_name VARCHAR,
  device_type VARCHAR,  -- Computer, Laptop, Printer, etc.
  
  -- Specifications
  brand VARCHAR,
  model VARCHAR,
  processor VARCHAR,
  memory_gb VARCHAR,
  ssd VARCHAR,
  hdd VARCHAR,
  graphics_card VARCHAR,
  operating_system VARCHAR,
  
  -- Assignment
  used_by VARCHAR,
  department VARCHAR,
  workstation_no VARCHAR,
  location VARCHAR,
  work_mode VARCHAR,  -- office, wfh, field
  status VARCHAR,  -- available, assigned, repair, etc.
  
  -- Peripherals
  monitor_asset_tags VARCHAR,
  mouse_asset_tag VARCHAR,
  keyboard_asset_tag VARCHAR,
  
  -- Network
  ip_address VARCHAR,
  mac_address VARCHAR,
  network_type VARCHAR,
  connection_type VARCHAR,
  
  -- External HDD specific
  capacity VARCHAR,
  ownership VARCHAR,  -- NakshaTech, Client
  client_name VARCHAR,
  project_id VARCHAR,
  current_holder VARCHAR,
  
  -- Financial
  price DECIMAL(12, 2),
  
  -- Metadata
  antivirus VARCHAR,
  performed_by VARCHAR,
  approved_by VARCHAR,
  remarks TEXT,
  asset_date DATE,
  original_asset_date DATE,
  
  -- Tracking
  last_change_at TIMESTAMP,
  last_changed_by VARCHAR,
  last_changed_by_role VARCHAR,
  last_change_type VARCHAR,
  last_change_reason VARCHAR,
  last_field_count INTEGER,
  
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

#### 3. asset_history (Audit Trail)
```sql
CREATE TABLE asset_history (
  id SERIAL PRIMARY KEY,
  asset_id INTEGER REFERENCES assets(id),
  batch_code VARCHAR,
  reporting_month VARCHAR,  -- YYYY-MM
  
  action VARCHAR NOT NULL,  -- "Asset assigned", "Component replaced"
  change_type VARCHAR,  -- assignment, transfer, repair, etc.
  
  -- Old and new values (JSON)
  old_value TEXT,
  new_value TEXT,
  field_count INTEGER,
  
  reason VARCHAR,
  remarks TEXT,
  
  changed_by VARCHAR,
  changed_by_name VARCHAR,
  changed_by_role VARCHAR,
  
  created_at TIMESTAMP DEFAULT NOW()
);
```

#### 4. it_handover_records (IT Activity)
```sql
CREATE TABLE it_handover_records (
  id SERIAL PRIMARY KEY,
  activity_code VARCHAR UNIQUE NOT NULL,
  reporting_month VARCHAR,
  
  activity_type VARCHAR,  -- handover, return
  action_type VARCHAR,  -- new_assign, transfer, return
  device_category VARCHAR,  -- laptop, desktop
  
  activity_date DATE,
  activity_time TIME,
  
  employee_name VARCHAR,
  previous_custodian VARCHAR,
  dc_number VARCHAR,
  
  asset_id INTEGER REFERENCES assets(id),
  internal_asset_no VARCHAR,
  serial_number VARCHAR,
  department VARCHAR,
  
  performed_by VARCHAR,
  remarks TEXT,
  
  created_at TIMESTAMP DEFAULT NOW()
);
```

#### 5. it_purchase_requests (Purchase Approval Workflow)
```sql
CREATE TABLE it_purchase_requests (
  id SERIAL PRIMARY KEY,
  request_code VARCHAR UNIQUE NOT NULL,
  branch VARCHAR,
  
  status VARCHAR NOT NULL,  -- pending_approval, approved, rejected
  
  -- Request details
  item_name VARCHAR NOT NULL,
  quantity INTEGER NOT NULL,
  estimated_unit_price DECIMAL(12, 2),
  estimated_total_amount DECIMAL(12, 2),
  priority VARCHAR,  -- low, medium, high, urgent
  justification TEXT NOT NULL,
  specifications TEXT,
  preferred_vendor VARCHAR,
  
  -- Requester
  requested_by_email VARCHAR NOT NULL,
  requested_by_name VARCHAR,
  requested_at TIMESTAMP DEFAULT NOW(),
  
  -- Management decision
  approved_amount DECIMAL(12, 2),
  management_remarks TEXT,
  decided_by_email VARCHAR,
  decided_by_name VARCHAR,
  decided_at TIMESTAMP,
  
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

#### 6. drone_survey_assets
```sql
CREATE TABLE drone_survey_assets (
  id SERIAL PRIMARY KEY,
  asset_tag VARCHAR UNIQUE NOT NULL,  -- DRN-CAM-001
  category VARCHAR,  -- drone, camera, gnss, battery
  
  -- Identification
  imported_equipment_id VARCHAR,
  asset_name VARCHAR NOT NULL,
  serial_number VARCHAR,
  model_number VARCHAR,
  manufacturer VARCHAR,
  
  -- Status & Location
  current_status VARCHAR,  -- available, dispatched, in_maintenance
  current_project_id INTEGER REFERENCES drone_projects(id),
  current_custodian VARCHAR,
  
  -- Tracking
  tracking_type VARCHAR,  -- serialized_asset, consumable
  is_serialized BOOLEAN DEFAULT true,
  raw_serial_number VARCHAR,
  
  -- Calibration (for precision equipment)
  last_calibration_date DATE,
  next_calibration_date DATE,
  calibration_status VARCHAR,
  
  -- Import metadata
  reconciliation_status VARCHAR,
  source_workbook VARCHAR,
  source_sheet VARCHAR,
  
  archived_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

#### 7. drone_operations (Dispatch/Return)
```sql
CREATE TABLE drone_operations (
  id SERIAL PRIMARY KEY,
  operation_code VARCHAR UNIQUE NOT NULL,
  
  operation_type VARCHAR NOT NULL,  -- dispatch, return, transfer, assignment
  status VARCHAR DEFAULT 'active',  -- active, completed, cancelled
  
  project_id INTEGER REFERENCES drone_projects(id),
  from_project_id INTEGER,
  to_project_id INTEGER,
  
  operation_date DATE NOT NULL,
  dispatched_to VARCHAR,
  assigned_to VARCHAR,
  purpose TEXT,
  expected_return_date DATE,
  
  performed_by VARCHAR,
  remarks TEXT,
  
  created_at TIMESTAMP DEFAULT NOW()
);
```

#### 8. support_tickets (Employee Portal)
```sql
CREATE TABLE support_tickets (
  id SERIAL PRIMARY KEY,
  ticket_code VARCHAR UNIQUE NOT NULL,  -- TKT-2026-001234
  
  requester_id INTEGER REFERENCES users(id),
  branch_id INTEGER REFERENCES branches(id),
  
  department VARCHAR NOT NULL,  -- it, hr, admin
  category VARCHAR,
  
  title VARCHAR NOT NULL,
  description TEXT NOT NULL,
  
  priority VARCHAR NOT NULL,  -- low, medium, high, urgent
  priority_reason TEXT,
  sla_target_minutes INTEGER,
  sla_target_at TIMESTAMP,
  sla_breached BOOLEAN DEFAULT false,
  
  -- IT-specific
  component VARCHAR,  -- hardware, software, network
  problem_code VARCHAR,
  problem_label VARCHAR,
  component_asset_tag VARCHAR,
  impact_assessment JSONB,
  
  asset_id INTEGER REFERENCES assets(id),
  asset_number VARCHAR,
  asset_snapshot JSONB,
  
  status VARCHAR DEFAULT 'open',  -- open, in_progress, resolved, closed
  assigned_to_id INTEGER REFERENCES users(id),
  
  resolved_at TIMESTAMP,
  closed_at TIMESTAMP,
  resolution_notes TEXT,
  
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

#### 9. expense_claims (Finance)
```sql
CREATE TABLE expense_claims (
  id SERIAL PRIMARY KEY,
  claim_code VARCHAR UNIQUE NOT NULL,  -- EXP-2026-Q3-001
  
  requester_id INTEGER REFERENCES users(id),
  project_id INTEGER REFERENCES finance_projects(id),
  
  claim_type VARCHAR NOT NULL,  -- travel, materials, accommodation
  status VARCHAR NOT NULL,  -- draft, pending_admin_review, approved, paid
  
  -- Work period
  work_start_date DATE,
  work_end_date DATE,
  approved_work_start_date DATE,
  approved_work_end_date DATE,
  
  -- Amounts
  total_amount DECIMAL(12, 2),
  approved_amount DECIMAL(12, 2),
  paid_amount DECIMAL(12, 2),
  
  -- Approval workflow
  submitted_at TIMESTAMP,
  admin_reviewed_at TIMESTAMP,
  admin_reviewed_by_id INTEGER,
  finance_approved_at TIMESTAMP,
  finance_approved_by_id INTEGER,
  paid_at TIMESTAMP,
  
  settlement_due_date DATE,
  remarks TEXT,
  
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

#### 10. expense_claim_line_items
```sql
CREATE TABLE expense_claim_line_items (
  id SERIAL PRIMARY KEY,
  claim_id INTEGER REFERENCES expense_claims(id),
  
  category VARCHAR NOT NULL,  -- transportation, food, accommodation
  description VARCHAR NOT NULL,
  date DATE NOT NULL,
  amount DECIMAL(12, 2) NOT NULL,
  quantity INTEGER DEFAULT 1,
  
  receipt_attached BOOLEAN DEFAULT false,
  remarks VARCHAR,
  
  created_at TIMESTAMP DEFAULT NOW()
);
```

### Relationship Diagram (Simplified)

```
users
  ├─→ assets (via used_by email)
  ├─→ support_tickets (requester_id)
  ├─→ expense_claims (requester_id)
  └─→ ortho_project_members (user_id)

assets
  ├─→ asset_history (asset_id)
  ├─→ it_handover_records (asset_id)
  ├─→ work_records (asset_id)
  └─→ support_tickets (asset_id)

drone_survey_assets
  ├─→ drone_projects (current_project_id)
  ├─→ drone_operations (via asset_movements)
  └─→ drone_audit_log (entity_id)

support_tickets
  ├─→ ticket_messages (ticket_id)
  ├─→ ticket_attachments (ticket_id)
  └─→ ticket_notifications (ticket_id)

expense_claims
  ├─→ expense_claim_line_items (claim_id)
  ├─→ expense_settlements (claim_id)
  └─→ expense_claim_attachments (claim_id)

finance_projects
  ├─→ expense_claims (project_id)
  ├─→ ortho_project_profile (project_id)
  └─→ finance_clients (client_id)
```

---

## 🔍 KEY BUSINESS LOGIC SERVICES

### 1. Asset Lifecycle Service
**Location:** `backend/app/services/asset_lifecycle_service.py`

**Responsibilities:**
- Device type canonicalization ("laptop" → "Laptop")
- Asset code generation (NT-LAP-0042)
- Assignment validation (can only assign available assets)
- Transfer logic (detect previous custodian)
- Component replacement tracking
- Disposal/retirement workflow

**Key Functions:**
```python
def create_asset(db, payload, user):
    # Generate asset_code
    # Validate device_type
    # Create Asset record
    # Create initial history entry

def assign_asset(db, asset, payload, user):
    # Validate assignment
    # Detect transfer vs new assignment
    # Create handover record
    # Update asset status
    # Log history

def vendor_return(db, asset, payload, user):
    # Create return record
    # Update status to "returned"
    # Clear assignment
    # Decrement counts
    # Log history
```

### 2. Approval Workflow Service
**Location:** `backend/app/services/approval_workflow_service.py`

**Responsibilities:**
- Purchase request approval flow
- Email approval tokens (secure links)
- Multi-level approval (Admin → Finance → Management)
- Status transitions (pending → approved → rejected)
- Notification orchestration

**Key Functions:**
```python
def create_purchase_request(db, payload, requester):
    # Generate request_code
    # Validate justification
    # Set initial status
    # Create approval channel
    # Send email to approver

def approve_request(db, request_id, approver, remarks):
    # Validate approver role
    # Check current status
    # Update status
    # Notify next approver OR requester
    # Log decision

def send_back_request(db, request_id, approver, reason):
    # Revert to pending status
    # Add rejection reason
    # Notify requester
    # Allow resubmission
```

### 3. Monthly Snapshot Service
**Location:** `backend/app/services/monthly_snapshot_service.py`

**Responsibilities:**
- Create monthly snapshots of all assets
- Historical data preservation
- Month-over-month reporting
- Opening/closing balance tracking

**Key Functions:**
```python
def finalize_month_snapshot(db, month_start, actor):
    # Query all current assets
    # Get previous month's closing
    # Create snapshot run
    # Serialize each asset to JSON
    # Store in monthly_asset_snapshots
    # Mark as finalized

def get_assets_for_month(db, month_start):
    # If current month: return live assets
    # If has snapshot: return snapshot data
    # If historical Excel: parse template
    # Else: return empty
```

### 4. Excel Import/Export Service
**Location:** `backend/app/services/excel_import_service.py`

**Responsibilities:**
- Parse Excel workbooks
- Validate data before import
- Handle duplicates and conflicts
- Generate import reports

**Key Functions:**
```python
def import_nakshatech_workbook(db, excel_bytes):
    # Load workbook
    # Find latest month sheet
    # For each row:
    #   - Validate device_type
    #   - Check serial duplicates
    #   - Create or update Asset
    # Return { created, updated, skipped }

def import_printer_assets(db, excel_bytes):
    # Validate required columns
    # Check asset_id conflicts
    # Create Printer assets
    # Return validation report
```

### 5. Ticket SLA Service
**Location:** `backend/app/services/ticket_sla_service.py`

**Responsibilities:**
- Calculate SLA targets based on priority
- Monitor SLA compliance
- Send breach warnings
- Generate SLA reports

**Key Logic:**
```python
SLA_TARGETS = {
    "urgent": 2 * 60,    # 2 hours
    "high": 4 * 60,      # 4 hours
    "medium": 24 * 60,   # 1 day
    "low": 72 * 60       # 3 days
}

def calculate_sla_target(priority, created_at):
    target_minutes = SLA_TARGETS[priority]
    return created_at + timedelta(minutes=target_minutes)

def check_sla_breaches(db):
    # Query open/in_progress tickets
    # For each: check if now > sla_target_at
    # Mark breached and notify
```

---

## 📧 EMAIL & NOTIFICATION SYSTEM

### Email Configuration
```python
# backend/app/core/config.py

settings.email_delivery_mode = "smtp"  # or "console", "log"
settings.smtp_host = "smtp.gmail.com"
settings.smtp_port = 587
settings.smtp_user = "noreply@nakshatech.com"
settings.smtp_password = "***"
settings.smtp_from_email = "Asset Management <noreply@nakshatech.com>"
```

### Email Templates

#### 1. Purchase Request Approval Email
```python
Subject: Purchase Request Approval Required - {request_code}

Dear {approver_name},

A new IT purchase request requires your approval:

Request Code: {request_code}
Item: {item_name}
Quantity: {quantity}
Estimated Cost: ₹{estimated_total_amount}
Priority: {priority}
Requested By: {requester_name}

Justification:
{justification}

[Approve] [Send Back] [Reject]

Or use this secure link:
{approval_url}

---
NakshaTech Asset Management System
```

#### 2. Ticket Created Notification
```python
Subject: New Support Ticket - {ticket_code}

Dear IT Team,

A new support ticket has been created:

Ticket Code: {ticket_code}
Requester: {requester_name}
Department: {department}
Priority: {priority}
SLA Target: {sla_target_time}

Title: {title}
Description: {description}

Asset: {asset_tag}

[View Ticket] [Assign to Me]

---
NakshaTech Employee Portal
```

#### 3. Expense Claim Status Update
```python
Subject: Expense Claim {status} - {claim_code}

Dear {requester_name},

Your expense claim has been {status}:

Claim Code: {claim_code}
Project: {project_name}
Submitted Amount: ₹{total_amount}
Approved Amount: ₹{approved_amount}
Status: {status}

{status == "approved" ? "Payment will be processed by {settlement_due_date}" : ""}
{status == "sent_back" ? f"Reason: {rejection_reason}" : ""}

[View Claim Details]

---
NakshaTech Finance Department
```

### Notification Types

```python
# Database notifications (bell icon in UI)
notification_types = [
    "ticket_created",
    "ticket_assigned",
    "ticket_updated",
    "ticket_resolved",
    "claim_submitted",
    "claim_approved",
    "claim_rejected",
    "purchase_request_pending",
    "purchase_approved",
    "asset_assigned_to_you",
    "sla_breach_warning",
]
```

---

## 🔒 SECURITY BEST PRACTICES

### 1. Password Security
```python
# Bcrypt hashing with 12 rounds
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)
```

### 2. JWT Token Security
```python
# Token payload (minimal PII)
{
  "sub": user.email,
  "uid": user.id,
  "role": user.role,
  "branch_id": selected_branch_id,
  "token_version": user.token_version,
  "exp": datetime.utcnow() + timedelta(hours=8),
  "iat": datetime.utcnow()
}

# Token invalidation
def invalidate_user_tokens(db, user):
    user.token_version += 1
    db.commit()
    # All old tokens now invalid (version mismatch)
```

### 3. SQL Injection Prevention
```python
# Always use ORM or parameterized queries
# BAD:
db.execute(f"SELECT * FROM users WHERE email = '{email}'")

# GOOD:
db.query(User).filter(User.email == email).first()

# GOOD (raw SQL):
db.execute(
    text("SELECT * FROM users WHERE email = :email"),
    {"email": email}
)
```

### 4. CORS Configuration
```python
# backend/app/main.py

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Dev
        "https://assets.nakshatech.com"  # Prod
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 5. File Upload Security
```python
# Validate file types
ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".pdf", ".jpg", ".png"}

def validate_upload(file: UploadFile):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, "File type not allowed")
    
    # Check file size (10 MB max)
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if size > 10 * 1024 * 1024:
        raise HTTPException(413, "File too large")
```

### 6. Rate Limiting
```python
from slowapi import Limiter

limiter = Limiter(key_func=get_remote_address)

@app.post("/auth/login")
@limiter.limit("5/minute")
async def login(request: Request, ...):
    # Max 5 login attempts per minute per IP
```

---

## 📊 REPORTING & ANALYTICS

### 1. IT Dashboard Metrics
```python
# backend/app/api/router.py

@router.get("/dashboard")
def dashboard(user: User = Depends(get_current_user)):
    return {
        "total_assets": count_all_assets(),
        "by_device_type": {
            "Computer": count_by_type("Computer"),
            "Laptop": count_by_type("Laptop"),
            "Smartphone": count_by_type("Smartphone"),
            "Printer": count_by_type("Printer"),
        },
        "by_status": {
            "available": count_by_status("available"),
            "assigned": count_by_status("assigned"),
            "repair": count_by_status("repair"),
            "replacement_pending": count_by_status("replacement_pending"),
        },
        "quality_alerts": {
            "replacement_pending": list_replacement_pending(),
            "repair": list_under_repair(),
            "missing_mac": list_missing_mac(),
            "duplicate_ip": list_duplicate_ips(),
            "unassigned": list_unassigned(),
        },
        "recent_activity": {
            "handovers_this_month": count_handovers_this_month(),
            "returns_this_month": count_returns_this_month(),
            "purchases_this_month": count_purchases_this_month(),
        }
    }
```

### 2. Drone Operations Dashboard
```python
@router.get("/drone/dashboard")
def drone_dashboard(user: User = Depends(require_roles("drone", "admin"))):
    return {
        "total_assets": count_drone_assets(),
        "by_category": {
            "Drones": count_by_category("drone"),
            "Cameras": count_by_category("camera"),
            "GNSS": count_by_category("gnss"),
            "Batteries": count_by_category("battery"),
        },
        "by_status": {
            "available": count_by_status("available"),
            "dispatched": count_by_status("dispatched"),
            "in_maintenance": count_by_status("in_maintenance"),
        },
        "active_projects": list_active_projects(),
        "calibration_due": list_calibration_due(),
    }
```

### 3. Finance Reporting
```python
@router.get("/finance/reports")
def finance_reports(
    period: str = "month",
    year: int = 2026,
    month: int | None = None,
    project_id: int | None = None,
    user: User = Depends(require_roles("finance", "management", "admin"))
):
    claims = query_claims(period, year, month, project_id)
    
    return {
        "summary": {
            "total_claims": len(claims),
            "total_claimed": sum(c.total_amount for c in claims),
            "total_approved": sum(c.approved_amount for c in claims),
            "total_paid": sum(c.paid_amount for c in claims),
        },
        "by_status": {
            "pending": count_by_status("pending_admin_review"),
            "approved": count_by_status("approved"),
            "paid": count_by_status("paid"),
            "rejected": count_by_status("rejected"),
        },
        "by_type": {
            "travel": sum_by_type("travel"),
            "materials": sum_by_type("materials"),
            "accommodation": sum_by_type("accommodation"),
        },
        "by_project": [
            {
                "project_name": project.name,
                "total_claims": count_claims_for_project(project.id),
                "total_amount": sum_claims_for_project(project.id),
            }
            for project in active_projects()
        ],
        "claims": [serialize_claim(c) for c in claims],
    }
```

---

## 🚀 DEPLOYMENT & INFRASTRUCTURE

### Docker Compose Setup
```yaml
# docker-compose.yml

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: nakshatech_crm
      POSTGRES_USER: nakshatech
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  minio:
    image: minio/minio:latest
    environment:
      MINIO_ROOT_USER: admin
      MINIO_ROOT_PASSWORD: ${MINIO_PASSWORD}
    command: server /data --console-address ":9001"
    volumes:
      - minio_data:/data
    ports:
      - "9000:9000"
      - "9001:9001"

  backend:
    build: ./backend
    environment:
      DATABASE_URL: postgresql://nakshatech:${DB_PASSWORD}@postgres:5432/nakshatech_crm
      MINIO_ENDPOINT: minio:9000
      MINIO_ACCESS_KEY: admin
      MINIO_SECRET_KEY: ${MINIO_PASSWORD}
      SECRET_KEY: ${JWT_SECRET}
    depends_on:
      - postgres
      - minio
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app
      - backup_storage:/backups

  frontend:
    build: ./frontend
    environment:
      VITE_API_URL: http://localhost:8000/api
    ports:
      - "5173:5173"
    volumes:
      - ./frontend:/app

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - backend
      - frontend

volumes:
  postgres_data:
  minio_data:
  backup_storage:
```

### Environment Variables (.env)
```bash
# Database
DB_PASSWORD=secure_postgres_password
DATABASE_URL=postgresql://nakshatech:${DB_PASSWORD}@localhost:5432/nakshatech_crm

# MinIO
MINIO_PASSWORD=secure_minio_password
MINIO_ROOT_USER=admin
MINIO_ROOT_PASSWORD=${MINIO_PASSWORD}

# JWT
JWT_SECRET=your_secret_key_change_in_production
JWT_ALGORITHM=HS256
JWT_EXPIRY_HOURS=8

# SMTP Email
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=noreply@nakshatech.com
SMTP_PASSWORD=app_specific_password
SMTP_FROM_EMAIL=Asset Management <noreply@nakshatech.com>

# Application
EMPLOYEE_PORTAL_ENABLED=true
ALLOWED_EMAIL_DOMAINS=nakshatech.com,naksha.tech
BACKUP_ROOT=/backups
BACKUP_DATABASE_ENABLED=true
BACKUP_MINIO_ENABLED=true
```

---

## 🧪 TESTING STRATEGY

### Backend Tests
```python
# tests/test_assets.py

def test_create_asset(client, admin_token):
    response = client.post(
        "/api/assets",
        json={
            "cpu_asset_tag": "TEST-LAP-001",
            "device_type": "Laptop",
            "brand": "Dell",
            "status": "available"
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["cpu_asset_tag"] == "TEST-LAP-001"

def test_assign_asset(client, admin_token, test_asset):
    response = client.post(
        f"/api/assets/{test_asset.id}/assign",
        json={
            "used_by": "Test User",
            "department": "IT",
            "workstation_no": "WS-TEST-01",
            "work_mode": "office"
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["used_by"] == "Test User"
    assert data["status"] == "assigned"
```

### Frontend Tests
```typescript
// tests/AssetsPage.test.tsx

describe('AssetsPage', () => {
  it('loads and displays assets', async () => {
    render(<AssetsPage />)
    
    await waitFor(() => {
      expect(screen.getByText('NT-LAP-0042')).toBeInTheDocument()
    })
  })
  
  it('allows admin to assign asset', async () => {
    const user = userEvent.setup()
    render(<AssetsPage />)
    
    await user.click(screen.getByText('NT-LAP-0042'))
    await user.click(screen.getByText('Assign / Transfer'))
    
    await user.type(screen.getByLabelText('Assign To'), 'John Doe')
    await user.click(screen.getByText('Confirm Assignment'))
    
    await waitFor(() => {
      expect(screen.getByText(/assigned to John Doe/i)).toBeInTheDocument()
    })
  })
})
```

---

## 📈 PERFORMANCE OPTIMIZATION

### 1. Database Indexing
```sql
-- Critical indexes for performance

CREATE INDEX idx_assets_cpu_tag ON assets(cpu_asset_tag);
CREATE INDEX idx_assets_serial ON assets(serial_number);
CREATE INDEX idx_assets_used_by ON assets(used_by);
CREATE INDEX idx_assets_status ON assets(status);
CREATE INDEX idx_assets_device_type ON assets(device_type);

CREATE INDEX idx_asset_history_asset ON asset_history(asset_id);
CREATE INDEX idx_asset_history_month ON asset_history(reporting_month);

CREATE INDEX idx_tickets_requester ON support_tickets(requester_id);
CREATE INDEX idx_tickets_status ON support_tickets(status);
CREATE INDEX idx_tickets_sla ON support_tickets(sla_target_at) WHERE status IN ('open', 'in_progress');

CREATE INDEX idx_claims_requester ON expense_claims(requester_id);
CREATE INDEX idx_claims_project ON expense_claims(project_id);
CREATE INDEX idx_claims_status ON expense_claims(status);
```

### 2. Query Optimization
```python
# Use eager loading to prevent N+1 queries

# BAD (N+1 query problem):
assets = db.query(Asset).all()
for asset in assets:
    print(asset.history)  # Triggers separate query for each asset

# GOOD (eager loading):
assets = db.query(Asset).options(
    joinedload(Asset.history),
    joinedload(Asset.work_records)
).all()
```

### 3. Caching Strategy
```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_department_list(db):
    """Cache department list (rarely changes)"""
    return db.query(distinct(Asset.department)).all()

# Cache historical months (never changes)
@lru_cache(maxsize=48)
def template_months():
    # Parse historical Excel template
    return months
```

### 4. Pagination
```python
@router.get("/assets")
def list_assets(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db)
):
    total = db.query(func.count(Asset.id)).scalar()
    assets = db.query(Asset).offset(offset).limit(limit).all()
    
    return {
        "items": assets,
        "total": total,
        "offset": offset,
        "limit": limit
    }
```

---

## 🎯 SUMMARY

This is a **production-grade Enterprise Resource Planning (ERP)** system that demonstrates:

1. **Full-Stack Architecture**: React + FastAPI + PostgreSQL
2. **Role-Based Access Control**: 10+ user roles with hierarchical permissions
3. **Comprehensive Asset Management**: IT assets, drones, and survey equipment
4. **Approval Workflows**: Multi-level approval for purchases and expenses
5. **Employee Self-Service**: Support tickets, expense claims, project tracking
6. **Audit Trail**: Complete history for all operations
7. **Reporting**: Dashboard metrics, Excel exports, monthly snapshots
8. **Email Notifications**: SMTP integration for workflow alerts
9. **File Management**: MinIO for attachments and backups
10. **Security**: JWT auth, password hashing, RBAC, SQL injection protection
11. **Backup & Recovery**: Automated daily backups with disaster recovery

**Key Operational Flows:**
- **IT Asset Lifecycle**: Create → Assign → Transfer → Component Changes → Return → Retire
- **Drone Operations**: Import → Dispatch → Assign → Track → Return
- **Support Tickets**: Create → Auto-assign → Resolve → SLA tracking
- **Expense Claims**: Draft → Submit → Admin Review → Finance Approval → Payment
- **Purchase Requests**: Request → Management Approval → Email approval workflow

**Technical Highlights:**
- **Modular Architecture**: Each feature is a self-contained module
- **Service Layer**: Business logic separated from API routes
- **Database Relationships**: Normalized schema with proper foreign keys
- **Historical Tracking**: Monthly snapshots + audit logs
- **Excel Integration**: Import/export for bulk operations
- **Type Safety**: TypeScript frontend + Pydantic backend
- **Docker Deployment**: Multi-container orchestration
- **Scalable Design**: Ready for horizontal scaling

---

*This document represents a complete understanding of the NakshaTech Asset Management CRM system. Every component, flow, and integration has been studied and documented.*
