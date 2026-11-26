# 2026 Full-Year ERP UAT Dataset

This branch contains a deterministic synthetic dataset used only for end-to-end ERP testing before production deployment.

## Safety contract

- Tag: `UAT_YEAR_SIMULATION_2026`
- Client codes: `UAT26-CLI-###`
- Project codes: `UAT26-PRJ-####`
- Invoice codes: `UAT26-INV-####`
- Payment references: `UAT26-PAY-####-#`
- The generator refuses to run when the application is configured as production.
- The generator refuses to create a second copy if UAT26 clients/projects already exist.
- Cleanup requires the exact confirmation token `UAT_YEAR_SIMULATION_2026`.
- Cleanup targets only UAT26-tagged/prefixed fixtures. It does not reset, truncate or drop the database.
- Neither seed nor cleanup runs automatically at application startup.

## Default coverage

Default generation uses fixed seed `2026` and creates:

- 50 synthetic clients
- 200 projects
- all five performing departments
- dates spread from January through December 2026
- INR, USD, GBP and AED commercial data
- exactly INR 4,00,00,000 of realized revenue from fully-paid, closed Finance invoices
- draft and Finance-returned projects
- Production and QA work-in-progress
- client feedback waiting state
- correction/rework and change-request states
- ready-for-billing, invoice-raised, payment-pending, partial, overdue and payment-received/open states
- fully paid + invoice-closed Revenue records
- technical project teams and work packages
- employee project expenses
- vendor invoices
- employee reimbursement claims
- Travel/KM claims in multiple approval states
- synthetic Asset/IT work records
- synthetic Drone inventory/location rows

The generator reuses active BD, Finance, technical PM and department Employee accounts already configured in the ERP. It intentionally does not create or hard-code login passwords.

## Commands

Run from the repository root while on `feature/2026-uat-data-analytics`.

Preview without writing:

```powershell
docker compose exec backend python scripts/seed_2026_uat_data.py --dry-run
```

Create the default full-year dataset:

```powershell
docker compose exec backend python scripts/seed_2026_uat_data.py
```

Validate loaded UAT data:

```powershell
docker compose exec backend python scripts/validate_2026_uat_data.py
```

Preview cleanup:

```powershell
docker compose exec backend python scripts/cleanup_2026_uat_data.py --dry-run
```

Delete only this UAT dataset:

```powershell
docker compose exec backend python scripts/cleanup_2026_uat_data.py --confirm UAT_YEAR_SIMULATION_2026
```

Validate again after cleanup. Expected UAT client/project count is zero:

```powershell
docker compose exec backend python scripts/validate_2026_uat_data.py
```

## Production deployment rule

Do not deploy synthetic UAT rows as production business records. Before production cutover:

1. take the normal database backup;
2. run the UAT cleanup command with the explicit confirmation token;
3. validate that UAT clients/projects and UAT cross-module fixtures are gone;
4. run application regression/build/health tests;
5. then deploy the clean application/database state.

Never replace this controlled cleanup with `docker compose down -v`, database drops, global truncation, or broad delete statements.
