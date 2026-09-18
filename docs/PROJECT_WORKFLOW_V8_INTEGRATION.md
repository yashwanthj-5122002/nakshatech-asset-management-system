# Project Workflow V8 Integration

## Purpose

V8 replaces the previous BD/Ortho project-operations path with the accepted Nakshatech workflow while preserving unrelated application modules and historical data.

## Authoritative workflow

```text
BD
  ↓
Search Existing Client / Create Client
  ↓
Create Project
  ↓
Manually enter Project ID
  ↓
Project details + dates + scope + commercial data
  ↓
Submit to Finance
  ↓
Finance Approve / Return with mandatory feedback
  ↓
BD corrects + resubmits when returned
  ↓
Finance Approved
  ↓
BD assigns Ortho Project Manager
  ↓
PM notified by ERP + email
  ↓
Project Manager selects exactly one Team Lead
  + multiple Production employees
  + multiple QC employees
  + multiple QA employees
  ↓
Selected employees notified by ERP + email
  ↓
Team Lead allocates Area + Code + Quantity + Target Date
  only to PM-selected employees for that role
  ↓
Assigned employee receives ERP + email + exact dashboard task
  ↓
Daily Activity
  ↓
Team Lead + PM monitoring
  ↓
Production Complete
  ↓
QC Approve → QA | QC Reject → Production Rework
  ↓
QA Approve → Ready for Delivery | QA Reject → Production Rework
  ↓
Delivery
  ↓
PM Operational Completion
  ↓
BD + Finance notified
  ↓
Finance Closure
  ↓
CLOSED
```

## Security and visibility rules

The backend is authoritative for visibility; React hiding alone is not relied upon.

### BD

BD can see client identity, project details, dates, scope and commercial information. BD creates clients/projects, submits projects to Finance, corrects returned projects, and assigns the Ortho PM only after Finance approval.

### Finance

Finance can see business/commercial data required for approval and closure. V8 Finance can approve or return a project. Return feedback is mandatory. Existing Finance-side expense approval and payment logic is preserved.

### Project Manager

PM sees Project ID, Client ID, schedule, operational scope, team, work packages and progress. PM does not receive Client Name, client contacts or commercial values through the V8 Ortho API.

### Team Lead

Team Lead sees only the project(s) where assigned as Team Lead. They can allocate work only to Production/QC/QA employees selected by the PM for that project and role.

### Production / QC / QA employee

A normal employee sees only work packages where their user ID is directly assigned as Team Lead, Production, QC or QA. Merely being a project participant no longer exposes every project work package.

Normal employees receive Client ID + Project ID and exact operational task data; Client Name and commercial information are not exposed.

## Backend additions

### New workflow state tables

- `ops_v800_project_workflows`
- `ops_v800_project_workflow_events`

These are additive tables. Existing legacy project records and other module tables are not deleted.

### Existing table additions

- `ops_v600_ortho_work_packages.target_date`
- `ops_v600_ortho_daily_updates.files_completed`

`backend/app/main.py::ensure_schema_compatibility()` adds these columns/indexes safely when missing.

## V8 API routes

All routes are below `/operations/workflow`.

### BD

- `GET /bd/dashboard`
- `POST /bd/clients`
- `POST /bd/projects`
- `PUT /bd/projects/{project_id}`
- `POST /bd/projects/{project_id}/submit-finance`
- `POST /bd/projects/{project_id}/assign-pm`

### Finance

- `GET /finance/dashboard`
- `POST /finance/projects/{project_id}/review`
- `POST /finance/projects/{project_id}/close`

### Ortho / Employee

- `GET /ortho/dashboard`
- `POST /ortho/projects/{project_id}/team`
- `POST /ortho/projects/{project_id}/work-packages`
- `POST /ortho/work-packages/{package_id}/daily-activity`
- `POST /ortho/work-packages/{package_id}/production-complete`
- `POST /ortho/work-packages/{package_id}/qc`
- `POST /ortho/work-packages/{package_id}/qa`
- `POST /ortho/work-packages/{package_id}/deliver`
- `POST /ortho/projects/{project_id}/complete`

