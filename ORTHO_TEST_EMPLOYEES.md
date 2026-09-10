# Ortho Test Employees - V7.0.13+

## Overview
These 4 dummy employees are created for testing the complete Ortho/LiDAR project workflow including team assignments, work package execution, QC/QA reviews.

## Enabling Test Employees

Add to your `.env` file:
```bash
SEED_OPERATIONS_TEST_USERS_ENABLED=true
```

Then restart the backend:
```bash
cd backend
python -m app.main
```

## Test Employee Accounts

### 1. **Ortho Team Leader**
- **Email**: `ortho.teamleader@nakshatech.com`
- **Password**: `TestTeamLeader@2026`
- **Employee ID**: `ORTHO-TL-001`
- **Department**: Ortho
- **Designation**: Team Leader
- **Role**: employee
- **Responsibility**: Record daily updates (achieved area, progress %, hours, blockers, remarks)

### 2. **Ortho Production Staff**
- **Email**: `ortho.production@nakshatech.com`
- **Password**: `TestProduction@2026`
- **Employee ID**: `ORTHO-PROD-001`
- **Department**: Ortho
- **Designation**: Production Specialist
- **Role**: employee
- **Responsibility**: Execute production work (start, pause, resume, complete), submit to QC

### 3. **Ortho QC Reviewer**
- **Email**: `ortho.qc@nakshatech.com`
- **Password**: `TestQC@2026`
- **Employee ID**: `ORTHO-QC-001`
- **Department**: Ortho
- **Designation**: QC Specialist
- **Role**: employee
- **Responsibility**: QC review (approve/reject with comments), send to QA or back to Production

### 4. **Ortho QA Reviewer**
- **Email**: `ortho.qa@nakshatech.com`
- **Password**: `TestQA@2026`
- **Employee ID**: `ORTHO-QA-001`
- **Department**: Ortho
- **Designation**: QA Specialist
- **Role**: employee
- **Responsibility**: Final QA review (approve/reject with comments), mark as delivery ready

## Testing the Complete Ortho Workflow

### Step 1: Create Finance Project
1. Login as Finance user
2. Create Client → Create Project
3. Set Project Manager
4. Activate project (status: Active)

### Step 2: Link BD Opportunity (Optional)
1. Login as BD user
2. Create opportunity
3. Mark as "accepted"
4. Link to Finance Project

### Step 3: Activate Ortho Project
1. Login as Ortho PM (`ortho.pm@nakshatech.com`)
2. Navigate to Ortho Dashboard
3. Activate Project:
   - Total area (e.g., 500 ha)
   - Planned hours (e.g., 200)
   - Target value (e.g., 500000)
   - Scope text

### Step 4: Configure Project Team
1. Assign team roles:
   - **Team Leader**: ortho.teamleader@nakshatech.com
   - **Production**: ortho.production@nakshatech.com
   - **QC**: ortho.qc@nakshatech.com
   - **QA**: ortho.qa@nakshatech.com
2. Enable "Apply to unassigned packages"
3. Save team configuration
4. Send assignment emails (optional)

### Step 5: Create Work Package
1. Create work package:
   - Package Code: PKG-001
   - Package Name: Zone A Processing
   - Area: 100 ha
   - Target hours: 40
   - Assignments inherit from project team

### Step 6: Production Work
1. Login as Production user (`ortho.production@nakshatech.com`)
2. Navigate to Ortho Dashboard → My Packages
3. Start production: Click "Start" → Status changes to "In Progress"
4. Record daily updates (as Team Leader):
   - Achieved area: 25 ha
   - Progress: 25%
   - Hours spent: 10
   - Status: On Track
   - Remarks: "Processing going well"
5. Complete production: Click "Complete"
6. Submit to QC

### Step 7: QC Review
1. Login as QC user (`ortho.qc@nakshatech.com`)
2. Navigate to Ortho Dashboard → QC Queue
3. Review work package:
   - **Option A - Approve**: Click "Approve" → Goes to QA queue
   - **Option B - Reject**: Click "Reject" + comments → Back to Production (rework)

