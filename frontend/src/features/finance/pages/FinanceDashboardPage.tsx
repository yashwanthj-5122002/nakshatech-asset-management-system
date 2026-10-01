import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  CreditCard,
  DollarSign,
  Eye,
  FileCheck2,
  FileSpreadsheet,
  FileText,
  Filter,
  FolderKanban,
  Inbox,
  IndianRupee,
  Layers,
  PieChart,
  ReceiptIndianRupee,
  RefreshCcw,
  RotateCcw,
  Search,
  ShieldCheck,
  TrendingUp,
  User,
  Wallet,
  WalletCards,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch } from '../../../lib/api'
import type { FinanceBreakdownItem, FinanceDashboard } from '../../../types'
import { financeClaimTypeLabels, financeStatusLabels, financeStatusTone, formatInr } from '../finance-utils'
import { FinanceCommercialSummary } from '../../commercial/components/FinanceCommercialSummary'
import type { CommercialAnalytics, CommercialSummary } from '../../commercial/types'
import { FinanceCommandCenter } from './FinanceCommandCenter'
import '../finance-expenses.css'
import '../finance-dashboard-v2.css'

/* ────────────────────────── Types ────────────────────────── */

type EventRow = {
  id: number
  event_type: string
  from_status?: string | null
  to_status: string
  comments?: string | null
  actor_name?: string | null
  actor_role?: string | null
  created_at: string
}

type WorkflowClient = {
  organization_name?: string | null
  client_code?: string | null
  client_email?: string | null
  organization_email?: string | null
  location?: string | null
  gst_number?: string | null
  contact_person_name?: string | null
  contact_person_email?: string | null
  contact_person_phone?: string | null
  bd_person?: string | null
}

type WorkflowProject = {
  id: number
  project_code: string
  project_name: string
  client_code?: string | null
  client_name?: string | null
  start_date?: string | null
  end_date?: string | null
  scope_text?: string | null
  quantity?: number | null
  quantity_unit?: string | null
  priority?: string | null
  performing_department_code?: string
  performing_department_label?: string
  commercial_value?: number | null
  currency?: string | null
  po_wo_number?: string | null
  attachment_references?: string[]
  workflow_status: string
  normalized_status: string
  finance_closable?: boolean
  finance_closure_blocker?: string | null
  finance_feedback?: string | null
  project_manager_name?: string | null
  completion_date?: string | null
  final_delivery_reference?: string | null
  submission_count?: number
  finance_reviewer_name?: string | null
  finance_reviewed_at?: string | null
  created_at?: string
  created_by_name?: string | null
  submitted_by_name?: string | null
  submitted_by_email?: string | null
  client?: WorkflowClient
  events?: EventRow[]
  commercial_summary?: CommercialSummary
  expense_summary?: {
    claim_count: number
    requested_amount: number
    approved_amount: number
    paid_amount: number
    outstanding_amount: number
    unresolved_claim_count: number
  }
}

type WorkflowDashboard = {
  summary: {
    pending_approval: number
    returned: number
    approved: number
    closure_pending: number
    closed: number
  }
  projects: WorkflowProject[]
}

type ActiveTab = 'queue' | 'analytics' | 'expenses' | 'command_center'
type QueueFilter = 'all' | 'pending' | 'returned' | 'approved' | 'closure_pending' | 'closed'

function label(v: string) {
  return v.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function pct(value: number, total: number): number {
  return total > 0 ? Math.round((value / total) * 100) : 0
}

/* ────────────────────────── Inline Charts ────────────────────────── */

const CHART_COLORS = ['#2563eb', '#0891b2', '#16a34a', '#d97706', '#dc2626', '#7c3aed', '#db2777', '#059669']

function DonutChart({ segments, size = 150, centerLabel }: { segments: { value: number; color: string; label: string }[]; size?: number; centerLabel?: string }) {
  const total = segments.reduce((s, seg) => s + seg.value, 0)
  if (total === 0) return <div className="nk-empty"><p>No expense data available</p></div>
  const radius = (size - 24) / 2
  const cx = size / 2
  const cy = size / 2
  let cumulative = 0
  const paths = segments.filter(s => s.value > 0).map((seg) => {
    const startAngle = (cumulative / total) * 360
    cumulative += seg.value
    const endAngle = (cumulative / total) * 360
    const largeArc = endAngle - startAngle > 180 ? 1 : 0
    const startRad = ((startAngle - 90) * Math.PI) / 180
    const endRad = ((endAngle - 90) * Math.PI) / 180
    const x1 = cx + radius * Math.cos(startRad)
    const y1 = cy + radius * Math.sin(startRad)
    const x2 = cx + radius * Math.cos(endRad)
    const y2 = cy + radius * Math.sin(endRad)
    const innerRadius = radius * 0.6
    const x3 = cx + innerRadius * Math.cos(endRad)
    const y3 = cy + innerRadius * Math.sin(endRad)
    const x4 = cx + innerRadius * Math.cos(startRad)
    const y4 = cy + innerRadius * Math.sin(startRad)
    return (
      <path
        key={seg.label}
        d={`M ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2} L ${x3} ${y3} A ${innerRadius} ${innerRadius} 0 ${largeArc} 0 ${x4} ${y4} Z`}
        fill={seg.color}
        opacity={0.9}
      >
        <title>{`${seg.label}: ${formatInr(seg.value)} (${pct(seg.value, total)}%)`}</title>
      </path>
    )
  })
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '20px', flexWrap: 'wrap' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {paths}
        {centerLabel && <text x={cx} y={cy + 5} textAnchor="middle" fill="#082a52" fontSize="12" fontWeight="800">{centerLabel}</text>}
      </svg>
      <div style={{ display: 'grid', gap: '6px', fontSize: '0.78rem' }}>
        {segments.filter(s => s.value > 0).map(seg => (
          <div key={seg.label} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ width: 10, height: 10, borderRadius: 3, background: seg.color }} />
            <span style={{ color: '#475569', fontWeight: 600 }}>{seg.label}:</span>
            <strong style={{ color: '#082a52' }}>{formatInr(seg.value)}</strong>
          </div>
        ))}
      </div>
    </div>
  )
}

