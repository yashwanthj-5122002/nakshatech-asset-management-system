import { Bell, CheckCircle2, Clock3, FilePlus2, LifeBuoy, MessageSquarePlus, ReceiptIndianRupee, TicketCheck } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { StatCard } from '../../../components/StatCard'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch } from '../../../lib/api'
import type { ExpenseClaim, SupportTicketSummary, TicketNotification } from '../../../types'
import { financeClaimTypeLabels, financeStatusLabels, financeStatusTone, formatInr } from '../../finance/finance-utils'
import '../../finance/finance-expenses.css'
import { ticketProgressFromStatus, ticketProgressShortLabel } from '../ticketProgress'

export function EmployeeSupportDashboard() {
  const { user } = useAuth()
  const [tickets, setTickets] = useState<SupportTicketSummary[]>([])
  const [notifications, setNotifications] = useState<TicketNotification[]>([])
  const [expenseClaims, setExpenseClaims] = useState<ExpenseClaim[]>([])
  const [financeAvailable, setFinanceAvailable] = useState(true)

  useEffect(() => {
    void Promise.all([
      apiFetch<SupportTicketSummary[]>('/tickets'),
      apiFetch<TicketNotification[]>('/notifications'),
    ]).then(([ticketItems, notificationItems]) => {
      setTickets(ticketItems); setNotifications(notificationItems)
    })
  }, [])

  // Finance intentionally loads independently. A Finance CRM issue must never
  // block or blank the existing ticket workspace.
  useEffect(() => {
    void apiFetch<ExpenseClaim[]>('/finance/claims')
      .then(items => { setExpenseClaims(items); setFinanceAvailable(true) })
      .catch(() => setFinanceAvailable(false))
  }, [])

  const open = useMemo(() => tickets.filter(ticket => !['resolved', 'closed'].includes(ticket.status)).length, [tickets])
  const resolved = useMemo(() => tickets.filter(ticket => ['resolved', 'closed'].includes(ticket.status)).length, [tickets])
  const unread = notifications.filter(item => !item.is_read).length
  const expenseInApproval = expenseClaims.filter(claim => ['submitted', 'admin_approved'].includes(claim.status)).length
  const expensePaid = expenseClaims.filter(claim => claim.status === 'paid').reduce((sum, claim) => sum + (claim.paid_amount || 0), 0)

  return (
    <>
      <DashboardHeader eyebrow="EMPLOYEE SUPPORT" title="Support & Project Expense Workspace" description={`Raise support tickets and project-linked expense requests. Current branch: ${user?.selected_branch_name || user?.branch || 'Not selected'}.`} />
      <section className="stats-grid">
        <StatCard icon={TicketCheck} label="My Tickets" value={tickets.length} />
        <StatCard icon={Clock3} label="Open" value={open} tone="orange" />
        <StatCard icon={CheckCircle2} label="Completed" value={resolved} tone="green" />
        <StatCard icon={Bell} label="Unread Updates" value={unread} tone="cyan" />
      </section>

      <section className="support-action-grid">
        <Link className="support-action-card primary" to="/support/new"><MessageSquarePlus /><div><span>IT / DEPARTMENT SUPPORT</span><h2>Raise a New Ticket</h2><p>Select the responsible department, explain the problem, and track the response.</p></div></Link>
        <Link className="support-action-card" to="/tickets"><LifeBuoy /><div><span>TRACK SUPPORT</span><h2>My Tickets</h2><p>Read department replies, provide updates, and confirm whether an issue is resolved.</p></div></Link>
        <Link className="support-action-card finance-support-card" to="/expenses/new"><FilePlus2 /><div><span>PROJECT FINANCE</span><h2>Raise Project Expense</h2><p>Select Project ID and raise an Advance, Reimbursement, or Additional Advance request.</p></div></Link>
        <Link className="support-action-card finance-support-card" to="/expenses"><ReceiptIndianRupee /><div><span>TRACK FINANCE</span><h2>My Expense Claims</h2><p>{financeAvailable ? `${expenseClaims.length} claim(s) · ${expenseInApproval} in approval · ${formatInr(expensePaid)} paid` : 'Open your project expense claims and approval status.'}</p></div></Link>
      </section>

      <section className="panel-card support-recent-panel">
        <div className="section-heading"><div><span className="section-kicker">RECENT SUPPORT ACTIVITY</span><h2>Latest tickets</h2></div><Link to="/tickets">View all</Link></div>
        {tickets.length === 0 ? <div className="empty-state">No tickets have been raised yet.</div> : <div className="support-ticket-list">{tickets.slice(0, 5).map(ticket => { const progress = ticketProgressFromStatus(ticket.status); return <Link key={ticket.id} to={`/tickets/${ticket.id}`} className="support-ticket-row"><div><strong>{ticket.ticket_code} · {ticket.title}</strong><span>{ticket.department.replace('_', ' ')} · {ticket.branch_name}</span></div><span className={`ticket-progress-pill progress-${progress}`}><i />{ticketProgressShortLabel(ticket.status)}</span></Link> })}</div>}
      </section>

      {financeAvailable && (
        <section className="panel-card support-recent-panel employee-finance-recent">
          <div className="section-heading"><div><span className="section-kicker">RECENT PROJECT EXPENSES</span><h2>Latest claims</h2></div><Link to="/expenses">View all</Link></div>
          {expenseClaims.length === 0 ? <div className="empty-state">No project expense claims have been raised yet.</div> : (
            <div className="support-ticket-list">{expenseClaims.slice(0, 5).map(claim => (
              <Link key={claim.id} to={`/expenses/${claim.id}`} className="support-ticket-row">
                <div><strong>{claim.claim_code} · {claim.project.project_code}</strong><span>{financeClaimTypeLabels[claim.claim_type]} · {formatInr(claim.total_amount)}</span></div>
                <span className={`finance-status tone-${financeStatusTone(claim.status)}`}>{financeStatusLabels[claim.status]}</span>
              </Link>
            ))}</div>
          )}
        </section>
      )}
    </>
  )
}
