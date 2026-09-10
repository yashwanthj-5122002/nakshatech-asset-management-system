import { Filter, Search, TicketCheck } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch } from '../../../lib/api'
import { formatDuration, formatStandardDateTime } from '../../../lib/dateTime'
import { ticketSlaDisplay } from '../../../lib/ticketSla'
import type { SupportTicketSummary, TicketDepartment, TicketPriority } from '../../../types'
import { type TicketProgressState, ticketProgressFromStatus, ticketProgressShortLabel } from '../ticketProgress'

const departmentLabels: Record<TicketDepartment, string> = {
  it: 'IT Department',
  drone: 'Drone Department',
  software_team: 'Software Team',
  management: 'Management',
}

function priorityLabel(priority: TicketPriority): string {
  return priority === 'medium' ? 'Moderate' : priority.charAt(0).toUpperCase() + priority.slice(1)
}

function slaLabel(minutes?: number): string {
  if (!minutes) return 'No SLA'
  if (minutes < 60) return `${minutes}m target`
  if (minutes < 1440) return `${Math.round(minutes / 60)}h target`
  return `${Math.round(minutes / 1440)}d target`
}

function durationState(ticket: SupportTicketSummary, nowMs: number): { value: string; label: string } {
  const progress = ticketProgressFromStatus(ticket.status)
  if (progress === 'completed') {
    return { value: formatDuration(ticket.created_at, ticket.resolved_at || ticket.closed_at || ticket.updated_at, nowMs), label: 'completed in' }
  }
  return { value: formatDuration(ticket.created_at, undefined, nowMs), label: progress === 'ongoing' ? 'work ongoing' : 'waiting to start' }
}

