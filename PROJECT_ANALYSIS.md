# NakshaTech CRM - Complete Project Analysis

**Analysis Date**: September 10, 2026  
**Project**: Corporate Resource Management & Operations Platform  
**Company**: NakshaTech (India-based Surveying/Mapping Company)

---

## EXECUTIVE SUMMARY

This is NOT just an "asset management system" - it's a **comprehensive enterprise operations platform** managing:
- IT Hardware Assets
- Drone Survey Operations
- Business Development Pipeline
- Ortho/LiDAR Project Execution
- Financial Claims & Client Management
- Employee Self-Service Portal
- Travel/KM Claims with GPS Verification

---

## ROLE-BASED ACCESS & FUNCTIONALITY

### 1. **SOFTWARE_TEAM** (Super Admin)
- Full system access equivalent to admin
- Database backups & restores
- System configuration
- User management
- All module oversight

### 2. **ADMIN** (System Administrator)
- User account management
- IT asset lifecycle management
- Work record approvals
- Replacement approvals
- Expense claim verification (first level)
- Database backups
- Data quality checks
- **READ-ONLY** access to Management features

### 3. **MANAGEMENT** (Executive Leadership)
- **READ-ONLY** oversight of ALL operations:
  - IT work records (view only, cannot modify)
  - Asset replacements (approval workflow)
  - Purchase requests (approval workflow)
  - Financial reports & dashboards
  - BD opportunities (view only)
  - Ortho project progress (view only)
- Corporate summary reports
- Cross-module analytics

### 4. **IT** (IT Department Staff)
- **PRIMARY CONTROLLER** of IT assets
- Asset CRUD operations (create, update, assign, transfer, return)
- Component replacements (RAM, SSD, HDD upgrades)
- Work record creation & management
- Repair workflows
- Purchase request creation
- Handover/Return documentation
- Monthly IT dashboard
- Excel import/export for assets

### 5. **DRONE** (Drone Operations Team)
- Drone fleet management (drones, batteries, controllers, sensors)
- Drone project creation & assignment
- Operation tracking (survey missions)
- Calibration schedules
- Equipment movement (issue/transfer/return)
- Drone work records
- Hardware inventory import

### 6. **FINANCE** (Finance Department)
- **CLIENT MASTER MANAGEMENT**:
  - Client CRUD (Client Code, Company details, GST, contacts)
  - Project Master (Project Code, lifecycle, dates, staffing)
  - Client/Project tracking & reporting
  - Excel import/export for Client Master
  
- **EXPENSE CLAIM WORKFLOW** (Second-level approval):
  - Admin-approved claims → Finance verification
  - Amount approval/adjustment
  - Work period validation
  - Payment recording (reference, mode, date)
  - Settlement tracking for advances
  
- **TRAVEL/KM CLAIM WORKFLOW** (Final payment):
  - HR-reviewed claims → Finance payment authorization
  - GPS route verification
  - Odometer vs GPS distance validation
  
- **PROJECT LIFECYCLE CONTROL**:
  - Activate/Deactivate projects
  - Status changes (Active, On Hold, Completed, Inactive)
  - Date adjustments (Start/End dates)
  - **BLOCKS employee claims** when project is not Active

### 7. **BD** (Business Development)
- **OPPORTUNITY PIPELINE MANAGEMENT**:
  - Create BD opportunities (client requirements, service type, priority)
  - Stage progression:
    - `opportunity` → Technical sample → Client review → Revision
    - `accepted` → Finance handoff → `project_linked`
    - Production → Delivery ready → `delivered` → `closed`
  - Client feedback tracking
  - Expected value, dates, service type
  - Finance Project linking (acceptance → official Project ID)
  
- **CLIENT RELATIONSHIP**:
  - Opportunity ownership (BD user creates, manages own opportunities)
  - Technical sample notes
  - Client review feedback
  - Acceptance recording
  - Finance handoff coordination

