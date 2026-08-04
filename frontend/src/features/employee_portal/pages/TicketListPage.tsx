import { Filter, Search, TicketCheck } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch } from '../../../lib/api'
import type { SupportTicketSummary, TicketDepartment, TicketStatus } from '../../../types'

const departmentLabels: Record<TicketDepartment, string> = {
  it: 'IT Department',
  drone: 'Drone Department',
  software_team: 'Software Team',
  management: 'Management',
}

export function TicketListPage() {
  const { user } = useAuth()
  const [tickets, setTickets] = useState<SupportTicketSummary[]>([])
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | TicketStatus>('all')
  const [departmentFilter, setDepartmentFilter] = useState<'all' | TicketDepartment>('all')
  const [error, setError] = useState('')

  useEffect(() => {
    void apiFetch<SupportTicketSummary[]>('/tickets').then(setTickets).catch(err => setError(err instanceof Error ? err.message : 'Could not load tickets'))
  }, [])

  const filtered = useMemo(() => {
    const text = query.trim().toLowerCase()
    return tickets.filter(ticket => {
      if (statusFilter !== 'all' && ticket.status !== statusFilter) return false
      if (departmentFilter !== 'all' && ticket.department !== departmentFilter) return false
      if (!text) return true
      return [ticket.ticket_code, ticket.title, ticket.requester_name, ticket.requester_email, ticket.branch_name, ticket.department]
        .some(value => value.toLowerCase().includes(text))
    })
  }, [tickets, query, statusFilter, departmentFilter])

  const softwareView = user?.role === 'software_team'
  const employeeView = user?.role === 'employee'
  const title = softwareView ? 'All Department Tickets' : employeeView ? 'My Support Tickets' : `${user?.role === 'it' ? 'IT' : user?.role === 'drone' ? 'Drone' : 'Management'} Ticket Queue`
  const description = softwareView
    ? 'Read-only monitoring for other departments and full handling access for Software Team tickets.'
    : employeeView
      ? 'Track department replies, ticket status, and resolution history.'
      : 'Only tickets routed to your department are visible and actionable.'

  return <>
    <DashboardHeader eyebrow="TICKET OPERATIONS" title={title} description={description} />
    <section className="panel-card ticket-list-panel">
      <div className="ticket-list-toolbar">
        <label className="ticket-search"><Search size={17} /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search ticket, employee, branch, or issue" /></label>
        <label><Filter size={16} /><select value={statusFilter} onChange={e => setStatusFilter(e.target.value as 'all' | TicketStatus)}><option value="all">All statuses</option><option value="new">New</option><option value="assigned">Assigned</option><option value="in_progress">In Progress</option><option value="waiting_for_employee">Waiting for Employee</option><option value="resolved">Resolved</option><option value="closed">Closed</option><option value="reopened">Reopened</option></select></label>
        {softwareView && <label><Filter size={16} /><select value={departmentFilter} onChange={e => setDepartmentFilter(e.target.value as 'all' | TicketDepartment)}><option value="all">All departments</option><option value="it">IT</option><option value="drone">Drone</option><option value="software_team">Software Team</option><option value="management">Management</option></select></label>}
        {employeeView && <Link className="primary-button" to="/support/new">Raise Ticket</Link>}
      </div>
      {error && <div className="error-message">{error}</div>}
      {filtered.length === 0 ? <div className="empty-state"><TicketCheck size={30} /><span>No tickets match the current filters.</span></div> : <div className="table-wrap"><table className="data-table ticket-table"><thead><tr><th>Ticket</th>{!employeeView && <th>Raised By</th>}<th>Department</th><th>Branch</th><th>Priority</th><th>Status</th><th>Updated</th></tr></thead><tbody>{filtered.map(ticket => <tr key={ticket.id}><td><Link to={`/tickets/${ticket.id}`}><strong>{ticket.ticket_code}</strong><small>{ticket.title}</small></Link></td>{!employeeView && <td><strong>{ticket.requester_name}</strong><small>{ticket.requester_email}</small></td>}<td>{departmentLabels[ticket.department]}</td><td>{ticket.branch_name}</td><td><span className={`ticket-priority priority-${ticket.priority}`}>{ticket.priority}</span></td><td><span className={`ticket-status status-${ticket.status}`}>{ticket.status.replaceAll('_', ' ')}</span></td><td>{new Date(ticket.updated_at).toLocaleString()}</td></tr>)}</tbody></table></div>}
    </section>
  </>
}
