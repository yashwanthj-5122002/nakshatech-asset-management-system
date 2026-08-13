import {
  CheckCircle2,
  Clock3,
  Download,
  Eye,
  FileCheck2,
  IndianRupee,
  PackageCheck,
  PencilLine,
  RotateCcw,
  Search,
  Send,
  ShoppingCart,
  ThumbsDown,
  X,
} from 'lucide-react'
import { type FormEvent, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { DashboardHeader } from '../components/DashboardHeader'
import { StatCard } from '../components/StatCard'
import { useAuth } from '../context/AuthContext'
import { useITMonthUrl } from '../context/ITMonthContext'
import { apiFetch, downloadFile } from '../lib/api'
import { monthLabel } from '../lib/itMonth'
import { isFullAccessRole } from '../lib/roles'
import type {
  ITPurchaseRequest,
  PurchaseRequestStatus,
  PurchaseRequestSummary,
} from '../types'

const emptySummary: PurchaseRequestSummary = {
  total: 0,
  pending_approval: 0,
  approved: 0,
  rejected: 0,
  sent_back: 0,
  purchase_completed: 0,
  estimated_value: 0,
  approved_value: 0,
  departments: [],
}

const initialForm = {
  requesting_department: '',
  requested_employee: '',
  item_type: 'hardware',
  item_name: '',
  item_description: '',
  quantity: '1',
  estimated_unit_price: '',
  estimated_total_amount: '',
  business_reason: '',
  required_by_date: '',
  priority: 'medium',
  it_remarks: '',
}

function formatMoney(value?: number) {
  if (value === undefined || value === null) return '—'
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(value)
}

function formatDateTime(value?: string) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Kolkata',
  }).format(new Date(value))
}

function labelStatus(status: string) {
  return status.replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase())
}

