import { BarChart3, CalendarDays, ChevronDown, ChevronRight, CircleDollarSign, Eye, EyeOff, FileText, IndianRupee, Lock, RefreshCcw, Target, TrendingUp, WalletCards, X } from 'lucide-react'
import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch } from '../../../lib/api'
import { useAuth } from '../../../context/AuthContext'
import { CommandCenterHero, useNkReveal } from '../../../components/CommandCenterHero'
import { departmentCodeForRole, isTechnicalProjectManager } from '../../../lib/roles'
import { aggregateFinanceCommandCenterKpis, openSalesCategoriesForProject, openSalesForProject } from './financeCommandCenterKpis'
import '../finance-expenses.css'
import './sales-revenue.css'

interface PaymentRow {
  id: number
  payment_reference: string
  payment_date: string
  amount: number
  currency: string
  amount_inr: number
  payment_mode: string
  comments: string | null
}

interface InvoiceRow {
  id: number
  invoice_number: string
  status: string
  invoice_date: string
  due_date: string
  currency: string
  base_amount: number
  tax_amount: number
  total_amount: number
  total_inr: number
  paid_amount: number
  paid_inr: number
  balance: number
  balance_inr: number
  raised_at: string | null
  closed_at: string | null
  notes: string | null
  open_sales_category: string | null
  payments: PaymentRow[]
}

interface BDSalesInvoice {
  reference: string | null
  revision_no: number | null
  status: string | null
  is_locked: boolean
  date: string
  currency: string
  amount: number
  amount_inr: number
  payment_terms: string | null
  po_wo_reference: string | null
  billing_type: string | null
  expected_billing_milestone: string | null
  projected_payment_date: string | null
  notes: string | null
}

interface SalesProject {
  project_id: number
  project_code: string
  project_name: string
  client_code: string | null
  client_name: string
  bd_name: string
  department_code: string
  department_label: string
  project_manager_name: string
  currency: string
  sales_date: string
  projected_payment_date: string | null
  completion_date?: string | null
  project_created_at?: string | null
  project_status?: string | null
  sales_value: number
  sales_value_inr: number
  open_sales_inr: number
  open_sales_categories: OpenSalesCategories
  open_sales_reconciliation_difference_inr: number
  open_sales_reconciled: boolean
  unbilled_open_sales_inr: number
  partial_payment_balance_inr: number
  open_payment_pending_invoice_count: number
  open_partial_invoice_count: number
  received_against_open_sales_inr: number
  outstanding_inr: number
  closed_revenue_inr: number
  sales_status: string
  invoice_not_raised: boolean
  sales_visible: boolean
  revenue_visible: boolean
  bd_sales_invoice: BDSalesInvoice
  invoice_count: number
  open_invoice_count: number
  closed_invoice_count: number
  invoices: InvoiceRow[]
}

interface OpenSalesCategories {
  invoice_not_raised_inr: number
  payment_pending_inr: number
  partial_payment_inr: number
  payment_received_closure_pending_inr: number
  other_open_inr: number
}

interface KpiSummary {
  open_sales_inr: number
  categories: OpenSalesCategories
  categories_sum_inr: number
  reconciliation_difference_inr: number
  reconciled: boolean
  realized_revenue_inr: number
  outstanding_inr: number
  received_against_open_sales_inr: number
  open_invoice_total_inr: number
  open_invoice_balance_inr: number
  unbilled_open_sales_inr: number
  counts: {
    open_sales_projects: number
    revenue_events: number
    partial_projects: number
    overdue_projects: number
    payment_pending_invoices: number
    partial_invoices: number
    invoice_not_raised_projects: number
  }
  collection: {
    payment_pending_amount_inr: number
    partial_payment_balance_inr: number
    invoice_not_raised_amount_inr: number
  }
}

interface RevenueEvent {
  project_id: number
  project_code: string
  project_name: string
  client_code: string | null
  client_name: string
  bd_name: string
  department_code: string
  department_label: string
  project_manager_name: string
  currency: string
  finance_invoice_number: string
  finance_invoice_date: string
  finance_invoice_amount: number
  finance_invoice_amount_inr: number
  revenue_amount_inr: number
  revenue_date: string
  final_payment_date: string | null
  invoice_closed_at: string | null
  payment_references: string[]
  remarks: string | null
}

interface Overview {
  projects: SalesProject[]
  revenue_events: RevenueEvent[]
  kpi_summary?: KpiSummary
}

interface RevenueTarget {
  id: number
  month_start: string
  month: string
  department_code: string
  department_label: string
  target_amount_inr: number
  created_by_name: string | null
  updated_by_name: string | null
  created_at: string | null
  updated_at: string | null
}

interface RevenueTargetResponse {
  targets: RevenueTarget[]
}

type VisualizationKey = 'monthly' | 'department' | 'status' | 'bd' | 'sales_revenue'

type DrilldownKey = 'open_sales' | 'revenue' | 'outstanding' | 'target' | 'payment_pending' | 'partial_payment' | 'invoice_not_raised'

type Period = 'today' | 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'yearly' | 'custom'

interface DrilldownMeta {
  kicker: string
  title: string
  subtitle: string
}

const drilldownMeta: Record<DrilldownKey, DrilldownMeta> = {
  open_sales: {
    kicker: 'KPI DRILL-DOWN',
    title: 'Open Sales Pipeline — Contributing Projects',
    subtitle: 'Projects that make up Open Sales Pipeline, with a line-by-line recomputation of open_sales_inr from the Sales/Revenue API formula.',
  },
  revenue: {
    kicker: 'KPI DRILL-DOWN',
    title: 'Realized Revenue — Contributing Events',
    subtitle: 'Closed Finance invoice events behind Realized Revenue, each checked against invoice closure and full payment.',
  },
  outstanding: {
    kicker: 'KPI DRILL-DOWN',
    title: 'Outstanding — Contributing Projects & Invoices',
    subtitle: 'Open receivables behind Outstanding, with recomputed outstanding_inr and days pending past invoice due date.',
  },
  target: {
    kicker: 'KPI DRILL-DOWN',
    title: 'Monthly Target — Department Performance',
    subtitle: 'Target vs Actual Revenue for the selected month. Actual only counts fully paid + closed Finance invoices.',
  },
  payment_pending: {
    kicker: 'KPI DRILL-DOWN',
    title: 'Payment Pending — Invoices Awaiting First Payment',
    subtitle: 'Finance invoices that are raised with paid amount = 0, scoped to the selected department and filters.',
  },
  partial_payment: {
    kicker: 'KPI DRILL-DOWN',
    title: 'Partial Payment — Partly Collected Invoices',
    subtitle: 'Finance invoices raised with paid > 0 and balance > 0, scoped to the selected department and filters.',
  },
  invoice_not_raised: {
    kicker: 'KPI DRILL-DOWN',
    title: 'Invoice Not Raised — Commercial Value Without Finance Invoice',
    subtitle: 'Projects with commercial/sales value but zero Finance invoices, scoped to the selected department and filters.',
  },
}

const PAYMENT_STATUS_FILTERS = ['Payment Pending', 'Partial Payment', 'Invoice Not Raised', 'Revenue Closed'] as const

const DEPARTMENTS = [
  ['ortho', 'ORTHO'],
  ['lidar', 'LiDAR'],
  ['mobile_mapping', 'Mobile Mapping'],
  ['laser_scanning', 'Laser Scanning'],
  ['civil', 'Civil'],
] as const

const visualizationOptions: Array<{ key: VisualizationKey; label: string }> = [
  { key: 'monthly', label: 'Monthly Sales vs Received' },
  { key: 'department', label: 'Department-wise Sales' },
  { key: 'status', label: 'Payment Status Distribution' },
  { key: 'bd', label: 'BD-wise Open Sales' },
  { key: 'sales_revenue', label: 'Sales vs Revenue (with gap)' },
]

function inr(value: number) {
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(value || 0)
}

function money(value: number, currency: string) {
  try {
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency: currency || 'INR', maximumFractionDigits: 2 }).format(value || 0)
  } catch {
    return `${currency || 'INR'} ${Number(value || 0).toLocaleString('en-IN')}`
  }
}

function currentMonth() {
  return new Date().toISOString().slice(0, 7)
}

function currentDate() {
  return new Date().toISOString().slice(0, 10)
}

function currentWeek() {
  const now = new Date()
  const target = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()))
  const day = target.getUTCDay() || 7
  target.setUTCDate(target.getUTCDate() + 4 - day)
  const yearStart = new Date(Date.UTC(target.getUTCFullYear(), 0, 1))
  const week = Math.ceil((((target.getTime() - yearStart.getTime()) / 86400000) + 1) / 7)
  return `${target.getUTCFullYear()}-W${String(week).padStart(2, '0')}`
}

function isoDate(d: Date) {
  return d.toISOString().slice(0, 10)
}

function weekRange(value: string): [string, string] {
  const match = /^(\d{4})-W(\d{2})$/.exec(value)
  if (!match) return [currentDate(), currentDate()]
  const year = Number(match[1])
  const week = Number(match[2])
  const jan4 = new Date(Date.UTC(year, 0, 4))
  const day = jan4.getUTCDay() || 7
  const week1 = new Date(jan4)
  week1.setUTCDate(jan4.getUTCDate() - day + 1)
  const start = new Date(week1)
  start.setUTCDate(week1.getUTCDate() + (week - 1) * 7)
  const end = new Date(start)
  end.setUTCDate(start.getUTCDate() + 6)
  return [isoDate(start), isoDate(end)]
}

function monthRange(value: string): [string, string] {
  const match = /^(\d{4})-(\d{2})$/.exec(value)
  if (!match) return [value, value]
  const year = Number(match[1])
  const month = Number(match[2])
  const start = Date.UTC(year, month - 1, 1)
  const end = Date.UTC(year, month, 0)
  return [isoDate(new Date(start)), isoDate(new Date(end))]
}

function quarterRange(year: number, quarter: number): [string, string] {
  const startMonth = (quarter - 1) * 3
  const start = Date.UTC(year, startMonth, 1)
  const end = Date.UTC(year, startMonth + 3, 0)
  return [isoDate(new Date(start)), isoDate(new Date(end))]
}

function dateRange(period: Period, values: {
  day: string
  week: string
  month: string
  quarter: number
  year: number
  from: string
  to: string
}): [string, string] {
  if (period === 'today') return [currentDate(), currentDate()]
  if (period === 'daily') return [values.day, values.day]
  if (period === 'weekly') return weekRange(values.week)
  if (period === 'monthly') return monthRange(values.month)
  if (period === 'quarterly') return quarterRange(values.year, values.quarter)
  if (period === 'yearly') return [`${values.year}-01-01`, `${values.year}-12-31`]
  return [values.from, values.to]
}

function dateInside(value: string | null, range: [string, string]) {
  if (!value) return false
  const day = value.slice(0, 10)
  return day >= range[0] && day <= range[1]
}

function monthLabel(value: string) {
  const d = new Date(`${value}-01T00:00:00`)
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })
}

function titleCase(value: string) {
  return value.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase())
}

function isRevenueQualifyingInvoice(inv: InvoiceRow) {
  return inv.status === 'INVOICE_CLOSED' && inv.paid_amount >= inv.total_amount
}

function isOpenInvoice(inv: InvoiceRow) {
  return !isRevenueQualifyingInvoice(inv)
}

function isPaymentPendingInvoice(inv: InvoiceRow) {
  if (inv.open_sales_category != null) return inv.open_sales_category === 'payment_pending_inr'
  return isOpenInvoice(inv) && inv.paid_amount <= 0 && inv.total_amount > 0
}

function isPartialPaymentInvoice(inv: InvoiceRow) {
  if (inv.open_sales_category != null) return inv.open_sales_category === 'partial_payment_inr'
  return isOpenInvoice(inv) && inv.paid_amount > 0 && inv.balance > 0
}

function isInvoicesNotRaised(row: SalesProject) {
  return Boolean(row.invoice_not_raised ?? (row.sales_value_inr > 0 && row.invoice_count === 0))
}

