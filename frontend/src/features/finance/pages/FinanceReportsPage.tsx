import { AlertTriangle, CalendarRange, ChevronLeft, ChevronRight, Download, FileSpreadsheet, Search, ShieldCheck } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch, downloadFile } from '../../../lib/api'
import type { FinanceClaimStatus, FinanceClaimType, FinanceProject, FinanceReport, FinanceReportPeriod } from '../../../types'
import { financeClaimTypeLabels, financeExpenseCategories, financeStatusLabels, financeStatusTone, formatInr } from '../finance-utils'
import '../finance-expenses.css'

const now = new Date()
const defaultQuarter = Math.floor(now.getMonth() / 3) + 1

function monthLabel(month: number): string {
  return new Intl.DateTimeFormat('en-IN', { month: 'long' }).format(new Date(2026, month - 1, 1))
}

function buildQuery(values: Record<string, string | number | undefined | null>): string {
  const params = new URLSearchParams()
  Object.entries(values).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '' || value === 'all') return
    params.set(key, String(value))
  })
  return params.toString()
}

function MiniBreakdown({ title, items }: { title: string; items: FinanceReport['by_project'] }) {
  const max = useMemo(() => Math.max(1, ...items.map(item => item.amount)), [items])
  return (
    <article className="finance-panel finance-report-breakdown">
      <div className="finance-panel-header"><div><span className="finance-panel-kicker">HISTORICAL ANALYTICS</span><h2>{title}</h2></div></div>
      {items.length === 0 ? <div className="finance-empty-state">No data in this period.</div> : (
        <div className="finance-breakdown-list">
          {items.slice(0, 7).map(item => (
            <div className="finance-breakdown-row" key={item.key}>
              <div><span>{item.label}</span><span>{formatInr(item.amount)} · {item.count}</span></div>
              <div className="finance-breakdown-track"><i style={{ width: `${Math.max(4, item.amount / max * 100)}%` }} /></div>
            </div>
          ))}
        </div>
      )}
    </article>
  )
}

