import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Clock3,
  Link2,
  RefreshCcw,
  Save,
  ShieldAlert,
  UsersRound,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { StatCard } from '../../../components/StatCard'
import { apiFetch } from '../../../lib/api'
import '../operations.css'
import '../project-monitoring.css'

type BlockedBy = {
  handover_id:number
  handover_code:string
  department_code:string
  department_label:string
  handover_status:string
}

type Workstream = {
  id:number
  project_id:number
  department_code:string
  department_label:string
  project_manager_user_id:number
  project_manager_name?:string|null
  project_manager_email?:string|null
  sequence_order:number
  status:string
  progress_percent:number
  reported_progress_percent?:number|null
  progress_source:string
  progress_note?:string|null
  progress_updated_at?:string|null
  incoming_dependencies:number
  unresolved_incoming_dependencies:number
  outgoing_connections:number
  blocked_by:BlockedBy[]
  can_update_progress:boolean
  updated_at?:string|null
}

type Handover = {
  id:number
  handover_code:string
  project_id:number
  from_workstream_id:number
  from_department_code?:string|null
  from_department_label?:string|null
  to_workstream_id:number
  to_department_code?:string|null
  to_department_label?:string|null
  title:string
  expected_output:string
  status:string
  current_attempt_no:number
  revision_feedback?:string|null
  accepted_at?:string|null
  due_at?:string|null
  coordination_note?:string|null
  overdue:boolean
  age_hours:number
  bottleneck_department_code?:string|null
  bottleneck_department_label?:string|null
  action_required:string
  can_schedule:boolean
  updated_at?:string|null
}

type ProjectRow = {
  project_id:number
  project_code:string
  project_name:string
  client_name?:string|null
  project_status:string
  opportunity_id?:number|null
  opportunity_code?:string|null
  summary:{
    overall_progress_percent:number
    total_workstreams:number
    completed_workstreams:number
    blocked_workstreams:number
    reported_workstreams:number
    total_handovers:number
    unresolved_handovers:number
    pending_receipt_handovers:number
    revision_handovers:number
    overdue_handovers:number
    health:string
    bottleneck_departments:string[]
  }
  workstreams:Workstream[]
  handovers:Handover[]
}

type Dashboard = {
  viewer_mode:'bd_monitor'|'department'|'read_only'
  current_role:string
  current_department_code?:string|null
  demo_mode:boolean
  routing_mode?:string
  live_technical_routing_enabled?:boolean
  summary:{
    total_projects:number
    average_progress_percent:number
    delayed_projects:number
    blocked_projects:number
    unresolved_handovers:number
    overdue_handovers:number
  }
  progress_method:{description:string;status_estimates:Record<string,number>}
  projects:ProjectRow[]
}

type ProgressDraft = { percent:string; note:string }
type ScheduleDraft = { due:string; note:string }

function label(value:string){return value.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase())}

function healthClass(value:string){
  if(value==='completed'||value==='on_track')return 'success'
  if(value==='delayed'||value==='blocked')return 'warning'
  return ''
}

