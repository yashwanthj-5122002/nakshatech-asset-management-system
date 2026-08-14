import {
  CheckCircle2,
  Download,
  ExternalLink,
  FileCheck2,
  IndianRupee,
  RotateCcw,
  ShieldCheck,
  ThumbsDown,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../components/DashboardHeader'
import { StatCard } from '../components/StatCard'
import { useITMonthUrl } from '../context/ITMonthContext'
import { apiFetch, downloadFile } from '../lib/api'
import { monthLabel } from '../lib/itMonth'
import '../management-control.css'

type PurchaseStatus = 'pending_approval' | 'approved' | 'sent_back' | 'rejected' | 'purchase_completed'
type StatusFilter = 'all' | PurchaseStatus

type PurchaseRequestItem = {
  workflow: 'purchase_request'
  id: number
  code: string
  title: string
  submitted_by?: string
  submitted_at?: string
  department?: string
  priority?: string
  amount?: number
  reason?: string
  status: PurchaseStatus
  target_url: string
  reporting_month?: string
  approved_amount?: number
  management_remarks?: string
  decided_by?: string
  decided_at?: string
  purchase_completed_at?: string
  purchase_record_id?: number
  purchase_code?: string
  actual_purchase_amount?: number
  purchase_date?: string
  metadata: {
    requested_employee?: string
    quantity?: number
    item_type?: string
    required_by_date?: string
    it_remarks?: string
  }
}

type ManagementControlData = {
  generated_at: string
  month?: string
  authority_model: string
  executive: {
    pending_purchase_requests: number
    approved_purchase_value: number
  }
  purchase_summary: {
    total: number
    pending_approval: number
    approved: number
    sent_back: number
    rejected: number
    purchase_completed: number
    approved_purchase_value: number
  }
  purchase_requests: PurchaseRequestItem[]
}

const statusFilters: Array<{ value: StatusFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'pending_approval', label: 'Pending' },
  { value: 'approved', label: 'Approved' },
  { value: 'sent_back', label: 'Sent Back' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'purchase_completed', label: 'Purchase Completed' },
]

function formatMoney(value?: number) {
  if (value == null) return '—'
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(value)
}

function formatDate(value?: string) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Kolkata',
  }).format(new Date(value))
}

function statusLabel(status: PurchaseStatus) {
  return status.replaceAll('_', ' ').replace(/\b\w/g, character => character.toUpperCase())
}