### Step 8: QA Review
1. Login as QA user (`ortho.qa@nakshatech.com`)
2. Navigate to Ortho Dashboard → QA Queue
3. Final review:
   - **Option A - Approve**: Click "Approve" → Status: Delivery Ready
   - **Option B - Reject**: Click "Reject" + comments → Back to Production (rework)

### Step 9: Final Delivery
1. Login as Ortho PM
2. When all packages are "Delivery Ready"
3. Trigger "Final Delivery"
4. BD Opportunity auto-updates to "Delivered" stage

## Testing Rework Loops

### QC Rework
1. QC rejects work → `rework_source: qc`
2. Production fixes issues
3. Production re-submits to QC
4. QC re-reviews

### QA Rework
1. QA rejects work → `rework_source: qa`
2. Production fixes issues
3. Production submits to QC (starts from QC again)
4. QC approves → QA
5. QA re-reviews

## Email Notifications

When "Send Assignment Emails" is triggered, each team member receives:

**Subject**: `[PROJECT-CODE] Ortho/LiDAR assignment - [Role]`

**Body** includes:
- Project ID
- Project Name
- Client
- Role / Responsibility
- Project Manager details
- Start/End dates
- Scope
- Specific update responsibilities
- ERP Ortho Dashboard link

## Database Schema

The employees are created in the `users` table with:
- `role`: "employee" (NOT ortho or bd, they are assignees)
- `email_verified`: true
- `account_status`: "active"
- `is_active`: true
- `mfa_required`: false
- `must_change_password`: false

## Notes

1. **Employee Role**: These are regular employees who get assigned Ortho responsibilities by the PM
2. **Not Ortho Role**: Only the PM has `role=ortho`, team members are `role=employee`
3. **Multiple Projects**: Same employees can be assigned to multiple Ortho projects
4. **Email Display**: The UI should show `employee_email` (e.g., `ortho.teamleader@nakshatech.com`) when displaying assignments
5. **Employee ID Display**: The UI can also show `employee_id` (e.g., `ORTHO-TL-001`) for internal tracking

## Troubleshooting

### Issue: "Other email" showing instead of correct email
**Cause**: Frontend might be looking at wrong field or backend returning wrong data  
**Fix**: Check `OrthoProjectMember` payload - it should include:
- `user_id`
- `user_name` (from User.full_name)
- `user_email` (from User.email)
- `member_role`

### Issue: Cannot assign team members
**Cause**: `SEED_OPERATIONS_TEST_USERS_ENABLED` not enabled or employees not created  
**Fix**: 
1. Add `SEED_OPERATIONS_TEST_USERS_ENABLED=true` to `.env`
2. Restart backend
3. Check database: `SELECT * FROM users WHERE employee_id LIKE 'ORTHO-%'`

### Issue: Assignment email not sent
**Cause**: SMTP not configured or email sending failed  
**Fix**: V7.0.13+ separates assignment saving from email delivery - assignment is saved even if email fails. Check SMTP configuration and retry "Send Assignment Emails"

## API Endpoints for Testing

### Get Ortho Projects (as Team Member)
```bash
GET /api/operations/ortho/projects
Headers: Authorization: Bearer <employee_token>
```

### Record Daily Update
```bash
POST /api/operations/ortho/work-packages/{work_package_id}/daily-update
{
  "achieved_area": 25,
  "progress_percent": 25,
  "hours_spent": 10,
  "status": "on_track",
  "remarks": "Progress good"
}
```

### Production Actions
```bash
POST /api/operations/ortho/work-packages/{work_package_id}/work-action
{
  "action": "start"  // or "pause", "resume", "complete"
}
```

### Submit to QC
```bash
POST /api/operations/ortho/work-packages/{work_package_id}/submit-qc
```

### QC Review
```bash
POST /api/operations/ortho/work-packages/{work_package_id}/qc
{
  "decision": "approve",  // or "reject"
  "comments": "Quality is good"
}
```

### QA Review
```bash
POST /api/operations/ortho/work-packages/{work_package_id}/qa
{
  "decision": "approve",  // or "reject"
  "comments": "Final approval"
}
```
