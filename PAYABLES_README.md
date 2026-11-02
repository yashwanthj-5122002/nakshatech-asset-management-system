# NakshaTech Payables — integration package (30 October 2026)

This contains working new module source files plus a **conservative Windows installer**. It is not already deployed to your Windows ERP. It is designed against the NakshaTech source files previously uploaded in this conversation; your local Git branch may have newer edits. The installer refuses to apply if required routing/sidebar insertion points have changed.

## Scope

- **Admin Bills**: Admin raises office and maintenance bills; Finance views and pays; Vinod and Chethan each approve. Admin + both managers receive notifications after partial and final payments.
- **Finance Team Bills**: Finance raises, both managers independently approve, Finance records payments. Admin cannot access the bills, documents, or notification events.
- **Both approvals on the current bill version are required** before a payment can be recorded. Finance edits reset approvals; submitting again requests two new approvals.
- Partial payments, running balance, percentage progress bar and status are displayed. Payments are ledger entries only: **the ERP does not initiate transfers**.
- Every recorded payment requires a PDF/JPEG/PNG challan and an individual transaction reference, unique per payable. Original bill upload required before submitting to management.
- Download original bill and payment challans after payment, subject to per-login authorization.
- Existing ERP notification bell is reused; no email alerts or changes to existing module notifications.
- Existing financial ledger / billing data is **not** modified or auto-posted into another finance ledger. Avoid double-counting.

## Package contents

- `NAKSHA_PAYABLES_INSTALL.py` — `--check`, `--apply`, `--restore`
- `payables_bundle.zip` — 8 additive backend/frontend source files, plus new Payables router/model/migration.
- This README.

## Windows PowerShell — safe installation procedure

**0. Before deploying:** do this on a development/staging copy first. Ensure your current working files have been committed or securely backed up. Verify `git status` and create a restore branch before applying. Do not drop or recreate PostgreSQL data volumes.

```powershell
cd "E:\nakshatech-erp-shreeyansh1"
git status --short
git branch backup/payables-before-integration
```

**1. Extract the package** into the ERP root, where `backend` and `frontend` folders exist. For example, after downloading the ZIP into Downloads:

```powershell
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\NAKSHA_PAYABLES_INTEGRATION.zip" -DestinationPath "E:\nakshatech-erp-shreeyansh1" -Force
cd "E:\nakshatech-erp-shreeyansh1"
```

**2. Run dry-run validation.** This makes **no changes**:

```powershell
py .\NAKSHA_PAYABLES_INSTALL.py --check
```

If it says `STOP`, do **not** bypass the check. It means the newer ERP's source needs a more precise integration. Back up and supply the conflicting files.

**3. Back up PostgreSQL (before applying source and database changes).** This uses PostgreSQL's own custom-format dump and copies it to your personal Documents folder. Ensure free disk space.

```powershell
docker compose -p nakshatech_asset_management_local_master ps
# This writes inside the running db container, not into your repo:
docker compose -p nakshatech_asset_management_local_master exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" -f /tmp/payables-prechange.dump'
docker cp "nakshatech_asset_management_local_master-db-1:/tmp/payables-prechange.dump" "$env:USERPROFILE\Documents\payables-prechange-20261030.dump"
```

Ensure the dump file exists and has nonzero size. Don't upload, commit or email database dumps. If `pg_dump` fails, **stop** instead of proceeding without backup.

**4. Apply source integration** (only if `--check` succeeds):

```powershell
py .\NAKSHA_PAYABLES_INSTALL.py --apply
```

The installer adds new files and inserts Payables imports/routes/sidebar entry into only these existing files:

- `backend/app/main.py`
- `frontend/src/App.tsx`
- `frontend/src/components/Layout.tsx`

**No other existing ERP module file is changed by this installer.** It saves originals outside the repo under `%LOCALAPPDATA%\NakshaTech\payables-backups\...`, and prints the exact backup directory.

**5. Build and compile:**