### 8. **ORTHO** (Ortho/LiDAR Production Team)
- **PROJECT ACTIVATION**:
  - Link Finance Project → Ortho Project Profile
  - Define scope (total area, hours, target value)
  - Assign Project Manager (from Finance Project Master)
  
- **TEAM CONFIGURATION**:
  - Assign 4 roles per project:
    - Team Leader (daily updates)
    - Production (execution)
    - QC (Quality Control)
    - QA (Quality Assurance)
  - Email assignment notifications
  
- **WORK PACKAGE MANAGEMENT**:
  - Break project into packages (area-based)
  - Assign package-level responsibilities
  - Track production stages:
    - `not_started` → Production (start/pause/resume/complete)
    - → QC review (approve/reject/rework)
    - → QA review (approve/reject/rework)
    - → `delivery_ready` → `delivered`
  
- **DAILY OPERATIONS**:
  - Record daily updates (achieved area, progress %, hours, blockers)
  - Production state transitions (start, pause, resume, complete)
  - Submit to QC → QC Review → Submit to QA → QA Review
  - Final delivery coordination
  
- **REWORK MANAGEMENT**:
  - QC/QA can reject packages → rework loop
  - Rework source tracking (QC vs QA)
  - Re-submission workflow

### 9. **HR** (Human Resources)
- **TRAVEL/KM CLAIM REVIEW** (Second-level verification):
  - Admin-reviewed claims → HR verification
  - GPS route validation:
    - Geofence entry detection (project site proximity)
    - Route distance vs odometer variance check
    - Photo timestamp validation
  - Work period verification
  - Forward to Finance for payment

### 10. **EMPLOYEE** (General Staff)
- **SELF-SERVICE PORTAL**:
  - Registration (email OTP verification)
  - 2FA setup (TOTP authenticator)
  - Branch selection
  
- **IT SUPPORT TICKETS**:
  - Create tickets (hardware issues, software requests)
  - Track ticket status
  - View responses from IT team
  
- **EXPENSE CLAIMS** (Draft → Submit → Approval chain):
  - **Advance Request**: Money needed before work/travel
  - **Reimbursement**: Submit bills after spending own money
  - **Additional Advance**: Top-up for existing advance
  - **Settlement**: Return unused advance + submit bills
  
- **TRAVEL/KM CLAIMS**:
  - Draft claim with project assignment
  - GPS tracking (route recording)
  - Photo attachments (timestamped)
  - Submit → Admin → HR → Finance → Payment
  
- **ORTHO PARTICIPATION** (if assigned):
  - View assigned work packages
  - Record daily updates (if Team Leader)
  - Execute production tasks (if Production role)
  - Perform QC/QA reviews (if assigned)

---

## BUSINESS WORKFLOWS BY DEPARTMENT

### **IT ASSET MANAGEMENT WORKFLOWS**

#### Asset Lifecycle
```
Purchase → Available (stock)
  ├→ Assign/Handover → Assigned/In-Use/WFH/Field
  │   ├→ Transfer (change custodian)
  │   ├→ Component Replacement (RAM/SSD upgrade)
  │   └→ Return → Available/Repair/Damaged
  ├→ Repair Request → Under Inspection → Repair Complete → Available
  ├→ Replacement Request (damage) → Pending Approval
  │   └→ Management Approves → Old: Replaced, New: Assigned
  └→ Retirement → Retired/Disposed
```

#### Component Replacement Tracking
- **Upgrade**: 8GB RAM → 16GB RAM (old component marked as spare)
- **Downgrade**: 512GB SSD → 256GB SSD (larger SSD returned to stock)
- **Replacement**: Failed HDD → New HDD (faulty HDD marked damaged)
- **History**: Every component change is audited with dates, reasons

#### Purchase Request Workflow
```
Employee/IT submits → Pending Management Approval
  └→ Management approves (amount, remarks)
      └→ IT records purchase (vendor, PO, date)
          └→ Asset created & linked to purchase record
```

### **DRONE OPERATIONS WORKFLOWS**

