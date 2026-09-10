import { Building2, CalendarDays, CheckCircle2, CircleDollarSign, Clock3, FileCheck2, FileSpreadsheet, IndianRupee, ReceiptIndianRupee } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch } from '../../../lib/api'
import type { FinanceBreakdownItem, FinanceDashboard, FinanceProject } from '../../../types'
import { financeClaimTypeLabels, financeStatusLabels, financeStatusTone, formatInr } from '../finance-utils'
import '../finance-expenses.css'

function BreakdownPanel({ title, subtitle, items }: { title: string; subtitle: string; items: FinanceBreakdownItem[] }) {
  const max = useMemo(() => Math.max(1, ...items.map(item => item.amount)), [items])
  return (
    <article className="finance-panel">
      <div className="finance-panel-header"><div><span className="finance-panel-kicker">ANALYTICS</span><h2>{title}</h2><p>{subtitle}</p></div></div>
      {items.length === 0 ? <div className="finance-empty-state">No financial activity yet.</div> : (
        <div className="finance-breakdown-list">
          {items.slice(0, 8).map(item => (
            <div className="finance-breakdown-row" key={item.key}>
              <div><span>{item.label}</span><span>{formatInr(item.amount)} · {item.count}</span></div>
              <div className="finance-breakdown-track"><i style={{ width: `${Math.max(4, (item.amount / max) * 100)}%` }} /></div>
            </div>
          ))}
        </div>
      )}
    </article>
  )
}

