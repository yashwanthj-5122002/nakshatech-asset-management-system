import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import ts from 'typescript'

const root = process.cwd()
const helperPath = path.join(root, 'src/features/finance/pages/financeCommandCenterAlerts.ts')
const commandCenterPath = path.join(root, 'src/features/finance/pages/FinanceCommandCenter.tsx')
const apiPath = path.join(root, 'src/features/finance/advancePaymentApi.ts')

const helperSource = fs.readFileSync(helperPath, 'utf8')
const commandCenterSource = fs.readFileSync(commandCenterPath, 'utf8')
const apiSource = fs.readFileSync(apiPath, 'utf8')
const compiled = ts.transpileModule(helperSource, {
  compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 },
  fileName: helperPath,
}).outputText
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
const {
  ADVANCE_HIGH_VALUE_THRESHOLD_INR,
  buildAdvanceAlerts,
  canViewAdvanceAlerts,
  formatAdvanceAlertDate,
  summarizeAdvanceAlerts,
} = await import(moduleUrl)

// ---------------------------------------------------------------------------
// Source contract: section placement and backend refresh wiring
// ---------------------------------------------------------------------------
assert.ok(
  commandCenterSource.includes('aria-label="Advance Alerts"'),
  'Command Center must render the Advance Alerts section',
)
const kpiGridIndex = commandCenterSource.indexOf('aria-label="Advance Payment KPI summary"')
const alertsIndex = commandCenterSource.indexOf('aria-label="Advance Alerts"')
const visualizationIndex = commandCenterSource.indexOf('aria-label="Advance Payment visualizations"')
assert.ok(kpiGridIndex !== -1 && alertsIndex !== -1 && visualizationIndex !== -1, 'All three sections must exist')
assert.ok(
  kpiGridIndex < alertsIndex && alertsIndex < visualizationIndex,
  'Advance Alerts must sit after the Advance KPI cards and before the visualization section',
)
assert.ok(
  commandCenterSource.includes('refreshAdvanceNotifications()'),
  'Command Center must call the Phase 4 refresh-notifications API',
)
assert.ok(
  apiSource.includes("'/finance/advance-payments/refresh-notifications'"),
  'The refresh API must POST /finance/advance-payments/refresh-notifications',
)
assert.ok(
  apiSource.includes('export function refreshAdvanceNotifications'),
  'advancePaymentApi must export refreshAdvanceNotifications',
)
assert.ok(
  commandCenterSource.includes('buildAdvanceAlerts('),
  'Alert rows must come from the shared buildAdvanceAlerts helper',
)
assert.ok(
  commandCenterSource.includes('Due Today') && commandCenterSource.includes('Pending Follow-ups'),
  'Alert summary must show Due Today, Overdue and Pending Follow-ups counts',
)
assert.ok(
  commandCenterSource.includes('Restricted'),
  'PM/restricted rows must fall back to the Restricted label instead of amounts',
)

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------
const TODAY = '2026-10-15'

