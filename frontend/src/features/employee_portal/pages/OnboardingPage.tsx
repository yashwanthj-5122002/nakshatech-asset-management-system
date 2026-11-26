import { Building2, CheckCircle2, CircleDot, Mail, Phone, RefreshCcw, Send, UserRound, XCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch } from '../../../lib/api'

interface OnboardingRequest {
  id: number
  employee_name: string
  personal_email: string
  phone: string
  employee_number: string
  access_card_no: string
  department_code: string
  designation: string
  joining_date: string | null
  notes: string | null
  status: string
  official_email: string | null
  decided_by: string | null
  created_by_user_id: number
  submitted_to_it_at: string | null
  it_approved_at: string | null
  management_approved_at: string | null
  rejected_reason: string | null
  employee_master_id: number | null
  created_at: string
}

const DEPARTMENT_OPTIONS = [
  'bd', 'civil', 'digital_marketing', 'finance_admin', 'housekeeping', 'hr', 'it',
  'laser_scanning', 'lidar', 'mobile_mapping', 'ortho', 'photogrammetry',
  'project_coordination', 'reality_capture_bim', 'software_team', 'survey', 'tender',
]

const STATUS_LABELS: Record<string, string> = {
  hr_draft: 'HR Draft',
  hr_submitted: 'Submitted to IT',
  management_pending: 'Management Pending',
  final_approved: 'Final Approved',
  rejected: 'Rejected',
}

function statusTone(status: string): string {
  if (status === 'final_approved') return 'success'
  if (status === 'rejected') return 'danger'
  if (status === 'hr_draft') return ''
  return 'warning'
}

const EMPTY_FORM = {
  employee_name: '',
  personal_email: '',
  phone: '',
  employee_number: '',
  access_card_no: '',
  department_code: 'ortho',
  designation: '',
  joining_date: '',
  notes: '',
}