#### Equipment Tracking
- **Asset Types**: Drones, Batteries, Controllers, Ground Control Points, Sensors, Accessories
- **Calibration**: Schedule & track calibration dates for sensors
- **Movement**: Issue to project → Transfer between projects → Return to warehouse

#### Project Assignment
```
Create Drone Project → Assign Equipment Kit
  └→ Deploy to survey site
      └→ Record operations (flight hours, area covered)
          └→ Return equipment → Maintenance check
```

### **BUSINESS DEVELOPMENT WORKFLOWS**

#### Opportunity to Project Pipeline
```
BD creates Opportunity (client requirement, service type)
  └→ Technical Sample (demo/proof of concept)
      └→ Client Review → Feedback collection
          └→ Revision (if needed) → Client Re-review
              └→ Acceptance (BD records acceptance date)
                  └→ Finance Handoff (commercial discussion)
                      └→ Link Finance Project (official Project ID)
                          └→ Ortho Activation (production ready)
                              └→ Production Progress (work packages)
                                  └→ Delivery Ready → Delivered → Closed
```

#### Stage Control
- **BD controls**: opportunity → accepted → finance_handoff → project_linked
- **Ortho controls**: production → delivery_ready → delivered (auto-syncs to BD)
- **Project-linked stages**: Read-only for BD, controlled by Ortho workflow

### **ORTHO/LIDAR PROJECT EXECUTION**

#### Project Setup
```
Finance Project Master (Client, Project Code, Dates, PM)
  └→ BD links Opportunity (acceptance recorded)
      └→ Ortho PM activates project (scope, area, hours, value)
          └→ Configure Team (TL, Production, QC, QA)
              └→ Create Work Packages (area-based breakdown)
                  └→ Assign package responsibilities
```

#### Work Package Execution
```
Not Started
  └→ Production Start → In Progress
      └→ Daily Updates (area, progress %, hours, status, blockers)
          └→ Production Complete → Submit to QC
              └→ QC Review:
                  ├→ Approve → QC Complete → Submit to QA
                  │   └→ QA Review:
                  │       ├→ Approve → Delivery Ready
                  │       └→ Reject → Rework (back to Production)
                  └→ Reject → Rework (back to Production)
```

#### Rework Loop
- QC rejects → `rework_source: qc` → Production fixes → Re-submit to QC
- QA rejects → `rework_source: qa` → Production fixes → Re-submit to QC → QC → QA

#### Final Delivery
- All packages in `delivery_ready` → PM triggers Final Delivery
- Records delivery date, package count, remarks
- Auto-syncs BD opportunity stage to `delivered`

### **FINANCE CLIENT & PROJECT MANAGEMENT**

#### Client Master
```
Create Client (Code, Name, Contact, GST, Country, Source Team)
  └→ Add Projects (Project Code, Name, Dates, Status)
      └→ Assign Project Manager & Reporting Manager
          └→ Assign Employees to Project (staffing)
              └→ Set Project Status:
                  ├→ Active (employees can raise claims)
                  ├→ On Hold (claims blocked)
                  ├→ Completed (claims blocked)
                  └→ Inactive (claims blocked)
```

#### Project Lifecycle Control
- **Active**: Employees can create expense/travel claims
- **On Hold**: Temporary pause, no new claims
- **Completed**: Project delivered, archived, no new claims
- **Inactive**: Not yet started or cancelled, no new claims

**Finance BLOCKS employee self-service** by changing project status.

### **EXPENSE CLAIM WORKFLOWS**

#### Advance Request
```
Employee: Draft → Submit (purpose, project, amount, work dates)
  └→ Admin: Review → Approve/Send Back/Reject (verify work period)
      └→ Finance: Verify → Approve/Adjust Amount/Send Back/Reject
          └→ Finance: Mark Paid (payment reference, mode, date)
              └→ Status: Paid (advance released)
                  └→ Settlement Required (employee must submit bills)
```

