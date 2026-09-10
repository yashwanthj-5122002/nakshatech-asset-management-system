import { AlertTriangle, Search, SlidersHorizontal } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch } from '../../../lib/api'
import type { ExpenseClaim, FinanceClaimStatus, FinanceClaimType } from '../../../types'
import { financeClaimTypeLabels, financeStatusLabels, financeStatusTone, formatInr } from '../finance-utils'
import '../finance-expenses.css'

export function FinanceClaimsPage() {
  const { user } = useAuth()
  const [claims, setClaims] = useState<ExpenseClaim[]>([])
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | FinanceClaimStatus>(() => user?.role === 'admin' ? 'submitted' : user?.role === 'finance' ? 'admin_approved' : 'all')
  const [typeFilter, setTypeFilter] = useState<'all' | FinanceClaimType>('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  function load() { setLoading(true); setError(''); void apiFetch<ExpenseClaim[]>('/finance/claims').then(setClaims).catch(err => setError(err instanceof Error ? err.message : 'Could not load expense claims')).finally(() => setLoading(false)) }
  useEffect(load, [])

  const settlementQueue = useMemo(() => claims.filter(claim => {
    const status = claim.settlement?.status
    if (!status) return false
    if (user?.role === 'admin') return status === 'submitted'
    if (user?.role === 'finance') return status === 'admin_approved'
    if (user?.role === 'management') return status !== 'draft'
    return false
  }), [claims, user?.role])

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return claims.filter(claim => {
      if (statusFilter !== 'all' && claim.status !== statusFilter) return false
      if (typeFilter !== 'all' && claim.claim_type !== typeFilter) return false
      if (!needle) return true
      return [claim.claim_code, claim.requester_name, claim.requester_email, claim.project.project_code, claim.project.project_name, claim.purpose_description].some(value => value.toLowerCase().includes(needle))
    })
  }, [claims, query, statusFilter, typeFilter])

  const actionLabel = user?.role === 'management' ? 'Management read-only review' : user?.role === 'admin' ? 'Admin verification queue' : 'Finance verification, payment & settlement queue'
  const emptyMessage = user?.role === 'admin' && statusFilter === 'submitted' ? 'No new claims are waiting for Admin verification.' : user?.role === 'finance' && statusFilter === 'admin_approved' ? 'No new claims are waiting for Finance verification.' : 'No claims match the selected filters.'
  const reviewLabel = user?.role === 'admin' ? 'Review / Approve' : user?.role === 'finance' ? 'Finance Review' : 'View Claim'

  return <div className="finance-page">
    <DashboardHeader eyebrow="FINANCE CRM" title="Expense Claims & Settlements" description={`${actionLabel}. Original requests, payments, final bills and settlement history remain linked to the same Project ID.`} />

    {(user?.role === 'admin' || user?.role === 'finance' || user?.role === 'management') && <section className="finance-panel">
      <div className="finance-panel-header"><div><span className="finance-panel-kicker">ADVANCE SETTLEMENT QUEUE</span><h2>{user?.role === 'admin' ? 'Waiting for Admin bill verification' : user?.role === 'finance' ? 'Waiting for Finance final settlement' : 'Settlement activity'}</h2><p>These are post-work settlements against advances already released by the organization.</p></div>{settlementQueue.some(c => c.settlement_overdue) && <span className="finance-status tone-danger"><AlertTriangle size={14}/> Overdue exists</span>}</div>
      {settlementQueue.length === 0 ? <div className="finance-empty-state">No settlements are waiting at this stage.</div> : <div className="finance-table-wrap"><table className="finance-table"><thead><tr><th>Settlement</th><th>Employee</th><th>Project</th><th>Advance Received</th><th>Actual Bills</th><th>Tally</th><th>Due</th><th>Action</th></tr></thead><tbody>{settlementQueue.map(claim => <tr key={`set-${claim.id}`}><td><strong>{claim.settlement!.settlement_code}</strong><br/><small>{claim.claim_code}</small></td><td>{claim.requester_name}</td><td>{claim.project.project_code}</td><td><strong>{formatInr(claim.settlement!.total_advance_received)}</strong></td><td><strong>{formatInr(claim.settlement!.total_expense_amount)}</strong><br/><small>{claim.settlement!.attachments.length} bill(s)</small></td><td>{claim.settlement!.tally_status.replaceAll('_',' ')}</td><td>{claim.settlement_due_date || '—'}{claim.settlement_overdue && <><br/><small className="finance-danger-text">OVERDUE</small></>}</td><td><Link className="finance-primary-button" to={`/finance/claims/${claim.id}`}>{user?.role === 'management' ? 'View' : 'Verify Settlement'}</Link></td></tr>)}</tbody></table></div>}
    </section>}

    <section className="finance-panel"><div className="finance-toolbar finance-filter-toolbar"><label className="finance-search"><Search size={16}/><input value={query} onChange={event=>setQuery(event.target.value)} placeholder="Search claim, employee, Project ID..."/></label><div className="finance-filter-group"><SlidersHorizontal size={15}/><select value={statusFilter} onChange={event=>setStatusFilter(event.target.value as 'all'|FinanceClaimStatus)}><option value="all">All statuses</option>{Object.entries(financeStatusLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select><select value={typeFilter} onChange={event=>setTypeFilter(event.target.value as 'all'|FinanceClaimType)}><option value="all">All request types</option>{Object.entries(financeClaimTypeLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></div></div>
      {error && <div className="finance-error">{error} <button type="button" className="finance-inline-link" onClick={load}>Retry</button></div>}
      {loading ? <div className="finance-empty-state">Loading claims...</div> : visible.length===0 ? <div className="finance-empty-state">{emptyMessage}</div> : <div className="finance-table-wrap"><table className="finance-table"><thead><tr><th>Claim</th><th>Employee</th><th>Project</th><th>Request Type</th><th>Amount</th><th>Status</th><th>Settlement</th><th>Proof</th><th>Action</th></tr></thead><tbody>{visible.map(claim=><tr key={claim.id}><td><Link to={`/finance/claims/${claim.id}`}>{claim.claim_code}</Link></td><td><strong>{claim.requester_name}</strong><br/><small>{claim.requester_email}</small></td><td><strong>{claim.project.project_code}</strong><br/><small>{claim.project.project_name}</small></td><td>{financeClaimTypeLabels[claim.claim_type]}</td><td><strong>{formatInr(claim.total_amount)}</strong></td><td><span className={`finance-status tone-${financeStatusTone(claim.status)}`}>{financeStatusLabels[claim.status]}</span></td><td>{claim.claim_type === 'advance' ? claim.settlement_status.replaceAll('_',' ') : '—'}</td><td>{claim.attachments.length + (claim.settlement?.attachments.length || 0)} file(s)</td><td><Link className="finance-secondary-button" to={`/finance/claims/${claim.id}`}>{reviewLabel}</Link></td></tr>)}</tbody></table></div>}
    </section>
  </div>
}
