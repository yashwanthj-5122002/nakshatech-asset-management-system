import {
  CalendarDays,
  CheckCircle2,
  Clock3,
  FolderKanban,
  LockKeyhole,
  Mail,
  Pause,
  Play,
  RefreshCcw,
  RotateCcw,
  Send,
  ShieldCheck,
  Truck,
  UserCheck,
  Users,
  XCircle,
} from 'lucide-react'
import { type FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { StatCard } from '../../../components/StatCard'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch } from '../../../lib/api'
import '../operations.css'

type ViewKey = 'project_manager' | 'team_leader' | 'production' | 'qc' | 'qa'
type AssignableRole = Exclude<ViewKey, 'project_manager'>
type ViewerMode = 'project_manager' | 'participant' | 'read_only'

type UserOption = {
  id: number
  full_name: string
  email: string
  employee_id?: string | null
  department?: string | null
  designation?: string | null
  role: string
  is_active: boolean
}

type ProjectMaster = {
  id: number
  project_code: string
  project_name: string
  client_name?: string | null
  start_date?: string | null
  end_date?: string | null
  project_status: string
  project_manager_id?: number | null
}

type Member = {
  id: number
  user_id: number
  user_name?: string | null
  user_email?: string | null
  employee_id?: string | null
  member_role: ViewKey
  is_active: boolean
}

type DailyUpdate = {
  id: number
  update_date: string
  achieved_area?: number | null
  progress_percent?: number | null
  hours_spent?: number | null
  status: string
  blockers?: string | null
  remarks?: string | null
  updated_by_id: number
  updated_by_name?: string | null
  created_at: string
}

type WorkPackage = {
  id: number
  project_id: number
  package_code: string
  package_name: string
  area?: number | null
  area_unit: string
  target_hours?: number | null
  current_stage: string
  production_state: string
  qc_state: string
  qa_state: string
  rework_source?: string | null
  team_leader_user_id?: number | null
  team_leader_name?: string | null
  team_leader_email?: string | null
  production_user_id?: number | null
  production_user_name?: string | null
  production_user_email?: string | null
  qc_user_id?: number | null
  qc_user_name?: string | null
  qc_user_email?: string | null
  qa_user_id?: number | null
  qa_user_name?: string | null
  qa_user_email?: string | null
  actual_hours: number
  timer_running_for_viewer: boolean
  permissions: {
    can_daily_update: boolean
    can_production: boolean
    can_qc: boolean
    can_qa: boolean
  }
  daily_updates: DailyUpdate[]
  review_history: Array<{
    review_type: string
    attempt_no: number
    reviewer_user_id: number
    decision: string
    comments?: string | null
    created_at: string
  }>
}

type OrthoProject = {
  project: ProjectMaster
  profile: {
    project_id: number
    opportunity_id?: number | null
    total_area?: number | null
    area_unit: string
    scope_text?: string | null
    planned_hours?: number | null
    target_value?: number | null
    project_manager_user_id?: number | null
    project_manager_name?: string | null
    project_manager_email?: string | null
    status: string
    final_delivery_at?: string | null
    final_delivery_remarks?: string | null
  }
  permissions: Record<ViewKey, boolean>
  progress: {
    total_packages: number
    progress_percent: number
    delivered_packages: number
    stage_counts: Record<string, number>
    total_hours: number
    total_area: number
    delivered_area: number
    status: string
  }
  members: Member[]
  work_packages: WorkPackage[]
}

type OrthoDashboard = {
  viewer_mode: ViewerMode
  view_permissions: Record<ViewKey, boolean>
  summary: {
    projects: number
    packages: number
    production: number
    qc: number
    qa: number
    delivery_ready: number
    delivered: number
    total_hours: number
  }
  projects: OrthoProject[]
  project_master: ProjectMaster[]
  users: UserOption[]
}

type DailyForm = {
  update_date: string
  achieved_area: string
  progress_percent: string
  hours_spent: string
  status: 'on_track' | 'at_risk' | 'blocked' | 'completed'
  blockers: string
  remarks: string
}

const views: Array<{ key: ViewKey; label: string; step: number; description: string }> = [
  { key: 'project_manager', label: 'Project Manager', step: 1, description: 'Finance project, project team, assignment email and work packages' },
  { key: 'team_leader', label: 'Team Leader', step: 2, description: 'Daily achieved area, progress, hours, blockers and remarks' },
  { key: 'production', label: 'Production', step: 3, description: 'Assigned Production employee or PM updates work timer and submits QC' },
  { key: 'qc', label: 'QC', step: 4, description: 'Assigned QC employee or PM approves / rejects with remarks' },
  { key: 'qa', label: 'QA', step: 5, description: 'Assigned QA employee or PM approves / rejects; PM controls final delivery' },
]

