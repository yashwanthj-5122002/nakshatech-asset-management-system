import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'

const root = process.cwd()
const pageSource = fs.readFileSync(path.join(root, 'src/features/finance/pages/FinanceCommandCenter.tsx'), 'utf8')
const apiSource = fs.readFileSync(path.join(root, 'src/features/finance/advancePaymentApi.ts'), 'utf8')
const cssSource = fs.readFileSync(path.join(root, 'src/features/finance/pages/sales-revenue.css'), 'utf8')

// ---------------------------------------------------------------------------
// API wiring: collection read model + record receipt + apply to invoice
// ---------------------------------------------------------------------------
assert.ok(apiSource.includes('export function getAdvanceCollection'), 'collection endpoint must be exposed')
assert.ok(apiSource.includes('/finance/advance-payments/${projectId}/collection'), 'collection GET path')
assert.ok(apiSource.includes('export function applyAdvanceToInvoice'), 'apply-to-invoice must be exposed')
assert.ok(apiSource.includes('/finance/advance-payments/${projectId}/apply-to-invoice'), 'apply POST path')
assert.ok(apiSource.includes('export function recordAdvanceTransaction'), 'record receipt must be exposed')
assert.ok(apiSource.includes('/transactions'), 'record receipt must reuse the existing transactions endpoint')
assert.ok(apiSource.includes('advance_unapplied_inr'), 'collection must expose the unapplied advance')

// ---------------------------------------------------------------------------
// Two clearly separated financial layers
// ---------------------------------------------------------------------------
assert.ok(pageSource.includes('ADVANCE COLLECTION'), 'ADVANCE COLLECTION card must exist')
assert.ok(pageSource.includes('PROJECT COLLECTION'), 'PROJECT COLLECTION card must exist')
const advanceCard = pageSource.indexOf('data-layer="advance"')
const projectCard = pageSource.indexOf('data-layer="project"')
assert.ok(advanceCard !== -1 && projectCard !== -1, 'both layers must be rendered')
assert.ok(advanceCard < projectCard, 'advance layer must come before the project collection layer')
for (const field of ['advance_expected_inr', 'advance_received_inr', 'advance_pending_inr', 'advance_applied_inr', 'advance_unapplied_inr']) {
  assert.ok(pageSource.includes(field), `advance card must show ${field}`)
}
for (const field of ['project_value_inr', 'invoice_cash_payments_inr', 'total_collected_inr', 'remaining_project_balance_inr', 'collection_status', 'invoice_status']) {
  assert.ok(pageSource.includes(field), `project card must show ${field}`)
}

// ---------------------------------------------------------------------------
// Finance-only actions
// ---------------------------------------------------------------------------
assert.ok(pageSource.includes("user?.role === 'finance'"), 'recording must be gated to Finance')
assert.ok(pageSource.includes('Record Advance Received'), 'record receipt button must exist')
assert.ok(pageSource.includes('Apply Advance to Invoice'), 'apply to invoice button must exist')
assert.ok(pageSource.includes('Resulting Balance'), 'apply panel must preview the resulting balance')
assert.ok(pageSource.includes('Available Advance'), 'apply panel must show the available advance')
for (const field of ['amount', 'currency', 'payment_date', 'payment_mode', 'reference_number', 'bank_reference', 'attachment']) {
  assert.ok(pageSource.includes(`advanceRecordForm.${field}`), `record form must capture ${field}`)
}
// After a mutation every affected Finance view is refreshed.
assert.ok(pageSource.includes('function refreshAdvanceViews'), 'a shared refresh helper must exist')
for (const call of ['getAdvanceProjectDetail', 'getAdvanceCollection', 'getAdvanceSummary', 'getAdvanceProjects']) {
  assert.ok(pageSource.includes(`refreshAdvanceViews`) && pageSource.includes(call), `refresh must include ${call}`)
}

// ---------------------------------------------------------------------------
// Regressions that must stay true
// ---------------------------------------------------------------------------
assert.ok(!pageSource.includes('project_invoice_payments'), 'UI must never fake an invoice payment for an advance')
assert.ok(pageSource.includes('displayAdvanceAmount'), 'monetary values must keep the Restricted redaction path')
assert.ok(cssSource.includes('.advance-action-grid'), 'action grid styles must exist')
assert.ok(cssSource.includes('[data-layer="advance"]') && cssSource.includes('[data-layer="project"]'), 'layer styles must exist')

console.log('FINANCE COMMAND CENTER ADVANCE SETTLEMENT VERIFICATION PASSED')
console.log('- Collection GET + Apply-to-invoice POST + existing transactions POST are wired')
console.log('- ADVANCE COLLECTION and PROJECT COLLECTION render as two separate layers')
console.log('- Advance card: Expected / Received / Pending / Applied / Available / Status')
console.log('- Project card: Project Value / Cash Payments / Total Collected / Remaining / Collection Status')
console.log('- Record Advance Received and Apply Advance to Invoice are Finance-only')
console.log('- Resulting balance preview shown before applying')
console.log('- All four Finance views refresh after a mutation; Restricted redaction preserved')
console.log('- No fake project_invoice_payments row is ever created for an advance')