import { ArrowLeft, CheckCircle2, Download, ExternalLink, FileArchive, FileText, IndianRupee, RefreshCw, Send, XCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { useAuth } from '../../../context/AuthContext'
import { apiBlob, apiFetch, downloadFile } from '../../../lib/api'
import type { ExpenseClaim, ExpenseSettlement, FinancePaymentMode } from '../../../types'
import { financeClaimTypeLabels, financeClaimTypeTone, financeStatusLabels, financeStatusTone, formatInr } from '../finance-utils'
import '../finance-expenses.css'

function displayDate(value?: string | null) { return value ? new Date(`${value}T00:00:00`).toLocaleDateString('en-IN') : 'Not set' }
function settlementLabel(value: string) { return value.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase()) }

export function ExpenseClaimDetailPage() {
  const { id } = useParams()
  const { user } = useAuth()
  const location = useLocation()
  const staffView = location.pathname.startsWith('/finance/')
  const [claim, setClaim] = useState<ExpenseClaim | null>(null)
  const [comments, setComments] = useState('')
  const [settlementComments, setSettlementComments] = useState('')
  const [paymentReference, setPaymentReference] = useState('')
  const [approvedAmount, setApprovedAmount] = useState('')
  const [paidAmount, setPaidAmount] = useState('')
  const [paymentMode, setPaymentMode] = useState<FinancePaymentMode>('bank_transfer')
  const [paymentDate, setPaymentDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [approvedWorkStart, setApprovedWorkStart] = useState('')
  const [approvedWorkEnd, setApprovedWorkEnd] = useState('')
  const [settlementDue, setSettlementDue] = useState('')
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState('')
  const [error, setError] = useState('')

  function applyClaim(result: ExpenseClaim) {
    setClaim(result)
    setApprovedAmount(String(result.finance_approved_amount ?? result.total_amount))
    setPaidAmount(String(result.remaining_amount || result.finance_approved_amount || result.total_amount))
    setApprovedWorkStart(result.approved_work_start_date || result.requested_work_start_date || '')
    setApprovedWorkEnd(result.approved_work_end_date || result.requested_work_end_date || '')
    setSettlementDue(result.settlement_due_date || '')
  }

  function load() {
    if (!id) return
    setLoading(true); setError('')
    void apiFetch<ExpenseClaim>(`/finance/claims/${id}`).then(applyClaim).catch(err => setError(err instanceof Error ? err.message : 'Could not load expense claim')).finally(() => setLoading(false))
  }
  useEffect(load, [id])

  async function decision(kind: 'admin' | 'finance', action: 'approve' | 'reject' | 'send_back') {
    if (!claim) return
    if (comments.trim().length < 2) { setError('Add a short verification comment before taking an approval action.'); return }
    if (action === 'approve' && (!approvedWorkStart || !approvedWorkEnd)) { setError('Confirm the approved work start and end dates.'); return }
    if (kind === 'finance' && action === 'approve' && ['advance', 'additional_advance'].includes(claim.claim_type) && !settlementDue) { setError('Set the settlement due date before approving this advance.'); return }
    setActionLoading(`${kind}-${action}`); setError('')
    try {
      const result = await apiFetch<ExpenseClaim>(`/finance/claims/${claim.id}/${kind}-decision`, { method: 'POST', body: JSON.stringify({
        action,
        comments: comments.trim(),
        approved_amount: kind === 'finance' && action === 'approve' ? Number(approvedAmount) || claim.total_amount : undefined,
        approved_work_start_date: action === 'approve' ? approvedWorkStart : undefined,
        approved_work_end_date: action === 'approve' ? approvedWorkEnd : undefined,
        settlement_due_date: action === 'approve' && settlementDue ? settlementDue : undefined,
      }) })
      applyClaim(result); setComments('')
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not update the claim') } finally { setActionLoading('') }
  }

  async function settlementDecision(kind: 'admin' | 'finance', action: 'approve' | 'reject' | 'send_back') {
    const settlement = claim?.settlement
    if (!settlement) return
    if (settlementComments.trim().length < 2) { setError('Add a settlement verification comment.'); return }
    setActionLoading(`settlement-${kind}-${action}`); setError('')
    try {
      await apiFetch<ExpenseSettlement>(`/finance/settlements/${settlement.id}/${kind}-decision`, { method: 'POST', body: JSON.stringify({ action, comments: settlementComments.trim() }) })
      setSettlementComments(''); load()
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not update settlement') } finally { setActionLoading('') }
  }

  async function markPayment() {
    if (!claim) return
    if (!paymentReference.trim()) { setError('Enter the bank / UTR / payment reference.'); return }
    setActionLoading('paid'); setError('')
    try {
      const result = await apiFetch<ExpenseClaim>(`/finance/claims/${claim.id}/mark-paid`, { method: 'POST', body: JSON.stringify({ payment_reference: paymentReference.trim(), paid_amount: Number(paidAmount) || claim.remaining_amount, payment_mode: paymentMode, payment_date: paymentDate || undefined, comments: comments.trim() || undefined }) })
      applyClaim(result); setPaymentReference(''); setComments('')
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not record payment') } finally { setActionLoading('') }
  }

  async function resubmit() {
    if (!claim) return
    setActionLoading('submit'); setError('')
    try { applyClaim(await apiFetch<ExpenseClaim>(`/finance/claims/${claim.id}/submit`, { method: 'POST' })) } catch (err) { setError(err instanceof Error ? err.message : 'Could not submit the claim') } finally { setActionLoading('') }
  }

  async function openBlob(path: string, fallbackName: string) {
    try {
      const blob = await apiBlob(path); const url = URL.createObjectURL(blob); const tab = window.open(url, '_blank', 'noopener,noreferrer')
      if (!tab) { const anchor = document.createElement('a'); anchor.href = url; anchor.download = fallbackName; anchor.click() }
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not open document') }
  }

  if (loading) return <div className="finance-empty-state">Loading expense claim...</div>
  if (!claim) return <div className="finance-page"><div className="finance-error">{error || 'Expense claim not found.'}</div></div>
  const backPath = staffView ? '/finance/claims' : '/expenses'
  const settlement = claim.settlement

  return <div className="finance-page">
    <DashboardHeader eyebrow={staffView ? 'FINANCE CRM · CLAIM REVIEW' : 'PROJECT EXPENSES · CLAIM DETAIL'} title={claim.claim_code} description={`${claim.project.project_code} · ${claim.project.project_name} · ${claim.requester_name}`} actions={<div className="finance-header-actions">{staffView && <><button className="finance-secondary-button" onClick={() => void openBlob(`/finance/claims/${claim.id}/documents/report.pdf`, `${claim.claim_code}_A4_Report.pdf`)}><FileText size={15}/> View A4</button><button className="finance-secondary-button" onClick={() => void downloadFile(`/finance/claims/${claim.id}/documents/all-bills.zip`, `${claim.claim_code}_All_Bills.zip`)}><FileArchive size={15}/> All Bills</button><button className="finance-primary-button" onClick={() => void downloadFile(`/finance/claims/${claim.id}/documents/a4-pack.pdf`, `${claim.claim_code}_A4_Pack.pdf`)}><Download size={15}/> Complete A4 Pack</button></>}<Link className="finance-secondary-button" to={backPath}><ArrowLeft size={16}/> Back</Link></div>} />
    {error && <div className="finance-error">{error}</div>}

    <section className="finance-detail-grid"><div className="finance-page">
      <article className="finance-claim-card"><div className="finance-claim-card-header"><div><span className={`finance-type-badge type-${financeClaimTypeTone(claim.claim_type)}`}>{financeClaimTypeLabels[claim.claim_type]}</span><h2>{formatInr(claim.total_amount)}</h2></div><span className={`finance-status tone-${financeStatusTone(claim.status)}`}>{financeStatusLabels[claim.status]}</span></div>
        <div className="finance-detail-facts">
          <div className="finance-fact"><span>Employee</span><strong>{claim.requester_name}</strong></div><div className="finance-fact"><span>Department</span><strong>{claim.requester_department || 'Not specified'}</strong></div>
          <div className="finance-fact"><span>Project ID</span><strong>{claim.project.project_code}</strong></div><div className="finance-fact"><span>Project Period</span><strong>{displayDate(claim.project.start_date)} → {displayDate(claim.project.end_date)}</strong></div>
          <div className="finance-fact"><span>Employee Requested Work</span><strong>{displayDate(claim.requested_work_start_date)} → {displayDate(claim.requested_work_end_date)} · {claim.requested_work_days || 0} day(s)</strong></div>
          <div className="finance-fact"><span>Approved Work</span><strong>{displayDate(claim.approved_work_start_date)} → {displayDate(claim.approved_work_end_date)}{claim.approved_work_days ? ` · ${claim.approved_work_days} day(s)` : ''}</strong></div>
          <div className="finance-fact"><span>Settlement Due</span><strong>{displayDate(claim.settlement_due_date)}{claim.settlement_overdue ? ' · OVERDUE' : ''}</strong></div><div className="finance-fact"><span>Settlement Status</span><strong>{settlementLabel(claim.settlement_status)}</strong></div>
          <div className="finance-fact"><span>Admin Verification</span><strong>{claim.admin_decision_by_name || 'Pending'}</strong></div><div className="finance-fact"><span>Finance Verification</span><strong>{claim.finance_decision_by_name || 'Pending'}</strong></div>
          <div className="finance-fact"><span>Finance Approved</span><strong>{formatInr(claim.finance_approved_amount)}</strong></div><div className="finance-fact"><span>Paid</span><strong>{formatInr(claim.paid_amount)}</strong></div>
          {claim.parent_advance_claim_code && <div className="finance-fact"><span>Original Advance</span><strong>{claim.parent_advance_claim_code}</strong></div>}
        </div><span className="finance-panel-kicker">PURPOSE / DESCRIPTION</span><p className="finance-purpose">{claim.purpose_description}</p>
      </article>

      <article className="finance-panel"><div className="finance-panel-header"><div><span className="finance-panel-kicker">REQUEST BREAKUP</span><h2>{claim.claim_type === 'reimbursement' ? 'Personally-paid expenses' : 'Requested / planned expenses'}</h2></div></div><div className="finance-table-wrap"><table className="finance-table"><thead><tr><th>Category</th><th>Description</th><th>Mode</th><th>Date</th><th>Amount</th></tr></thead><tbody>{claim.items.map(item => <tr key={item.id}><td>{(item.other_category || item.category).replaceAll('_',' ')}</td><td>{item.description}</td><td>{item.payment_mode?.replaceAll('_',' ') || '—'}</td><td>{displayDate(item.expense_date)}</td><td><strong>{formatInr(item.amount)}</strong></td></tr>)}</tbody></table></div><div className="finance-total-strip"><span>Total Claim Amount</span><strong>{formatInr(claim.total_amount)}</strong></div></article>

      <article className="finance-panel"><div className="finance-panel-header"><div><span className="finance-panel-kicker">REQUEST PROOF</span><h2>Submitted bills / supporting documents</h2></div></div>{claim.attachments.length === 0 ? <div className="finance-empty-state">No request attachments.</div> : <div className="finance-attachment-list">{claim.attachments.map(file => <div className="finance-attachment-row" key={file.id}><div><strong>{file.original_filename}</strong><br/><small>{Math.max(1,Math.round(file.file_size/1024))} KB · {file.uploaded_by_name}</small></div><div className="finance-inline-actions"><button type="button" onClick={() => void openBlob(`/finance/claims/${claim.id}/attachments/${file.id}/content`, file.original_filename)}><ExternalLink size={14}/> View</button><button type="button" onClick={() => void downloadFile(`/finance/claims/${claim.id}/attachments/${file.id}/content?download=true`, file.original_filename)}><Download size={14}/> Download</button></div></div>)}</div>}</article>

      {settlement && <article className="finance-panel"><div className="finance-panel-header"><div><span className="finance-panel-kicker">ADVANCE SETTLEMENT</span><h2>{settlement.settlement_code}</h2><p>Actual bills after completion of work. The original Advance plus released Additional Advances are tallied together.</p></div><span className={`finance-status tone-${settlement.status === 'finance_finalized' ? 'success' : settlement.status.includes('rejected') ? 'danger' : settlement.status.includes('sent_back') ? 'warning' : 'pending'}`}>{settlementLabel(settlement.status)}</span></div>
        <div className="finance-tally-grid"><div><span>Total Advance Received</span><strong>{formatInr(settlement.total_advance_received)}</strong></div><div><span>Actual Supported Expense</span><strong>{formatInr(settlement.total_expense_amount)}</strong></div><div><span>Balance To Return</span><strong>{formatInr(settlement.balance_to_return)}</strong></div><div><span>Shortage</span><strong>{formatInr(settlement.shortage_amount)}</strong></div></div>
        <div className="finance-table-wrap"><table className="finance-table"><thead><tr><th>Category</th><th>Actual Usage</th><th>Payment Mode</th><th>Expense Date</th><th>Amount</th></tr></thead><tbody>{settlement.items.map(item => <tr key={item.id}><td>{(item.other_category || item.category).replaceAll('_',' ')}</td><td>{item.description}</td><td>{item.payment_mode.replaceAll('_',' ')}</td><td>{displayDate(item.expense_date)}</td><td><strong>{formatInr(item.amount)}</strong></td></tr>)}</tbody></table></div>
        <div className="finance-panel-header"><div><span className="finance-panel-kicker">SETTLEMENT BILLS</span><h2>{settlement.attachments.length} supporting file(s)</h2></div></div>{settlement.attachments.length === 0 ? <div className="finance-empty-state">No settlement bills uploaded yet.</div> : <div className="finance-attachment-list">{settlement.attachments.map(file => <div className="finance-attachment-row" key={file.id}><div><strong>{file.original_filename}</strong><br/><small>{Math.max(1,Math.round(file.file_size/1024))} KB · {file.uploaded_by_name}</small></div><div className="finance-inline-actions"><button type="button" onClick={() => void openBlob(`/finance/settlements/${settlement.id}/attachments/${file.id}/content`, file.original_filename)}><ExternalLink size={14}/> View</button><button type="button" onClick={() => void downloadFile(`/finance/settlements/${settlement.id}/attachments/${file.id}/content?download=true`, file.original_filename)}><Download size={14}/> Download</button></div></div>)}</div>}
      </article>}
    </div>

    <aside className="finance-page">
      {user?.role === 'employee' && claim.can_edit && <article className="finance-panel"><div className="finance-decision-box"><strong>{claim.status === 'draft' ? 'Complete this draft' : 'Claim was sent back for correction'}</strong><span className="finance-help-text">Update the same auditable claim, then resubmit to Admin.</span><Link className="finance-secondary-button" to={`/expenses/${claim.id}/edit`}><RefreshCw size={15}/> Edit Claim</Link><button className="finance-primary-button" type="button" onClick={() => void resubmit()} disabled={Boolean(actionLoading)}><Send size={15}/> Submit / Resubmit</button></div></article>}
      {user?.role === 'employee' && claim.can_settle_advance && <article className="finance-panel"><div className="finance-decision-box"><span className="finance-panel-kicker">WORK COMPLETED</span><strong>Upload actual bills and settle this released advance.</strong><span className="finance-help-text">Settlement due: {displayDate(claim.settlement_due_date)}{claim.settlement_overdue ? ' · OVERDUE' : ''}</span><Link className="finance-primary-button" to={`/expenses/${claim.id}/settle`}><FileText size={15}/> {settlement ? 'Open / Correct Settlement' : 'Settle Advance'}</Link>{claim.can_request_additional_advance && <Link className="finance-secondary-button" to={`/expenses/new?parent=${claim.id}`}><IndianRupee size={15}/> Request Additional Advance</Link>}</div></article>}

      {claim.can_admin_decide && <article className="finance-panel"><div className="finance-decision-box"><span className="finance-panel-kicker">ADMIN VERIFICATION</span><strong>Verify project, requested work dates, purpose, amount and proof.</strong><label className="finance-field"><span>Admin Proposed Work Start</span><input type="date" value={approvedWorkStart} onChange={e=>setApprovedWorkStart(e.target.value)}/></label><label className="finance-field"><span>Admin Proposed Work End</span><input type="date" value={approvedWorkEnd} onChange={e=>setApprovedWorkEnd(e.target.value)}/></label>{['advance','additional_advance'].includes(claim.claim_type) && <label className="finance-field"><span>Proposed Settlement Due</span><input type="date" value={settlementDue} onChange={e=>setSettlementDue(e.target.value)}/></label>}<textarea value={comments} onChange={e=>setComments(e.target.value)} placeholder="Admin verification comments *"/><button className="finance-success-button" onClick={() => void decision('admin','approve')} disabled={Boolean(actionLoading)}><CheckCircle2 size={15}/> Approve & Send to Finance</button><button className="finance-warning-button" onClick={() => void decision('admin','send_back')} disabled={Boolean(actionLoading)}><RefreshCw size={15}/> Send Back</button><button className="finance-danger-button" onClick={() => void decision('admin','reject')} disabled={Boolean(actionLoading)}><XCircle size={15}/> Reject</button></div></article>}

      {claim.can_finance_decide && <article className="finance-panel"><div className="finance-decision-box"><span className="finance-panel-kicker">FINANCE VERIFICATION</span><strong>Finance may shorten/change the approved work period while preserving the employee-requested dates.</strong><label className="finance-field"><span>Finance Approved Amount *</span><input type="number" min="0.01" max={claim.total_amount} step="0.01" value={approvedAmount} onChange={e=>setApprovedAmount(e.target.value)}/></label><label className="finance-field"><span>Finance Approved Work Start *</span><input type="date" value={approvedWorkStart} onChange={e=>setApprovedWorkStart(e.target.value)}/></label><label className="finance-field"><span>Finance Approved Work End *</span><input type="date" value={approvedWorkEnd} onChange={e=>setApprovedWorkEnd(e.target.value)}/></label>{['advance','additional_advance'].includes(claim.claim_type) && <label className="finance-field"><span>Settlement Due Date *</span><input type="date" value={settlementDue} onChange={e=>setSettlementDue(e.target.value)}/></label>}<textarea value={comments} onChange={e=>setComments(e.target.value)} placeholder="Finance verification comments *"/><button className="finance-success-button" onClick={() => void decision('finance','approve')} disabled={Boolean(actionLoading)}><CheckCircle2 size={15}/> Finance Approve</button><button className="finance-warning-button" onClick={() => void decision('finance','send_back')} disabled={Boolean(actionLoading)}><RefreshCw size={15}/> Send Back</button><button className="finance-danger-button" onClick={() => void decision('finance','reject')} disabled={Boolean(actionLoading)}><XCircle size={15}/> Reject</button></div></article>}

      {claim.can_mark_paid && <article className="finance-panel"><div className="finance-decision-box"><span className="finance-panel-kicker">PAYMENT RELEASE</span><strong>Record only money actually released.</strong><div className="finance-payment-balance"><span>Approved {formatInr(claim.finance_approved_amount || claim.total_amount)}</span><span>Paid {formatInr(claim.paid_amount)}</span><strong>Remaining {formatInr(claim.remaining_amount)}</strong></div><label className="finance-field"><span>Payment / UTR Reference *</span><input value={paymentReference} onChange={e=>setPaymentReference(e.target.value)}/></label><label className="finance-field"><span>Payment Mode</span><select value={paymentMode} onChange={e=>setPaymentMode(e.target.value as FinancePaymentMode)}><option value="bank_transfer">Bank Transfer</option><option value="upi">UPI</option><option value="cash">Cash</option><option value="cheque">Cheque</option><option value="card">Card</option><option value="other">Other</option></select></label><label className="finance-field"><span>Payment Date</span><input type="date" value={paymentDate} onChange={e=>setPaymentDate(e.target.value)}/></label><label className="finance-field"><span>Payment Amount</span><input type="number" min="0.01" max={claim.remaining_amount} step="0.01" value={paidAmount} onChange={e=>setPaidAmount(e.target.value)}/></label><textarea value={comments} onChange={e=>setComments(e.target.value)} placeholder="Payment note (optional)"/><button className="finance-primary-button" onClick={() => void markPayment()} disabled={Boolean(actionLoading)}><IndianRupee size={15}/> Record Payment</button></div></article>}

      {settlement?.can_admin_decide && <article className="finance-panel"><div className="finance-decision-box"><span className="finance-panel-kicker">ADMIN SETTLEMENT VERIFICATION</span><strong>Verify all final bills and the automatic advance tally.</strong><textarea value={settlementComments} onChange={e=>setSettlementComments(e.target.value)} placeholder="Settlement verification comments *"/><button className="finance-success-button" onClick={() => void settlementDecision('admin','approve')}><CheckCircle2 size={15}/> Verify & Send to Finance</button><button className="finance-warning-button" onClick={() => void settlementDecision('admin','send_back')}><RefreshCw size={15}/> Send Back</button><button className="finance-danger-button" onClick={() => void settlementDecision('admin','reject')}><XCircle size={15}/> Reject</button></div></article>}
      {settlement?.can_finance_decide && <article className="finance-panel"><div className="finance-decision-box"><span className="finance-panel-kicker">FINANCE FINAL SETTLEMENT</span><strong>Finalize supported expenses, balance or shortage after Admin verification.</strong><div className="finance-payment-balance"><span>Advance {formatInr(settlement.total_advance_received)}</span><span>Expense {formatInr(settlement.total_expense_amount)}</span><strong>{settlementLabel(settlement.tally_status)}</strong></div><textarea value={settlementComments} onChange={e=>setSettlementComments(e.target.value)} placeholder="Finance settlement comments *"/><button className="finance-success-button" onClick={() => void settlementDecision('finance','approve')}><CheckCircle2 size={15}/> Finalize Settlement</button><button className="finance-warning-button" onClick={() => void settlementDecision('finance','send_back')}><RefreshCw size={15}/> Send Back</button><button className="finance-danger-button" onClick={() => void settlementDecision('finance','reject')}><XCircle size={15}/> Reject</button></div></article>}

      {claim.payments.length > 0 && <article className="finance-panel"><div className="finance-panel-header"><div><span className="finance-panel-kicker">PAYMENT LEDGER</span><h2>Recorded payments</h2></div></div><div className="finance-payment-history">{[...claim.payments].reverse().map(p => <div className="finance-payment-history-row" key={p.id}><div><strong>{formatInr(p.amount)}</strong><span>{p.payment_mode.replaceAll('_',' ')} · {displayDate(p.payment_date)}</span></div><div><strong>{p.payment_reference}</strong><span>{p.recorded_by_name}</span></div></div>)}</div></article>}
      <article className="finance-panel"><div className="finance-panel-header"><div><span className="finance-panel-kicker">AUDIT TRAIL</span><h2>Claim timeline</h2></div></div><div className="finance-timeline">{[...claim.events].reverse().map(event => <div className="finance-timeline-item" key={event.id}><strong>{event.action.replaceAll('_',' ')}</strong><span>{event.actor_name || 'System'} · {new Date(event.created_at).toLocaleString('en-IN')}</span>{event.comments && <p>{event.comments}</p>}</div>)}</div>{settlement && <><div className="finance-panel-header"><div><span className="finance-panel-kicker">SETTLEMENT AUDIT</span><h2>Settlement timeline</h2></div></div><div className="finance-timeline">{[...settlement.events].reverse().map(event => <div className="finance-timeline-item" key={event.id}><strong>{event.action.replaceAll('_',' ')}</strong><span>{event.actor_name || 'System'} · {new Date(event.created_at).toLocaleString('en-IN')}</span>{event.comments && <p>{event.comments}</p>}</div>)}</div></>}</article>
    </aside></section>
  </div>
}
