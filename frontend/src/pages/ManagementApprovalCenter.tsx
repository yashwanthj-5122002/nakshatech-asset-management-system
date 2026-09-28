import {
  AlertCircle,
  Building2,
  Calendar,
  CheckCircle2,
  Clock,
  Download,
  ExternalLink,
  FileCheck2,
  IndianRupee,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  ThumbsDown,
  User,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../components/DashboardHeader'
import { StatCard } from '../components/StatCard'
import { useITMonthUrl } from '../context/ITMonthContext'
import { useAuth } from '../context/AuthContext'
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
  { value: 'all', label: 'All Requests' },
  { value: 'pending_approval', label: 'Pending Approval' },
  { value: 'approved', label: 'Approved' },
  { value: 'sent_back', label: 'Sent Back' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'purchase_completed', label: 'Completed Purchases' },
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
  const { user } = useAuth()
  const canDecide = user?.role === 'management'
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
        eyebrow="MANAGEMENT · EXPENDITURE & PROCUREMENT GOVERNANCE"
        title="Purchase Approval Centre"
        description={`Executive procurement oversight and expenditure authorizations for ${monthLabel(selectedMonth)}. Authorize, send back for revision, or review closed purchase logs.`}
        actions={
          <button className="secondary-button" onClick={() => void exportWorkbook()} disabled={busy === 'excel'}>
            <Download size={16} /> {busy === 'excel' ? 'Preparing…' : 'Export Excel Audit'}
          </button>
        }
      />

      {message && <div className="success-message">{message}</div>}
      {error && <div className="error-message">{error}</div>}

      {/* Executive Outlay Hero Banner */}
      <section className="approval-outlay-hero">
        <div className="approval-outlay-metric">
          <span>Approved Capital & Operational Outlay ({monthLabel(selectedMonth)})</span>
          <strong>{summary ? formatMoney(summary.approved_purchase_value) : '—'}</strong>
          <small style={{ color: '#64748b', fontSize: '0.78rem' }}>
            Cumulative authorized expenditure across all department workflows this cycle.
          </small>
        </div>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          {(summary?.pending_approval ?? 0) > 0 ? (
            <div style={{ background: '#fffbeb', border: '1px solid #fde68a', borderRadius: '12px', padding: '12px 18px', textAlign: 'right' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#b45309', fontWeight: 800, fontSize: '0.85rem' }}>
                <Clock size={16} /> Pending Decision
              </div>
              <strong style={{ fontSize: '1.4rem', color: '#b45309' }}>{summary?.pending_approval}</strong>
            </div>
          ) : (
            <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '12px', padding: '12px 18px', textAlign: 'right' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#166534', fontWeight: 800, fontSize: '0.85rem' }}>
                <CheckCircle2 size={16} /> Up to Date
              </div>
              <small style={{ color: '#166534', fontWeight: 600 }}>0 pending actions</small>
            </div>
          )}
        </div>
      </section>

      {/* 4-Card Status Quad */}
      <section className="stats-grid" style={{ marginBottom: '20px' }}>
        <StatCard icon={AlertCircle} label="Pending Review" value={summary?.pending_approval ?? '—'} tone="purple" />
        <StatCard icon={CheckCircle2} label="Approved & Active" value={summary?.approved ?? '—'} tone="green" />
        <StatCard icon={RotateCcw} label="Sent Back" value={summary?.sent_back ?? '—'} tone="orange" />
        <StatCard icon={ThumbsDown} label="Rejected" value={summary?.rejected ?? '—'} tone="red" />
      </section>

      {/* Filter Chips Toolbar */}
      <div className="approval-status-chips-wrap">
        {statusFilters.map(filter => {
          let count = summary?.total ?? 0
          if (filter.value === 'pending_approval') count = summary?.pending_approval ?? 0
          else if (filter.value === 'approved') count = summary?.approved ?? 0
          else if (filter.value === 'sent_back') count = summary?.sent_back ?? 0
          else if (filter.value === 'rejected') count = summary?.rejected ?? 0
          else if (filter.value === 'purchase_completed') count = summary?.purchase_completed ?? 0

          return (
            <button
              type="button"
              key={filter.value}
              className={`approval-status-chip ${statusFilter === filter.value ? 'active' : ''}`}
              onClick={() => setStatusFilter(filter.value)}
            >
              {filter.label} <span style={{ opacity: 0.7, fontSize: '0.72rem' }}>({count})</span>
            </button>
          )
        })}
      </div>

      {/* Purchase Requests List */}
      <section className="management-approval-list">
        {filteredRequests.map(item => {
          const isPending = item.status === 'pending_approval'
          return (
            <article className="approval-card-refined" key={item.id}>
              <div className="approval-card-header">
                <div>
                  <span style={{ fontSize: '0.72rem', fontWeight: 800, letterSpacing: '0.06em', textTransform: 'uppercase', color: '#0284c7' }}>
                    {item.code}
                  </span>
                  <h3>{item.title}</h3>
                </div>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <span className={`operations-status ${item.priority === 'urgent' ? 'danger' : 'neutral'}`} style={{ textTransform: 'capitalize' }}>
                    {item.priority || 'Normal'} Priority
                  </span>
                  <span className={`status ${item.status}`}>{statusLabel(item.status)}</span>
                </div>
              </div>

              <div className="approval-meta-grid">
                <span><User size={13} /> Submitted by: <strong>{item.submitted_by || 'Not recorded'}</strong></span>
                <span><Calendar size={13} /> {formatDate(item.submitted_at)}</span>
                <span><Building2 size={13} /> Department: <strong>{item.department || 'General'}</strong></span>
                {item.amount != null && (
                  <span style={{ color: '#0f766e' }}>
                    Estimated Outlay: <strong>{formatMoney(item.amount)}</strong>
                  </span>
                )}
                {item.metadata.requested_employee && (
                  <span>For: <strong>{item.metadata.requested_employee}</strong></span>
                )}
              </div>

              <div className="approval-reason-text">
                <strong>Business Justification:</strong> {item.reason || 'No specific business justification provided.'}
                {item.metadata.it_remarks && (
                  <div style={{ marginTop: 6, fontSize: '0.78rem', color: '#475569' }}>
                    <em>IT Technical Remarks:</em> {item.metadata.it_remarks}
                  </div>
                )}
              </div>

              {isPending ? (
                canDecide ? (
                <>
                  <div className="approval-form-row">
                    <label className="operations-field">
                      <span style={{ fontWeight: 700, fontSize: '0.75rem' }}>Approved Amount (INR)</span>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        value={approvedAmounts[item.id] ?? (item.amount == null ? '' : String(item.amount))}
                        onChange={event => setApprovedAmounts(current => ({ ...current, [item.id]: event.target.value }))}
                      />
                    </label>
                    <label className="operations-field">
                      <span style={{ fontWeight: 700, fontSize: '0.75rem' }}>Management Executive Remarks</span>
                      <textarea
                        rows={1}
                        value={remarks[item.id] || ''}
                        onChange={event => setRemarks(current => ({ ...current, [item.id]: event.target.value }))}
                        placeholder="Required for Send Back / Reject; optional for Approval…"
                      />
                    </label>
                  </div>
                  <div className="approval-btn-group">
                    <button
                      className="btn-approve"
                      onClick={() => void decide(item, 'approve')}
                      disabled={busy.startsWith(`${item.id}-`)}
                    >
                      <CheckCircle2 size={15} /> Authorize & Approve
                    </button>
                    <button
                      className="btn-sendback"
                      onClick={() => void decide(item, 'send_back')}
                      disabled={busy.startsWith(`${item.id}-`)}
                    >
                      <RotateCcw size={15} /> Send Back For Revision
                    </button>
                    <button
                      className="btn-reject"
                      onClick={() => void decide(item, 'reject')}
                      disabled={busy.startsWith(`${item.id}-`)}
                    >
                      <ThumbsDown size={15} /> Reject Request
                    </button>
                    <Link className="ghost-link" to={item.target_url}>
                      <ExternalLink size={14} /> Full Dossier
                    </Link>
                  </div>
                </>
                ) : (
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#f8fafc', padding: '10px 14px', borderRadius: '10px', fontSize: '0.8rem', color: '#475569' }}>
                    <div>
                      <strong>Pending Management decision.</strong> Admin has read-only visibility; only Management can authorize.
                      {item.amount != null && <> · Requested: {formatMoney(item.amount)}</>}
                    </div>
                    <Link className="ghost-link" to={item.target_url}>
                      <ExternalLink size={14} /> Full Dossier
                    </Link>
                  </div>
                )
              ) : (
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#f8fafc', padding: '10px 14px', borderRadius: '10px', fontSize: '0.8rem', color: '#475569' }}>
                  <div>
                    <strong>{statusLabel(item.status)}:</strong>
                    {item.approved_amount != null && <> Authorized amount: {formatMoney(item.approved_amount)}</>}
                    {item.decided_by && <> by {item.decided_by}</>}
                    {item.decided_at && <> on {formatDate(item.decided_at)}</>}
                    {item.management_remarks && <> · &quot;{item.management_remarks}&quot;</>}
                    {item.status === 'purchase_completed' && item.actual_purchase_amount != null && (
                      <> · Actual procured: {formatMoney(item.actual_purchase_amount)}</>
                    )}
                  </div>
                  <Link className="ghost-link" to={item.target_url}>
                    <ExternalLink size={14} /> View Dossier
                  </Link>
                </div>
              )}
            </article>
          )
        })}
        {!filteredRequests.length && (
          <div className="empty-state">
            <ShieldCheck size={32} />
            <strong>No Purchase Requests in this view</strong>
            <span>Select another filter chip or reporting month above to review other stages.</span>
          </div>
        )}
      </section>
    </>
  )
}
