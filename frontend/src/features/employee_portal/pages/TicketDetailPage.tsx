import { ArrowLeft, Building2, CheckCircle2, Clock3, Cpu, Gauge, HardDrive, Keyboard, MessageCircle, Monitor, MousePointer2, Paperclip, Send, ShieldAlert, UserCheck, UserRound, Wrench } from 'lucide-react'
import { type FormEvent, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { useAuth } from '../../../context/AuthContext'
import { apiBlob, apiFetch } from '../../../lib/api'
import { formatDuration, formatStandardDateTime } from '../../../lib/dateTime'
import { ticketSlaDisplay } from '../../../lib/ticketSla'
import type { SupportTicket, TicketAttachment, TicketPriority, TicketStatus } from '../../../types'

function priorityLabel(priority: TicketPriority): string {
  return priority === 'medium' ? 'Moderate' : priority.charAt(0).toUpperCase() + priority.slice(1)
}

function booleanLabel(value: boolean | undefined): string {
  return value ? 'Yes' : 'No'
}

function formatAttachmentSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function TicketAttachmentPreview({ ticketId, attachment }: { ticketId: number; attachment: TicketAttachment }) {
  const [url, setUrl] = useState('')
  const [previewError, setPreviewError] = useState(false)

  useEffect(() => {
    let active = true
    let objectUrl = ''
    setPreviewError(false)
    void apiBlob(`/tickets/${ticketId}/attachments/${attachment.id}/content`)
      .then(blob => {
        if (!active) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch(() => { if (active) setPreviewError(true) })
    return () => {
      active = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [attachment.id, ticketId])

  if (previewError) return <article className="ticket-evidence-card ticket-evidence-error"><Paperclip size={20} /><div><strong>{attachment.original_filename}</strong><span>Preview unavailable</span></div></article>
  return <a className="ticket-evidence-card" href={url || undefined} target="_blank" rel="noreferrer" aria-label={`Open ${attachment.original_filename}`}>
    {url ? <img src={url} alt={attachment.original_filename} /> : <div className="ticket-evidence-loading">Loading…</div>}
    <div><strong>{attachment.original_filename}</strong><span>{formatAttachmentSize(attachment.file_size)} · {attachment.uploaded_by_name}</span></div>
  </a>
}

export function TicketDetailPage() {
  const { id } = useParams()
  const { user } = useAuth()
  const [ticket, setTicket] = useState<SupportTicket | null>(null)
  const [message, setMessage] = useState('')
  const [statusValue, setStatusValue] = useState<TicketStatus>('new')
  const [resolution, setResolution] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [nowMs, setNowMs] = useState(() => Date.now())

  function load() {
    if (!id) return
    void apiFetch<SupportTicket>(`/tickets/${id}`).then(item => {
      setTicket(item); setStatusValue(item.status); setResolution(item.resolution || '')
    }).catch(err => setError(err instanceof Error ? err.message : 'Could not load ticket'))
  }
  useEffect(load, [id])
  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 30_000)
    return () => window.clearInterval(timer)
  }, [])

  async function sendMessage(event: FormEvent) {
    event.preventDefault()
    if (!ticket || !message.trim()) return
    setLoading(true); setError('')
    try {
      const updated = await apiFetch<SupportTicket>(`/tickets/${ticket.id}/messages`, { method: 'POST', body: JSON.stringify({ message }) })
      setTicket(updated); setMessage('')
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not send message') }
    finally { setLoading(false) }
  }

  async function updateTicket() {
    if (!ticket) return
    setLoading(true); setError('')
    try {
      const updated = await apiFetch<SupportTicket>(`/tickets/${ticket.id}`, { method: 'PATCH', body: JSON.stringify({ status: statusValue, resolution: resolution || undefined }) })
      setTicket(updated)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not update ticket') }
    finally { setLoading(false) }
  }

  async function assignToMe() {
    if (!ticket) return
    setLoading(true); setError('')
    try {
      const updated = await apiFetch<SupportTicket>(`/tickets/${ticket.id}`, { method: 'PATCH', body: JSON.stringify({ assign_to_self: true }) })
      setTicket(updated); setStatusValue(updated.status)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not assign ticket') }
    finally { setLoading(false) }
  }

  async function reopen() {
    if (!ticket) return
    setLoading(true); setError('')
    try {
      const updated = await apiFetch<SupportTicket>(`/tickets/${ticket.id}`, { method: 'PATCH', body: JSON.stringify({ status: 'reopened' }) })
      setTicket(updated); setStatusValue(updated.status)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not reopen ticket') }
    finally { setLoading(false) }
  }

  if (!ticket) return <div className="panel-card">{error || 'Loading ticket...'}</div>
  const requester = user?.id === ticket.messages[0]?.author_id || user?.email === ticket.requester_email
  const monitoringReadOnly = !requester && (
    (user?.role === 'software_team' && ticket.department !== 'software_team')
    || (user?.role === 'management' && ticket.department !== 'management')
  )
  const canReply = requester || ticket.can_handle
  const sla = ticketSlaDisplay(ticket, nowMs)

  return <>
    <DashboardHeader eyebrow={`${ticket.ticket_code} · ${ticket.department.replace('_', ' ').toUpperCase()}`} title={ticket.title} description={`${ticket.requester_name} · ${ticket.branch_name} · Raised ${formatStandardDateTime(ticket.created_at)}`} />
    <div className="ticket-detail-layout">
      <section className="panel-card ticket-conversation-panel">
        <Link to="/tickets" className="ticket-back-link"><ArrowLeft size={16} />Back to tickets</Link>
        <div className="ticket-description-card"><span className="section-kicker">ORIGINAL ISSUE</span><p>{ticket.description}</p>{ticket.location && <small>Issue location: {ticket.location}</small>}{ticket.asset_number && !ticket.asset_snapshot && <small>Asset: {ticket.asset_number}</small>}</div>
        {(ticket.attachments?.length || 0) > 0 && <section className="ticket-evidence-section">
          <div className="ticket-section-heading"><div><span className="section-kicker">ATTACHED EVIDENCE</span><p>Screenshots and photos supplied by the employee for this ticket.</p></div><span className="ticket-attachment-count">{ticket.attachments?.length}</span></div>
          <div className="ticket-evidence-grid">
            {ticket.attachments?.map(attachment => <TicketAttachmentPreview key={attachment.id} ticketId={ticket.id} attachment={attachment} />)}
          </div>
        </section>}
        {ticket.asset_snapshot && <article className="ticket-selected-asset-card ticket-detail-asset-card">
          <header>
            <div><span>ASSET SNAPSHOT WHEN TICKET WAS RAISED</span><h2>{ticket.asset_snapshot.cpu_asset_tag || ticket.asset_snapshot.asset_code}</h2><p>Internal reference {ticket.asset_snapshot.asset_code}</p></div>
            <span className={`status ${ticket.asset_snapshot.status}`}>{ticket.asset_snapshot.status.replaceAll('_', ' ')}</span>
          </header>
          <div className="ticket-asset-detail-grid">
            <div><Gauge size={17} /><span>Workstation</span><strong>{ticket.asset_snapshot.workstation_no || 'Not recorded'}</strong></div>
            <div><UserRound size={17} /><span>Used By</span><strong>{ticket.asset_snapshot.used_by || 'Unassigned'}</strong></div>
            <div><Building2 size={17} /><span>Department</span><strong>{ticket.asset_snapshot.department || 'Not recorded'}</strong></div>
            <div><Cpu size={17} /><span>Device</span><strong>{ticket.asset_snapshot.device_type} · {ticket.asset_snapshot.system_name || 'Unnamed system'}</strong></div>
            <div><HardDrive size={17} /><span>Configuration</span><strong>{[ticket.asset_snapshot.processor, ticket.asset_snapshot.memory_gb, ticket.asset_snapshot.ssd || ticket.asset_snapshot.hdd].filter(Boolean).join(' · ') || 'Not recorded'}</strong></div>
            <div><Building2 size={17} /><span>Asset Location</span><strong>{ticket.asset_snapshot.location || ticket.asset_snapshot.work_mode || 'Not recorded'}</strong></div>
          </div>
          <div className="ticket-component-tags">
            <span><Monitor size={16} />Monitor <strong>{ticket.asset_snapshot.monitor_asset_tags || 'Not recorded'}</strong></span>
            <span><MousePointer2 size={16} />Mouse <strong>{ticket.asset_snapshot.mouse_asset_tag || 'Not recorded'}</strong></span>
            <span><Keyboard size={16} />Keyboard <strong>{ticket.asset_snapshot.keyboard_asset_tag || 'Not recorded'}</strong></span>
          </div>
        </article>}
        {ticket.component && <article className="ticket-issue-classification-card">
          <header><div><Wrench size={19} /><span>ISSUE CLASSIFICATION</span></div><span className={`ticket-priority priority-${ticket.priority}`}>{priorityLabel(ticket.priority)}</span></header>
          <div className="ticket-classification-grid">
            <div><span>Affected component</span><strong>{ticket.category || ticket.component.replaceAll('_', ' ')}</strong></div>
            <div><span>Component tag</span><strong>{ticket.component_asset_tag || 'No separate tag'}</strong></div>
            <div><span>Exact problem</span><strong>{ticket.problem_label || ticket.problem_code || 'Not recorded'}</strong></div>
            <div><span>Initial response target</span><strong>{ticket.sla_target_minutes ? `${ticket.sla_target_minutes < 60 ? `${ticket.sla_target_minutes} minutes` : `${Math.round(ticket.sla_target_minutes / 60)} hours`}` : 'Not assigned'}</strong></div>
          </div>
          {ticket.priority_reason && <div className="ticket-priority-reason"><ShieldAlert size={18} /><div><strong>Why this priority was selected</strong><p>{ticket.priority_reason}</p></div></div>}
          {ticket.impact_assessment && <div className="ticket-impact-summary">
            <span>Work stopped <strong>{booleanLabel(ticket.impact_assessment.work_stopped)}</strong></span>
            <span>Alternative available <strong>{booleanLabel(ticket.impact_assessment.alternative_available)}</strong></span>
            <span>Multiple employees <strong>{booleanLabel(ticket.impact_assessment.multiple_users_affected)}</strong></span>
            <span>Data-loss risk <strong>{booleanLabel(ticket.impact_assessment.data_loss_risk)}</strong></span>
            <span>Security risk <strong>{booleanLabel(ticket.impact_assessment.security_risk)}</strong></span>
            <span>Delivery affected <strong>{booleanLabel(ticket.impact_assessment.client_delivery_affected)}</strong></span>
            <span>Recurring issue <strong>{booleanLabel(ticket.impact_assessment.recurring_issue)}</strong></span>
            {ticket.impact_assessment.started_when && <span>Started <strong>{ticket.impact_assessment.started_when}</strong></span>}
          </div>}
        </article>}
        <div className="ticket-message-thread">{ticket.messages.map(item => <article key={item.id} className={`ticket-message ${item.author_id === user?.id ? 'mine' : ''}`}><header><strong>{item.author_name}</strong><span>{item.author_role.replace('_', ' ')} · {formatStandardDateTime(item.created_at)}</span></header><p>{item.message}</p></article>)}</div>
        {monitoringReadOnly && <div className="auth-flow-info"><Clock3 size={18} /><span>Monitoring access only. The {ticket.department.replace('_', ' ')} team handles this ticket.</span></div>}
        {canReply && !monitoringReadOnly && <form className="ticket-reply-form" onSubmit={sendMessage}><textarea value={message} onChange={e => setMessage(e.target.value)} rows={4} placeholder="Add a message or update" required /><button className="primary-button" disabled={loading}><Send size={17} />Send Reply</button></form>}
        {requester && ticket.status === 'resolved' && <button className="secondary-button" onClick={reopen} disabled={loading}>Issue not fixed — Reopen Ticket</button>}
      </section>
      <aside className="panel-card ticket-control-panel">
        <div className="ticket-meta-row"><span>Status</span><span className={`ticket-status status-${ticket.status}`}>{ticket.status.replaceAll('_', ' ')}</span></div>
        <div className="ticket-meta-row"><span>Priority</span><span className={`ticket-priority priority-${ticket.priority}`}>{priorityLabel(ticket.priority)}</span></div>
        <div className="ticket-meta-row"><span>Initial Response SLA</span><span className={`ticket-sla-badge sla-${sla.state}`}>{sla.label}</span></div>
        <div className="ticket-meta-row"><span>SLA Timing</span><strong>{sla.value}</strong></div>
        {ticket.sla_due_at && <div className="ticket-meta-row"><span>SLA Due</span><strong>{formatStandardDateTime(ticket.sla_due_at)}</strong></div>}
        {ticket.sla_first_response_at && <div className="ticket-meta-row"><span>First Response</span><strong>{formatStandardDateTime(ticket.sla_first_response_at)}</strong></div>}
        <div className="ticket-meta-row"><span>Assigned To</span><strong>{ticket.assigned_to_name || 'Not assigned'}</strong></div>
        <div className="ticket-meta-row"><span>Department</span><strong>{ticket.department.replace('_', ' ')}</strong></div>
        <div className="ticket-meta-row"><span>Reporting Manager</span><strong>{ticket.reporting_manager_email || 'Not recorded'}</strong></div>
        <div className="ticket-meta-row"><span>Raised At</span><strong>{formatStandardDateTime(ticket.created_at)}</strong></div>
        <div className="ticket-meta-row"><span>Last Updated</span><strong>{formatStandardDateTime(ticket.updated_at)}</strong></div>
        {ticket.status === 'resolved' && <div className="ticket-meta-row"><span>Resolved In</span><strong>{formatDuration(ticket.created_at, ticket.resolved_at || ticket.updated_at)}</strong></div>}
        {ticket.status === 'closed' && <div className="ticket-meta-row"><span>Closed In</span><strong>{formatDuration(ticket.created_at, ticket.closed_at || ticket.updated_at)}</strong></div>}
        {ticket.can_handle && <div className="ticket-handler-controls"><span className="section-kicker">DEPARTMENT ACTIONS</span><button className="secondary-button" onClick={assignToMe} disabled={loading}><UserCheck size={17} />Assign to Me</button><label><span>Status</span><select value={statusValue} onChange={e => setStatusValue(e.target.value as TicketStatus)}><option value="new">New</option><option value="assigned">Assigned</option><option value="in_progress">In Progress</option><option value="waiting_for_employee">Waiting for Employee</option><option value="resolved">Resolved</option><option value="closed">Closed</option><option value="reopened">Reopened</option></select></label><label><span>Resolution Notes</span><textarea value={resolution} onChange={e => setResolution(e.target.value)} rows={5} placeholder="Describe the fix or next action" /></label><button className="primary-button" onClick={updateTicket} disabled={loading}><CheckCircle2 size={17} />Save Update</button></div>}
        {ticket.resolution && <div className="ticket-resolution"><MessageCircle size={18} /><div><strong>Resolution</strong><p>{ticket.resolution}</p></div></div>}
        {error && <div className="error-message">{error}</div>}
      </aside>
    </div>
  </>
}
