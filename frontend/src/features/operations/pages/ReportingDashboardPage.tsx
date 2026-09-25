import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Clock3,
  Database,
  FileCheck2,
  Link2,
  RefreshCcw,
  ShieldCheck,
  UsersRound,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { StatCard } from '../../../components/StatCard'
import { apiFetch } from '../../../lib/api'
import '../operations.css'
import '../reporting.css'

type DepartmentCard = {
  department_code:string
  department_label:string
  projects:number
  workstreams:number
  completed_workstreams:number
  blocked_workstreams:number
  average_progress_percent:number
  sample_requests:number
  open_samples:number
  incoming_handovers:number
  outgoing_handovers:number
  unresolved_handovers:number
  overdue_handovers:number
  configured_real_members:number
  pm_candidates:number
  live_ready:boolean
}

type ProjectFact = {
  project_id:number
  project_code?:string|null
  project_name?:string|null
  client_name?:string|null
  project_status?:string|null
  health?:string|null
  overall_progress_percent?:number|null
  total_workstreams?:number|null
  completed_workstreams?:number|null
  blocked_workstreams?:number|null
  unresolved_handovers?:number|null
  overdue_handovers?:number|null
  final_delivery_recorded:boolean
  finance_status?:string|null
}

type ReportingDashboard = {
  viewer_mode:'executive'|'bd_manager'|'technical_manager'|'finance_manager'
  current_role:string
  current_department_code?:string|null
  current_department_label?:string|null
  generated_at:string
  routing:{
    routing_mode?:string
    live_technical_routing_enabled?:boolean
    live_ready_departments?:number
    configured_real_members?:number
    cutover_blockers?:Record<string,number>
  }
  summary:Record<string,number>
  bd:Record<string,number>
  samples:{total:number;open:number;client_approved:number;by_status:Record<string,number>}
  handovers:{total:number;unresolved:number;overdue:number;by_status:Record<string,number>}
  completion:Record<string,number>
  department_scorecards:DepartmentCard[]
  projects:ProjectFact[]
  powerbi:{semantic_model_url?:string;projects_csv_url?:string;departments_csv_url?:string;note:string}
}

function label(value?:string|null){
  if(!value)return '—'
  return value.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase())
}

function percent(value?:number|null){
  const safe=Number.isFinite(Number(value))?Number(value):0
  return `${Math.round(safe*10)/10}%`
}

function healthClass(value?:string|null){
  if(value==='completed'||value==='on_track'||value==='delivered')return 'success'
  if(value==='delayed'||value==='blocked'||value==='attention')return 'warning'
  return ''
}