const today = () => new Date().toISOString().slice(0, 10)
const emptyDaily = (): DailyForm => ({ update_date: today(), achieved_area: '', progress_percent: '', hours_spent: '', status: 'on_track', blockers: '', remarks: '' })
function label(value: string) { return value.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase()) }
function stageTone(value: string) { return value === 'delivered' || value === 'delivery_ready' || value === 'approved' ? 'success' : value.includes('rework') || value === 'rejected' ? 'danger' : value === 'qc' || value === 'qa' || value === 'pending' ? 'warning' : '' }

export function OrthoDashboardPage() {
  const { user } = useAuth()
  const [data, setData] = useState<OrthoDashboard | null>(null)
  const [view, setView] = useState<ViewKey>('project_manager')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [activateProject, setActivateProject] = useState('')
  const [totalArea, setTotalArea] = useState('')
  const [scope, setScope] = useState('')
  const [plannedHours, setPlannedHours] = useState('')
  const [selectedProject, setSelectedProject] = useState('')
  const [teamSetupOpen, setTeamSetupOpen] = useState(false)
  const [teamTL, setTeamTL] = useState('')
  const [teamProd, setTeamProd] = useState('')
  const [teamQC, setTeamQC] = useState('')
  const [teamQA, setTeamQA] = useState('')
  const teamSectionRef = useRef<HTMLElement | null>(null)
  const [packageCode, setPackageCode] = useState('')
  const [packageName, setPackageName] = useState('')
  const [packageArea, setPackageArea] = useState('')
  const [packageTarget, setPackageTarget] = useState('')
  const [packageTL, setPackageTL] = useState('')
  const [packageProd, setPackageProd] = useState('')
  const [packageQC, setPackageQC] = useState('')
  const [packageQA, setPackageQA] = useState('')
  const [dailyForms, setDailyForms] = useState<Record<number, DailyForm>>({})

  function load(preferredProjectId?: string) {
    setError('')
    void apiFetch<OrthoDashboard>('/operations/ortho/dashboard')
      .then(result => {
        setData(result)
        setSelectedProject(previous => {
          const preferred = preferredProjectId || previous
          if (preferred && result.projects.some(item => String(item.profile.project_id) === preferred)) return preferred
          return result.projects[0] ? String(result.projects[0].profile.project_id) : ''
        })
      })
      .catch(err => setError(err instanceof Error ? err.message : 'Unable to load Ortho dashboard'))
  }

  useEffect(load, [])

  const readOnly = data?.viewer_mode === 'read_only'
  const currentProject = useMemo(
    () => data?.projects.find(item => String(item.profile.project_id) === selectedProject) || data?.projects[0] || null,
    [data, selectedProject],
  )
  const canView = (key: ViewKey) => Boolean(readOnly || currentProject?.permissions[key] || (!currentProject && data?.view_permissions[key]))

  useEffect(() => {
    if (!data || canView(view)) return
    const first = views.find(item => canView(item.key))
    if (first) setView(first.key)
  }, [data, currentProject, view])

  const projectPackages = currentProject?.work_packages ?? []
  const packagesFor = (key: ViewKey) => {
    if (key === 'team_leader') return projectPackages.filter(pkg => readOnly || pkg.permissions.can_daily_update)
    if (key === 'production') return projectPackages.filter(pkg => readOnly || pkg.permissions.can_production)
    if (key === 'qc') return projectPackages.filter(pkg => pkg.current_stage === 'qc' && pkg.qc_state === 'pending' && (readOnly || pkg.permissions.can_qc))
    if (key === 'qa') return projectPackages.filter(pkg => pkg.current_stage === 'qa' && pkg.qa_state === 'pending' && (readOnly || pkg.permissions.can_qa))
    return projectPackages
  }

  async function run(path: string, method: string, body?: unknown, success = 'Updated successfully.') {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await apiFetch(path, { method, body: body === undefined ? undefined : JSON.stringify(body) })
      setNotice(success)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Operation failed')
    } finally {
      setBusy(false)
    }
  }

  async function activate(event: FormEvent) {
    event.preventDefault()
    if (!activateProject) return
    const activatedId = activateProject
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await apiFetch('/operations/ortho/projects/activate', {
        method: 'POST',
        body: JSON.stringify({
          project_id: Number(activatedId),
          total_area: totalArea ? Number(totalArea) : null,
          area_unit: 'ha',
          scope_text: scope || null,
          planned_hours: plannedHours ? Number(plannedHours) : null,
        }),
      })
      setNotice('Finance-assigned project activated in Ortho. Next: click Setup Project Team and select Team Leader, Production, QC and QA.')
      setSelectedProject(activatedId)
      setTeamSetupOpen(true)
      load(activatedId)
      window.setTimeout(() => teamSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 450)
      setActivateProject(''); setTotalArea(''); setScope(''); setPlannedHours('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Project activation failed')
    } finally {
      setBusy(false)
    }
  }

  async function saveTeam(event: FormEvent) {
    event.preventDefault()
    if (!selectedProject) return
    if (!teamTL || !teamProd || !teamQC || !teamQA) {
      setError('Select Team Leader, Production, QC and QA before saving the project team.')
      return
    }
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await apiFetch(`/operations/ortho/projects/${selectedProject}/team`, {
        method: 'PUT',
        body: JSON.stringify({
          team_leader_user_id: Number(teamTL),
          production_user_id: Number(teamProd),
          qc_user_id: Number(teamQC),
          qa_user_id: Number(teamQA),
          apply_to_unassigned_packages: true,
        }),
      })
      setPackageTL(teamTL)
      setPackageProd(teamProd)
      setPackageQC(teamQC)
      setPackageQA(teamQA)
      setTeamSetupOpen(false)
      setNotice('Project team saved. Existing unassigned package responsibilities were filled automatically. Email delivery is separate and cannot remove these assignments.')
      load(selectedProject)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to save project team')
    } finally {
      setBusy(false)
    }
  }

  async function sendTeamEmails() {
    if (!selectedProject) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const result = await apiFetch<{ sent: number; failed: number; message: string }>(`/operations/ortho/projects/${selectedProject}/team/emails`, { method: 'POST' })
      setNotice(result.failed > 0
        ? `Project team is still saved. ${result.sent} email(s) sent and ${result.failed} failed. The current SMTP login must be corrected before failed emails can be delivered.`
        : `${result.sent} project-team assignment email(s) sent successfully.`)
      load(selectedProject)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to send assignment emails')
    } finally {
      setBusy(false)
    }
  }

  async function addPackage(event: FormEvent) {
    event.preventDefault()
    if (!selectedProject) return
    await run(`/operations/ortho/projects/${selectedProject}/work-packages`, 'POST', {
      package_code: packageCode,
      package_name: packageName,
      area: packageArea ? Number(packageArea) : null,
      area_unit: 'ha',
      target_hours: packageTarget ? Number(packageTarget) : null,
      team_leader_user_id: packageTL ? Number(packageTL) : null,
      production_user_id: packageProd ? Number(packageProd) : null,
      qc_user_id: packageQC ? Number(packageQC) : null,
      qa_user_id: packageQA ? Number(packageQA) : null,
    }, 'Work package created with responsibility owners.')
    setPackageCode(''); setPackageName(''); setPackageArea(''); setPackageTarget('')
  }

  async function submitDaily(pkg: WorkPackage) {
    const form = dailyForms[pkg.id] || emptyDaily()
    await run(`/operations/ortho/work-packages/${pkg.id}/daily-update`, 'POST', {
      update_date: form.update_date || null,
      achieved_area: form.achieved_area ? Number(form.achieved_area) : null,
      progress_percent: form.progress_percent ? Number(form.progress_percent) : null,
      hours_spent: form.hours_spent ? Number(form.hours_spent) : null,
      status: form.status,
      blockers: form.blockers || null,
      remarks: form.remarks || null,
    }, `${pkg.package_code} daily update recorded.`)
    setDailyForms(previous => ({ ...previous, [pkg.id]: emptyDaily() }))
  }

  async function review(pkg: WorkPackage, kind: 'qc' | 'qa', decision: 'approve' | 'reject') {
    const comments = window.prompt(`${kind.toUpperCase()} ${decision} comments:`, decision === 'reject' ? 'Reason for rework:' : 'Approved') ?? ''
    await run(`/operations/ortho/work-packages/${pkg.id}/${kind}`, 'POST', { decision, comments }, `${kind.toUpperCase()} ${decision} recorded.`)
  }

  async function finalDelivery(project: OrthoProject) {
    const remarks = window.prompt(`Record final delivery for ${project.project.project_code}. Delivery remarks:`, 'Final package delivered to BD / Sales.') ?? ''
    await run(`/operations/ortho/projects/${project.profile.project_id}/final-delivery`, 'POST', { remarks }, `${project.project.project_code} final delivery recorded and shared back to BD.`)
  }

  const memberOptions = (role: AssignableRole) => currentProject?.members.filter(member => member.member_role === role && member.is_active) ?? []
  // V7.0.10: project_master is already server-side filtered to Finance projects
  // assigned to the logged-in Ortho PM. Do not rely on an already-activated
  // Ortho project to discover a new Finance assignment.
  const assignedFinanceProjects = data?.project_master ?? []
  const orthoProjectIds = new Set(data?.projects.map(existing => existing.profile.project_id) ?? [])
  const projectManagerProjects = assignedFinanceProjects.filter(project => !orthoProjectIds.has(project.id))
  const alreadyInOrthoProjects = assignedFinanceProjects.filter(project => orthoProjectIds.has(project.id))
  const currentIsPM = Boolean(currentProject?.permissions.project_manager && !readOnly)
  const primaryMember = (role: AssignableRole) => { const matches = currentProject?.members.filter(member => member.member_role === role && member.is_active) ?? []; return matches.length ? matches[matches.length - 1] : null }
  const primaryTL = primaryMember('team_leader')
  const primaryProd = primaryMember('production')
  const primaryQC = primaryMember('qc')
  const primaryQA = primaryMember('qa')
  const teamReady = Boolean(primaryTL && primaryProd && primaryQC && primaryQA)
  const activeUsers = data?.users.filter(option => option.is_active) ?? []

  useEffect(() => {
    const tl = primaryTL ? String(primaryTL.user_id) : ''
    const prod = primaryProd ? String(primaryProd.user_id) : ''
    const qc = primaryQC ? String(primaryQC.user_id) : ''
    const qa = primaryQA ? String(primaryQA.user_id) : ''
    setTeamTL(tl)
    setTeamProd(prod)
    setTeamQC(qc)
    setTeamQA(qa)
    setPackageTL(tl)
    setPackageProd(prod)
    setPackageQC(qc)
    setPackageQA(qa)
    if (currentProject && !(tl && prod && qc && qa)) setTeamSetupOpen(true)
  }, [currentProject?.profile.project_id, primaryTL?.user_id, primaryProd?.user_id, primaryQC?.user_id, primaryQA?.user_id])

  return <div className="operations-page">
    <DashboardHeader
      eyebrow="ORTHO / LIDAR · PROJECT COLLABORATION"
      title="Ortho / LiDAR Dashboard"
      description="One dashboard, one official Project ID and five role-based sections. Project Manager has full control; assigned Team Leader, Production, QC and QA employees update only their own responsibilities."
      actions={<button className="operations-button secondary" onClick={() => load()}><RefreshCcw size={16}/> Refresh</button>}
    />

    {readOnly && <div className="operations-readonly"><ShieldCheck size={16}/> Management/Admin oversight is read-only.</div>}
    {data?.viewer_mode === 'project_manager' && <div className="operations-readonly"><ShieldCheck size={16}/> Project Manager has full workflow control and can also perform Team Leader, Production, QC and QA updates.</div>}
    {data?.viewer_mode === 'participant' && <div className="operations-readonly"><UserCheck size={16}/> You are an assigned Ortho project participant. Only the sections assigned to you are enabled; your normal Employee Dashboard remains unchanged.</div>}
    {error && <div className="operations-alert error">{error}</div>}
    {notice && <div className="operations-alert success">{notice}</div>}

    <div className="operations-stats-grid">
      <StatCard icon={FolderKanban} label="Projects" value={data?.summary.projects ?? 0}/>
      <StatCard icon={Users} label="Production / Rework" value={data?.summary.production ?? 0}/>
      <StatCard icon={ShieldCheck} label="QC Queue" value={data?.summary.qc ?? 0}/>
      <StatCard icon={CheckCircle2} label="QA Queue" value={data?.summary.qa ?? 0}/>
      <StatCard icon={Truck} label="Delivered Packages" value={data?.summary.delivered ?? 0}/>
      <StatCard icon={Clock3} label="Tracked Hours" value={data?.summary.total_hours ?? 0}/>
    </div>

    <section className="operations-panel operations-current-project">
      <header><div><span className="operations-kicker">CURRENT PROJECT</span><h2>Project being updated in all five sections</h2></div></header>
      {data?.projects.length ? <div className="operations-current-project-row">
        <label className="operations-field"><span>Official Finance Project ID</span><select value={selectedProject} onChange={event => setSelectedProject(event.target.value)}>{data.projects.map(project => <option key={project.profile.project_id} value={project.profile.project_id}>{project.project.project_code} · {project.project.project_name}</option>)}</select></label>
        {currentProject && <div className="operations-current-project-meta">
          <strong>{currentProject.project.project_name}</strong>
          <span>Client: {currentProject.project.client_name || '—'}</span>
          <span>Project Manager: {currentProject.profile.project_manager_name || '—'}</span>
          <span>PM Email: {currentProject.profile.project_manager_email || '—'}</span>
        </div>}
      </div> : <div className="operations-empty">No Ortho project is available for this login yet. Finance must assign the Project Manager, or the Project Manager must assign you a Team Leader / Production / QC / QA responsibility.</div>}
    </section>

    <section className="operations-flow-lane">
      {views.map(item => {
        const allowed = canView(item.key)
        return <button key={item.key} type="button" className={`operations-flow-step ${view === item.key ? 'active' : ''}`} disabled={!allowed} onClick={() => allowed && setView(item.key)}>
          <span className="operations-flow-number">{item.step}</span>
          <span><strong>{item.label}</strong><small>{item.description}</small></span>
          {!allowed && <LockKeyhole size={15}/>} 
        </button>
      })}
    </section>

    {view === 'project_manager' && <>
      {data?.viewer_mode === 'project_manager' && <section className="operations-panel">
        <header><div><span className="operations-kicker">FINANCE PROJECT MASTER → ORTHO</span><h2>Finance Assignment & Ortho Activation</h2><p>Finance must place this login in the <strong>Project Manager</strong> field. The Reporting Manager field does not grant Ortho ownership. Projects already linked from BD appear directly in Current Project; only projects not yet in Ortho need activation here.</p></div></header>
        <div className="operations-member-grid">
          <div className="operations-member-chip"><strong>Finance projects assigned to you</strong><span>{assignedFinanceProjects.length}</span><small>{user?.email || 'Current Ortho PM'}</small></div>
          <div className="operations-member-chip"><strong>Already in Ortho</strong><span>{alreadyInOrthoProjects.length}</span><small>Select them from Current Project above.</small></div>
          <div className="operations-member-chip"><strong>Waiting activation</strong><span>{projectManagerProjects.length}</span><small>Only these require Activate in Ortho.</small></div>
        </div>
        {projectManagerProjects.length > 0 ? <form className="operations-form-grid" onSubmit={activate}>
          <label className="operations-field"><span>Official Project ID</span><select value={activateProject} onChange={event => setActivateProject(event.target.value)} required><option value="">Select Project</option>{projectManagerProjects.map(project => <option key={project.id} value={project.id}>{project.project_code} · {project.project_name}</option>)}</select></label>
          <label className="operations-field"><span>Total Area (Ha)</span><input type="number" min="0" step="0.001" value={totalArea} onChange={event => setTotalArea(event.target.value)}/></label>
          <label className="operations-field"><span>Planned Hours</span><input type="number" min="0" step="0.1" value={plannedHours} onChange={event => setPlannedHours(event.target.value)}/></label>
          <label className="operations-field operations-span-2"><span>Scope</span><textarea value={scope} onChange={event => setScope(event.target.value)} placeholder="DTM + Orthomosaic + QC + QA + delivery scope"/></label>
          <div className="operations-actions operations-span-2"><button className="operations-button" disabled={busy}>Activate in Ortho</button></div>
        </form> : assignedFinanceProjects.length > 0 ? <div className="operations-empty"><strong>No Finance project is waiting for activation.</strong><br/>Every Finance project assigned to this login is already present in Ortho. Select the required project in <strong>Current Project</strong> above.</div> : <div className="operations-empty"><strong>No Finance project is assigned to this Ortho Project Manager.</strong><br/>In Finance → Client & Project Master → Edit Project, set <strong>Project Manager</strong> to <strong>{user?.full_name || 'this Ortho PM'} · {user?.email || ''}</strong>. Do not place the Ortho PM only in Reporting Manager. Then save and press Refresh here.</div>}
      </section>}

      {currentProject && currentIsPM && <>
        <section className="operations-panel" ref={teamSectionRef}>
          <header><div><span className="operations-kicker">{currentProject.project.project_code} · PROJECT TEAM</span><h2>Project Team Setup</h2><p>After Finance activation, the Project Manager selects the four operational responsibilities here. <strong>Save Project Team</strong> writes the assignments first. Email is a separate notification step and an SMTP failure can never remove the saved team.</p></div></header>
          <div className="operations-pm-identity"><UserCheck size={18}/><div><strong>Project Manager: {currentProject.profile.project_manager_name || '—'}</strong><span>{currentProject.profile.project_manager_email || '—'} · Finance Project Master is authoritative</span></div></div>
          <div className="operations-actions">
            <button type="button" className="operations-button" disabled={busy} onClick={() => setTeamSetupOpen(previous => !previous)}><Users size={15}/> {teamReady ? 'Edit Project Team' : 'Setup Project Team'}</button>
            {teamReady && <button type="button" className="operations-button secondary" disabled={busy} onClick={() => void sendTeamEmails()}><Mail size={15}/> Send Assignment Emails</button>}
          </div>
          {teamSetupOpen && <form className="operations-form-grid" onSubmit={saveTeam}>
            <label className="operations-field"><span>Team Leader</span><select value={teamTL} onChange={event => setTeamTL(event.target.value)} required><option value="">Select Team Leader</option>{activeUsers.map(option => <option key={option.id} value={option.id}>{option.full_name} · {option.email}</option>)}</select></label>
            <label className="operations-field"><span>Production</span><select value={teamProd} onChange={event => setTeamProd(event.target.value)} required><option value="">Select Production Employee</option>{activeUsers.map(option => <option key={option.id} value={option.id}>{option.full_name} · {option.email}</option>)}</select></label>
            <label className="operations-field"><span>QC</span><select value={teamQC} onChange={event => setTeamQC(event.target.value)} required><option value="">Select QC Employee</option>{activeUsers.map(option => <option key={option.id} value={option.id}>{option.full_name} · {option.email}</option>)}</select></label>
            <label className="operations-field"><span>QA</span><select value={teamQA} onChange={event => setTeamQA(event.target.value)} required><option value="">Select QA Employee</option>{activeUsers.map(option => <option key={option.id} value={option.id}>{option.full_name} · {option.email}</option>)}</select></label>
            <div className="operations-actions operations-span-2"><button className="operations-button" disabled={busy}><UserCheck size={15}/> Save Project Team</button></div>
          </form>}
          {teamReady ? <div className="operations-member-grid">{(['team_leader','production','qc','qa'] as AssignableRole[]).map(role => { const member = primaryMember(role); return <div className="operations-member-chip" key={role}><strong>{label(role)}</strong><span>{member?.user_name || '—'}</span><small>{member?.user_email || '—'}</small></div> })}</div> : <div className="operations-empty"><strong>Project team is not configured yet.</strong><br/>Click <strong>Setup Project Team</strong>, select Team Leader, Production, QC and QA, then save. You do not need email to continue the workflow.</div>}
        </section>

        <section className="operations-panel">
          <header><div><span className="operations-kicker">{currentProject.project.project_code} · WORK BREAKDOWN</span><h2>Create Work Package / Area</h2><p>The saved Project Team becomes the default responsibility set for work packages. Saving the team also fills any currently unassigned responsibilities on existing packages without overwriting explicit package assignments.</p></div></header>
          {!teamReady ? <div className="operations-empty"><strong>Complete Project Team Setup first.</strong><br/>Work-package responsibility dropdowns are intentionally locked until Team Leader, Production, QC and QA are saved.</div> : <form className="operations-form-grid" onSubmit={addPackage}>
            <label className="operations-field"><span>Package Code</span><input value={packageCode} onChange={event => setPackageCode(event.target.value)} required/></label>
            <label className="operations-field"><span>Package Name</span><input value={packageName} onChange={event => setPackageName(event.target.value)} required/></label>
            <label className="operations-field"><span>Area (Ha)</span><input type="number" min="0" step="0.001" value={packageArea} onChange={event => setPackageArea(event.target.value)}/></label>
            <label className="operations-field"><span>Target Hours</span><input type="number" min="0" step="0.1" value={packageTarget} onChange={event => setPackageTarget(event.target.value)}/></label>
            <label className="operations-field"><span>Team Leader</span><select value={packageTL} onChange={event => setPackageTL(event.target.value)} required>{memberOptions('team_leader').map(member => <option key={member.id} value={member.user_id}>{member.user_name} · {member.user_email}</option>)}</select></label>
            <label className="operations-field"><span>Production</span><select value={packageProd} onChange={event => setPackageProd(event.target.value)} required>{memberOptions('production').map(member => <option key={member.id} value={member.user_id}>{member.user_name} · {member.user_email}</option>)}</select></label>
            <label className="operations-field"><span>QC</span><select value={packageQC} onChange={event => setPackageQC(event.target.value)} required>{memberOptions('qc').map(member => <option key={member.id} value={member.user_id}>{member.user_name} · {member.user_email}</option>)}</select></label>
            <label className="operations-field"><span>QA</span><select value={packageQA} onChange={event => setPackageQA(event.target.value)} required>{memberOptions('qa').map(member => <option key={member.id} value={member.user_id}>{member.user_name} · {member.user_email}</option>)}</select></label>
            <div className="operations-actions operations-span-2"><button className="operations-button" disabled={busy}>Create Work Package</button></div>
          </form>}
        </section>
      </>}

      {currentProject && <PackageTable packages={currentProject.work_packages} title={`${currentProject.project.project_code} Work Packages`}/>} 
    </>}

    {view === 'team_leader' && <section className="operations-panel">
      <header><div><span className="operations-kicker">TEAM LEADER · DAILY UPDATE</span><h2>Daily Project / Work-Package Progress</h2><p>The assigned Team Leader and the Project Manager can both submit daily updates. Every entry is kept in history.</p></div></header>
      {packagesFor('team_leader').length === 0 ? <div className="operations-empty">No work package is assigned to you as Team Leader for the selected project.</div> : <div className="operations-daily-list">{packagesFor('team_leader').map(pkg => {
        const form = dailyForms[pkg.id] || emptyDaily()
        return <article className="operations-daily-card" key={pkg.id}>
          <div className="operations-daily-heading"><div><span className="operations-kicker">{pkg.package_code}</span><h3>{pkg.package_name}</h3></div><span className={`operations-status ${stageTone(pkg.current_stage)}`}>{label(pkg.current_stage)}</span></div>
          <div className="operations-project-meta"><span>TL: {pkg.team_leader_name || '—'}</span><span>Production: {pkg.production_user_name || '—'}</span><span>QC: {pkg.qc_user_name || '—'}</span><span>QA: {pkg.qa_user_name || '—'}</span></div>
          {pkg.permissions.can_daily_update && !readOnly && <div className="operations-daily-form">
            <label className="operations-field"><span>Date</span><input type="date" value={form.update_date} onChange={event => setDailyForms(value => ({ ...value, [pkg.id]: { ...form, update_date: event.target.value } }))}/></label>
            <label className="operations-field"><span>Achieved Area</span><input type="number" min="0" step="0.001" value={form.achieved_area} onChange={event => setDailyForms(value => ({ ...value, [pkg.id]: { ...form, achieved_area: event.target.value } }))}/></label>
            <label className="operations-field"><span>Progress %</span><input type="number" min="0" max="100" step="0.1" value={form.progress_percent} onChange={event => setDailyForms(value => ({ ...value, [pkg.id]: { ...form, progress_percent: event.target.value } }))}/></label>
            <label className="operations-field"><span>Hours Today</span><input type="number" min="0" step="0.1" value={form.hours_spent} onChange={event => setDailyForms(value => ({ ...value, [pkg.id]: { ...form, hours_spent: event.target.value } }))}/></label>
            <label className="operations-field"><span>Status</span><select value={form.status} onChange={event => setDailyForms(value => ({ ...value, [pkg.id]: { ...form, status: event.target.value as DailyForm['status'] } }))}><option value="on_track">On Track</option><option value="at_risk">At Risk</option><option value="blocked">Blocked</option><option value="completed">Completed</option></select></label>
            <label className="operations-field operations-span-2"><span>Blockers / Issues</span><textarea value={form.blockers} onChange={event => setDailyForms(value => ({ ...value, [pkg.id]: { ...form, blockers: event.target.value } }))} placeholder="Any blocker, dependency or delay"/></label>
            <label className="operations-field operations-span-2"><span>Daily Remarks</span><textarea value={form.remarks} onChange={event => setDailyForms(value => ({ ...value, [pkg.id]: { ...form, remarks: event.target.value } }))} placeholder="Work completed today / next plan"/></label>
            <div className="operations-actions operations-span-2"><button type="button" className="operations-button" disabled={busy} onClick={() => void submitDaily(pkg)}><CalendarDays size={15}/> Save Daily Update</button></div>
          </div>}
          <div className="operations-daily-history"><strong>Daily Update History</strong>{pkg.daily_updates.length === 0 ? <small>No daily update yet.</small> : [...pkg.daily_updates].reverse().slice(0, 10).map(update => <div key={update.id}><span>{update.update_date} · {update.updated_by_name || 'User'} · {label(update.status)}</span><small>{update.progress_percent ?? '—'}% · {update.achieved_area ?? '—'} area · {update.hours_spent ?? '—'} h{update.remarks ? ` · ${update.remarks}` : ''}{update.blockers ? ` · Blocker: ${update.blockers}` : ''}</small></div>)}</div>
        </article>
      })}</div>}
    </section>}

    {view === 'production' && <section className="operations-panel">
      <header><div><span className="operations-kicker">PRODUCTION</span><h2>Production Work Control</h2><p>The assigned Production employee and the Project Manager can update these controls. Time remains attributed to the assigned Production employee.</p></div></header>
      {packagesFor('production').length === 0 ? <div className="operations-empty">No Production work package is assigned to you for the selected project.</div> : <div className="operations-project-grid">{packagesFor('production').map(pkg => <article className="operations-project-card" key={pkg.id}>
        <div><span className="operations-kicker">{pkg.package_code}</span><h3>{pkg.package_name}</h3></div>
        <div className="operations-project-meta"><span>Production: {pkg.production_user_name || '—'}</span><span>{label(pkg.current_stage)}</span><span>{pkg.actual_hours} h tracked</span>{pkg.rework_source && <span>Rework from {pkg.rework_source.toUpperCase()}</span>}</div>
        {pkg.permissions.can_production && !readOnly && <div className="operations-actions">
          <button className="operations-button" disabled={busy || !['not_started', 'rework_required'].includes(pkg.production_state)} onClick={() => void run(`/operations/ortho/work-packages/${pkg.id}/work-action`, 'POST', { action: 'start' }, 'Work timer started.')}><Play size={14}/> Start</button>
          <button className="operations-button warning" disabled={busy || !pkg.timer_running_for_viewer} onClick={() => void run(`/operations/ortho/work-packages/${pkg.id}/work-action`, 'POST', { action: 'pause' }, 'Work paused.')}><Pause size={14}/> Pause</button>
          <button className="operations-button secondary" disabled={busy || !['paused', 'rework_paused'].includes(pkg.production_state)} onClick={() => void run(`/operations/ortho/work-packages/${pkg.id}/work-action`, 'POST', { action: 'resume' }, 'Work resumed.')}><RotateCcw size={14}/> Resume</button>
          <button className="operations-button success" disabled={busy || !pkg.timer_running_for_viewer} onClick={() => void run(`/operations/ortho/work-packages/${pkg.id}/work-action`, 'POST', { action: 'complete' }, 'Production work session completed.')}><CheckCircle2 size={14}/> Complete</button>
          <button className="operations-button" disabled={busy || pkg.production_state !== 'completed'} onClick={() => void run(`/operations/ortho/work-packages/${pkg.id}/submit-qc`, 'POST', undefined, 'Submitted to QC.')}><Send size={14}/> Submit QC</button>
        </div>}
      </article>)}</div>}
    </section>}

    {view === 'qc' && <ReviewTable title="QC Queue" packages={packagesFor('qc')} kind="qc" readOnly={Boolean(readOnly)} busy={busy} onReview={review}/>} 
    {view === 'qa' && <ReviewTable title="QA Queue" packages={packagesFor('qa')} kind="qa" readOnly={Boolean(readOnly)} busy={busy} onReview={review}/>} 

    {currentProject?.permissions.project_manager && currentProject.progress.total_packages > 0 && currentProject.progress.progress_percent === 100 && currentProject.profile.status !== 'delivered' && <section className="operations-panel operations-final-delivery">
      <header><div><span className="operations-kicker">PROJECT MANAGER ONLY</span><h2>Final Delivery</h2><p>Available only when every work package is QA-approved / Delivery Ready.</p></div></header>
      <button className="operations-button success" disabled={busy} onClick={() => void finalDelivery(currentProject)}><Truck size={15}/> Record Final Delivery</button>
    </section>}
  </div>
}

