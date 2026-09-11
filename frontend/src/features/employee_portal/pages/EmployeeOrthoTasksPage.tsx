import { ArrowRight, Briefcase, Calendar, CheckCircle2, CircleDashed, ClipboardList, Clock3, Inbox, Package, Timer } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { StatCard } from '../../../components/StatCard'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch } from '../../../lib/api'

type OrthoTask = {
  id: number
  project_id: number
  project_name: string | null
  project_code: string | null
  package_code: string
  package_name: string
  current_stage: string
  production_state: string
  qc_state: string
  qa_state: string
  rework_source: string | null
  area: number | null
  area_unit: string | null
  target_hours: number | null
  actual_hours: number
  assigned_roles: string[]
  permissions: { team_leader: boolean; production: boolean; qc: boolean; qa: boolean }
  production_completed_at: string | null
  delivery_ready_at: string | null
  delivered_at: string | null
  daily_updates_count: number
}

type EmployeeOrthoTasksResponse = {
  employee: { id: number; full_name: string; email: string; employee_id: string | null; department: string | null; designation: string | null }
  total_assigned: number
  active_count: number
  tasks: OrthoTask[]
}

const ROLE_LABELS: Record<string, string> = {
  team_leader: 'Team Leader',
  production: 'Production',
  qc: 'QC',
  qa: 'QA',
}

const STAGE_LABELS: Record<string, string> = {
  not_started: 'Not started',
  production: 'In production',
  production_rework: 'Production rework',
  qc: 'In QC',
  qa: 'In QA',
  delivery_ready: 'Delivery ready',
  delivered: 'Delivered',
}

function stageTone(stage: string): 'success' | 'warning' | 'danger' | 'pending' {
  if (stage === 'delivered' || stage === 'delivery_ready') return 'success'
  if (stage.includes('rework') || stage === 'rejected') return 'danger'
  if (stage === 'qc' || stage === 'qa' || stage === 'production' || stage === 'production_rework') return 'warning'
  return 'pending'
}

function formatArea(area: number | null, unit: string | null) {
  if (area == null) return null
  return `${area} ${unit || 'ha'}`
}

function formatDate(value: string | null) {
  if (!value) return null
  return new Date(value).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' })
}