function projectPaymentStatus(row: SalesProject): string {
  if (row.invoice_not_raised && row.open_invoice_count === 0) return 'Invoice Not Raised'
  if (row.invoices.some(inv => isOpenInvoice(inv) && inv.open_sales_category === 'partial_payment_inr')) return 'Partial Payment'
  if (row.invoices.some(inv => isOpenInvoice(inv) && inv.open_sales_category === 'payment_pending_inr')) return 'Payment Pending'
  if (row.invoices.some(inv => isOpenInvoice(inv) && inv.open_sales_category === 'payment_received_closure_pending_inr')) return 'Payment Pending'
  if (row.closed_invoice_count > 0 && row.open_invoice_count === 0) return 'Revenue Closed'
  if (row.invoices.some(isOpenInvoice)) return 'Payment Pending'
  return 'Payment Pending'
}

interface ProjectCalc {
  closedSalesValueInr: number
  openInvoiceTotalInr: number
  openInvoiceBalanceInr: number
  openReceivedInr: number
  baselineOpenSalesInr: number
  unbilledOpenSalesInr: number
  expectedOpenSalesInr: number
  commandCenterOpenSalesInr: number
  expectedOutstandingInr: number
  openSalesMatched: boolean
  outstandingMatched: boolean
}

function computeProjectCalc(row: SalesProject): ProjectCalc {
  const qualifying = row.invoices.filter(isRevenueQualifyingInvoice)
  const openInvoices = row.invoices.filter(inv => !isRevenueQualifyingInvoice(inv))
  const closedSalesValueInr = qualifying.reduce((sum, inv) => sum + inv.total_inr, 0)
  const openInvoiceTotalInr = openInvoices.reduce((sum, inv) => sum + inv.total_inr, 0)
  const openInvoiceBalanceInr = openInvoices.reduce((sum, inv) => sum + inv.balance_inr, 0)
  const openReceivedInr = openInvoices.reduce((sum, inv) => sum + inv.paid_inr, 0)
  const baselineOpenSalesInr = Math.max(row.sales_value_inr - closedSalesValueInr, 0)
  const unbilledOpenSalesInr = Math.max(baselineOpenSalesInr - openInvoiceTotalInr, 0)
  const expectedOpenSalesInr = unbilledOpenSalesInr + openInvoiceBalanceInr
  const commandCenterOpenSalesInr = openSalesForProject(row)
  const expectedOutstandingInr = unbilledOpenSalesInr + openInvoiceBalanceInr
  const tolerance = 0.01
  return {
    closedSalesValueInr,
    openInvoiceTotalInr,
    openInvoiceBalanceInr,
    openReceivedInr,
    baselineOpenSalesInr,
    unbilledOpenSalesInr,
    expectedOpenSalesInr,
    commandCenterOpenSalesInr,
    expectedOutstandingInr,
    openSalesMatched: Math.abs(expectedOpenSalesInr - commandCenterOpenSalesInr) <= tolerance,
    outstandingMatched: Math.abs(expectedOutstandingInr - row.outstanding_inr) <= tolerance,
  }
}

function revenueEventCheck(event: RevenueEvent, projects: SalesProject[]) {
  const project = projects.find(row => row.project_id === event.project_id)
  const invoice = project?.invoices.find(row => row.invoice_number === event.finance_invoice_number) ?? null
  const closedOk = Boolean(event.invoice_closed_at) && invoice?.status === 'INVOICE_CLOSED'
  const paidOk = invoice != null && invoice.paid_amount >= invoice.total_amount
  const amountOk = event.revenue_amount_inr > 0
  return { invoice, closedOk, paidOk, amountOk, matched: closedOk && paidOk && amountOk }
}

function daysPending(dueDate: string) {
  const due = new Date(`${dueDate}T00:00:00`)
  if (Number.isNaN(due.getTime())) return null
  return Math.floor((Date.now() - due.getTime()) / 86_400_000)
}

function ChartShell({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <article className="sr-panel sr-chart-panel sr-selected-chart">
      <div className="sr-panel-heading">
        <div>
          <span>VISUAL ANALYTICS</span>
          <h3>{title}</h3>
          <p>{subtitle}</p>
        </div>
        <BarChart3 size={19} />
      </div>
      {children}
    </article>
  )
}

function ColumnChart({ title, subtitle, rows }: { title: string; subtitle: string; rows: Array<{ label: string; value: number }> }) {
  if (rows.length === 0) return <ChartShell title={title} subtitle={subtitle}><div className="sr-empty">No data for the selected filters.</div></ChartShell>
  const width = 760
  const height = 300
  const padX = 46
  const padTop = 24
  const padBottom = 72
  const plotHeight = height - padTop - padBottom
  const plotWidth = width - padX * 2
  const max = Math.max(1, ...rows.map(row => row.value))
  const gap = 16
  const barWidth = Math.max(30, (plotWidth - gap * (rows.length - 1)) / rows.length)

  return (
    <ChartShell title={title} subtitle={subtitle}>
      <div className="sr-svg-chart-wrap">
        <svg className="sr-svg-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
          {[0, .25, .5, .75, 1].map(step => {
            const y = padTop + plotHeight - step * plotHeight
            return <line key={step} x1={padX} x2={width - padX} y1={y} y2={y} className="sr-grid-line" />
          })}
          {rows.map((row, index) => {
            const h = Math.max(3, (row.value / max) * plotHeight)
            const x = padX + index * (barWidth + gap)
            const y = padTop + plotHeight - h
            return (
              <g key={row.label}>
                <rect x={x} y={y} width={barWidth} height={h} rx="8" className="sr-column" />
                <text x={x + barWidth / 2} y={Math.max(14, y - 8)} textAnchor="middle" className="sr-column-value">{inr(row.value)}</text>
                <text x={x + barWidth / 2} y={height - 34} textAnchor="middle" className="sr-axis-label">{row.label}</text>
              </g>
            )
          })}
        </svg>
      </div>
    </ChartShell>
  )
}

function TrendChart({ title, subtitle, rows, secondaryLabel, gapLabel }: {
  title: string
  subtitle: string
  rows: Array<{ label: string; value: number; secondary?: number }>
  secondaryLabel?: string
  gapLabel?: string
}) {
  if (rows.length === 0) return <ChartShell title={title} subtitle={subtitle}><div className="sr-empty">No data for the selected filters.</div></ChartShell>
  const width = 760
  const height = 270
  const padX = 48
  const padTop = 18
  const padBottom = 48
  const plotHeight = height - padTop - padBottom
  const plotWidth = width - padX * 2
  const max = Math.max(1, ...rows.flatMap(row => [row.value, row.secondary || 0]))
  const points = rows.map((row, index) => {
    const x = rows.length === 1 ? width / 2 : padX + (index / (rows.length - 1)) * plotWidth
    const y = padTop + plotHeight - (row.value / max) * plotHeight
    const secondaryY = row.secondary == null ? null : padTop + plotHeight - ((row.secondary || 0) / max) * plotHeight
    return { ...row, x, y, secondaryY }
  })
  const line = points.map((point, index) => `${index ? 'L' : 'M'} ${point.x} ${point.y}`).join(' ')
  const area = `${line} L ${points.at(-1)?.x ?? padX} ${padTop + plotHeight} L ${points[0]?.x ?? padX} ${padTop + plotHeight} Z`
  const secondaryLine = points.every(point => point.secondaryY == null) ? '' : points.map((point, index) => `${index ? 'L' : 'M'} ${point.x} ${point.secondaryY ?? padTop + plotHeight}`).join(' ')

  return (
    <ChartShell title={title} subtitle={subtitle}>
      <div className="sr-svg-chart-wrap">
        <svg className="sr-svg-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
          {[0, .25, .5, .75, 1].map(step => {
            const y = padTop + plotHeight - step * plotHeight
            return <line key={step} x1={padX} x2={width - padX} y1={y} y2={y} className="sr-grid-line" />
          })}
          <path d={area} className="sr-area-fill" />
          <path d={line} className="sr-trend-line" />
          {secondaryLine && <path d={secondaryLine} className="sr-trend-line secondary" />}
          {points.map(point => (
            <g key={point.label}>
              <circle cx={point.x} cy={point.y} r="4" className="sr-trend-dot" />
              {point.secondaryY != null && <circle cx={point.x} cy={point.secondaryY} r="4" className="sr-trend-dot secondary" />}
              <text x={point.x} y={height - 18} textAnchor="middle" className="sr-axis-label">{point.label}</text>
            </g>
          ))}
        </svg>
      </div>
      <div className="sr-chart-legend">
        <span><i className="primary" /> {secondaryLabel ? 'Sales' : 'Sales'}</span>
        {secondaryLabel && <span><i className="secondary" /> {secondaryLabel}</span>}
        {gapLabel && <span><i className="primary" style={{ background: '#ea580c' }} /> {gapLabel}</span>}
      </div>
    </ChartShell>
  )
}

function DonutChart({ title, subtitle, rows }: { title: string; subtitle: string; rows: Array<{ label: string; value: number }> }) {
  const usable = rows.filter(row => row.value > 0)
  const total = usable.reduce((sum, row) => sum + row.value, 0)
  if (!usable.length || total <= 0) return <ChartShell title={title} subtitle={subtitle}><div className="sr-empty">No data for the selected filters.</div></ChartShell>
  const palette = ['#0f172a', '#2563eb', '#0891b2', '#7c3aed', '#64748b', '#16a34a', '#ea580c', '#be123c']
  let cursor = 0
  const stops = usable.map((row, index) => {
    const start = cursor
    const end = cursor + (row.value / total) * 100
    cursor = end
    return `${palette[index % palette.length]} ${start}% ${end}%`
  }).join(', ')

  return (
    <ChartShell title={title} subtitle={subtitle}>
      <div className="sr-donut-layout">
        <div className="sr-donut" style={{ background: `conic-gradient(${stops})` }}>
          <div><strong>{inr(total)}</strong><span>Total</span></div>
        </div>
        <div className="sr-donut-legend">
          {usable.map((row, index) => (
            <div key={row.label}>
              <i style={{ background: palette[index % palette.length] }} />
              <span>{row.label}</span>
              <strong>{inr(row.value)}</strong>
              <small>{((row.value / total) * 100).toFixed(1)}%</small>
            </div>
          ))}
        </div>
      </div>
    </ChartShell>
  )
}

function RankingChart({ title, subtitle, rows }: { title: string; subtitle: string; rows: Array<{ label: string; value: number }> }) {
  const max = Math.max(1, ...rows.map(row => row.value))
  return (
    <ChartShell title={title} subtitle={subtitle}>
      {rows.length === 0 ? (
        <div className="sr-empty">No data for the selected filters.</div>
      ) : (
        <div className="sr-ranking-list">
          {rows.map((row, index) => (
            <div className="sr-ranking-row" key={row.label}>
              <div className="sr-ranking-index">{index + 1}</div>
              <div className="sr-ranking-main">
                <div><strong>{row.label}</strong><span>{inr(row.value)}</span></div>
                <div className="sr-bar-track"><i style={{ width: `${Math.max(2, (row.value / max) * 100)}%` }} /></div>
              </div>
            </div>
          ))}
        </div>
      )}
    </ChartShell>
  )
}

