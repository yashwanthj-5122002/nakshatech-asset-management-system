NAKSHA - BD Project 1234 Draft Expense Cancellation
=============================================
WHY: Project 1234 (project_id 1) cannot close while PEXP-20261030-4EBCF78F0C
is DRAFT. Admin rejected KM claim NT-KM-2026-00001, a DIFFERENT record.
There is no evidence of a database link between them. Do not auto-cancel it.

CHANGES (ONLY 3 FILES):
  backend/app/modules/commercial/schemas.py
  backend/app/modules/commercial/service.py
  backend/app/modules/commercial/router.py

ADDS an authenticated POST /api/commercial/expenses/{expense_id}/cancel endpoint.
Only expense owner, Finance or Admin. Only DRAFT or RETURNED status, explicit
reason of >=10 characters. Reimbursement/approval/vendor-linked expenses blocked.
Status transitions to CANCELLED (not deleted) with ProjectExpenseEvent and Audit log.
NO database migration; status column is varchar(30). The Finance Closure check
remains unchanged and will continue to block all genuine unsettled expenses.

WINDOWS POWERSHELL 5.1 INSTALL (from ERP repository root):
  Expand-Archive -LiteralPath "$HOME\Downloads\NAKSHA_BD_1234_CANCEL_FIX.zip" -DestinationPath ".\bd_cancel_fix" -Force
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\bd_cancel_fix\apply_bd_expense_fix.ps1" -ProjectRoot (Get-Location).Path
  [expect: DRY RUN ONLY, no files changed]
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\bd_cancel_fix\apply_bd_expense_fix.ps1" -ProjectRoot (Get-Location).Path -Apply
  git diff --check -- backend/app/modules/commercial/service.py backend/app/modules/commercial/router.py backend/app/modules/commercial/schemas.py
  docker compose up -d --build --no-deps backend

READ-ONLY CHECK:
  Get-Content ".\bd_cancel_fix\verify_bd_expense_readonly.py" -Raw | docker compose exec -T backend python -

TO CANCEL EXISTING DRAFT (only if you confirm it is invalid):
  Log into your ERP as the owner (employee id 46), Finance or Admin.
  Open F12 DevTools > Console in the ERP tab.
  Read and paste 'cancel_project_1234_browser_console.js' after reviewing it.
  Confirm the exact code and give a genuine reason. This performs one authorized
  audited API transaction (does NOT silently cancel any expense).
  Refresh Finance Closure and rerun verify script.

No modifications to Project 1717/Management, BD feedback, Travel/KM rejection,
invoice payments, commercial closure validation, database schema or Docker volumes.

CAVEATS:
 - The ZIP did not contain the Commercial Expense frontend page, so this is a
   backend endpoint and browser-console helper, NOT a new UI button.
 - Other validations may still prevent Finance Closure after cancellation.
 - If expense is legitimate, resolve it through its normal Finance workflow.
 - Project data is never modified by the installer itself.
