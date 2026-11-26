import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import ts from 'typescript'

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

// Execute the page's actual filtering/card/drill-down callbacks. In particular,
// closed write-offs must survive selection without returning to Open Sales.
const source = ts.createSourceFile('SalesRevenuePage.tsx', page, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
function findNode(predicate) {
  let result
  function visit(node) {
    if (!result && predicate(node)) result = node
    if (!result) ts.forEachChild(node, visit)
  }
  visit(source)
  assert.ok(result, 'required Sales KPI expression must exist')
  return result
}
function evaluate(code, context, expression = false) {
  const output = ts.transpileModule(expression ? `const result = ${code};` : code, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
  }).outputText
  return new Function(...Object.keys(context), `${output}\n${expression ? 'return result;' : ''}`)(...Object.values(context))
}
function pageFunction(name, context = {}) {
  const node = findNode(n => ts.isFunctionDeclaration(n) && n.name?.text === name)
  const output = ts.transpileModule(node.getText(source), { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText
  return new Function(...Object.keys(context), `${output}; return ${name};`)(...Object.values(context))
}
const helperOutput = ts.transpileModule(helper, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText
const { aggregateFinanceCommandCenterKpis } = await import(`data:text/javascript;base64,${Buffer.from(helperOutput).toString('base64')}`)
function pageMemo(name, context) {
  const node = findNode(n => ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === name)
  return evaluate(node.initializer.getText(source), context, true)
}
function projectRow(code, { total, cash, debt, closed }) {
  return {
    project_id: code, project_code: code, project_name: code,
    department_code: 'ortho', client_name: code === 'ZYX123' ? 'XYZ' : code,
    bd_name: 'BD Owner', project_manager_name: 'PM', currency: 'INR',
    sales_date: '2026-10-14', projected_payment_date: '2026-10-15',
    sales_visible: !closed, sales_status: closed ? 'Moved to Revenue' : 'Overdue',
    bad_debt_inr: debt, cash_received_inr: cash, closed_revenue_inr: closed ? cash : 0,
    open_sales_inr: closed ? 0 : total, received_against_open_sales_inr: closed ? 0 : cash,
    outstanding_inr: Math.max(Math.round((total-cash-debt)*100)/100, 0),
    unbilled_open_sales_inr: 0, partial_payment_balance_inr: 0,
    invoices: [{ status: closed ? 'INVOICE_CLOSED' : 'PAYMENT_OVERDUE', paid_amount: cash,
      total_amount: total, total_inr: total, balance_inr: total-cash,
      open_sales_category: closed ? null : 'payment_pending_inr' }],
  }
}
function displayedKpis(projects, filters = {}) {
  const context = {
    allProjects: projects, range: ['2026-10-01','2026-10-31'],
    department: 'all', client: 'all', project: 'all', bd: 'all', pm: 'all', currency: 'all',
    statusFilter: 'all', salesDateBasis: 'projected', ...filters,
    useMemo: callback => callback(), aggregateFinanceCommandCenterKpis,
    kpiDrilldown: 'bad_debt', revenueRows: [], revenueKpis: {}, revenueByProject: [],
  }
  context.dateInside = pageFunction('dateInside')
  context.dimensionsMatch = pageFunction('dimensionsMatch', context)
  context.roundMoney = pageFunction('roundMoney')
  context.sumMoney = pageFunction('sumMoney', context)
  context.salesKpiAmount = pageFunction('salesKpiAmount', context)
  for (const name of ['filteredProjects','salesRows','salesKpis','kpiDrilldownData']) context[name] = pageMemo(name, context)
  assert.equal(context.salesKpis.badDebt, context.kpiDrilldownData.traced, 'card and drill-down must reconcile')
  return context
}
export { displayedKpis }
const gorilla = projectRow('GORILLA', { total: 80788.70, cash: 0, debt: 80788.70, closed: false })
const zyx = projectRow('ZYX123', { total: 24148.70, cash: 20000, debt: 4148.70, closed: true })
let actual = displayedKpis([gorilla, zyx])
assert.equal(actual.salesKpis.badDebt, 84937.40)
assert.deepEqual(actual.kpiDrilldownData.rows.map(item => item.row.project_code), ['GORILLA','ZYX123'])
assert.deepEqual(actual.salesRows.map(row => row.project_code), ['GORILLA'], 'closed write-off must stay out of the Sales register')
const receivedExpression = findNode(n => ts.isConditionalExpression(n) && n.whenTrue.getText(source) === 'item.row.cash_received_inr')
assert.equal(evaluate(receivedExpression.getText(source), { kpiDrilldown: 'bad_debt', item: { row: zyx } }, true), 20000)
assert.equal(zyx.outstanding_inr, 0)
assert.equal(displayedKpis([gorilla, { ...zyx, sales_visible: true, sales_status: 'Overdue' }]).salesKpis.badDebt, 84937.40, 'closure cannot change Bad Debt')
const recovered = { ...zyx, bad_debt_inr: 3148.70, cash_received_inr: 21000, closed_revenue_inr: 21000 }
assert.equal(displayedKpis([gorilla, recovered]).salesKpis.badDebt, 83937.40)
for (const code of ['FULLY-PAID','PENDING','REJECTED']) {
  const row = projectRow(code, { total: 10000, cash: code === 'FULLY-PAID' ? 10000 : 0, debt: 0, closed: code === 'FULLY-PAID' })
  assert.equal(displayedKpis([row]).salesKpis.badDebt, 0)
  assert.equal(displayedKpis([row]).kpiDrilldownData.rows.length, 0)
}
const zeroCash = projectRow('ZERO-CASH', { total: 50000, cash: 0, debt: 50000, closed: true })
assert.equal(displayedKpis([zeroCash]).salesKpis.badDebt, 50000)
assert.equal(displayedKpis([zeroCash]).salesRows.length, 0)
assert.equal(displayedKpis([gorilla,zyx], { client: 'XYZ' }).salesKpis.badDebt, 4148.70)
assert.equal(displayedKpis([gorilla,zyx], { project: 'ZYX123' }).salesKpis.badDebt, 4148.70)
assert.equal(displayedKpis([gorilla,zyx], { department: 'lidar' }).salesKpis.badDebt, 0)
assert.equal(displayedKpis([gorilla,zyx], { range: ['2026-11-01','2026-11-30'] }).salesKpis.badDebt, 0)
assert.equal(displayedKpis([gorilla,zyx], { statusFilter: 'Moved to Revenue' }).salesKpis.badDebt, 4148.70)
assert.equal(displayedKpis([gorilla,zyx], { range: ['2026-10-14','2026-10-14'], salesDateBasis: 'booked' }).salesKpis.badDebt, 84937.40)

console.log('SALES / REVENUE KPI DRILL-DOWN VERIFICATION PASSED')
console.log('- Sales and Revenue reuse the same canonical KPI calculator as Finance Command Center')
console.log('- all Sales/Revenue KPI cards open exact contributing-record drill-downs')
console.log('- active filters are preserved and card-vs-row reconciliation is visible')
console.log('- project detail retains invoice/payment trace including partial payments and Bad Debt')
console.log('- Finance Command Center UI file is not required to change for this feature')
console.log('- Closed write-offs remain in the Bad Debt card and drill-down, with backend cash receipts')
console.log('- Recovery, zero-cash write-off, excluded pending/rejected debt and active filters reconcile')