export function TicketListPage() {
  const { user } = useAuth()
  const [tickets, setTickets] = useState<SupportTicketSummary[]>([])
  const [query, setQuery] = useState('')
  const [progressFilter, setProgressFilter] = useState<'all' | TicketProgressState>('all')
  const [departmentFilter, setDepartmentFilter] = useState<'all' | TicketDepartment>('all')
  const [priorityFilter, setPriorityFilter] = useState<'all' | TicketPriority>('all')
  const [error, setError] = useState('')
  const [nowMs, setNowMs] = useState(() => Date.now())

  useEffect(() => {
    void apiFetch<SupportTicketSummary[]>('/tickets').then(setTickets).catch(err => setError(err instanceof Error ? err.message : 'Could not load tickets'))
  }, [])

  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 60_000)
    return () => window.clearInterval(timer)
  }, [])

  const filtered = useMemo(() => {
    const text = query.trim().toLowerCase()
    return tickets.filter(ticket => {
      if (progressFilter !== 'all' && ticketProgressFromStatus(ticket.status) !== progressFilter) return false
      if (departmentFilter !== 'all' && ticket.department !== departmentFilter) return false
      if (priorityFilter !== 'all' && ticket.priority !== priorityFilter) return false
      if (!text) return true
      return [
        ticket.ticket_code,
        ticket.title,
        ticket.requester_name,
        ticket.requester_email,
        ticket.branch_name,
        ticket.department,
        ticket.asset_number || '',
        ticket.component || '',
        ticket.problem_label || '',
      ].some(value => value.toLowerCase().includes(text))
    })
  }, [departmentFilter, priorityFilter, progressFilter, query, tickets])

  const softwareView = user?.role === 'software_team'
  const managementView = user?.role === 'management'
  const oversightView = softwareView || managementView
  const employeeView = user?.role === 'employee'
  const title = oversightView ? 'All Department Tickets' : employeeView ? 'My Support Tickets' : `${user?.role === 'it' ? 'IT' : 'Drone'} Ticket Queue`
  const description = managementView
    ? 'Read-only oversight of every department ticket. The responsible department retains all handling actions.'
    : softwareView
      ? 'Read-only monitoring for other departments and full handling access for Software Team tickets.'
      : employeeView
        ? 'Track whether your issue is waiting, ongoing, or completed.'
        : 'Simple work status: red is not started, yellow is ongoing, and green is completed. Priority remains visible for queue urgency.'

  return <>
    <DashboardHeader eyebrow="TICKET OPERATIONS" title={title} description={description} />
    <section className="panel-card ticket-list-panel ticket-simple-list-panel">
      <div className="ticket-list-toolbar">
        <label className="ticket-search"><Search size={17} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search ticket, employee, asset tag, component, or issue" /></label>
        <label><Filter size={16} /><select value={priorityFilter} onChange={event => setPriorityFilter(event.target.value as 'all' | TicketPriority)}><option value="all">All priorities</option><option value="critical">Critical</option><option value="high">High</option><option value="medium">Moderate</option><option value="low">Low</option></select></label>
        <label><Filter size={16} /><select value={progressFilter} onChange={event => setProgressFilter(event.target.value as 'all' | TicketProgressState)}><option value="all">All work statuses</option><option value="not_started">Not Started</option><option value="ongoing">Ongoing</option><option value="completed">Completed</option></select></label>
        {oversightView && <label><Filter size={16} /><select value={departmentFilter} onChange={event => setDepartmentFilter(event.target.value as 'all' | TicketDepartment)}><option value="all">All departments</option><option value="it">IT</option><option value="drone">Drone</option><option value="software_team">Software Team</option><option value="management">Management</option></select></label>}
        {employeeView && <Link className="primary-button" to="/support/new">Raise Ticket</Link>}
      </div>
      {error && <div className="error-message">{error}</div>}
      {filtered.length === 0 ? <div className="empty-state"><TicketCheck size={30} /><span>No tickets match the current filters.</span></div> : <div className="table-wrap"><table className="data-table ticket-table ticket-priority-queue ticket-progress-queue"><thead><tr>{!employeeView && <th>Queue #</th>}<th>Ticket</th>{!employeeView && <th>Raised By</th>}<th>Asset / Component</th><th>Priority</th><th>Work Status</th>{!employeeView && <th>SLA</th>}<th>Raised At</th><th>Waiting / Resolution</th><th>Branch</th><th>Updated At</th></tr></thead><tbody>{filtered.map(ticket => {
        const duration = durationState(ticket, nowMs)
        const sla = ticketSlaDisplay(ticket, nowMs)
        const progress = ticketProgressFromStatus(ticket.status)
        return <tr key={ticket.id} className={`ticket-queue-row progress-row-${progress} ${!employeeView ? `sla-row-${sla.state}` : ''}`}>
          {!employeeView && <td className="ticket-queue-position"><strong>#{ticket.queue_position ?? '—'}</strong></td>}
          <td><Link to={`/tickets/${ticket.id}`}><strong>{ticket.ticket_code}</strong><small>{ticket.title}</small></Link></td>
          {!employeeView && <td><strong>{ticket.requester_name}</strong><small>{ticket.requester_email}</small></td>}
          <td><strong>{ticket.asset_number || 'No asset'}</strong><small>{ticket.problem_label || ticket.category || departmentLabels[ticket.department]}</small>{ticket.component_asset_tag && ticket.component_asset_tag !== ticket.asset_number && <small>Component tag: {ticket.component_asset_tag}</small>}</td>
          <td><span className={`ticket-priority priority-${ticket.priority}`}>{priorityLabel(ticket.priority)}</span><small>{slaLabel(ticket.sla_target_minutes)}</small></td>
          <td><span className={`ticket-progress-pill progress-${progress}`}><i />{ticketProgressShortLabel(ticket.status)}</span></td>
          {!employeeView && <td className="ticket-sla-cell"><span className={`ticket-sla-badge sla-${sla.state}`}>{sla.label}</span><small>{sla.value}</small></td>}
          <td className="ticket-time-cell"><strong>{formatStandardDateTime(ticket.created_at)}</strong></td>
          <td><strong>{duration.value}</strong><small>{duration.label}</small></td>
          <td>{ticket.branch_name}</td>
          <td className="ticket-time-cell"><strong>{formatStandardDateTime(ticket.updated_at)}</strong></td>
        </tr>
      })}</tbody></table></div>}
    </section>
  </>
}
