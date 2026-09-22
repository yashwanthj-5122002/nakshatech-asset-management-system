import { BarChart3, CalendarDays, CircleDollarSign, FileText, RefreshCcw, TrendingUp, WalletCards } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import './sales-revenue.css'

type Mode = 'sales' | 'revenue'
type Period = 'today' | 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'yearly' | 'custom'

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
  sales_value: number
  sales_value_inr: number
  open_sales_inr: number
  received_against_open_sales_inr: number
  outstanding_inr: number
  closed_revenue_inr: number
  sales_status: string
  sales_visible: boolean
  revenue_visible: boolean
  bd_sales_invoice: BDSalesInvoice
  invoice_count: number
  open_invoice_count: number
  closed_invoice_count: number
  invoices: InvoiceRow[]
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
}

const DEPARTMENTS = [
  ['ortho', 'ORTHO'],
  ['lidar', 'LiDAR'],
  ['mobile_mapping', 'Mobile Mapping'],
  ['laser_scanning', 'Laser Scanning'],
  ['civil', 'Civil'],
] as const

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
  const jan4Day = jan4.getUTCDay() || 7
  const monday = new Date(jan4)
  monday.setUTCDate(jan4.getUTCDate() - jan4Day + 1 + (week - 1) * 7)
  const sunday = new Date(monday)
  sunday.setUTCDate(monday.getUTCDate() + 6)
  return [isoDate(monday), isoDate(sunday)]
}

function monthRange(value: string): [string, string] {
  const [year, month] = value.split('-').map(Number)
  if (!year || !month) return [currentDate(), currentDate()]
  return [
    `${year}-${String(month).padStart(2, '0')}-01`,
    isoDate(new Date(Date.UTC(year, month, 0))),
  ]
}

