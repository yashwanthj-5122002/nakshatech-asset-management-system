import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Download,
  ExternalLink,
  FileCheck2,
  HardDrive,
  IndianRupee,
  RotateCcw,
  ShieldCheck,
  ThumbsDown,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../components/DashboardHeader'
import { StatCard } from '../components/StatCard'
import { useITMonthUrl } from '../context/ITMonthContext'
import { apiFetch, downloadFile } from '../lib/api'
import { monthLabel } from '../lib/itMonth'
import '../management-control.css'

type ApprovalItem = {
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
  status: string
  target_url: string
  reporting_month?: string
  metadata: Record<string, unknown>
}

type RiskTicket = {
  id: number
  ticket_code: string
  title: string
  department: string
  priority: string
  status: string
  created_at: string
  sla_status?: string
  sla_due_at?: string
  sla_breached: boolean
  sla_warning: boolean
  target_url: string
}

type RecentDecision = {
  id: number
  workflow: string
  code: string
  action: string
  from_status?: string
  to_status: string
  remarks?: string
  performed_by: string
  performed_by_role: string
  created_at: string
}

type ManagementControlData = {
  generated_at: string
  month?: string
  authority_model: string
  executive: {
    primary_assets: number
    assigned_assets: number
    available_assets: number
    repair_assets: number
    replacement_pending_assets: number
    active_it_work: number
    active_replacements: number
    pending_approvals: number
    pending_purchase_requests: number
    approved_purchase_value: number
    open_critical_tickets: number
    sla_warnings: number
    sla_breaches: number
  }
  approvals: ApprovalItem[]
  risk_tickets: RiskTicket[]
  recent_decisions: RecentDecision[]
}

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