function PackageTable({ packages, title }: { packages: WorkPackage[]; title: string }) {
  return <section className="operations-panel"><header><div><span className="operations-kicker">WORK PACKAGE STATUS</span><h2>{title}</h2></div></header>{packages.length === 0 ? <div className="operations-empty">No work packages created.</div> : <div className="operations-table-wrap"><table className="operations-table"><thead><tr><th>Package</th><th>Area</th><th>Team Leader</th><th>Production</th><th>QC</th><th>QA</th><th>Stage</th><th>Hours</th></tr></thead><tbody>{packages.map(pkg => <tr key={pkg.id}><td><strong>{pkg.package_code}</strong><small>{pkg.package_name}</small></td><td>{pkg.area ?? '—'} {pkg.area_unit}</td><td>{pkg.team_leader_name || '—'}<small>{pkg.team_leader_email || ''}</small></td><td>{pkg.production_user_name || '—'}<small>{label(pkg.production_state)}</small></td><td>{pkg.qc_user_name || '—'}<small>{label(pkg.qc_state)}</small></td><td>{pkg.qa_user_name || '—'}<small>{label(pkg.qa_state)}</small></td><td><span className={`operations-status ${stageTone(pkg.current_stage)}`}>{label(pkg.current_stage)}</span></td><td>{pkg.actual_hours}</td></tr>)}</tbody></table></div>}</section>
}

