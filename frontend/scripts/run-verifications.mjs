import { spawnSync } from 'node:child_process'

const checks = [
  'verify-finance-command-center-partial-payment',
  'verify-finance-command-center-advance-alerts',
  'verify-finance-command-center-advance-settlement',
  'verify-finance-command-center-invoice-document',
  'verify-finance-bad-debt-workflow',
  'verify-sales-revenue-kpi-drilldown',
  'verify-finance-generate-invoice-standalone',
  'verify-notification-popup',
  'verify-critical-action-visibility',
  'verify-bd-client-feedback-action-center',
  'verify-india-dates',
  'verify-dashboard-drawer-layout-focus',
  'verify-dashboard-drawer-visual-toggle',
  'verify-dashboard-drawer-visuals',
  'verify-dashboard-drilldown',
  'verify-dashboard-visual-analytics',
  'verify-reporting-month-race-fix',
]
const failures = []
for (const name of checks) {
  const result = spawnSync(process.execPath, [`scripts/${name}.mjs`], { stdio: 'inherit' })
  if (result.error || result.status !== 0) failures.push(name)
}
if (failures.length) {
  console.error('Failed verification scripts:', failures.join(', '))
  process.exitCode = 1
}
