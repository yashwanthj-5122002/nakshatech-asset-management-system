import { Building2, RefreshCcw, Search, ShieldCheck, UserRound } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'

interface EmployeeMasterRecord {
  id: number
  employee_name: string
  employee_number: string
  access_card_no: string
  department: string
  department_code: string
  designation: string
  email: string
  employment_status: string
  crm_account_status: string
  linked_user_id: number | null
  review_reason: string | null
  imported_at: string
}

const DEPARTMENT_OPTIONS = [
  'bd', 'civil', 'digital_marketing', 'finance_admin', 'housekeeping', 'hr', 'it',
  'laser_scanning', 'lidar', 'mobile_mapping', 'ortho', 'photogrammetry',
  'project_coordination', 'reality_capture_bim', 'software_team', 'survey', 'tender',
]

const STATUS_OPTIONS = [
  'not_registered', 'email_otp_pending', 'email_verified', 'account_setup_pending',
  'authenticator_pending', 'active', 'disabled', 'needs_review',
]

const STATUS_LABELS: Record<string, string> = {
  not_registered: 'Not Registered',
  email_otp_pending: 'Email OTP Pending',
  email_verified: 'Email Verified',
  account_setup_pending: 'Account Setup Pending',
  authenticator_pending: 'Authenticator Pending',
  active: 'Active',
  disabled: 'Disabled',
  needs_review: 'Needs Review',
}

function statusTone(status: string): string {
  if (status === 'active') return 'success'
  if (status === 'needs_review' || status === 'disabled') return 'danger'
  if (status === 'not_registered') return ''
  return 'warning'
}

export function EmployeeMasterPage() {
  const [rows, setRows] = useState<EmployeeMasterRecord[]>([])
  const [status, setStatus] = useState('')
  const [department, setDepartment] = useState('')
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  function load() {
    setLoading(true)
    setError('')
    const params = new URLSearchParams()
    if (status) params.set('status', status)
    if (department) params.set('department', department)
    if (search.trim()) params.set('search', search.trim())
    const query = params.toString()
    apiFetch<EmployeeMasterRecord[]>(`/software/employee-master${query ? `?${query}` : ''}`)
      .then(setRows)
      .catch(err => setError(err instanceof Error ? err.message : 'Could not load Employee Master'))
      .finally(() => setLoading(false))
  }

  useEffect(load, [status, department, search])

  const counts = useMemo(() => {
    const byStatus: Record<string, number> = {}
    for (const row of rows) byStatus[row.crm_account_status] = (byStatus[row.crm_account_status] || 0) + 1
    return byStatus
  }, [rows])

  return (
    <div className="operations-page">
      <DashboardHeader
        eyebrow="SOFTWARE TEAM · EMPLOYEE MASTER"
        title="Employee Master Directory"
        description="HR-owned employee identity source. CRM account status, employment status and review reasons are visible here; passwords, OTP and TOTP secrets are never exposed."
        actions={<button className="operations-button secondary" onClick={load}><RefreshCcw size={16} /> Refresh</button>}
      />

      <section className="operations-panel">
        <header>
          <div>
            <span className="operations-kicker">WORKFORCE IDENTITY</span>
            <h2>Employee Master records</h2>
            <p>{rows.length} records · {counts['active'] || 0} active CRM · {counts['needs_review'] || 0} need review</p>
          </div>
        </header>
        <div className="operations-toolbar" style={{ marginBottom: 14 }}>
          <label className="operations-search"><Search size={16} />
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search name, email, employee number, access card..." />
          </label>
          <label className="operations-field"><span>CRM Status</span>
            <select value={status} onChange={e => setStatus(e.target.value)}>
              <option value="">All statuses</option>
              {STATUS_OPTIONS.map(item => <option key={item} value={item}>{STATUS_LABELS[item] || item}</option>)}
            </select>
          </label>
          <label className="operations-field"><span>Department</span>
            <select value={department} onChange={e => setDepartment(e.target.value)}>
              <option value="">All departments</option>
              {DEPARTMENT_OPTIONS.map(item => <option key={item} value={item}>{item.replaceAll('_', ' ')}</option>)}
            </select>
          </label>
        </div>
        {error && <div className="operations-alert error">{error}</div>}
        {loading ? <div className="operations-empty">Loading Employee Master...</div> : !rows.length ? (
          <div className="operations-empty">No Employee Master records match these filters.</div>
        ) : (
          <div className="operations-table-wrap"><table className="operations-table">
            <thead><tr><th>Employee</th><th>Employee Number</th><th>Access Card</th><th>Department</th><th>Designation</th><th>Official Email</th><th>Employment</th><th>CRM Account</th><th>Review</th></tr></thead>
            <tbody>{rows.map(row => (
              <tr key={row.id}>
                <td><strong>{row.employee_name}</strong></td>
                <td>{row.employee_number}</td>
                <td>{row.access_card_no}</td>
                <td>{row.department}</td>
                <td>{row.designation}</td>
                <td>{row.email}</td>
                <td><span className="operations-status">{row.employment_status}</span></td>
                <td><span className={`operations-status ${statusTone(row.crm_account_status)}`}>{STATUS_LABELS[row.crm_account_status] || row.crm_account_status}</span></td>
                <td>{row.review_reason ? <span className="operations-alert warning" style={{ display: 'inline-flex', padding: '4px 10px' }}>{row.review_reason}</span> : <span className="muted">—</span>}</td>
              </tr>
            ))}</tbody>
          </table></div>
        )}
      </section>
    </div>
  )
}
