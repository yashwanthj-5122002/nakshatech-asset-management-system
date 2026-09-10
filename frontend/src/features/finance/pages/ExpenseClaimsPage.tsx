import { FilePlus2, ReceiptText, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import type { ExpenseClaim, FinanceClaimStatus, FinanceClaimType } from '../../../types'
import { financeClaimTypeLabels, financeClaimTypeTone, financeStatusLabels, financeStatusTone, formatInr } from '../finance-utils'
import '../finance-expenses.css'

export function ExpenseClaimsPage() {
  const [claims, setClaims] = useState<ExpenseClaim[]>([])
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | FinanceClaimStatus>('all')
  const [typeFilter, setTypeFilter] = useState<'all' | FinanceClaimType>('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  function load() {
    setLoading(true)
    setError('')
    void apiFetch<ExpenseClaim[]>('/finance/claims')
      .then(setClaims)
      .catch(err => setError(err instanceof Error ? err.message : 'Could not load expense claims'))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return claims.filter(claim => {
      if (statusFilter !== 'all' && claim.status !== statusFilter) return false
      if (typeFilter !== 'all' && claim.claim_type !== typeFilter) return false
      if (!needle) return true
      return [claim.claim_code, claim.project.project_code, claim.project.project_name, claim.purpose_description]
        .some(value => value.toLowerCase().includes(needle))
    })
  }, [claims, query, statusFilter, typeFilter])

  const pending = claims.filter(claim => ['submitted', 'admin_approved'].includes(claim.status)).length
  const approved = claims.filter(claim => ['finance_approved', 'partially_paid', 'paid'].includes(claim.status)).length
  const paid = claims.filter(claim => claim.status === 'paid').reduce((sum, claim) => sum + (claim.paid_amount || 0), 0)

  return (
    <div className="finance-page">
      <DashboardHeader
        eyebrow="MY PROJECT EXPENSES"
        title="Expense Claims"
        description="Track every Advance, Reimbursement, and Additional Advance request from submission through Admin and Finance approval."
        actions={<Link className="finance-primary-button" to="/expenses/new"><FilePlus2 size={16} /> New Claim</Link>}
      />

      <section className="finance-kpi-grid">
        <article className="finance-kpi-card"><span>Total Claims</span><strong>{claims.length}</strong><small>All project-linked requests</small></article>
        <article className="finance-kpi-card"><span>In Approval</span><strong>{pending}</strong><small>Admin or Finance review pending</small></article>
        <article className="finance-kpi-card"><span>Approved</span><strong>{approved}</strong><small>Finance-approved or settled</small></article>
        <article className="finance-kpi-card"><span>Paid / Released</span><strong>{formatInr(paid)}</strong><small>Actual payment recorded by Finance</small></article>
      </section>

      <section className="finance-panel">
        <div className="finance-panel-header">
          <div><span className="finance-panel-kicker">CLAIM REGISTER</span><h2>My project expense history</h2><p>Drafts remain private to you until submitted.</p></div>
          <div className="finance-filter-row">
            <label><Search size={15} aria-hidden="true" /></label>
            <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Claim / project / description" />
            <select value={typeFilter} onChange={event => setTypeFilter(event.target.value as 'all' | FinanceClaimType)}>
              <option value="all">All request types</option>
              <option value="advance">Advance</option>
              <option value="reimbursement">Reimbursement</option>
              <option value="additional_advance">Additional Advance</option>
            </select>
            <select value={statusFilter} onChange={event => setStatusFilter(event.target.value as 'all' | FinanceClaimStatus)}>
              <option value="all">All statuses</option>
              {Object.entries(financeStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
        </div>

        {error && <div className="finance-error">{error}</div>}
        {loading ? <div className="finance-empty-state">Loading expense claims...</div> : visible.length === 0 ? (
          <div className="finance-empty-state"><ReceiptText size={28} /><p>No expense claims match this view.</p></div>
        ) : (
          <div className="finance-table-wrap">
            <table className="finance-table">
              <thead><tr><th>Claim</th><th>Project</th><th>Type</th><th>Amount</th><th>Status</th><th>Settlement</th><th>Updated</th><th>Action</th></tr></thead>
              <tbody>
                {visible.map(claim => (
                  <tr key={claim.id}>
                    <td><Link to={`/expenses/${claim.id}`}>{claim.claim_code}</Link></td>
                    <td><strong>{claim.project.project_code}</strong><br/><small>{claim.project.project_name}</small></td>
                    <td><span className={`finance-type-badge type-${financeClaimTypeTone(claim.claim_type)}`}>{financeClaimTypeLabels[claim.claim_type]}</span></td>
                    <td><strong>{formatInr(claim.total_amount)}</strong></td>
                    <td><span className={`finance-status tone-${financeStatusTone(claim.status)}`}>{financeStatusLabels[claim.status]}</span></td>
                    <td>{claim.claim_type === 'advance' ? claim.settlement_status.replaceAll('_', ' ') : '—'}{claim.settlement_overdue && <><br/><small className="finance-danger-text">OVERDUE</small></>}</td>
                    <td>{new Date(claim.updated_at).toLocaleString('en-IN')}</td>
                    <td>{claim.can_settle_advance ? <Link className="finance-primary-button" to={`/expenses/${claim.id}/settle`}>{claim.settlement ? 'Open Settlement' : 'Settle Advance'}</Link> : <Link className="finance-secondary-button" to={`/expenses/${claim.id}`}>View</Link>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