export function ReportingDashboardPage(){
  const [data,setData]=useState<ReportingDashboard|null>(null)
  const [error,setError]=useState('')

  function load(){
    setError('')
    void apiFetch<ReportingDashboard>('/operations/reporting/dashboard')
      .then(setData)
      .catch(err=>setError(err instanceof Error?err.message:'Could not load Phase 8 reporting'))
  }

  useEffect(load,[])

  const title=useMemo(()=>{
    if(data?.viewer_mode==='executive')return 'Executive Reporting'
    if(data?.viewer_mode==='finance_manager')return 'Finance Manager Reporting'
    if(data?.viewer_mode==='bd_manager')return 'Business Development Reporting'
    if(data?.current_department_label)return `${data.current_department_label} Manager Reporting`
    return 'Manager Reporting'
  },[data])

  const description=useMemo(()=>{
    if(data?.viewer_mode==='executive')return 'One read-only view of project health, technical-team performance, sample activity, cross-team handovers, delivery readiness and Finance closure.'
    if(data?.viewer_mode==='finance_manager')return 'Read-only Finance reporting for delivery handoff, pending billing and financial closure.'
    if(data?.viewer_mode==='bd_manager')return 'Read-only reporting across your BD pipeline and the connected technical execution of your projects.'
    return 'A role-scoped reporting view of your technical projects, progress, samples, handovers and completion state.'
  },[data])

  const totalProjects=data?.summary.total_projects ?? data?.summary.visible_projects ?? 0
  const averageProgress=data?.summary.average_progress_percent ?? 0
  const attention=data?.summary.attention_projects ?? 0
  const openSamples=data?.summary.open_samples ?? data?.samples.open ?? 0
  const unresolvedHandovers=data?.summary.unresolved_handovers ?? data?.handovers.unresolved ?? 0
  const pendingFinance=data?.summary.pending_finance ?? data?.completion.pending_finance ?? 0

  return <div className="operations-page phase8-reporting-page">
    <DashboardHeader
      variant="ops"
      icon={BarChart3}
      eyebrow="PHASE 8 · OPERATIONAL & ANALYTICAL REPORTING"
      title={title}
      description={description}
      actions={<button className="operations-button secondary" type="button" onClick={load}><RefreshCcw size={16}/> Refresh</button>}
      meta={<>
        <span className="nk-meta-chip"><BarChart3 size={14}/> Read-only operational & analytical reporting</span>
        <span className="nk-meta-chip"><ShieldCheck size={14}/> {data?label(data.routing.routing_mode):'Routing mode'}</span>
        <span className="nk-meta-chip"><UsersRound size={14}/> Scoped to your ERP role</span>
      </>}
    />

    {data&&<div className={`reporting-routing-banner ${data.routing.live_technical_routing_enabled?'live':'locked'}`}>
      <ShieldCheck size={17}/>
      <div><strong>{data.routing.live_technical_routing_enabled?'Production technical routing active':'Technical routing remains UAT/demo locked'}</strong><span>Reporting is read-only and does not change Phase 7 routing, project workflow or Finance state.</span></div>
      <span className="operations-status">{label(data.routing.routing_mode)}</span>
    </div>}
    {error&&<div className="error-message">{error}</div>}

    <section className="stats-grid reporting-stats">
      <StatCard icon={BarChart3} label="Visible Projects" value={data?totalProjects:'—'} />
      <StatCard icon={CheckCircle2} label="Average Progress" value={data?percent(averageProgress):'—'} tone="green" />
      <StatCard icon={AlertTriangle} label="Needs Attention" value={data?attention:'—'} tone="orange" />
      <StatCard icon={FileCheck2} label="Open Samples" value={data?openSamples:'—'} tone="purple" />
      <StatCard icon={Link2} label="Open Handovers" value={data?unresolvedHandovers:'—'} tone="orange" />
      <StatCard icon={Clock3} label="Pending Finance" value={data?pendingFinance:'—'} />
    </section>

    {!data?<section className="operations-panel"><div className="operations-empty">Loading Phase 8 reporting…</div></section>
    :<>
      {data.viewer_mode==='executive'&&<section className="reporting-summary-grid">
        <article className="operations-panel reporting-summary-card">
          <span className="operations-kicker">BD PIPELINE</span><h2>Business Development</h2>
          <div className="reporting-mini-grid">
            <span><strong>{data.bd.total??0}</strong>Total opportunities</span>
            <span><strong>{data.bd.active??0}</strong>Active</span>
            <span><strong>{data.bd.linked??0}</strong>Linked projects</span>
            <span><strong>{data.bd.delivered??0}</strong>Delivered</span>
          </div>
        </article>
        <article className="operations-panel reporting-summary-card">
          <span className="operations-kicker">DELIVERY & FINANCE</span><h2>Closure Position</h2>
          <div className="reporting-mini-grid">
            <span><strong>{data.completion.ready_for_delivery??0}</strong>Ready for delivery</span>
            <span><strong>{data.completion.delivered_projects??0}</strong>Final delivered</span>
            <span><strong>{data.completion.pending_finance??0}</strong>Pending Finance</span>
            <span><strong>{data.completion.financially_closed??0}</strong>Financially closed</span>
          </div>
        </article>
        <article className="operations-panel reporting-summary-card">
          <span className="operations-kicker">LIVE TEAM READINESS</span><h2>Technical Directory</h2>
          <div className="reporting-mini-grid">
            <span><strong>{data.routing.live_ready_departments??0}/6</strong>Departments ready</span>
            <span><strong>{data.routing.configured_real_members??0}</strong>Configured members</span>
            <span><strong>{data.samples.open}</strong>Open samples</span>
            <span><strong>{data.handovers.overdue}</strong>Overdue handovers</span>
          </div>
        </article>
      </section>}

      {data.department_scorecards.length>0&&<section className="operations-panel reporting-departments">
        <header><div><span className="operations-kicker">MANAGER SCORECARDS</span><h2>Department Performance</h2><p>Progress and dependency indicators are calculated from the same live workflow data used by Project Monitoring.</p></div></header>
        <div className="reporting-department-grid">{data.department_scorecards.map(row=><article key={row.department_code} className="reporting-department-card">
          <div className="reporting-department-head"><div><strong>{row.department_label}</strong><small>{row.projects} project{row.projects===1?'':'s'} · {row.workstreams} workstreams</small></div><span className={`operations-status ${row.live_ready?'success':''}`}>{row.live_ready?'Directory Ready':'Preparation Needed'}</span></div>
          <div className="reporting-progress-track"><span style={{width:`${Math.min(100,Math.max(0,row.average_progress_percent))}%`}}/></div>
          <div className="reporting-department-progress"><strong>{percent(row.average_progress_percent)}</strong><span>average workstream progress</span></div>
          <div className="reporting-department-metrics">
            <span><b>{row.completed_workstreams}</b> completed</span>
            <span><b>{row.blocked_workstreams}</b> blocked</span>
            <span><b>{row.open_samples}</b> open samples</span>
            <span><b>{row.unresolved_handovers}</b> open handovers</span>
            <span><b>{row.overdue_handovers}</b> overdue</span>
            <span><b>{row.pm_candidates}</b> PM candidates</span>
          </div>
        </article>)}</div>
      </section>}

      <section className="operations-panel reporting-projects">
        <header><div><span className="operations-kicker">PROJECT PORTFOLIO</span><h2>Health & Closure Overview</h2><p>Read-only portfolio facts for the projects visible to your current ERP role.</p></div></header>
        {data.projects.length===0?<div className="nk-empty"><span className="nk-empty-icon"><BarChart3 size={22}/></span><h3>No project reporting rows</h3><p>Projects appear here once they are visible to your ERP role — the portfolio table is read-only and mirrors the live Project Monitoring data.</p></div>
        :<div className="reporting-table-wrap"><table className="reporting-table"><thead><tr><th>Project</th><th>Client</th><th>Health</th><th>Progress</th><th>Teams</th><th>Open Handovers</th><th>Finance</th></tr></thead><tbody>{data.projects.map(row=><tr key={row.project_id}>
          <td><strong>{row.project_code||`#${row.project_id}`}</strong><small>{row.project_name||'Project'}</small></td>
          <td>{row.client_name||'—'}</td>
          <td><span className={`operations-status ${healthClass(row.health)}`}>{label(row.health)}</span></td>
          <td>{row.overall_progress_percent==null?'—':percent(row.overall_progress_percent)}</td>
          <td>{row.completed_workstreams??0}/{row.total_workstreams??0}</td>
          <td>{row.unresolved_handovers??0}{Number(row.overdue_handovers||0)>0?<small className="reporting-overdue"> · {row.overdue_handovers} overdue</small>:null}</td>
          <td>{row.final_delivery_recorded?label(row.finance_status||'pending_billing'):'Not handed off'}</td>
        </tr>)}</tbody></table></div>}
      </section>

      <section className="operations-panel reporting-powerbi">
        <header><div><span className="operations-kicker">POWER BI READY</span><h2>Read-Only Reporting Feeds</h2><p>{data.powerbi.note}</p></div><Database size={24}/></header>
        <div className="reporting-feed-grid">
          {data.powerbi.semantic_model_url&&<div><strong>Semantic JSON</strong><code>{data.powerbi.semantic_model_url}</code></div>}
          {data.powerbi.projects_csv_url&&<div><strong>Project Facts CSV</strong><code>{data.powerbi.projects_csv_url}</code></div>}
          {data.powerbi.departments_csv_url&&<div><strong>Department Facts CSV</strong><code>{data.powerbi.departments_csv_url}</code></div>}
        </div>
        <div className="reporting-governance"><UsersRound size={17}/><span>These feeds preserve ERP role/data scope and are read-only. Workflow approvals and updates remain inside Nakshatech ERP.</span></div>
      </section>
    </>}
  </div>
}