export function OnboardingPage() {
  const { user } = useAuth()
  const role = user?.role || ''
  const canCreate = role === 'hr'
  const canItApprove = role === 'it'
  const canManage = role === 'management'
  const [rows, setRows] = useState<OnboardingRequest[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [officialEmail, setOfficialEmail] = useState<Record<number, string>>({})
  const [busy, setBusy] = useState(0)

  function load() {
    setLoading(true)
    setError('')
    apiFetch<OnboardingRequest[]>('/onboarding/requests')
      .then(setRows)
      .catch(err => setError(err instanceof Error ? err.message : 'Could not load onboarding requests'))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  async function run(action: () => Promise<unknown>, successMessage: string) {
    setBusy(1); setError(''); setNotice('')
    try {
      await action()
      setNotice(successMessage)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Action failed')
    } finally {
      setBusy(0)
    }
  }

  function createDraft() {
    const payload = { ...form, joining_date: form.joining_date || null, notes: form.notes || null }
    return run(async () => {
      await apiFetch('/onboarding/requests', { method: 'POST', body: JSON.stringify(payload) })
      setShowForm(false)
      setForm(EMPTY_FORM)
    }, 'New Joiner draft created.')
  }

  return (
    <div className="operations-page">
      <DashboardHeader
        eyebrow="NEW JOINER ONBOARDING"
        title="New Joiner Workflow"
        description="HR creates the record, IT assigns the official email, and Management gives final approval. The new joiner then self-registers with the official email."
        actions={<>
          {canCreate && <button className="operations-button" onClick={() => setShowForm(value => !value)}><UserRound size={16} /> New Joiner</button>}
          <button className="operations-button secondary" onClick={load}><RefreshCcw size={16} /> Refresh</button>
        </>}
      />
      {error && <div className="operations-alert error">{error}</div>}
      {notice && <div className="operations-alert success">{notice}</div>}

      {showForm && canCreate && (
        <section className="operations-panel">
          <header>
            <div>
              <span className="operations-kicker">HR · NEW JOINER DRAFT</span>
              <h2>Create New Joiner record</h2>
              <p>Enter the employee's personal email and identity details. IT will create the official NakshaTech email after submission.</p>
            </div>
          </header>
          <div className="operations-form-grid">
            <label className="operations-field"><span>Employee Name *</span><input value={form.employee_name} onChange={e => setForm({ ...form, employee_name: e.target.value })} required /></label>
            <label className="operations-field"><span>Personal Email *</span><input type="email" value={form.personal_email} onChange={e => setForm({ ...form, personal_email: e.target.value })} placeholder="name@gmail.com" required /></label>
            <label className="operations-field"><span>Phone *</span><input value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} placeholder="+91..." required /></label>
            <label className="operations-field"><span>Employee Number *</span><input value={form.employee_number} onChange={e => setForm({ ...form, employee_number: e.target.value })} required /></label>
            <label className="operations-field"><span>Access Card Number *</span><input value={form.access_card_no} onChange={e => setForm({ ...form, access_card_no: e.target.value })} required /></label>
            <label className="operations-field"><span>Department *</span><select value={form.department_code} onChange={e => setForm({ ...form, department_code: e.target.value })}>{DEPARTMENT_OPTIONS.map(item => <option key={item} value={item}>{item.replaceAll('_', ' ')}</option>)}</select></label>
            <label className="operations-field"><span>Designation *</span><input value={form.designation} onChange={e => setForm({ ...form, designation: e.target.value })} required /></label>
            <label className="operations-field"><span>Joining Date</span><input type="date" value={form.joining_date} onChange={e => setForm({ ...form, joining_date: e.target.value })} /></label>
            <label className="operations-field" style={{ gridColumn: '1 / -1' }}><span>Notes</span><textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} /></label>
          </div>
          <div className="operations-actions">
            <button className="operations-button" disabled={busy === 1} onClick={() => void createDraft()}><Send size={15} /> Save Draft</button>
            <button className="operations-button secondary" onClick={() => setShowForm(false)}>Cancel</button>
          </div>
        </section>
      )}

      <section className="operations-panel">
        <header>
          <div>
            <span className="operations-kicker">ONBOARDING QUEUE</span>
            <h2>New Joiner requests</h2>
            <p>{rows.length} requests visible to your role.</p>
          </div>
        </header>
        {loading ? <div className="operations-empty">Loading requests...</div> : !rows.length ? (
          <div className="operations-empty">No onboarding requests yet.</div>
        ) : (
          <div className="operations-table-wrap"><table className="operations-table">
            <thead><tr><th>Employee</th><th>Employee Number</th><th>Department</th><th>Personal Email</th><th>Official Email</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>{rows.map(row => (
              <tr key={row.id}>
                <td><strong>{row.employee_name}</strong><small>{row.designation}</small></td>
                <td>{row.employee_number}</td>
                <td>{row.department_code.replaceAll('_', ' ')}</td>
                <td>{row.personal_email}</td>
                <td>{row.official_email || <span className="muted">—</span>}</td>
                <td><span className={`operations-status ${statusTone(row.status)}`}>{STATUS_LABELS[row.status] || row.status}</span></td>
                <td><div className="operations-actions">
                  {canCreate && row.status === 'hr_draft' && (
                    <button className="operations-button" disabled={busy === 1} onClick={() => void run(() => apiFetch(`/onboarding/requests/${row.id}/submit`, { method: 'POST' }), 'Submitted to IT.')}>
                      <Send size={14} /> Submit to IT
                    </button>
                  )}
                  {canItApprove && row.status === 'hr_submitted' && (
                    <form className="operations-actions" onSubmit={e => {
                      e.preventDefault()
                      const email = (officialEmail[row.id] || '').trim()
                      if (!email) { setError('Enter the official email first.'); return }
                      void run(() => apiFetch(`/onboarding/requests/${row.id}/it-approve`, { method: 'POST', body: JSON.stringify({ official_email: email }) }), 'Official email created. Request sent to Management.')
                    }}>
                      <input value={officialEmail[row.id] || ''} onChange={e => setOfficialEmail({ ...officialEmail, [row.id]: e.target.value })} placeholder="name@nakshatech.com" style={{ minWidth: 200 }} />
                      <button className="operations-button" disabled={busy === 1}><Mail size={14} /> IT Approve</button>
                    </form>
                  )}
                  {canManage && row.status === 'management_pending' && (
                    <button className="operations-button success" disabled={busy === 1} onClick={() => void run(() => apiFetch(`/onboarding/requests/${row.id}/management-approve`, { method: 'POST' }), 'Final approval recorded. New joiner notified by personal email.')}>
                      <CheckCircle2 size={14} /> Final Approve
                    </button>
                  )}
                  {(canCreate || canItApprove || canManage) && !['final_approved', 'rejected'].includes(row.status) && (
                    <button className="operations-button danger" disabled={busy === 1} onClick={() => void run(() => apiFetch(`/onboarding/requests/${row.id}/reject`, { method: 'POST', body: JSON.stringify({ reason: 'Rejected during review' }) }), 'Request rejected.')}>
                      <XCircle size={14} /> Reject
                    </button>
                  )}
                </div></td>
              </tr>
            ))}</tbody>
          </table></div>
        )}
      </section>
    </div>
  )
}