## Workflow states

```text
draft
pending_finance_approval
finance_returned
finance_approved
pm_assigned
team_assigned
in_progress
finance_closure_pending
closed
```

Work-package stage/review state remains independently tracked so each Area/Code can progress through Production, QC, QA, rework and delivery without conflating it with overall project status.

## PM team rules

- Exactly one Team Lead is required.
- Multiple Production employees are supported.
- Multiple QC employees are supported.
- Multiple QA employees are supported.
- The Team Lead may also be selected in Production, QC and/or QA.
- Employee choices are active Employee-role accounts.
- Saving the team synchronizes project assignment records used by the Expense project selector.

## Work allocation rules

A Team Lead supplies:

- Area
- Code
- Quantity
- Unit
- Target Date
- Production employee
- QC employee
- QA employee

Each role assignee must be present in the corresponding PM-selected role list for the project.

## Daily activity and progress

Production employees enter daily activity against their exact work package. The service calculates cumulative completed quantity, remaining quantity and progress from stored daily activity. Employees cannot directly set overall project progress.

## QC / QA / rework

QC and QA actions require the exact assigned reviewer. Rejection comments are mandatory and review history is retained. Rejected work returns to Production rework; approvals advance to the next stage.

## Delivery and completion

Team Lead or PM can mark a QA-approved work package delivered. PM operational completion is available only when every required work package is delivered. Operational completion notifies BD and Finance and moves the project to Finance Closure Pending.

Finance is the only business role that can execute the V8 final closure action. Closure sets the workflow status to `closed` and sends final notifications.

## Expenses integration

The existing Expense module and its approval chain remain active. V8 changes only project visibility/integration:

- Employee `/finance/projects` returns assigned projects only.
- Employee-safe project payload keeps Client ID and Project ID but removes Client Name and unrelated project metadata.
- Expense creation/update validates that the employee is assigned to the selected project.
- Finance V8 dashboard shows an informational expense summary for closure context.
- Existing expense approval/payment/settlement records and routes are not replaced.

## Existing modules intentionally preserved

This integration does not replace the existing workflows for:

- IT
- Asset Management
- Drone
- Expenses and expense approvals
- Travel/KM
- Support/Ticket raising
- HR
- Backup and system operations

Legacy cross-department project pages remain available to the technical roles that still use them. BD and Ortho navigation/route access is moved to the V8 authoritative workflow rather than deleting legacy database history.

## Frontend entry points

- `/bd` → V8 BD dashboard
- `/ortho` → V8 PM/Team Lead/Employee operations dashboard
- `/finance` → existing Finance expense dashboard plus V8 project approval/closure section

`/finance/clients` is retained only as a legacy Admin/Management surface; Finance no longer creates BD-owned V8 clients/projects there.

## Notifications

V8 sends ERP notifications and email for the main workflow transitions, including:

- Submit to Finance
- Finance approve/return
- PM assignment
- PM team assignment
- Team Lead work allocation
- Production completion
- QC transition/rework
- QA transition/rework
- Delivery
- Operational completion
- Finance closure

Operational emails use Client ID + Project ID and do not include Client Name or commercial values.

## Validation performed on this source package

- Python source compilation: `python -m compileall -q backend/app`
- Frontend TypeScript project check: `npx tsc -b --pretty false`

Both checks pass in the analysis environment.

A full backend runtime/test boot could not be completed in the analysis environment because its preinstalled FastAPI is older than the version pinned by this project and the required PostgreSQL driver is not available there. The project itself specifies `fastapi>=0.137.2,<0.138` and the Docker/runtime dependency files should be used for real integration testing.

The Vite production bundle additionally requires platform-specific optional Rollup packages. The uploaded `node_modules` tree did not contain the Linux Rollup optional binary, so the source-level TypeScript validation was used here rather than treating that environment-only package mismatch as an application-code failure.
