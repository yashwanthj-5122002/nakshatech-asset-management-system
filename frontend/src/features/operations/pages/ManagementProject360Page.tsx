import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  FolderKanban,
  IndianRupee,
  MessageSquare,
  RefreshCcw,
  Search,
  Send,
  ShieldCheck,
  UserCheck,
  Users,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { PaginationBar } from '../../../components/PaginationBar'
import { StatCard } from '../../../components/StatCard'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch } from '../../../lib/api'
import { useClientPagination } from '../../../hooks/useClientPagination'
import {
  ChangeRequestRow,
  LifecycleDashboard,
  Project360,
  ProjectMessageRow,
  formatDateTime,
  formatMoney,
  lifecycleStatusLabel,
  lifecycleStatusTone,
  reworkCycleTypeLabel,
} from '../lifecycle-types'
import '../operations.css'

const CHAT_ROLES = new Set(['management', 'admin', 'ortho'])

type StatusFilterTab = 'all' | 'active' | 'awaiting_feedback' | 'rework' | 'closed'

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
  const [statusFilter, setStatusFilter] = useState<StatusFilterTab>('all')
  const [chatText, setChatText] = useState('')
  const detailScrollRef = useRef<HTMLDivElement | null>(null)

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
        if (!selectedId && data.projects.length) navigate(`${basePath}/${data.projects[0].id}`, { replace: true })
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

  useEffect(loadDashboard, [])
  useEffect(() => { if (selectedId) loadDetail(selectedId) }, [selectedId])

  const filteredProjects = useMemo(() => {
    const rows = dashboard?.projects ?? []
    const term = search.trim().toLowerCase()
    return rows.filter(row => {
      const matchesSearch =
        !term ||
        row.project_code.toLowerCase().includes(term) ||
        row.project_name.toLowerCase().includes(term) ||
        (row.client_name || '').toLowerCase().includes(term) ||
        (row.client_id || '').toLowerCase().includes(term)

      if (!matchesSearch) return false

      if (statusFilter === 'active') {
        return row.workflow_status === 'in_progress' || row.workflow_status === 'operational_complete'
      }
      if (statusFilter === 'awaiting_feedback') {
        return row.workflow_status === 'awaiting_feedback'
      }
      if (statusFilter === 'rework') {
        return row.workflow_status === 'rework'
      }
      if (statusFilter === 'closed') {
        return row.workflow_status === 'closed' || row.workflow_status === 'ready_for_billing'
      }
      return true
    })
  }, [dashboard, search, statusFilter])

  const {
    page: registerPage,
    setPage: setRegisterPage,
    pageRows: registerRows,
    pageCount: registerPageCount,
    total: registerTotal,
    rangeStart: registerRangeStart,
    rangeEnd: registerRangeEnd,
  } = useClientPagination(filteredProjects, 25)

  useEffect(() => {
    setRegisterPage(1)
  }, [search, statusFilter, setRegisterPage])

  useEffect(() => {
    detailScrollRef.current?.scrollTo({ top: 0 })
  }, [selectedId])

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

  return (
    <div className="operations-page">
      <DashboardHeader
        eyebrow={isManagement ? 'MANAGEMENT · EXECUTIVE PROJECT 360' : 'OPERATIONS · PROJECT 360 VIEW'}
        title="Project 360 Command Center"
        description={
          isManagement
            ? 'Unified executive lifecycle view combining operational stages, client feedback loops, deemed acceptance governance, and commercial balances.'
            : 'Operational Project 360: delivery versions, client feedback status, and direct Management communication.'
        }
        actions={
          <button className="operations-button secondary" onClick={loadDashboard}>
            <RefreshCcw size={15} /> Refresh Data
          </button>
        }
      />

      {error && <div className="operations-alert error">{error}</div>}
      {notice && <div className="operations-alert success">{notice}</div>}

      {dashboard && (
        <section className="p360-kpi-quad">
          <StatCard icon={FolderKanban} label="Total Projects" value={dashboard.summary.total_projects} tone="navy" />
          <StatCard icon={Clock} label="Awaiting Client Feedback" value={dashboard.summary.awaiting_feedback} tone="orange" />
          <StatCard icon={AlertTriangle} label="Critical / Overdue" value={dashboard.summary.overdue} tone="red" />
          <StatCard icon={CheckCircle2} label="Closed / Billing Ready" value={dashboard.summary.closed + dashboard.summary.ready_for_billing} tone="green" />
        </section>
      )}

      <div className="operations-workflow-console-grid p360-console">
        {/* Project Register Navigation Panel */}
        <section className="operations-panel">
          <header>
            <div>
              <span className="operations-kicker">PORTFOLIO REGISTER</span>
              <h2>Lifecycle Projects</h2>
            </div>
            <span className="count-chip">{filteredProjects.length}</span>
          </header>

          <div className="p360-register-search-wrap">
            <Search size={15} className="p360-register-search-icon" />
            <input
              placeholder="Search code, title, or client…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>

          <div className="p360-filter-chips">
            <button
              type="button"
              className={`p360-filter-chip ${statusFilter === 'all' ? 'active' : ''}`}
              onClick={() => setStatusFilter('all')}
            >
              All ({dashboard?.projects.length ?? 0})
            </button>
            <button
              type="button"
              className={`p360-filter-chip ${statusFilter === 'active' ? 'active' : ''}`}
              onClick={() => setStatusFilter('active')}
            >
              Active
            </button>
            <button
              type="button"
              className={`p360-filter-chip ${statusFilter === 'awaiting_feedback' ? 'active' : ''}`}
              onClick={() => setStatusFilter('awaiting_feedback')}
            >
              Feedback
            </button>
            <button
              type="button"
              className={`p360-filter-chip ${statusFilter === 'rework' ? 'active' : ''}`}
              onClick={() => setStatusFilter('rework')}
            >
              Rework
            </button>
            <button
              type="button"
              className={`p360-filter-chip ${statusFilter === 'closed' ? 'active' : ''}`}
              onClick={() => setStatusFilter('closed')}
            >
              Closed
            </button>
          </div>

          {loading && <div className="operations-empty">Loading project registry…</div>}

          <div className="operations-workflow-tree p360-register-list">
            {registerRows.map(row => {
              const isSelected = row.id === selectedId
              const initials = row.project_code.slice(0, 3).toUpperCase()
              return (
                <div
                  key={row.id}
                  className={`p360-project-card ${isSelected ? 'active' : ''}`}
                  onClick={() => navigate(`${basePath}/${row.id}`)}
                  role="button"
                  tabIndex={0}
                >
                  <div className="p360-code-avatar">{initials}</div>
                  <div className="p360-project-info">
                    <strong>{row.project_code}</strong>
                    <small>{row.project_name || row.client_name || 'Project'}</small>
                  </div>
                  <span className={`operations-status ${lifecycleStatusTone(row.workflow_status)}`}>
                    {lifecycleStatusLabel(row.workflow_status)}
                  </span>
                </div>
              )
            })}
            {!loading && !filteredProjects.length && (
              <div className="operations-empty">No projects match the selected filter.</div>
            )}
          </div>
          <PaginationBar
            page={registerPage}
            pageCount={registerPageCount}
            total={registerTotal}
            rangeStart={registerRangeStart}
            rangeEnd={registerRangeEnd}
            onPageChange={setRegisterPage}
            label="Projects"
          />
        </section>

        {/* Project 360 Detail Command Center */}
        <section className="operations-panel">
          {!detail && <div className="operations-empty">Select a project from the register to view full 360 telemetry.</div>}
          {detail && (
            <div className="p360-detail-scroll" ref={detailScrollRef}>
              <>
              {/* Project Hero Header */}
              <div className="p360-hero-header">
                <div>
                  <span className="operations-kicker">
                    {detail.project_code} · {detail.client_name || detail.client_id || 'Client identity restricted'}
                  </span>
                  <h2 style={{ fontSize: '1.35rem', fontWeight: 800, margin: '4px 0 8px 0', color: '#0f172a' }}>
                    {detail.project_name}
                  </h2>
                  <div className="p360-progress-container" style={{ maxWidth: '320px' }}>
                    <div className="p360-progress-label-row">
                      <span>Milestone Completion</span>
                      <span>{detail.progress_percent}%</span>
                    </div>
                    <div className="p360-progress-bar-outer">
                      <div className="p360-progress-bar-inner" style={{ width: `${Math.min(100, detail.progress_percent)}%` }} />
                    </div>
                  </div>
                </div>
                <span className={`operations-status ${lifecycleStatusTone(detail.workflow_status)}`} style={{ fontSize: '0.82rem', padding: '6px 14px' }}>
                  {lifecycleStatusLabel(detail.workflow_status)}
                </span>
              </div>

              {/* Executive Metrics Quad */}
              <div className="p360-metrics-grid">
                <div className="p360-metric-box">
                  <span><UserCheck size={12} style={{ display: 'inline', marginRight: 4 }} />Project Manager</span>
                  <strong style={{ fontSize: '0.95rem' }}>{detail.project_manager_name || 'Unassigned'}</strong>
                </div>
                <div className="p360-metric-box">
                  <span><Users size={12} style={{ display: 'inline', marginRight: 4 }} />Team Lead</span>
                  <strong style={{ fontSize: '0.95rem' }}>{detail.team_leader_name || 'Unassigned'}</strong>
                </div>
                <div className="p360-metric-box">
                  <span>Rework Iterations</span>
                  <strong>{detail.rework_count} Cycles</strong>
                </div>
                <div className={`p360-metric-box ${detail.has_overdue_invoice ? 'is-overdue' : ''}`}>
                  <span><IndianRupee size={12} style={{ display: 'inline', marginRight: 2 }} />Outstanding Balance</span>
                  <strong>{isManagement ? formatMoney(detail.invoice_balance) : 'Restricted'}</strong>
                </div>
              </div>

              {/* Actionable Governance: Deemed Acceptance */}
              {isManagement && closureRecommendedRequest && (
                <div className="p360-action-alert-card warning">
                  <div className="p360-action-header">
                    <ShieldCheck size={20} color="#d97706" />
                    <strong>Authorization Required: Deemed Acceptance ({closureRecommendedRequest.request_code})</strong>
                  </div>
                  <div className="p360-action-body">
                    Business Development has recommended no-feedback automatic closure. Under commercial policy, Management or Admin authority is required to approve deemed acceptance and transition this project to <em>Ready For Billing</em>.
                  </div>
                  <label className="operations-field" style={{ marginBottom: 12 }}>
                    <span style={{ fontWeight: 700, fontSize: '0.78rem' }}>Authorization Basis (Clause / Justification)</span>
                    <textarea
                      placeholder="Enter contractual justification or client waiver basis…"
                      value={deemedBasis}
                      onChange={e => setDeemedBasis(e.target.value)}
                      rows={2}
                    />
                  </label>
                  <div className="operations-actions">
                    <button
                      className="operations-button warning"
                      disabled={busy === 'deemed' || deemedBasis.trim().length < 5}
                      onClick={() => void run('deemed', () => authorizeDeemedAcceptance(closureRecommendedRequest.id), 'Deemed acceptance authorized; project marked Ready For Billing')}
                    >
                      Authorize Deemed Acceptance
                    </button>
                  </div>
                </div>
              )}

              {/* Actionable Governance: Pending Change Requests */}
              {isManagement && pendingChangeRequests.length > 0 && (
                <div style={{ marginBottom: '18px' }}>
                  <h3 style={{ fontSize: '0.95rem', fontWeight: 800, marginBottom: 8, color: '#0f172a' }}>
                    Pending Scope Change Requests
                  </h3>
                  {pendingChangeRequests.map(row => {
                    const form = decisionForm[row.id] || { decision: 'approved' as const, comments: '' }
                    return (
                      <div key={row.id} className="p360-action-alert-card" style={{ background: '#f8fafc', borderColor: '#cbd5e1' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                          <strong style={{ fontSize: '0.88rem', color: '#0f172a' }}>{row.request_code}</strong>
                          {row.commercial_impact != null && (
                            <span style={{ fontSize: '0.82rem', fontWeight: 800, color: '#0f766e' }}>
                              Impact: {formatMoney(row.commercial_impact, row.currency)}
                            </span>
                          )}
                        </div>
                        <p style={{ margin: '0 0 10px 0', fontSize: '0.82rem', color: '#475569' }}>{row.description}</p>
                        <div className="operations-form-grid" style={{ marginBottom: 10 }}>
                          <label className="operations-field">
                            <span>Decision</span>
                            <select
                              value={form.decision}
                              onChange={e => setDecisionForm({
                                ...decisionForm,
                                [row.id]: { ...form, decision: e.target.value as 'approved' | 'rejected' },
                              })}
                            >
                              <option value="approved">Approve Additional Scope</option>
                              <option value="rejected">Reject Additional Scope</option>
                            </select>
                          </label>
                          <label className="operations-field operations-span-2">
                            <span>Comments</span>
                            <input
                              placeholder="Decision rationale…"
                              value={form.comments}
                              onChange={e => setDecisionForm({
                                ...decisionForm,
                                [row.id]: { ...form, comments: e.target.value },
                              })}
                            />
                          </label>
                        </div>
                        <button
                          className="operations-button"
                          disabled={busy === `decide-${row.id}`}
                          onClick={() => void run(`decide-${row.id}`, () => decide(row), 'Change request decision recorded')}
                        >
                          Record Decision
                        </button>
                      </div>
                    )
                  })}
                </div>
              )}

              {/* Milestone Timeline Stream */}
              <div style={{ marginBottom: '22px' }}>
                <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <div>
                    <span className="operations-kicker">CHRONOLOGY</span>
                    <h3 style={{ fontSize: '1.05rem', fontWeight: 800, margin: 0 }}>Lifecycle Milestones</h3>
                  </div>
                  <span style={{ fontSize: '0.72rem', color: '#64748b' }}>Latest 25 Events</span>
                </header>

                <div className="p360-timeline-stream">
                  {detail.timeline.slice().reverse().slice(0, 25).map(row => (
                    <div key={row.id} className="p360-timeline-item">
                      <div className="p360-timeline-dot" />
                      <div className="p360-timeline-content">
                        <strong>{row.title}</strong>
                        {row.details && <small>{row.details}</small>}
                      </div>
                      <div className="p360-timeline-meta">
                        <div>{row.actor_name || 'System'}</div>
                        <div style={{ opacity: 0.75 }}>{formatDateTime(row.occurred_at)}</div>
                      </div>
                    </div>
                  ))}
                  {!detail.timeline.length && (
                    <div className="operations-empty" style={{ padding: '16px' }}>No recorded lifecycle events.</div>
                  )}
                </div>
              </div>

              {/* Commercial Invoices Table */}
              {isManagement && detail.invoices.length > 0 && (
                <div style={{ marginBottom: '22px' }}>
                  <header style={{ marginBottom: 10 }}>
                    <span className="operations-kicker">COMMERCIAL STATUS</span>
                    <h3 style={{ fontSize: '1.05rem', fontWeight: 800, margin: 0 }}>Invoices & Payment Realization</h3>
                  </header>
                  <div className="operations-table-wrap">
                    <table className="operations-table">
                      <thead>
                        <tr>
                          <th>Invoice Ref</th>
                          <th>Status</th>
                          <th>Total Amount</th>
                          <th>Paid Realized</th>
                          <th>Outstanding</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.invoices.map(row => (
                          <tr key={row.id}>
                            <td><strong>{row.invoice_number}</strong></td>
                            <td>
                              <span className={`operations-status ${lifecycleStatusTone(row.status)}`}>
                                {lifecycleStatusLabel(row.status)}
                              </span>
                            </td>
                            <td>{formatMoney(row.total_amount, row.currency)}</td>
                            <td style={{ color: '#166534', fontWeight: 700 }}>{formatMoney(row.paid_amount, row.currency)}</td>
                            <td style={{ color: row.balance > 0 ? '#b91c1c' : '#475569', fontWeight: 700 }}>
                              {formatMoney(row.balance, row.currency)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Rework Cycles Table */}
              {detail.rework_cycles.length > 0 && (
                <div style={{ marginBottom: '22px' }}>
                  <header style={{ marginBottom: 10 }}>
                    <span className="operations-kicker">QUALITY & CORRECTIONS</span>
                    <h3 style={{ fontSize: '1.05rem', fontWeight: 800, margin: 0 }}>Rework & Correction Cycles</h3>
                  </header>
                  <div className="operations-table-wrap">
                    <table className="operations-table">
                      <thead>
                        <tr>
                          <th>Cycle</th>
                          <th>Classification</th>
                          <th>Status</th>
                          <th>Scope of Work</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.rework_cycles.map(row => (
                          <tr key={row.id}>
                            <td><strong>Cycle {row.cycle_number}</strong></td>
                            <td>
                              <span className={`operations-status ${row.cycle_type === 'APPROVED_CHANGE_REQUEST' ? 'warning' : 'neutral'}`}>
                                {reworkCycleTypeLabel(row.cycle_type)}
                              </span>
                            </td>
                            <td>
                              <span className={`operations-status ${lifecycleStatusTone(row.status)}`}>
                                {lifecycleStatusLabel(row.status)}
                              </span>
                            </td>
                            <td>{row.correction_scope}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Management ↔ PM Dedicated Chat Thread */}
              {canChat && (
                <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '16px', padding: '16px' }}>
                  <header style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                    <MessageSquare size={18} color="#0284c7" />
                    <h3 style={{ fontSize: '0.95rem', fontWeight: 800, margin: 0, color: '#0f172a' }}>
                      Management ↔ Project Operations Chat
                    </h3>
                  </header>

                  <div className="p360-chat-thread">
                    {messages.map(row => {
                      const isMe = row.sender_user_id === user?.id
                      return (
                        <div key={row.id} className={`p360-chat-bubble ${isMe ? 'mine' : 'theirs'}`}>
                          <strong>{row.sender_name || 'User'}:</strong> {row.message}
                          <small>{formatDateTime(row.created_at)}</small>
                        </div>
                      )
                    })}
                    {!messages.length && (
                      <div className="operations-empty-compact">No conversation history on this project yet.</div>
                    )}
                  </div>

                  <div className="p360-chat-form-row">
                    <input
                      placeholder="Send coordination note to Project Manager…"
                      value={chatText}
                      onChange={e => setChatText(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === 'Enter') void sendChat()
                      }}
                    />
                    <button
                      className="operations-button"
                      disabled={!chatText.trim()}
                      onClick={() => void sendChat()}
                    >
                      <Send size={15} /> Send
                    </button>
                  </div>
                </div>
              )}
              </>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