function TrendChart({ data, height = 130 }: { data: { label: string; billing: number; payments: number; margin: number }[]; height?: number }) {
  if (!data.length) return null
  const max = Math.max(...data.map(d => Math.max(d.billing, d.payments, 1)))
  const width = Math.max(data.length * 68, 380)
  const padding = 34
  const chartWidth = width - padding * 2
  const chartHeight = height - 34

  const billingPts = data.map((d, i) => ({
    x: padding + (i / Math.max(data.length - 1, 1)) * chartWidth,
    y: 12 + chartHeight - (d.billing / max) * chartHeight,
  }))
  const paymentPts = data.map((d, i) => ({
    x: padding + (i / Math.max(data.length - 1, 1)) * chartWidth,
    y: 12 + chartHeight - (d.payments / max) * chartHeight,
  }))

  const billPath = billingPts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')
  const payPath = paymentPts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')

  return (
    <div className="fin-trend-wrap">
      <svg className="fin-trend-svg" width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <defs>
          <linearGradient id="billGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2563eb" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#2563eb" stopOpacity="0.01" />
          </linearGradient>
        </defs>
        <path d={`${billPath} L ${billingPts[billingPts.length - 1].x} ${chartHeight + 12} L ${billingPts[0].x} ${chartHeight + 12} Z`} fill="url(#billGrad)" />
        <path d={billPath} fill="none" stroke="#2563eb" strokeWidth="2.5" strokeLinejoin="round" />
        <path d={payPath} fill="none" stroke="#16a34a" strokeWidth="2" strokeDasharray="4 3" strokeLinejoin="round" />
        {billingPts.map((p, i) => (
          <g key={data[i].label}>
            <circle cx={p.x} cy={p.y} r="3.5" fill="#2563eb" />
            <circle cx={paymentPts[i].x} cy={paymentPts[i].y} r="3" fill="#16a34a" />
            <text x={p.x} y={height - 6} textAnchor="middle">{data[i].label}</text>
            <title>{`${data[i].label} — Billed: ${formatInr(data[i].billing)}, Paid: ${formatInr(data[i].payments)}`}</title>
          </g>
        ))}
      </svg>
      <div style={{ display: 'flex', gap: '16px', fontSize: '0.74rem', marginTop: '4px', paddingLeft: '8px' }}>
        <span style={{ color: '#2563eb', fontWeight: 700 }}>● Billed Net</span>
        <span style={{ color: '#16a34a', fontWeight: 700 }}>┄ Payments Realized</span>
      </div>
    </div>
  )
}

/* ────────────────────────── Main Component ────────────────────────── */