function advanceFixture(overrides = {}) {
  return {
    project_id: 1,
    project_name: 'GIS4456',
    client: 'ABC',
    department: 'LiDAR',
    department_code: 'lidar',
    bd_person: 'BD Owner',
    project_manager: null,
    project_value: 500000,
    advance_required: true,
    advance_amount: 500000,
    received_amount: 0,
    pending_amount: 500000,
    adjusted_amount: 0,
    advance_currency: 'INR',
    expected_date: '2026-10-15',
    final_date: '2026-10-20',
    status: 'pending',
    status_label: 'Pending',
    financial_amounts_visible: true,
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Finance sees all alert kinds
// ---------------------------------------------------------------------------
const financeRows = [
  advanceFixture({ project_id: 1, project_name: 'DueProject' }), // due today
  advanceFixture({
    project_id: 2,
    project_name: 'OverdueProject',
    status: 'overdue',
    status_label: 'Overdue',
    expected_date: '2026-10-05',
    final_date: '2026-10-10',
  }),
  advanceFixture({
    project_id: 3,
    project_name: 'PartialProject',
    status: 'partial_received',
    status_label: 'Partial Received',
    advance_amount: 500000,
    received_amount: 200000,
    pending_amount: 300000,
    expected_date: '2026-12-01',
    final_date: '2026-12-10',
  }),
  advanceFixture({
    project_id: 4,
    project_name: 'HighValueProject',
    advance_amount: 2500000,
    pending_amount: 2500000,
    expected_date: '2026-12-01',
    final_date: '2026-12-10',
  }),
]
const financeAlerts = buildAdvanceAlerts(financeRows, { role: 'finance', today: TODAY })
const financeCounts = summarizeAdvanceAlerts(financeAlerts)
assert.equal(financeCounts.total, 4, 'Finance must see every alert')
assert.equal(financeCounts.dueToday, 1)
assert.equal(financeCounts.overdue, 1)
assert.equal(financeCounts.pendingFollowUps, 1)
assert.equal(financeCounts.highValue, 1)

const overdueAlert = financeAlerts.find(alert => alert.project_id === 2)
assert.equal(overdueAlert.kind, 'overdue')
assert.equal(overdueAlert.days_overdue, 5, 'Overdue days = today - final date')
assert.equal(formatAdvanceAlertDate(overdueAlert.due_date), '10-10-2026')
assert.equal(overdueAlert.pending_amount, 500000)

// ---------------------------------------------------------------------------
// Management: only high-value alerts
// ---------------------------------------------------------------------------
const managementAlerts = buildAdvanceAlerts(financeRows, { role: 'management', today: TODAY })
assert.equal(managementAlerts.length, 1, 'Management must only receive high-value alerts')
assert.equal(managementAlerts[0].kind, 'high_value')
assert.equal(managementAlerts[0].project_id, 4)


// ---------------------------------------------------------------------------
// BD: only own-project rows (rows arrive pre-scoped by the backend API)
// ---------------------------------------------------------------------------
assert.equal(canViewAdvanceAlerts('bd'), true, 'BD keeps read access to own-project alerts')
const bdOwnedOnly = financeRows.filter(row => row.project_id !== 4)
const bdAlerts = buildAdvanceAlerts(bdOwnedOnly, { role: 'bd', today: TODAY })
assert.equal(bdAlerts.length, 3, 'BD sees alerts for own projects only (server-scoped rows)')
assert.ok(bdAlerts.every(alert => alert.project_id !== 4))

// ---------------------------------------------------------------------------
// PM: restricted view - no amount visibility, status/dates only
// ---------------------------------------------------------------------------
assert.equal(canViewAdvanceAlerts('lidar'), true)
const pmRows = financeRows.map(row => ({
  ...row,
  advance_amount: null,
  received_amount: null,
  pending_amount: null,
  financial_amounts_visible: false,
}))
const pmAlerts = buildAdvanceAlerts(pmRows, { role: 'lidar', today: TODAY })
const pmDue = pmAlerts.find(alert => alert.project_id === 1)
assert.equal(pmDue.amounts_visible, false)
assert.equal(pmDue.pending_amount, null, 'PM rows must never carry amounts')
assert.equal(pmDue.status_label, 'Pending', 'PM still sees status labels')

// ---------------------------------------------------------------------------
// Production/QC/QA/other operational roles: no access
// ---------------------------------------------------------------------------
for (const role of ['employee', 'production', 'qc', 'qa', 'it', 'hr']) {
  assert.equal(canViewAdvanceAlerts(role), false, `${role} must not access Advance Alerts`)
  assert.equal(buildAdvanceAlerts(financeRows, { role, today: TODAY }).length, 0)
}
assert.equal(canViewAdvanceAlerts(null), false)
assert.equal(canViewAdvanceAlerts(undefined), false)

// ---------------------------------------------------------------------------
// Threshold + terminal statuses
// ---------------------------------------------------------------------------
assert.equal(ADVANCE_HIGH_VALUE_THRESHOLD_INR, 1000000, 'Default threshold is Rs.10,00,000')
const atThreshold = buildAdvanceAlerts([
  advanceFixture({ project_id: 9, advance_amount: 1000000, pending_amount: 1000000, expected_date: '2026-10-15', final_date: '2026-10-30' }),
], { role: 'finance', today: TODAY })
assert.equal(
  atThreshold.find(alert => alert.project_id === 9)?.kind,
  'due',
  'Exactly at threshold is not high-value, so the due rule labels the row',
)
const aboveThreshold = buildAdvanceAlerts([
  advanceFixture({ project_id: 10, advance_amount: 1000001, pending_amount: 1000001, expected_date: '2026-10-15', final_date: '2026-10-30' }),
], { role: 'finance', today: TODAY })
assert.equal(aboveThreshold.find(alert => alert.project_id === 10)?.kind, 'due', 'Overdue/due outranks high-value')
const highValueOnlyRow = buildAdvanceAlerts([
  advanceFixture({ project_id: 11, advance_amount: 1500000, pending_amount: 1500000, expected_date: '2026-12-01', final_date: '2026-12-10' }),
], { role: 'finance', today: TODAY })
assert.equal(highValueOnlyRow[0]?.kind, 'high_value', 'Above threshold with no due condition is high-value')

const terminal = ['not_required', 'received', 'adjusted', 'closed']
for (const status of terminal) {
  const alerts = buildAdvanceAlerts([
    advanceFixture({ status, status_label: status, received_amount: 100000, pending_amount: 400000 }),
  ], { role: 'finance', today: TODAY })
  assert.equal(alerts.length, 0, `Terminal status ${status} must not alert`)
}

console.log('FINANCE COMMAND CENTER ADVANCE ALERTS VERIFICATION PASSED')
console.log('- Section placement: Advance KPI cards -> Advance Alerts -> advance visualizations')
console.log('- Finance sees due/overdue/partial/high-value alerts (4 rows)')
console.log('- Management sees only high-value alerts (1 row)')
console.log('- BD sees only own-project alerts (server-scoped rows)')
console.log('- PM rows are amount-redacted (Restricted) with status preserved')
console.log('- Production/QC/QA/operational roles: no access')
console.log('- Terminal statuses never alert; default threshold Rs.10,00,000')
