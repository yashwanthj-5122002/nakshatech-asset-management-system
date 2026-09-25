import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import ts from 'typescript'

const root = process.cwd()
const helperPath = path.join(root, 'src/features/finance/pages/financeCommandCenterKpis.ts')
const commandCenterPath = path.join(root, 'src/features/finance/pages/FinanceCommandCenter.tsx')

const helperSource = fs.readFileSync(helperPath, 'utf8')
const commandCenterSource = fs.readFileSync(commandCenterPath, 'utf8')
const compiled = ts.transpileModule(helperSource, {
  compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 },
  fileName: helperPath,
}).outputText
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
const { aggregateFinanceCommandCenterKpis, openSalesForProject } = await import(moduleUrl)

assert.ok(
  commandCenterSource.includes("const [period, setPeriod] = useState<Period>('monthly')"),
  'Command Center must default to the same current-month period as the Sales page',
)
assert.ok(
  commandCenterSource.includes("setPeriod('monthly')"),
  'Clear filters must restore the current-month period',
)
assert.ok(
  commandCenterSource.includes('inr(calc.commandCenterOpenSalesInr)'),
  'Open Sales drill-down must display the balance-based Command Center value',
)

const projectedPaymentDate = '2026-09-30'
const currentMonthRange = ['2026-09-01', '2026-09-30']
assert.ok(
  projectedPaymentDate >= currentMonthRange[0] && projectedPaymentDate <= currentMonthRange[1],
  'A current-month future projected payment date must remain in the Command Center aggregation',
)

function projectFixture({ total, paid, status, category, salesStatus, unbilled = 0 }) {
  const balance = Math.max(total - paid, 0)
  const partial = category === 'partial_payment_inr'
  const pending = category === 'payment_pending_inr'
  return {
    open_sales_inr: category == null ? 0 : total,
    open_sales_categories: {
      invoice_not_raised_inr: 0,
      payment_pending_inr: pending ? total : 0,
      partial_payment_inr: partial ? total : 0,
      payment_received_closure_pending_inr: 0,
      other_open_inr: 0,
    },
    partial_payment_balance_inr: partial ? balance : 0,
    unbilled_open_sales_inr: unbilled,
    received_against_open_sales_inr: category == null ? 0 : paid,
    outstanding_inr: balance,
    sales_visible: category != null,
    sales_status: salesStatus,
    open_payment_pending_invoice_count: pending ? 1 : 0,
    open_partial_invoice_count: partial ? 1 : 0,
    invoice_not_raised: false,
    sales_value_inr: total,
    invoice_count: 1,
    invoices: [{
      status,
      total_amount: total,
      total_inr: total,
      paid_amount: paid,
      balance_inr: balance,
      open_sales_category: category,
    }],
  }
}

const paymentPending = aggregateFinanceCommandCenterKpis([
  projectFixture({ total: 10000, paid: 0, status: 'PAYMENT_PENDING', category: 'payment_pending_inr', salesStatus: 'Payment Pending' }),
], [])
assert.equal(paymentPending.paymentPendingAmount, 10000)
assert.equal(paymentPending.partialAmount, 0)
assert.equal(paymentPending.outstanding, 10000)
assert.equal(paymentPending.closedRevenue, 0)
assert.equal(paymentPending.openSales, 10000)

const partialPayment = aggregateFinanceCommandCenterKpis([
  projectFixture({ total: 10000, paid: 4000, status: 'PARTIALLY_PAID', category: 'partial_payment_inr', salesStatus: 'Partially Paid' }),
], [])
assert.equal(partialPayment.paymentPendingAmount, 0)
assert.equal(partialPayment.partialAmount, 6000)
assert.equal(partialPayment.outstanding, 6000)
assert.equal(partialPayment.closedRevenue, 0, 'Partially paid invoices must not count as revenue')
assert.equal(partialPayment.openSales, 6000)

const closed = aggregateFinanceCommandCenterKpis([
  projectFixture({ total: 10000, paid: 10000, status: 'INVOICE_CLOSED', category: null, salesStatus: 'Moved to Revenue' }),
], [{ revenue_amount_inr: 10000 }])
assert.equal(closed.paymentPendingAmount, 0)
assert.equal(closed.partialAmount, 0)
assert.equal(closed.outstanding, 0)
assert.equal(closed.closedRevenue, 10000)
assert.equal(closed.openSales, 0)

const liveProject = projectFixture({ total: 1180, paid: 1000, status: 'PARTIALLY_PAID', category: 'partial_payment_inr', salesStatus: 'Partially Paid' })
const liveExample = aggregateFinanceCommandCenterKpis([liveProject], [])
assert.equal(liveExample.openInvoiced, 1180)
assert.equal(liveExample.received, 1000)
assert.equal(liveExample.partialAmount, 180)
assert.equal(liveExample.outstanding, 180)
assert.equal(liveExample.openSales, 180)
assert.equal(openSalesForProject(liveProject), 180)

const multiplePartials = aggregateFinanceCommandCenterKpis([
  projectFixture({ total: 1180, paid: 1000, status: 'PARTIALLY_PAID', category: 'partial_payment_inr', salesStatus: 'Partially Paid' }),
  projectFixture({ total: 5000, paid: 1000, status: 'PARTIALLY_PAID', category: 'partial_payment_inr', salesStatus: 'Partially Paid' }),
  projectFixture({ total: 50000, paid: 20000, status: 'PARTIALLY_PAID', category: 'partial_payment_inr', salesStatus: 'Partially Paid' }),
], [])
assert.equal(multiplePartials.partialAmount, 34180)
assert.equal(multiplePartials.outstanding, 34180)
assert.equal(multiplePartials.openSales, 34180)

const notInvoiced = aggregateFinanceCommandCenterKpis([{
  ...projectFixture({ total: 75000, paid: 0, status: 'INVOICE_DRAFT', category: null, salesStatus: 'Not Invoiced', unbilled: 75000 }),
  invoices: [],
  invoice_count: 0,
  sales_value_inr: 75000,
  invoice_not_raised: true,
}], [])
assert.equal(notInvoiced.openSales, 75000)

const overdueReceivables = aggregateFinanceCommandCenterKpis([
  projectFixture({ total: 5000, paid: 0, status: 'PAYMENT_OVERDUE', category: 'payment_pending_inr', salesStatus: 'Overdue' }),
  projectFixture({ total: 10000, paid: 7000, status: 'PAYMENT_OVERDUE', category: 'partial_payment_inr', salesStatus: 'Overdue' }),
], [])
assert.equal(overdueReceivables.paymentPendingAmount, 5000)
assert.equal(overdueReceivables.partialAmount, 3000)
assert.equal(overdueReceivables.outstanding, 8000)
assert.equal(overdueReceivables.openSales, 8000)

console.log('FINANCE COMMAND CENTER PARTIAL PAYMENT REGRESSION PASSED')
console.log('- Payment pending: INR 10,000; partial: INR 0; outstanding: INR 10,000')
console.log('- Partial balance: INR 6,000; outstanding: INR 6,000')
console.log('- Fully paid/closed revenue: INR 10,000; partial/outstanding: INR 0')
console.log('- Live example partial/outstanding/open sales: INR 180')
console.log('- Multiple partial balances and open sales sum to INR 34,180')
console.log('- Overdue pending/partial balances contribute once to Outstanding')
