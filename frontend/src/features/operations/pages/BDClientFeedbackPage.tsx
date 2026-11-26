import { AlertTriangle, CheckCircle2, Clock3, Copy, MailCheck, MessageSquareOff, RefreshCcw, RotateCcw, Send, ThumbsDown, ThumbsUp, Wallet } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
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
/** Project statuses where BD is actively driving the client feedback decision. */
const FEEDBACK_ACTION_STATUSES = [...OPEN_REQUEST_STATUSES, 'FEEDBACK_REQUESTED', 'CLIENT_ACCEPTANCE_PENDING_BD', 'FEEDBACK_NEGATIVE']
/** Terminal feedback outcomes: no further BD decision is required. */
const FEEDBACK_END_STATUSES = ['CLIENT_ACCEPTED', 'DEEMED_ACCEPTED', 'NO_FEEDBACK_CLOSURE_RECOMMENDED', 'READY_FOR_BILLING', 'CHANGE_REQUEST_PENDING']

export function BDClientFeedbackPage() {
  const [searchParams] = useSearchParams()
  const requestedProjectId = Number(searchParams.get('project') || 0) || null
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
  const [manualForm, setManualForm] = useState<{ open: 'accepted' | 'negative' | null; comments: string; correctionDescription: string; clientName: string; reference: string }>({ open: null, comments: '', correctionDescription: '', clientName: '', reference: '' })

  function loadDashboard() {
    setLoading(true)
    setError('')
    void apiFetch<LifecycleDashboard>('/operations/lifecycle/dashboard')
      .then(data => {
        setDashboard(data)
        if (!selectedId && data.projects.length) {
          const requested = requestedProjectId && data.projects.some(row => row.id === requestedProjectId) ? requestedProjectId : null
          setSelectedId(requested || data.projects[0].id)
        }
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

  async function confirmAcceptance(response: FeedbackResponseRow) {
    await apiFetch(`/operations/lifecycle/feedback-responses/${response.id}/confirm-acceptance`, { method: 'POST' })
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
      body: JSON.stringify({ remarks: closureRemarks.trim() || 'No client feedback received after reminder and feedback-link expiry; requesting billing authorization.' }),
    })
    setClosureRemarks('')
  }

  async function recordManualFeedback(responseType: 'accepted' | 'correction' | 'additional_scope') {
    if (!selectedId) return
    await apiFetch(`/operations/lifecycle/projects/${selectedId}/feedback-responses/manual`, {
      method: 'POST',
      body: JSON.stringify({
        response_type: responseType,
        comments: manualForm.comments.trim(),
        correction_description: responseType === 'accepted' ? null : (manualForm.correctionDescription.trim() || null),
        client_name: manualForm.clientName.trim() || null,
        reference: manualForm.reference.trim() || null,
      }),
    })
    setManualForm({ open: null, comments: '', correctionDescription: '', clientName: '', reference: '' })
  }

  const openRequest = detail?.feedback_requests.find(row => row.status === 'sent' && !row.responded_at) || null
  const canSend = detail ? OPEN_REQUEST_STATUSES.includes(detail.workflow_status) && !openRequest : false
  const canRemind = !!openRequest && new Date(openRequest.expires_at).getTime() > Date.now()
  const pendingAccepted = detail?.feedback_responses.filter(row => row.classification_status === 'pending_bd' && row.response_type === 'accepted') ?? []
  const pendingClassification = detail?.feedback_responses.filter(row => row.classification_status === 'pending_bd' && row.response_type !== 'accepted') ?? []
  const deliveredReworks = detail?.rework_cycles.filter(row => row.status === 'REWORK_DELIVERED') ?? []
  const staleReworks = detail?.rework_cycles.filter(row => row.out_of_sync) ?? []
  const pendingChangeRequests = detail?.change_requests.filter(row => row.status === 'pending') ?? []

  // ---- BD Feedback Action Center (STATE A) ----
  // The four BD decisions are presented as soon as the project legitimately
  // enters the client feedback stage, not only after a portal response exists.
  const inFeedbackStage = detail ? FEEDBACK_ACTION_STATUSES.includes(detail.workflow_status) : false
  const feedbackFinished = detail ? FEEDBACK_END_STATUSES.includes(detail.workflow_status) : false
  const canRecordManual = detail ? OPEN_REQUEST_STATUSES.includes(detail.workflow_status) : false
  const noFeedbackReason = !detail ? ''
    : !openRequest ? 'Send a feedback request first; No-Feedback closure needs an unanswered request.'
    : openRequest.reminder_count < 1 ? 'Send at least one reminder before recommending no-feedback closure.'
    : canRemind ? `Waiting for the client; the current link expires ${formatDateTime(openRequest.expires_at)}.`
    : null // null = eligible

  return <div className="operations-page">
    <DashboardHeader
      eyebrow="CLIENT FEEDBACK LIFECYCLE"
      title="Client Feedback"
      description="Send secure post-delivery feedback requests, confirm client classification and drive Ready For Billing hand-off to Finance."
      actions={<button className="operations-button secondary" onClick={loadDashboard}><RefreshCcw size={16}/> Refresh</button>}
      meta={<>
        <span className="nk-meta-chip"><MailCheck size={14}/> Secure post-delivery feedback links</span>
        <span className="nk-meta-chip"><Wallet size={14}/> Approved feedback drives Ready For Billing</span>
        <span className="nk-meta-chip"><Clock3 size={14}/> Link validity tracked per request</span>
      </>}
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

          {inFeedbackStage && <div className="operations-daily-card">
            <div className="operations-daily-heading"><h3>Client Feedback Action Center</h3><span className={`operations-status ${lifecycleStatusTone(detail.workflow_status)}`}>{lifecycleStatusLabel(detail.workflow_status)}</span></div>
            <p className="operations-muted">Choose the client's outcome. Portal responses appear below automatically; use these controls when the client responds offline (call, email or letter).</p>
            <div className="operations-actions">
              <button className="operations-button success" disabled={!canRecordManual || busy === 'manual-accepted'} onClick={() => setManualForm({ open: 'accepted', comments: '', correctionDescription: '', clientName: '', reference: '' })} title={canRecordManual ? 'Record a positive client outcome' : 'Available once the project is awaiting client feedback'}><ThumbsUp size={15}/> Client Accepted / Positive</button>
              <button className="operations-button warning" disabled={!canRecordManual || busy === 'manual-negative'} onClick={() => setManualForm({ open: 'negative', comments: '', correctionDescription: '', clientName: '', reference: '' })} title={canRecordManual ? 'Record a negative client outcome' : 'Available once the project is awaiting client feedback'}><ThumbsDown size={15}/> Negative Feedback</button>
              <button className="operations-button secondary" disabled={!!noFeedbackReason || busy === 'closure'} title={noFeedbackReason || 'Recommend no-feedback closure to Management'} onClick={() => void run('closure', () => recommendNoFeedback(openRequest!.id), 'No-feedback closure recommended to Management')}><MessageSquareOff size={15}/> No Feedback Received</button>
            </div>
            {!noFeedbackReason && openRequest && <label className="operations-field"><span>No-feedback closure justification</span><textarea value={closureRemarks} onChange={e => setClosureRemarks(e.target.value)} rows={2} placeholder="Why billing should proceed without client feedback"/></label>}
            {noFeedbackReason && <div className="operations-note">{noFeedbackReason}</div>}
          </div>}

          {feedbackFinished && <div className="operations-note">The client feedback decision is complete for this project — {lifecycleStatusLabel(detail.workflow_status)}.</div>}

          {manualForm.open && <div className="operations-daily-card">
            <div className="operations-daily-heading"><h3>{manualForm.open === 'accepted' ? 'Record Client Acceptance (offline)' : 'Record Negative Client Feedback (offline)'}</h3></div>
            <div className="operations-alert error"><AlertTriangle size={15}/> {manualForm.open === 'accepted'
              ? 'Confirm the client has accepted the delivery outside the portal. This creates a client acceptance awaiting your confirmation, then sends the project to Finance as Ready For Billing.'
              : 'Confirm the client reported a correction or additional scope outside the portal. This opens BD classification, then rework or a change request.'}</div>
            <div className="operations-form-grid">
              <label className="operations-field"><span>Client contact name</span><input value={manualForm.clientName} onChange={e => setManualForm({ ...manualForm, clientName: e.target.value })} placeholder="Who communicated the outcome"/></label>
              <label className="operations-field"><span>Reference (email / call / letter)</span><input value={manualForm.reference} onChange={e => setManualForm({ ...manualForm, reference: e.target.value })} placeholder="e.g. email 2026-10-06, call with Mr. Rao"/></label>
              {manualForm.open === 'negative' && <label className="operations-field operations-span-2"><span>What the client wants corrected / added</span><textarea value={manualForm.correctionDescription} onChange={e => setManualForm({ ...manualForm, correctionDescription: e.target.value })} rows={3} placeholder="Required: the correction or additional scope the client described"/></label>}
              <label className="operations-field operations-span-2"><span>BD remarks</span><textarea value={manualForm.comments} onChange={e => setManualForm({ ...manualForm, comments: e.target.value })} rows={2} placeholder="Required: how and when the outcome was received"/></label>
            </div>
            <div className="operations-actions">
              <button className="operations-button success" disabled={busy === 'manual-submit' || !manualForm.comments.trim() || (manualForm.open === 'negative' && !manualForm.correctionDescription.trim())} onClick={() => void run('manual-submit', () => recordManualFeedback(manualForm.open === 'accepted' ? 'accepted' : 'correction'), manualForm.open === 'accepted' ? 'Client acceptance recorded; confirm it below to send for billing' : 'Negative feedback recorded; classify it below')}><CheckCircle2 size={15}/> Confirm & Record</button>
              <button className="operations-button secondary" onClick={() => setManualForm({ open: null, comments: '', correctionDescription: '', clientName: '', reference: '' })}>Cancel</button>
            </div>
          </div>}

          {canSend && <div className="operations-daily-form operations-span-2">
            <label className="operations-field operations-span-2"><span>Message to client (optional)</span><textarea value={sendMessage} onChange={e => setSendMessage(e.target.value)} rows={3}/></label>
            <label className="operations-field"><span>Link expiry (days)</span><input type="number" min={1} max={90} value={sendExpiry} onChange={e => setSendExpiry(Number(e.target.value) || 14)}/></label>
            <div className="operations-actions"><button className="operations-button" disabled={busy === 'send'} onClick={() => void run('send', sendFeedbackRequest, 'Feedback request sent to client')}><Send size={15}/> Send Feedback Request</button></div>
          </div>}

          {canRemind && openRequest && <div className="operations-actions"><button className="operations-button secondary" disabled={busy === 'remind'} onClick={() => void run('remind', () => sendReminder(openRequest.id), 'Reminder sent')}><MailCheck size={15}/> Send Reminder ({openRequest.reminder_count} sent)</button></div>}

          {pendingAccepted.map(response => <div key={response.id} className="operations-daily-card">
            <div><strong>Positive client feedback received{response.source === 'bd_manual' ? ' (recorded offline by BD)' : ''}</strong><p>{response.comments || 'The client accepted the delivery.'}</p></div>
            <div className="operations-note">BD confirmation is required before Finance receives the billing hand-off.</div>
            <div className="operations-actions"><button className="operations-button success" disabled={busy === `accept-${response.id}`} onClick={() => void run(`accept-${response.id}`, () => confirmAcceptance(response), 'Client acceptance confirmed; project sent to Finance as Ready For Billing')}><CheckCircle2 size={15}/> Client Accepted – Send for Billing</button></div>
          </div>)}

          {pendingClassification.map(response => {
            const form = classifyForm[response.id] || { classification: 'correction' as const, remarks: '', commercial_impact: '', currency: 'INR' }
            return <div key={response.id} className="operations-daily-card">
              <div><strong>Client response requires classification{response.source === 'bd_manual' ? ' (recorded offline by BD)' : ''}</strong><p>{response.correction_description || response.comments || 'No description provided.'}</p></div>
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
