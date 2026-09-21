import { CheckCircle2, Clock3, Copy, MailCheck, RefreshCcw, RotateCcw, Send, Wallet } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { StatCard } from '../../../components/StatCard'
import { apiFetch } from '../../../lib/api'
import {
  ChangeRequestRow,
  FeedbackRequestRow,
  FeedbackResponseRow,
  LifecycleDashboard,
  Project360,
  ReworkCycleRow,
  formatDateTime,
  formatMoney,
  lifecycleStatusLabel,
  lifecycleStatusTone,
} from '../lifecycle-types'
import '../operations.css'

const OPEN_REQUEST_STATUSES = ['FEEDBACK_NOT_SENT', 'REWORK_RESUBMITTED', 'FEEDBACK_REMINDER_SENT', 'AWAITING_CLIENT_FEEDBACK']

export function BDClientFeedbackPage() {
  const [dashboard, setDashboard] = useState<LifecycleDashboard | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<Project360 | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [lastLink, setLastLink] = useState('')

  const [sendMessage, setSendMessage] = useState('')
  const [sendExpiry, setSendExpiry] = useState(14)
  const [classifyForm, setClassifyForm] = useState<Record<number, { classification: 'correction' | 'additional_scope'; remarks: string; commercial_impact: string; currency: string }>>({})
  const [decisionForm, setDecisionForm] = useState<Record<number, { decision: 'approved' | 'rejected'; comments: string }>>({})
  const [closureRemarks, setClosureRemarks] = useState('')

  function loadDashboard() {
    setLoading(true)
    setError('')
    void apiFetch<LifecycleDashboard>('/operations/lifecycle/dashboard')
      .then(data => {
        setDashboard(data)
        if (!selectedId && data.projects.length) setSelectedId(data.projects[0].id)
      })
      .catch(err => setError(err instanceof Error ? err.message : 'Unable to load the feedback lifecycle dashboard'))
      .finally(() => setLoading(false))
  }

  function loadDetail(id: number) {
    void apiFetch<Project360>(`/operations/lifecycle/projects/${id}`)
      .then(setDetail)
      .catch(err => setError(err instanceof Error ? err.message : 'Unable to load project detail'))
  }

  useEffect(loadDashboard, [])
  useEffect(() => { if (selectedId) loadDetail(selectedId) }, [selectedId])

  const projects = useMemo(() => dashboard?.projects ?? [], [dashboard])

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

  async function sendFeedbackRequest() {
    if (!selectedId) return
    const result = await apiFetch<{ external_url: string }>(`/operations/lifecycle/projects/${selectedId}/feedback-requests`, {
      method: 'POST',
      body: JSON.stringify({ message: sendMessage.trim() || null, expiry_days: sendExpiry }),
    })
    setLastLink(result.external_url)
    setSendMessage('')
  }

  async function sendReminder(requestId: number) {
    const result = await apiFetch<{ external_url: string }>(`/operations/lifecycle/feedback-requests/${requestId}/reminders`, { method: 'POST' })
    setLastLink(result.external_url)
  }

  async function classify(response: FeedbackResponseRow) {
    const form = classifyForm[response.id]
    if (!form) return
    await apiFetch(`/operations/lifecycle/feedback-responses/${response.id}/classification`, {
      method: 'POST',
      body: JSON.stringify({
        classification: form.classification,
        remarks: form.remarks.trim() || null,
        commercial_impact: form.classification === 'additional_scope' && form.commercial_impact ? Number(form.commercial_impact) : null,
        currency: form.currency || 'INR',
      }),
    })
  }

  async function syncRework(cycle: ReworkCycleRow) {
    await apiFetch(`/operations/lifecycle/rework-cycles/${cycle.id}/sync`, { method: 'POST' })
  }

  async function resubmit(cycle: ReworkCycleRow) {
    const result = await apiFetch<{ external_url: string }>(`/operations/lifecycle/rework-cycles/${cycle.id}/resubmit`, {
      method: 'POST',
      body: JSON.stringify({ message: sendMessage.trim() || null, expiry_days: sendExpiry }),
    })
    setLastLink(result.external_url)
    setSendMessage('')
  }

  async function decide(row: ChangeRequestRow) {
    const form = decisionForm[row.id]
    if (!form) return
    await apiFetch(`/operations/lifecycle/change-requests/${row.id}/decision`, {
      method: 'POST',
      body: JSON.stringify({ decision: form.decision, comments: form.comments.trim() || 'Decision recorded', commercial_impact: row.commercial_impact, currency: row.currency }),
    })
  }

  async function recommendNoFeedback(requestId: number) {
    await apiFetch(`/operations/lifecycle/feedback-requests/${requestId}/no-feedback-recommendation`, {
      method: 'POST',
      body: JSON.stringify({ remarks: closureRemarks.trim() || 'No response received after reminder and link expiry.' }),
    })
    setClosureRemarks('')
  }

  const openRequest = detail?.feedback_requests.find(row => row.status === 'sent' && !row.responded_at) || null
  const canSend = detail ? OPEN_REQUEST_STATUSES.includes(detail.workflow_status) && !openRequest : false
  const canRemind = !!openRequest && new Date(openRequest.expires_at).getTime() > Date.now()
  const canRecommendClosure = !!openRequest && !canRemind && openRequest.reminder_count >= 1
  const pendingClassification = detail?.feedback_responses.filter(row => row.classification_status === 'pending_bd') ?? []
  const deliveredReworks = detail?.rework_cycles.filter(row => row.status === 'REWORK_DELIVERED') ?? []
  const staleReworks = detail?.rework_cycles.filter(row => row.out_of_sync) ?? []
  const pendingChangeRequests = detail?.change_requests.filter(row => row.status === 'pending') ?? []

  return <div className="operations-page">
    <DashboardHeader
      eyebrow="CLIENT FEEDBACK LIFECYCLE"
      title="Client Feedback"
      description="Send secure post-delivery feedback requests, confirm client classification and drive Ready For Billing hand-off to Finance."
      actions={<button className="operations-button secondary" onClick={loadDashboard}><RefreshCcw size={16}/> Refresh</button>}
    />
    {error && <div className="operations-alert error">{error}</div>}
    {notice && <div className="operations-alert success">{notice}</div>}
    {lastLink && <div className="operations-note">Secure client link: <code>{lastLink}</code> <button type="button" className="operations-button secondary" onClick={() => { void navigator.clipboard.writeText(lastLink); setNotice('Link copied to clipboard') }}><Copy size={14}/> Copy</button></div>}

    {dashboard && <section className="operations-stats-grid">
      <StatCard icon={Clock3} label="Awaiting Feedback" value={dashboard.summary.awaiting_feedback} tone="orange"/>
      <StatCard icon={RotateCcw} label="In Rework / Classification" value={dashboard.summary.rework} tone="purple"/>
      <StatCard icon={CheckCircle2} label="Ready For Billing" value={dashboard.summary.ready_for_billing} tone="green"/>
      <StatCard icon={Wallet} label="Payment Pending" value={dashboard.summary.payment_pending} tone="orange"/>
    </section>}

    <div className="operations-workflow-console-grid">
      <section className="operations-panel">
        <header><div><span className="operations-kicker">MY PROJECTS</span><h2>Feedback Pipeline</h2></div></header>
        {loading && <div className="operations-empty">Loading...</div>}
        {!loading && !projects.length && <div className="operations-empty">No projects have reached operational completion yet.</div>}
        <div className="operations-workflow-tree">
          {projects.map(row => <button key={row.id} type="button" className={row.id === selectedId ? 'active' : ''} onClick={() => setSelectedId(row.id)}>
            <span className="operations-workflow-step-number">{row.project_code.slice(-2)}</span>
            <span><strong>{row.project_code}</strong><small>{row.client_name || row.client_id || 'Client not recorded'}</small><small className={`operations-status ${lifecycleStatusTone(row.workflow_status)}`}>{lifecycleStatusLabel(row.workflow_status)}</small></span>
          </button>)}
        </div>
      </section>

      <section className="operations-panel">
        {!detail && <div className="operations-empty">Select a project to review its feedback lifecycle.</div>}
        {detail && <>
          <header><div><span className="operations-kicker">{detail.project_code} · {detail.client_name || detail.client_id || 'Client not recorded'}</span><h2>{detail.project_name}</h2></div><span className={`operations-status ${lifecycleStatusTone(detail.workflow_status)}`}>{lifecycleStatusLabel(detail.workflow_status)}</span></header>

          {canSend && <div className="operations-daily-form operations-span-2">
            <label className="operations-field operations-span-2"><span>Message to client (optional)</span><textarea value={sendMessage} onChange={e => setSendMessage(e.target.value)} rows={3}/></label>
            <label className="operations-field"><span>Link expiry (days)</span><input type="number" min={1} max={90} value={sendExpiry} onChange={e => setSendExpiry(Number(e.target.value) || 14)}/></label>
            <div className="operations-actions"><button className="operations-button" disabled={busy === 'send'} onClick={() => void run('send', sendFeedbackRequest, 'Feedback request sent to client')}><Send size={15}/> Send Feedback Request</button></div>
          </div>}

          {canRemind && openRequest && <div className="operations-actions"><button className="operations-button secondary" disabled={busy === 'remind'} onClick={() => void run('remind', () => sendReminder(openRequest.id), 'Reminder sent')}><MailCheck size={15}/> Send Reminder ({openRequest.reminder_count} sent)</button></div>}

          {canRecommendClosure && openRequest && <div className="operations-daily-form operations-span-2">
            <label className="operations-field operations-span-2"><span>No-feedback closure justification</span><textarea value={closureRemarks} onChange={e => setClosureRemarks(e.target.value)} rows={2}/></label>
            <div className="operations-actions"><button className="operations-button warning" disabled={busy === 'closure'} onClick={() => void run('closure', () => recommendNoFeedback(openRequest.id), 'No-feedback closure recommended to Management')}>Recommend No-Feedback Closure</button></div>
          </div>}

          {pendingClassification.map(response => {
            const form = classifyForm[response.id] || { classification: 'correction' as const, remarks: '', commercial_impact: '', currency: 'INR' }
            return <div key={response.id} className="operations-daily-card">
              <div><strong>Client response requires classification</strong><p>{response.correction_description || response.comments || 'No description provided.'}</p></div>
              <div className="operations-form-grid">
                <label className="operations-field"><span>Classification</span><select value={form.classification} onChange={e => setClassifyForm({ ...classifyForm, [response.id]: { ...form, classification: e.target.value as 'correction' | 'additional_scope' } })}>
                  <option value="correction">Correction / rework</option>
                  <option value="additional_scope">Additional scope / change request</option>
                </select></label>
                {form.classification === 'additional_scope' && <label className="operations-field"><span>Commercial impact</span><input type="number" min={0} step="0.01" value={form.commercial_impact} onChange={e => setClassifyForm({ ...classifyForm, [response.id]: { ...form, commercial_impact: e.target.value } })}/></label>}
                <label className="operations-field operations-span-2"><span>Remarks</span><textarea value={form.remarks} onChange={e => setClassifyForm({ ...classifyForm, [response.id]: { ...form, remarks: e.target.value } })} rows={2}/></label>
              </div>
              <div className="operations-actions"><button className="operations-button" disabled={busy === `classify-${response.id}`} onClick={() => void run(`classify-${response.id}`, () => classify(response), 'Classification confirmed')}>Confirm Classification</button></div>
            </div>
          })}

          {staleReworks.map(cycle => <div key={cycle.id} className="operations-daily-card">
            <div><strong>Rework Cycle {cycle.cycle_number}: status is behind the rework work</strong><p>The rework work packages are at {lifecycleStatusLabel(cycle.expected_status || '')}, but the lifecycle still shows {lifecycleStatusLabel(cycle.status)}. Synchronise it to continue.</p></div>
            <div className="operations-actions"><button className="operations-button secondary" disabled={busy === `sync-${cycle.id}`} onClick={() => void run(`sync-${cycle.id}`, () => syncRework(cycle), 'Rework status synchronised with the work packages')}><RefreshCcw size={15}/> Sync Rework Status</button></div>
          </div>)}

          {deliveredReworks.map(cycle => <div key={cycle.id} className="operations-daily-card">
            <div><strong>Rework Cycle {cycle.cycle_number} delivered: corrected delivery ready</strong><p>{cycle.correction_scope}</p></div>
            <div className="operations-actions"><button className="operations-button" disabled={busy === `resubmit-${cycle.id}`} onClick={() => void run(`resubmit-${cycle.id}`, () => resubmit(cycle), 'Corrected delivery resubmitted to the client')}><Send size={15}/> Resubmit Corrected Delivery to Client</button></div>
          </div>)}

          {pendingChangeRequests.map(row => {
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
              <thead><tr><th>Feedback Request</th><th>Recipient</th><th>Status</th><th>Reminders</th><th>Expires</th></tr></thead>
              <tbody>{detail.feedback_requests.map((row: FeedbackRequestRow) => <tr key={row.id}><td><strong>{row.request_code}</strong><small>Cycle {row.cycle_number}</small></td><td>{row.recipient_email || 'Restricted'}</td><td>{row.status}</td><td>{row.reminder_count}</td><td>{formatDateTime(row.expires_at)}</td></tr>)}
              {!detail.feedback_requests.length && <tr><td colSpan={5}>No feedback requests sent yet.</td></tr>}</tbody>
            </table>
          </div>
        </>}
      </section>
    </div>
  </div>
}