```powershell
cd "E:\nakshatech-erp-shreeyansh1\frontend"
npm.cmd install
npm.cmd run build
cd "E:\nakshatech-erp-shreeyansh1"
docker compose -p nakshatech_asset_management_local_master build backend frontend
```

If frontend build fails, do **not** proceed to the database migration/deployment; share the errors.

**6. Apply the five-table additive migration** against the running **staging** PostgreSQL container. It does not change existing ERP tables.

```powershell
docker compose -p nakshatech_asset_management_local_master run --rm --no-deps backend python -m app.modules.payables.migrate --check
docker compose -p nakshatech_asset_management_local_master run --rm --no-deps backend python -m app.modules.payables.migrate --apply
```

The normal ERP FastAPI startup also calls SQLAlchemy `Base.metadata.create_all`, and newly imported Payables models are registered, so if you skip the explicit migration the tables may be created at startup. Use the explicit, audited migration path instead.

**7. Start services in order** (database must be healthy first):

```powershell
docker compose -p nakshatech_asset_management_local_master ps
docker compose -p nakshatech_asset_management_local_master up -d --no-deps backend
docker compose -p nakshatech_asset_management_local_master ps backend
docker compose -p nakshatech_asset_management_local_master logs --tail 50 backend
docker compose -p nakshatech_asset_management_local_master up -d --no-deps frontend
docker compose -p nakshatech_asset_management_local_master restart nginx
docker compose -p nakshatech_asset_management_local_master ps
```

If your frontend container keeps old `node_modules`, install from the **already updated** package.json in that container:

```powershell
docker compose -p nakshatech_asset_management_local_master exec frontend npm install
```

Then open **http://localhost:3100/payables** (same server as your ERP).

## Manual four-login UAT

1. Admin: `Payables > Raise Admin Bill`, attach original bill, submit. Check manager bell alerts, finance visibility and admin tracking.
2. Vinod: login as `vinod@nakshatech.com`, open pending bill, approve. Verify Finance still **cannot pay**.
3. Chethan: login as `chethan@nakshatech.com`, approve. Verify Finance can now record payment.
4. Finance: pay e.g. 30% using challan, verify 30% progress and outstanding 70%. Pay the rest with a new unique transaction reference and challan. Verify 100% Paid & Closed and notifications for Admin + Vinod + Chethan.
5. Repeat with Finance Team Bill. Verify Admin can **not** list, open, download or receive notifications about this bill.
6. Edit an approved but unpaid bill in Finance and verify both approvals reset and payment is blocked until resubmission and two new approvals.
7. Verify existing modules: Finance Dashboard, billing, expense claims, BD/Operations, Pilot, Travel/KM and Welcome/Login. If any existing workflow changes, stop deployment and use Git/installer rollback.

The two management users **must** already exist in `users` as active users with `role = management` and the exact emails you specified. The module will reject submission if either is unavailable; it does not create or modify user accounts.

## Precautions and rollback

- **Never run** `docker compose down -v`, `docker volume prune`, or `git reset --hard` as a workaround.
- To restore only source files to their pre-install state, use the exact printed backup directory:

```powershell
py .\NAKSHA_PAYABLES_INSTALL.py --restore "C:\Users\YOUR_USER\AppData\Local\NakshaTech\payables-backups\payables-YYYYMMDD-HHMMSS"
```

Then rebuild affected Docker images as normal. The restore deliberately **does not delete Payables tables or their data**; database rollback requires a separate reviewed migration. The source installer never changes the database itself.

## Validation already performed in the sandbox

- Python syntax validation on all new backend modules.
- TypeScript/JSX syntax transpilation: zero parser errors (a full frontend dependency build must run on your Windows PC).
- Isolated FastAPI + SQLite API workflow smoke tests passed: Admin creation, required bill file, approvals and payment lock, partial/full payments, per-payment proof downloads, Admin denial for Finance Team Bills, edit/reset approvals, and immutable paid bills.
- Source installer dry-run and apply tested against the prior uploaded source snapshot. **Not tested against your latest Windows branch or actual PostgreSQL data.**