export function EmployeeOrthoTasksPage() {
  const { user } = useAuth()
  const [data, setData] = useState<EmployeeOrthoTasksResponse | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    void apiFetch<EmployeeOrthoTasksResponse>('/operations/employee/ortho-tasks')
      .then(setData)
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load assignments'))
  }, [])

  const tasks = data?.tasks ?? []
  const activeTasks = tasks.filter(task => task.current_stage !== 'delivered')
  const deliveredTasks = tasks.filter(task => task.current_stage === 'delivered')

  return (
    <>
      <DashboardHeader
        eyebrow="EMPLOYEE SUPPORT"
        title="My Ortho Assignments"
        description="Read-only view of Ortho / LiDAR work packages where you are listed as Team Leader, Production, QC, or QA. Use the Ortho Dashboard to perform actions."
      />

      {error && <div className="empty-state" style={{ color: '#b03a3a' }}>{error}</div>}

      <section className="stats-grid" style={{ marginBottom: '20px' }}>
        <StatCard icon={Inbox} label="Total assigned" value={data?.total_assigned ?? 0} tone="blue" />
        <StatCard icon={Clock3} label="Active" value={data?.active_count ?? 0} tone="orange" />
        <StatCard icon={CheckCircle2} label="Delivered" value={deliveredTasks.length} tone="green" />
        <StatCard icon={Briefcase} label="Department" value={data?.employee.department || user?.department || 'Employee'} />
      </section>

      <section className="panel-card support-recent-panel">
        <div className="section-heading">
          <div>
            <span className="section-kicker">ACTIVE ORTHO WORK</span>
            <h2>Current assignments</h2>
          </div>
          <Link to="/ortho">Open Ortho Dashboard <ArrowRight size={14} /></Link>
        </div>
        {activeTasks.length === 0 ? (
          <div className="empty-state">No active Ortho assignments. The PM will notify you when a work package is assigned.</div>
        ) : (
          <div className="support-ticket-list">
            {activeTasks.map(task => {
              const stage = STAGE_LABELS[task.current_stage] || task.current_stage
              const roles = task.assigned_roles.map(role => ROLE_LABELS[role] || role).join(' · ')
              return (
                <div key={task.id} className="support-ticket-row" style={{ cursor: 'default' }}>
                  <div>
                    <strong>{task.package_code} · {task.package_name}</strong>
                    <span>
                      <Package size={12} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                      {task.project_code || `Project #${task.project_id}`} {task.project_name ? `· ${task.project_name}` : ''}
                    </span>
                    <span style={{ display: 'flex', gap: 12, marginTop: 4, fontSize: '0.7rem', color: '#3b556e' }}>
                      <span><ClipboardList size={11} style={{ verticalAlign: 'middle', marginRight: 3 }} />Role: {roles || 'Project participant'}</span>
                      {task.area != null && <span>Area: {formatArea(task.area, task.area_unit)}</span>}
                      {task.target_hours != null && <span>Target: {task.target_hours} h</span>}
                      {task.actual_hours > 0 && <span><Timer size={11} style={{ verticalAlign: 'middle', marginRight: 3 }} />Logged: {task.actual_hours.toFixed(1)} h</span>}
                      {task.daily_updates_count > 0 && <span>Daily updates: {task.daily_updates_count}</span>}
                    </span>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
                    <span className={`finance-status tone-${stageTone(task.current_stage)}`}>{stage}</span>
                    {task.rework_source && <span className="finance-status tone-danger">Rework · {task.rework_source.toUpperCase()}</span>}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </section>

      {deliveredTasks.length > 0 && (
        <section className="panel-card support-recent-panel" style={{ marginTop: '20px' }}>
          <div className="section-heading">
            <div>
              <span className="section-kicker">DELIVERY HISTORY</span>
              <h2>Completed assignments</h2>
            </div>
          </div>
          <div className="support-ticket-list">
            {deliveredTasks.map(task => (
              <div key={task.id} className="support-ticket-row" style={{ cursor: 'default' }}>
                <div>
                  <strong>{task.package_code} · {task.package_name}</strong>
                  <span>
                    <Package size={12} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                    {task.project_code || `Project #${task.project_id}`} {task.project_name ? `· ${task.project_name}` : ''}
                  </span>
                  {task.delivered_at && (
                    <span style={{ display: 'flex', gap: 8, marginTop: 4, fontSize: '0.7rem', color: '#3b556e' }}>
                      <Calendar size={11} style={{ verticalAlign: 'middle', marginRight: 3 }} />Delivered: {formatDate(task.delivered_at)}
                    </span>
                  )}
                </div>
                <span className="finance-status tone-success"><CheckCircle2 size={12} /> Delivered</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {data && data.total_assigned === 0 && (
        <section className="panel-card" style={{ marginTop: '20px', padding: '20px' }}>
          <div className="section-heading" style={{ marginBottom: 8 }}>
            <div>
              <span className="section-kicker">HOW IT WORKS</span>
              <h2>What this page shows</h2>
            </div>
          </div>
          <p style={{ color: '#5f6b7a', fontSize: '0.82rem', lineHeight: 1.6, margin: 0 }}>
            <CircleDashed size={14} style={{ verticalAlign: 'middle', marginRight: 6 }} />
            When the Ortho Project Manager assigns you to a work package — as Team Leader, Production, QC, or QA — the package appears here automatically.
            Use the <Link to="/ortho">Ortho Dashboard</Link> to perform actions: start/pause production, record daily updates, or submit QC/QA decisions.
          </p>
        </section>
      )}
    </>
  )
}
