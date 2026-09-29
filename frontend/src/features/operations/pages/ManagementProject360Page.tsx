import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  Check,
  CheckCircle2,
  Clock3,
  CreditCard,
  DollarSign,
  FileCheck,
  FileText,
  Filter,
  FolderKanban,
  IndianRupee,
  Layers,
  MessageSquare,
  Package,
  RefreshCcw,
  RotateCcw,
  Search,
  Send,
  ShieldAlert,
  ShieldCheck,
  User,
  Users,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch } from '../../../lib/api'
import {
  ChangeRequestRow,
  LifecycleDashboard,
  Project360,
  ProjectMessageRow,
  formatDate,
  formatDateTime,
  formatMoney,
  lifecycleStatusLabel,
  lifecycleStatusTone,
  reworkCycleTypeLabel,
} from '../lifecycle-types'
import '../operations.css'
import '../project-360-v2.css'

const CHAT_ROLES = new Set(['management', 'admin', 'ortho'])

type FilterCategory = 'all' | 'active' | 'review' | 'billing' | 'overdue' | 'closed'

/** 6-stage lifecycle pipeline calculation */
function getLifecycleStage(status: string): { stage: number; label: string } {
  const s = (status || '').toLowerCase()
  if (['closed', 'invoice_closed', 'payment_received'].includes(s)) {
    return { stage: 6, label: 'Closed & Paid' }
  }
  if (['payment_pending', 'partially_paid', 'payment_overdue', 'invoice_raised', 'invoice_draft', 'ready_for_billing', 'deemed_accepted', 'client_accepted'].includes(s)) {
    return { stage: 5, label: 'Billing & Invoicing' }
  }
  if (s.includes('feedback') || s.includes('rework') || s.includes('awaiting')) {
    return { stage: 4, label: 'Client Review & QC' }
  }
  if (['operational_complete', 'qa_review', 'qc_review', 'in_production', 'production'].includes(s)) {
    return { stage: 3, label: 'Production & QA' }
  }
  if (['finance_approved', 'pm_assigned', 'team_assigned'].includes(s)) {
    return { stage: 2, label: 'Finance & PM Setup' }
  }
  return { stage: 1, label: 'Initiation & Scope' }
}

const LIFECYCLE_STAGES = [
  { step: 1, name: 'Initiation' },
  { step: 2, name: 'Setup & Approval' },
  { step: 3, name: 'Production' },
  { step: 4, name: 'Client Review' },
  { step: 5, name: 'Invoicing' },
  { step: 6, name: 'Closed' },
]