export function ManagementApprovalCenter() {
  const { selectedMonth } = useITMonthUrl()
  const [data, setData] = useState<ManagementControlData | null>(null)
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

  useEffect(() => { void load() }, [selectedMonth])

  async function decide(item: ApprovalItem, action: 'approve' | 'reject' | 'send_back') {
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
        `NakshaTech Management Control - ${selectedMonth}.xlsx`,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to download Management workbook')
    } finally {
      setBusy('')
    }
  }

  return (
    <>
      <DashboardHeader
        eyebrow="PURCHASE GOVERNANCE"
        title="Purchase Approval Centre"
        description={`Management permission is required only for Purchase Requests in ${monthLabel(selectedMonth)}. IT Work, replacements, handovers and asset operations remain under IT control and are visible to Management in read-only mode.`}
        actions={<button className="secondary-button" onClick={() => void exportWorkbook()} disabled={busy === 'excel'}><Download size={17} /> {busy === 'excel' ? 'Preparing…' : 'Management Excel'}</button>}
      />
      {message && <div className="success-message">{message}</div>}
      {error && <div className="error-message">{error}</div>}

      <div className="approval-note"><ShieldCheck size={16} /> Final authority model: Management approves expenditure only. Operational IT records remain fully visible but read-only.</div>

      <section className="stats-grid management-control-kpis">
        <StatCard icon={FileCheck2} label="Pending Purchase Approvals" value={data?.executive.pending_purchase_requests ?? '—'} tone="purple" />
        <StatCard icon={IndianRupee} label="Approved Purchase Value" value={data ? formatMoney(data.executive.approved_purchase_value) : '—'} tone="green" />
        <StatCard icon={HardDrive} label="Primary IT Assets" value={data?.executive.primary_assets ?? '—'} />
        <StatCard icon={AlertTriangle} label="SLA Breaches" value={data?.executive.sla_breaches ?? '—'} tone="red" />
        <StatCard icon={Clock3} label="Critical Tickets" value={data?.executive.open_critical_tickets ?? '—'} tone="orange" />
      </section>

      <section className="management-control-grid">
        <article className="panel management-approval-queue">
          <div className="panel-title-row">
            <div><span className="section-kicker">ONLY APPROVAL QUEUE</span><h2>Pending Purchase Requests</h2></div>
            <span className="count-chip">{data?.approvals.length ?? 0}</span>
          </div>

          <div className="management-approval-list">
            {(data?.approvals || []).map(item => (
              <article className="management-approval-card" key={item.id}>
                <header>
                  <div><span>Purchase Request</span><h3>{item.code} · {item.title}</h3></div>
                  <strong className={`priority ${item.priority || 'medium'}`}>{item.priority || 'normal'}</strong>
                </header>
                <div className="management-approval-meta">
                  <span>Submitted by <b>{item.submitted_by || 'Not recorded'}</b></span>
                  <span>{formatDate(item.submitted_at)}</span>
                  <span>{item.department || 'No department'}</span>
                  {item.amount != null && <span>{formatMoney(item.amount)}</span>}
                </div>
                <p>{item.reason || 'No business reason recorded.'}</p>
                {typeof item.metadata.it_remarks === 'string' && item.metadata.it_remarks && <div className="approval-note">IT Remarks · {item.metadata.it_remarks}</div>}
                <label className="management-approved-amount"><span>Approved Amount (INR)</span><input type="number" min="0" step="0.01" value={approvedAmounts[item.id] ?? (item.amount == null ? '' : String(item.amount))} onChange={event => setApprovedAmounts(current => ({ ...current, [item.id]: event.target.value }))} /></label>
                <label className="management-decision-remarks"><span>Management Remarks</span><textarea rows={2} value={remarks[item.id] || ''} onChange={event => setRemarks(current => ({ ...current, [item.id]: event.target.value }))} placeholder="Required for Send Back / Reject; optional for approval" /></label>
                <div className="management-decision-actions">
                  <button className="primary-button" onClick={() => void decide(item, 'approve')} disabled={busy.startsWith(`${item.id}-`)}><CheckCircle2 size={16} /> Approve Purchase</button>
                  <button className="secondary-button" onClick={() => void decide(item, 'send_back')} disabled={busy.startsWith(`${item.id}-`)}><RotateCcw size={16} /> Send Back</button>
                  <button className="danger-button" onClick={() => void decide(item, 'reject')} disabled={busy.startsWith(`${item.id}-`)}><ThumbsDown size={16} /> Reject</button>
                  <Link className="ghost-link" to={item.target_url}><ExternalLink size={15} /> Open Full Request</Link>
                </div>
              </article>
            ))}
            {!data?.approvals.length && <div className="empty-state"><ShieldCheck size={28} /><strong>No purchase approvals pending</strong><span>Management has no expenditure decision waiting for this period.</span></div>}
          </div>
        </article>

        <aside className="management-control-side">
          <section className="panel">
            <div className="panel-title-row"><div><span className="section-kicker">EXECUTIVE RISK</span><h2>Critical Tickets & SLA</h2></div><AlertTriangle /></div>
            <div className="management-risk-list">
              {(data?.risk_tickets || []).map(ticket => (
                <Link to={ticket.target_url} key={ticket.id} className={ticket.sla_breached ? 'breached' : ticket.sla_warning ? 'warning' : ''}>
                  <div><strong>{ticket.ticket_code}</strong><span>{ticket.title}</span></div>
                  <small>{ticket.priority} · {ticket.sla_status?.replaceAll('_', ' ') || 'SLA not applicable'}</small>
                </Link>
              ))}
              {!data?.risk_tickets.length && <div className="empty-state">No active ticket risk.</div>}
            </div>
          </section>

          <section className="panel">
            <div className="panel-title-row"><div><span className="section-kicker">PURCHASE TRACE</span><h2>Recent Purchase Decisions</h2></div><FileCheck2 /></div>
            <div className="management-decision-history">
              {(data?.recent_decisions || []).slice(0, 12).map(item => (
                <div key={item.id}>
                  <i />
                  <p><strong>{item.code} · {item.action.replaceAll('_', ' ')}</strong><span>{item.performed_by} · {formatDate(item.created_at)}</span><small>{item.remarks || `${item.from_status || 'new'} → ${item.to_status}`}</small></p>
                </div>
              ))}
              {!data?.recent_decisions.length && <div className="empty-state">No purchase decisions for this period.</div>}
            </div>
          </section>
        </aside>
      </section>
    </>
  )
}