#### Settlement (Return Unused Advance)
```
Employee: Create Settlement (link to paid advance)
  └→ Add Bills (expense items, dates, amounts, attachments)
      └→ Calculate:
          ├→ Balance to Return (advance > expenses)
          └→ Shortage Amount (expenses > advance)
      └→ Submit
          └→ Admin Review → Approve/Send Back/Reject
              └→ Finance Review → Approve/Send Back/Reject
                  └→ Finalized (settlement complete)
```

#### Reimbursement
```
Employee: Draft → Add Bills → Submit (already spent own money)
  └→ Admin: Review → Approve (verify receipts, work period)
      └→ Finance: Approve → Mark Paid (employee gets refund)
```

#### Additional Advance (Top-up)
```
Employee: Request Additional Advance (link to parent advance)
  └→ Admin → Finance → Payment
      └→ Both advances tracked together for final settlement
```

### **TRAVEL/KM CLAIM WORKFLOWS**

#### GPS-Verified Travel Claims
```
Employee: Draft (project, dates, odometer readings)
  └→ GPS Tracking:
      ├→ Start GPS recording (route capture)
      ├→ Geofence detection (auto-detect project site entry)
      └→ Stop tracking (calculate distance)
  └→ Photo Attachments (timestamped evidence)
      └→ Submit
          └→ Admin Review:
              ├→ Verify geofence entry (site proximity validation)
              ├→ Check distance variance (odometer vs GPS)
              └→ Approve/Send Back/Reject
                  └→ HR Review:
                      ├→ Final work period validation
                      └→ Approve/Send Back/Reject
                          └→ Finance Payment → Paid
```

#### Geofence Validation
- **Project Sites**: Configured with lat/lon + radius
- **Auto-Detection**: GPS track enters geofence → flag on claim
- **Admin/HR Verification**: Confirm site visit via geofence + photos

#### Distance Variance Check
- **Odometer Reading**: Employee enters start/end km
- **GPS Distance**: Calculated from route track points
- **Variance Threshold**: System flags excessive difference
- **Admin/HR Review**: Investigate discrepancy before approval

---

## DATA MODELS & RELATIONSHIPS

### **IT Assets**
- `Asset` → Many `AssetHistory` (audit trail)
- `Asset` → Many `ComponentReplacement` (upgrades/downgrades)
- `Asset` → Many `WorkRecord` (maintenance/repair)
- `Asset` → One `ReplacementRecord` (old_asset → new_asset)
- `Asset` → Many `MonthlyAssetSnapshot` (historical register)

### **Drone Operations**
- `DroneProject` → Many `DroneAssetKit` → Many `DroneKitComponent` → `DroneSurveyAsset`
- `DroneProject` → Many `DroneOperation` → Many `DroneOperationItem`
- `DroneProject` → Many `DroneWorkRecord`

### **Business Development & Ortho**
- `BDOpportunity` ←→ `FinanceProject` (1:1 link after acceptance)
- `FinanceProject` ←→ `OrthoProjectProfile` (1:1 activation)
- `OrthoProjectProfile` → Many `OrthoProjectMember` (team assignments)
- `OrthoProjectProfile` → Many `OrthoWorkPackage` (area breakdown)
- `OrthoWorkPackage` → Many `OrthoWorkSession` (time tracking)
- `OrthoWorkPackage` → Many `OrthoDailyUpdate` (progress records)
- `OrthoWorkPackage` → Many `OrthoReview` (QC/QA decisions)
- `OrthoProjectProfile` → Many `OrthoDelivery` (final handoffs)

### **Finance**
- `FinanceClient` → Many `FinanceProject`
- `FinanceClient` ←→ `FinanceClientMasterProfile` (1:1 additive metadata)
- `FinanceProject` ←→ `FinanceProjectMasterProfile` (1:1 lifecycle/staffing)
- `FinanceProject` → Many `FinanceProjectAssignment` (employee staffing)
- `User` → Many `ExpenseClaim` (requester relationship)
- `FinanceProject` → Many `ExpenseClaim` (project assignment)
- `ExpenseClaim` → Many `ExpenseClaimItem` (line items)
- `ExpenseClaim` → Many `ExpenseClaimAttachment` (bills, receipts)
- `ExpenseClaim` → Many `ExpenseClaimPayment` (payment records)
- `ExpenseClaim` ←→ `ExpenseSettlement` (1:1 for advances)
- `ExpenseClaim` → Many `ExpenseClaim` (parent advance → additional advances)

