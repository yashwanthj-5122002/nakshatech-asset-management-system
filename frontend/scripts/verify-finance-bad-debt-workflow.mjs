import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'

// Static structural guard only. Backend pytest + browser UAT are still required.
const root = process.cwd()
const read = relative => fs.readFileSync(path.join(root, relative), 'utf8')

const billing = read('src/features/finance/pages/FinanceBillingPage.tsx')
const management = read('src/features/operations/pages/ManagementProject360Page.tsx')
const lifecycle = read('../backend/app/modules/operations/lifecycle_service.py')
const router = read('../backend/app/modules/operations/lifecycle_router.py')

// Finance can escalate a genuinely overdue collectible invoice, while normal
// collection remains available before Management approves a write-off.
assert.ok(billing.includes('Propose Bad Debt to Management'), 'Finance must expose Propose Bad Debt')
assert.ok(billing.includes("invoice.status === 'PAYMENT_OVERDUE'"), 'Bad Debt proposal must be overdue-gated')
assert.ok(billing.includes('invoice.collectible_balance > 0'), 'proposal/payment must use collectible balance')
assert.ok(billing.includes("canProposeBadDebt && (!badDebt || badDebt.status === 'REJECTED')"),
  'Management rejection must allow Finance to submit a corrected proposal later')

// Existing Bad Debt history must remain visible after approval/recovery even
// when the normal payment status is no longer PAYMENT_OVERDUE.
assert.ok(billing.includes('const showBadDebtSection = Boolean(badDebt) || canProposeBadDebt'),
  'existing Bad Debt state must remain visible after overdue state changes')
assert.ok(billing.includes("label: 'Bad Debt Proposed'"), 'proposed status badge missing')
assert.ok(billing.includes("label: 'Bad Debt / Written Off'"), 'approved/write-off badge missing')
assert.ok(billing.includes("label: 'Bad Debt Recovered'"), 'recovered status badge missing')
assert.ok(billing.includes('operations-status-stack'), 'invoice must show Bad Debt disposition alongside payment status')

// Once Management approved a write-off, an ordinary Record Payment may only
// collect the non-written-off balance. Written-off money must use Recovery so
// recovered_amount/audit history stay correct.
assert.ok(billing.includes('max={invoice.collectible_balance}'), 'Record Payment must be capped at collectible balance')
assert.ok(billing.includes('Record Recovery'), 'approved Bad Debt must expose the Recovery path')
assert.ok(billing.includes('/bad-debt/recovery'), 'Recovery must call the dedicated backend endpoint')
assert.ok(lifecycle.includes('_allow_bad_debt_recovery: bool = False'), 'backend direct-payment/recovery separation guard missing')
assert.ok(lifecycle.includes('Payment exceeds the collectible balance while Management-approved Bad Debt exists'),
  'backend must reject normal payments that consume the written-off portion')
assert.ok(lifecycle.includes('_allow_bad_debt_recovery=True'), 'Recovery must deliberately reuse normal cash payment architecture')

// Partial write-offs must not make a project closure-ready while collectible
// cash remains. Partial recoveries of a fully covered write-off must restore
// closure eligibility after the payment transition.
assert.ok(lifecycle.includes('and _approved_bad_debt_remaining(db, invoice.id) >= _invoice_cash_balance(db, invoice)'),
  'Bad Debt closure eligibility must require full coverage of current cash balance')
assert.ok(lifecycle.includes('restore Finance Closure Pending eligibility'),
  'partial recovery must re-evaluate Finance Closure Pending eligibility')

// Management remains the decision maker; Finance remains proposal/recovery.
assert.ok(router.includes('/invoices/{invoice_id}/bad-debt/decision'), 'Bad Debt decision endpoint missing')
assert.ok(management.includes('/bad-debt/decision'), 'Management Project 360 must expose the decision action')
assert.ok(management.includes('Confirm Bad Debt') && management.includes('Reject Proposal'),
  'Management must have approve/reject controls')

console.log('FINANCE BAD DEBT WORKFLOW VERIFICATION PASSED')
console.log('- overdue Finance proposal + re-proposal after rejection are structurally present')
console.log('- Bad Debt status remains visible after approval/recovery')
console.log('- ordinary payment is capped to collectible balance; written-off cash uses Recovery')
console.log('- partial write-off/recovery closure eligibility is guarded on the backend')
console.log('- Management remains the Bad Debt approval/rejection authority')
