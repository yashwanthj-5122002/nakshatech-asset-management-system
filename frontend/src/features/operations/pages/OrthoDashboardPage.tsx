import { CheckCircle2, ClipboardList, RefreshCcw, Send, ShieldCheck, Truck, UserRoundCog, Users } from 'lucide-react'
import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { StatCard } from '../../../components/StatCard'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch } from '../../../lib/api'
import '../operations.css'

type Employee = { id:number; full_name:string; email:string; employee_id?:string|null; department?:string|null; designation?:string|null }
type Member = Employee & { user_id:number; member_role:'team_leader'|'production'|'qc'|'qa' }
type Assignment = { id:number; full_name:string; email:string; employee_id?:string|null } | null
type DailyUpdate = {id:number;update_date:string;work_type?:string|null;quantity_completed:number;progress_percent?:number|null;files_completed:number;hours_spent?:number|null;status:string;blockers?:string|null;remarks?:string|null;created_at:string}
type Package = {
  id:number; package_code:string; area_name:string; quantity?:number|null; quantity_unit:string; target_date?:string|null; instructions?:string|null;
  current_stage:string; production_state:string; qc_state:string; qa_state:string; rework_source?:string|null;
  cumulative_completed:number; remaining_quantity:number; progress_percent:number; files_completed:number; my_roles:string[];
  can_daily_activity:boolean; can_complete_production:boolean; can_qc:boolean; can_qa:boolean; can_deliver:boolean;
  daily_updates:DailyUpdate[]; review_history:{review_type:string;attempt_no:number;decision:string;comments?:string|null;created_at:string}[];
  assignments?:{team_leader:Assignment;production:Assignment;qc:Assignment;qa:Assignment}
}
type Project = {
  project_id:number; project_code:string; client_code?:string|null; start_date?:string|null; end_date?:string|null; workflow_status:string;
  my_roles:string[]; summary:{packages:number;production:number;qc:number;qa:number;delivery_ready:number;delivered:number}; packages:Package[];
  can_manage_team:boolean; can_allocate_work:boolean; can_complete_project:boolean; scope_text?:string|null;quantity?:number|null;quantity_unit?:string|null;priority?:string|null;members?:Member[]
}
type OrthoDashboard = {viewer_mode:'project_manager'|'participant'|'read_only';projects:Project[];employees:Employee[]}
type TeamDraft={team_leader_user_id:string;production_user_ids:number[];qc_user_ids:number[];qa_user_ids:number[]}
type AllocationDraft={package_code:string;area_name:string;quantity:string;quantity_unit:string;target_date:string;instructions:string;production_user_id:string;qc_user_id:string;qa_user_id:string}
type DailyDraft={work_type:string;quantity_completed:string;files_completed:string;hours_spent:string;status:string;blockers:string;remarks:string}
const emptyAllocation:AllocationDraft={package_code:'',area_name:'',quantity:'',quantity_unit:'km',target_date:'',instructions:'',production_user_id:'',qc_user_id:'',qa_user_id:''}
const emptyDaily:DailyDraft={work_type:'Production',quantity_completed:'',files_completed:'0',hours_spent:'',status:'on_track',blockers:'',remarks:''}

function label(value:string){return value.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase())}
function localDate(){return new Date().toISOString().slice(0,10)}
function uniqMembers(rows:Member[]|undefined,role:string){const seen=new Set<number>();return (rows??[]).filter(r=>r.member_role===role&&!seen.has(r.user_id)&&seen.add(r.user_id))}