export function FinanceDashboardPage() {
  const { user } = useAuth()
  const [data, setData] = useState<FinanceDashboard | null>(null)
  const [projects, setProjects] = useState<FinanceProject[]>([])
  const [projectSaving, setProjectSaving] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  function load() {
    setLoading(true)
    setError('')
    void Promise.all([apiFetch<FinanceDashboard>('/finance/dashboard'), apiFetch<FinanceProject[]>('/finance/report-projects')])
      .then(([dashboard, projectRows]) => { setData(dashboard); setProjects(projectRows) })
      .catch(err => setError(err instanceof Error ? err.message : 'Could not load Finance dashboard'))
      .finally(() => setLoading(false))
  }

  function updateProjectLocal(id: number, patch: Partial<FinanceProject>) {
    setProjects(current => current.map(project => project.id === id ? { ...project, ...patch } : project))
  }

  async function saveProjectSchedule(project: FinanceProject) {
    if (user?.role === 'management') return
    if (!project.start_date || !project.end_date) { setError('Set both project start and end dates.'); return }
    setProjectSaving(project.id); setError('')
    try {
      const updated = await apiFetch<FinanceProject>(`/finance/projects/${project.id}/schedule`, { method: 'PUT', body: JSON.stringify({ start_date: project.start_date, end_date: project.end_date, is_active: project.is_active }) })
      updateProjectLocal(project.id, updated)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not update project timeline') } finally { setProjectSaving(null) }
  }

  useEffect(load, [])

  return (
    <div className="finance-page">
      <DashboardHeader
        eyebrow="FINANCE CRM"
        title={user?.role === 'management' ? 'Project Expense Intelligence' : 'Finance & Project Expense Dashboard'}
        description={user?.role === 'management'
          ? 'Read-only management visibility across project expenses, advances, reimbursements, approvals, and settlement status.'
          : user?.role === 'admin'
            ? 'Verify employee project-expense requests before Finance performs the financial approval and payment stage.'
            : 'Review Admin-verified project expenses, approve legitimate requests, record payments, and monitor project spend.'}
        actions={<div className="finance-header-actions"><Link className="finance-secondary-button" to="/finance/clients"><Building2 size={16} /> Client Management</Link><Link className="finance-secondary-button" to="/finance/reports"><FileSpreadsheet size={16} /> Reports & Excel</Link><Link className="finance-primary-button" to="/finance/claims"><FileCheck2 size={16} /> Expense Claims & Approvals</Link></div>}
      />

      {error && <div className="finance-error">{error} <button type="button" className="finance-inline-link" onClick={load}>Retry</button></div>}
      {loading && <div className="finance-panel finance-empty-state">Loading Finance dashboard...</div>}

      {data && (
        <>
          <section className="finance-kpi-grid finance-kpi-grid-4">
            <article className="finance-kpi-card"><span><ReceiptIndianRupee size={15} /> Total Requested</span><strong>{formatInr(data.total_requested_amount)}</strong><small>{data.total_claims} project-linked claim(s)</small></article>
            <article className="finance-kpi-card"><span><Clock3 size={15} /> Pending Admin</span><strong>{data.pending_admin_count}</strong><small>{formatInr(data.pending_admin_amount)} awaiting legitimacy check</small></article>
            <article className="finance-kpi-card"><span><CheckCircle2 size={15} /> Pending Finance</span><strong>{data.pending_finance_count}</strong><small>{formatInr(data.pending_finance_amount)} Admin-verified</small></article>
            <article className="finance-kpi-card"><span><IndianRupee size={15} /> Paid / Released</span><strong>{formatInr(data.paid_amount)}</strong><small>{data.paid_count} claim payment(s) recorded</small></article>
          </section>

          <section className="finance-kpi-grid finance-kpi-grid-4 finance-kpi-grid-secondary">
            <article className="finance-kpi-card"><span><ReceiptIndianRupee size={15} /> Finance Approved</span><strong>{formatInr(data.approved_amount)}</strong><small>{data.approved_count} approved / payment-stage claim(s)</small></article>
            <article className="finance-kpi-card"><span><CircleDollarSign size={15} /> Outstanding</span><strong>{formatInr(data.outstanding_amount)}</strong><small>{data.partially_paid_count} partially paid claim(s)</small></article>
            <article className="finance-kpi-card"><span><FileCheck2 size={15} /> Sent Back / Rejected</span><strong>{data.sent_back_count + data.rejected_count}</strong><small>{data.sent_back_count} sent back · {data.rejected_count} rejected</small></article>
            <article className="finance-kpi-card"><span>Control</span><strong>{user?.role === 'management' ? 'Read Only' : user?.role === 'admin' ? 'Admin Verify' : 'Finance Approve'}</strong><small>Role-scoped financial authority</small></article>
          </section>

          <section className="finance-kpi-grid finance-kpi-grid-4 finance-kpi-grid-secondary">
            <article className="finance-kpi-card"><span><Clock3 size={15} /> Pending Settlement</span><strong>{data.pending_settlement_count}</strong><small>Released advances not yet finally settled</small></article>
            <article className="finance-kpi-card"><span><Clock3 size={15} /> Overdue Settlement</span><strong>{data.overdue_settlement_count}</strong><small>Past the Finance-approved settlement due date</small></article>
            <article className="finance-kpi-card"><span><FileCheck2 size={15} /> Settlement Review</span><strong>{data.settlement_under_review_count}</strong><small>Submitted / Admin-approved settlement(s)</small></article>
            <article className="finance-kpi-card"><span><CheckCircle2 size={15} /> Finalized Settlement</span><strong>{data.settled_count}</strong><small>Tallied, balance or shortage finalized by Finance</small></article>
          </section>

          <section className="finance-panel">
            <div className="finance-panel-header"><div><span className="finance-panel-kicker">CLIENT PROJECT MASTER</span><h2>Project Timeline Control</h2><p>Client Management is now the master source for Client IDs, Project IDs, project dates and project status. These quick controls update the same project records used by Employee Project Expense selection.</p></div><div className="finance-header-actions"><CalendarDays size={20} /><Link className="finance-secondary-button" to="/finance/clients"><Building2 size={16} /> Manage Clients & Projects</Link></div></div>
            <div className="finance-table-wrap"><table className="finance-table"><thead><tr><th>Project</th><th>Client</th><th>Start Date</th><th>End Date</th><th>Enabled</th><th>Status</th><th>Action</th></tr></thead><tbody>{projects.map(project => <tr key={project.id}><td><strong>{project.project_code}</strong><br/><small>{project.project_name}</small></td><td><strong>{project.client_code || 'Legacy'}</strong><br/><small>{project.client_name || 'Client not linked'}</small></td><td><input className="finance-inline-date" type="date" disabled={user?.role === 'management'} value={project.start_date || ''} onChange={event => updateProjectLocal(project.id,{start_date:event.target.value})}/></td><td><input className="finance-inline-date" type="date" disabled={user?.role === 'management'} value={project.end_date || ''} onChange={event => updateProjectLocal(project.id,{end_date:event.target.value})}/></td><td><input type="checkbox" disabled={user?.role === 'management'} checked={project.is_active} onChange={event => updateProjectLocal(project.id,{is_active:event.target.checked})}/></td><td>{project.lifecycle_status.replaceAll('_',' ')}</td><td>{user?.role === 'management' ? 'Read only' : <button className="finance-secondary-button" type="button" disabled={projectSaving === project.id} onClick={() => void saveProjectSchedule(project)}>{projectSaving === project.id ? 'Saving...' : 'Save Dates'}</button>}</td></tr>)}</tbody></table></div>
          </section>

          <section className="finance-breakdown-grid">
            <BreakdownPanel title="Project-wise Spend" subtitle="Requested amount grouped by Project ID." items={data.by_project} />
            <BreakdownPanel title="Request Type Mix" subtitle="Advance, reimbursement, and additional-advance exposure." items={data.by_type.map(item => ({ ...item, label: financeClaimTypeLabels[item.key as keyof typeof financeClaimTypeLabels] || item.label }))} />
            <BreakdownPanel title="Category-wise Spend" subtitle="Where project money is being requested or reimbursed." items={data.by_category} />
          </section>

          <section className="finance-panel">
            <div className="finance-panel-header">
              <div><span className="finance-panel-kicker">LIVE WORKFLOW</span><h2>Recent Expense Claims</h2><p>Latest employee submissions and their current Admin → Finance → Payment → Settlement state.</p></div>
              <Link className="finance-secondary-button" to="/finance/claims">View All</Link>
            </div>
            {data.recent_claims.length === 0 ? <div className="finance-empty-state">No project expense claims have been raised yet.</div> : (
              <div className="finance-table-wrap"><table className="finance-table">
                <thead><tr><th>Claim</th><th>Employee</th><th>Project</th><th>Type</th><th>Amount</th><th>Status</th><th>Submitted</th></tr></thead>
                <tbody>{data.recent_claims.map(claim => (
                  <tr key={claim.id}>
                    <td><Link to={`/finance/claims/${claim.id}`}>{claim.claim_code}</Link></td>
                    <td><strong>{claim.requester_name}</strong><br /><small>{claim.requester_email}</small></td>
                    <td>{claim.project.project_code}<br /><small>{claim.project.project_name}</small></td>
                    <td>{financeClaimTypeLabels[claim.claim_type]}</td>
                    <td><strong>{formatInr(claim.total_amount)}</strong></td>
                    <td><span className={`finance-status tone-${financeStatusTone(claim.status)}`}>{financeStatusLabels[claim.status]}</span></td>
                    <td>{claim.submitted_at ? new Date(claim.submitted_at).toLocaleDateString('en-IN') : 'Draft'}</td>
                  </tr>
                ))}</tbody>
              </table></div>
            )}
          </section>
        </>
      )}
    </div>
  )
}
