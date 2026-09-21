import { AlertTriangle, CheckCircle2, MessageSquare, RefreshCcw, Send, ShieldCheck } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { StatCard } from '../../../components/StatCard'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch } from '../../../lib/api'
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
        if (!selectedId && data.projects.length) navigate(`${basePath}/${data.projects[0].id}`, { replace: true })
      })
      .catch(err => setError(err instanceof Error ? err.message : 'Unable to load the lifecycle dashboard'))
      .finally(() => setLoading(false))
  }

  function loadDetail(id: number) {
    void apiFetch<Project360>(`/operations/lifecycle/projects/${id}`).then(setDetail).catch(err => setError(err instanceof Error ? err.message : 'Unable to load project detail'))
    if (canChat) {
      void apiFetch<ProjectMessageRow[]>(`/operations/lifecycle/projects/${id}/messages`).then(setMessages).catch(() => setMessages([]))
    } else {
      setMessages([])
    }
  }

  useEffect(loadDashboard, [])
  useEffect(() => { if (selectedId) loadDetail(selectedId) }, [selectedId])

  const projects = useMemo(() => {
    const rows = dashboard?.projects ?? []
    const term = search.trim().toLowerCase()
    if (!term) return rows
    return rows.filter(row => row.project_code.toLowerCase().includes(term) || (row.client_name || '').toLowerCase().includes(term) || (row.client_id || '').toLowerCase().includes(term))
  }, [dashboard, search])

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
      body: JSON.stringify({ decision: form.decision, comments: form.comments.trim() || 'Decision recorded', commercial_impact: row.commercial_impact, currency: row.currency }),
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

  return <div className="operations-page">
    <DashboardHeader
      eyebrow={isManagement ? 'MANAGEMENT · FULL PROJECT 360' : 'PROJECT MANAGER · OPERATIONAL PROJECT VIEW'}
      title="Project 360"
      description={isManagement ? 'Full lifecycle history including client identity, commercial impact, invoices and payments.' : 'Operational Project 360: stage, feedback/rework status, delivery versions and Management chat. Client identity and commercial data are restricted.'}
      actions={<button className="operations-button secondary" onClick={loadDashboard}><RefreshCcw size={16}/> Refresh</button>}
    />
    {error && <div className="operations-alert error">{error}</div>}
    {notice && <div className="operations-alert success">{notice}</div>}

    {dashboard && <section className="operations-stats-grid">
      <StatCard icon={CheckCircle2} label="Total Projects" value={dashboard.summary.total_projects} tone="navy"/>
      <StatCard icon={AlertTriangle} label="Awaiting Feedback" value={dashboard.summary.awaiting_feedback} tone="orange"/>
      <StatCard icon={AlertTriangle} label="Overdue" value={dashboard.summary.overdue} tone="red"/>
      <StatCard icon={CheckCircle2} label="Closed" value={dashboard.summary.closed} tone="green"/>
    </section>}

    <div className="operations-workflow-console-grid">
      <section className="operations-panel">
        <header><div><span className="operations-kicker">PROJECT REGISTER</span><h2>All Projects</h2></div></header>
        <div className="operations-field operations-span-2"><input placeholder="Search Project ID or Client" value={search} onChange={e => setSearch(e.target.value)} /></div>
        {loading && <div className="operations-empty">Loading...</div>}
        <div className="operations-workflow-tree">
          {projects.map(row => <button key={row.id} type="button" className={row.id === selectedId ? 'active' : ''} onClick={() => navigate(`${basePath}/${row.id}`)}>
            <span className="operations-workflow-step-number">{row.project_code.slice(-2)}</span>
            <span><strong>{row.project_code}</strong><small>{row.client_name || row.client_id || 'Client not recorded'}</small><small className={`operations-status ${lifecycleStatusTone(row.workflow_status)}`}>{lifecycleStatusLabel(row.workflow_status)}</small></span>
          </button>)}
          {!loading && !projects.length && <div className="operations-empty">No lifecycle projects yet.</div>}
        </div>
      </section>

      <section className="operations-panel">
        {!detail && <div className="operations-empty">Select a project.</div>}
        {detail && <>
          <header><div><span className="operations-kicker">{detail.project_code} · {detail.client_name || detail.client_id || 'Client identity restricted'}</span><h2>{detail.project_name}</h2></div><span className={`operations-status ${lifecycleStatusTone(detail.workflow_status)}`}>{lifecycleStatusLabel(detail.workflow_status)}</span></header>

          <div className="operations-detail-grid">
            <div><span>Project Manager</span><strong>{detail.project_manager_name || 'Not assigned'}</strong></div>
            <div><span>Team Leader</span><strong>{detail.team_leader_name || 'Not assigned'}</strong></div>
            <div><span>Progress</span><strong>{detail.progress_percent}%</strong></div>
            <div><span>Rework Cycles</span><strong>{detail.rework_count}</strong></div>
            {isManagement && <div><span>Invoice Balance</span><strong>{formatMoney(detail.invoice_balance)}</strong></div>}
          </div>

          {isManagement && closureRecommendedRequest && <div className="operations-daily-form operations-span-2">
            <div className="operations-note operations-span-2"><ShieldCheck size={15}/> BD recommended no-feedback closure for {closureRecommendedRequest.request_code}. Only Management/Admin may authorize deemed acceptance.</div>
            <label className="operations-field operations-span-2"><span>Authorization basis (contractual clause / commercial justification)</span><textarea value={deemedBasis} onChange={e => setDeemedBasis(e.target.value)} rows={2}/></label>
            <div className="operations-actions"><button className="operations-button warning" disabled={busy === 'deemed' || deemedBasis.trim().length < 5} onClick={() => void run('deemed', () => authorizeDeemedAcceptance(closureRecommendedRequest.id), 'Deemed acceptance authorized; project is Ready For Billing')}>Authorize Deemed Acceptance</button></div>
          </div>}

          {isManagement && pendingChangeRequests.map(row => {
            const form = decisionForm[row.id] || { decision: 'approved' as const, comments: '' }
            return <div key={row.id} className="operations-daily-card">
              <div><strong>{row.request_code} pending decision</strong><p>{row.description}</p>{row.commercial_impact != null && <small>Commercial impact: {formatMoney(row.commercial_impact, row.currency)}</small>}</div>
              <div className="operations-form-grid">
                <label className="operations-field"><span>Decision</span><select value={form.decision} onChange={e => setDecisionForm({ ...decisionForm, [row.id]: { ...form, decision: e.target.value as 'approved' | 'rejected' } })}>
                  <option value="approved">Approve additional scope</option>
                  <option value="rejected">Reject additional scope</option>
                </select></label>
                <label className="operations-field operations-span-2"><span>Comments</span><textarea value={form.comments} onChange={e => setDecisionForm({ ...decisionForm, [row.id]: { ...form, comments: e.target.value } })} rows={2}/></label>
              </div>
              <div className="operations-actions"><button className="operations-button" disabled={busy === `decide-${row.id}`} onClick={() => void run(`decide-${row.id}`, () => decide(row), 'Change request decision recorded')}>Record Decision</button></div>
            </div>
          })}

          <div className="operations-table-wrap">
            <table className="operations-table">
              <thead><tr><th>Timeline</th><th>Status</th><th>Actor</th><th>When</th></tr></thead>
              <tbody>{detail.timeline.slice().reverse().slice(0, 25).map(row => <tr key={row.id}><td><strong>{row.title}</strong>{row.details && <small>{row.details}</small>}</td><td>{row.status ? lifecycleStatusLabel(row.status) : '—'}</td><td>{row.actor_name || 'System'}</td><td>{formatDateTime(row.occurred_at)}</td></tr>)}
              {!detail.timeline.length && <tr><td colSpan={4}>No lifecycle activity yet.</td></tr>}</tbody>
            </table>
          </div>

          {detail.rework_cycles.length > 0 && <div className="operations-table-wrap">
            <table className="operations-table">
              <thead><tr><th>Rework Cycle</th><th>Type</th><th>Status</th><th>Scope</th></tr></thead>
              <tbody>{detail.rework_cycles.map(row => <tr key={row.id}><td>Cycle {row.cycle_number}</td><td><span className={`operations-status ${row.cycle_type === 'APPROVED_CHANGE_REQUEST' ? 'warning' : ''}`}>{reworkCycleTypeLabel(row.cycle_type)}</span></td><td><span className={`operations-status ${lifecycleStatusTone(row.status)}`}>{lifecycleStatusLabel(row.status)}</span></td><td>{row.correction_scope}</td></tr>)}</tbody>
            </table>
          </div>}

          {isManagement && detail.invoices.length > 0 && <div className="operations-table-wrap">
            <table className="operations-table">
              <thead><tr><th>Invoice</th><th>Status</th><th>Amount</th><th>Paid</th><th>Balance</th></tr></thead>
              <tbody>{detail.invoices.map(row => <tr key={row.id}><td>{row.invoice_number}</td><td><span className={`operations-status ${lifecycleStatusTone(row.status)}`}>{lifecycleStatusLabel(row.status)}</span></td><td>{formatMoney(row.total_amount, row.currency)}</td><td>{formatMoney(row.paid_amount, row.currency)}</td><td>{formatMoney(row.balance, row.currency)}</td></tr>)}</tbody>
            </table>
          </div>}

          {canChat && <div className="operations-panel operations-current-project">
            <header><div><span className="operations-kicker">MANAGEMENT ↔ PROJECT MANAGER</span><h2><MessageSquare size={16}/> Project Chat</h2></div></header>
            <div className="operations-daily-history">
              {messages.map(row => <div key={row.id} className={row.sender_user_id === user?.id ? 'operations-check' : 'operations-note'}><strong>{row.sender_name || 'User'}:</strong> {row.message} <small>{formatDateTime(row.created_at)}</small></div>)}
              {!messages.length && <div className="operations-empty-compact">No project chat messages yet.</div>}
            </div>
            <div className="operations-actions">
              <input style={{ flex: 1 }} placeholder="Message the Project Manager / Management" value={chatText} onChange={e => setChatText(e.target.value)} />
              <button className="operations-button" disabled={!chatText.trim()} onClick={() => void sendChat()}><Send size={15}/> Send</button>
            </div>
          </div>}
        </>}
      </section>
    </div>
  </div>
}