export function ManagementApprovalCenter() {
  const { selectedMonth } = useITMonthUrl()
  const [data, setData] = useState<ManagementControlData | null>(null)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [remarks, setRemarks] = useState<Record<number, string>>({})
  const [approvedAmounts, setApprovedAmounts] = useState<Record<number, string>>({})
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  async function load() {
    setError('')
    try {
      setData(await apiFetch<ManagementControlData>(`/management/control-center?month=${encodeURIComponent(selectedMonth)}`))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load Purchase Approval Centre')
    }
  }

  useEffect(() => {
    setStatusFilter('all')
    void load()
  }, [selectedMonth])

  useEffect(() => {
    const synchronizeEmailDecision = () => { void load() }
    window.addEventListener('focus', synchronizeEmailDecision)
    return () => window.removeEventListener('focus', synchronizeEmailDecision)
  }, [selectedMonth])

  const filteredRequests = useMemo(() => {
    const requests = data?.purchase_requests || []
    return statusFilter === 'all' ? requests : requests.filter(item => item.status === statusFilter)
  }, [data?.purchase_requests, statusFilter])

  async function decide(item: PurchaseRequestItem, action: 'approve' | 'reject' | 'send_back') {
    if (item.status !== 'pending_approval') return
    const note = (remarks[item.id] || '').trim()
    if (['reject', 'send_back'].includes(action) && !note) {
      setError('Management remarks are required when rejecting or sending back a Purchase Request.')
      return
    }
    setBusy(`${item.id}-${action}`)
    setError('')
    setMessage('')
    try {
      await apiFetch(`/management/approvals/purchase_request/${item.id}/decision`, {
        method: 'POST',
        body: JSON.stringify({
          action,
          remarks: note || null,
          approved_amount: action === 'approve'
            ? Number(approvedAmounts[item.id] || item.amount || 0)
            : null,
        }),
      })
      setMessage(`${item.code} purchase decision saved: ${action.replaceAll('_', ' ')}.`)
      setRemarks(current => ({ ...current, [item.id]: '' }))
      setApprovedAmounts(current => ({ ...current, [item.id]: '' }))
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to save purchase decision')
    } finally {
      setBusy('')
    }
  }

  async function exportWorkbook() {
    setBusy('excel')
    setError('')
    try {
      await downloadFile(
        `/management/control-center.xlsx?month=${encodeURIComponent(selectedMonth)}`,
        `NakshaTech Purchase Approval Centre - ${selectedMonth}.xlsx`,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to download Purchase Approval workbook')
    } finally {
      setBusy('')
    }
  }

  const summary = data?.purchase_summary

  return (
    <>
      <DashboardHeader
        eyebrow="PURCHASE GOVERNANCE"
        title="Purchase Approval Centre"
        description={`Management purchase governance for ${monthLabel(selectedMonth)}. Every Purchase Request remains visible through Pending, Approved, Sent Back, Rejected and Purchase Completed states.`}
        actions={<button className="secondary-button" onClick={() => void exportWorkbook()} disabled={busy === 'excel'}><Download size={17} /> {busy === 'excel' ? 'Preparing…' : 'Purchase Excel'}</button>}
      />
      {message && <div className="success-message">{message}</div>}
      {error && <div className="error-message">{error}</div>}

      <div className="approval-note"><ShieldCheck size={16} /> Management can Approve, Send Back or Reject only Pending Purchase Requests. Approved, Sent Back, Rejected and Purchase Completed requests stay visible as read-only trace records.</div>

      <section className="stats-grid management-control-kpis">
        <StatCard icon={FileCheck2} label="Pending" value={summary?.pending_approval ?? '—'} tone="purple" />
        <StatCard icon={CheckCircle2} label="Approved" value={summary?.approved ?? '—'} tone="green" />
        <StatCard icon={RotateCcw} label="Sent Back" value={summary?.sent_back ?? '—'} tone="orange" />
        <StatCard icon={ThumbsDown} label="Rejected" value={summary?.rejected ?? '—'} tone="red" />
        <StatCard icon={FileCheck2} label="Purchase Completed" value={summary?.purchase_completed ?? '—'} tone="blue" />
        <StatCard icon={IndianRupee} label="Approved Purchase Value" value={summary ? formatMoney(summary.approved_purchase_value) : '—'} tone="green" />
      </section>

      <section className="panel management-approval-queue">
        <div className="panel-title-row">
          <div><span className="section-kicker">PURCHASE REQUEST LIFECYCLE</span><h2>Purchase Requests</h2></div>
          <span className="count-chip">{filteredRequests.length}</span>
        </div>

        <div className="management-decision-actions">
          {statusFilters.map(filter => (
            <button
              type="button"
              key={filter.value}
              className={statusFilter === filter.value ? 'primary-button' : 'secondary-button'}
              onClick={() => setStatusFilter(filter.value)}
            >
              {filter.label}
            </button>
          ))}
        </div>

        <div className="management-approval-list">
          {filteredRequests.map(item => {
            const isPending = item.status === 'pending_approval'
            return (
              <article className="management-approval-card" key={item.id}>
                <header>
                  <div><span>Purchase Request</span><h3>{item.code} · {item.title}</h3></div>
                  <div>
                    <strong className={`priority ${item.priority || 'medium'}`}>{item.priority || 'normal'}</strong>
                    <span className={`status ${item.status}`}>{statusLabel(item.status)}</span>
                  </div>
                </header>
                <div className="management-approval-meta">
                  <span>Submitted by <b>{item.submitted_by || 'Not recorded'}</b></span>
                  <span>{formatDate(item.submitted_at)}</span>
                  <span>{item.department || 'No department'}</span>
                  {item.amount != null && <span>Estimated {formatMoney(item.amount)}</span>}
                  {item.metadata.requested_employee && <span>For {item.metadata.requested_employee}</span>}
                </div>
                <p>{item.reason || 'No business reason recorded.'}</p>
                {item.metadata.it_remarks && <div className="approval-note">IT Remarks · {item.metadata.it_remarks}</div>}

                {isPending ? <>
                  <label className="management-approved-amount"><span>Approved Amount (INR)</span><input type="number" min="0" step="0.01" value={approvedAmounts[item.id] ?? (item.amount == null ? '' : String(item.amount))} onChange={event => setApprovedAmounts(current => ({ ...current, [item.id]: event.target.value }))} /></label>
                  <label className="management-decision-remarks"><span>Management Remarks</span><textarea rows={2} value={remarks[item.id] || ''} onChange={event => setRemarks(current => ({ ...current, [item.id]: event.target.value }))} placeholder="Required for Send Back / Reject; optional for approval" /></label>
                  <div className="management-decision-actions">
                    <button className="primary-button" onClick={() => void decide(item, 'approve')} disabled={busy.startsWith(`${item.id}-`)}><CheckCircle2 size={16} /> Approve Purchase</button>
                    <button className="secondary-button" onClick={() => void decide(item, 'send_back')} disabled={busy.startsWith(`${item.id}-`)}><RotateCcw size={16} /> Send Back</button>
                    <button className="danger-button" onClick={() => void decide(item, 'reject')} disabled={busy.startsWith(`${item.id}-`)}><ThumbsDown size={16} /> Reject</button>
                    <Link className="ghost-link" to={item.target_url}><ExternalLink size={15} /> Open Full Request</Link>
                  </div>
                </> : <>
                  <div className="approval-note">
                    <strong>{statusLabel(item.status)}</strong>
                    {item.approved_amount != null && <> · Approved Amount {formatMoney(item.approved_amount)}</>}
                    {item.decided_by && <> · Decision by {item.decided_by}</>}
                    {item.decided_at && <> · {formatDate(item.decided_at)}</>}
                    {item.management_remarks && <> · {item.management_remarks}</>}
                  </div>
                  {item.status === 'purchase_completed' && <div className="approval-note">
                    Purchase {item.purchase_code || 'record'} completed{item.purchase_date ? ` on ${item.purchase_date}` : ''}{item.actual_purchase_amount != null ? ` · Actual ${formatMoney(item.actual_purchase_amount)}` : ''}.
                  </div>}
                  <div className="management-decision-actions">
                    <Link className="ghost-link" to={item.target_url}><ExternalLink size={15} /> Open Full Request</Link>
                  </div>
                </>}
              </article>
            )
          })}
          {!filteredRequests.length && <div className="empty-state"><ShieldCheck size={28} /><strong>No Purchase Requests in this view</strong><span>Change the status filter or reporting month to review another part of the purchase lifecycle.</span></div>}
        </div>
      </section>
    </>
  )
}