export function FinanceDashboardPage() {
  const { user } = useAuth()
  const [data, setData] = useState<FinanceDashboard | null>(null)
  const [workflow, setWorkflow] = useState<WorkflowDashboard | null>(null)
  const [commercial, setCommercial] = useState<CommercialAnalytics | null>(null)
  const [activeTab, setActiveTab] = useState<ActiveTab>('queue')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  // Table filtering & search
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<QueueFilter>('all')

  // Review Drawer state
  const [reviewId, setReviewId] = useState<number | null>(null)
  const [returnFeedback, setReturnFeedback] = useState('')
  const [approveNote, setApproveNote] = useState('')

  function load() {
    setLoading(true)
    setError('')
    void Promise.all([
      apiFetch<FinanceDashboard>('/finance/dashboard'),
      apiFetch<WorkflowDashboard>('/operations/workflow/finance/dashboard'),
      apiFetch<CommercialAnalytics>('/commercial/management/analytics').catch(() => null),
    ])
      .then(([finData, wfData, commData]) => {
        setData(finData)
        setWorkflow(wfData)
        setCommercial(commData)
      })
      .catch(e => setError(e instanceof Error ? e.message : 'Could not load Finance dashboard'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const reviewProject = workflow?.projects.find(row => row.id === reviewId) ?? null

  function openReview(row: WorkflowProject) {
    setReviewId(row.id)
    setReturnFeedback('')
    setApproveNote('')
    setError('')
  }

  async function review(row: WorkflowProject, decision: 'approve' | 'return') {
    const feedback = decision === 'return' ? returnFeedback.trim() : approveNote.trim()
    if (decision === 'return' && !feedback) {
      setError('Finance feedback is mandatory when returning a project.')
      return
    }
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await apiFetch(`/operations/workflow/finance/projects/${row.id}/review`, {
        method: 'POST',
        body: JSON.stringify({ decision, feedback: feedback || null }),
      })
      setNotice(
        decision === 'approve'
          ? `${row.project_code} approved. Commercial baseline locked and BD notified.`
          : `${row.project_code} returned to BD with mandatory feedback.`
      )
      setReviewId(null)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to review project')
    } finally {
      setBusy(false)
    }
  }

  async function closeProject(row: WorkflowProject) {
    if (!window.confirm(`Complete Finance Closure for ${row.project_code}?`)) return
    if (row.expense_summary && (row.expense_summary.unresolved_claim_count > 0 || row.expense_summary.outstanding_amount > 0)) {
      const proceed = window.confirm(
        `${row.project_code} still shows ${row.expense_summary.unresolved_claim_count} unresolved claim(s) and ${formatInr(row.expense_summary.outstanding_amount)} outstanding. Continue with Finance Closure anyway?`
      )
      if (!proceed) return
    }
    const remarks = window.prompt(`Finance Closure remarks for ${row.project_code} (required):`, '')
    if (remarks === null) return
    if (!remarks.trim()) {
      setError('Finance Closure remarks are required.')
      return
    }
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await apiFetch(`/operations/workflow/finance/projects/${row.id}/close`, {
        method: 'POST',
        body: JSON.stringify({ remarks }),
      })
      setNotice(`${row.project_code} financially closed.`)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to close project')
    } finally {
      setBusy(false)
    }
  }

  // Filtered project list for the queue
  const filteredProjects = useMemo(() => {
    const list = workflow?.projects ?? []
    return list.filter(row => {
      // Keyword search
      const term = search.trim().toLowerCase()
      const matchesSearch = !term || (
        row.project_code.toLowerCase().includes(term) ||
        row.project_name.toLowerCase().includes(term) ||
        (row.client_name || '').toLowerCase().includes(term) ||
        (row.client_code || '').toLowerCase().includes(term) ||
        (row.performing_department_label || '').toLowerCase().includes(term) ||
        (row.project_manager_name || '').toLowerCase().includes(term)
      )
      if (!matchesSearch) return false

      // Status pill filter
      const s = row.normalized_status
      if (filter === 'pending') return s === 'pending_finance_approval'
      if (filter === 'returned') return s === 'finance_returned'
      if (filter === 'approved') return ['finance_approved', 'pm_assigned', 'team_assigned', 'in_progress'].includes(s)
      if (filter === 'closure_pending') return s === 'finance_closure_pending'
      if (filter === 'closed') return s === 'closed'
      return true
    })
  }, [workflow, search, filter])

  // Top financial totals
  const totalCommercialValue = workflow?.projects.reduce((sum, p) => sum + (p.commercial_value || 0), 0) ?? 0
  const billedNet = commercial?.summary_inr?.billed_net_inr ?? 0
  const paymentsRealized = commercial?.summary_inr?.payments_realized_inr ?? 0
  const totalExpensesPaid = data?.paid_amount ?? 0
  const netMargin = commercial?.summary_inr?.margin_inr ?? (paymentsRealized - totalExpensesPaid)

  // Category expense breakdown for donut chart
  const categorySegments = (data?.by_category ?? []).slice(0, 6).map((c, i) => ({
    label: c.label,
    value: c.amount,
    color: CHART_COLORS[i % CHART_COLORS.length],
  }))

  // Monthly trend data
  const monthlyTrend = (commercial?.monthly ?? []).slice(-7).map((m: {
    month: string
    billing_inr: number
    payments_inr: number
    margin_inr: number
  }) => ({
    label: m.month.slice(5),
    billing: m.billing_inr,
    payments: m.payments_inr,
    margin: m.margin_inr,
  }))

  return (
    <div className="finance-page">
      <DashboardHeader
        variant="workbench"
        icon={ReceiptIndianRupee}
        eyebrow="FINANCE & OPERATIONS OVERSIGHT"
        title={user?.role === 'management' ? 'Finance & Project Oversight' : 'Finance Dashboard'}
        description={
          user?.role === 'finance'
            ? 'Review and approve BD project submissions, lock commercial baselines, track cash flow and billing realization, and authorize project closure.'
            : 'Executive financial oversight: commercial baseline reviews, cash collections, expense disbursement, and project margin intelligence.'
        }
        meta={
          <>
            <span className="nk-meta-chip"><ShieldCheck size={14} /> Full Financial Authority</span>
            <span className="nk-meta-chip"><Clock3 size={14} /> {workflow ? `${workflow.summary.pending_approval} Pending Approval` : 'Loading…'}</span>
            <span className="nk-meta-chip"><IndianRupee size={14} /> {data ? `${formatInr(data.paid_amount)} Disbursed` : 'Loading…'}</span>
          </>
        }
        actions={
          <div className="finance-header-actions">
            <button className="fin-btn-secondary" type="button" onClick={load}>
              <RefreshCcw size={15} /> Refresh
            </button>
            <Link className="fin-btn-secondary" to="/finance/reports">
              <FileSpreadsheet size={15} /> Reports & Excel
            </Link>
            <Link className="fin-btn-primary" to="/finance/claims">
              <FileCheck2 size={15} /> Expense Claims & Approvals
            </Link>
          </div>
        }
      />

      {notice && <div className="finance-success-message">{notice}</div>}
      {error && <div className="finance-error">{error} <button type="button" className="finance-inline-link" onClick={load}>Retry</button></div>}

      {/* ═══════════ 1. HIGH-LEVEL FINANCIAL & CASH FLOW METRICS ═══════════ */}
      <section className="fin-hero-kpis">
        <div className="fin-hero-kpi-card">
          <div className="fin-kpi-top">
            <span className="fin-kpi-label">Commercial Pipeline Value</span>
            <div className="fin-kpi-icon blue"><FolderKanban size={18} /></div>
          </div>
          <span className="fin-kpi-value">{formatInr(totalCommercialValue)}</span>
          <span className="fin-kpi-sub">
            <CheckCircle2 size={13} style={{ color: '#16a34a' }} /> {workflow?.projects.length ?? 0} Active Project Contracts
          </span>
        </div>

        <div className="fin-hero-kpi-card">
          <div className="fin-kpi-top">
            <span className="fin-kpi-label">Total Billed Net</span>
            <div className="fin-kpi-icon cyan"><FileText size={18} /></div>
          </div>
          <span className="fin-kpi-value">{formatInr(billedNet)}</span>
          <span className="fin-kpi-sub">
            Invoiced to clients to date
          </span>
        </div>

        <div className="fin-hero-kpi-card">
          <div className="fin-kpi-top">
            <span className="fin-kpi-label">Realized Cash Collections</span>
            <div className="fin-kpi-icon green"><IndianRupee size={18} /></div>
          </div>
          <span className="fin-kpi-value" style={{ color: '#15803d' }}>{formatInr(paymentsRealized)}</span>
          <div className="fin-progress-row" style={{ marginTop: 2 }}>
            <div className="fin-progress-track">
              <div className="fin-progress-fill" style={{ width: `${pct(paymentsRealized, billedNet || 1)}%`, background: '#16a34a' }} />
            </div>
            <span className="fin-progress-pct">{pct(paymentsRealized, billedNet || 1)}%</span>
          </div>
        </div>

        <div className="fin-hero-kpi-card">
          <div className="fin-kpi-top">
            <span className="fin-kpi-label">Project Expenses Paid</span>
            <div className="fin-kpi-icon orange"><Wallet size={18} /></div>
          </div>
          <span className="fin-kpi-value" style={{ color: '#b45309' }}>{formatInr(totalExpensesPaid)}</span>
          <span className="fin-kpi-sub">
            {data ? `${data.paid_count} claims paid · ${formatInr(data.outstanding_amount)} outstanding` : 'Expenses'}
          </span>
        </div>

        <div className="fin-hero-kpi-card">
          <div className="fin-kpi-top">
            <span className="fin-kpi-label">Net Operating Margin</span>
            <div className="fin-kpi-icon purple"><TrendingUp size={18} /></div>
          </div>
          <span className="fin-kpi-value" style={{ color: netMargin >= 0 ? '#15803d' : '#b91c1c' }}>
            {formatInr(netMargin)}
          </span>
          <span className="fin-kpi-sub">
            {billedNet > 0 ? `${pct(netMargin, billedNet)}% of Billed Net Revenue` : 'Net Margin'}
          </span>
        </div>
      </section>

      {/* ═══════════ 2. TABS NAVIGATION ═══════════ */}
      <nav className="fin-tabs-bar">
        <button
          type="button"
          className={`fin-tab-button ${activeTab === 'queue' ? 'active' : ''}`}
          onClick={() => setActiveTab('queue')}
        >
          <FolderKanban size={16} /> Project Approvals & Workflow Queue
          {workflow && <span className="fin-tab-badge">{workflow.projects.length}</span>}
        </button>

        <button
          type="button"
          className={`fin-tab-button ${activeTab === 'analytics' ? 'active' : ''}`}
          onClick={() => setActiveTab('analytics')}
        >
          <BarChart3 size={16} /> Financial Analytics & Cash Flow
        </button>

        <button
          type="button"
          className={`fin-tab-button ${activeTab === 'expenses' ? 'active' : ''}`}
          onClick={() => setActiveTab('expenses')}
        >
          <CreditCard size={16} /> Expense Claims & Spend Mix
          {data && <span className="fin-tab-badge">{data.total_claims}</span>}
        </button>

        <button
          type="button"
          className={`fin-tab-button ${activeTab === 'command_center' ? 'active' : ''}`}
          onClick={() => setActiveTab('command_center')}
        >
          <DollarSign size={16} /> Open Sales & Command Center
        </button>
      </nav>

      {/* ═══════════ TAB 1: PROJECT APPROVALS & WORKFLOW QUEUE ═══════════ */}
      {activeTab === 'queue' && (
        <>
          {/* Clickable Workflow Filter Cards */}
          {workflow && (
            <section className="fin-status-cards">
              <div
                className={`fin-status-card ${filter === 'all' ? 'active' : ''}`}
                onClick={() => setFilter('all')}
              >
                <div className="fin-status-badge blue"><FolderKanban size={20} /></div>
                <div className="fin-status-info">
                  <span className="fin-status-label">All Projects</span>
                  <span className="fin-status-count">{workflow.projects.length}</span>
                </div>
              </div>

              <div
                className={`fin-status-card ${filter === 'pending' ? 'active' : ''}`}
                onClick={() => setFilter(filter === 'pending' ? 'all' : 'pending')}
              >
                <div className="fin-status-badge orange"><Clock3 size={20} /></div>
                <div className="fin-status-info">
                  <span className="fin-status-label">Pending Approval</span>
                  <span className="fin-status-count">{workflow.summary.pending_approval}</span>
                </div>
              </div>

              <div
                className={`fin-status-card ${filter === 'returned' ? 'active' : ''}`}
                onClick={() => setFilter(filter === 'returned' ? 'all' : 'returned')}
              >
                <div className="fin-status-badge red"><RotateCcw size={20} /></div>
                <div className="fin-status-info">
                  <span className="fin-status-label">Returned to BD</span>
                  <span className="fin-status-count">{workflow.summary.returned}</span>
                </div>
              </div>

              <div
                className={`fin-status-card ${filter === 'approved' ? 'active' : ''}`}
                onClick={() => setFilter(filter === 'approved' ? 'all' : 'approved')}
              >
                <div className="fin-status-badge green"><CheckCircle2 size={20} /></div>
                <div className="fin-status-info">
                  <span className="fin-status-label">Operational</span>
                  <span className="fin-status-count">{workflow.summary.approved}</span>
                </div>
              </div>

              <div
                className={`fin-status-card ${filter === 'closure_pending' ? 'active' : ''}`}
                onClick={() => setFilter(filter === 'closure_pending' ? 'all' : 'closure_pending')}
              >
                <div className="fin-status-badge purple"><WalletCards size={20} /></div>
                <div className="fin-status-info">
                  <span className="fin-status-label">Closure Pending</span>
                  <span className="fin-status-count">{workflow.summary.closure_pending}</span>
                </div>
              </div>

              <div
                className={`fin-status-card ${filter === 'closed' ? 'active' : ''}`}
                onClick={() => setFilter(filter === 'closed' ? 'all' : 'closed')}
              >
                <div className="fin-status-badge blue"><CheckCircle2 size={20} /></div>
                <div className="fin-status-info">
                  <span className="fin-status-label">Closed</span>
                  <span className="fin-status-count">{workflow.summary.closed}</span>
                </div>
              </div>
            </section>
          )}

          {/* Table Toolbar */}
          <div className="fin-table-toolbar">
            <div className="fin-search-box">
              <Search className="fin-search-icon" size={16} />
              <input
                className="fin-search-input"
                placeholder="Search project code, name, client, PM..."
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
            </div>

            <div className="fin-filter-group">
              <button className={`fin-filter-pill ${filter === 'all' ? 'active' : ''}`} onClick={() => setFilter('all')}>All</button>
              <button className={`fin-filter-pill ${filter === 'pending' ? 'active' : ''}`} onClick={() => setFilter('pending')}>Pending ({workflow?.summary.pending_approval ?? 0})</button>
              <button className={`fin-filter-pill ${filter === 'returned' ? 'active' : ''}`} onClick={() => setFilter('returned')}>Returned ({workflow?.summary.returned ?? 0})</button>
              <button className={`fin-filter-pill ${filter === 'approved' ? 'active' : ''}`} onClick={() => setFilter('approved')}>Operational ({workflow?.summary.approved ?? 0})</button>
              <button className={`fin-filter-pill ${filter === 'closure_pending' ? 'active' : ''}`} onClick={() => setFilter('closure_pending')}>Closure Pending ({workflow?.summary.closure_pending ?? 0})</button>
              <button className={`fin-filter-pill ${filter === 'closed' ? 'active' : ''}`} onClick={() => setFilter('closed')}>Closed ({workflow?.summary.closed ?? 0})</button>
            </div>
          </div>

          {/* Perfectly Fitted Clean Table */}
          <div className="fin-table-card">
            <table className="fin-table">
              <thead>
                <tr>
                  <th>Project & Client</th>
                  <th>Department</th>
                  <th>Commercial Baseline</th>
                  <th>Timeline</th>
                  <th>Expenses Exposure</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr><td colSpan={7} style={{ textAlign: 'center', padding: '32px', color: '#64748b' }}>Loading projects…</td></tr>
                )}
                {!loading && !filteredProjects.length && (
                  <tr><td colSpan={7} style={{ textAlign: 'center', padding: '36px', color: '#64748b' }}>No projects match the selected filter.</td></tr>
                )}
                {filteredProjects.map(row => {
                  const isPending = row.normalized_status === 'pending_finance_approval'
                  const isClosurePending = row.normalized_status === 'finance_closure_pending'
                  const isClosed = row.normalized_status === 'closed'
                  const isReturned = row.normalized_status === 'finance_returned'
                  const statusTone = isClosed ? 'success' : isReturned ? 'danger' : isPending ? 'warning' : 'info'

                  return (
                    <tr key={row.id}>
                      {/* 1. Project & Client */}
                      <td style={{ minWidth: 200 }}>
                        <div className="fin-cell-code">{row.project_code}</div>
                        <div className="fin-cell-name">{row.project_name}</div>
                        <div className="fin-cell-client">
                          <User size={11} /> {row.client_name || row.client_code || 'Client unrecorded'}
                        </div>
                      </td>

                      {/* 2. Department */}
                      <td>
                        <span className="fin-cell-dept">{row.performing_department_label || 'Ortho'}</span>
                        {row.project_manager_name && (
                          <div style={{ fontSize: '0.7rem', color: '#64748b', marginTop: 3 }}>
                            PM: {row.project_manager_name}
                          </div>
                        )}
                      </td>

                      {/* 3. Commercial Baseline */}
                      <td>
                        <div className="fin-cell-amount">
                          {formatInr(row.commercial_value || 0)}
                        </div>
                        {row.po_wo_number ? (
                          <span className="fin-cell-powo">PO/WO: {row.po_wo_number}</span>
                        ) : (
                          <span style={{ fontSize: '0.68rem', color: '#94a3b8' }}>No PO/WO</span>
                        )}
                        {row.commercial_summary?.baseline && (
                          <div style={{ fontSize: '0.68rem', color: '#0369a1', marginTop: 2 }}>
                            {row.commercial_summary.baseline.billing_type_label || 'Fixed Price'}
                          </div>
                        )}
                      </td>

                      {/* 4. Timeline */}
                      <td>
                        <div className="fin-cell-dates">
                          {row.start_date || '—'} → {row.end_date || '—'}
                        </div>
                        {row.scope_text && (
                          <div
                            style={{
                              fontSize: '0.7rem',
                              color: '#64748b',
                              maxWidth: 160,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                              marginTop: 2,
                            }}
                            title={row.scope_text}
                          >
                            {row.scope_text}
                          </div>
                        )}
                      </td>

                      {/* 5. Expenses Exposure */}
                      <td>
                        {row.expense_summary ? (
                          <div className="fin-cell-expenses">
                            <span className="fin-cell-expenses-paid">
                              {formatInr(row.expense_summary.paid_amount)} Paid
                            </span>
                            <span className="fin-cell-expenses-out">
                              {formatInr(row.expense_summary.requested_amount)} Req ({row.expense_summary.claim_count} claims)
                            </span>
                          </div>
                        ) : (
                          <span style={{ fontSize: '0.72rem', color: '#94a3b8' }}>Zero claims</span>
                        )}
                      </td>

                      {/* 6. Status */}
                      <td>
                        <span className={`fin-status-pill ${statusTone}`}>
                          {label(row.workflow_status)}
                        </span>
                        {row.finance_feedback && (
                          <div style={{ fontSize: '0.68rem', color: '#b91c1c', marginTop: 3, maxWidth: 140 }}>
                            FB: {row.finance_feedback}
                          </div>
                        )}
                      </td>

                      {/* 7. Action */}
                      <td style={{ textAlign: 'right' }}>
                        {user?.role === 'finance' && isPending ? (
                          <button
                            className="fin-btn-primary"
                            disabled={busy}
                            onClick={() => openReview(row)}
                          >
                            Review Project
                          </button>
                        ) : user?.role === 'finance' && isClosurePending ? (
                          <button
                            className="fin-btn-success"
                            disabled={busy || !row.finance_closable}
                            title={row.finance_closable ? undefined : (row.finance_closure_blocker || 'Not ready')}
                            onClick={() => closeProject(row)}
                          >
                            Finance Closure
                          </button>
                        ) : (
                          <button
                            className="fin-btn-secondary"
                            onClick={() => openReview(row)}
                          >
                            {isClosed ? 'View' : 'Details'}
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ═══════════ TAB 2: FINANCIAL ANALYTICS & CHARTS ═══════════ */}
      {activeTab === 'analytics' && (
        <div className="fin-analytics-grid">
          {/* Chart 1: Monthly Billing vs Collection Trend */}
          <div className="fin-card">
            <div className="fin-card-header">
              <h3 className="fin-card-title"><TrendingUp size={16} /> Monthly Billing & Collections Trend</h3>
              <span className="fin-card-subtitle">Last 7 months cash flow</span>
            </div>
            {monthlyTrend.length > 1 ? (
              <TrendChart data={monthlyTrend} height={140} />
            ) : (
              <div className="nk-empty"><p>Trend analytics will display once multiple months are billed.</p></div>
            )}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, paddingTop: 12, borderTop: '1px solid #f1f5f9' }}>
              <div>
                <span className="fin-kpi-label">Total Billed Net</span>
                <div style={{ fontSize: '1.05rem', fontWeight: 800, color: '#1d4ed8' }}>{formatInr(billedNet)}</div>
              </div>
              <div>
                <span className="fin-kpi-label">Payments Realized</span>
                <div style={{ fontSize: '1.05rem', fontWeight: 800, color: '#15803d' }}>{formatInr(paymentsRealized)}</div>
              </div>
              <div>
                <span className="fin-kpi-label">Outstanding Balance</span>
                <div style={{ fontSize: '1.05rem', fontWeight: 800, color: '#b45309' }}>{formatInr(billedNet - paymentsRealized)}</div>
              </div>
            </div>
          </div>

          {/* Chart 2: Expense Allocation by Category */}
          <div className="fin-card">
            <div className="fin-card-header">
              <h3 className="fin-card-title"><PieChart size={16} /> Expense Allocation by Category</h3>
              <span className="fin-card-subtitle">Where company funds are spent</span>
            </div>
            {categorySegments.length > 0 ? (
              <DonutChart segments={categorySegments} size={150} centerLabel={`${data?.total_claims ?? 0} Claims`} />
            ) : (
              <div className="nk-empty"><p>No expense claims recorded yet.</p></div>
            )}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12, paddingTop: 12, borderTop: '1px solid #f1f5f9' }}>
              <div>
                <span className="fin-kpi-label">Total Claims Requested</span>
                <div style={{ fontSize: '1.05rem', fontWeight: 800, color: '#082a52' }}>{formatInr(data?.total_requested_amount ?? 0)}</div>
              </div>
              <div>
                <span className="fin-kpi-label">Total Disbursed</span>
                <div style={{ fontSize: '1.05rem', fontWeight: 800, color: '#15803d' }}>{formatInr(data?.paid_amount ?? 0)}</div>
              </div>
            </div>
          </div>

          {/* Project-wise Spend Breakdown */}
          {data && data.by_project.length > 0 && (
            <div className="fin-card" style={{ gridColumn: '1 / -1' }}>
              <div className="fin-card-header">
                <h3 className="fin-card-title"><FolderKanban size={16} /> Project-Wise Expense Exposure</h3>
                <span className="fin-card-subtitle">Grouped by assigned Project ID</span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14 }}>
                {data.by_project.slice(0, 9).map(proj => {
                  const maxAmt = Math.max(1, ...data.by_project.map(p => p.amount))
                  return (
                    <div key={proj.key} style={{ background: '#f8fbfe', border: '1px solid #d8e4ef', borderRadius: 10, padding: 12 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 4 }}>
                        <strong style={{ fontSize: '0.84rem', color: '#082a52' }}>{proj.label}</strong>
                        <span style={{ fontSize: '0.84rem', fontWeight: 800, color: '#1d4ed8' }}>{formatInr(proj.amount)}</span>
                      </div>
                      <div className="fin-progress-track" style={{ height: 6 }}>
                        <div className="fin-progress-fill" style={{ width: `${Math.max(4, (proj.amount / maxAmt) * 100)}%`, background: '#2563eb' }} />
                      </div>
                      <div style={{ fontSize: '0.68rem', color: '#64748b', marginTop: 4 }}>{proj.count} claims lodged</div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ═══════════ TAB 3: EXPENSE CLAIMS & DISBURSEMENTS ═══════════ */}
      {activeTab === 'expenses' && data && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* Claims Secondary KPIs */}
          <div className="fin-hero-kpis" style={{ margin: 0 }}>
            <div className="fin-hero-kpi-card">
              <span className="fin-kpi-label">Pending Admin Approval</span>
              <span className="fin-kpi-value" style={{ color: '#b45309' }}>{data.pending_admin_count}</span>
              <span className="fin-kpi-sub">{formatInr(data.pending_admin_amount)} awaiting verification</span>
            </div>
            <div className="fin-hero-kpi-card">
              <span className="fin-kpi-label">Pending Finance Approval</span>
              <span className="fin-kpi-value" style={{ color: '#6d28d9' }}>{data.pending_finance_count}</span>
              <span className="fin-kpi-sub">{formatInr(data.pending_finance_amount)} Admin-verified</span>
            </div>
            <div className="fin-hero-kpi-card">
              <span className="fin-kpi-label">Finance Approved</span>
              <span className="fin-kpi-value" style={{ color: '#15803d' }}>{data.approved_count}</span>
              <span className="fin-kpi-sub">{formatInr(data.approved_amount)} in payment stage</span>
            </div>
            <div className="fin-hero-kpi-card">
              <span className="fin-kpi-label">Paid / Settled</span>
              <span className="fin-kpi-value" style={{ color: '#082a52' }}>{data.paid_count}</span>
              <span className="fin-kpi-sub">{formatInr(data.paid_amount)} released</span>
            </div>
          </div>

          {/* Recent Claims Table */}
          <div className="fin-table-card">
            <div style={{ padding: '16px 18px', background: '#f8fbfe', borderBottom: '1px solid #d8e4ef', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <strong style={{ fontSize: '0.92rem', color: '#082a52' }}>Recent Expense Claims</strong>
                <p style={{ margin: 0, fontSize: '0.74rem', color: '#64748b' }}>Review submitted employee project expenses and payment statuses.</p>
              </div>
              <Link className="fin-btn-secondary" to="/finance/claims">View All Claims</Link>
            </div>
            <table className="fin-table">
              <thead>
                <tr>
                  <th>Claim Code</th>
                  <th>Employee</th>
                  <th>Project</th>
                  <th>Type</th>
                  <th>Amount</th>
                  <th>Status</th>
                  <th>Submitted Date</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_claims.map(claim => (
                  <tr key={claim.id}>
                    <td><Link to={`/finance/claims/${claim.id}`} style={{ fontWeight: 800, color: '#1d4ed8' }}>{claim.claim_code}</Link></td>
                    <td>
                      <strong style={{ color: '#082a52' }}>{claim.requester_name}</strong>
                      <div style={{ fontSize: '0.7rem', color: '#64748b' }}>{claim.requester_email}</div>
                    </td>
                    <td>
                      <div style={{ fontWeight: 700, color: '#082a52' }}>{claim.project.project_code}</div>
                      <div style={{ fontSize: '0.7rem', color: '#64748b' }}>{claim.project.project_name}</div>
                    </td>
                    <td>
                      <span className="fin-cell-dept" style={{ fontSize: '0.68rem' }}>
                        {financeClaimTypeLabels[claim.claim_type]}
                      </span>
                    </td>
                    <td><strong style={{ fontSize: '0.9rem', color: '#082a52' }}>{formatInr(claim.total_amount)}</strong></td>
                    <td>
                      <span className={`fin-status-pill tone-${financeStatusTone(claim.status)}`}>
                        {financeStatusLabels[claim.status]}
                      </span>
                    </td>
                    <td style={{ fontSize: '0.76rem', color: '#475569' }}>
                      {claim.submitted_at ? new Date(claim.submitted_at).toLocaleDateString('en-IN') : 'Draft'}
                    </td>
                  </tr>
                ))}
                {!data.recent_claims.length && (
                  <tr><td colSpan={7} style={{ textAlign: 'center', padding: '28px', color: '#64748b' }}>No expense claims found.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ═══════════ TAB 4: FINANCE COMMAND CENTER ═══════════ */}
      {activeTab === 'command_center' && (
        <FinanceCommandCenter />
      )}

      {/* ═══════════ SLIDE-OVER REVIEW DRAWER ═══════════ */}
      {reviewProject && createPortal(
        <div className="fin-detail-overlay" role="presentation" onMouseDown={e => { if (e.target === e.currentTarget) setReviewId(null) }}>
          <aside className="fin-detail-drawer" role="dialog" aria-modal="true" aria-labelledby="review-drawer-title">
            <div className="fin-drawer-header">
              <div className="fin-drawer-title-group">
                <span className="fin-status-pill info">
                  {reviewProject.normalized_status === 'pending_finance_approval' ? 'Pending Finance Approval' : label(reviewProject.workflow_status)}
                </span>
                <h2 id="review-drawer-title">{reviewProject.project_code} — {reviewProject.project_name}</h2>
              </div>
              <button type="button" className="fin-drawer-close" onClick={() => setReviewId(null)} aria-label="Close drawer">
                <X size={18} />
              </button>
            </div>

            {/* Client Facts */}
            <div>
              <span className="fin-kpi-label">Client Information</span>
              <div className="fin-facts-grid" style={{ marginTop: 8 }}>
                <div className="fin-fact-item">
                  <span className="fin-fact-label">Organization Name</span>
                  <span className="fin-fact-value">{reviewProject.client?.organization_name || reviewProject.client_name || '—'}</span>
                </div>
                <div className="fin-fact-item">
                  <span className="fin-fact-label">Client Code</span>
                  <span className="fin-fact-value">{reviewProject.client?.client_code || reviewProject.client_code || '—'}</span>
                </div>
                <div className="fin-fact-item">
                  <span className="fin-fact-label">GST Number</span>
                  <span className="fin-fact-value">{reviewProject.client?.gst_number || 'Not recorded'}</span>
                </div>
                <div className="fin-fact-item">
                  <span className="fin-fact-label">Location</span>
                  <span className="fin-fact-value">{reviewProject.client?.location || '—'}</span>
                </div>
                <div className="fin-fact-item">
                  <span className="fin-fact-label">Contact Person</span>
                  <span className="fin-fact-value">{reviewProject.client?.contact_person_name || '—'}</span>
                </div>
                <div className="fin-fact-item">
                  <span className="fin-fact-label">BD Representative</span>
                  <span className="fin-fact-value">{reviewProject.client?.bd_person || '—'}</span>
                </div>
              </div>
            </div>

            {/* Project Facts */}
            <div>
              <span className="fin-kpi-label">Project Scope & Dates</span>
              <div className="fin-facts-grid" style={{ marginTop: 8 }}>
                <div className="fin-fact-item">
                  <span className="fin-fact-label">Performing Department</span>
                  <span className="fin-fact-value">{reviewProject.performing_department_label || 'Ortho'}</span>
                </div>
                <div className="fin-fact-item">
                  <span className="fin-fact-label">Timeline</span>
                  <span className="fin-fact-value">{reviewProject.start_date || '—'} → {reviewProject.end_date || '—'}</span>
                </div>
                <div className="fin-fact-item" style={{ gridColumn: '1 / -1' }}>
                  <span className="fin-fact-label">Project Scope Description</span>
                  <span className="fin-fact-value" style={{ fontWeight: 500, lineHeight: 1.5, fontSize: '0.84rem' }}>
                    {reviewProject.scope_text || 'No scope details recorded.'}
                  </span>
                </div>
              </div>
            </div>

            {/* Commercial Summary Component */}
            <div>
              <span className="fin-kpi-label">Commercial Baseline (Revision 1)</span>
              <div style={{ marginTop: 8 }}>
                <FinanceCommercialSummary
                  projectId={reviewProject.id}
                  fallback={{
                    currency: reviewProject.currency,
                    commercial_value: reviewProject.commercial_value,
                    po_wo_number: reviewProject.po_wo_number,
                  }}
                />
              </div>
            </div>

            {/* Audit Trail */}
            <div>
              <span className="fin-kpi-label">Submission & Review History</span>
              <div className="fin-facts-grid" style={{ marginTop: 8 }}>
                <div className="fin-fact-item">
                  <span className="fin-fact-label">Created By</span>
                  <span className="fin-fact-value">{reviewProject.created_by_name || '—'}</span>
                </div>
                <div className="fin-fact-item">
                  <span className="fin-fact-label">Submitted By</span>
                  <span className="fin-fact-value">{reviewProject.submitted_by_name || '—'}</span>
                </div>
                <div className="fin-fact-item">
                  <span className="fin-fact-label">Finance Reviewer</span>
                  <span className="fin-fact-value">{reviewProject.finance_reviewer_name || 'Not reviewed'}</span>
                </div>
                <div className="fin-fact-item">
                  <span className="fin-fact-label">Reviewed At</span>
                  <span className="fin-fact-value">
                    {reviewProject.finance_reviewed_at ? new Date(reviewProject.finance_reviewed_at).toLocaleString('en-IN') : '—'}
                  </span>
                </div>
              </div>
              {reviewProject.finance_feedback && (
                <div className="finance-error" style={{ marginTop: 10 }}>
                  <strong>Previous Finance Feedback:</strong> {reviewProject.finance_feedback}
                </div>
              )}
            </div>

            {/* Decision Controls */}
            {user?.role === 'finance' && reviewProject.normalized_status === 'pending_finance_approval' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12, borderTop: '2px solid #eef4fa', paddingTop: 16 }}>
                <label className="finance-field">
                  <span>Mandatory Feedback if Returning to BD</span>
                  <textarea
                    value={returnFeedback}
                    onChange={e => setReturnFeedback(e.target.value)}
                    placeholder="Explain what the BD team must correct before resubmission..."
                    rows={2}
                  />
                </label>
                <label className="finance-field">
                  <span>Approval Note (Optional)</span>
                  <textarea
                    value={approveNote}
                    onChange={e => setApproveNote(e.target.value)}
                    placeholder="Optional internal remarks for baseline lock..."
                    rows={2}
                  />
                </label>
                <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 6 }}>
                  <button
                    className="fin-btn-secondary"
                    disabled={busy}
                    onClick={() => review(reviewProject, 'return')}
                  >
                    Return to BD
                  </button>
                  <button
                    className="fin-btn-primary"
                    disabled={busy}
                    onClick={() => review(reviewProject, 'approve')}
                  >
                    Approve Project & Lock Baseline
                  </button>
                </div>
              </div>
            )}

            {user?.role === 'finance' && reviewProject.normalized_status === 'finance_closure_pending' && (
              <div style={{ borderTop: '2px solid #eef4fa', paddingTop: 16 }}>
                <strong style={{ color: '#082a52' }}>Finance Closure Readiness</strong>
                <p style={{ fontSize: '0.8rem', color: '#475569', margin: '4px 0 12px' }}>
                  {reviewProject.finance_closable
                    ? 'All deliverables, invoices, and payments are complete. Ready for formal Finance Closure.'
                    : (reviewProject.finance_closure_blocker || 'Project has pending items blocking closure.')}
                </p>
                <button
                  className="fin-btn-success"
                  disabled={busy || !reviewProject.finance_closable}
                  onClick={() => closeProject(reviewProject)}
                >
                  Complete Finance Closure
                </button>
              </div>
            )}
          </aside>
        </div>,
        document.body,
      )}
    </div>
  )
}
