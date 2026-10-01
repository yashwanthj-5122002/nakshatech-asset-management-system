import { AlertTriangle, BarChart3, CalendarRange, ChevronDown, ChevronLeft, ChevronRight, CircleDollarSign, CreditCard, Download, ExternalLink, FileCheck2, FileSpreadsheet, FileText, Inbox, Info, ListChecks, Loader2, Paperclip, Receipt, Search, ShieldCheck, UserRound, Wallet, X } from 'lucide-react'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch, downloadFile } from '../../../lib/api'
import type { ExpenseClaim, FinanceClaimStatus, FinanceClaimType, FinanceProject, FinanceReport, FinanceReportPeriod } from '../../../types'
import { financeClaimTypeLabels, financeExpenseCategories, financeStatusLabels, financeStatusTone, formatInr } from '../finance-utils'
import '../finance-expenses.css'
import '../finance-dashboard-v2.css'

const now = new Date()
const defaultQuarter = Math.floor(now.getMonth() / 3) + 1

function monthLabel(month: number): string {
  return new Intl.DateTimeFormat('en-IN', { month: 'long' }).format(new Date(2026, month - 1, 1))
}

function buildQuery(values: Record<string, string | number | undefined | null>): string {
  const params = new URLSearchParams()
  Object.entries(values).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    if (value === 'all' && key !== 'period') return
    params.set(key, String(value))
  })
  return params.toString()
}

const TOP_N = 8

function MiniBreakdown({ title, items, accent = '#2563eb' }: { title: string; items: FinanceReport['by_project']; accent?: string }) {
  const [expanded, setExpanded] = useState(false)
  const max = useMemo(() => Math.max(1, ...items.map(item => item.amount)), [items])
  const total = useMemo(() => items.reduce((sum, item) => sum + item.amount, 0), [items])
  const totalCount = useMemo(() => items.reduce((sum, item) => sum + item.count, 0), [items])
  const visible = expanded ? items : items.slice(0, TOP_N)
  return (
    <article className="fin-card">
      <div className="fin-card-header">
        <h3 className="fin-card-title">{title}</h3>
        <span className="fin-card-subtitle">{items.length} entr{items.length === 1 ? 'y' : 'ies'}</span>
      </div>
      {items.length === 0 ? <div className="nk-empty">
        <span className="nk-empty-icon"><Inbox size={22} /></span>
        <h3>No data in this period</h3>
        <p>Widen the period or clear a filter to bring records back into this breakdown.</p>
      </div> : (
        <>
          <div className={`fin-rank-list${expanded ? ' fin-rank-list-scroll' : ''}`}>
            {visible.map((item, index) => (
              <div className="fin-rank-row" key={item.key}>
                <span className="fin-rank-no" style={{ background: `${accent}14`, color: accent }}>{index + 1}</span>
                <div className="fin-rank-body">
                  <div className="fin-rank-top">
                    <span className="fin-rank-label" title={item.label}>{item.label}</span>
                    <strong>{formatInr(item.amount)}</strong>
                  </div>
                  <div className="fin-progress-track" style={{ height: 6 }}><div className="fin-progress-fill" style={{ width: `${Math.max(4, item.amount / max * 100)}%`, background: accent }} /></div>
                  <span className="fin-rank-meta">{item.count} claim(s) · {total > 0 ? Math.round(item.amount / total * 100) : 0}% of total</span>
                </div>
              </div>
            ))}
          </div>
          <div className="fin-rank-foot">
            <span>{totalCount} claim(s) · {formatInr(total)} total</span>
            {items.length > TOP_N && (
              <button type="button" className="fin-link-btn" onClick={() => setExpanded(value => !value)}>
                {expanded ? 'Show top 8' : `Show all ${items.length}`}
              </button>
            )}
          </div>
        </>
      )}
    </article>
  )
}

const statusFilterOptions = (Object.entries(financeStatusLabels) as Array<[FinanceClaimStatus, string]>).filter(([value]) => value !== 'draft')

function FactItem({ label, value, wide }: { label: string; value: ReactNode; wide?: boolean }) {
  return (
    <div className="fin-fact-item" style={wide ? { gridColumn: '1 / -1' } : undefined}>
      <span className="fin-fact-label">{label}</span>
      <span className="fin-fact-value">{value}</span>
    </div>
  )
}