### **Travel/KM**
- `User` → Many `TravelKmClaim`
- `FinanceProject` → Many `TravelKmClaim`
- `TravelKmClaim` → Many `TravelKmAttachment` (photos)
- `TravelKmClaim` → Many `TravelKmTrackPoint` (GPS route)
- `TravelKmClaim` → Many `TravelKmVerificationSnapshot` (geofence checks)
- `FinanceProject` → Many `TravelKmGeofence` (project site boundaries)

### **Employee Portal**
- `Branch` → Many `User` (via `UserBranchAccess`)
- `User` → Many `SupportTicket`
- `SupportTicket` → Many `TicketMessage`
- `User` ←→ `AuthenticatorCredential` (1:1 for 2FA TOTP)
- `User` → Many `EmailOTPChallenge` (registration verification)

---

## APPROVAL HIERARCHIES

### IT Work Records
```
Open → IT creates → In Progress → IT completes → Closed
Management: Read-only view
```

### Asset Replacements
```
IT creates → Pending → Management approves/rejects → 
  Approved: Old asset "replaced", new asset assigned
  Rejected: Request cancelled, old asset restored
```

### Purchase Requests
```
IT/Employee submits → Pending → Management approves (amount, remarks) → 
  Approved → IT records purchase (vendor, PO) → Completed
```

### Expense Claims
```
Employee: Draft → Submit
  └→ Admin: Review → Approve/Send Back/Reject
      └→ Finance: Verify → Approve/Adjust Amount/Send Back/Reject
          └→ Finance: Mark Paid
```

### Travel/KM Claims
```
Employee: Draft → Submit
  └→ Admin: Review (GPS/geofence/distance) → Approve/Send Back/Reject
      └→ HR: Review (work period) → Approve/Send Back/Reject
          └→ Finance: Payment → Paid
```

### Expense Settlements
```
Employee: Draft → Submit
  └→ Admin: Review → Approve/Send Back/Reject
      └→ Finance: Review → Approve/Send Back/Reject → Finalized
```

### Ortho QC/QA
```
Production: Complete → Submit to QC
  └→ QC: Review → Approve (→ QA) / Reject (→ Rework)
      └→ QA: Review → Approve (→ Delivery Ready) / Reject (→ Rework)
```

---

## REPORTING & ANALYTICS

### IT Dashboard (Monthly View)
- Opening balance (assets at month start)
- Handovers (new assignments)
- Returns (devices returned)
- Purchases (new assets added)
- Replacements (damaged → new)
- Component changes (upgrades/downgrades)
- Closing balance (assets at month end)
- **Historical Mode**: View any past month via monthly snapshots

### Finance Dashboard
- **Employee View**: My claims, project assignments
- **Staff View**: 
  - Pending admin verifications
  - Pending finance approvals
  - Paid/completed claims
  - Settlement tracking
  - Project-wise expense breakdown

### BD Dashboard
- Opportunity pipeline (by stage)
- Accepted opportunities (pending finance handoff)
- Project-linked opportunities (production progress)
- Delivery-ready count
- Delivered count
- Client master integration

### Ortho Dashboard
- **PM View**: All projects, all packages
- **Participant View**: My assigned packages
- Package status breakdown (not_started, in_progress, qc, qa, delivery_ready, delivered)
- Rework tracking (QC vs QA rejections)
- Daily progress tracking (area, hours, blockers)

### Management Dashboard
- Corporate summary (all modules)
- IT asset utilization
- Drone fleet status
- BD pipeline health
- Ortho production metrics
- Finance expense trends
- Travel/KM claim patterns