export function FinanceReportsPage() {
  const [projects, setProjects] = useState<FinanceProject[]>([])
  const [data, setData] = useState<FinanceReport | null>(null)
  const [period, setPeriod] = useState<FinanceReportPeriod>('month')
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [quarter, setQuarter] = useState(defaultQuarter)
  const [projectId, setProjectId] = useState('all')
  const [claimType, setClaimType] = useState<'all' | FinanceClaimType>('all')
  const [status, setStatus] = useState<'all' | FinanceClaimStatus>('all')
  const [category, setCategory] = useState('all')
  const [employee, setEmployee] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [downloading, setDownloading] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    void apiFetch<FinanceProject[]>('/finance/report-projects').then(setProjects).catch(() => undefined)
  }, [])

  const queryString = useMemo(() => buildQuery({
    period,
    year: period === 'all' ? undefined : year,
    month: period === 'month' ? month : undefined,
    quarter: period === 'quarter' ? quarter : undefined,
    project_id: projectId,
    claim_type: claimType,
    status,
    employee: employee.trim() || undefined,
    category,
    search: search.trim() || undefined,
    page,
    page_size: 50,
  }), [period, year, month, quarter, projectId, claimType, status, employee, category, search, page])

  useEffect(() => {
    setLoading(true)
    setError('')
    void apiFetch<FinanceReport>(`/finance/reports?${queryString}`)
      .then(setData)
      .catch(err => setError(err instanceof Error ? err.message : 'Could not load Finance historical report'))
      .finally(() => setLoading(false))
  }, [queryString])

  function resetPage() {
    setPage(1)
  }

  async function exportReport(kind: 'selected' | 'month' | 'quarter' | 'year') {
    const exportPeriod = kind === 'selected' ? period : kind
    const query = buildQuery({
      period: exportPeriod,
      year: exportPeriod === 'all' ? undefined : year,
      month: exportPeriod === 'month' ? month : undefined,
      quarter: exportPeriod === 'quarter' ? quarter : undefined,
      project_id: projectId,
      claim_type: claimType,
      status,
      employee: employee.trim() || undefined,
      category,
      search: search.trim() || undefined,
    })
    setDownloading(kind)
    setError('')
    try {
      await downloadFile(`/finance/reports/export.xlsx?${query}`, `NakshaTech_Finance_${exportPeriod}.xlsx`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not download Finance Excel report')
    } finally {
      setDownloading('')
    }
  }

  const years = Array.from(new Set([year, ...(data?.available_years || [])])).sort((a, b) => b - a)

  return (
    <div className="finance-page">
      <DashboardHeader
        eyebrow="FINANCE CRM · HISTORICAL LEDGER"
        title="Finance Reports & Excel"
        description="Search years of project-expense history, reconcile approvals and payments, and download database-backed monthly, quarterly, yearly, or all-time Excel workbooks."
        actions={<button className="finance-primary-button" type="button" onClick={() => exportReport('selected')} disabled={Boolean(downloading)}><Download size={16} /> {downloading === 'selected' ? 'Preparing Excel...' : 'Download Current View'}</button>}
      />

      <section className="finance-report-control-panel">
        <div className="finance-report-period-tabs" role="tablist" aria-label="Finance report period">
          {(['month', 'quarter', 'year', 'all'] as FinanceReportPeriod[]).map(value => (
            <button key={value} type="button" className={period === value ? 'active' : ''} onClick={() => { setPeriod(value); resetPage() }}>
              {value === 'month' ? 'Monthly' : value === 'quarter' ? 'Quarterly' : value === 'year' ? 'Yearly' : 'All Time'}
            </button>
          ))}
        </div>

        <div className="finance-report-filters">
          {period !== 'all' && <label className="finance-field"><span>Year</span><select value={year} onChange={event => { setYear(Number(event.target.value)); resetPage() }}>{years.map(value => <option key={value} value={value}>{value}</option>)}</select></label>}
          {period === 'month' && <label className="finance-field"><span>Month</span><select value={month} onChange={event => { setMonth(Number(event.target.value)); resetPage() }}>{Array.from({ length: 12 }, (_, index) => index + 1).map(value => <option key={value} value={value}>{monthLabel(value)}</option>)}</select></label>}
          {period === 'quarter' && <label className="finance-field"><span>Quarter</span><select value={quarter} onChange={event => { setQuarter(Number(event.target.value)); resetPage() }}>{[1, 2, 3, 4].map(value => <option key={value} value={value}>Q{value}</option>)}</select></label>}
          <label className="finance-field"><span>Project</span><select value={projectId} onChange={event => { setProjectId(event.target.value); resetPage() }}><option value="all">All projects</option>{projects.map(project => <option key={project.id} value={project.id}>{project.project_code} · {project.project_name}</option>)}</select></label>
          <label className="finance-field"><span>Request Type</span><select value={claimType} onChange={event => { setClaimType(event.target.value as 'all' | FinanceClaimType); resetPage() }}><option value="all">All request types</option>{Object.entries(financeClaimTypeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label className="finance-field"><span>Status</span><select value={status} onChange={event => { setStatus(event.target.value as 'all' | FinanceClaimStatus); resetPage() }}><option value="all">All statuses</option>{Object.entries(financeStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label className="finance-field"><span>Category</span><select value={category} onChange={event => { setCategory(event.target.value); resetPage() }}><option value="all">All categories</option>{financeExpenseCategories.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label className="finance-field"><span>Employee</span><input value={employee} onChange={event => { setEmployee(event.target.value); resetPage() }} placeholder="Name or email" /></label>
          <label className="finance-field finance-report-search"><span>Search Ledger</span><div><Search size={15} /><input value={search} onChange={event => { setSearch(event.target.value); resetPage() }} placeholder="Claim ID, project, purpose..." /></div></label>
        </div>

        <div className="finance-report-export-row">
          <span><FileSpreadsheet size={16} /> Standard Finance Exports</span>
          <button type="button" onClick={() => exportReport('month')} disabled={Boolean(downloading)}><Download size={14} /> Monthly Excel</button>
          <button type="button" onClick={() => exportReport('quarter')} disabled={Boolean(downloading)}><Download size={14} /> Quarterly Excel</button>
          <button type="button" onClick={() => exportReport('year')} disabled={Boolean(downloading)}><Download size={14} /> Yearly Excel</button>
        </div>
      </section>

      {error && <div className="finance-error">{error}</div>}
      {loading && <div className="finance-panel finance-empty-state">Loading Finance ledger...</div>}

      {data && !loading && (
        <>
          <div className="finance-report-period-banner"><CalendarRange size={17} /><div><strong>{data.period_label}</strong><span>{data.start_date && data.end_date ? `${data.start_date} → ${data.end_date}` : 'Complete Finance history'} · {data.total_records} claim(s)</span></div></div>

          <section className="finance-kpi-grid finance-kpi-grid-4">
            <article className="finance-kpi-card"><span>Requested</span><strong>{formatInr(data.requested_amount)}</strong><small>Original employee request value</small></article>
            <article className="finance-kpi-card"><span>Finance Approved</span><strong>{formatInr(data.approved_amount)}</strong><small>Approved amount preserved separately</small></article>
            <article className="finance-kpi-card"><span>Paid Against Claims</span><strong>{formatInr(data.paid_amount)}</strong><small>Cumulative payment against claims submitted in this period</small></article>
            <article className="finance-kpi-card"><span>Outstanding</span><strong>{formatInr(data.outstanding_amount)}</strong><small>Approved but not yet fully settled</small></article>
          </section>

          <section className="finance-kpi-grid finance-kpi-grid-4 finance-kpi-grid-secondary">
            <article className="finance-kpi-card"><span>Cash Paid in Period</span><strong>{formatInr(data.payment_period_amount)}</strong><small>{data.payment_period_count} payment transaction(s) dated in this period</small></article>
            <article className="finance-kpi-card"><span>Pending Admin</span><strong>{formatInr(data.pending_admin_amount)}</strong><small>Awaiting legitimacy verification</small></article>
            <article className="finance-kpi-card"><span>Pending Finance</span><strong>{formatInr(data.pending_finance_amount)}</strong><small>Admin-verified and awaiting Finance</small></article>
            <article className={`finance-kpi-card ${data.integrity_issue_count ? 'finance-integrity-card-warning' : ''}`}><span><ShieldCheck size={15} /> Integrity Review</span><strong>{data.integrity_issue_count}</strong><small>{data.integrity_issue_count ? 'Record(s) require Finance review' : `${years.length} reporting year(s) available`}</small></article>
          </section>

          <div className="finance-report-accounting-note"><FileSpreadsheet size={16} /><span><strong>Period accounting:</strong> claim totals follow the claim submission date; <strong>Cash Paid in Period</strong> follows each payment transaction date. This keeps monthly, quarterly, and yearly cash reporting accurate even when an older claim is paid later.</span></div>

          {data.integrity_issue_count > 0 && <div className="finance-integrity-alert"><AlertTriangle size={17} /><div><strong>Data integrity review required</strong><span>The Excel workbook includes a Data Integrity sheet identifying the exact records. No record is automatically modified.</span></div></div>}

          <section className="finance-breakdown-grid">
            <MiniBreakdown title="Project-wise Requested Spend" items={data.by_project} />
            <MiniBreakdown title="Employee-wise Requested Spend" items={data.by_employee} />
            <MiniBreakdown title="Category-wise Spend" items={data.by_category} />
          </section>

          <section className="finance-panel">
            <div className="finance-panel-header">
              <div><span className="finance-panel-kicker">AUDITABLE FINANCE LEDGER</span><h2>Historical Claims</h2><p>Requested, approved, paid, and outstanding values remain separate so reports can be reconciled years later.</p></div>
              <span className="finance-history-count">Page {data.page} of {data.total_pages}</span>
            </div>
            {data.claims.length === 0 ? <div className="finance-empty-state">No Finance records match this period and filter combination.</div> : (
              <div className="finance-table-wrap"><table className="finance-table finance-report-table">
                <thead><tr><th>Claim</th><th>Date</th><th>Employee</th><th>Project</th><th>Type</th><th>Requested</th><th>Approved</th><th>Paid</th><th>Outstanding</th><th>Status</th><th>Evidence</th></tr></thead>
                <tbody>{data.claims.map(claim => (
                  <tr key={claim.id}>
                    <td><Link to={`/finance/claims/${claim.id}`}>{claim.claim_code}</Link></td>
                    <td>{claim.submitted_at ? new Date(claim.submitted_at).toLocaleDateString('en-IN') : 'Legacy'}</td>
                    <td><strong>{claim.requester_name}</strong><br/><small>{claim.requester_email}</small></td>
                    <td><strong>{claim.project_code}</strong><br/><small>{claim.project_name}</small></td>
                    <td>{financeClaimTypeLabels[claim.claim_type]}</td>
                    <td>{formatInr(claim.requested_amount)}</td>
                    <td>{formatInr(claim.approved_amount)}</td>
                    <td>{formatInr(claim.paid_amount)}</td>
                    <td><strong>{formatInr(claim.outstanding_amount)}</strong></td>
                    <td><span className={`finance-status tone-${financeStatusTone(claim.status)}`}>{financeStatusLabels[claim.status]}</span></td>
                    <td>{claim.attachment_count} proof · {claim.payment_count} payment</td>
                  </tr>
                ))}</tbody>
              </table></div>
            )}

            <div className="finance-report-pagination">
              <button type="button" disabled={data.page <= 1} onClick={() => setPage(value => Math.max(1, value - 1))}><ChevronLeft size={15} /> Previous</button>
              <span>{data.total_records} records · 50 per page</span>
              <button type="button" disabled={data.page >= data.total_pages} onClick={() => setPage(value => value + 1)}>Next <ChevronRight size={15} /></button>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