function ClaimDetailDrawer({ claimId, onClose }: { claimId: number; onClose: () => void }) {
  const [claim, setClaim] = useState<ExpenseClaim | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    void apiFetch<ExpenseClaim>(`/finance/claims/${claimId}`)
      .then(result => { if (active) setClaim(result) })
      .catch(err => { if (active) setError(err instanceof Error ? err.message : 'Could not load this claim') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [claimId])

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = previousOverflow
    }
  }, [onClose])

  const approved = claim?.finance_approved_amount ?? 0
  const paid = claim?.paid_amount ?? 0
  const outstanding = claim?.remaining_amount ?? 0

  return createPortal(
    <div className="fin-detail-overlay" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
      <aside className="fin-detail-drawer" role="dialog" aria-modal="true" aria-label="Claim detail">
        <div className="fin-drawer-header">
          <div className="fin-drawer-title-group">
            {claim && <span className={`fin-status-pill ${pillTone[financeStatusTone(claim.status)] ?? 'neutral'}`}>{financeStatusLabels[claim.status]}</span>}
            <h2>{claim ? claim.claim_code : 'Claim detail'}</h2>
          </div>
          <button type="button" className="fin-drawer-close" onClick={onClose} aria-label="Close detail"><X size={18} /></button>
        </div>

        {loading && <div className="fin-drawer-state"><Loader2 size={22} className="fin-spin" /> Loading full claim record...</div>}
        {!loading && error && <div className="fin-drawer-state error"><AlertTriangle size={20} /> {error}</div>}

        {!loading && !error && claim && (
          <>
            <div>
              <span className="fin-kpi-label"><UserRound size={13} /> Employee &amp; Project</span>
              <div className="fin-facts-grid" style={{ marginTop: 8 }}>
                <FactItem label="Employee" value={claim.requester_name} />
                <FactItem label="Email" value={<span style={{ fontWeight: 600, fontSize: '0.8rem' }}>{claim.requester_email}</span>} />
                <FactItem label="Department" value={claim.requester_department || '—'} />
                <FactItem label="Request Type" value={financeClaimTypeLabels[claim.claim_type]} />
                <FactItem label="Project Code" value={claim.project.project_code} />
                <FactItem label="Project Name" value={claim.project.project_name} />
              </div>
            </div>

            <div>
              <span className="fin-kpi-label"><Receipt size={13} /> Money Matters</span>
              <div className="fin-facts-grid" style={{ marginTop: 8 }}>
                <FactItem label="Requested" value={formatInr(claim.total_amount)} />
                <FactItem label="Finance Approved" value={formatInr(approved)} />
                <FactItem label="Paid to Date" value={<span style={{ color: '#15803d' }}>{formatInr(paid)}</span>} />
                <FactItem label="Outstanding" value={<span style={{ color: outstanding > 0 ? '#b45309' : '#15803d' }}>{formatInr(outstanding)}</span>} />
                <FactItem label="Submitted On" value={claim.submitted_at ? new Date(claim.submitted_at).toLocaleString('en-IN') : 'Legacy record'} />
                <FactItem label="Settlement" value={claim.settlement_status.replace(/_/g, ' ')} />
                <FactItem label="Purpose" value={<span style={{ fontWeight: 600, lineHeight: 1.5, fontSize: '0.82rem' }}>{claim.purpose_description || '—'}</span>} wide />
              </div>
            </div>

            {claim.items.length > 0 && (
              <div>
                <span className="fin-kpi-label"><ListChecks size={13} /> Expense Line Items ({claim.items.length})</span>
                <div className="fin-drawer-table">
                  <table className="fin-table">
                    <thead><tr><th>Category</th><th>Description</th><th className="num">Amount</th></tr></thead>
                    <tbody>{claim.items.map((item, index) => (
                      <tr key={item.id}>
                        <td><span className="fin-cell-dept">{item.other_category || item.category.replace(/_/g, ' ')}</span></td>
                        <td><div className="fin-cell-name-strong" style={{ fontWeight: 600 }}>{item.description || '—'}</div>{item.expense_date && <div className="fin-cell-sub">{new Date(item.expense_date).toLocaleDateString('en-IN')}</div>}</td>
                        <td className="num">{formatInr(item.amount)}</td>
                      </tr>
                    ))}</tbody>
                    <tfoot><tr><td colSpan={2}><strong>Line total</strong></td><td className="num"><strong>{formatInr(claim.items.reduce((sum, item) => sum + item.amount, 0))}</strong></td></tr></tfoot>
                  </table>
                </div>
              </div>
            )}

            {claim.payments.length > 0 && (
              <div>
                <span className="fin-kpi-label"><CreditCard size={13} /> Payments ({claim.payments.length})</span>
                <div className="fin-facts-grid" style={{ marginTop: 8 }}>
                  {claim.payments.map(payment => (
                    <div className="fin-fact-item" key={payment.id} style={{ gridColumn: '1 / -1' }}>
                      <span className="fin-fact-label">{new Date(payment.payment_date).toLocaleDateString('en-IN')} · {payment.payment_mode.replace(/_/g, ' ')}</span>
                      <span className="fin-fact-value">{formatInr(payment.amount)} <span style={{ fontWeight: 600, fontSize: '0.76rem', color: '#64748b' }}>ref {payment.payment_reference || '—'} · by {payment.recorded_by_name}</span></span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div>
              <span className="fin-kpi-label"><Paperclip size={13} /> Evidence &amp; History</span>
              <div className="fin-facts-grid" style={{ marginTop: 8 }}>
                <FactItem label="Attachments" value={`${claim.attachments.length} file(s)`} />
                <FactItem label="Activity Entries" value={`${claim.events.length} event(s)`} />
              </div>
              {claim.events.length > 0 && (
                <ol className="fin-timeline">
                  {claim.events.slice(0, 8).map(event => (
                    <li key={event.id}>
                      <strong>{event.action.replace(/_/g, ' ')}</strong> · {event.actor_name || 'System'} · {new Date(event.created_at).toLocaleString('en-IN')}
                      {event.comments && <div className="fin-timeline-note">{event.comments}</div>}
                    </li>
                  ))}
                </ol>
              )}
            </div>

            <div className="fin-drawer-actions">
              <Link className="fin-btn-primary" to={`/finance/claims/${claim.id}`} onClick={onClose}><ExternalLink size={14} /> Open full claim page</Link>
              <button type="button" className="fin-btn-secondary" onClick={onClose}>Close</button>
            </div>
          </>
        )}
      </aside>
    </div>,
    document.body,
  )
}

const pillTone: Record<string, string> = { success: 'success', warning: 'warning', danger: 'danger', pending: 'info', draft: 'neutral' }

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
  const [tab, setTab] = useState<'ledger' | 'breakdown'>('ledger')
  const [detailId, setDetailId] = useState<number | null>(null)
  const [debouncedEmployee, setDebouncedEmployee] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedEmployee(employee.trim())
      setDebouncedSearch(search.trim())
      setPage(1)
    }, 350)
    return () => window.clearTimeout(timer)
  }, [employee, search])

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
    employee: debouncedEmployee || undefined,
    category,
    search: debouncedSearch || undefined,
    page,
    page_size: 50,
  }), [period, year, month, quarter, projectId, claimType, status, debouncedEmployee, category, debouncedSearch, page])

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    void apiFetch<FinanceReport>(`/finance/reports?${queryString}`)
      .then(result => { if (active) setData(result) })
      .catch(err => { if (active) setError(err instanceof Error ? err.message : 'Could not load Finance historical report') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [queryString])

  function resetPage() {
    setPage(1)
  }

  const filtersActive = projectId !== 'all' || claimType !== 'all' || status !== 'all' || category !== 'all' || Boolean(employee) || Boolean(search)

  function clearFilters() {
    setProjectId('all'); setClaimType('all'); setStatus('all'); setCategory('all'); setEmployee(''); setSearch(''); resetPage()
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
  const paidPct = data && data.approved_amount > 0 ? Math.min(100, Math.round(data.paid_amount / data.approved_amount * 100)) : 0

  return (
    <div className="finance-page">
      <DashboardHeader
        variant="workbench"
        icon={FileSpreadsheet}
        eyebrow="FINANCE CRM · HISTORICAL LEDGER"
        title="Finance Reports & Excel"
        description="Search years of project-expense history, reconcile approvals and payments, and download database-backed Excel workbooks."
        meta={<>
          <span className="nk-meta-chip"><CalendarRange size={14} /> Monthly · quarterly · yearly · all-time</span>
          <span className="nk-meta-chip"><ShieldCheck size={14} /> Read-only historical ledger</span>
        </>}
        actions={
          <div className="finance-header-actions">
            <details className="fin-menu">
              <summary className="fin-btn-secondary">Standard Exports <ChevronDown size={14} /></summary>
              <div className="fin-menu-list">
                {(['month', 'quarter', 'year'] as const).map(kind => (
                  <button key={kind} type="button" onClick={() => exportReport(kind)} disabled={Boolean(downloading)}>
                    <Download size={14} /> {kind === 'month' ? 'Monthly' : kind === 'quarter' ? 'Quarterly' : 'Yearly'} Excel
                  </button>
                ))}
              </div>
            </details>
            <button className="fin-btn-primary" type="button" onClick={() => exportReport('selected')} disabled={Boolean(downloading)}>
              <Download size={15} /> {downloading === 'selected' ? 'Preparing Excel...' : 'Download Current View'}
            </button>
          </div>
        }
      />

      {/* ═══════════ FILTER BAR ═══════════ */}
      <section className="fin-card fin-rpt-bar">
        <div className="fin-rpt-row">
          <div className="fin-filter-group" role="tablist" aria-label="Finance report period">
            {(['month', 'quarter', 'year', 'all'] as FinanceReportPeriod[]).map(value => (
              <button key={value} type="button" className={`fin-filter-pill ${period === value ? 'active' : ''}`} onClick={() => { setPeriod(value); resetPage() }}>
                {value === 'month' ? 'Monthly' : value === 'quarter' ? 'Quarterly' : value === 'year' ? 'Yearly' : 'All Time'}
              </button>
            ))}
          </div>
          {period !== 'all' && <label className="fin-rpt-field fin-rpt-field-sm"><span>Year</span><select value={year} onChange={event => { setYear(Number(event.target.value)); resetPage() }}>{years.map(value => <option key={value} value={value}>{value}</option>)}</select></label>}
          {period === 'month' && <label className="fin-rpt-field fin-rpt-field-sm"><span>Month</span><select value={month} onChange={event => { setMonth(Number(event.target.value)); resetPage() }}>{Array.from({ length: 12 }, (_, index) => index + 1).map(value => <option key={value} value={value}>{monthLabel(value)}</option>)}</select></label>}
          {period === 'quarter' && <label className="fin-rpt-field fin-rpt-field-sm"><span>Quarter</span><select value={quarter} onChange={event => { setQuarter(Number(event.target.value)); resetPage() }}>{[1, 2, 3, 4].map(value => <option key={value} value={value}>Q{value}</option>)}</select></label>}
          {data && <span className="fin-rpt-period"><CalendarRange size={14} /> <strong>{data.period_label}</strong> · {data.start_date && data.end_date ? `${data.start_date} → ${data.end_date}` : 'Complete history'}</span>}
        </div>

        <div className="fin-rpt-row fin-rpt-row-filters">
          <label className="fin-rpt-field fin-rpt-field-grow"><span>Project</span><select value={projectId} onChange={event => { setProjectId(event.target.value); resetPage() }}><option value="all">All projects</option>{projects.map(project => <option key={project.id} value={project.id}>{project.project_code} · {project.project_name}</option>)}</select></label>
          <label className="fin-rpt-field"><span>Request Type</span><select value={claimType} onChange={event => { setClaimType(event.target.value as 'all' | FinanceClaimType); resetPage() }}><option value="all">All types</option>{Object.entries(financeClaimTypeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label className="fin-rpt-field"><span>Status</span><select value={status} onChange={event => { setStatus(event.target.value as 'all' | FinanceClaimStatus); resetPage() }}><option value="all">All statuses</option>{statusFilterOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label className="fin-rpt-field"><span>Category</span><select value={category} onChange={event => { setCategory(event.target.value); resetPage() }}><option value="all">All categories</option>{financeExpenseCategories.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label className="fin-rpt-field"><span>Employee</span><input value={employee} onChange={event => { setEmployee(event.target.value); resetPage() }} placeholder="Name or email" /></label>
          <div className="fin-search-box fin-rpt-search">
            <Search className="fin-search-icon" size={16} />
            <input className="fin-search-input" value={search} onChange={event => { setSearch(event.target.value); resetPage() }} placeholder="Search claim ID, project, purpose..." aria-label="Search ledger" />
          </div>
          {filtersActive && <button type="button" className="fin-btn-secondary" onClick={clearFilters}><X size={13} /> Clear</button>}
        </div>
      </section>

      {error && (data ? <div className="finance-error">{error}</div> : (
        <div className="nk-empty">
          <span className="nk-empty-icon"><AlertTriangle size={22} /></span>
          <h3>Report unavailable</h3>
          <p>{error} Your period and filter selections above are retained — change any filter to request the ledger again, or use Refresh in your browser.</p>
        </div>
      ))}
      {loading && <div className="finance-panel finance-empty-state">Loading Finance ledger...</div>}

      {data && !loading && (
        <>
          {/* ═══════════ KPI CARDS ═══════════ */}
          <section className="fin-hero-kpis">
            <div className="fin-hero-kpi-card">
              <div className="fin-kpi-top"><span className="fin-kpi-label">Requested</span><div className="fin-kpi-icon blue"><FileText size={18} /></div></div>
              <span className="fin-kpi-value">{formatInr(data.requested_amount)}</span>
              <span className="fin-kpi-sub">{data.total_records} claim(s) · original request value</span>
            </div>
            <div className="fin-hero-kpi-card">
              <div className="fin-kpi-top"><span className="fin-kpi-label">Finance Approved</span><div className="fin-kpi-icon cyan"><FileCheck2 size={18} /></div></div>
              <span className="fin-kpi-value">{formatInr(data.approved_amount)}</span>
              <span className="fin-kpi-sub">Approved amount, kept separate</span>
            </div>
            <div className="fin-hero-kpi-card">
              <div className="fin-kpi-top"><span className="fin-kpi-label">Paid Against Claims</span><div className="fin-kpi-icon green"><Wallet size={18} /></div></div>
              <span className="fin-kpi-value" style={{ color: '#15803d' }}>{formatInr(data.paid_amount)}</span>
              <div className="fin-progress-row" style={{ marginTop: 2 }}>
                <div className="fin-progress-track"><div className="fin-progress-fill" style={{ width: `${paidPct}%`, background: '#16a34a' }} /></div>
                <span className="fin-progress-pct">{paidPct}%</span>
              </div>
            </div>
            <div className="fin-hero-kpi-card">
              <div className="fin-kpi-top"><span className="fin-kpi-label">Outstanding</span><div className="fin-kpi-icon orange"><CircleDollarSign size={18} /></div></div>
              <span className="fin-kpi-value" style={{ color: data.outstanding_amount > 0 ? '#b45309' : '#15803d' }}>{formatInr(data.outstanding_amount)}</span>
              <span className="fin-kpi-sub">Approved, not yet settled</span>
            </div>
            <div className="fin-hero-kpi-card">
              <div className="fin-kpi-top"><span className="fin-kpi-label">Cash Paid in Period</span><div className="fin-kpi-icon purple"><CreditCard size={18} /></div></div>
              <span className="fin-kpi-value">{formatInr(data.payment_period_amount)}</span>
              <span className="fin-kpi-sub">{data.payment_period_count} payment(s) dated in this period</span>
            </div>
          </section>

          {/* ═══════════ PIPELINE STRIP ═══════════ */}
          <section className="fin-status-cards fin-status-cards-3">
            <div className="fin-status-card static">
              <div className="fin-status-badge orange"><ListChecks size={20} /></div>
              <div className="fin-status-info"><span className="fin-status-label">Pending Admin</span><span className="fin-status-count">{formatInr(data.pending_admin_amount)}</span><span className="fin-status-hint">Awaiting legitimacy verification</span></div>
            </div>
            <div className="fin-status-card static">
              <div className="fin-status-badge purple"><ListChecks size={20} /></div>
              <div className="fin-status-info"><span className="fin-status-label">Pending Finance</span><span className="fin-status-count">{formatInr(data.pending_finance_amount)}</span><span className="fin-status-hint">Admin-verified, awaiting Finance</span></div>
            </div>
            <div className={`fin-status-card static ${data.integrity_issue_count ? 'warn' : ''}`}>
              <div className={`fin-status-badge ${data.integrity_issue_count ? 'red' : 'green'}`}><ShieldCheck size={20} /></div>
              <div className="fin-status-info"><span className="fin-status-label">Integrity Review</span><span className="fin-status-count">{data.integrity_issue_count}</span><span className="fin-status-hint">{data.integrity_issue_count ? 'Record(s) need Finance review' : `${years.length} reporting year(s) available`}</span></div>
            </div>
          </section>

          <p className="fin-rpt-note"><Info size={14} /> <span><strong>Period accounting:</strong> claim totals follow the submission date; <strong>Cash Paid in Period</strong> follows each payment date, so an older claim paid later still lands in the right month.</span></p>

          {data.integrity_issue_count > 0 && <div className="finance-integrity-alert"><AlertTriangle size={17} /><div><strong>Data integrity review required</strong><span>The Excel workbook includes a Data Integrity sheet identifying the exact records. No record is automatically modified.</span></div></div>}

          {/* ═══════════ TABS ═══════════ */}
          <nav className="fin-tabs-bar">
            <button type="button" className={`fin-tab-button ${tab === 'ledger' ? 'active' : ''}`} onClick={() => setTab('ledger')}>
              <FileText size={16} /> Historical Claims <span className="fin-tab-badge">{data.total_records}</span>
            </button>
            <button type="button" className={`fin-tab-button ${tab === 'breakdown' ? 'active' : ''}`} onClick={() => setTab('breakdown')}>
              <BarChart3 size={16} /> Spend Breakdown
            </button>
          </nav>

          {tab === 'breakdown' && (
            <section className="fin-breakdown-cards">
              <MiniBreakdown title="Project-wise Spend" items={data.by_project} accent="#2563eb" />
              <MiniBreakdown title="Employee-wise Spend" items={data.by_employee} accent="#0891b2" />
              <MiniBreakdown title="Category-wise Spend" items={data.by_category} accent="#7c3aed" />
              <MiniBreakdown title="Request Type Split" items={data.by_type} accent="#16a34a" />
              <MiniBreakdown title="Status Pipeline" items={data.by_status} accent="#d97706" />
            </section>
          )}

          {tab === 'ledger' && (
            <div className="fin-table-card">
              {data.claims.length === 0 ? <div className="nk-empty">
                <span className="nk-empty-icon"><Inbox size={22} /></span>
                <h3>No Finance records match this period and filter combination</h3>
                <p>Widen the period, clear a filter, or switch to All Time to search the complete Finance ledger.</p>
                {period !== 'all' && <div className="nk-empty-action"><button type="button" className="fin-btn-primary" onClick={() => { setPeriod('all'); resetPage() }}><CalendarRange size={14} /> Search all time</button></div>}
              </div> : (
                <div className="fin-table-scroll">
                  <table className="fin-table fin-rpt-table fin-rpt-clickable">
                    <thead><tr><th>Claim</th><th>Employee</th><th>Project</th><th>Type</th><th className="num">Requested</th><th className="num">Approved</th><th className="num">Paid</th><th className="num">Outstanding</th><th>Status</th><th>Evidence</th></tr></thead>
                    <tbody>{data.claims.map(claim => (
                      <tr key={claim.id} onClick={() => setDetailId(claim.id)} title="Click for full claim detail">
                        <td>
                          <Link className="fin-cell-code" to={`/finance/claims/${claim.id}`} onClick={event => event.stopPropagation()}>{claim.claim_code}</Link>
                          <div className="fin-cell-sub">{claim.submitted_at ? new Date(claim.submitted_at).toLocaleDateString('en-IN') : 'Legacy'}</div>
                        </td>
                        <td><div className="fin-cell-name-strong">{claim.requester_name}</div><div className="fin-cell-sub">{claim.requester_email}</div></td>
                        <td><div className="fin-cell-name-strong">{claim.project_code}</div><div className="fin-cell-sub">{claim.project_name}</div></td>
                        <td><span className="fin-cell-dept">{financeClaimTypeLabels[claim.claim_type]}</span></td>
                        <td className="num">{formatInr(claim.requested_amount)}</td>
                        <td className="num">{formatInr(claim.approved_amount)}</td>
                        <td className="num" style={{ color: '#15803d' }}>{formatInr(claim.paid_amount)}</td>
                        <td className="num"><strong style={{ color: claim.outstanding_amount > 0 ? '#b45309' : '#64748b' }}>{formatInr(claim.outstanding_amount)}</strong></td>
                        <td><span className={`fin-status-pill ${pillTone[financeStatusTone(claim.status)] ?? 'neutral'}`}>{financeStatusLabels[claim.status]}</span></td>
                        <td><span className="fin-evidence" title={`${claim.attachment_count} proof(s), ${claim.payment_count} payment(s)`}><Paperclip size={12} /> {claim.attachment_count} <CreditCard size={12} /> {claim.payment_count}</span></td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              )}

              <div className="fin-pager">
                <span>Page {data.page} of {data.total_pages} · {data.total_records} records · 50 per page · click any row for full detail</span>
                <div>
                  <button type="button" className="fin-btn-secondary" disabled={data.page <= 1} onClick={() => setPage(value => Math.max(1, value - 1))}><ChevronLeft size={14} /> Previous</button>
                  <button type="button" className="fin-btn-secondary" disabled={data.page >= data.total_pages} onClick={() => setPage(value => value + 1)}>Next <ChevronRight size={14} /></button>
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {detailId !== null && <ClaimDetailDrawer claimId={detailId} onClose={() => setDetailId(null)} />}
    </div>
  )
}