export function OrthoDashboardPage(){
  const { user }=useAuth()
  const [data,setData]=useState<OrthoDashboard|null>(null); const [selectedId,setSelectedId]=useState<number|null>(null)
  const [error,setError]=useState(''); const [notice,setNotice]=useState(''); const [busy,setBusy]=useState(false)
  const [teamDrafts,setTeamDrafts]=useState<Record<number,TeamDraft>>({}); const [allocation,setAllocation]=useState<AllocationDraft>(emptyAllocation)
  const [daily,setDaily]=useState<Record<number,DailyDraft>>({})

  function load(){setError('');void apiFetch<OrthoDashboard>('/operations/workflow/ortho/dashboard').then(v=>{setData(v);setSelectedId(current=>current&&v.projects.some(p=>p.project_id===current)?current:(v.projects[0]?.project_id??null))}).catch(e=>setError(e instanceof Error?e.message:'Unable to load Ortho workflow'))}
  useEffect(load,[])
  const selected=useMemo(()=>data?.projects.find(p=>p.project_id===selectedId)??null,[data,selectedId])

  function currentTeam(project:Project):TeamDraft{return {
    team_leader_user_id:String(project.members?.find(m=>m.member_role==='team_leader')?.user_id??''),
    production_user_ids:(project.members??[]).filter(m=>m.member_role==='production').map(m=>m.user_id),
    qc_user_ids:(project.members??[]).filter(m=>m.member_role==='qc').map(m=>m.user_id),
    qa_user_ids:(project.members??[]).filter(m=>m.member_role==='qa').map(m=>m.user_id),
  }}
  function draftFor(project:Project){return teamDrafts[project.project_id]??currentTeam(project)}
  function patchTeam(project:Project,patch:Partial<TeamDraft>){setTeamDrafts(current=>({...current,[project.project_id]:{...draftFor(project),...patch}}))}
  function toggleTeam(project:Project,key:'production_user_ids'|'qc_user_ids'|'qa_user_ids',id:number){const d=draftFor(project);const arr=d[key];patchTeam(project,{[key]:arr.includes(id)?arr.filter(v=>v!==id):[...arr,id]} as Partial<TeamDraft>)}

  async function saveTeam(project:Project){
    const d=draftFor(project);if(!d.team_leader_user_id||!d.production_user_ids.length||!d.qc_user_ids.length||!d.qa_user_ids.length){setError('Select exactly one Team Lead and at least one Production, QC and QA employee.');return}
    setBusy(true);setError('');setNotice('')
    try{await apiFetch(`/operations/workflow/ortho/projects/${project.project_id}/team`,{method:'POST',body:JSON.stringify({...d,team_leader_user_id:Number(d.team_leader_user_id)})});setNotice('Project team saved. Every selected employee was notified by ERP notification and email.');load()}
    catch(e){setError(e instanceof Error?e.message:'Unable to save team')}finally{setBusy(false)}
  }

  async function allocate(e:FormEvent){
    e.preventDefault();if(!selected)return;setBusy(true);setError('');setNotice('')
    try{await apiFetch(`/operations/workflow/ortho/projects/${selected.project_id}/work-packages`,{method:'POST',body:JSON.stringify({...allocation,quantity:Number(allocation.quantity),production_user_id:Number(allocation.production_user_id),qc_user_id:Number(allocation.qc_user_id),qa_user_id:Number(allocation.qa_user_id)})});setAllocation(emptyAllocation);setNotice('Area / Code / Quantity allocated. Assigned Production, QC and QA employees were notified.');load()}
    catch(e){setError(e instanceof Error?e.message:'Unable to allocate work')}finally{setBusy(false)}
  }

  async function submitDaily(pkg:Package){
    const d=daily[pkg.id]??emptyDaily;if(d.quantity_completed===''){setError('Enter today\'s completed quantity.');return}
    setBusy(true);setError('');setNotice('')
    try{await apiFetch(`/operations/workflow/ortho/work-packages/${pkg.id}/daily-activity`,{method:'POST',body:JSON.stringify({update_date:localDate(),work_type:d.work_type||'Production',quantity_completed:Number(d.quantity_completed),files_completed:Number(d.files_completed||0),hours_spent:d.hours_spent===''?null:Number(d.hours_spent),status:d.status,blockers:d.blockers||null,remarks:d.remarks||null})});setDaily(v=>({...v,[pkg.id]:emptyDaily}));setNotice(`${pkg.package_code}: daily activity updated.`);load()}
    catch(e){setError(e instanceof Error?e.message:'Unable to update daily activity')}finally{setBusy(false)}
  }

  async function action(path:string,body:unknown,success:string){setBusy(true);setError('');setNotice('');try{await apiFetch(path,{method:'POST',body:body===undefined?undefined:JSON.stringify(body)});setNotice(success);load()}catch(e){setError(e instanceof Error?e.message:'Action failed')}finally{setBusy(false)}}
  async function productionComplete(pkg:Package){if(window.confirm(`Mark ${pkg.package_code} Production complete and send to QC?`))await action(`/operations/workflow/ortho/work-packages/${pkg.id}/production-complete`,{},`${pkg.package_code}: Production completed; Team Lead, PM and QC notified.`)}
  async function review(pkg:Package,kind:'qc'|'qa',decision:'approve'|'reject'){
    const comments=decision==='reject'?window.prompt(`${kind.toUpperCase()} rejection reason / rework instructions (required):`,''):window.prompt(`${kind.toUpperCase()} comments (optional):`,'')
    if(decision==='reject'&&!(comments??'').trim()){setError(`${kind.toUpperCase()} rejection requires comments.`);return}
    if(comments===null&&decision==='approve')return
    await action(`/operations/workflow/ortho/work-packages/${pkg.id}/${kind}`,{decision,comments:comments||null},`${pkg.package_code}: ${kind.toUpperCase()} ${decision==='approve'?'approved':'returned for rework'}.`)
  }
  async function deliver(pkg:Package){const remarks=window.prompt('Delivery remarks / reference (optional):','');if(remarks===null)return;await action(`/operations/workflow/ortho/work-packages/${pkg.id}/deliver`,{remarks:remarks||null},`${pkg.package_code}: marked Delivered.`)}
  async function completeProject(project:Project){
    const completion_date=window.prompt('Operational completion date (YYYY-MM-DD):',localDate());if(!completion_date)return
    const final_delivery_reference=window.prompt('Final delivery reference (optional):','')??'';const remarks=window.prompt('Final completion remarks (optional):','')??''
    await action(`/operations/workflow/ortho/projects/${project.project_id}/complete`,{completion_date,final_delivery_reference:final_delivery_reference||null,remarks:remarks||null},`${project.project_code}: Operational Completion recorded. BD and Finance notified for closure.`)
  }

  const title=user?.role==='employee'?'My Assigned Ortho Work':'Ortho Project Operations'
  const tlProduction=selected?uniqMembers(selected.members,'production'):[];const tlQc=selected?uniqMembers(selected.members,'qc'):[];const tlQa=selected?uniqMembers(selected.members,'qa'):[]

  return <div className="operations-page">
    <DashboardHeader eyebrow="ORTHO · ASSIGNMENT-BASED OPERATIONS" title={title} description="Operations users see Client ID + Project ID only. PM selects the project team; Team Lead allocates exact work; employees see only the tasks assigned to them." actions={<button className="operations-button secondary" onClick={load}><RefreshCcw size={16}/> Refresh</button>}/>
    {notice&&<div className="operations-alert success">{notice}</div>}{error&&<div className="operations-alert error">{error}</div>}

    {!data?.projects.length?<section className="operations-panel"><div className="operations-empty">No assigned Ortho project/work is available for this login.</div></section>:<>
      <section className="operations-panel operations-current-project"><div className="operations-current-project-row"><label className="operations-field"><span>Project</span><select value={selectedId??''} onChange={e=>setSelectedId(Number(e.target.value))}>{data.projects.map(p=><option key={p.project_id} value={p.project_id}>{p.project_code} · Client ID {p.client_code||'—'}</option>)}</select></label>{selected&&<div className="operations-current-project-meta"><strong>{selected.project_code}</strong><span>Client ID: {selected.client_code||'—'}</span><span>{selected.start_date||'—'} → {selected.end_date||'—'}</span><span>My Role: {selected.my_roles.map(label).join(', ')||'Read only'}</span><span>Status: {label(selected.workflow_status)}</span></div>}</div></section>

      {selected&&<section className="stats-grid">
        <StatCard icon={ClipboardList} label="Work Packages" value={selected.summary.packages}/><StatCard icon={Users} label="Production" value={selected.summary.production}/><StatCard icon={ShieldCheck} label="QC" value={selected.summary.qc} tone="purple"/><StatCard icon={CheckCircle2} label="QA" value={selected.summary.qa} tone="green"/><StatCard icon={Truck} label="Delivered" value={selected.summary.delivered} tone="green"/>
      </section>}

      {selected?.can_manage_team&&<section className="operations-panel"><header><div><span className="operations-kicker">PROJECT MANAGER · TEAM SELECTION</span><h2>Exactly One Team Lead + Multiple Production / QC / QA</h2><p>The Team Lead may also be selected in Production, QC and/or QA. Team selection does not allocate Area/Code work; the Team Lead performs that next.</p></div></header>
        <div className="operations-form-grid"><label className="operations-field"><span>Team Lead *</span><select value={draftFor(selected).team_leader_user_id} onChange={e=>patchTeam(selected,{team_leader_user_id:e.target.value})}><option value="">Select exactly one</option>{data.employees.map(emp=><option key={emp.id} value={emp.id}>{emp.employee_id?`${emp.employee_id} · `:''}{emp.full_name}</option>)}</select></label></div>
        <div className="operations-team-columns">{(['production_user_ids','qc_user_ids','qa_user_ids'] as const).map(key=><div className="operations-team-box" key={key}><strong>{key.startsWith('production')?'Production Employees':key.startsWith('qc')?'QC Employees':'QA Employees'}</strong>{data.employees.map(emp=><label className="operations-check" key={emp.id}><input type="checkbox" checked={draftFor(selected)[key].includes(emp.id)} onChange={()=>toggleTeam(selected,key,emp.id)}/><span>{emp.employee_id?`${emp.employee_id} · `:''}{emp.full_name}</span></label>)}</div>)}</div>
        <div className="operations-actions"><button className="operations-button" disabled={busy} onClick={()=>saveTeam(selected)}><Send size={15}/> Save & Notify Team</button></div>
      </section>}

      {selected?.can_allocate_work&&<section className="operations-panel"><header><div><span className="operations-kicker">TEAM LEAD · WORK ALLOCATION</span><h2>Allocate Area / Code / Quantity / Target Date</h2><p>Each dropdown contains only employees selected by the Project Manager for that exact role.</p></div></header><form className="operations-form-grid" onSubmit={allocate}>
        <label className="operations-field"><span>Code *</span><input value={allocation.package_code} onChange={e=>setAllocation({...allocation,package_code:e.target.value})} required placeholder="DX20-24730"/></label>
        <label className="operations-field"><span>Area *</span><input value={allocation.area_name} onChange={e=>setAllocation({...allocation,area_name:e.target.value})} required placeholder="Murlo"/></label>
        <label className="operations-field"><span>Quantity *</span><input type="number" step="0.001" min="0.001" value={allocation.quantity} onChange={e=>setAllocation({...allocation,quantity:e.target.value})} required/></label>
        <label className="operations-field"><span>Unit *</span><input value={allocation.quantity_unit} onChange={e=>setAllocation({...allocation,quantity_unit:e.target.value})} required/></label>
        <label className="operations-field"><span>Target Date *</span><input type="date" value={allocation.target_date} onChange={e=>setAllocation({...allocation,target_date:e.target.value})} required/></label>
        <label className="operations-field"><span>Production *</span><select value={allocation.production_user_id} onChange={e=>setAllocation({...allocation,production_user_id:e.target.value})} required><option value="">Select</option>{tlProduction.map(m=><option key={m.user_id} value={m.user_id}>{m.employee_id?`${m.employee_id} · `:''}{m.full_name}</option>)}</select></label>
        <label className="operations-field"><span>QC *</span><select value={allocation.qc_user_id} onChange={e=>setAllocation({...allocation,qc_user_id:e.target.value})} required><option value="">Select</option>{tlQc.map(m=><option key={m.user_id} value={m.user_id}>{m.employee_id?`${m.employee_id} · `:''}{m.full_name}</option>)}</select></label>
        <label className="operations-field"><span>QA *</span><select value={allocation.qa_user_id} onChange={e=>setAllocation({...allocation,qa_user_id:e.target.value})} required><option value="">Select</option>{tlQa.map(m=><option key={m.user_id} value={m.user_id}>{m.employee_id?`${m.employee_id} · `:''}{m.full_name}</option>)}</select></label>
        <label className="operations-field operations-span-2"><span>Instructions *</span><textarea value={allocation.instructions} onChange={e=>setAllocation({...allocation,instructions:e.target.value})} required placeholder="Work instructions for the assigned Production/QC/QA employees"/></label>
        <div className="operations-actions operations-span-2"><button className="operations-button" disabled={busy}>Assign Work & Notify</button></div>
      </form></section>}

      {selected&&<section className="operations-panel"><header><div><span className="operations-kicker">ASSIGNMENT TRACKER</span><h2>{selected.can_manage_team||selected.can_allocate_work?'Project Work Packages':'My Exact Assigned Work'}</h2><p>Daily progress is calculated from activity entries. Cumulative quantity and progress percentage cannot be manually overwritten.</p></div>{selected.can_complete_project&&<button className="operations-button success" disabled={busy} onClick={()=>completeProject(selected)}><CheckCircle2 size={15}/> Complete Project</button>}</header>
        {!selected.packages.length?<div className="operations-empty">No work package is visible for this assignment yet.</div>:<div className="operations-daily-list">{selected.packages.map(pkg=>{const d=daily[pkg.id]??emptyDaily;return <article className="operations-daily-card" key={pkg.id}>
          <div className="operations-daily-heading"><div><span className="operations-kicker">{pkg.package_code}</span><h3>{pkg.area_name}</h3><div className="operations-project-meta"><span>Project: {selected.project_code}</span><span>Client ID: {selected.client_code||'—'}</span><span>My Role: {pkg.my_roles.map(label).join(', ')||'Monitoring'}</span><span>Target: {pkg.target_date||'—'}</span></div></div><div><span className="operations-status">{label(pkg.current_stage)}</span></div></div>
          {pkg.instructions&&<div className="operations-instructions"><strong>Instructions:</strong> {pkg.instructions}</div>}
          <div className="operations-progress"><span style={{width:`${Math.min(100,pkg.progress_percent)}%`}}/></div><div className="operations-project-meta"><span>Assigned: {pkg.quantity??'—'} {pkg.quantity_unit}</span><span>Completed: {pkg.cumulative_completed} {pkg.quantity_unit}</span><span>Remaining: {pkg.remaining_quantity} {pkg.quantity_unit}</span><span>Progress: {pkg.progress_percent}%</span><span>Files: {pkg.files_completed}</span></div>
          {pkg.assignments&&<div className="operations-project-meta"><span>Production: {pkg.assignments.production?.full_name||'—'}</span><span>QC: {pkg.assignments.qc?.full_name||'—'}</span><span>QA: {pkg.assignments.qa?.full_name||'—'}</span></div>}
          {pkg.can_daily_activity&&<div className="operations-daily-form"><label className="operations-field"><span>Work Type / Task</span><input value={d.work_type} onChange={e=>setDaily(v=>({...v,[pkg.id]:{...d,work_type:e.target.value}}))} placeholder="Production"/></label><label className="operations-field"><span>Today's Quantity *</span><input type="number" min="0" step="0.001" value={d.quantity_completed} onChange={e=>setDaily(v=>({...v,[pkg.id]:{...d,quantity_completed:e.target.value}}))}/></label><label className="operations-field"><span>Files Completed</span><input type="number" min="0" value={d.files_completed} onChange={e=>setDaily(v=>({...v,[pkg.id]:{...d,files_completed:e.target.value}}))}/></label><label className="operations-field"><span>Hours</span><input type="number" min="0" step="0.25" value={d.hours_spent} onChange={e=>setDaily(v=>({...v,[pkg.id]:{...d,hours_spent:e.target.value}}))}/></label><label className="operations-field"><span>Status</span><select value={d.status} onChange={e=>setDaily(v=>({...v,[pkg.id]:{...d,status:e.target.value}}))}><option value="on_track">On Track</option><option value="at_risk">At Risk</option><option value="blocked">Blocked</option><option value="completed">Completed</option></select></label><label className="operations-field"><span>Issue / Blocker</span><input value={d.blockers} onChange={e=>setDaily(v=>({...v,[pkg.id]:{...d,blockers:e.target.value}}))}/></label><label className="operations-field"><span>Remarks</span><input value={d.remarks} onChange={e=>setDaily(v=>({...v,[pkg.id]:{...d,remarks:e.target.value}}))}/></label><div className="operations-actions"><button type="button" className="operations-button" disabled={busy} onClick={()=>submitDaily(pkg)}>Update Daily Activity</button>{pkg.can_complete_production&&<button type="button" className="operations-button success" disabled={busy} onClick={()=>productionComplete(pkg)}>Complete Production</button>}</div></div>}
          <div className="operations-actions">{pkg.can_qc&&<><button className="operations-button success" disabled={busy} onClick={()=>review(pkg,'qc','approve')}>QC Approve → QA</button><button className="operations-button danger" disabled={busy} onClick={()=>review(pkg,'qc','reject')}>QC Reject → Rework</button></>}{pkg.can_qa&&<><button className="operations-button success" disabled={busy} onClick={()=>review(pkg,'qa','approve')}>QA Approve → Delivery</button><button className="operations-button danger" disabled={busy} onClick={()=>review(pkg,'qa','reject')}>QA Reject → Rework</button></>}{pkg.can_deliver&&<button className="operations-button success" disabled={busy} onClick={()=>deliver(pkg)}><Truck size={15}/> Mark Delivered</button>}</div>
          {!!pkg.daily_updates.length&&<div className="operations-daily-history"><strong>Daily Activity</strong>{pkg.daily_updates.slice().reverse().map(row=><div key={row.id}><span>{row.update_date} · {row.work_type||'Production'} · {row.quantity_completed} {pkg.quantity_unit} · {row.files_completed} files · {row.hours_spent??0} h · {label(row.status)}</span><small>{row.blockers?`Blocker: ${row.blockers} · `:''}{row.remarks||''}</small></div>)}</div>}
          {!!pkg.review_history.length&&<div className="operations-review-history"><strong>QC / QA History:</strong> {pkg.review_history.map((r,i)=><span key={`${r.review_type}-${r.attempt_no}-${i}`}> {r.review_type.toUpperCase()} #{r.attempt_no} {label(r.decision)}{r.comments?` — ${r.comments}`:''};</span>)}</div>}
        </article>})}</div>}
      </section>}
    </>}
  </div>
}