export function ManagementProject360Page() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const { projectId } = useParams()
  const isManagement = user?.role === 'management' || user?.role === 'admin'
  const canChat = user ? CHAT_ROLES.has(user.role) : false

  const [dashboard, setDashboard] = useState<LifecycleDashboard | null>(null)
  const [detail, setDetail] = useState<Project360 | null>(null)
  const [messages, setMessages] = useState<ProjectMessageRow[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<FilterCategory>('all')
  const [activeTab, setActiveTab] = useState<'overview' | 'invoices' | 'deliveries' | 'actions' | 'timeline' | 'chat'>('overview')
  const [chatText, setChatText] = useState('')

  const [deemedBasis, setDeemedBasis] = useState('')
  const [decisionForm, setDecisionForm] = useState<Record<number, { decision: 'approved' | 'rejected'; comments: string }>>({})

  const selectedId = projectId ? Number(projectId) : null
  const basePath = user?.role === 'ortho' ? '/ortho/project-360' : '/management/project-360'

  function loadDashboard() {
    setLoading(true)
    setError('')
    void apiFetch<LifecycleDashboard>('/operations/lifecycle/dashboard')
      .then(data => {
        setDashboard(data)
        if (!selectedId && data.projects.length) {
          navigate(`${basePath}/${data.projects[0].id}`, { replace: true })
        }
      })
      .catch(err => setError(err instanceof Error ? err.message : 'Unable to load the lifecycle dashboard'))
      .finally(() => setLoading(false))
  }

  function loadDetail(id: number) {
    void apiFetch<Project360>(`/operations/lifecycle/projects/${id}`)
      .then(setDetail)
      .catch(err => setError(err instanceof Error ? err.message : 'Unable to load project detail'))

    if (canChat) {
      void apiFetch<ProjectMessageRow[]>(`/operations/lifecycle/projects/${id}/messages`)
        .then(setMessages)
        .catch(() => setMessages([]))
    } else {
      setMessages([])
    }
  }

  useEffect(() => { loadDashboard() }, [])
  useEffect(() => { if (selectedId) loadDetail(selectedId) }, [selectedId])

  // Filter projects by category and search keyword
  const filteredProjects = useMemo(() => {
    const rows = dashboard?.projects ?? []
    return rows.filter(row => {
      // Search match
      const term = search.trim().toLowerCase()
      const matchesSearch = !term || (
        row.project_code.toLowerCase().includes(term) ||
        row.project_name.toLowerCase().includes(term) ||
        (row.client_name || '').toLowerCase().includes(term) ||
        (row.client_id || '').toLowerCase().includes(term) ||
        (row.project_manager_name || '').toLowerCase().includes(term)
      )
      if (!matchesSearch) return false

      // Category filter
      const s = (row.workflow_status || '').toLowerCase()
      if (filter === 'overdue') return row.has_overdue_invoice
      if (filter === 'closed') return ['closed', 'invoice_closed', 'payment_received'].includes(s)
      if (filter === 'review') return s.includes('feedback') || s.includes('rework') || s.includes('awaiting')
      if (filter === 'billing') return ['ready_for_billing', 'invoice_draft', 'invoice_raised', 'payment_pending', 'partially_paid', 'payment_overdue'].includes(s)
      if (filter === 'active') return !['closed', 'invoice_closed'].includes(s)
      return true
    })
  }, [dashboard, search, filter])

  async function run(key: string, action: () => Promise<unknown>, successMessage: string) {
    setBusy(key)
    setError('')
    setNotice('')
    try {
      await action()
      setNotice(successMessage)
      if (selectedId) loadDetail(selectedId)
      loadDashboard()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Action failed')
    } finally {
      setBusy('')
    }
  }

  async function authorizeDeemedAcceptance(requestId: number) {
    await apiFetch(`/operations/lifecycle/feedback-requests/${requestId}/deemed-acceptance`, {
      method: 'POST',
      body: JSON.stringify({ authority_basis: deemedBasis.trim() }),
    })
    setDeemedBasis('')
  }

  async function decide(row: ChangeRequestRow) {
    const form = decisionForm[row.id]
    if (!form) return
    await apiFetch(`/operations/lifecycle/change-requests/${row.id}/decision`, {
      method: 'POST',
      body: JSON.stringify({
        decision: form.decision,
        comments: form.comments.trim() || 'Decision recorded',
        commercial_impact: row.commercial_impact,
        currency: row.currency,
      }),
    })
  }

  async function sendChat() {
    if (!selectedId || !chatText.trim()) return
    await apiFetch(`/operations/lifecycle/projects/${selectedId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ message: chatText.trim() }),
    })
    setChatText('')
    loadDetail(selectedId)
  }

  const closureRecommendedRequest = detail?.feedback_requests.find(row => row.status === 'closure_recommended') || null
  const pendingChangeRequests = detail?.change_requests.filter(row => row.status === 'pending') ?? []
  const hasActionsNeeded = Boolean(closureRecommendedRequest || pendingChangeRequests.length > 0)

  // Current project stage
  const currentStageInfo = detail ? getLifecycleStage(detail.workflow_status) : { stage: 1, label: 'Initiation' }

  // Total invoice stats for this project
  const totalInvoiced = detail?.invoices.reduce((sum, inv) => sum + (inv.total_amount || 0), 0) ?? 0
  const totalPaid = detail?.invoices.reduce((sum, inv) => sum + (inv.paid_amount || 0), 0) ?? 0
  const totalBalance = detail?.invoices.reduce((sum, inv) => sum + (inv.balance || 0), 0) ?? (detail?.invoice_balance ?? 0)

  return (
    <div className="operations-page">
      <DashboardHeader
        variant="workbench"
        eyebrow={isManagement ? 'MANAGEMENT · EXECUTIVE SUITE' : 'OPERATIONAL PROJECT VIEW'}
        title="Project 360"
        description={
          isManagement
            ? 'Complete 360° overview of every project: lifecycle stage, assigned PM, commercial impact, invoices, and timeline.'
            : 'Operational project tracking: delivery milestones, feedback status, rework history, and management communication.'
        }
        actions={
          <button className="operations-button secondary" onClick={loadDashboard}>
            <RefreshCcw size={16} /> Refresh
          </button>
        }
        meta={
          <>
            <span className="nk-meta-chip"><ShieldCheck size={14} /> {isManagement ? 'Full Executive Access' : 'Restricted Operational View'}</span>
            <span className="nk-meta-chip"><FolderKanban size={14} /> {dashboard?.projects.length ?? 0} Total Projects</span>
            <span className="nk-meta-chip"><Activity size={14} /> Real-time Progress Tracking</span>
          </>
        }
      />

      {error && <div className="operations-alert error"><AlertCircle size={16} /> {error}</div>}
      {notice && <div className="operations-alert success"><CheckCircle2 size={16} /> {notice}</div>}

      {/* ═══════════ TOP SUMMARY CARDS (Clickable Filters) ═══════════ */}
      {dashboard && (
        <section className="p360-summary-cards">
          <div
            className={`p360-summary-card ${filter === 'all' ? 'active' : ''}`}
            onClick={() => setFilter('all')}
          >
            <div className="p360-summary-icon blue"><FolderKanban size={22} /></div>
            <div className="p360-summary-data">
              <span className="p360-summary-label">Total Projects</span>
              <span className="p360-summary-value">{dashboard.summary.total_projects}</span>
            </div>
          </div>

          <div
            className={`p360-summary-card ${filter === 'review' ? 'active' : ''}`}
            onClick={() => setFilter(filter === 'review' ? 'all' : 'review')}
          >
            <div className="p360-summary-icon orange"><Clock3 size={22} /></div>
            <div className="p360-summary-data">
              <span className="p360-summary-label">Awaiting Feedback</span>
              <span className="p360-summary-value">{dashboard.summary.awaiting_feedback}</span>
            </div>
          </div>

          <div
            className={`p360-summary-card ${filter === 'overdue' ? 'active' : ''}`}
            onClick={() => setFilter(filter === 'overdue' ? 'all' : 'overdue')}
          >
            <div className="p360-summary-icon red"><AlertTriangle size={22} /></div>
            <div className="p360-summary-data">
              <span className="p360-summary-label">Overdue Invoices</span>
              <span className="p360-summary-value">{dashboard.summary.overdue}</span>
            </div>
          </div>

          <div
            className={`p360-summary-card ${filter === 'closed' ? 'active' : ''}`}
            onClick={() => setFilter(filter === 'closed' ? 'all' : 'closed')}
          >
            <div className="p360-summary-icon green"><CheckCircle2 size={22} /></div>
            <div className="p360-summary-data">
              <span className="p360-summary-label">Closed Projects</span>
              <span className="p360-summary-value">{dashboard.summary.closed}</span>
            </div>
          </div>
        </section>
      )}

      {/* ═══════════ MAIN MASTER-DETAIL WORKSPACE ═══════════ */}
      <div className="p360-workspace-grid">
        {/* ─── LEFT: PROJECT DIRECTORY & REGISTER ─── */}
        <aside className="p360-sidebar">
          <div className="p360-sidebar-header">
            <h3 className="p360-sidebar-title">Project Directory</h3>
            <span className="p360-sidebar-count">{filteredProjects.length}</span>
          </div>

          {/* Search box */}
          <div className="p360-search-box">
            <Search className="p360-search-icon" size={16} />
            <input
              className="p360-search-input"
              placeholder="Search code, client, PM..."
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>

          {/* Filter Pills */}
          <div className="p360-filter-chips">
            <button className={`p360-filter-chip ${filter === 'all' ? 'active' : ''}`} onClick={() => setFilter('all')}>All</button>
            <button className={`p360-filter-chip ${filter === 'active' ? 'active' : ''}`} onClick={() => setFilter('active')}>Active</button>
            <button className={`p360-filter-chip ${filter === 'review' ? 'active' : ''}`} onClick={() => setFilter('review')}>Feedback</button>
            <button className={`p360-filter-chip ${filter === 'billing' ? 'active' : ''}`} onClick={() => setFilter('billing')}>Billing</button>
            <button className={`p360-filter-chip ${filter === 'overdue' ? 'active' : ''}`} onClick={() => setFilter('overdue')}>Overdue</button>
            <button className={`p360-filter-chip ${filter === 'closed' ? 'active' : ''}`} onClick={() => setFilter('closed')}>Closed</button>
          </div>

          {/* Project List Items */}
          <div className="p360-project-list">
            {loading && <div className="operations-empty">Loading projects…</div>}
            {!loading && !filteredProjects.length && (
              <div className="operations-empty">No projects match the selected filter.</div>
            )}
            {filteredProjects.map(proj => (
              <button
                key={proj.id}
                type="button"
                className={`p360-project-item ${proj.id === selectedId ? 'active' : ''}`}
                onClick={() => navigate(`${basePath}/${proj.id}`)}
              >
                <div className="p360-item-top">
                  <span className="p360-item-code">{proj.project_code}</span>
                  <span className={`p360-status-pill ${lifecycleStatusTone(proj.workflow_status)}`} style={{ padding: '2px 8px', fontSize: '0.68rem' }}>
                    {lifecycleStatusLabel(proj.workflow_status)}
                  </span>
                </div>

                <div className="p360-item-name">{proj.project_name}</div>
                <div className="p360-item-client">
                  <User size={12} /> {proj.client_name || proj.client_id || 'Client unrecorded'}
                </div>

                <div className="p360-item-bottom">
                  <div className="p360-item-progress-wrap" title={`Progress: ${proj.progress_percent}%`}>
                    <div className="p360-item-progress-bar" style={{ width: `${proj.progress_percent}%` }} />
                  </div>
                  {proj.has_overdue_invoice && (
                    <span className="p360-badge-overdue" title="Overdue invoice pending payment">
                      <AlertTriangle size={11} /> Overdue
                    </span>
                  )}
                </div>
              </button>
            ))}
          </div>
        </aside>

        {/* ─── RIGHT: COMPREHENSIVE PROJECT 360 DETAIL ─── */}
        <main className="p360-detail-panel">
          {!detail && <div className="operations-empty">Select a project to inspect its 360° lifecycle view.</div>}

          {detail && (
            <>
              {/* 1. HERO HEADER */}
              <div className="p360-hero-header">
                <div className="p360-hero-title-group">
                  <div className="p360-hero-chips">
                    <span className="p360-hero-code">{detail.project_code}</span>
                    <span className="p360-hero-client">
                      {detail.client_name || detail.client_id || 'Client Identity Restricted'}
                    </span>
                    {detail.has_overdue_invoice && (
                      <span className="p360-badge-overdue">
                        <AlertTriangle size={12} /> Overdue Invoice
                      </span>
                    )}
                  </div>
                  <h2 className="p360-hero-title">{detail.project_name}</h2>
                </div>

                <div className="p360-hero-status-wrap">
                  <span className={`p360-status-pill ${lifecycleStatusTone(detail.workflow_status)}`}>
                    {lifecycleStatusLabel(detail.workflow_status)}
                  </span>
                </div>
              </div>

              {/* 2. LIFECYCLE STAGE PIPELINE STEPPER */}
              <section className="p360-stepper-container">
                <div className="p360-stepper-title">
                  <span>Lifecycle Pipeline Status</span>
                  <span>Current: <strong>{currentStageInfo.label}</strong> ({detail.progress_percent}% complete)</span>
                </div>
                <div className="p360-stepper-steps">
                  {LIFECYCLE_STAGES.map(stage => {
                    const isCompleted = stage.step < currentStageInfo.stage
                    const isActive = stage.step === currentStageInfo.stage
                    return (
                      <div
                        key={stage.step}
                        className={`p360-step ${isCompleted ? 'completed' : ''} ${isActive ? 'active' : ''}`}
                      >
                        <div className="p360-step-indicator">
                          {isCompleted ? <Check size={16} /> : stage.step}
                        </div>
                        <span className="p360-step-label">{stage.name}</span>
                      </div>
                    )
                  })}
                </div>
              </section>

              {/* 3. KEY METRICS GRID */}
              <section className="p360-metrics-grid">
                <div className="p360-metric-card">
                  <span className="p360-metric-label">Project Manager</span>
                  <span className="p360-metric-val">{detail.project_manager_name || 'Not Assigned'}</span>
                  <span className="p360-metric-sub">TL: {detail.team_leader_name || 'None'}</span>
                </div>

                <div className="p360-metric-card">
                  <span className="p360-metric-label">Progress</span>
                  <span className="p360-metric-val">{detail.progress_percent}%</span>
                  <div className="operations-progress" style={{ marginTop: 4 }}>
                    <span style={{ width: `${detail.progress_percent}%` }} />
                  </div>
                </div>

                <div className="p360-metric-card">
                  <span className="p360-metric-label">Rework & Deliveries</span>
                  <span className="p360-metric-val">{detail.rework_count} Cycles</span>
                  <span className="p360-metric-sub">{detail.delivery_versions?.length || 0} Delivery Version(s)</span>
                </div>

                {isManagement && (
                  <div className="p360-metric-card">
                    <span className="p360-metric-label">Invoice Balance</span>
                    <span className={`p360-metric-val ${detail.has_overdue_invoice ? 'text-red' : ''}`}>
                      {formatMoney(totalBalance)}
                    </span>
                    <span className="p360-metric-sub">
                      {totalInvoiced > 0 ? `${formatMoney(totalPaid)} Paid` : 'No Invoices Yet'}
                    </span>
                  </div>
                )}
              </section>

              {/* 4. ACTION REQUIRED BANNERS (If any management action is pending) */}
              {isManagement && closureRecommendedRequest && (
                <div className="p360-action-banner">
                  <div className="p360-banner-header">
                    <ShieldAlert size={18} />
                    <span>Management Authorization Required: Deemed Acceptance</span>
                  </div>
                  <p className="p360-banner-desc">
                    BD has recommended no-feedback closure for <strong>{closureRecommendedRequest.request_code}</strong>.
                    As per compliance policy, only Management or Admin can authorize deemed acceptance to release the project for billing.
                  </p>
                  <label className="operations-field">
                    <span>Contractual Clause / Authorization Basis</span>
                    <textarea
                      placeholder="Enter contractual justification (e.g. Section 4.2 expired after 14 days client silence)..."
                      value={deemedBasis}
                      onChange={e => setDeemedBasis(e.target.value)}
                      rows={2}
                    />
                  </label>
                  <div className="operations-actions">
                    <button
                      className="operations-button warning"
                      disabled={busy === 'deemed' || deemedBasis.trim().length < 5}
                      onClick={() => void run('deemed', () => authorizeDeemedAcceptance(closureRecommendedRequest.id), 'Deemed acceptance authorized; project marked Ready for Billing')}
                    >
                      Authorize Deemed Acceptance
                    </button>
                  </div>
                </div>
              )}

              {/* 5. TABS NAVIGATION */}
              <nav className="p360-tabs-nav">
                <button
                  type="button"
                  className={`p360-tab-btn ${activeTab === 'overview' ? 'active' : ''}`}
                  onClick={() => setActiveTab('overview')}
                >
                  <FileText size={15} /> Overview & Scope
                </button>

                {isManagement && (
                  <button
                    type="button"
                    className={`p360-tab-btn ${activeTab === 'invoices' ? 'active' : ''}`}
                    onClick={() => setActiveTab('invoices')}
                  >
                    <CreditCard size={15} /> Invoices & Payments
                    {detail.invoices.length > 0 && <span className="p360-tab-badge">{detail.invoices.length}</span>}
                  </button>
                )}

                <button
                  type="button"
                  className={`p360-tab-btn ${activeTab === 'deliveries' ? 'active' : ''}`}
                  onClick={() => setActiveTab('deliveries')}
                >
                  <Package size={15} /> Deliveries & Feedback
                  {(detail.delivery_versions.length > 0 || detail.rework_cycles.length > 0) && (
                    <span className="p360-tab-badge">{detail.delivery_versions.length + detail.rework_cycles.length}</span>
                  )}
                </button>

                {isManagement && (
                  <button
                    type="button"
                    className={`p360-tab-btn ${activeTab === 'actions' ? 'active' : ''}`}
                    onClick={() => setActiveTab('actions')}
                  >
                    <ShieldCheck size={15} /> Decisions & Scope Changes
                    {pendingChangeRequests.length > 0 && (
                      <span className="p360-tab-badge" style={{ background: '#ef4444', color: '#fff' }}>
                        {pendingChangeRequests.length}
                      </span>
                    )}
                  </button>
                )}

                <button
                  type="button"
                  className={`p360-tab-btn ${activeTab === 'timeline' ? 'active' : ''}`}
                  onClick={() => setActiveTab('timeline')}
                >
                  <Clock3 size={15} /> Activity Feed
                  <span className="p360-tab-badge">{detail.timeline.length}</span>
                </button>

                {canChat && (
                  <button
                    type="button"
                    className={`p360-tab-btn ${activeTab === 'chat' ? 'active' : ''}`}
                    onClick={() => setActiveTab('chat')}
                  >
                    <MessageSquare size={15} /> PM Chat
                    {messages.length > 0 && <span className="p360-tab-badge">{messages.length}</span>}
                  </button>
                )}
              </nav>

              {/* 6. TAB CONTENTS */}

              {/* TAB 1: OVERVIEW & TEAM */}
              {activeTab === 'overview' && (
                <div className="p360-tab-content">
                  {detail.scope && (
                    <div className="p360-table-card">
                      <div className="p360-table-title">Project Scope & Specifications</div>
                      <div style={{ padding: '16px', fontSize: '0.86rem', color: '#334155', lineHeight: 1.6 }}>
                        {detail.scope}
                      </div>
                    </div>
                  )}

                  <div className="p360-table-card">
                    <div className="p360-table-title">Assigned Team Members & Roles</div>
                    <table className="p360-table">
                      <thead>
                        <tr>
                          <th>Role</th>
                          <th>Name</th>
                          <th>User ID</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td><strong>Project Manager</strong></td>
                          <td>{detail.project_manager_name || 'Not assigned'}</td>
                          <td>{detail.project_manager_id ?? '—'}</td>
                        </tr>
                        <tr>
                          <td><strong>Team Leader</strong></td>
                          <td>{detail.team_leader_name || 'Not assigned'}</td>
                          <td>{detail.team_leader_id ?? '—'}</td>
                        </tr>
                        {detail.selected_team?.map(member => (
                          <tr key={`${member.user_id}-${member.role}`}>
                            <td><span className="operations-status info">{member.role}</span></td>
                            <td>{member.name || `User ${member.user_id}`}</td>
                            <td>{member.user_id}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* TAB 2: INVOICES & PAYMENTS */}
              {activeTab === 'invoices' && isManagement && (
                <div className="p360-tab-content">
                  {/* Financial KPIs */}
                  <div className="p360-fin-kpis">
                    <div className="p360-fin-kpi">
                      <span className="p360-fin-kpi-label">Total Invoiced</span>
                      <span className="p360-fin-kpi-value blue">{formatMoney(totalInvoiced)}</span>
                    </div>
                    <div className="p360-fin-kpi">
                      <span className="p360-fin-kpi-label">Realized Payments</span>
                      <span className="p360-fin-kpi-value green">{formatMoney(totalPaid)}</span>
                    </div>
                    <div className="p360-fin-kpi">
                      <span className="p360-fin-kpi-label">Balance Pending</span>
                      <span className={`p360-fin-kpi-value ${detail.has_overdue_invoice ? 'red' : 'orange'}`}>
                        {formatMoney(totalBalance)}
                      </span>
                    </div>
                  </div>

                  {/* Invoices Table */}
                  <div className="p360-table-card">
                    <div className="p360-table-title">
                      <span>Project Invoices</span>
                      <span className="p360-sidebar-count">{detail.invoices.length} invoices</span>
                    </div>
                    <table className="p360-table">
                      <thead>
                        <tr>
                          <th>Invoice #</th>
                          <th>Date</th>
                          <th>Due Date</th>
                          <th>Status</th>
                          <th>Total Amount</th>
                          <th>Paid</th>
                          <th>Balance</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.invoices.map(inv => (
                          <tr key={inv.id}>
                            <td><strong>{inv.invoice_number}</strong></td>
                            <td>{formatDate(inv.invoice_date)}</td>
                            <td>{formatDate(inv.due_date)}</td>
                            <td>
                              <span className={`p360-status-pill ${lifecycleStatusTone(inv.status)}`} style={{ padding: '2px 8px', fontSize: '0.68rem' }}>
                                {lifecycleStatusLabel(inv.status)}
                              </span>
                            </td>
                            <td>{formatMoney(inv.total_amount, inv.currency)}</td>
                            <td><strong style={{ color: '#16a34a' }}>{formatMoney(inv.paid_amount, inv.currency)}</strong></td>
                            <td><strong style={{ color: inv.balance > 0 ? '#dc2626' : 'inherit' }}>{formatMoney(inv.balance, inv.currency)}</strong></td>
                          </tr>
                        ))}
                        {!detail.invoices.length && (
                          <tr><td colSpan={7} style={{ textAlign: 'center', padding: '24px', color: '#94a3b8' }}>No invoices raised yet.</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>

                  {/* Payments Breakdown */}
                  {detail.invoices.some(inv => inv.payments && inv.payments.length > 0) && (
                    <div className="p360-table-card">
                      <div className="p360-table-title">Realized Payments Ledger</div>
                      <table className="p360-table">
                        <thead>
                          <tr>
                            <th>Payment Reference</th>
                            <th>Date</th>
                            <th>Amount</th>
                            <th>Mode</th>
                            <th>INR Equivalent</th>
                            <th>Comments</th>
                          </tr>
                        </thead>
                        <tbody>
                          {detail.invoices.flatMap(inv => inv.payments || []).map(payment => (
                            <tr key={payment.id}>
                              <td><strong>{payment.payment_reference}</strong></td>
                              <td>{formatDate(payment.payment_date)}</td>
                              <td>{formatMoney(payment.amount, payment.payment_currency)}</td>
                              <td>{payment.payment_mode || 'Bank Transfer'}</td>
                              <td>{payment.inr_equivalent ? `₹${payment.inr_equivalent.toLocaleString('en-IN')}` : '—'}</td>
                              <td>{payment.comments || '—'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {/* TAB 3: DELIVERIES & REWORK */}
              {activeTab === 'deliveries' && (
                <div className="p360-tab-content">
                  {/* Delivery Versions */}
                  <div className="p360-table-card">
                    <div className="p360-table-title">
                      <span>Delivery Versions</span>
                      <span className="p360-sidebar-count">{detail.delivery_versions.length} versions</span>
                    </div>
                    <table className="p360-table">
                      <thead>
                        <tr>
                          <th>Version</th>
                          <th>Reference</th>
                          <th>Delivered Date</th>
                          <th>Notes</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.delivery_versions.map(ver => (
                          <tr key={ver.id}>
                            <td><strong>Version {ver.version_number}</strong></td>
                            <td><code>{ver.delivery_reference}</code></td>
                            <td>{formatDateTime(ver.delivered_at)}</td>
                            <td>{ver.notes || '—'}</td>
                          </tr>
                        ))}
                        {!detail.delivery_versions.length && (
                          <tr><td colSpan={4} style={{ textAlign: 'center', padding: '24px', color: '#94a3b8' }}>No delivery versions logged yet.</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>

                  {/* Rework Cycles */}
                  <div className="p360-table-card">
                    <div className="p360-table-title">
                      <span>Rework & Correction Cycles</span>
                      <span className="p360-sidebar-count">{detail.rework_cycles.length} cycles</span>
                    </div>
                    <table className="p360-table">
                      <thead>
                        <tr>
                          <th>Cycle #</th>
                          <th>Type</th>
                          <th>Status</th>
                          <th>Opened At</th>
                          <th>Scope Description</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.rework_cycles.map(cycle => (
                          <tr key={cycle.id}>
                            <td><strong>Cycle {cycle.cycle_number}</strong></td>
                            <td>
                              <span className={`p360-status-pill ${cycle.cycle_type === 'APPROVED_CHANGE_REQUEST' ? 'warning' : 'info'}`} style={{ padding: '2px 8px', fontSize: '0.68rem' }}>
                                {reworkCycleTypeLabel(cycle.cycle_type)}
                              </span>
                            </td>
                            <td>
                              <span className={`p360-status-pill ${lifecycleStatusTone(cycle.status)}`} style={{ padding: '2px 8px', fontSize: '0.68rem' }}>
                                {lifecycleStatusLabel(cycle.status)}
                              </span>
                            </td>
                            <td>{formatDate(cycle.opened_at)}</td>
                            <td>{cycle.correction_scope}</td>
                          </tr>
                        ))}
                        {!detail.rework_cycles.length && (
                          <tr><td colSpan={5} style={{ textAlign: 'center', padding: '24px', color: '#94a3b8' }}>Zero rework cycles recorded. Excellent quality performance!</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* TAB 4: DECISIONS & SCOPE CHANGES */}
              {activeTab === 'actions' && isManagement && (
                <div className="p360-tab-content">
                  {pendingChangeRequests.length > 0 && (
                    <div className="p360-table-card">
                      <div className="p360-table-title">Pending Scope Change Requests</div>
                      <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
                        {pendingChangeRequests.map(row => {
                          const form = decisionForm[row.id] || { decision: 'approved' as const, comments: '' }
                          return (
                            <div key={row.id} className="operations-daily-card">
                              <div className="operations-daily-heading">
                                <div>
                                  <h3>{row.request_code}</h3>
                                  <p>{row.description}</p>
                                  {row.commercial_impact != null && (
                                    <small style={{ color: '#2563eb', fontWeight: 700 }}>
                                      Commercial Impact: {formatMoney(row.commercial_impact, row.currency)}
                                    </small>
                                  )}
                                </div>
                                <span className="p360-status-pill warning">Pending Approval</span>
                              </div>
                              <div className="operations-form-grid">
                                <label className="operations-field">
                                  <span>Decision</span>
                                  <select
                                    value={form.decision}
                                    onChange={e => setDecisionForm({ ...decisionForm, [row.id]: { ...form, decision: e.target.value as 'approved' | 'rejected' } })}
                                  >
                                    <option value="approved">Approve Additional Scope</option>
                                    <option value="rejected">Reject Additional Scope</option>
                                  </select>
                                </label>
                                <label className="operations-field operations-span-2">
                                  <span>Management Comments</span>
                                  <textarea
                                    value={form.comments}
                                    onChange={e => setDecisionForm({ ...decisionForm, [row.id]: { ...form, comments: e.target.value } })}
                                    rows={2}
                                    placeholder="Add commercial or operational notes for the decision..."
                                  />
                                </label>
                              </div>
                              <div className="operations-actions">
                                <button
                                  className="operations-button"
                                  disabled={busy === `decide-${row.id}`}
                                  onClick={() => void run(`decide-${row.id}`, () => decide(row), 'Change request decision recorded')}
                                >
                                  Record Decision
                                </button>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )}

                  {/* All change requests historical */}
                  <div className="p360-table-card">
                    <div className="p360-table-title">All Change Requests History</div>
                    <table className="p360-table">
                      <thead>
                        <tr>
                          <th>Code</th>
                          <th>Status</th>
                          <th>Description</th>
                          <th>Commercial Impact</th>
                          <th>Decision Comments</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.change_requests.map(cr => (
                          <tr key={cr.id}>
                            <td><strong>{cr.request_code}</strong></td>
                            <td>
                              <span className={`p360-status-pill ${cr.status === 'approved' ? 'success' : cr.status === 'rejected' ? 'danger' : 'warning'}`} style={{ padding: '2px 8px', fontSize: '0.68rem' }}>
                                {cr.status}
                              </span>
                            </td>
                            <td>{cr.description}</td>
                            <td>{cr.commercial_impact != null ? formatMoney(cr.commercial_impact, cr.currency) : '—'}</td>
                            <td>{cr.decision_comments || '—'}</td>
                          </tr>
                        ))}
                        {!detail.change_requests.length && (
                          <tr><td colSpan={5} style={{ textAlign: 'center', padding: '24px', color: '#94a3b8' }}>No scope change requests for this project.</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* TAB 5: ACTIVITY FEED TIMELINE */}
              {activeTab === 'timeline' && (
                <div className="p360-tab-content">
                  <div className="p360-table-card">
                    <div className="p360-table-title">Chronological Project Activity & Audit Feed</div>
                    <div style={{ padding: '18px 20px' }}>
                      <div className="p360-timeline-feed">
                        {detail.timeline.slice().reverse().slice(0, 40).map(item => {
                          const isGreen = item.status && ['completed', 'approved', 'closed', 'client_accepted'].includes(item.status.toLowerCase())
                          const isRed = item.status && ['rejected', 'danger', 'overdue'].includes(item.status.toLowerCase())
                          return (
                            <div key={item.id} className="p360-timeline-item">
                              <span className={`p360-timeline-dot ${isGreen ? 'green' : isRed ? 'red' : ''}`} />
                              <div className="p360-timeline-header">
                                <span className="p360-timeline-title">{item.title}</span>
                                <span className="p360-timeline-time">{formatDateTime(item.occurred_at)}</span>
                              </div>
                              {item.details && <p className="p360-timeline-desc">{item.details}</p>}
                              <div className="p360-timeline-meta">
                                <span className="p360-timeline-actor">👤 {item.actor_name || 'System'}</span>
                                {item.status && (
                                  <span className={`p360-status-pill ${lifecycleStatusTone(item.status)}`} style={{ padding: '1px 6px', fontSize: '0.64rem' }}>
                                    {lifecycleStatusLabel(item.status)}
                                  </span>
                                )}
                              </div>
                            </div>
                          )
                        })}
                        {!detail.timeline.length && (
                          <div style={{ padding: '24px', textAlign: 'center', color: '#94a3b8' }}>No activity records logged yet.</div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 6: EXECUTIVE PM CHAT */}
              {activeTab === 'chat' && canChat && (
                <div className="p360-tab-content">
                  <div className="p360-chat-card">
                    <div className="p360-table-title">
                      <span>Executive ↔ Project Manager Direct Channel</span>
                      <span className="p360-sidebar-count">{messages.length} messages</span>
                    </div>

                    <div className="p360-chat-messages">
                      {messages.map(msg => {
                        const isMine = msg.sender_user_id === user?.id
                        return (
                          <div key={msg.id} className={`p360-chat-bubble ${isMine ? 'mine' : 'theirs'}`}>
                            <span className="p360-chat-bubble-sender">{msg.sender_name || 'Colleague'}</span>
                            <span className="p360-chat-bubble-text">{msg.message}</span>
                            <span className="p360-chat-bubble-time">{formatDateTime(msg.created_at)}</span>
                          </div>
                        )
                      })}
                      {!messages.length && (
                        <div style={{ padding: '32px', textAlign: 'center', color: '#94a3b8' }}>
                          No messages exchanged yet. Send a direct instruction or question to the Project Manager below.
                        </div>
                      )}
                    </div>

                    <div className="p360-chat-input-bar">
                      <input
                        className="p360-chat-input"
                        placeholder="Type a message or instruction for the Project Manager..."
                        value={chatText}
                        onChange={e => setChatText(e.target.value)}
                        onKeyDown={e => {
                          if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault()
                            void sendChat()
                          }
                        }}
                      />
                      <button
                        className="p360-chat-send-btn"
                        disabled={!chatText.trim()}
                        onClick={() => void sendChat()}
                      >
                        <Send size={15} /> Send
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </main>
      </div>
    </div>
  )
}
