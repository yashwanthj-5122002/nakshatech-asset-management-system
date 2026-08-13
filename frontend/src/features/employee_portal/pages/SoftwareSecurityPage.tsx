import { Activity, RefreshCcw, Search, ShieldCheck, Users } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch } from '../../../lib/api'
import type { AuditEvent, SoftwareUser } from '../../../types'

type Tab = 'users' | 'audit'

const managementTitles: Record<string, string> = {
  'vinod@nakshatech.com': 'Managing Director',
  'chethan@nakshatech.com': 'Technical Director',
}

function managementRoleTitle(user: SoftwareUser): string {
  return managementTitles[user.email.trim().toLowerCase()] || user.role.replaceAll('_', ' ')
}

function managementRoleDepartment(user: SoftwareUser): string {
  return managementTitles[user.email.trim().toLowerCase()] ? 'Management' : `${user.department || '—'}${user.designation ? ` · ${user.designation}` : ''}`
}

const HIDDEN_AUDIT_DETAIL_KEYS = [
  'password',
  'password_hash',
  'otp',
  'token',
  'secret',
  'qr',
  'api_key',
  'smtp',
]

function formatAuditDetails(details?: string): string {
  if (!details) return '—'
  try {
    const parsed = JSON.parse(details)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return String(parsed)
    const parts = Object.entries(parsed)
      .filter(([key]) => !HIDDEN_AUDIT_DETAIL_KEYS.some(hidden => key.toLowerCase().includes(hidden)))
      .map(([key, value]) => {
        const label = key.replaceAll('_', ' ')
        const text = value && typeof value === 'object' ? JSON.stringify(value) : String(value)
        return `${label}: ${text}`
      })
    return parts.length ? parts.join(' · ') : 'Protected security details'
  } catch {
    return details
  }
}

export function SoftwareSecurityPage() {
  const { user: currentUser } = useAuth()
  const managementView = currentUser?.role === 'management'
  const [tab, setTab] = useState<Tab>('users')
  const [users, setUsers] = useState<SoftwareUser[]>([])
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  function load() {
    setError('')
    void Promise.all([
      apiFetch<SoftwareUser[]>('/software/users'),
      apiFetch<AuditEvent[]>('/software/audit?limit=500'),
    ]).then(([userItems, auditItems]) => { setUsers(userItems); setEvents(auditItems) })
      .catch(err => setError(err instanceof Error ? err.message : 'Could not load security data'))
  }
  useEffect(load, [])

  const filteredUsers = useMemo(() => {
    const term = query.trim().toLowerCase()
    if (!term) return users
    return users.filter(user => [user.full_name, user.email, user.employee_id || '', user.department || '', user.role, user.branch].some(value => value.toLowerCase().includes(term)))
  }, [users, query])
  const filteredEvents = useMemo(() => {
    const term = query.trim().toLowerCase()
    if (!term) return events
    return events.filter(event => [event.actor_email || '', event.event_type, event.result, event.branch_name || '', event.module || '', event.ip_address || ''].some(value => value.toLowerCase().includes(term)))
  }, [events, query])



  return <>
    <DashboardHeader
      eyebrow={managementView ? 'MANAGEMENT · USER & ACTIVITY OVERSIGHT' : 'SOFTWARE TEAM · SECURITY & AUDIT'}
      title={managementView ? 'Organization Access & Activity' : 'User Access & Activity Monitor'}
      description={managementView
        ? 'Read-only oversight of user accounts, login and logout activity, module visits, ticket actions, and other recorded system events. Passwords, OTP values, secrets, and tokens are never displayed.'
        : 'Review verified employees, one-time Authenticator activation status, password sign-ins, branch selections, password-reset events, and important CRM actions. Passwords, OTP values, secrets, and tokens are never displayed.'}
    />
    <section className="panel-card software-security-panel">
      <div className="software-security-toolbar">
        <div className="software-security-tabs"><button className={tab === 'users' ? 'active' : ''} onClick={() => setTab('users')}><Users size={17} />Users</button><button className={tab === 'audit' ? 'active' : ''} onClick={() => setTab('audit')}><Activity size={17} />Audit Events</button></div>
        <label className="ticket-search"><Search size={17} /><input value={query} onChange={e => setQuery(e.target.value)} placeholder={tab === 'users' ? 'Search employee, email, department, or branch' : 'Search event, user, branch, IP, or module'} /></label>
        <button className="secondary-button" onClick={load}><RefreshCcw size={16} />Refresh</button>
      </div>
      {notice && <div className="success-message">{notice}</div>}
      {error && <div className="error-message">{error}</div>}
      {tab === 'users' ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Employee</th><th>Role & Department</th><th>Branch</th><th>Verification</th><th>Last Login</th><th>Account</th><th>Security</th></tr></thead><tbody>{filteredUsers.map(user => <tr key={user.id}><td><strong>{user.full_name}</strong><small>{user.email}</small><small>{user.employee_id || 'No employee ID'}</small></td><td><strong>{managementRoleTitle(user)}</strong><small>{managementRoleDepartment(user)}</small></td><td>{user.branch}</td><td><span className={user.email_verified ? 'verification-ok' : 'verification-pending'}>{user.email_verified ? 'Email verified' : 'Email not verified'}</span><small>{user.phone_masked || 'No phone provided'}</small></td><td>{user.last_login_at ? new Date(user.last_login_at).toLocaleString() : 'Never'}</td><td><span className={`ticket-status ${user.is_active ? 'status-resolved' : 'status-closed'}`}>{user.account_status}</span></td><td><div className="security-cell"><span><ShieldCheck size={15} />{user.mfa_enabled ? 'Registration Authenticator verified' : 'Authenticator not verified'}</span></div></td></tr>)}</tbody></table></div>
      : <div className="table-wrap"><table className="data-table"><thead><tr><th>Time</th><th>User</th><th>Event</th><th>Branch / Module</th><th>Result</th><th>Action Details</th><th>Device Context</th></tr></thead><tbody>{filteredEvents.map(event => <tr key={event.id}><td>{new Date(event.created_at).toLocaleString()}</td><td>{event.actor_email || 'System'}</td><td><strong>{event.event_type.replaceAll('_', ' ')}</strong><small>{event.target_type && event.target_id ? `${event.target_type} #${event.target_id}` : ''}</small></td><td><strong>{event.branch_name || '—'}</strong><small>{event.module || '—'}</small></td><td><span className={`audit-result result-${event.result}`}>{event.result}</span></td><td><small title={event.details || ''}>{formatAuditDetails(event.details)}</small></td><td><small>{event.ip_address || 'No IP'}</small><small title={event.user_agent}>{event.user_agent ? event.user_agent.slice(0, 58) : 'No user agent'}</small></td></tr>)}</tbody></table></div>}
    </section>
  </>
}