function quarterRange(year: number, quarter: number): [string, string] {
  const startMonth = (quarter - 1) * 3
  return [
    isoDate(new Date(Date.UTC(year, startMonth, 1))),
    isoDate(new Date(Date.UTC(year, startMonth + 3, 0))),
  ]
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

function BarPanel({ title, subtitle, rows }: { title: string; subtitle: string; rows: Array<{ label: string; value: number; secondary?: number }> }) {
  const max = Math.max(1, ...rows.flatMap(row => [row.value, row.secondary || 0]))
  return <article className="sr-panel sr-chart-panel">
    <div className="sr-panel-heading"><div><span>VISUAL ANALYTICS</span><h3>{title}</h3><p>{subtitle}</p></div><BarChart3 size={19}/></div>
    {rows.length === 0 ? <div className="sr-empty">No data for the selected filters.</div> :
      <div className="sr-bars">{rows.map(row => <div className="sr-bar-row" key={row.label}>
        <div className="sr-bar-label"><strong>{row.label}</strong><span>{inr(row.value)}{row.secondary != null ? ` · received ${inr(row.secondary)}` : ''}</span></div>
        <div className="sr-bar-track"><i style={{ width: `${Math.max(2, (row.value / max) * 100)}%` }}/></div>
        {row.secondary != null && <div className="sr-bar-track secondary"><i style={{ width: `${Math.max(2, (row.secondary / max) * 100)}%` }}/></div>}
      </div>)}</div>}
  </article>
}

export function SalesRevenuePage({ mode }: { mode: Mode }) {
  const [data, setData] = useState<Overview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [period, setPeriod] = useState<Period>('monthly')
  const [day, setDay] = useState(currentDate)
  const [week, setWeek] = useState(currentWeek)
  const [month, setMonth] = useState(currentMonth)
  const [quarter, setQuarter] = useState(Math.floor(new Date().getMonth() / 3) + 1)
  const [year, setYear] = useState(new Date().getFullYear())
  const [from, setFrom] = useState(`${new Date().getFullYear()}-01-01`)
  const [to, setTo] = useState(currentDate)
  const [department, setDepartment] = useState('all')
  const [client, setClient] = useState('all')
  const [project, setProject] = useState('all')
  const [bd, setBd] = useState('all')
  const [pm, setPm] = useState('all')
  const [currency, setCurrency] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [salesDateBasis, setSalesDateBasis] = useState<'projected' | 'booked'>('projected')
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null)
  const [selectedInvoiceNumber, setSelectedInvoiceNumber] = useState<string | null>(null)
  const [detailTab, setDetailTab] = useState<'sales' | 'finance' | 'payments'>('sales')

  function load() {
    setLoading(true)
    setError('')
    void apiFetch<Overview>('/finance/sales-revenue')
      .then(setData)
      .catch(err => setError(err instanceof Error ? err.message : 'Unable to load Sales and Revenue analytics'))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const range = useMemo(() => dateRange(period, { day, week, month, quarter, year, from, to }), [period, day, week, month, quarter, year, from, to])
  const allProjects = data?.projects ?? []
  const allRevenue = data?.revenue_events ?? []

  const options = useMemo(() => {
    const source = allProjects
    const unique = (values: string[]) => [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b))
    return {
      clients: unique(source.map(row => row.client_name)),
      projects: unique(source.map(row => row.project_code)),
      bd: unique(source.map(row => row.bd_name)),
      pm: unique(source.map(row => row.project_manager_name)),
      currencies: unique(source.map(row => row.currency)),
      statuses: unique(source.map(row => row.sales_status)),
    }
  }, [allProjects])

  function dimensionsMatch(row: { department_code: string; client_name: string; project_code: string; bd_name: string; project_manager_name: string; currency: string }) {
    return (department === 'all' || row.department_code === department)
      && (client === 'all' || row.client_name === client)
      && (project === 'all' || row.project_code === project)
      && (bd === 'all' || row.bd_name === bd)
      && (pm === 'all' || row.project_manager_name === pm)
      && (currency === 'all' || row.currency === currency)
  }

  const salesRows = useMemo(() => allProjects.filter(row =>
    row.sales_visible
    && dateInside(salesDateBasis === 'projected' ? row.projected_payment_date : row.sales_date, range)
    && dimensionsMatch(row)
    && (statusFilter === 'all' || row.sales_status === statusFilter)
  ), [allProjects, range, department, client, project, bd, pm, currency, statusFilter, salesDateBasis])

  const revenueRows = useMemo(() => allRevenue.filter(row =>
    dateInside(row.revenue_date, range)
    && dimensionsMatch(row)
  ), [allRevenue, range, department, client, project, bd, pm, currency])

  const activeRows = mode === 'sales' ? salesRows : revenueRows
  const selectedProject = selectedProjectId == null ? null : allProjects.find(row => row.project_id === selectedProjectId) ?? null
  const selectedInvoice = selectedProject?.invoices.find(row => row.invoice_number === selectedInvoiceNumber)
    ?? (mode === 'revenue' ? selectedProject?.invoices.find(row => row.status === 'INVOICE_CLOSED') : selectedProject?.invoices[0])
    ?? null

  const salesKpis = useMemo(() => {
    const openSales = salesRows.reduce((sum, row) => sum + row.open_sales_inr, 0)
    const received = salesRows.reduce((sum, row) => sum + row.received_against_open_sales_inr, 0)
    const outstanding = salesRows.reduce((sum, row) => sum + row.outstanding_inr, 0)
    const invoiced = salesRows.reduce((sum, row) => sum + row.invoices.filter(inv => inv.status !== 'INVOICE_CLOSED').reduce((s, inv) => s + inv.total_inr, 0), 0)
    return {
      openSales,
      received,
      outstanding,
      invoiced,
      partial: salesRows.filter(row => row.sales_status === 'Partially Paid').length,
      overdue: salesRows.filter(row => row.sales_status === 'Overdue').length,
    }
  }, [salesRows])

  const revenueKpis = useMemo(() => {
    const total = revenueRows.reduce((sum, row) => sum + row.revenue_amount_inr, 0)
    return {
      total,
      invoices: revenueRows.length,
      projects: new Set(revenueRows.map(row => row.project_id)).size,
      average: revenueRows.length ? total / revenueRows.length : 0,
    }
  }, [revenueRows])

  const monthlyChart = useMemo(() => {
    const map = new Map<string, { value: number; secondary: number }>()
    if (mode === 'sales') {
      for (const row of salesRows) {
        const chartDate = salesDateBasis === 'projected' ? row.projected_payment_date : row.sales_date
        if (!chartDate) continue
        const key = chartDate.slice(0, 7)
        const item = map.get(key) || { value: 0, secondary: 0 }
        item.value += row.open_sales_inr
        item.secondary += row.received_against_open_sales_inr
        map.set(key, item)
      }
    } else {
      for (const row of revenueRows) {
        const key = row.revenue_date.slice(0, 7)
        const item = map.get(key) || { value: 0, secondary: 0 }
        item.value += row.revenue_amount_inr
        map.set(key, item)
      }
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([key, value]) => ({ label: monthLabel(key), value: value.value, secondary: mode === 'sales' ? value.secondary : undefined }))
  }, [mode, salesRows, revenueRows, salesDateBasis])

  const departmentChart = useMemo(() => {
    const map = new Map<string, number>()
    if (mode === 'sales') for (const row of salesRows) map.set(row.department_label, (map.get(row.department_label) || 0) + row.open_sales_inr)
    else for (const row of revenueRows) map.set(row.department_label, (map.get(row.department_label) || 0) + row.revenue_amount_inr)
    return [...map.entries()].sort((a, b) => b[1] - a[1]).map(([label, value]) => ({ label, value }))
  }, [mode, salesRows, revenueRows])

  const thirdChart = useMemo(() => {
    const map = new Map<string, number>()
    if (mode === 'sales') for (const row of salesRows) map.set(row.sales_status, (map.get(row.sales_status) || 0) + row.open_sales_inr)
    else for (const row of revenueRows) map.set(row.client_name || 'Unknown client', (map.get(row.client_name || 'Unknown client') || 0) + row.revenue_amount_inr)
    return [...map.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8).map(([label, value]) => ({ label, value }))
  }, [mode, salesRows, revenueRows])

  function resetDimensions() {
    setDepartment('all'); setClient('all'); setProject('all'); setBd('all'); setPm('all'); setCurrency('all'); setStatusFilter('all')
  }

  function openSales(row: SalesProject) {
    setSelectedProjectId(row.project_id)
    setSelectedInvoiceNumber(row.invoices[0]?.invoice_number ?? null)
    setDetailTab('sales')
  }

  function openRevenue(row: RevenueEvent) {
    setSelectedProjectId(row.project_id)
    setSelectedInvoiceNumber(row.finance_invoice_number)
    setDetailTab('finance')
  }

  const periodLabel = `${range[0]} to ${range[1]}`

  return <div className="sr-page">
    <DashboardHeader
      eyebrow={mode === 'sales' ? 'FINANCE · SALES PIPELINE' : 'FINANCE · REALIZED REVENUE'}
      title={mode === 'sales' ? 'Sales' : 'Revenue'}
      description={mode === 'sales'
        ? 'BD commercial value and every still-open collection remain here, including pending, partial, overdue and fully paid invoices awaiting Finance closure.'
        : 'Only Finance invoices that are fully paid and closed appear here. Revenue is actual realized money, never a forecast.'}
      actions={<button className="finance-secondary-button" type="button" onClick={load}><RefreshCcw size={16}/> Refresh</button>}
    />

    <section className="sr-filter-panel">
      <div className="sr-filter-title"><CalendarDays size={18}/><div><strong>Analytics filters</strong><span>Every KPI, table and chart below follows the same selection.</span></div></div>
      <div className="sr-filter-grid">
        <label><span>Period</span><select value={period} onChange={e => setPeriod(e.target.value as Period)}>
          <option value="today">Today</option><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option><option value="quarterly">Quarterly</option><option value="yearly">Yearly</option><option value="custom">Custom Range</option>
        </select></label>
        {period === 'daily' && <label><span>Date</span><input type="date" value={day} onChange={e => setDay(e.target.value)}/></label>}
        {period === 'weekly' && <label><span>Week</span><input type="week" value={week} onChange={e => setWeek(e.target.value)}/></label>}
        {period === 'monthly' && <label><span>Month</span><input type="month" value={month} onChange={e => setMonth(e.target.value)}/></label>}
        {period === 'quarterly' && <><label><span>Year</span><input type="number" min="2000" max="2100" value={year} onChange={e => setYear(Number(e.target.value))}/></label><label><span>Quarter</span><select value={quarter} onChange={e => setQuarter(Number(e.target.value))}><option value={1}>Q1</option><option value={2}>Q2</option><option value={3}>Q3</option><option value={4}>Q4</option></select></label></>}
        {period === 'yearly' && <label><span>Year</span><input type="number" min="2000" max="2100" value={year} onChange={e => setYear(Number(e.target.value))}/></label>}
        {period === 'custom' && <><label><span>From</span><input type="date" value={from} onChange={e => setFrom(e.target.value)}/></label><label><span>To</span><input type="date" value={to} onChange={e => setTo(e.target.value)}/></label></>}

        <label><span>Department</span><select value={department} onChange={e => setDepartment(e.target.value)}><option value="all">All Departments</option>{DEPARTMENTS.map(([code, label]) => <option key={code} value={code}>{label}</option>)}</select></label>
        <label><span>Client</span><select value={client} onChange={e => setClient(e.target.value)}><option value="all">All Clients</option>{options.clients.map(v => <option key={v}>{v}</option>)}</select></label>
        <label><span>Project</span><select value={project} onChange={e => setProject(e.target.value)}><option value="all">All Projects</option>{options.projects.map(v => <option key={v}>{v}</option>)}</select></label>
        <label><span>BD Person</span><select value={bd} onChange={e => setBd(e.target.value)}><option value="all">All BD</option>{options.bd.map(v => <option key={v}>{v}</option>)}</select></label>
        <label><span>Project Manager</span><select value={pm} onChange={e => setPm(e.target.value)}><option value="all">All PMs</option>{options.pm.map(v => <option key={v}>{v}</option>)}</select></label>
        <label><span>Currency</span><select value={currency} onChange={e => setCurrency(e.target.value)}><option value="all">All Currencies</option>{options.currencies.map(v => <option key={v}>{v}</option>)}</select></label>
        {mode === 'sales' && <label><span>Sales Date Basis</span><select value={salesDateBasis} onChange={e => setSalesDateBasis(e.target.value as 'projected' | 'booked')}><option value="projected">Projected Payment Date</option><option value="booked">BD Sales / Commercial Date</option></select></label>}
        {mode === 'sales' && <label><span>Payment Status</span><select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}><option value="all">All Statuses</option>{options.statuses.map(v => <option key={v}>{v}</option>)}</select></label>}
        <button className="sr-reset" type="button" onClick={resetDimensions}>Clear dimension filters</button>
      </div>
      <div className="sr-range-note">Showing {mode} for <strong>{periodLabel}</strong></div>
    </section>

    {error && <div className="finance-error">{error}</div>}
    {loading && <div className="finance-panel finance-empty-state">Loading {mode} intelligence...</div>}

    {!loading && !error && <>

      {mode === 'sales' ? <section className="sr-kpi-grid">
        <article><TrendingUp/><span>Open Sales Pipeline</span><strong>{inr(salesKpis.openSales)}</strong><small>{salesRows.length} project(s) in selected period</small></article>
        <article><FileText/><span>Open Invoiced</span><strong>{inr(salesKpis.invoiced)}</strong><small>Finance invoices not yet closed</small></article>
        <article><WalletCards/><span>Received on Open Sales</span><strong>{inr(salesKpis.received)}</strong><small>Still stays in Sales until invoice closure</small></article>
        <article><CircleDollarSign/><span>Outstanding</span><strong>{inr(salesKpis.outstanding)}</strong><small>{salesKpis.partial} partial · {salesKpis.overdue} overdue</small></article>
      </section> : <section className="sr-kpi-grid">
        <article><CircleDollarSign/><span>Realized Revenue</span><strong>{inr(revenueKpis.total)}</strong><small>Fully received + invoice closed only</small></article>
        <article><FileText/><span>Closed Invoices</span><strong>{revenueKpis.invoices}</strong><small>In selected period</small></article>
        <article><TrendingUp/><span>Revenue Projects</span><strong>{revenueKpis.projects}</strong><small>Distinct projects realized</small></article>
        <article><WalletCards/><span>Average Closed Invoice</span><strong>{inr(revenueKpis.average)}</strong><small>Realized average in selected period</small></article>
      </section>}

      <section className="sr-chart-grid">
        <BarPanel title={mode === 'sales' ? 'Monthly Sales vs Received' : 'Monthly Revenue Trend'} subtitle={mode === 'sales' ? 'Open sales pipeline compared with money already received on still-open invoices.' : 'Actual realized revenue by final payment/closure period.'} rows={monthlyChart}/>
        <BarPanel title={mode === 'sales' ? 'Department-wise Sales' : 'Department-wise Revenue'} subtitle="Compare ORTHO, LiDAR, Mobile Mapping, Laser Scanning and Civil under the current filters." rows={departmentChart}/>
        <BarPanel title={mode === 'sales' ? 'Payment Status Exposure' : 'Top Clients by Revenue'} subtitle={mode === 'sales' ? 'Where open sales money currently sits in the collection lifecycle.' : 'Clients contributing the most realized revenue in this selection.'} rows={thirdChart}/>
      </section>

      <section className="sr-panel">
        <div className="sr-panel-heading"><div><span>{mode === 'sales' ? 'LIVE MONEY PIPELINE' : 'CLOSED & REALIZED MONEY'}</span><h3>{mode === 'sales' ? 'Sales Projects' : 'Revenue Register'}</h3><p>{mode === 'sales' ? 'A project remains here until the relevant invoice is fully paid and Finance closes it.' : 'Every row below is backed by a closed Finance invoice and completed payment.'}</p></div><strong>{activeRows.length}</strong></div>
        {activeRows.length === 0 ? <div className="sr-empty">No {mode} records match the selected filters.</div> :
          <div className="sr-table-wrap"><table className="sr-table"><thead><tr>
            <th>Project / Client</th><th>BD / Department / PM</th><th>Currency</th>
            {mode === 'sales' ? <><th>Sales / Invoice</th><th>Projected Payment</th><th>Received / Outstanding</th><th>Status</th></> : <><th>Finance Invoice</th><th>Revenue Date</th><th>Payment Received</th><th>Status</th></>}
            <th>Action</th>
          </tr></thead><tbody>
            {mode === 'sales' ? salesRows.map(row => <tr key={row.project_id}>
              <td><strong>{row.project_code}</strong><br/><span>{row.project_name}</span><br/><small>{row.client_code || '—'} · {row.client_name}</small></td>
              <td><strong>{row.bd_name}</strong><br/><span>{row.department_label}</span><br/><small>PM: {row.project_manager_name}</small></td>
              <td>{row.currency}</td>
              <td><strong>{inr(row.open_sales_inr)}</strong><br/><small>{row.bd_sales_invoice.reference || 'Commercial Rev ' + (row.bd_sales_invoice.revision_no || 1)} · {row.invoice_count} Finance invoice(s)</small></td>
              <td>{row.projected_payment_date || '—'}</td>
              <td><strong>{inr(row.received_against_open_sales_inr)}</strong><br/><small>Outstanding {inr(row.outstanding_inr)}</small></td>
              <td><span className="sr-status">{row.sales_status}</span></td>
              <td><button className="finance-secondary-button" onClick={() => openSales(row)}>Project details</button></td>
            </tr>) : revenueRows.map(row => <tr key={`${row.project_id}-${row.finance_invoice_number}`}>
              <td><strong>{row.project_code}</strong><br/><span>{row.project_name}</span><br/><small>{row.client_code || '—'} · {row.client_name}</small></td>
              <td><strong>{row.bd_name}</strong><br/><span>{row.department_label}</span><br/><small>PM: {row.project_manager_name}</small></td>
              <td>{row.currency}</td>
              <td><strong>{row.finance_invoice_number}</strong><br/><small>{row.finance_invoice_date} · {money(row.finance_invoice_amount, row.currency)}</small></td>
              <td>{row.revenue_date}<br/><small>Closed {row.invoice_closed_at ? row.invoice_closed_at.slice(0, 10) : '—'}</small></td>
              <td><strong>{inr(row.revenue_amount_inr)}</strong><br/><small>Final payment {row.final_payment_date || '—'}</small></td>
              <td><span className="sr-status success">Revenue Realized</span></td>
              <td><button className="finance-secondary-button" onClick={() => openRevenue(row)}>Project details</button></td>
            </tr>)}
          </tbody></table></div>}
      </section>

      {selectedProject && <section className="sr-panel sr-detail">
        <div className="sr-panel-heading"><div><span>PROJECT FINANCIAL DETAIL</span><h3>{selectedProject.project_code} — {selectedProject.project_name}</h3><p>{selectedProject.client_code || '—'} · {selectedProject.client_name} · {selectedProject.department_label} · PM {selectedProject.project_manager_name}</p></div><button className="finance-secondary-button" onClick={() => { setSelectedProjectId(null); setSelectedInvoiceNumber(null) }}>Close</button></div>

        <div className="sr-detail-tabs">
          <button className={detailTab === 'sales' ? 'active' : ''} onClick={() => setDetailTab('sales')}>View BD Sales Invoice</button>
          <button className={detailTab === 'finance' ? 'active' : ''} onClick={() => setDetailTab('finance')}>View Finance Invoice</button>
          <button className={detailTab === 'payments' ? 'active' : ''} onClick={() => setDetailTab('payments')}>View Payment History</button>
        </div>

        {detailTab === 'sales' && <div className="sr-facts">
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
        </div>}

        {detailTab === 'finance' && <>{selectedProject.invoices.length === 0 ? <div className="sr-empty">Finance has not generated an invoice for this project yet.</div> : <>
          <div className="sr-invoice-picker">{selectedProject.invoices.map(inv => <button key={inv.id} className={selectedInvoice?.id === inv.id ? 'active' : ''} onClick={() => setSelectedInvoiceNumber(inv.invoice_number)}>{inv.invoice_number}</button>)}</div>
          {selectedInvoice && <div className="sr-facts">
            <div><span>Finance Invoice</span><strong>{selectedInvoice.invoice_number}</strong></div><div><span>Status</span><strong>{titleCase(selectedInvoice.status)}</strong></div>
            <div><span>Invoice Date</span><strong>{selectedInvoice.invoice_date}</strong></div><div><span>Due Date</span><strong>{selectedInvoice.due_date}</strong></div>
            <div><span>Currency</span><strong>{selectedInvoice.currency}</strong></div><div><span>Invoice Total</span><strong>{money(selectedInvoice.total_amount, selectedInvoice.currency)}</strong></div>
            <div><span>Invoice INR</span><strong>{inr(selectedInvoice.total_inr)}</strong></div><div><span>Paid INR</span><strong>{inr(selectedInvoice.paid_inr)}</strong></div>
            <div><span>Outstanding INR</span><strong>{inr(selectedInvoice.balance_inr)}</strong></div><div><span>Closed At</span><strong>{selectedInvoice.closed_at ? selectedInvoice.closed_at.replace('T', ' ').slice(0, 19) : 'Not closed'}</strong></div>
            <div className="wide"><span>Finance Remarks</span><strong>{selectedInvoice.notes || '—'}</strong></div>
          </div>}
        </>}</>}

        {detailTab === 'payments' && <>{selectedProject.invoices.length === 0 ? <div className="sr-empty">No Finance invoice or payment exists yet.</div> : selectedProject.invoices.map(inv => <div className="sr-payment-block" key={inv.id}>
          <h4>{inv.invoice_number} <span>{titleCase(inv.status)}</span></h4>
          {inv.payments.length === 0 ? <div className="sr-empty compact">No payment recorded.</div> : <div className="sr-table-wrap"><table className="sr-table"><thead><tr><th>Date</th><th>Reference</th><th>Amount</th><th>INR Realized</th><th>Mode</th><th>Remarks</th></tr></thead><tbody>{inv.payments.map(payment => <tr key={payment.id}><td>{payment.payment_date}</td><td>{payment.payment_reference}</td><td>{money(payment.amount, payment.currency)}</td><td>{inr(payment.amount_inr)}</td><td>{titleCase(payment.payment_mode)}</td><td>{payment.comments || '—'}</td></tr>)}</tbody></table></div>}
        </div>)}</>}
      </section>}
    </>}
  </div>
}
