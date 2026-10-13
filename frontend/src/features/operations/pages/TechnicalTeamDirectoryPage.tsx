import {
  CheckCircle2,
  LockKeyhole,
  RefreshCcw,
  Save,
  ShieldAlert,
  ShieldCheck,
  UserPlus,
  Users,
  XCircle,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { StatCard } from '../../../components/StatCard'
import { apiFetch } from '../../../lib/api'
import '../operations.css'
import '../technical-team-directory.css'

type ViewerMode = 'admin_editor' | 'read_only' | 'department_read_only'

type UserOption = {
  id: number
  full_name: string
  email: string
  employee_id?: string | null
  designation?: string | null
  role: string
}

type Member = UserOption & {
  department_code: string
  user_id: number
  stored_role?: string | null
  user_active: boolean
  role_match: boolean
  pm_eligible: boolean
  receive_sample_notifications: boolean
  receive_handover_notifications: boolean
  receive_completion_notifications: boolean
  is_active: boolean
  ready_for_live_use: boolean
  notes?: string | null
}

type MemberFlagKey =
  | 'pm_eligible'
  | 'receive_sample_notifications'
  | 'receive_handover_notifications'
  | 'receive_completion_notifications'

type MemberFlags = Pick<Member, MemberFlagKey>

type Department = {
  department_code: string
  department_label: string
  role: string
  routing_mode: string
  demo_account: { email?: string | null; present: boolean; active: boolean }
  configured_members: Member[]
  eligible_users: UserOption[]
  readiness: {
    configured_real_members: number
    pm_candidates: number
    sample_recipients: number
    handover_recipients: number
    completion_recipients: number
    live_ready: boolean
  }
}

type Dashboard = {
  viewer_mode: ViewerMode
  routing_mode: string
  live_technical_routing_enabled: boolean
  go_live_activation_available: boolean
  go_live_message: string
  summary: {
    visible_departments: number
    configured_real_members: number
    live_ready_departments: number
    not_ready_departments: number
  }
  departments: Department[]
  cutover: {
    routing_mode: string
    live_technical_routing_enabled: boolean
    activation_confirmation: string
    all_departments_ready: boolean
    can_activate: boolean
    blockers: { open_sample_requests: number; open_technical_workstreams: number; unresolved_handovers: number }
    activated_at?: string | null
    activated_by_name?: string | null
    activation_note?: string | null
    message: string
  }
}

function flagsFromMember(member: Member): MemberFlags {
  return {
    pm_eligible: member.pm_eligible,
    receive_sample_notifications: member.receive_sample_notifications,
    receive_handover_notifications: member.receive_handover_notifications,
    receive_completion_notifications: member.receive_completion_notifications,
  }
}

function draftsFromDashboard(data: Dashboard): Record<number, MemberFlags> {
  const next: Record<number, MemberFlags> = {}
  for (const department of data.departments) {
    for (const member of department.configured_members) next[member.id] = flagsFromMember(member)
  }
  return next
}

export function TechnicalTeamDirectoryPage() {
  const [data, setData] = useState<Dashboard | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState('')
  const [choices, setChoices] = useState<Record<string, string>>({})
  const [drafts, setDrafts] = useState<Record<number, MemberFlags>>({})
  const [activationText, setActivationText] = useState('')
  const [activationNote, setActivationNote] = useState('')

  function applyDashboard(next: Dashboard) {
    setData(next)
    setDrafts(draftsFromDashboard(next))
  }

  function load() {
    setError('')
    void apiFetch<Dashboard>('/operations/technical-team-directory/dashboard')
      .then(applyDashboard)
      .catch(err => setError(err instanceof Error ? err.message : 'Unable to load Technical Team Directory'))
  }

  useEffect(load, [])
  const editor = data?.viewer_mode === 'admin_editor'
  const title = useMemo(
    () => data?.viewer_mode === 'department_read_only' ? 'My Department · Production Readiness' : 'Technical Team Directory',
    [data],
  )

  async function addMember(department: Department) {
    const raw = choices[department.department_code]
    if (!raw) {
      setError(`Select a real ${department.department_label} ERP account first.`)
      return
    }
    setBusy(`add-${department.department_code}`)
    setError('')
    setNotice('')
    try {
      const result = await apiFetch<Dashboard>(`/operations/technical-team-directory/departments/${department.department_code}/members`, {
        method: 'POST',
        body: JSON.stringify({
          user_id: Number(raw),
          pm_eligible: true,
          receive_sample_notifications: true,
          receive_handover_notifications: true,
          receive_completion_notifications: true,
        }),
      })
      applyDashboard(result)
      setChoices(current => ({ ...current, [department.department_code]: '' }))
      setNotice(`${department.department_label} production-directory candidate added. ${result.live_technical_routing_enabled ? 'Production routing remains active.' : 'Production routing is still locked.'}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to add technical-team directory member')
    } finally {
      setBusy('')
    }
  }

  function setFlag(member: Member, key: MemberFlagKey, value: boolean) {
    setDrafts(current => ({
      ...current,
      [member.id]: {
        ...(current[member.id] || flagsFromMember(member)),
        [key]: value,
      },
    }))
  }

  async function saveFlags(member: Member) {
    const payload = drafts[member.id] || flagsFromMember(member)
    setBusy(`save-${member.id}`)
    setError('')
    setNotice('')
    try {
      const result = await apiFetch<Dashboard>(`/operations/technical-team-directory/members/${member.id}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      })
      applyDashboard(result)
      setNotice(`Responsibilities updated for ${member.full_name || member.email}. ${result.live_technical_routing_enabled ? 'Production routing remains active.' : 'Live routing is still locked.'}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to save technical-team responsibilities')
    } finally {
      setBusy('')
    }
  }

  async function activateProductionRouting() {
    if (!data?.cutover.can_activate || activationText !== data.cutover.activation_confirmation) {
      setError(`Type exactly: ${data?.cutover.activation_confirmation || 'ACTIVATE REAL TECHNICAL ROUTING'}`)
      return
    }
    if (!window.confirm('Activate REAL technical routing now? This switches PM, sample, handover, progress, completion and technical email routing from demo users to the prepared real directory.')) return
    setBusy('activate-routing')
    setError('')
    setNotice('')
    try {
      await apiFetch('/operations/technical-team-routing/activate', {
        method: 'POST',
        body: JSON.stringify({ confirmation: activationText, note: activationNote || null }),
      })
      setActivationText('')
      setActivationNote('')
      setNotice('Phase 7 production technical routing activated. Real directory users now own the technical workflow.')
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to activate production technical routing')
    } finally {
      setBusy('')
    }
  }

  async function removeMember(member: Member) {
    if (!window.confirm(`Remove ${member.full_name || member.email} from the future production directory? This does not delete the ERP user.`)) return
    setBusy(`remove-${member.id}`)
    setError('')
    setNotice('')
    try {
      const result = await apiFetch<Dashboard>(`/operations/technical-team-directory/members/${member.id}`, { method: 'DELETE' })
      applyDashboard(result)
      setNotice('Production-directory membership disabled. The ERP user account itself was not changed.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to update technical-team directory')
    } finally {
      setBusy('')
    }
  }

  return <div className="operations-page technical-directory-page">
    <DashboardHeader
      eyebrow="PHASE 7 · REAL TECHNICAL ROUTING · CONTROLLED CUTOVER"
      title={title}
      description={data?.live_technical_routing_enabled ? 'Production routing is active. Real directory PMs and configured recipients now own technical assignments, samples, handovers, progress, completion and email notifications.' : 'Prepare all six real technical teams, finish open UAT work, then Admin can perform one controlled production cutover from demo routing to real NakshaTech accounts.'}
      actions={<button className="operations-button secondary" type="button" onClick={load}><RefreshCcw size={16}/> Refresh</button>}
      meta={<>
        <span className="nk-meta-chip"><ShieldCheck size={14}/> {data?.live_technical_routing_enabled ? 'Production technical routing active' : 'UAT demo routing active'}</span>
        <span className="nk-meta-chip"><LockKeyhole size={14}/> Controlled Admin cutover only</span>
        <span className="nk-meta-chip"><Users size={14}/> Six real technical departments</span>
      </>}
    />

    <div className={`technical-directory-lock ${data?.live_technical_routing_enabled ? 'technical-routing-live' : ''}`}>{data?.live_technical_routing_enabled ? <ShieldCheck size={17}/> : <LockKeyhole size={17}/>}<div><strong>{data?.live_technical_routing_enabled ? 'PRODUCTION TECHNICAL ROUTING ACTIVE' : 'UAT DEMO ROUTING ACTIVE'}</strong><span>{data?.cutover.message || data?.go_live_message || 'Checking Phase 7 production prerequisites…'}</span></div></div>
    {notice && <div className="success-message">{notice}</div>}
    {error && <div className="error-message">{error}</div>}

    <section className="stats-grid technical-directory-stats">
      <StatCard icon={Users} label="Visible Departments" value={data?.summary.visible_departments ?? '—'} />
      <StatCard icon={Users} label="Real Accounts Prepared" value={data?.summary.configured_real_members ?? '—'} tone="purple" />
      <StatCard icon={CheckCircle2} label="Live-Ready Departments" value={data?.summary.live_ready_departments ?? '—'} tone="green" />
      <StatCard icon={ShieldAlert} label="Still To Prepare" value={data?.summary.not_ready_departments ?? '—'} tone="orange" />
    </section>

    {data && <section className={`operations-panel technical-routing-cutover ${data.live_technical_routing_enabled ? 'is-live' : ''}`}>
      <header><div><span className="operations-kicker">PHASE 7 CUTOVER CONTROL</span><h2>{data.live_technical_routing_enabled ? 'Real Technical Routing Is Live' : 'Production Activation Gate'}</h2><p>{data.cutover.message}</p></div><span className={`operations-status ${data.live_technical_routing_enabled ? 'success' : data.cutover.can_activate ? 'success' : 'warning'}`}>{data.live_technical_routing_enabled ? 'LIVE' : data.cutover.can_activate ? 'READY TO ACTIVATE' : 'BLOCKED'}</span></header>
      {!data.live_technical_routing_enabled && <div className="technical-routing-blockers">
        <span><strong>{data.cutover.all_departments_ready ? '6 / 6' : `${data.summary.live_ready_departments} / 6`}</strong> departments ready</span>
        <span><strong>{data.cutover.blockers.open_sample_requests}</strong> open samples</span>
        <span><strong>{data.cutover.blockers.open_technical_workstreams}</strong> unfinished workstreams</span>
        <span><strong>{data.cutover.blockers.unresolved_handovers}</strong> unresolved handovers</span>
      </div>}
      {editor && !data.live_technical_routing_enabled && <div className="technical-routing-activation-form">
        <label><span>Activation Confirmation</span><input value={activationText} onChange={event => setActivationText(event.target.value)} placeholder={data.cutover.activation_confirmation} /></label>
        <label><span>Activation Note (optional)</span><input value={activationNote} onChange={event => setActivationNote(event.target.value)} placeholder="Approved production cutover / UAT sign-off reference" /></label>
        <button className="operations-button" type="button" disabled={!data.cutover.can_activate || activationText !== data.cutover.activation_confirmation || busy === 'activate-routing'} onClick={() => void activateProductionRouting()}><ShieldCheck size={15}/> Activate Real Technical Routing</button>
        <small>This is an explicit production cutover. Installation alone never activates live routing.</small>
      </div>}
      {data.live_technical_routing_enabled && <div className="technical-routing-live-meta"><CheckCircle2 size={18}/><div><strong>Activated {data.cutover.activated_at ? new Date(data.cutover.activated_at).toLocaleString() : ''}</strong><span>{data.cutover.activated_by_name ? `By ${data.cutover.activated_by_name}` : 'Production routing control is active.'}{data.cutover.activation_note ? ` · ${data.cutover.activation_note}` : ''}</span></div></div>}
    </section>}

    {!data
      ? <section className="operations-panel"><div className="operations-empty">Loading technical team directory…</div></section>
      : <div className="technical-directory-grid">{data.departments.map(department => <section className={`operations-panel technical-directory-card ${department.readiness.live_ready ? 'is-ready' : ''}`} key={department.department_code}>
          <header>
            <div><span className="operations-kicker">PEER TECHNICAL DEPARTMENT</span><h2>{department.department_label}</h2><p>Login role: <strong>{department.role}</strong></p></div>
            <span className={`operations-status ${department.readiness.live_ready ? 'success' : 'warning'}`}>{department.readiness.live_ready ? 'Directory Ready' : 'Preparation Needed'}</span>
          </header>

          <div className="technical-directory-demo">
            <strong>Current UAT recipient</strong>
            <span>{department.demo_account.email || 'Not configured'}</span>
            <small>{department.demo_account.active ? 'Demo account active' : 'Demo account missing / inactive'}</small>
          </div>

          <div className="technical-directory-readiness">
            <span><strong>{department.readiness.configured_real_members}</strong> real members</span>
            <span><strong>{department.readiness.pm_candidates}</strong> PM candidates</span>
            <span><strong>{department.readiness.sample_recipients}</strong> sample recipients</span>
            <span><strong>{department.readiness.handover_recipients}</strong> handover recipients</span>
            <span><strong>{department.readiness.completion_recipients}</strong> completion recipients</span>
          </div>

          {editor && <div className="technical-directory-add">
            <label><span>Add Existing Real ERP User</span><select value={choices[department.department_code] || ''} onChange={event => setChoices(current => ({ ...current, [department.department_code]: event.target.value }))}><option value="">Select active {department.department_label} user</option>{department.eligible_users.map(user => <option value={user.id} key={user.id}>{user.full_name} · {user.email}{user.employee_id ? ` · ${user.employee_id}` : ''}</option>)}</select></label>
            <button className="operations-button" type="button" disabled={busy === `add-${department.department_code}` || !department.eligible_users.length} onClick={() => void addMember(department)}><UserPlus size={15}/> Add to Production Directory</button>
            {!department.eligible_users.length && <small>No active non-demo ERP users with the exact {department.role} role are currently available.</small>}
          </div>}

          <div className="technical-directory-members">
            <h3>Prepared Real Team Accounts</h3>
            {department.configured_members.length === 0
              ? <div className="operations-empty compact">No real team account prepared yet.</div>
              : department.configured_members.map(member => {
                  const memberFlags = drafts[member.id] || flagsFromMember(member)
                  return <article className="technical-directory-member" key={member.id}>
                    <div className="technical-directory-person"><strong>{member.full_name || 'ERP User'}</strong><span>{member.email}</span><small>{member.employee_id || 'No Employee ID'} · {member.designation || member.stored_role || department.role}</small></div>
                    {editor
                      ? <div className="technical-directory-flag-controls" aria-label={`Future responsibilities for ${member.full_name || member.email}`}>
                          <label><input type="checkbox" checked={memberFlags.pm_eligible} onChange={event => setFlag(member, 'pm_eligible', event.target.checked)}/> PM</label>
                          <label><input type="checkbox" checked={memberFlags.receive_sample_notifications} onChange={event => setFlag(member, 'receive_sample_notifications', event.target.checked)}/> Sample</label>
                          <label><input type="checkbox" checked={memberFlags.receive_handover_notifications} onChange={event => setFlag(member, 'receive_handover_notifications', event.target.checked)}/> Handover</label>
                          <label><input type="checkbox" checked={memberFlags.receive_completion_notifications} onChange={event => setFlag(member, 'receive_completion_notifications', event.target.checked)}/> Completion</label>
                        </div>
                      : <div className="technical-directory-flags">
                          <span className={member.pm_eligible ? 'on' : ''}>PM</span>
                          <span className={member.receive_sample_notifications ? 'on' : ''}>Sample</span>
                          <span className={member.receive_handover_notifications ? 'on' : ''}>Handover</span>
                          <span className={member.receive_completion_notifications ? 'on' : ''}>Completion</span>
                        </div>}
                    <span className={`operations-status ${member.ready_for_live_use ? 'success' : 'warning'}`}>{member.ready_for_live_use ? 'Ready' : 'Check Account'}</span>
                    {editor && <div className="technical-directory-member-actions">
                      <button className="operations-button secondary" type="button" disabled={busy === `save-${member.id}`} onClick={() => void saveFlags(member)}><Save size={14}/> Save Flags</button>
                      <button className="operations-button secondary danger-lite" type="button" disabled={busy === `remove-${member.id}`} onClick={() => void removeMember(member)}><XCircle size={14}/> Remove</button>
                    </div>}
                  </article>
                })}
          </div>
        </section>)}</div>}

    <section className="operations-panel technical-directory-next">
      <div><span className="operations-kicker">ROUTING STATUS</span><h2>{data?.live_technical_routing_enabled ? 'Real Technical Accounts Are Active' : 'Demo Routing Remains Protected'}</h2><p>{data?.live_technical_routing_enabled ? 'PM selection, technical sample actions and notifications, data handovers, progress reporting, department completion and technical emails now use the prepared real Technical Team Directory.' : 'Configure every department and clear all active UAT work first. Phase 7 will not mix unfinished demo workflows with live production accounts.'}</p></div>
    </section>
  </div>
}
