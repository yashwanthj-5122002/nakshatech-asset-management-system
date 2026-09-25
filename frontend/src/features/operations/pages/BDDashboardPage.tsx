import { Activity, BriefcaseBusiness, Building2, CheckCircle2, Clock3, FileText, RefreshCw, RefreshCcw, RotateCcw, Shield, WalletCards, Workflow } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { StatCard } from '../../../components/StatCard'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch } from '../../../lib/api'
import '../operations.css'

type EventRow = { id:number; event_type:string; actor_name?:string|null; created_at:string; comments?:string|null }
type ProjectRow = {
  id:number; project_code:string; project_name:string; client_code?:string|null; client_name?:string|null;
  workflow_status:string; normalized_status:string; updated_at?:string; finance_feedback?:string|null; events?:EventRow[]
}
type ClientRow = {
  id:number; client_code:string; client_name:string; location?:string|null; country?:string|null;
  contact_person_name?:string|null; project_count?:number
}
type Dashboard = {
  summary:{total:number;draft:number;pending_finance:number;returned:number;approved:number;completion_pending:number;closed:number};
  clients:ClientRow[]; projects:ProjectRow[]
}

function label(value:string){return value.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase())}

function greetingFor(name:string){
  const hour = new Date().getHours()
  const part = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
  return `${part}, ${name}`
}

export function BDDashboardPage(){
  const { user } = useAuth()
  const [data,setData]=useState<Dashboard|null>(null)
  const [error,setError]=useState('')
  const [loading,setLoading]=useState(true)

  function load(){
    setLoading(true);setError('')
    void apiFetch<Dashboard>('/operations/workflow/bd/dashboard')
      .then(setData)
      .catch(err=>setError(err instanceof Error?err.message:'Unable to load BD dashboard'))
      .finally(()=>setLoading(false))
  }
  useEffect(load,[])

  const recentProjects=useMemo(()=>data?.projects.slice(0,8)??[],[data])
  const recentActivity=useMemo(()=>{
    return (data?.projects??[]).flatMap(project=>(project.events??[]).map(event=>({...event,project_code:project.project_code})))
      .sort((a,b)=>Date.parse(b.created_at)-Date.parse(a.created_at)).slice(0,10)
  },[data])

  const firstName = (user?.full_name || '').trim().split(/\s+/)[0] || 'there'

  return <div className="operations-page">
    <DashboardHeader variant="ops" icon={BriefcaseBusiness} eyebrow="BUSINESS DEVELOPMENT · PROJECT OPERATIONS" title={greetingFor(firstName)} description="Here is your portfolio at a glance — clients, live projects and everything waiting on a Finance decision." actions={<button className="operations-button secondary" onClick={load}><RefreshCcw size={16}/> Refresh</button>} summary={data?<><StatCard icon={Building2} label="Total Clients" value={data.clients.length} note="Registered BD clients"/><StatCard icon={BriefcaseBusiness} label="Total Projects" value={data.summary.total} tone="blue" note="Across the V8.1 workflow"/><StatCard icon={Clock3} label="Pending Finance Approval" value={data.summary.pending_finance} tone="orange" note="Waiting on Finance"/><StatCard icon={CheckCircle2} label="Finance Approved / Active" value={data.summary.approved} tone="green" note="Cleared to execute"/></>:undefined} meta={<><span className="nk-meta-chip"><BriefcaseBusiness size={14}/> Portfolio overview</span><span className="nk-meta-chip"><Workflow size={14}/> BD → Finance → PM → Delivery</span>{data&&<span className="nk-meta-chip"><Building2 size={14}/> {data.clients.length} clients · {data.summary.total} projects</span>}</>}/>

    {error&&<div className="operations-alert error" aria-live="polite">{error}<button className="operations-button secondary" onClick={load} style={{marginLeft:'8px'}}><RefreshCw size={14}/> Retry</button></div>}
    {loading&&<section className="operations-panel"><div className="operations-empty"><span className="spinner"/> Loading BD summary…</div></section>}
    {data&&<>
      <section className="operations-stats-grid">
        <StatCard icon={FileText} label="Draft" value={data.summary.draft} tone="blue"/>
        <StatCard icon={RotateCcw} label="Returned for Correction" value={data.summary.returned} tone="purple"/>
        <StatCard icon={WalletCards} label="Closure Pending" value={data.summary.completion_pending} tone="orange"/>
        <StatCard icon={Shield} label="Closed" value={data.summary.closed} tone="teal"/>
      </section>

      <div className="operations-summary-columns">
        <section className="operations-panel"><header><div><span className="operations-kicker">RECENT PROJECTS</span><h2>Latest Portfolio Activity</h2></div><Link className="operations-button secondary" to="/bd/projects">View All</Link></header>
          {!recentProjects.length?<div className="nk-empty"><span className="nk-empty-icon"><BriefcaseBusiness size={22}/></span><h3>No projects in your portfolio yet</h3><p>New client projects appear here as soon as they are created and move through the V8.1 workflow.</p><div className="nk-empty-action"><button className="operations-button secondary" onClick={load}><RefreshCcw size={16}/> Refresh</button></div></div>:<div className="operations-daily-list">{recentProjects.map(row=><article className="operations-daily-card" key={row.id}><div className="operations-daily-heading"><div><span className="operations-kicker">{row.client_code||'CLIENT ID NOT RECORDED'}</span><h3>{row.project_code}</h3><p>{row.project_name}</p></div><span className={`operations-status ${row.normalized_status==='finance_returned'?'danger':row.normalized_status==='closed'?'success':'warning'}`}>{label(row.workflow_status)}</span></div>{row.finance_feedback&&<small><b>Finance feedback:</b> {row.finance_feedback}</small>}</article>)}</div>}
        </section>
        <section className="operations-panel"><header><div><span className="operations-kicker">RECENT ACTIVITY</span><h2>Project History</h2></div></header>
          {!recentActivity.length?<div className="nk-empty"><span className="nk-empty-icon"><Activity size={22}/></span><h3>No workflow activity yet</h3><p>Status changes, finance decisions and project updates stream in here once your first project starts moving.</p><div className="nk-empty-action"><button className="operations-button secondary" onClick={load}><RefreshCcw size={16}/> Refresh</button></div></div>:<div className="operations-activity-list">{recentActivity.map(row=><div key={`${row.project_code}-${row.id}`}><Activity size={15}/><div><strong>{row.project_code} · {label(row.event_type)}</strong><span>{row.actor_name||'System'} · {new Date(row.created_at).toLocaleString('en-IN')}</span>{row.comments&&<small>{row.comments}</small>}</div></div>)}</div>}
        </section>
      </div>
    </>}
  </div>
}