---

## INTEGRATION POINTS

### Email Notifications
- OTP delivery (employee registration)
- Purchase approval requests (to Management)
- Expense claim lifecycle (submit, approve, reject, paid)
- Travel/KM claim decisions
- Ortho team assignments
- IT ticket responses

### AI Integration (Naksha Copilot)
- Gemini API for aggregated asset queries
- PII redaction (emails, phones, identifiers)
- Rate limiting (hourly quota per user)
- Privacy-safe reporting

### Excel Import/Export
- **IT Assets**: Bulk import (desktops, laptops, printers, external HDDs)
- **Drone Hardware**: Inventory import
- **Historical Activity**: Handover/return/purchase records
- **Client Master**: Client/Project workbook import/export
- **Finance Reports**: Filtered expense/travel claim exports
- **Monthly IT Summary**: Dashboard export

### GPS/Geolocation
- Real-time GPS tracking (Travel/KM claims)
- Geofence validation (project site entry detection)
- Route distance calculation
- Photo geotagging & timestamp validation

### Backup Systems
- **PostgreSQL Dumps**: Scheduled backups with retention
- **Local Windows Agent**: Desktop backup integration
- **Restore Workflows**: Version tracking, restore points

---

## SECURITY & COMPLIANCE

### Authentication
- **JWT Tokens**: 480-minute expiration
- **Argon2 Hashing**: Password security
- **2FA (TOTP)**: Required for privileged roles (admin, management, software_team)
- **Email Verification**: Employee portal registration
- **Session Tracking**: IP, user-agent, branch logging

### Authorization
- **Role-Based Access Control** (RBAC): 11 role types
- **Branch-Based Access**: Employee portal filtered by branch
- **Row-Level Security**: Employees see only their own claims/tickets
- **Privileged Account Validation**: MFA enforcement on first login

### Audit Trails
- `AssetHistory`: Every asset edit/assignment/return
- `ApprovalDecisionHistory`: All approval actions
- `ExpenseClaimEvent`: Claim state transitions
- `TravelKmEvent`: Travel claim lifecycle
- `BDOpportunityEvent`: BD stage changes
- `AuditEvent`: Login attempts, privileged actions

### Data Privacy
- **PII Redaction**: AI queries strip personal identifiers
- **Employee Project View**: Hides commercial client metadata
- **Finance Separation**: Employees cannot see other employees' claims
- **Branch Isolation**: Employee portal filtered by branch access

---

## TECHNOLOGY STACK

### Backend
- **Framework**: FastAPI (Python 3.11+)
- **ORM**: SQLAlchemy 2.x
- **Database**: PostgreSQL 15+ (production), SQLite (testing)
- **Migrations**: Alembic
- **Authentication**: JWT (python-jose), Argon2 (passlib)
- **2FA**: PyOTP (TOTP)
- **Email**: SMTP (smtplib)
- **AI**: Google Gemini API
- **Excel**: openpyxl, pandas
- **Async**: asyncio, websockets

### Frontend
- **Framework**: React 18.3.1
- **Language**: TypeScript 5.x
- **Build Tool**: Vite 5.x
- **Routing**: React Router 6.x
- **State**: Context API + hooks
- **Styling**: Tailwind CSS (assumed from modern stack)
- **HTTP Client**: Axios

### Infrastructure
- **Deployment**: Docker Compose (dev), cPanel Passenger (prod)
- **Reverse Proxy**: Nginx / cPanel Apache
- **Storage**: Local filesystem (future: MinIO S3-compatible)
- **Cache**: Redis (optional, falls back to in-memory)
- **Monitoring**: Agent Monitor integration

---

## KEY BUSINESS RULES

### IT Asset Management
1. **Custody Tracking**: Every assignment must record custodian (user) and department
2. **Component Changes**: Upgrading RAM from 8GB to 16GB creates spare 8GB stock entry
3. **Replacement Approval**: Management must approve before swapping damaged asset with new one
4. **Monthly Snapshots**: Immutable historical register created at month boundary
5. **Status Transitions**: Strict state machine (Available → Assigned → Repair → Replaced)