function toLocalInput(value?:string|null){
  if(!value)return ''
  const date=new Date(value)
  if(Number.isNaN(date.getTime()))return ''
  const pad=(n:number)=>String(n).padStart(2,'0')
  return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function ProjectMonitoringPage(){
  const [data,setData]=useState<Dashboard|null>(null)
  const [error,setError]=useState('')
  const [notice,setNotice]=useState('')
  const [busy,setBusy]=useState('')
  const [progressDrafts,setProgressDrafts]=useState<Record<number,ProgressDraft>>({})
  const [scheduleDrafts,setScheduleDrafts]=useState<Record<number,ScheduleDraft>>({})

  function load(){
    setError('')
    void apiFetch<Dashboard>('/operations/project-monitoring/dashboard')
      .then(setData)
      .catch(err=>setError(err instanceof Error?err.message:'Could not load Master Project Monitoring'))
  }
  useEffect(load,[])

  const title=useMemo(()=>{
    if(data?.viewer_mode==='department'&&data.current_department_code)return `${label(data.current_department_code)} Project Monitoring`
    return 'Master Project Monitoring'
  },[data])

  function progressDraft(row:Workstream):ProgressDraft{
    return progressDrafts[row.id]||{
      percent:String(row.reported_progress_percent ?? row.progress_percent),
      note:row.progress_note||'',
    }
  }

  function scheduleDraft(row:Handover):ScheduleDraft{
    return scheduleDrafts[row.id]||{
      due:toLocalInput(row.due_at),
      note:row.coordination_note||'',
    }
  }

  async function saveProgress(row:Workstream){
    const draft=progressDraft(row)
    const percent=Number(draft.percent)
    if(!Number.isFinite(percent)||percent<0||percent>100){setError('Progress must be between 0 and 100.');return}
    setBusy(`progress-${row.id}`);setError('');setNotice('')
    try{
      const result=await apiFetch<Dashboard>(`/operations/project-monitoring/workstreams/${row.id}/progress`,{
        method:'PATCH',
        body:JSON.stringify({progress_percent:Math.round(percent),note:draft.note.trim()||null}),
      })
      setData(result)
      setProgressDrafts(current=>{const next={...current};delete next[row.id];return next})
      setNotice(`${row.department_label}: progress updated to ${Math.round(percent)}%.`)
    }catch(err){setError(err instanceof Error?err.message:'Could not update workstream progress')}
    finally{setBusy('')}
  }

  async function saveSchedule(row:Handover){
    const draft=scheduleDraft(row)
    let dueAt:string|null=null
    if(draft.due){
      const parsed=new Date(draft.due)
      if(Number.isNaN(parsed.getTime())){setError('Enter a valid handover due date and time.');return}
      dueAt=parsed.toISOString()
    }
    setBusy(`schedule-${row.id}`);setError('');setNotice('')
    try{
      const result=await apiFetch<Dashboard>(`/operations/bd/project-monitoring/handovers/${row.id}/schedule`,{
        method:'PUT',
        body:JSON.stringify({due_at:dueAt,note:draft.note.trim()||null}),
      })
      setData(result)
      setScheduleDrafts(current=>{const next={...current};delete next[row.id];return next})
      setNotice(`${row.handover_code}: coordination schedule saved.`)
    }catch(err){setError(err instanceof Error?err.message:'Could not update handover schedule')}
    finally{setBusy('')}
  }

  return <div className="operations-page project-monitoring-page">
    <DashboardHeader
      eyebrow="MASTER PROJECT · CROSS-TEAM CONTROL TOWER"
      title={title}
      description={data?.viewer_mode==='bd_monitor'
        ? 'Monitor every technical workstream, live progress, cross-team dependency, overdue handover and current bottleneck under the same official Project ID.'
        : data?.viewer_mode==='department'
          ? 'See the complete connected project while updating only your own department progress. Peer teams remain independent workstreams under the same Master Project.'
          : 'Read-only management oversight of project progress, technical dependencies, overdue handovers and bottlenecks.'}
      actions={<button className="operations-button secondary" type="button" onClick={load}><RefreshCcw size={16}/> Refresh</button>}
      meta={<>
        <span className="nk-meta-chip"><BarChart3 size={14}/> Live progress across every workstream</span>
        <span className="nk-meta-chip"><Clock3 size={14}/> Overdue handovers and bottlenecks surfaced</span>
        <span className="nk-meta-chip"><AlertTriangle size={14}/> Cross-team dependencies under one Project ID</span>
      </>}
    />

    {data&&<div className="monitoring-demo-banner"><ShieldAlert size={16}/><strong>{data.live_technical_routing_enabled?'Phase 7 LIVE:':'Phase 4 UAT:'}</strong> {data.live_technical_routing_enabled?'progress updates are restricted to the assigned live-ready real department PM.':'progress updates remain restricted to reserved demo department PM accounts.'}</div>}
    {notice&&<div className="success-message">{notice}</div>}
    {error&&<div className="error-message">{error}</div>}

    <section className="stats-grid monitoring-stats">
      <StatCard icon={BarChart3} label="Visible Projects" value={data?.summary.total_projects??'—'} />
      <StatCard icon={CheckCircle2} label="Average Coordination Progress" value={data?`${data.summary.average_progress_percent}%`:'—'} tone="green" />
      <StatCard icon={Link2} label="Open Handovers" value={data?.summary.unresolved_handovers??'—'} tone="purple" />
      <StatCard icon={Clock3} label="Overdue Handovers" value={data?.summary.overdue_handovers??'—'} tone="orange" />
      <StatCard icon={AlertTriangle} label="Blocked / Delayed Projects" value={data?(data.summary.blocked_projects+data.summary.delayed_projects):'—'} tone="orange" />
    </section>

    {data&&<section className="operations-panel monitoring-method">
      <header><div><span className="operations-kicker">PROGRESS METHOD</span><h2>Reported Progress First · Transparent Status Estimate as Fallback</h2><p>{data.progress_method.description}</p></div></header>
      <div className="monitoring-estimate-strip">{Object.entries(data.progress_method.status_estimates).map(([status,value])=><span key={status}><strong>{label(status)}</strong>{value}%</span>)}</div>
    </section>}

    {!data?<section className="operations-panel"><div className="operations-empty">Loading project monitoring…</div></section>
    :data.projects.length===0?<section className="operations-panel"><div className="operations-empty">No connected Master Projects are available for this login.</div></section>
    :<div className="monitoring-project-list">{data.projects.map(project=><section className={`operations-panel monitoring-project health-${project.summary.health}`} key={project.project_id}>
      <header className="monitoring-project-head">
        <div><span className="operations-kicker">{project.opportunity_code||'MASTER PROJECT'}</span><h2>{project.project_code} · {project.project_name}</h2><p>{project.client_name||'Client not recorded'} · Finance status: {label(project.project_status)}</p></div>
        <div className="monitoring-health-box"><span className={`operations-status ${healthClass(project.summary.health)}`}>{label(project.summary.health)}</span><strong>{project.summary.overall_progress_percent}%</strong><small>overall coordination</small></div>
      </header>

      <div className="monitoring-progress"><span style={{width:`${Math.min(100,Math.max(0,project.summary.overall_progress_percent))}%`}}/></div>
      <div className="monitoring-kpi-strip">
        <span><strong>{project.summary.completed_workstreams}/{project.summary.total_workstreams}</strong> teams completed</span>
        <span><strong>{project.summary.reported_workstreams}</strong> PM progress reports</span>
        <span><strong>{project.summary.unresolved_handovers}</strong> open dependencies</span>
        <span><strong>{project.summary.overdue_handovers}</strong> overdue handovers</span>
      </div>
      {project.summary.bottleneck_departments.length>0&&<div className="monitoring-bottleneck"><AlertTriangle size={17}/><strong>Current bottleneck:</strong><span>{project.summary.bottleneck_departments.join(', ')}</span></div>}

      <div className="monitoring-section-title"><span className="operations-kicker">DEPARTMENT WORKSTREAMS</span><h3>Technical Team Progress</h3></div>
      <div className="monitoring-workstream-grid">{project.workstreams.map(row=>{
        const draft=progressDraft(row)
        return <article className={`monitoring-workstream ${row.status==='blocked'?'blocked':''}`} key={row.id}>
          <div className="monitoring-workstream-head"><span>#{row.sequence_order}</span><strong>{row.department_label}</strong><span className={`operations-status ${row.status==='completed'?'success':row.status==='blocked'?'warning':''}`}>{label(row.status)}</span></div>
          <div className="monitoring-pm"><UsersRound size={14}/><span>{row.project_manager_name||'Project Manager'}</span></div>
          <div className="monitoring-percent"><strong>{row.progress_percent}%</strong><small>{row.progress_source==='pm_reported'?'PM reported':row.progress_source==='workflow_completed'?'Completed':'Status estimate'}</small></div>
          <div className="monitoring-progress compact"><span style={{width:`${row.progress_percent}%`}}/></div>
          <div className="monitoring-dependencies"><span>Incoming: {row.incoming_dependencies}</span><span>Waiting: {row.unresolved_incoming_dependencies}</span><span>Outgoing: {row.outgoing_connections}</span></div>
          {row.blocked_by.length>0&&<div className="monitoring-blocked-by"><strong>Waiting for:</strong>{row.blocked_by.map(item=><span key={item.handover_id}>{item.department_label} · {label(item.handover_status)}</span>)}</div>}
          {row.progress_note&&<p className="monitoring-note">{row.progress_note}</p>}
          {row.can_update_progress&&<div className="monitoring-edit-box">
            <label><span>My Progress %</span><input type="number" min={0} max={100} value={draft.percent} onChange={event=>setProgressDrafts(current=>({...current,[row.id]:{percent:event.target.value,note:current[row.id]?.note??row.progress_note??''}}))}/></label>
            <label><span>Progress Note</span><textarea value={draft.note} onChange={event=>setProgressDrafts(current=>({...current,[row.id]:{percent:current[row.id]?.percent??String(row.reported_progress_percent??row.progress_percent),note:event.target.value}}))} placeholder="Current output, issue, milestone or next step"/></label>
            <button className="operations-button" type="button" disabled={busy===`progress-${row.id}`} onClick={()=>void saveProgress(row)}><Save size={15}/> Save My Progress</button>
          </div>}
        </article>
      })}</div>

      <div className="monitoring-section-title"><span className="operations-kicker">CROSS-TEAM DEPENDENCIES</span><h3>Data Handover Monitoring</h3></div>
      {project.handovers.length===0?<div className="operations-empty">No connected data handovers configured for this project.</div>
      :<div className="monitoring-handover-list">{project.handovers.map(row=>{
        const draft=scheduleDraft(row)
        return <article className={`monitoring-handover ${row.overdue?'overdue':''}`} key={row.id}>
          <div className="monitoring-handover-main">
            <div><span className="operations-kicker">{row.handover_code}</span><h4>{row.title}</h4><p><strong>{row.from_department_label}</strong> → <strong>{row.to_department_label}</strong></p></div>
            <span className={`operations-status ${row.status==='accepted'?'success':row.status==='revision_requested'||row.overdue?'warning':''}`}>{label(row.status)}</span>
          </div>
          <div className="monitoring-handover-meta">
            <span><strong>Action:</strong> {row.action_required}</span>
            <span><strong>Age:</strong> {row.age_hours} h since last change</span>
            <span><strong>Attempt:</strong> {row.current_attempt_no}</span>
            <span><strong>Due:</strong> {row.due_at?new Date(row.due_at).toLocaleString('en-IN'):'Not scheduled'}</span>
          </div>
          {row.overdue&&<div className="monitoring-overdue"><Clock3 size={16}/><strong>Overdue:</strong> this unresolved handover has passed the BD coordination due time.</div>}
          {row.bottleneck_department_label&&<div className="monitoring-action-owner"><strong>Action owner:</strong> {row.bottleneck_department_label}</div>}
          {row.coordination_note&&<p className="monitoring-note">BD note: {row.coordination_note}</p>}
          {row.can_schedule&&<div className="monitoring-schedule-box">
            <label><span>BD Handover Due Date / Time</span><input type="datetime-local" value={draft.due} onChange={event=>setScheduleDrafts(current=>({...current,[row.id]:{due:event.target.value,note:current[row.id]?.note??row.coordination_note??''}}))}/></label>
            <label><span>Coordination Note</span><input value={draft.note} onChange={event=>setScheduleDrafts(current=>({...current,[row.id]:{due:current[row.id]?.due??toLocalInput(row.due_at),note:event.target.value}}))} placeholder="Client priority, dependency note or target milestone"/></label>
            <button className="operations-button secondary" type="button" disabled={busy===`schedule-${row.id}`} onClick={()=>void saveSchedule(row)}><Save size={15}/> Save Handover Schedule</button>
          </div>}
        </article>
      })}</div>}
    </section>)}</div>}
  </div>
}