export function PurchaseRequestsPage() {
  const { user } = useAuth()
  const { selectedMonth } = useITMonthUrl()
  const navigate = useNavigate()
  const formRef = useRef<HTMLElement | null>(null)
  const canCreate = !!user && (user.role === 'it' || isFullAccessRole(user.role))
  const canApprove = user?.role === 'management'

  const [summary, setSummary] = useState<PurchaseRequestSummary>(emptySummary)
  const [records, setRecords] = useState<ITPurchaseRequest[]>([])
  const [selected, setSelected] = useState<ITPurchaseRequest | null>(null)
  const [form, setForm] = useState(initialForm)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [statusFilter, setStatusFilter] = useState<'all' | PurchaseRequestStatus>('all')
  const [departmentFilter, setDepartmentFilter] = useState('')
  const [priorityFilter, setPriorityFilter] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [decisionAction, setDecisionAction] = useState<'approve' | 'reject' | 'send_back'>('approve')
  const [approvedAmount, setApprovedAmount] = useState('')
  const [managementRemarks, setManagementRemarks] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  function buildQuery(includeStatus = true) {
    const params = new URLSearchParams({ month: selectedMonth })
    if (includeStatus && statusFilter !== 'all') params.set('status', statusFilter)
    if (departmentFilter) params.set('department', departmentFilter)
    if (priorityFilter) params.set('priority', priorityFilter)
    if (search) params.set('search', search)
    return params.toString()
  }

  async function loadData() {
    setError('')
    try {
      const [summaryResult, recordResult] = await Promise.all([
        apiFetch<PurchaseRequestSummary>(`/it-activity/purchase-requests/summary?${buildQuery(false)}`),
        apiFetch<ITPurchaseRequest[]>(`/it-activity/purchase-requests?${buildQuery(true)}&limit=1000`),
      ])
      setSummary(summaryResult)
      setRecords(recordResult)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load purchase requests')
    }
  }

  useEffect(() => {
    void loadData()
  }, [selectedMonth, statusFilter, departmentFilter, priorityFilter, search])

  async function openDetails(id: number) {
    setBusy(`view-${id}`)
    setError('')
    try {
      const detail = await apiFetch<ITPurchaseRequest>(`/it-activity/purchase-requests/${id}`)
      setSelected(detail)
      setDecisionAction('approve')
      setApprovedAmount(detail.estimated_total_amount ? String(detail.estimated_total_amount) : '')
      setManagementRemarks('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load request details')
    } finally {
      setBusy('')
    }
  }

  async function submitRequest(event: FormEvent) {
    event.preventDefault()
    setBusy('save')
    setMessage('')
    setError('')
    try {
      const payload = {
        ...form,
        reporting_month: selectedMonth,
        quantity: Number(form.quantity),
        estimated_unit_price: form.estimated_unit_price ? Number(form.estimated_unit_price) : null,
        estimated_total_amount: form.estimated_total_amount ? Number(form.estimated_total_amount) : null,
        required_by_date: form.required_by_date || null,
      }
      const path = editingId
        ? `/it-activity/purchase-requests/${editingId}/resubmit`
        : '/it-activity/purchase-requests'
      const result = await apiFetch<ITPurchaseRequest>(path, {
        method: editingId ? 'PUT' : 'POST',
        body: JSON.stringify(payload),
      })
      setMessage(
        editingId
          ? `${result.request_code} was updated and resubmitted for management approval.`
          : `${result.request_code} was submitted for management approval.`,
      )
      setForm(initialForm)
      setEditingId(null)
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to save purchase request')
    } finally {
      setBusy('')
    }
  }

  function editSentBack(record: ITPurchaseRequest) {
    setEditingId(record.id)
    setForm({
      requesting_department: record.requesting_department,
      requested_employee: record.requested_employee,
      item_type: record.item_type,
      item_name: record.item_name,
      item_description: record.item_description || '',
      quantity: String(record.quantity),
      estimated_unit_price: record.estimated_unit_price ? String(record.estimated_unit_price) : '',
      estimated_total_amount: record.estimated_total_amount ? String(record.estimated_total_amount) : '',
      business_reason: record.business_reason,
      required_by_date: record.required_by_date || '',
      priority: record.priority,
      it_remarks: record.it_remarks || '',
    })
    setSelected(null)
    window.setTimeout(() => formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0)
  }

  async function submitDecision() {
    if (!selected) return
    setBusy('decision')
    setMessage('')
    setError('')
    try {
      const result = await apiFetch<ITPurchaseRequest>(
        `/it-activity/purchase-requests/${selected.id}/decision`,
        {
          method: 'POST',
          body: JSON.stringify({
            action: decisionAction,
            approved_amount: approvedAmount ? Number(approvedAmount) : null,
            management_remarks: managementRemarks || null,
          }),
        },
      )
      setSelected(result)
      setMessage(`${result.request_code} is now ${labelStatus(result.status)}.`)
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to save management decision')
    } finally {
      setBusy('')
    }
  }

  function createPurchase(record: ITPurchaseRequest) {
    const params = new URLSearchParams({ month: selectedMonth, requestId: String(record.id) })
    navigate(`/it/purchases?${params.toString()}`)
  }

  async function exportExcel() {
    setBusy('excel')
    setError('')
    try {
      await downloadFile(
        `/it-activity/purchase-requests.xlsx?${buildQuery(true)}`,
        `NakshaTech Purchase Requests - ${selectedMonth}.xlsx`,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to download Excel report')
    } finally {
      setBusy('')
    }
  }

  const cards: Array<{
    label: string
    value: number | string
    status?: PurchaseRequestStatus | 'all'
    icon: typeof FileCheck2
    tone: string
    note?: string
  }> = [
    { label: 'Total Requests', value: summary.total, status: 'all', icon: FileCheck2, tone: 'blue' },
    { label: 'Pending Approval', value: summary.pending_approval, status: 'pending_approval', icon: Clock3, tone: 'amber' },
    { label: 'Approved', value: summary.approved, status: 'approved', icon: CheckCircle2, tone: 'green' },
    { label: 'Rejected', value: summary.rejected, status: 'rejected', icon: ThumbsDown, tone: 'red' },
    { label: 'Sent Back', value: summary.sent_back, status: 'sent_back', icon: RotateCcw, tone: 'purple' },
    { label: 'Purchase Completed', value: summary.purchase_completed, status: 'purchase_completed', icon: PackageCheck, tone: 'teal' },
    { label: 'Estimated Value', value: formatMoney(summary.estimated_value), icon: IndianRupee, tone: 'blue' },
    { label: 'Approved Value', value: formatMoney(summary.approved_value), icon: IndianRupee, tone: 'green' },
  ]

  return (
    <>
      <DashboardHeader
        eyebrow="PURCHASE GOVERNANCE"
        title="Purchase Permission & Approvals"
        description={`Track requests, management decisions and completed procurement for ${monthLabel(selectedMonth)}. Quotation and supporting documents are not required for permission requests.`}
      />

      {message && <div className="success-message">{message}</div>}
      {error && <div className="error-message">{error}</div>}

      <section className="stats-grid purchase-approval-stats">
        {cards.map(card => (
          <StatCard
            key={card.label}
            icon={card.icon}
            label={card.label}
            value={card.value}
            note={card.note}
            tone={card.tone}
            onClick={card.status ? () => setStatusFilter(card.status!) : undefined}
            active={card.status ? statusFilter === card.status : false}
          />
        ))}
      </section>

      {canCreate && (
        <section ref={formRef} className="panel activity-entry-panel purchase-request-form-panel">
          <div className="panel-title-row">
            <div>
              <span className="section-kicker">{editingId ? 'RESUBMIT REQUEST' : 'NEW PERMISSION REQUEST'}</span>
              <h2>{editingId ? 'Update Sent-Back Request' : 'Ask Management for Purchase Permission'}</h2>
            </div>
            <FileCheck2 />
          </div>
          <form className="activity-form-grid" onSubmit={submitRequest}>
            <label>
              <span>Requesting Department</span>
              <input required value={form.requesting_department} onChange={event => setForm({ ...form, requesting_department: event.target.value })} />
            </label>
            <label>
              <span>Requested By Employee</span>
              <input required value={form.requested_employee} onChange={event => setForm({ ...form, requested_employee: event.target.value })} />
            </label>
            <label>
              <span>Item Type</span>
              <select value={form.item_type} onChange={event => setForm({ ...form, item_type: event.target.value })}>
                <option value="hardware">Hardware</option>
                <option value="software">Software</option>
                <option value="other">Other</option>
              </select>
            </label>
            <label>
              <span>Item Name</span>
              <input required value={form.item_name} onChange={event => setForm({ ...form, item_name: event.target.value })} />
            </label>
            <label className="span-2">
              <span>Item Description</span>
              <textarea value={form.item_description} onChange={event => setForm({ ...form, item_description: event.target.value })} />
            </label>
            <label>
              <span>Quantity</span>
              <input required type="number" min="0.01" step="0.01" value={form.quantity} onChange={event => setForm({ ...form, quantity: event.target.value })} />
            </label>
            <label>
              <span>Estimated Unit Price (INR)</span>
              <input type="number" min="0" step="0.01" value={form.estimated_unit_price} onChange={event => setForm({ ...form, estimated_unit_price: event.target.value })} />
            </label>
            <label>
              <span>Estimated Total Amount (INR)</span>
              <input type="number" min="0" step="0.01" value={form.estimated_total_amount} onChange={event => setForm({ ...form, estimated_total_amount: event.target.value })} placeholder="Calculated from unit price if blank" />
            </label>
            <label>
              <span>Required By Date</span>
              <input type="date" value={form.required_by_date} onChange={event => setForm({ ...form, required_by_date: event.target.value })} />
            </label>
            <label>
              <span>Priority</span>
              <select value={form.priority} onChange={event => setForm({ ...form, priority: event.target.value })}>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </label>
            <label className="span-2">
              <span>Business Requirement / Reason</span>
              <textarea required value={form.business_reason} onChange={event => setForm({ ...form, business_reason: event.target.value })} />
            </label>
            <label className="span-2">
              <span>IT Remarks</span>
              <textarea value={form.it_remarks} onChange={event => setForm({ ...form, it_remarks: event.target.value })} />
            </label>
            <div className="span-2 form-actions">
              {editingId && (
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => {
                    setEditingId(null)
                    setForm(initialForm)
                  }}
                >
                  <X size={17} /> Cancel Edit
                </button>
              )}
              <button className="primary-button" disabled={busy === 'save'}>
                <Send size={17} /> {busy === 'save' ? 'Submitting…' : editingId ? 'Resubmit for Approval' : 'Submit for Approval'}
              </button>
            </div>
          </form>
        </section>
      )}

      <section className="panel purchase-request-register">
        <div className="panel-title-row">
          <div>
            <span className="section-kicker">APPROVAL REGISTER</span>
            <h2>{monthLabel(selectedMonth)} Purchase Requests</h2>
          </div>
          <div className="purchase-request-toolbar-actions">
            <span className="record-count">{records.length}</span>
            <button className="secondary-button" onClick={() => void exportExcel()} disabled={busy === 'excel'}>
              <Download size={17} /> {busy === 'excel' ? 'Preparing…' : 'Download Excel'}
            </button>
          </div>
        </div>

        <div className="filter-bar purchase-request-filters">
          <label>
            <span>Status</span>
            <select value={statusFilter} onChange={event => setStatusFilter(event.target.value as 'all' | PurchaseRequestStatus)}>
              <option value="all">All statuses</option>
              <option value="pending_approval">Pending Approval</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
              <option value="sent_back">Sent Back</option>
              <option value="purchase_completed">Purchase Completed</option>
            </select>
          </label>
          <label>
            <span>Department</span>
            <select value={departmentFilter} onChange={event => setDepartmentFilter(event.target.value)}>
              <option value="">All departments</option>
              {summary.departments.map(department => <option key={department} value={department}>{department}</option>)}
            </select>
          </label>
          <label>
            <span>Priority</span>
            <select value={priorityFilter} onChange={event => setPriorityFilter(event.target.value)}>
              <option value="">All priorities</option>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
          </label>
          <label className="purchase-request-search">
            <span>Search</span>
            <div>
              <input value={searchInput} onChange={event => setSearchInput(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') setSearch(searchInput.trim()) }} placeholder="Request, employee, item or department" />
              <button type="button" onClick={() => setSearch(searchInput.trim())}><Search size={16} /> Search</button>
            </div>
          </label>
        </div>

        <div className="table-scroll">
          <table className="activity-table purchase-request-table">
            <thead>
              <tr>
                <th>Request</th>
                <th>Department / Employee</th>
                <th>Item</th>
                <th>Qty</th>
                <th>Estimated</th>
                <th>Priority</th>
                <th>Status</th>
                <th>Requested</th>
                <th>Decision / Purchase</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {records.map(record => (
                <tr key={record.id}>
                  <td><strong>{record.request_code}</strong><small>{record.reporting_month}</small></td>
                  <td>{record.requesting_department}<small>{record.requested_employee}</small></td>
                  <td>{record.item_name}<small>{record.item_type}</small></td>
                  <td>{record.quantity}</td>
                  <td>{formatMoney(record.estimated_total_amount)}</td>
                  <td><span className={`priority priority-${record.priority}`}>{record.priority}</span></td>
                  <td><span className={`status ${record.status}`}>{labelStatus(record.status)}</span></td>
                  <td>{formatDateTime(record.requested_at)}<small>{record.requested_by_name}</small></td>
                  <td>
                    {record.purchase_code || record.decided_by_name || 'Awaiting management'}
                    <small>{record.purchase_code ? formatMoney(record.actual_purchase_amount) : record.decided_at ? formatDateTime(record.decided_at) : ''}</small>
                  </td>
                  <td>
                    <div className="record-actions purchase-request-actions">
                      <button className="secondary-button" onClick={() => void openDetails(record.id)} disabled={busy === `view-${record.id}`}>
                        <Eye size={15} /> View
                      </button>
                      {canCreate && record.status === 'sent_back' && (
                        <button className="secondary-button" onClick={() => editSentBack(record)}>
                          <PencilLine size={15} /> Edit
                        </button>
                      )}
                      {canCreate && record.status === 'approved' && !record.purchase_record_id && (
                        <button className="primary-button" onClick={() => createPurchase(record)}>
                          <ShoppingCart size={15} /> Purchase
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {records.length === 0 && (
                <tr><td colSpan={10}><div className="empty-state">No purchase requests match the selected filters.</div></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {selected && (
        <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) setSelected(null) }}>
          <section className="modal-card purchase-request-modal">
            <button className="icon-button modal-close" onClick={() => setSelected(null)} aria-label="Close"><X /></button>
            <div className="modal-heading">
              <FileCheck2 />
              <div>
                <span className="section-kicker">PURCHASE REQUEST DETAILS</span>
                <h2>{selected.request_code}</h2>
              </div>
            </div>

            <div className="purchase-request-detail-grid">
              <div><span>Status</span><strong><span className={`status ${selected.status}`}>{labelStatus(selected.status)}</span></strong></div>
              <div><span>Requesting Department</span><strong>{selected.requesting_department}</strong></div>
              <div><span>Requested Employee</span><strong>{selected.requested_employee}</strong></div>
              <div><span>Item</span><strong>{selected.item_name}</strong></div>
              <div><span>Type / Quantity</span><strong>{selected.item_type} · {selected.quantity}</strong></div>
              <div><span>Estimated Amount</span><strong>{formatMoney(selected.estimated_total_amount)}</strong></div>
              <div><span>Requested By IT</span><strong>{selected.requested_by_name}<small>{selected.requested_by_email}</small></strong></div>
              <div><span>Requested At</span><strong>{formatDateTime(selected.requested_at)}</strong></div>
              <div><span>Required By</span><strong>{selected.required_by_date || 'Not specified'}</strong></div>
              <div><span>Priority</span><strong>{labelStatus(selected.priority)}</strong></div>
              <div><span>Management Decision</span><strong>{selected.decided_by_name || 'Awaiting management'}<small>{formatDateTime(selected.decided_at)}</small></strong></div>
              <div><span>Approved Amount</span><strong>{formatMoney(selected.approved_amount)}</strong></div>
              <div className="span-2"><span>Business Requirement</span><strong>{selected.business_reason}</strong></div>
              <div className="span-2"><span>Item Description</span><strong>{selected.item_description || 'Not provided'}</strong></div>
              <div className="span-2"><span>IT Remarks</span><strong>{selected.it_remarks || 'Not provided'}</strong></div>
              <div className="span-2"><span>Management Remarks</span><strong>{selected.management_remarks || 'Not provided'}</strong></div>
              {selected.purchase_code && (
                <div className="span-2 purchase-link-summary">
                  <PackageCheck />
                  <div><span>Linked Purchase Record</span><strong>{selected.purchase_code} · {formatMoney(selected.actual_purchase_amount)} · {selected.purchase_date}</strong></div>
                </div>
              )}
            </div>

            {canApprove && selected.status === 'pending_approval' && (
              <section className="purchase-decision-panel">
                <h3>Management Decision</h3>
                <div className="purchase-decision-options">
                  <button type="button" className={decisionAction === 'approve' ? 'active' : ''} onClick={() => setDecisionAction('approve')}><CheckCircle2 /> Approve</button>
                  <button type="button" className={decisionAction === 'send_back' ? 'active' : ''} onClick={() => setDecisionAction('send_back')}><RotateCcw /> Send Back</button>
                  <button type="button" className={decisionAction === 'reject' ? 'active' : ''} onClick={() => setDecisionAction('reject')}><ThumbsDown /> Reject</button>
                </div>
                {decisionAction === 'approve' && (
                  <label><span>Approved Amount (INR)</span><input type="number" min="0" step="0.01" value={approvedAmount} onChange={event => setApprovedAmount(event.target.value)} /></label>
                )}
                <label><span>Management Remarks {decisionAction !== 'approve' && '*'}</span><textarea value={managementRemarks} onChange={event => setManagementRemarks(event.target.value)} /></label>
                <button className={decisionAction === 'reject' ? 'danger-button' : 'primary-button'} onClick={() => void submitDecision()} disabled={busy === 'decision'}>
                  {decisionAction === 'approve' ? <CheckCircle2 size={17} /> : decisionAction === 'send_back' ? <RotateCcw size={17} /> : <ThumbsDown size={17} />}
                  {busy === 'decision' ? 'Saving…' : `Confirm ${labelStatus(decisionAction)}`}
                </button>
              </section>
            )}

            <section className="purchase-request-history">
              <h3>Request & Approval History</h3>
              <div className="timeline">
                {selected.histories.map(history => (
                  <div key={history.id}>
                    <i />
                    <p>
                      <strong>{labelStatus(history.action)} · {labelStatus(history.to_status)}</strong>
                      <span>{history.performed_by_name} ({history.performed_by_role})</span>
                      <small>{formatDateTime(history.created_at)}{history.remarks ? ` · ${history.remarks}` : ''}</small>
                    </p>
                  </div>
                ))}
              </div>
            </section>

            <div className="form-actions purchase-request-modal-actions">
              {canCreate && selected.status === 'sent_back' && (
                <button className="secondary-button" onClick={() => editSentBack(selected)}><PencilLine size={17} /> Edit & Resubmit</button>
              )}
              {canCreate && selected.status === 'approved' && !selected.purchase_record_id && (
                <button className="primary-button" onClick={() => createPurchase(selected)}><ShoppingCart size={17} /> Create Purchase Record</button>
              )}
            </div>
          </section>
        </div>
      )}
    </>
  )
}