function ReviewTable({ title, packages, kind, readOnly, busy, onReview }: { title: string; packages: WorkPackage[]; kind: 'qc' | 'qa'; readOnly: boolean; busy: boolean; onReview: (pkg: WorkPackage, kind: 'qc' | 'qa', decision: 'approve' | 'reject') => Promise<void> }) {
  return <section className="operations-panel"><header><div><span className="operations-kicker">{kind.toUpperCase()} VALIDATION</span><h2>{title}</h2><p>The assigned {kind.toUpperCase()} employee and the Project Manager can record this decision.</p></div></header>{packages.length === 0 ? <div className="operations-empty">No package is waiting in this queue for your assignment.</div> : <div className="operations-table-wrap"><table className="operations-table"><thead><tr><th>Package</th><th>Production</th><th>{kind.toUpperCase()} Owner</th><th>Stage</th><th>Previous Attempts</th><th>Decision</th></tr></thead><tbody>{packages.map(pkg => {
    const canReview = kind === 'qc' ? pkg.permissions.can_qc : pkg.permissions.can_qa
    const owner = kind === 'qc' ? pkg.qc_user_name : pkg.qa_user_name
    return <tr key={pkg.id}><td><strong>{pkg.package_code}</strong><small>{pkg.package_name}</small></td><td>{pkg.production_user_name || '—'}<small>{pkg.actual_hours} h</small></td><td>{owner || '—'}</td><td><span className={`operations-status ${stageTone(pkg.current_stage)}`}>{label(pkg.current_stage)}</span></td><td>{pkg.review_history.filter(review => review.review_type === kind).length}<div className="operations-review-history">{pkg.review_history.filter(review => review.review_type === kind).slice(-2).map(review => <div key={`${review.review_type}-${review.attempt_no}`}>#{review.attempt_no} {review.decision.toUpperCase()} {review.comments ? `· ${review.comments}` : ''}</div>)}</div></td><td>{!readOnly && canReview ? <div className="operations-actions"><button className="operations-button success" disabled={busy} onClick={() => void onReview(pkg, kind, 'approve')}><CheckCircle2 size={14}/> Approve</button><button className="operations-button danger" disabled={busy} onClick={() => void onReview(pkg, kind, 'reject')}><XCircle size={14}/> Reject / Rework</button></div> : <span className="operations-muted">Read only</span>}</td></tr>
  })}</tbody></table></div>}</section>
}
