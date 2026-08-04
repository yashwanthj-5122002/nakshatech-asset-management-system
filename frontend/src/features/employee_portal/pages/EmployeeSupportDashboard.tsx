import { Bell, CheckCircle2, Clock3, LifeBuoy, MessageSquarePlus, TicketCheck } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { StatCard } from '../../../components/StatCard'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch } from '../../../lib/api'
import type { SupportTicketSummary, TicketNotification } from '../../../types'

export function EmployeeSupportDashboard() {
  const { user } = useAuth()
  const [tickets, setTickets] = useState<SupportTicketSummary[]>([])
  const [notifications, setNotifications] = useState<TicketNotification[]>([])
  useEffect(() => {
    void Promise.all([
      apiFetch<SupportTicketSummary[]>('/tickets'),
      apiFetch<TicketNotification[]>('/notifications'),
    ]).then(([ticketItems, notificationItems]) => {
      setTickets(ticketItems); setNotifications(notificationItems)
    })
  }, [])
  const open = useMemo(() => tickets.filter(ticket => !['resolved', 'closed'].includes(ticket.status)).length, [tickets])
  const resolved = useMemo(() => tickets.filter(ticket => ['resolved', 'closed'].includes(ticket.status)).length, [tickets])
  const unread = notifications.filter(item => !item.is_read).length
  return (
    <>
      <DashboardHeader eyebrow="EMPLOYEE SUPPORT" title="Support & Ticket Workspace" description={`Raise an issue for IT, Drone, Software, or Management. Current branch: ${user?.selected_branch_name || user?.branch || 'Not selected'}.`} />
      <section className="stats-grid">
        <StatCard icon={TicketCheck} label="My Tickets" value={tickets.length} />
        <StatCard icon={Clock3} label="Open" value={open} tone="orange" />
        <StatCard icon={CheckCircle2} label="Resolved" value={resolved} tone="green" />
        <StatCard icon={Bell} label="Unread Updates" value={unread} tone="cyan" />
      </section>
      <section className="support-action-grid">
        <Link className="support-action-card primary" to="/support/new"><MessageSquarePlus /><div><span>START HERE</span><h2>Raise a New Ticket</h2><p>Select the responsible department, explain the problem, and track the response.</p></div></Link>
        <Link className="support-action-card" to="/tickets"><LifeBuoy /><div><span>TRACK PROGRESS</span><h2>My Tickets</h2><p>Read department replies, provide updates, and confirm whether an issue is resolved.</p></div></Link>
      </section>
      <section className="panel-card support-recent-panel">
        <div className="section-heading"><div><span className="section-kicker">RECENT ACTIVITY</span><h2>Latest tickets</h2></div><Link to="/tickets">View all</Link></div>
        {tickets.length === 0 ? <div className="empty-state">No tickets have been raised yet.</div> : <div className="support-ticket-list">{tickets.slice(0, 5).map(ticket => <Link key={ticket.id} to={`/tickets/${ticket.id}`} className="support-ticket-row"><div><strong>{ticket.ticket_code} · {ticket.title}</strong><span>{ticket.department.replace('_', ' ')} · {ticket.branch_name}</span></div><span className={`ticket-status status-${ticket.status}`}>{ticket.status.replaceAll('_', ' ')}</span></Link>)}</div>}
      </section>
    </>
  )
}
