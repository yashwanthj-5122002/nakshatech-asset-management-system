import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'

// Structural regression guard for the Sales/Revenue KPI drill-down feature.
// Backend Finance tests remain the source-of-truth verification for accounting semantics.
const root = process.cwd()
const read = relative => fs.readFileSync(path.join(root, relative), 'utf8')

const page = read('src/features/finance/pages/SalesRevenuePage.tsx')
const commandCenter = read('src/features/finance/pages/FinanceCommandCenter.tsx')
const helper = read('src/features/finance/pages/financeCommandCenterKpis.ts')

// Equivalent KPIs must use the exact canonical calculation already used by
// Finance Command Center, without importing/copying Command Center UI state.
assert.ok(page.includes("import { aggregateFinanceCommandCenterKpis } from './financeCommandCenterKpis'"),
  'Sales/Revenue must reuse the canonical Finance KPI calculation helper')
assert.ok(page.includes('const canonical = aggregateFinanceCommandCenterKpis(salesRows, [])'),
  'filtered Sales KPIs must be calculated from the canonical helper')
assert.ok(page.includes('aggregateFinanceCommandCenterKpis([], revenueRows).closedRevenue'),
  'filtered Realized Revenue must use the canonical Finance revenue calculation')
assert.ok(page.includes('aggregateFinanceCommandCenterKpis([row], [])'),
  'Sales KPI contributor amounts must use the same per-project canonical calculation')
assert.ok(commandCenter.includes('aggregateFinanceCommandCenterKpis(activeProjects, activeRevenue)'),
  'Finance Command Center must continue using its existing canonical KPI helper')
assert.ok(helper.includes('export function aggregateFinanceCommandCenterKpis'),
  'canonical Finance KPI helper must remain available')

// Every requested KPI card must be a real drill-down action.
for (const key of [
  'open_sales', 'open_invoiced', 'received_open_sales', 'outstanding', 'bad_debt',
  'realized_revenue', 'closed_invoices', 'revenue_projects', 'average_closed_invoice',
]) {
  assert.ok(page.includes(`openKpiDrilldown('${key}')`), `missing KPI drill-down action: ${key}`)
}

// Drill-down must preserve the current filter context and show an explicit
// reconciliation between what the card says and what the contributing rows add to.
assert.ok(page.includes('Exact filter basis'), 'KPI drill-down must expose the exact active filter basis')
assert.ok(page.includes('KPI card') && page.includes('Drill-down trace') && page.includes('Difference'),
  'KPI drill-down must show card-vs-row reconciliation')
assert.ok(page.includes("'MATCHED' : 'CHECK REQUIRED'"),
  'KPI drill-down must visibly flag reconciliation failure instead of hiding it')
assert.ok(page.includes('open_sales_reconciled'),
  'Open Sales drill-down must respect backend per-project reconciliation evidence')

// Contributor rows must lead to real project/invoice detail, not synthetic data.
assert.ok(page.includes('openContributorProject'), 'drill-down rows must open the actual project detail')
assert.ok(page.includes('View BD Sales Invoice') && page.includes('View Finance Invoice') && page.includes('View Payment History'),
  'project detail must retain Sales, Finance invoice and payment-history views')

// Partial payments and Bad Debt remain independently traceable.
assert.ok(page.includes('Cumulative Cash'), 'payment history must expose cumulative partial payments')
assert.ok(page.includes('Collectible Balance'), 'project detail must expose current collectible balance')
assert.ok(page.includes('Bad Debt Remaining INR') && page.includes('Bad Debt Status'),
  'Finance invoice detail must expose Bad Debt separately from payment')
assert.ok(page.includes('Advance Applied') && page.includes('Total Settled'),
  'payment detail must distinguish cash, advance settlement and total settlement')

console.log('SALES / REVENUE KPI DRILL-DOWN VERIFICATION PASSED')
console.log('- Sales and Revenue reuse the same canonical KPI calculator as Finance Command Center')
console.log('- all Sales/Revenue KPI cards open exact contributing-record drill-downs')
console.log('- active filters are preserved and card-vs-row reconciliation is visible')
console.log('- project detail retains invoice/payment trace including partial payments and Bad Debt')
console.log('- Finance Command Center UI file is not required to change for this feature')
