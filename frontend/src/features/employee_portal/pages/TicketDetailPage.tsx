import { ArrowLeft, CheckCircle2, Clock3, MessageCircle, Send, UserCheck } from 'lucide-react'
import { type FormEvent, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch } from '../../../lib/api'
import type { SupportTicket, TicketStatus } from '../../../types'

export function TicketDetailPage() {
  const { id } = useParams()
  const { user } = useAuth()
  const [ticket, setTicket] = useState<SupportTicket | null>(null)
  const [message, setMessage] = useState('')
  const [statusValue, setStatusValue] = useState<TicketStatus>('new')
  const [resolution, setResolution] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  function load() {
    if (!id) return
    void apiFetch<SupportTicket>(`/tickets/${id}`).then(item => {
      setTicket(item); setStatusValue(item.status); setResolution(item.resolution || '')
    }).catch(err => setError(err instanceof Error ? err.message : 'Could not load ticket'))
  }
  useEffect(load, [id])

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
  const softwareReadOnly = user?.role === 'software_team' && ticket.department !== 'software_team' && !requester
  const canReply = requester || ticket.can_handle

  return <>
    <DashboardHeader eyebrow={`${ticket.ticket_code} · ${ticket.department.replace('_', ' ').toUpperCase()}`} title={ticket.title} description={`${ticket.requester_name} · ${ticket.branch_name} · Created ${new Date(ticket.created_at).toLocaleString()}`} />
    <div className="ticket-detail-layout">
      <section className="panel-card ticket-conversation-panel">
        <Link to="/tickets" className="ticket-back-link"><ArrowLeft size={16} />Back to tickets</Link>
        <div className="ticket-description-card"><span className="section-kicker">ORIGINAL ISSUE</span><p>{ticket.description}</p>{ticket.location && <small>Location: {ticket.location}</small>}{ticket.asset_number && <small>Asset: {ticket.asset_number}</small>}</div>
        <div className="ticket-message-thread">{ticket.messages.map(item => <article key={item.id} className={`ticket-message ${item.author_id === user?.id ? 'mine' : ''}`}><header><strong>{item.author_name}</strong><span>{item.author_role.replace('_', ' ')} · {new Date(item.created_at).toLocaleString()}</span></header><p>{item.message}</p></article>)}</div>
        {softwareReadOnly && <div className="auth-flow-info"><Clock3 size={18} /><span>Monitoring access only. The {ticket.department.replace('_', ' ')} team handles this ticket.</span></div>}
        {canReply && !softwareReadOnly && <form className="ticket-reply-form" onSubmit={sendMessage}><textarea value={message} onChange={e => setMessage(e.target.value)} rows={4} placeholder="Add a message or update" required /><button className="primary-button" disabled={loading}><Send size={17} />Send Reply</button></form>}
        {requester && ticket.status === 'resolved' && <button className="secondary-button" onClick={reopen} disabled={loading}>Issue not fixed — Reopen Ticket</button>}
      </section>
      <aside className="panel-card ticket-control-panel">
        <div className="ticket-meta-row"><span>Status</span><span className={`ticket-status status-${ticket.status}`}>{ticket.status.replaceAll('_', ' ')}</span></div>
        <div className="ticket-meta-row"><span>Priority</span><span className={`ticket-priority priority-${ticket.priority}`}>{ticket.priority}</span></div>
        <div className="ticket-meta-row"><span>Assigned To</span><strong>{ticket.assigned_to_name || 'Not assigned'}</strong></div>
        <div className="ticket-meta-row"><span>Department</span><strong>{ticket.department.replace('_', ' ')}</strong></div>
        {ticket.can_handle && <div className="ticket-handler-controls"><span className="section-kicker">DEPARTMENT ACTIONS</span><button className="secondary-button" onClick={assignToMe} disabled={loading}><UserCheck size={17} />Assign to Me</button><label><span>Status</span><select value={statusValue} onChange={e => setStatusValue(e.target.value as TicketStatus)}><option value="new">New</option><option value="assigned">Assigned</option><option value="in_progress">In Progress</option><option value="waiting_for_employee">Waiting for Employee</option><option value="resolved">Resolved</option><option value="closed">Closed</option><option value="reopened">Reopened</option></select></label><label><span>Resolution Notes</span><textarea value={resolution} onChange={e => setResolution(e.target.value)} rows={5} placeholder="Describe the fix or next action" /></label><button className="primary-button" onClick={updateTicket} disabled={loading}><CheckCircle2 size={17} />Save Update</button></div>}
        {ticket.resolution && <div className="ticket-resolution"><MessageCircle size={18} /><div><strong>Resolution</strong><p>{ticket.resolution}</p></div></div>}
        {error && <div className="error-message">{error}</div>}
      </aside>
    </div>
  </>
}