### Finance Client/Project Master
1. **Project Status Controls Employee Access**: Only `Active` projects allow new claims
2. **Client Inactive**: Blocks all projects under that client
3. **Project Dates**: Claims before start_date or after end_date are blocked
4. **Legacy Projects**: Pre-V6 projects without client_id still function (historical compatibility)
5. **Project Manager Authority**: Only Finance-assigned PM can activate Ortho project

### Expense Claims
1. **Advance → Settlement**: Paid advance MUST have settlement before closure
2. **Additional Advance**: Links to parent advance, combined in settlement
3. **Amount Adjustment**: Finance can reduce approved amount (not increase beyond requested)
4. **Work Period**: Admin/Finance can adjust approved work dates (separate from employee request)
5. **Payment Tracking**: Multiple partial payments supported (installments)

### Travel/KM Claims
1. **GPS Required**: Cannot submit without GPS track
2. **Geofence Validation**: Admin/HR verify project site entry via geofence
3. **Distance Variance**: System flags if odometer differs significantly from GPS distance
4. **Photo Timestamps**: Attachments must have valid EXIF timestamps
5. **Three-Level Approval**: Admin → HR → Finance (all must approve)

### Business Development
1. **Opportunity Ownership**: BD user owns opportunities they create (cannot edit others')
2. **Acceptance Before Link**: Must record `accepted` stage before Finance Project link
3. **Project Uniqueness**: One Project ID can link to only one BD opportunity
4. **Stage Auto-Sync**: Ortho production progress auto-updates BD stage (production, delivery_ready, delivered)
5. **Closed Opportunities**: Cannot reopen from UI (data integrity)

### Ortho/LiDAR Projects
1. **Finance PM is Ortho PM**: Project Manager in Finance Project Master controls Ortho activation
2. **Team Roles**: 4 roles required (Team Leader, Production, QC, QA)
3. **Package Assignments**: Can override project-level team with package-specific assignments
4. **QC → QA Flow**: Must pass QC before QA review
5. **Rework Loop**: QC/QA rejection sends back to Production (rework_source tracked)
6. **Delivery Condition**: All packages must be in `delivery_ready` before final delivery

---

## DEPLOYMENT SCENARIOS

### Development (Docker Compose)
```yaml
services:
  db: PostgreSQL 15
  backend: FastAPI on port 8000
  frontend: Vite dev server on port 3100 (proxies /api to backend)
```

### Production (cPanel Passenger)
```
Domain: naksha.example.com
Backend: passenger_wsgi.py → FastAPI ASGI app
Frontend: Built static files in public_html
Database: PostgreSQL via TCP
API Mount: Externally configured (e.g., /api → backend)
```

---

## CONCLUSION

This is a **fully-integrated enterprise operations platform** with:
- **11 specialized role types** each with distinct workflows
- **8 major business modules** (IT, Drone, BD, Ortho, Finance, HR, Employee Portal, Management)
- **Complex multi-level approval chains** (3-4 steps for financial claims)
- **GPS-verified travel tracking** with geofence validation
- **Project-based access control** (Finance blocks employee claims via project status)
- **Real-time collaboration** (Ortho teams, BD pipeline, IT asset handovers)
- **Comprehensive audit trails** across all entities
- **Historical data integrity** (monthly snapshots, immutable archives)

The system handles the complete lifecycle from:
- **Client acquisition** (BD opportunity) 
- → **Project setup** (Finance Project Master)
- → **Production execution** (Ortho work packages)
- → **Resource allocation** (IT assets, Drone equipment)
- → **Financial tracking** (Expense claims, Travel KM)
- → **Delivery & closure** (Ortho final delivery, BD opportunity closed)

Each role has **distinct responsibilities** and **non-overlapping authority** to maintain operational integrity and audit compliance.