export function FinanceCommandCenter() {
  const { user } = useAuth()
  const lockedDepartment = user && isTechnicalProjectManager(user.role) ? departmentCodeForRole(user.role) : null
  const [data, setData] = useState<Overview | null>(null)
  const [revenueTargets, setRevenueTargets] = useState<RevenueTarget[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const rootRef = useRef<HTMLDivElement>(null)
  useNkReveal(rootRef, !loading && !error)
  const [visualizationKey, setVisualizationKey] = useState<VisualizationKey>('monthly')
  const [visualizationVisible, setVisualizationVisible] = useState(true)
  const [targetMonth, setTargetMonth] = useState(currentMonth)
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null)
  const [detailTab, setDetailTab] = useState<'sales' | 'finance' | 'payments' | 'timeline'>('sales')
  const [selectedInvoiceNumber, setSelectedInvoiceNumber] = useState<string | null>(null)
  const [drilldown, setDrilldown] = useState<DrilldownKey | null>(null)
  const [drilldownLoading, setDrilldownLoading] = useState(false)
  const [drilldownError, setDrilldownError] = useState('')
  const [drilldownData, setDrilldownData] = useState<{ overview: Overview; targets: RevenueTarget[] } | null>(null)
  const [expandedCalcId, setExpandedCalcId] = useState<string | null>(null)
  const [period, setPeriod] = useState<Period>('monthly')
  const [day, setDay] = useState(currentDate)
  const [week, setWeek] = useState(currentWeek)
  const [monthFilter, setMonthFilter] = useState(currentMonth)
  const [quarter, setQuarter] = useState(Math.floor(new Date().getMonth() / 3) + 1)
  const [year, setYear] = useState(new Date().getFullYear())
  const [from, setFrom] = useState('2000-01-01')
  const [to, setTo] = useState(currentDate)
  const [department, setDepartment] = useState(lockedDepartment ?? 'all')
  const [client, setClient] = useState('all')
  const [projectFilter, setProjectFilter] = useState('all')
  const [bd, setBd] = useState('all')
  const [pm, setPm] = useState('all')
  const [currency, setCurrency] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [salesDateBasis, setSalesDateBasis] = useState<'projected' | 'booked'>('projected')

  useEffect(() => {
    if (lockedDepartment) setDepartment(lockedDepartment)
  }, [lockedDepartment])

  function load() {
    setLoading(true)
    setError('')
    void Promise.all([
      apiFetch<Overview>('/finance/sales-revenue'),
      apiFetch<RevenueTargetResponse>('/finance/revenue-targets'),
    ])
      .then(([overview, targets]) => {
        setData(overview)
        setRevenueTargets(targets.targets)
      })
      .catch(err => setError(err instanceof Error ? err.message : 'Unable to load finance data'))
      .finally(() => setLoading(false))
  }

  function openDrilldown(key: DrilldownKey) {
    setDrilldown(key)
    setDrilldownLoading(true)
    setDrilldownError('')
    setDrilldownData(null)
    setExpandedCalcId(null)
    setSelectedProjectId(null)
    void Promise.all([
      apiFetch<Overview>('/finance/sales-revenue'),
      apiFetch<RevenueTargetResponse>('/finance/revenue-targets'),
    ])
      .then(([overview, targets]) => {
        setDrilldownData({ overview, targets: targets.targets })
        setData(overview)
        setRevenueTargets(targets.targets)
      })
      .catch(err => setDrilldownError(err instanceof Error && err.message ? err.message : 'Request failed'))
      .finally(() => setDrilldownLoading(false))
  }

  function closeDrilldown() {
    setDrilldown(null)
    setDrilldownData(null)
    setDrilldownError('')
    setExpandedCalcId(null)
  }

  useEffect(load, [])

  const allProjects = data?.projects ?? []
  const allRevenue = data?.revenue_events ?? []

  const range = useMemo(() => dateRange(period, { day, week, month: monthFilter, quarter, year, from, to }), [period, day, week, monthFilter, quarter, year, from, to])

  const filterOptions = useMemo(() => {
    const unique = (values: string[]) => [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b))
    return {
      clients: unique(allProjects.map(row => row.client_name)),
      projects: unique(allProjects.map(row => row.project_code)),
      bd: unique(allProjects.map(row => row.bd_name)),
      pm: unique(allProjects.map(row => row.project_manager_name)),
      currencies: unique(allProjects.map(row => row.currency)),
      statuses: [...PAYMENT_STATUS_FILTERS],
    }
  }, [allProjects])

  function dimensionsMatch(row: { department_code: string; client_name: string; project_code: string; bd_name: string; project_manager_name: string; currency: string }) {
    const departmentScope = lockedDepartment ?? department
    return (departmentScope === 'all' || row.department_code === departmentScope)
      && (client === 'all' || row.client_name === client)
      && (projectFilter === 'all' || row.project_code === projectFilter)
      && (bd === 'all' || row.bd_name === bd)
      && (pm === 'all' || row.project_manager_name === pm)
      && (currency === 'all' || row.currency === currency)
  }

  const filteredProjects = useMemo(() => allProjects.filter(row =>
    (salesDateBasis === 'projected' ? dateInside(row.projected_payment_date, range) : dateInside(row.sales_date, range))
    && dimensionsMatch(row)
    && (statusFilter === 'all' || projectPaymentStatus(row) === statusFilter)
  ), [allProjects, range, department, lockedDepartment, client, projectFilter, bd, pm, currency, statusFilter, salesDateBasis])

  const filteredRevenue = useMemo(() => allRevenue.filter(row =>
    dateInside(row.revenue_date, range)
    && dimensionsMatch(row)
  ), [allRevenue, range, department, client, projectFilter, bd, pm, currency])

  const activeProjects = filteredProjects
  const activeRevenue = filteredRevenue

  function resetDimensionFilters() {
    setDepartment(lockedDepartment ?? 'all')
    setClient('all')
    setProjectFilter('all')
    setBd('all')
    setPm('all')
    setCurrency('all')
    setStatusFilter('all')
    setSalesDateBasis('projected')
    setPeriod('monthly')
    setDay(currentDate)
    setWeek(currentWeek)
    setMonthFilter(currentMonth)
    setQuarter(Math.floor(new Date().getMonth() / 3) + 1)
    setYear(new Date().getFullYear())
    setFrom('2000-01-01')
    setTo(currentDate)
  }

  const selectedProject = selectedProjectId == null ? null : allProjects.find(row => row.project_id === selectedProjectId) ?? null
  const selectedInvoice = selectedProject?.invoices.find(row => row.invoice_number === selectedInvoiceNumber)
    ?? selectedProject?.invoices[0]
    ?? null

  useEffect(() => {
    if (selectedProjectId == null && drilldown == null) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      if (drilldown != null) closeDrilldown()
      else setSelectedProjectId(null)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [selectedProjectId, drilldown])

  const serverKpiSummary = data?.kpi_summary ?? null

  const salesKpis = useMemo(() => {
    return aggregateFinanceCommandCenterKpis(activeProjects, activeRevenue)
  }, [activeProjects, activeRevenue])

  const targetMonthRows = useMemo(() => {
    const departmentScope = lockedDepartment ?? department
    const targetByDepartment = new Map(
      revenueTargets
        .filter(row => row.month === targetMonth && (departmentScope === 'all' || row.department_code === departmentScope))
        .map(row => [row.department_code, row])
    )
    const departments = departmentScope === 'all'
      ? DEPARTMENTS
      : DEPARTMENTS.filter(([code]) => code === departmentScope)
    return departments.map(([code, label]) => {
      const targetRow = targetByDepartment.get(code)
      const actual = activeRevenue
        .filter(row => row.department_code === code && row.revenue_date.slice(0, 7) === targetMonth)
        .reduce((sum, row) => sum + row.revenue_amount_inr, 0)
      const target = targetRow?.target_amount_inr || 0
      const remaining = Math.max(target - actual, 0)
      const achievement = target > 0 ? (actual / target) * 100 : 0
      return { code, label, target, actual, remaining, achievement, updatedBy: targetRow?.updated_by_name || null }
    })
  }, [revenueTargets, activeRevenue, targetMonth, department, lockedDepartment])

  const targetSummary = useMemo(() => {
    const target = targetMonthRows.reduce((sum, row) => sum + row.target, 0)
    const actual = targetMonthRows.reduce((sum, row) => sum + row.actual, 0)
    return {
      target,
      actual,
      remaining: Math.max(target - actual, 0),
      achievement: target > 0 ? (actual / target) * 100 : 0,
    }
  }, [targetMonthRows])

  const monthlyChart = useMemo(() => {
    const map = new Map<string, { value: number; secondary: number }>()
    for (const row of activeProjects.filter(item => item.sales_visible)) {
      const chartDate = row.projected_payment_date || row.sales_date
      if (!chartDate) continue
      const key = chartDate.slice(0, 7)
      const item = map.get(key) || { value: 0, secondary: 0 }
      item.value += openSalesForProject(row)
      item.secondary += row.received_against_open_sales_inr
      map.set(key, item)
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([key, value]) => ({
      label: monthLabel(key),
      value: value.value,
      secondary: value.secondary,
    }))
  }, [activeProjects])

  const salesRevenueGapChart = useMemo(() => {
    const map = new Map<string, { sales: number; revenue: number }>()
    for (const row of activeProjects.filter(item => item.sales_visible)) {
      const chartDate = row.projected_payment_date || row.sales_date
      if (!chartDate) continue
      const key = chartDate.slice(0, 7)
      const item = map.get(key) || { sales: 0, revenue: 0 }
      item.sales += openSalesForProject(row)
      map.set(key, item)
    }
    for (const row of activeRevenue) {
      const key = row.revenue_date.slice(0, 7)
      const item = map.get(key) || { sales: 0, revenue: 0 }
      item.revenue += row.revenue_amount_inr
      map.set(key, item)
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([key, value]) => ({
      label: monthLabel(key),
      value: value.sales,
      secondary: value.revenue,
      gap: Math.max(value.sales - value.revenue, 0),
    }))
  }, [activeProjects, activeRevenue])

  const departmentChart = useMemo(() => {
    const map = new Map<string, number>()
    for (const row of activeProjects.filter(item => item.sales_visible)) {
      map.set(row.department_label, (map.get(row.department_label) || 0) + openSalesForProject(row))
    }
    return [...map.entries()].sort((a, b) => b[1] - a[1]).map(([label, value]) => ({ label, value }))
  }, [activeProjects])

  const statusChart = useMemo(() => {
    const buckets: Record<string, number> = {
      'Payment Pending': 0,
      'Partial Payment': 0,
      'Invoice Not Raised': 0,
      'Revenue Closed': 0,
    }
    for (const row of activeProjects) {
      const categories = openSalesCategoriesForProject(row)
      buckets['Payment Pending'] += (categories?.payment_pending_inr ?? 0)
        + (categories?.payment_received_closure_pending_inr ?? 0)
        + (categories?.other_open_inr ?? 0)
      buckets['Partial Payment'] += row.partial_payment_balance_inr || 0
      buckets['Invoice Not Raised'] += categories?.invoice_not_raised_inr ?? 0
      buckets['Revenue Closed'] += row.closed_revenue_inr
    }
    return Object.entries(buckets).map(([label, value]) => ({ label, value }))
  }, [activeProjects])

  const bdChart = useMemo(() => {
    const map = new Map<string, number>()
    for (const row of activeProjects.filter(item => item.sales_visible)) {
      const key = row.bd_name || 'Unassigned'
      map.set(key, (map.get(key) || 0) + openSalesForProject(row))
    }
    return [...map.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8).map(([label, value]) => ({ label, value }))
  }, [activeProjects])

  function renderVisualization() {
    if (visualizationKey === 'monthly') {
      return (
        <TrendChart
          title="Monthly Sales vs Received"
          subtitle="Open sales pipeline compared with money already received on still-open invoices."
          rows={monthlyChart}
          secondaryLabel="Received"
        />
      )
    }
    if (visualizationKey === 'department') {
      return (
        <ColumnChart
          title="Department-wise Sales"
          subtitle="Compare ORTHO, LiDAR, Mobile Mapping, Laser Scanning and Civil open sales."
          rows={departmentChart}
        />
      )
    }
    if (visualizationKey === 'status') {
      return <DonutChart title="Payment Status Distribution" subtitle="How open Sales money is distributed across collection states." rows={statusChart} />
    }
    if (visualizationKey === 'sales_revenue') {
      const totalSales = salesRevenueGapChart.reduce((sum, row) => sum + row.value, 0)
      const totalRevenue = salesRevenueGapChart.reduce((sum, row) => sum + (row.secondary || 0), 0)
      const totalGap = Math.max(totalSales - totalRevenue, 0)
      return (
        <TrendChart
          title="Sales vs Revenue (with gap)"
          subtitle={`Open Sales ${inr(totalSales)} vs Realized Revenue ${inr(totalRevenue)} · Gap ${inr(totalGap)}. Gap = open pipeline not yet closed into revenue.`}
          rows={salesRevenueGapChart}
          secondaryLabel="Revenue"
          gapLabel="Gap"
        />
      )
    }
    return <RankingChart title="BD-wise Open Sales" subtitle="Commercial ownership view for open sales pipeline." rows={bdChart} />
  }

  function openProject(row: SalesProject) {
    setSelectedProjectId(row.project_id)
    setSelectedInvoiceNumber(row.invoices[0]?.invoice_number ?? null)
    setDetailTab('sales')
  }

  const isEmpty = !loading && !error && allProjects.length === 0 && allRevenue.length === 0 && revenueTargets.length === 0

  if (loading) {
    return (
      <section aria-labelledby="finance-command-center-title" className="nk-arch-command">
        <article className="finance-panel">
          <div className="finance-panel-header">
            <div>
              <span>PHASE 3 · DEPARTMENT INTELLIGENCE</span>
              <h2 id="finance-command-center-title">FINANCE COMMAND CENTER</h2>
              <p>Unified KPI, sales visualization, revenue and target achievement view.</p>
            </div>
          </div>
          <div className="finance-panel finance-empty-state">Loading Finance Command Center...</div>
        </article>
      </section>
    )
  }

  if (error) {
    return (
      <section aria-labelledby="finance-command-center-title">
        <article className="finance-panel">
          <div className="finance-panel-header">
            <div>
              <span>PHASE 3 · DEPARTMENT INTELLIGENCE</span>
              <h2 id="finance-command-center-title">FINANCE COMMAND CENTER</h2>
            </div>
          </div>
          <div className="finance-error">
            Unable to load finance data{' '}
            <button type="button" className="finance-inline-link" onClick={load}>Retry</button>
          </div>
        </article>
      </section>
    )
  }

  if (isEmpty) {
    return (
      <section aria-labelledby="finance-command-center-title">
        <article className="finance-panel">
          <div className="finance-panel-header">
            <div>
              <span>PHASE 3 · DEPARTMENT INTELLIGENCE</span>
              <h2 id="finance-command-center-title">FINANCE COMMAND CENTER</h2>
              <p>Unified KPI, sales visualization, revenue and target achievement view.</p>
            </div>
            <button className="finance-secondary-button" type="button" onClick={load}><RefreshCcw size={16}/> Refresh</button>
          </div>
          <div className="finance-empty-state">No records available</div>
        </article>
      </section>
    )
  }

  return (
    <div className="nk-arch-command" ref={rootRef}>
      <CommandCenterHero
        id="finance-command-center-title"
        kicker="Phase 3 · Department Intelligence"
        title="Finance Command Center"
        description="Real KPI, sales visualization, revenue/collection summary and monthly target achievement from live Sales/Revenue APIs. No forecast, no hard-coded values."
        icon={BarChart3}
        liveTitle="Live Financial Data"
        liveNote="Streaming from Sales / Revenue APIs"
        actions={
          <button className="finance-secondary-button" type="button" onClick={load}><RefreshCcw size={16}/> Refresh</button>
        }
      />

      <section className="sr-filter-panel" aria-label="Finance Command Center filters" data-nk-reveal>
        <div className="sr-filter-title"><CalendarDays size={18}/><div><strong>Analytics filters</strong><span>Every KPI, table and chart below follows the same selection.</span></div></div>
        <div className="nk-range-chips" role="group" aria-label="Quick date range">
          <span className="nk-range-chips-label">Quick range</span>
          <button type="button" className={period === 'today' ? 'is-active' : ''} onClick={() => setPeriod('today')}>Today</button>
          <button type="button" className={period === 'weekly' ? 'is-active' : ''} onClick={() => setPeriod('weekly')}>This Week</button>
          <button type="button" className={period === 'monthly' ? 'is-active' : ''} onClick={() => setPeriod('monthly')}>This Month</button>
          <button type="button" className={period === 'quarterly' ? 'is-active' : ''} onClick={() => setPeriod('quarterly')}>This Quarter</button>
          <button type="button" className={period === 'yearly' ? 'is-active' : ''} onClick={() => setPeriod('yearly')}>This Year</button>
        </div>
        <div className="sr-filter-grid">
          <label><span>Period</span><select value={period} onChange={e => setPeriod(e.target.value as Period)}>
            <option value="today">Today</option><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option><option value="quarterly">Quarterly</option><option value="yearly">Yearly</option><option value="custom">Custom Range</option>
          </select></label>
          {period === 'daily' && <label><span>Date</span><input type="date" value={day} onChange={e => setDay(e.target.value)}/></label>}
          {period === 'weekly' && <label><span>Week</span><input type="week" value={week} onChange={e => setWeek(e.target.value)}/></label>}
          {period === 'monthly' && <label><span>Month</span><input type="month" value={monthFilter} onChange={e => setMonthFilter(e.target.value)}/></label>}
          {period === 'quarterly' && <><label><span>Year</span><input type="number" min="2000" max="2100" value={year} onChange={e => setYear(Number(e.target.value))}/></label><label><span>Quarter</span><select value={quarter} onChange={e => setQuarter(Number(e.target.value))}><option value={1}>Q1</option><option value={2}>Q2</option><option value={3}>Q3</option><option value={4}>Q4</option></select></label></>}
          {period === 'yearly' && <label><span>Year</span><input type="number" min="2000" max="2100" value={year} onChange={e => setYear(Number(e.target.value))}/></label>}
          {period === 'custom' && <><label><span>From</span><input type="date" value={from} onChange={e => setFrom(e.target.value)}/></label><label><span>To</span><input type="date" value={to} onChange={e => setTo(e.target.value)}/></label></>}
          <label><span>Department{lockedDepartment ? ' (locked)' : ''}</span>
            <select value={lockedDepartment ?? department} onChange={e => setDepartment(e.target.value)} disabled={Boolean(lockedDepartment)}>
              {lockedDepartment
                ? DEPARTMENTS.filter(([code]) => code === lockedDepartment).map(([code, label]) => <option key={code} value={code}>{label}</option>)
                : <><option value="all">All Departments</option>{DEPARTMENTS.map(([code, label]) => <option key={code} value={code}>{label}</option>)}</>}
            </select>
            {lockedDepartment && <small style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 4 }}><Lock size={11}/> Your department only</small>}
          </label>
          <label><span>Client</span><select value={client} onChange={e => setClient(e.target.value)}><option value="all">All Clients</option>{filterOptions.clients.map(v => <option key={v}>{v}</option>)}</select></label>
          <label><span>Project</span><select value={projectFilter} onChange={e => setProjectFilter(e.target.value)}><option value="all">All Projects</option>{filterOptions.projects.map(v => <option key={v}>{v}</option>)}</select></label>
          <label><span>BD Person</span><select value={bd} onChange={e => setBd(e.target.value)}><option value="all">All BD</option>{filterOptions.bd.map(v => <option key={v}>{v}</option>)}</select></label>
          <label><span>Project Manager</span><select value={pm} onChange={e => setPm(e.target.value)}><option value="all">All PMs</option>{filterOptions.pm.map(v => <option key={v}>{v}</option>)}</select></label>
          <label><span>Currency</span><select value={currency} onChange={e => setCurrency(e.target.value)}><option value="all">All Currencies</option>{filterOptions.currencies.map(v => <option key={v}>{v}</option>)}</select></label>
          <label><span>Sales Date Basis</span><select value={salesDateBasis} onChange={e => setSalesDateBasis(e.target.value as 'projected' | 'booked')}><option value="projected">Projected Payment Date</option><option value="booked">BD Sales / Commercial Date</option></select></label>
          <label><span>Payment Status</span><select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}><option value="all">All Statuses</option>{PAYMENT_STATUS_FILTERS.map(v => <option key={v} value={v}>{v}</option>)}</select></label>
          <button className="sr-reset" type="button" onClick={resetDimensionFilters}>Clear filters</button>
        </div>
        <div className="sr-range-note">Showing Command Center data for <strong>{range[0]} to {range[1]}</strong>{(lockedDepartment ?? department) !== 'all' ? ` · ${DEPARTMENTS.find(([code]) => code === (lockedDepartment ?? department))?.[1] || department}` : ''}{currency !== 'all' ? ` · ${currency}` : ''}{statusFilter !== 'all' ? ` · ${statusFilter}` : ''}{serverKpiSummary ? ` · Backend KPI ${serverKpiSummary.reconciled ? 'reconciled' : 'mismatch ' + serverKpiSummary.reconciliation_difference_inr}` : ''}{salesKpis.reconciled ? '' : ' · Filtered KPI mismatch'}</div>
      </section>

      <section className="finance-kpi-grid finance-kpi-grid-4" aria-label="Finance KPI summary" data-nk-reveal="stagger">
        <button className="finance-kpi-card kpi-drilldown" data-kpi="open_sales" type="button" onClick={() => openDrilldown('open_sales')} aria-label="Open Sales Pipeline details">
          <span><TrendingUp size={15}/> Open Sales Pipeline</span>
          <strong>{inr(salesKpis.openSales)}</strong>
          <small>{salesKpis.salesCount} open sales project(s)</small>
          <em className="kpi-drilldown-hint">View contributing projects</em>
        </button>
        <button className="finance-kpi-card kpi-drilldown" data-kpi="revenue" type="button" onClick={() => openDrilldown('revenue')} aria-label="Realized Revenue details">
          <span><IndianRupee size={15}/> Realized Revenue</span>
          <strong>{inr(salesKpis.closedRevenue)}</strong>
          <small>{salesKpis.revenueCount} closed invoice event(s)</small>
          <em className="kpi-drilldown-hint">View contributing events</em>
        </button>
        <button className="finance-kpi-card kpi-drilldown" data-kpi="target" type="button" onClick={() => openDrilldown('target')} aria-label="Monthly Target details">
          <span><Target size={15}/> Monthly Target</span>
          <strong>{inr(targetSummary.target)}</strong>
          <small>{monthLabel(targetMonth)} · {targetSummary.achievement.toFixed(1)}% achieved</small>
          <em className="kpi-drilldown-hint">View department performance</em>
        </button>
        <button className="finance-kpi-card kpi-drilldown" data-kpi="outstanding" type="button" onClick={() => openDrilldown('outstanding')} aria-label="Outstanding details">
          <span><CircleDollarSign size={15}/> Outstanding</span>
          <strong>{inr(salesKpis.outstanding)}</strong>
          <small>{salesKpis.partial} partial · {salesKpis.overdue} overdue</small>
          <em className="kpi-drilldown-hint">View open receivables</em>
        </button>
      </section>

      <section className="finance-kpi-grid finance-kpi-grid-4 finance-kpi-grid-secondary" aria-label="Collection summary" data-nk-reveal="stagger">
        <button className="finance-kpi-card kpi-drilldown" data-kpi="payment_pending" type="button" onClick={() => openDrilldown('payment_pending')} aria-label="Payment Pending details">
          <span><FileText size={15}/> Payment Pending</span>
          <strong>{inr(salesKpis.paymentPendingAmount)}</strong>
          <small>{salesKpis.paymentPendingCount} invoice(s) with paid = 0</small>
          <em className="kpi-drilldown-hint">View invoices awaiting first payment</em>
        </button>
        <button className="finance-kpi-card kpi-drilldown" data-kpi="partial_payment" type="button" onClick={() => openDrilldown('partial_payment')} aria-label="Partial Payment details">
          <span><WalletCards size={15}/> Partial Payment</span>
          <strong>{inr(salesKpis.partialAmount)}</strong>
          <small>{salesKpis.partialCount} invoice(s) partly paid · balance open</small>
          <em className="kpi-drilldown-hint">View partly collected invoices</em>
        </button>
        <button className="finance-kpi-card kpi-drilldown" data-kpi="invoice_not_raised" type="button" onClick={() => openDrilldown('invoice_not_raised')} aria-label="Invoice Not Raised details">
          <span><CircleDollarSign size={15}/> Invoice Not Raised</span>
          <strong>{inr(salesKpis.notRaisedAmount)}</strong>
          <small>{salesKpis.notRaisedCount} project(s) with sales value, no Finance invoice</small>
          <em className="kpi-drilldown-hint">View unbilled commercial value</em>
        </button>
        <article className="finance-kpi-card" data-kpi="target_remaining">
          <span><Target size={15}/> Target Remaining</span>
          <strong>{inr(targetSummary.remaining)}</strong>
          <small>Actual {inr(targetSummary.actual)} of {inr(targetSummary.target)}</small>
        </article>
      </section>

      <section className="sr-target-panel" aria-labelledby="command-target-heading" data-nk-reveal>
        <div className="sr-target-heading">
          <div>
            <span>MONTHLY REVENUE TARGET</span>
            <h3 id="command-target-heading">{monthLabel(targetMonth)} Department Performance</h3>
            <p>Target from Finance Revenue Targets. Actual Revenue only from fully paid + closed Finance invoices.</p>
          </div>
          <div className="sr-target-actions">
            <label>
              <span>Target Month</span>
              <input type="month" value={targetMonth} onChange={e => setTargetMonth(e.target.value)} />
            </label>
          </div>
        </div>
        <div className="sr-target-summary">
          <article><span>Target</span><strong>{inr(targetSummary.target)}</strong></article>
          <article><span>Actual Revenue</span><strong>{inr(targetSummary.actual)}</strong></article>
          <article><span>Remaining</span><strong>{inr(targetSummary.remaining)}</strong></article>
          <article><span>Achievement</span><strong>{targetSummary.achievement.toFixed(1)}%</strong></article>
        </div>
        <div className="sr-target-progress">
          <i style={{ width: `${Math.min(100, targetSummary.achievement)}%` }} />
          <span>{targetSummary.achievement.toFixed(1)}% achieved</span>
        </div>
        <div className="sr-target-departments">
          {targetMonthRows.map(row => (
            <div key={row.code}>
              <div><strong>{row.label}</strong><span>{inr(row.actual)} / {inr(row.target)}</span></div>
              <div className="sr-target-dept-track"><i style={{ width: `${Math.min(100, row.achievement)}%` }} /></div>
              <small>
                {row.target > 0
                  ? `${row.achievement.toFixed(1)}% · ${inr(row.remaining)} remaining`
                  : 'Target not set'}
                {row.updatedBy ? ` · by ${row.updatedBy}` : ''}
              </small>
            </div>
          ))}
        </div>
      </section>

      <section className="sr-viz-toolbar" data-nk-reveal>
        <div>
          <span>VISUALIZATIONS</span>
          <strong>Choose the analysis you want to view</strong>
          <small>Charts use real dated Sales and Revenue rows from the API.</small>
        </div>
        <label>
          <span>Visualization</span>
          <select value={visualizationKey} onChange={e => setVisualizationKey(e.target.value as VisualizationKey)}>
            {visualizationOptions.map(option => <option value={option.key} key={option.key}>{option.label}</option>)}
          </select>
        </label>
        <button className="finance-secondary-button" type="button" onClick={() => setVisualizationVisible(value => !value)}>
          {visualizationVisible ? <EyeOff size={16}/> : <Eye size={16}/>} {visualizationVisible ? 'Hide visualization' : 'Show visualization'}
        </button>
      </section>
      {visualizationVisible && <section className="sr-visual-stage">{renderVisualization()}</section>}

      <section className="sr-visual-stage" aria-label="Payment status and sales versus revenue charts" data-nk-reveal>
        <div className="sr-chart-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 14 }}>
          <DonutChart title="Payment Status Distribution" subtitle="How open Sales money is distributed across collection states under the current filters." rows={statusChart} />
          <TrendChart
            title="Sales vs Revenue (with gap)"
            subtitle="Open sales pipeline (Sales) vs fully paid + closed invoice events (Revenue). Gap = pipeline not yet realized."
            rows={salesRevenueGapChart}
            secondaryLabel="Revenue"
            gapLabel="Gap"
          />
        </div>
      </section>

      <section className="sr-panel" data-nk-reveal>
        <div className="sr-panel-heading">
          <div>
            <span>LIVE MONEY PIPELINE</span>
            <h3>Sales Projects</h3>
            <p>Open sales pipeline rows. Open a project for BD Sales, Finance Invoice and payment detail.</p>
          </div>
          <strong>{activeProjects.filter(row => row.sales_visible).length}</strong>
        </div>
        {activeProjects.filter(row => row.sales_visible).length === 0 ? (
          <div className="sr-empty">No records available</div>
        ) : (
          <div className="sr-table-wrap">
            <table className="sr-table">
              <thead>
                <tr>
                  <th>Project / Client</th>
                  <th>BD / Department / PM</th>
                  <th>Open Sales</th>
                  <th>Received / Outstanding</th>
                  <th>Projected Payment</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {[...activeProjects.filter(row => row.sales_visible)]
                  .sort((a, b) => (b.sales_date || '').localeCompare(a.sales_date || '') || b.project_code.localeCompare(a.project_code))
                  .slice(0, 10)
                  .map(row => (
                    <tr key={row.project_id}>
                      <td><strong>{row.project_code}</strong><br/><span>{row.project_name}</span><br/><small>{row.client_code || '—'} · {row.client_name}</small></td>
                      <td><strong>{row.bd_name}</strong><br/><span>{row.department_label}</span><br/><small>PM: {row.project_manager_name}</small></td>
                      <td><strong>{inr(openSalesForProject(row))}</strong></td>
                      <td><strong>{inr(row.received_against_open_sales_inr)}</strong><br/><small>Outstanding {inr(row.outstanding_inr)}</small></td>
                      <td>{row.projected_payment_date || '—'}</td>
                      <td><span className="sr-status">{row.sales_status}</span></td>
                      <td><button className="finance-secondary-button" type="button" onClick={() => openProject(row)}>Project details</button></td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="sr-panel" data-nk-reveal>
        <div className="sr-panel-heading">
          <div>
            <span>CLOSED & REALIZED MONEY</span>
            <h3>Revenue Summary</h3>
            <p>Recent realized revenue events from fully paid + closed Finance invoices.</p>
          </div>
          <strong>{activeRevenue.length}</strong>
        </div>
        {activeRevenue.length === 0 ? (
          <div className="sr-empty">No records available</div>
        ) : (
          <div className="sr-table-wrap">
            <table className="sr-table">
              <thead>
                <tr>
                  <th>Project / Client</th>
                  <th>Finance Invoice</th>
                  <th>Revenue Date</th>
                  <th>Amount</th>
                  <th>Final Payment</th>
                </tr>
              </thead>
              <tbody>
                {[...activeRevenue]
                  .sort((a, b) => b.revenue_date.localeCompare(a.revenue_date))
                  .slice(0, 10)
                  .map(row => (
                    <tr key={`${row.project_id}-${row.finance_invoice_number}`}>
                      <td><strong>{row.project_code}</strong><br/><span>{row.project_name}</span><br/><small>{row.client_code || '—'} · {row.client_name}</small></td>
                      <td><strong>{row.finance_invoice_number}</strong><br/><small>{row.finance_invoice_date}</small></td>
                      <td>{row.revenue_date}</td>
                      <td><strong>{money(row.finance_invoice_amount, row.currency)}</strong><br/><small>{inr(row.revenue_amount_inr)}</small></td>
                      <td>{row.final_payment_date || '—'}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {selectedProject && (
        <div className="sr-modal-backdrop" role="presentation" onMouseDown={() => setSelectedProjectId(null)}>
          <section className="sr-modal" role="dialog" aria-modal="true" aria-label={`Project details for ${selectedProject.project_code}`} onMouseDown={event => event.stopPropagation()}>
            <div className="sr-modal-header">
              <div>
                <span>PROJECT FINANCIAL DETAIL</span>
                <h3>{selectedProject.project_code} — {selectedProject.project_name}</h3>
                <p>{selectedProject.client_code || '—'} · {selectedProject.client_name} · {selectedProject.department_label} · PM {selectedProject.project_manager_name}</p>
              </div>
              <button className="sr-modal-close" type="button" onClick={() => setSelectedProjectId(null)} aria-label="Close project details"><X size={20}/></button>
            </div>

            <div className="sr-facts" style={{ marginBottom: 12 }}>
              <div><span>Client ID</span><strong>{selectedProject.client_code || '—'}</strong></div>
              <div><span>Client Name</span><strong>{selectedProject.client_name || '—'}</strong></div>
              <div><span>Project ID</span><strong>{selectedProject.project_code}</strong></div>
              <div><span>Project Name</span><strong>{selectedProject.project_name}</strong></div>
              <div><span>Department</span><strong>{selectedProject.department_label}</strong></div>
              <div><span>BD Person</span><strong>{selectedProject.bd_name || '—'}</strong></div>
              <div><span>Project Manager</span><strong>{selectedProject.project_manager_name || '—'}</strong></div>
              <div><span>Currency</span><strong>{selectedProject.currency || '—'}</strong></div>
              <div><span>Projected payment date</span><strong>{selectedProject.projected_payment_date || '—'}</strong></div>
              <div><span>Completion date</span><strong>{selectedProject.completion_date || '—'}</strong></div>
              <div><span>Project status</span><strong>{selectedProject.project_status || '—'}</strong></div>
              <div><span>Project created</span><strong>{selectedProject.project_created_at || '—'}</strong></div>
              <div><span>Payment status</span><strong>{projectPaymentStatus(selectedProject)}</strong></div>
            </div>

            <div className="sr-detail-tabs">
              <button className={detailTab === 'sales' ? 'active' : ''} onClick={() => setDetailTab('sales')}>Commercial</button>
              <button className={detailTab === 'finance' ? 'active' : ''} onClick={() => setDetailTab('finance')}>Finance Invoice</button>
              <button className={detailTab === 'payments' ? 'active' : ''} onClick={() => setDetailTab('payments')}>Payment History</button>
              <button className={detailTab === 'timeline' ? 'active' : ''} onClick={() => setDetailTab('timeline')}>Timeline</button>
            </div>

            {detailTab === 'sales' && (
              <div className="sr-facts">
                <div><span>BD Sales Reference</span><strong>{selectedProject.bd_sales_invoice.reference || 'Commercial Revision ' + (selectedProject.bd_sales_invoice.revision_no || 1)}</strong></div>
                <div><span>BD Sales Date</span><strong>{selectedProject.bd_sales_invoice.date}</strong></div>
                <div><span>Currency</span><strong>{selectedProject.bd_sales_invoice.currency}</strong></div>
                <div><span>Sales Value</span><strong>{money(selectedProject.bd_sales_invoice.amount, selectedProject.bd_sales_invoice.currency)}</strong></div>
                <div><span>Sales Value INR</span><strong>{inr(selectedProject.bd_sales_invoice.amount_inr)}</strong></div>
                <div><span>Status</span><strong>{selectedProject.bd_sales_invoice.status || '—'}{selectedProject.bd_sales_invoice.is_locked ? ' · Locked' : ''}</strong></div>
                <div><span>PO / WO</span><strong>{selectedProject.bd_sales_invoice.po_wo_reference || '—'}</strong></div>
                <div><span>Payment Terms</span><strong>{selectedProject.bd_sales_invoice.payment_terms || '—'}</strong></div>
                <div><span>Billing Type</span><strong>{selectedProject.bd_sales_invoice.billing_type ? titleCase(selectedProject.bd_sales_invoice.billing_type) : '—'}</strong></div>
                <div><span>Expected Milestone</span><strong>{selectedProject.bd_sales_invoice.expected_billing_milestone || '—'}</strong></div>
                <div><span>Projected Client Payment</span><strong>{selectedProject.bd_sales_invoice.projected_payment_date || selectedProject.projected_payment_date || '—'}</strong></div>
                <div className="wide"><span>Remarks</span><strong>{selectedProject.bd_sales_invoice.notes || '—'}</strong></div>
              </div>
            )}

            {detailTab === 'finance' && (
              <>
                {selectedProject.invoices.length === 0 ? (
                  <div className="sr-empty">Finance has not generated an invoice for this project yet.</div>
                ) : (
                  <>
                    <div className="sr-invoice-picker">
                      {selectedProject.invoices.map(inv => (
                        <button key={inv.id} className={selectedInvoice?.id === inv.id ? 'active' : ''} onClick={() => setSelectedInvoiceNumber(inv.invoice_number)}>{inv.invoice_number}</button>
                      ))}
                    </div>
                    {selectedInvoice && (
                      <div className="sr-facts">
                        <div><span>Finance Invoice</span><strong>{selectedInvoice.invoice_number}</strong></div>
                        <div><span>Status</span><strong>{titleCase(selectedInvoice.status)}</strong></div>
                        <div><span>Invoice Date</span><strong>{selectedInvoice.invoice_date}</strong></div>
                        <div><span>Due Date</span><strong>{selectedInvoice.due_date}</strong></div>
                        <div><span>Currency</span><strong>{selectedInvoice.currency}</strong></div>
                        <div><span>Invoice Total</span><strong>{money(selectedInvoice.total_amount, selectedInvoice.currency)}</strong></div>
                        <div><span>Invoice INR</span><strong>{inr(selectedInvoice.total_inr)}</strong></div>
                        <div><span>Paid INR</span><strong>{inr(selectedInvoice.paid_inr)}</strong></div>
                        <div><span>Outstanding INR</span><strong>{inr(selectedInvoice.balance_inr)}</strong></div>
                        <div><span>Closed At</span><strong>{selectedInvoice.closed_at ? selectedInvoice.closed_at.replace('T', ' ').slice(0, 19) : 'Not closed'}</strong></div>
                        <div className="wide"><span>Finance Remarks</span><strong>{selectedInvoice.notes || '—'}</strong></div>
                      </div>
                    )}
                  </>
                )}
              </>
            )}

            {detailTab === 'payments' && (
              <>
                {selectedProject.invoices.length === 0 ? (
                  <div className="sr-empty">No Finance invoice or payment exists yet.</div>
                ) : (
                  selectedProject.invoices.map(inv => (
                    <div className="sr-payment-block" key={inv.id}>
                      <h4>{inv.invoice_number} <span>{titleCase(inv.status)}</span></h4>
                      {inv.payments.length === 0 ? (
                        <div className="sr-empty">No payments recorded for this invoice.</div>
                      ) : (
                        <div className="sr-table-wrap">
                          <table className="sr-table">
                            <thead>
                              <tr><th>Reference</th><th>Date</th><th>Mode</th><th>Amount</th><th>INR</th></tr>
                            </thead>
                            <tbody>
                              {inv.payments.map(payment => (
                                <tr key={payment.id}>
                                  <td>{payment.payment_reference || '—'}</td>
                                  <td>{payment.payment_date}</td>
                                  <td>{titleCase(payment.payment_mode)}</td>
                                  <td>{money(payment.amount, payment.currency)}</td>
                                  <td>{inr(payment.amount_inr)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </>
            )}

            {detailTab === 'timeline' && (
              (() => {
                const events: Array<{ date: string; label: string; detail?: string }> = []
                if (selectedProject.project_created_at) events.push({ date: selectedProject.project_created_at, label: 'Project Created', detail: selectedProject.project_code })
                if (selectedProject.sales_date) events.push({ date: selectedProject.sales_date, label: 'Commercial Approval', detail: selectedProject.bd_sales_invoice.reference || `Revision ${selectedProject.bd_sales_invoice.revision_no || 1}` })
                if (selectedProject.projected_payment_date) events.push({ date: selectedProject.projected_payment_date, label: 'Projected client payment', detail: 'From commercial baseline or open invoice due date' })
                for (const inv of selectedProject.invoices) {
                  events.push({ date: inv.invoice_date, label: `Invoice Raised — ${inv.invoice_number}`, detail: `${titleCase(inv.status)} · due ${inv.due_date} · ${money(inv.total_amount, inv.currency)}` })
                  if (inv.raised_at) events.push({ date: inv.raised_at.slice(0, 10), label: `Invoice raised at — ${inv.invoice_number}`, detail: inv.raised_at.replace('T', ' ').slice(0, 19) })
                  for (const payment of inv.payments) {
                    events.push({ date: payment.payment_date, label: `Payment Received — ${payment.payment_reference || inv.invoice_number}`, detail: `${money(payment.amount, payment.currency)} · ${inr(payment.amount_inr)} · ${titleCase(payment.payment_mode)}` })
                  }
                  if (inv.closed_at) events.push({ date: inv.closed_at.slice(0, 10), label: `Revenue Closed — ${inv.invoice_number}`, detail: inv.closed_at.replace('T', ' ').slice(0, 19) })
                }
                if (selectedProject.completion_date) events.push({ date: selectedProject.completion_date, label: 'Completion date', detail: 'Project end date from Finance Project Master' })
                const completed = events.filter(row => row.date).sort((a, b) => a.date.localeCompare(b.date))
                if (completed.length === 0) return <div className="sr-empty">No records available</div>
                return (
                  <>
                    <div className="sr-facts">
                      <div><span>Timeline events</span><strong>{completed.length}</strong></div>
                      <div><span>Completion date</span><strong>{selectedProject.completion_date || '—'}</strong></div>
                      <div><span>Project status</span><strong>{selectedProject.project_status || '—'}</strong></div>
                      <div><span>Sales status</span><strong>{selectedProject.sales_status}</strong></div>
                      <div><span>Payment status</span><strong>{projectPaymentStatus(selectedProject)}</strong></div>
                    </div>
                    <div className="finance-timeline">
                      {completed.map((event, index) => (
                        <div className="finance-timeline-item" key={`${event.date}-${event.label}-${index}`}>
                          <strong>{event.label}</strong>
                          <span>{event.date}</span>
                          {event.detail && <p>{event.detail}</p>}
                        </div>
                      ))}
                    </div>
                  </>
                )
              })()
            )}
          </section>
        </div>
      )}

      {drilldown && (
        <div className="sr-modal-backdrop" role="presentation" onMouseDown={closeDrilldown}>
          <section className="sr-modal" role="dialog" aria-modal="true" aria-label={drilldownMeta[drilldown].title} onMouseDown={event => event.stopPropagation()}>
            <div className="sr-modal-header">
              <div>
                <span>{drilldownMeta[drilldown].kicker}</span>
                <h3>{drilldownMeta[drilldown].title}</h3>
                <p>{drilldownMeta[drilldown].subtitle}</p>
              </div>
              <button className="sr-modal-close" type="button" onClick={closeDrilldown} aria-label="Close KPI details"><X size={20}/></button>
            </div>

            {drilldownLoading && (
              <div className="finance-empty-state" role="status">Loading details...</div>
            )}

            {!drilldownLoading && drilldownError && (
              <div className="finance-error">
                Unable to load details{drilldownError ? `: ${drilldownError}` : ''}{' '}
                <button type="button" className="finance-inline-link" onClick={() => openDrilldown(drilldown)}>Retry</button>
              </div>
            )}

            {!drilldownLoading && !drilldownError && drilldownData && (() => {
              const ddProjects = drilldownData.overview.projects.filter(row => dimensionsMatch(row) && (salesDateBasis === 'projected' ? dateInside(row.projected_payment_date, range) : dateInside(row.sales_date, range)) && (statusFilter === 'all' || projectPaymentStatus(row) === statusFilter))
              const ddRevenue = drilldownData.overview.revenue_events.filter(row => dateInside(row.revenue_date, range) && dimensionsMatch(row))
              const departmentScope = lockedDepartment ?? department
              const ddTargets = drilldownData.targets.filter(row => departmentScope === 'all' || row.department_code === departmentScope)

              if (drilldown === 'payment_pending' || drilldown === 'partial_payment' || drilldown === 'invoice_not_raised') {
                type CollectionRow = { row: SalesProject; inv: InvoiceRow | null }
                let rows: CollectionRow[] = []
                let headline = 0
                let headlineLabel = ''
                if (drilldown === 'payment_pending') {
                  rows = ddProjects.flatMap(row => row.invoices.filter(isPaymentPendingInvoice).map(inv => ({ row, inv })))
                  headline = ddProjects.reduce((sum, row) => sum + (row.open_sales_categories?.payment_pending_inr ?? 0), 0)
                  headlineLabel = 'Payment Pending (backend category INR)'
                } else if (drilldown === 'partial_payment') {
                  rows = ddProjects.flatMap(row => row.invoices.filter(isPartialPaymentInvoice).map(inv => ({ row, inv })))
                  headline = ddProjects.reduce((sum, row) => sum + (row.partial_payment_balance_inr || 0), 0)
                  headlineLabel = 'Partial Payment (remaining balance INR)'
                } else {
                  rows = ddProjects.filter(isInvoicesNotRaised).map(row => ({ row, inv: null }))
                  headline = ddProjects.reduce((sum, row) => sum + (row.open_sales_categories?.invoice_not_raised_inr ?? 0), 0)
                  headlineLabel = 'Invoice Not Raised (backend unbilled INR)'
                }
                const projectCount = new Set(rows.map(item => item.row.project_id)).size
                return (
                  <>
                    <div className="sr-facts">
                      <div><span>{headlineLabel}</span><strong>{inr(headline)}</strong></div>
                      <div><span>Rows</span><strong>{rows.length}</strong></div>
                      <div><span>Projects</span><strong>{projectCount}</strong></div>
                      <div>
                        <span>Status</span>
                        <strong>
                          <span className={`finance-status ${rows.length > 0 ? 'tone-success' : 'tone-draft'}`}>
                            {rows.length > 0 ? 'RECORDS FOUND' : 'NO RECORDS'}
                          </span>
                        </strong>
                      </div>
                    </div>
                    {rows.length === 0 ? (
                      <div className="sr-empty">No records available</div>
                    ) : (
                      <div className="sr-table-wrap">
                        <table className="sr-table">
                          <thead>
                            <tr>
                              <th>Client Name</th>
                              <th>Client ID</th>
                              <th>Project ID / Name</th>
                              <th>Department</th>
                              <th>BD Person</th>
                              <th>Project Manager</th>
                              <th>Amount</th>
                              <th>Projected Payment</th>
                              <th>Currency</th>
                              <th>Payment Status</th>
                              <th>Completion / Status</th>
                              <th>Action</th>
                            </tr>
                          </thead>
                          <tbody>
                            {rows.map(({ row, inv }) => (
                              <tr key={inv ? `inv-${inv.id}` : `project-${row.project_id}`}>
                                <td>{row.client_name || '—'}</td>
                                <td>{row.client_code || '—'}</td>
                                <td><strong>{row.project_code}</strong><br/><span>{row.project_name}</span></td>
                                <td>{row.department_label}</td>
                                <td>{row.bd_name || '—'}</td>
                                <td>{row.project_manager_name || '—'}</td>
                                <td>{inv ? <>{inr(inv.total_inr)}<br/><small>Paid {inr(inv.paid_inr)} · Bal {inr(inv.balance_inr)}</small></> : <>{inr(row.sales_value_inr)}<br/><small>sales value</small></>}</td>
                                <td>{row.projected_payment_date || '—'}</td>
                                <td>{row.currency || '—'}</td>
                                <td><span className="sr-status">{inv ? titleCase(inv.status) : projectPaymentStatus(row)}</span></td>
                                <td>{row.completion_date || '—'}<br/><small>{row.project_status || '—'}</small></td>
                                <td><button className="finance-secondary-button" type="button" onClick={() => { setSelectedProjectId(row.project_id); setSelectedInvoiceNumber(inv?.invoice_number ?? row.invoices[0]?.invoice_number ?? null); setDetailTab('sales') }}>Project details</button></td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </>
                )
              }

              if (drilldown === 'open_sales') {
                const rows = ddProjects
                  .map(row => ({ row, calc: computeProjectCalc(row) }))
                  .filter(item => item.calc.commandCenterOpenSalesInr > 0)
                  .sort((a, b) => b.calc.commandCenterOpenSalesInr - a.calc.commandCenterOpenSalesInr)
                const total = rows.reduce((sum, item) => sum + item.calc.commandCenterOpenSalesInr, 0)
                const matched = rows.filter(item => item.calc.openSalesMatched).length
                const recomputed = rows.reduce((sum, item) => sum + item.calc.expectedOpenSalesInr, 0)
                return (
                  <>
                    <div className="sr-facts">
                      <div><span>Open Sales Pipeline</span><strong>{inr(total)}</strong></div>
                      <div><span>Contributing projects</span><strong>{rows.length}</strong></div>
                      <div><span>Recomputed total</span><strong>{inr(recomputed)}</strong></div>
                      <div>
                        <span>Validation</span>
                        <strong>
                          <span className={`finance-status ${matched === rows.length && rows.length > 0 ? 'tone-success' : 'tone-danger'}`}>
                            {matched === rows.length && rows.length > 0 ? 'ALL MATCHED' : `${matched}/${rows.length} MATCHED`}
                          </span>
                        </strong>
                      </div>
                    </div>
                    {rows.length === 0 ? (
                      <div className="sr-empty">No records available</div>
                    ) : (
                      <div className="sr-table-wrap">
                        <table className="sr-table">
                          <thead>
                            <tr>
                              <th>Project / Client</th>
                              <th>BD / Department</th>
                              <th>Sales Status</th>
                              <th>Sales Value INR</th>
                              <th>Closed Invoice INR</th>
                              <th>Open Invoice INR</th>
                              <th>Open Sales INR</th>
                              <th>Validation</th>
                              <th>Calculation</th>
                            </tr>
                          </thead>
                          <tbody>
                            {rows.map(({ row, calc }) => {
                              const key = `open_sales-${row.project_id}`
                              const expanded = expandedCalcId === key
                              return (
                                <Fragment key={row.project_id}>
                                  <tr>
                                    <td><strong>{row.project_code}</strong><br/><span>{row.project_name}</span><br/><small>{row.client_code || '—'} · {row.client_name}</small></td>
                                    <td><strong>{row.bd_name}</strong><br/><small>{row.department_label}</small></td>
                                    <td><span className="sr-status">{row.sales_status}</span></td>
                                    <td>{inr(row.sales_value_inr)}</td>
                                    <td>{inr(calc.closedSalesValueInr)}</td>
                                    <td>{inr(calc.openInvoiceTotalInr)}</td>
                                    <td><strong>{inr(calc.commandCenterOpenSalesInr)}</strong></td>
                                    <td>
                                      <span className={`finance-status ${calc.openSalesMatched ? 'tone-success' : 'tone-danger'}`}>
                                        {calc.openSalesMatched ? 'MATCHED' : 'MISMATCH'}
                                      </span>
                                    </td>
                                    <td>
                                      <button className="finance-secondary-button" type="button" onClick={() => setExpandedCalcId(expanded ? null : key)}>
                                        {expanded ? <ChevronDown size={14}/> : <ChevronRight size={14}/>} {expanded ? 'Hide' : 'Show'}
                                      </button>
                                    </td>
                                  </tr>
                                  {expanded && (
                                    <tr>
                                      <td colSpan={9}>
                                        <div className="sr-calc-detail">
                                          <div className="sr-calc-steps">
                                            <div className="sr-calc-step"><span>Baseline sales value (commercial Revision) INR</span><strong>{inr(row.sales_value_inr)}</strong></div>
                                            <div className="sr-calc-step"><span>Less: fully paid + closed invoice totals INR</span><strong>− {inr(calc.closedSalesValueInr)}</strong></div>
                                            <div className="sr-calc-step"><span>Baseline open = max(sales − closed, 0)</span><strong>{inr(calc.baselineOpenSalesInr)}</strong></div>
                                             <div className="sr-calc-step"><span>Open invoice balances still to collect INR</span><strong>{inr(calc.openInvoiceBalanceInr)}</strong></div>
                                             <div className="sr-calc-step"><span>Recomputed open_sales_inr = unbilled value + unpaid invoice balances</span><strong>{inr(calc.expectedOpenSalesInr)}</strong></div>
                                            <div className="sr-calc-step"><span>Command Center open_sales_inr</span><strong>{inr(calc.commandCenterOpenSalesInr)}</strong></div>
                                            <div className="sr-calc-step"><span>Raw API open_sales_inr</span><strong>{inr(row.open_sales_inr)}</strong></div>
                                            <div className="sr-calc-step"><span>Open invoices received INR (still in Sales)</span><strong>{inr(calc.openReceivedInr)}</strong></div>
                                          </div>
                                          <p className="sr-calc-formula">
                                            open_sales_inr = unbilled_open_sales_inr + unpaid invoice balances
                                          </p>
                                        </div>
                                      </td>
                                    </tr>
                                  )}
                                </Fragment>
                              )
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </>
                )
              }

              if (drilldown === 'revenue') {
                const rows = ddRevenue
                  .map(row => ({ row, check: revenueEventCheck(row, ddProjects) }))
                  .sort((a, b) => b.row.revenue_date.localeCompare(a.row.revenue_date))
                const total = rows.reduce((sum, item) => sum + item.row.revenue_amount_inr, 0)
                const verified = rows.filter(item => item.check.matched).length
                return (
                  <>
                    <div className="sr-facts">
                      <div><span>Realized Revenue</span><strong>{inr(total)}</strong></div>
                      <div><span>Contributing events</span><strong>{rows.length}</strong></div>
                      <div><span>Verified events</span><strong>{verified}</strong></div>
                      <div>
                        <span>Validation</span>
                        <strong>
                          <span className={`finance-status ${verified === rows.length && rows.length > 0 ? 'tone-success' : rows.length === 0 ? 'tone-draft' : 'tone-danger'}`}>
                            {rows.length === 0 ? 'NO RECORDS' : verified === rows.length ? 'ALL VERIFIED' : `${verified}/${rows.length} VERIFIED`}
                          </span>
                        </strong>
                      </div>
                    </div>
                    {rows.length === 0 ? (
                      <div className="sr-empty">No records available</div>
                    ) : (
                      <div className="sr-table-wrap">
                        <table className="sr-table">
                          <thead>
                            <tr>
                              <th>Project / Client</th>
                              <th>Finance Invoice</th>
                              <th>Revenue Date</th>
                              <th>Invoice INR</th>
                              <th>Revenue INR</th>
                              <th>Invoice Closed At</th>
                              <th>Validation</th>
                              <th>Calculation</th>
                            </tr>
                          </thead>
                          <tbody>
                            {rows.map(({ row, check }) => {
                              const key = `revenue-${row.project_id}-${row.finance_invoice_number}`
                              const expanded = expandedCalcId === key
                              return (
                                <Fragment key={key}>
                                  <tr>
                                    <td><strong>{row.project_code}</strong><br/><span>{row.project_name}</span><br/><small>{row.client_code || '—'} · {row.client_name}</small></td>
                                    <td><strong>{row.finance_invoice_number}</strong><br/><small>{row.finance_invoice_date}</small></td>
                                    <td>{row.revenue_date}</td>
                                    <td>{inr(row.finance_invoice_amount_inr)}</td>
                                    <td><strong>{inr(row.revenue_amount_inr)}</strong></td>
                                    <td>{row.invoice_closed_at ? row.invoice_closed_at.replace('T', ' ').slice(0, 19) : '—'}</td>
                                    <td>
                                      <span className={`finance-status ${check.matched ? 'tone-success' : 'tone-danger'}`}>
                                        {check.matched ? 'VERIFIED' : 'REVIEW'}
                                      </span>
                                    </td>
                                    <td>
                                      <button className="finance-secondary-button" type="button" onClick={() => setExpandedCalcId(expanded ? null : key)}>
                                        {expanded ? <ChevronDown size={14}/> : <ChevronRight size={14}/>} {expanded ? 'Hide' : 'Show'}
                                      </button>
                                    </td>
                                  </tr>
                                  {expanded && (
                                    <tr>
                                      <td colSpan={8}>
                                        <div className="sr-calc-detail">
                                          <div className="sr-calc-steps">
                                            <div className="sr-calc-step"><span>Finance invoice status</span><strong>{check.invoice ? titleCase(check.invoice.status) : 'Invoice not found'}</strong></div>
                                            <div className="sr-calc-step"><span>Invoice fully paid (paid amount ≥ total)</span><strong>{check.invoice ? `${money(check.invoice.paid_amount, check.invoice.currency)} / ${money(check.invoice.total_amount, check.invoice.currency)}` : '—'}</strong></div>
                                            <div className="sr-calc-step"><span>invoice_closed_at present</span><strong>{row.invoice_closed_at ? 'Yes' : 'No'}</strong></div>
                                            <div className="sr-calc-step"><span>Recomputed revenue (paid INR on closed invoice)</span><strong>{check.invoice ? inr(check.invoice.paid_inr) : '—'}</strong></div>
                                            <div className="sr-calc-step"><span>API revenue_amount_inr</span><strong>{inr(row.revenue_amount_inr)}</strong></div>
                                            <div className="sr-calc-step">
                                              <span>Checks: closed + fully paid + amount &gt; 0</span>
                                              <strong>
                                                <span className={`finance-status ${check.matched ? 'tone-success' : 'tone-danger'}`}>
                                                  {check.closedOk && check.paidOk && check.amountOk ? 'MATCHED' : 'MISMATCH'}
                                                </span>
                                              </strong>
                                            </div>
                                          </div>
                                          <p className="sr-calc-formula">
                                            Revenue event qualifies only when invoice status = INVOICE_CLOSED AND payments cover the full invoice total; revenue_amount_inr = realized paid INR on that invoice.
                                          </p>
                                        </div>
                                      </td>
                                    </tr>
                                  )}
                                </Fragment>
                              )
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </>
                )
              }

              if (drilldown === 'outstanding') {
                const rows = ddProjects
                  .filter(row => row.outstanding_inr > 0)
                  .map(row => ({ row, calc: computeProjectCalc(row) }))
                  .sort((a, b) => b.row.outstanding_inr - a.row.outstanding_inr)
                const total = rows.reduce((sum, item) => sum + item.row.outstanding_inr, 0)
                const matched = rows.filter(item => item.calc.outstandingMatched).length
                const recomputed = rows.reduce((sum, item) => sum + item.calc.expectedOutstandingInr, 0)
                const openInvoices = rows.flatMap(({ row }) => row.invoices.filter(inv => !isRevenueQualifyingInvoice(inv) && inv.balance_inr > 0).map(inv => ({ row, inv })))
                const overdueCount = openInvoices.filter(({ inv }) => (daysPending(inv.due_date) ?? 0) > 0).length
                return (
                  <>
                    <div className="sr-facts">
                      <div><span>Outstanding</span><strong>{inr(total)}</strong></div>
                      <div><span>Contributing projects</span><strong>{rows.length}</strong></div>
                      <div><span>Open invoices with balance</span><strong>{openInvoices.length}</strong></div>
                      <div>
                        <span>Validation / Overdue</span>
                        <strong>
                          <span className={`finance-status ${matched === rows.length && rows.length > 0 ? 'tone-success' : 'tone-danger'}`}>
                            {matched === rows.length && rows.length > 0 ? 'ALL MATCHED' : `${matched}/${rows.length} MATCHED`}
                          </span>{' '}
                          <span className={`finance-status ${overdueCount > 0 ? 'tone-warning' : 'tone-success'}`}>
                            {overdueCount} OVERDUE
                          </span>
                        </strong>
                      </div>
                    </div>
                    <div className="sr-facts">
                      <div><span>Recomputed total</span><strong>{inr(recomputed)}</strong></div>
                      <div><span>Unbilled open (baseline gap)</span><strong>{inr(rows.reduce((sum, item) => sum + item.calc.unbilledOpenSalesInr, 0))}</strong></div>
                      <div><span>Open invoice balance INR</span><strong>{inr(rows.reduce((sum, item) => sum + item.calc.openInvoiceBalanceInr, 0))}</strong></div>
                      <div><span>Formula</span><strong>unbilled + invoice balance</strong></div>
                    </div>
                    {rows.length === 0 ? (
                      <div className="sr-empty">No records available</div>
                    ) : (
                      <div className="sr-table-wrap">
                        <table className="sr-table">
                          <thead>
                            <tr>
                              <th>Project / Client</th>
                              <th>Sales Status</th>
                              <th>Unbilled Open INR</th>
                              <th>Open Invoice Balance INR</th>
                              <th>Outstanding INR</th>
                              <th>Validation</th>
                              <th>Calculation</th>
                            </tr>
                          </thead>
                          <tbody>
                            {rows.map(({ row, calc }) => {
                              const key = `outstanding-${row.project_id}`
                              const expanded = expandedCalcId === key
                const projectOpenInvoices = row.invoices.filter(inv => !isRevenueQualifyingInvoice(inv) && inv.balance_inr > 0)
                return (
                                  <Fragment key={row.project_id}>
                                    <tr>
                                      <td><strong>{row.project_code}</strong><br/><span>{row.project_name}</span><br/><small>{row.client_code || '—'} · {row.client_name}</small></td>
                                      <td><span className="sr-status">{row.sales_status}</span><br/><small>{projectPaymentStatus(row)}</small></td>
                                    <td>{inr(calc.unbilledOpenSalesInr)}</td>
                                    <td>{inr(calc.openInvoiceBalanceInr)}</td>
                                    <td><strong>{inr(row.outstanding_inr)}</strong></td>
                                    <td>
                                      <span className={`finance-status ${calc.outstandingMatched ? 'tone-success' : 'tone-danger'}`}>
                                        {calc.outstandingMatched ? 'MATCHED' : 'MISMATCH'}
                                      </span>
                                    </td>
                                    <td>
                                      <button className="finance-secondary-button" type="button" onClick={() => setExpandedCalcId(expanded ? null : key)}>
                                        {expanded ? <ChevronDown size={14}/> : <ChevronRight size={14}/>} {expanded ? 'Hide' : 'Show'}
                                      </button>
                                    </td>
                                  </tr>
                                  {expanded && (
                                    <tr>
                                      <td colSpan={7}>
                                        <div className="sr-calc-detail">
                                          <div className="sr-calc-steps">
                                            <div className="sr-calc-step"><span>Baseline open = max(sales − closed, 0)</span><strong>{inr(calc.baselineOpenSalesInr)}</strong></div>
                                            <div className="sr-calc-step"><span>Less: open invoice totals INR</span><strong>− {inr(calc.openInvoiceTotalInr)}</strong></div>
                                            <div className="sr-calc-step"><span>Unbilled open = max(baseline − open invoice total, 0)</span><strong>{inr(calc.unbilledOpenSalesInr)}</strong></div>
                                            <div className="sr-calc-step"><span>Open invoice balance INR</span><strong>{inr(calc.openInvoiceBalanceInr)}</strong></div>
                                            <div className="sr-calc-step"><span>Recomputed outstanding_inr = unbilled + balance</span><strong>{inr(calc.expectedOutstandingInr)}</strong></div>
                                            <div className="sr-calc-step"><span>API outstanding_inr</span><strong>{inr(row.outstanding_inr)}</strong></div>
                                          </div>
                                          <p className="sr-calc-formula">
                                            outstanding_inr = max(baseline_open − open_invoice_total, 0) + open_invoice_balance{row.sales_value_inr === 0 && calc.openInvoiceTotalInr > 0 ? '; special case sales_value_inr = 0 → outstanding_inr = open_invoice_balance' : ''}
                                          </p>
                                          {projectOpenInvoices.length === 0 ? (
                                            <div className="sr-empty compact">No open invoices with balance for this project.</div>
                                          ) : (
                                            <div className="sr-table-wrap" style={{ marginTop: 10 }}>
                                              <table className="sr-table">
                                                <thead>
                                                  <tr>
                                                    <th>Invoice</th>
                                                    <th>Status</th>
                                                    <th>Due Date</th>
                                                    <th>Days Pending</th>
                                                    <th>Balance INR</th>
                                                  </tr>
                                                </thead>
                                                <tbody>
                                                  {projectOpenInvoices.map(inv => {
                                                    const pending = daysPending(inv.due_date)
                                                    return (
                                                      <tr key={inv.id}>
                                                        <td><strong>{inv.invoice_number}</strong></td>
                                                        <td><span className="sr-status">{titleCase(inv.status)}</span></td>
                                                        <td>{inv.due_date}</td>
                                                        <td>
                                                          {pending == null ? '—' : (
                                                            <span className={`finance-status ${pending > 0 ? 'tone-danger' : 'tone-success'}`}>
                                                              {pending > 0 ? `${pending} day(s) overdue` : `${Math.abs(pending)} day(s) remaining`}
                                                            </span>
                                                          )}
                                                        </td>
                                                        <td><strong>{inr(inv.balance_inr)}</strong></td>
                                                      </tr>
                                                    )
                                                  })}
                                                </tbody>
                                              </table>
                                            </div>
                                          )}
                                        </div>
                                      </td>
                                    </tr>
                                  )}
                                </Fragment>
                              )
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </>
                )
              }

              const targetByDepartment = new Map(
                ddTargets.filter(row => row.month === targetMonth).map(row => [row.department_code, row])
              )
              const monthRevenue = ddRevenue.filter(row => row.revenue_date.slice(0, 7) === targetMonth)
              const targetDepartments = (lockedDepartment ?? department) === 'all'
                ? DEPARTMENTS
                : DEPARTMENTS.filter(([code]) => code === (lockedDepartment ?? department))
              const targetRows = targetDepartments.map(([code, label]) => {
                const targetRow = targetByDepartment.get(code)
                const events = monthRevenue.filter(row => row.department_code === code)
                const actual = events.reduce((sum, row) => sum + row.revenue_amount_inr, 0)
                const target = targetRow?.target_amount_inr || 0
                const remaining = Math.max(target - actual, 0)
                const achievement = target > 0 ? (actual / target) * 100 : 0
                const status = target <= 0
                  ? { label: 'Target not set', tone: 'tone-draft' }
                  : achievement >= 100
                    ? { label: 'Achieved', tone: 'tone-success' }
                    : achievement >= 50
                      ? { label: 'In progress', tone: 'tone-pending' }
                      : { label: 'Below target', tone: 'tone-warning' }
                return { code, label, target, actual, remaining, achievement, events, updatedBy: targetRow?.updated_by_name || null, status }
              })
              const targetTotal = targetRows.reduce((sum, row) => sum + row.target, 0)
              const actualTotal = targetRows.reduce((sum, row) => sum + row.actual, 0)
              const remainingTotal = Math.max(targetTotal - actualTotal, 0)
              const achievementTotal = targetTotal > 0 ? (actualTotal / targetTotal) * 100 : 0
              const rawTargetSum = ddTargets.filter(row => row.month === targetMonth).reduce((sum, row) => sum + row.target_amount_inr, 0)
              const monthRevenueSum = monthRevenue.reduce((sum, row) => sum + row.revenue_amount_inr, 0)
              const targetSumMatched = Math.abs(rawTargetSum - targetTotal) <= 0.01
              const actualSumMatched = Math.abs(monthRevenueSum - actualTotal) <= 0.01
              const expectedAchievement = targetTotal > 0 ? (actualTotal / targetTotal) * 100 : 0
              const achievementMatched = Math.abs(expectedAchievement - achievementTotal) <= 0.05

              return (
                <>
                  <div className="sr-facts">
                    <div><span>Target · {monthLabel(targetMonth)}</span><strong>{inr(targetTotal)}</strong></div>
                    <div><span>Actual Revenue</span><strong>{inr(actualTotal)}</strong></div>
                    <div><span>Remaining</span><strong>{inr(remainingTotal)}</strong></div>
                    <div><span>Achievement</span><strong>{achievementTotal.toFixed(1)}%</strong></div>
                  </div>
                  <div className="sr-facts">
                    <div>
                      <span>Target sum check</span>
                      <strong>
                        <span className={`finance-status ${targetSumMatched ? 'tone-success' : 'tone-danger'}`}>
                          {targetSumMatched ? 'MATCHED' : 'MISMATCH'}
                        </span>
                      </strong>
                    </div>
                    <div>
                      <span>Actual sum check</span>
                      <strong>
                        <span className={`finance-status ${actualSumMatched ? 'tone-success' : 'tone-danger'}`}>
                          {actualSumMatched ? 'MATCHED' : 'MISMATCH'}
                        </span>
                      </strong>
                    </div>
                    <div>
                      <span>Achievement recompute</span>
                      <strong>
                        <span className={`finance-status ${achievementMatched ? 'tone-success' : 'tone-danger'}`}>
                          {achievementMatched ? 'MATCHED' : 'MISMATCH'}
                        </span>
                      </strong>
                    </div>
                    <div><span>Revenue events in month</span><strong>{monthRevenue.length}</strong></div>
                  </div>
                  {targetRows.every(row => row.target === 0 && row.actual === 0) && monthRevenue.length === 0 ? (
                    <div className="sr-empty">No records available</div>
                  ) : (
                    <div className="sr-table-wrap">
                      <table className="sr-table">
                        <thead>
                          <tr>
                            <th>Department</th>
                            <th>Target INR</th>
                            <th>Actual INR</th>
                            <th>Remaining INR</th>
                            <th>Achievement</th>
                            <th>Events</th>
                            <th>Status</th>
                            <th>Calculation</th>
                          </tr>
                        </thead>
                        <tbody>
                          {targetRows.map(row => {
                            const key = `target-${row.code}`
                            const expanded = expandedCalcId === key
                            return (
                              <Fragment key={row.code}>
                                <tr>
                                  <td><strong>{row.label}</strong>{row.updatedBy ? <><br/><small>by {row.updatedBy}</small></> : null}</td>
                                  <td>{inr(row.target)}</td>
                                  <td><strong>{inr(row.actual)}</strong></td>
                                  <td>{inr(row.remaining)}</td>
                                  <td>{row.target > 0 ? `${row.achievement.toFixed(1)}%` : '—'}</td>
                                  <td>{row.events.length}</td>
                                  <td><span className={`finance-status ${row.status.tone}`}>{row.status.label}</span></td>
                                  <td>
                                    <button className="finance-secondary-button" type="button" onClick={() => setExpandedCalcId(expanded ? null : key)}>
                                      {expanded ? <ChevronDown size={14}/> : <ChevronRight size={14}/>} {expanded ? 'Hide' : 'Show'}
                                    </button>
                                  </td>
                                </tr>
                                {expanded && (
                                  <tr>
                                    <td colSpan={8}>
                                      <div className="sr-calc-detail">
                                        <div className="sr-calc-steps">
                                          <div className="sr-calc-step"><span>Department target from /finance/revenue-targets</span><strong>{inr(row.target)}</strong></div>
                                          <div className="sr-calc-step"><span>Sum of revenue_amount_inr where department = {row.label} and revenue month = {targetMonth}</span><strong>{inr(row.actual)}</strong></div>
                                          <div className="sr-calc-step"><span>Remaining = max(target − actual, 0)</span><strong>{inr(row.remaining)}</strong></div>
                                          <div className="sr-calc-step"><span>Achievement = actual ÷ target × 100</span><strong>{row.target > 0 ? `${row.achievement.toFixed(1)}%` : 'Target not set'}</strong></div>
                                        </div>
                                        <p className="sr-calc-formula">
                                          Actual Revenue only counts fully paid + closed Finance invoice events dated in {monthLabel(targetMonth)} for {row.label}.
                                        </p>
                                        {row.events.length === 0 ? (
                                          <div className="sr-empty compact">No records available</div>
                                        ) : (
                                          <div className="sr-table-wrap" style={{ marginTop: 10 }}>
                                            <table className="sr-table">
                                              <thead>
                                                <tr>
                                                  <th>Project</th>
                                                  <th>Invoice</th>
                                                  <th>Revenue Date</th>
                                                  <th>Revenue INR</th>
                                                  <th>Validation</th>
                                                </tr>
                                              </thead>
                                              <tbody>
                                                {row.events.map(event => {
                                                  const check = revenueEventCheck(event, ddProjects)
                                                  return (
                                                    <tr key={`${event.project_id}-${event.finance_invoice_number}`}>
                                                      <td><strong>{event.project_code}</strong><br/><small>{event.project_name}</small></td>
                                                      <td>{event.finance_invoice_number}</td>
                                                      <td>{event.revenue_date}</td>
                                                      <td><strong>{inr(event.revenue_amount_inr)}</strong></td>
                                                      <td>
                                                        <span className={`finance-status ${check.matched ? 'tone-success' : 'tone-danger'}`}>
                                                          {check.matched ? 'VERIFIED' : 'REVIEW'}
                                                        </span>
                                                      </td>
                                                    </tr>
                                                  )
                                                })}
                                              </tbody>
                                            </table>
                                          </div>
                                        )}
                                      </div>
                                    </td>
                                  </tr>
                                )}
                              </Fragment>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )
            })()}
          </section>
        </div>
      )}
    </div>
  )
}
