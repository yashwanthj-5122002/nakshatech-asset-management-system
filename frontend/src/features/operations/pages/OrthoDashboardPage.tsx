import { CheckCircle2, ClipboardList, RefreshCcw, Send, ShieldCheck, Truck, UserRoundCog, Users } from 'lucide-react'
import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { StatCard } from '../../../components/StatCard'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch } from '../../../lib/api'
import { PMBillingBasisPanel } from '../../commercial/components/PMBillingBasisPanel'
import '../operations.css'

type Employee = { id:number; full_name:string; email:string; employee_id?:string|null; department?:string|null; designation?:string|null }
type Member = Employee & { user_id:number; member_role:'team_leader'|'production'|'qc'|'qa' }
type Assignment = { id:number; full_name:string; email:string; employee_id?:string|null } | null
type DailyUpdate = {id:number;update_date:string;work_type?:string|null;quantity_completed:number;progress_percent?:number|null;files_completed:number;hours_spent?:number|null;status:string;blockers?:string|null;remarks?:string|null;created_at:string}
type Package = {
  id:number; package_code:string; area_name:string; quantity?:number|null; quantity_unit:string; target_date?:string|null; instructions?:string|null;
  current_stage:string; production_state:string; qc_state:string; qa_state:string; rework_source?:string|null; rework_cycle_id?:number|null; rework_cycle_number?:number|null; rework_of_package_code?:string|null;
  cumulative_completed:number; remaining_quantity:number; progress_percent:number; files_completed:number; my_roles:string[];
  can_daily_activity:boolean; can_complete_production:boolean; can_qc:boolean; can_qa:boolean; can_deliver:boolean;
  daily_updates:DailyUpdate[]; review_history:{review_type:string;attempt_no:number;decision:string;comments?:string|null;created_at:string}[];
  assignments?:{team_leader:Assignment;production:Assignment;qc:Assignment;qa:Assignment}
}
type ReworkSource = {id:number;package_code:string;area_name:string;quantity?:number|null;quantity_unit?:string|null;current_stage:string;team_leader_name?:string|null;production_user_id?:number|null;production_name?:string|null;qc_user_id?:number|null;qc_name?:string|null;qa_user_id?:number|null;qa_name?:string|null;carry_forward:{production:boolean;qc:boolean;qa:boolean}}
type Rework = {cycle_id:number;cycle_number:number;cycle_type:string;cycle_label:string;status:string;team_mode?:string|null;reason:string;client_feedback?:string|null;change_request_code?:string|null;project_manager_name?:string|null;team_leader_id?:number|null;team_leader_name?:string|null;can_confirm_team:boolean;can_allocate:boolean;original_packages:ReworkSource[]}
type Project = {
  project_id:number; project_code:string; client_code?:string|null; start_date?:string|null; end_date?:string|null; workflow_status:string;
  my_roles:string[]; summary:{packages:number;production:number;qc:number;qa:number;delivery_ready:number;delivered:number}; packages:Package[];
  rework?:Rework|null; can_manage_team:boolean; can_allocate_work:boolean; can_complete_project:boolean; scope_text?:string|null;quantity?:number|null;quantity_unit?:string|null;priority?:string|null;members?:Member[]
}
type OrthoDashboard = {viewer_mode:'project_manager'|'participant'|'read_only';projects:Project[];employees:Employee[]}
type TeamDraft={team_leader_user_id:string;production_user_ids:number[];qc_user_ids:number[];qa_user_ids:number[]}
type ReworkAllocationDraft={package_code:string;area_name:string;quantity:string;quantity_unit:string;target_date:string;instructions:string;production_user_id:string;qc_user_id:string;qa_user_id:string;rework_of_package_id:string;correct:boolean;correction_reason:string}
type AllocationDraft={package_code:string;area_name:string;quantity:string;quantity_unit:string;target_date:string;instructions:string;production_user_id:string;qc_user_id:string;qa_user_id:string}
type DailyDraft={work_type:string;quantity_completed:string;files_completed:string;hours_spent:string;status:string;blockers:string;remarks:string}
const emptyAllocation:AllocationDraft={package_code:'',area_name:'',quantity:'',quantity_unit:'km',target_date:'',instructions:'',production_user_id:'',qc_user_id:'',qa_user_id:''}
const emptyDaily:DailyDraft={work_type:'Production',quantity_completed:'',files_completed:'0',hours_spent:'',status:'on_track',blockers:'',remarks:''}
const emptyReworkAllocation:ReworkAllocationDraft={...emptyAllocation,rework_of_package_id:'',correct:false,correction_reason:''}

function label(value:string){return value.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase())}
function localDate(){return new Date().toISOString().slice(0,10)}
function uniqMembers(rows:Member[]|undefined,role:string){const seen=new Set<number>();return (rows??[]).filter(r=>r.member_role===role&&!seen.has(r.user_id)&&seen.add(r.user_id))}

export function OrthoDashboardPage(){
  const { user }=useAuth()
  const [data,setData]=useState<OrthoDashboard|null>(null); const [selectedId,setSelectedId]=useState<number|null>(null)
  const [error,setError]=useState(''); const [notice,setNotice]=useState(''); const [busy,setBusy]=useState(false)
  const [teamDrafts,setTeamDrafts]=useState<Record<number,TeamDraft>>({}); const [allocation,setAllocation]=useState<AllocationDraft>(emptyAllocation)
  const [reworkMode,setReworkMode]=useState<Record<number,'reuse'|'adjust'>>({}); const [reworkRemarks,setReworkRemarks]=useState<Record<number,string>>({}); const [reworkAllocation,setReworkAllocation]=useState<ReworkAllocationDraft>(emptyReworkAllocation)
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

  async function confirmReworkTeam(project:Project){
    const rw=project.rework;if(!rw)return
    const mode=reworkMode[project.project_id]??'reuse';const d=draftFor(project)
    if(mode==='adjust'&&(!d.team_leader_user_id||!d.production_user_ids.length||!d.qc_user_ids.length||!d.qa_user_ids.length)){setError('Select exactly one Team Lead and at least one Production, QC and QA employee.');return}
    setBusy(true);setError('');setNotice('')
    const remarks=reworkRemarks[project.project_id]?.trim()||null
    try{await apiFetch(`/operations/workflow/ortho/rework-cycles/${rw.cycle_id}/team`,{method:'POST',body:JSON.stringify(mode==='reuse'?{mode,remarks}:{mode,remarks,team_leader_user_id:Number(d.team_leader_user_id),production_user_ids:d.production_user_ids,qc_user_ids:d.qc_user_ids,qa_user_ids:d.qa_user_ids})});setNotice(`Rework Cycle ${rw.cycle_number} team confirmed. The Team Lead was notified to allocate the rework Area / Code / Quantity / Target Date.`);load()}
    catch(err){setError(err instanceof Error?err.message:'Unable to confirm the rework team')}finally{setBusy(false)}
  }

  // Derived state of the Team Lead rework form. Reuse team: the source package's Code / Area / unit / assignees are carried
  // forward (locked unless a justified correction is requested). Adjusted team: nothing is forced, everything is manual.
  function reworkForm(rw:Rework){
    const reuse=rw.team_mode==='reuse';const sources=rw.original_packages
    const sourceId=reworkAllocation.rework_of_package_id||(reuse&&sources.length===1?String(sources[0].id):'')
    const source=sources.find(p=>String(p.id)===sourceId)??null
    const locked=reuse&&!!source&&!reworkAllocation.correct
    const idKey={production:'production_user_id',qc:'qc_user_id',qa:'qa_user_id'} as const
    const carried=(role:'production'|'qc'|'qa')=>reuse&&source&&source.carry_forward[role]?String(source[idKey[role]]??''):''
    return {reuse,sources,source,sourceId,locked,needsSource:reuse&&sources.length>0&&!source,
      code:locked?source!.package_code:reworkAllocation.package_code,
      area:locked?source!.area_name:reworkAllocation.area_name,
      unit:locked?(source!.quantity_unit||'unit'):reworkAllocation.quantity_unit,
      production:reworkAllocation.production_user_id||carried('production'),
      qc:reworkAllocation.qc_user_id||carried('qc'),
      qa:reworkAllocation.qa_user_id||carried('qa')}
  }

  async function allocateRework(e:FormEvent){
    e.preventDefault();const rw=selected?.rework;if(!selected||!rw)return
    const f=reworkForm(rw)
    if(f.needsSource){setError('Select the original work package first.');return}
    if(f.reuse&&reworkAllocation.correct&&!reworkAllocation.correction_reason.trim()){setError('Enter a correction reason to change the carried-forward Code / Area.');return}
    setBusy(true);setError('');setNotice('')
    try{await apiFetch(`/operations/workflow/ortho/rework-cycles/${rw.cycle_id}/work-packages`,{method:'POST',body:JSON.stringify({rework_of_package_id:f.sourceId?Number(f.sourceId):null,package_code:f.code||null,area_name:f.area||null,quantity:Number(reworkAllocation.quantity),quantity_unit:f.unit||null,target_date:reworkAllocation.target_date,instructions:reworkAllocation.instructions,production_user_id:f.production?Number(f.production):null,qc_user_id:f.qc?Number(f.qc):null,qa_user_id:f.qa?Number(f.qa):null,correction_reason:f.reuse&&reworkAllocation.correct?reworkAllocation.correction_reason.trim():null})});setReworkAllocation(emptyReworkAllocation);setNotice(`Rework work allocated for Cycle ${rw.cycle_number}. Production, QC and QA employees were notified.`);load()}
    catch(err){setError(err instanceof Error?err.message:'Unable to allocate rework work')}finally{setBusy(false)}
  }

  function reworkAllocationPanel(project:Project){
    const rw=project.rework;if(!rw)return null
    const f=reworkForm(rw);const draft=reworkAllocation
    const lockedStyle=f.locked?{background:'#f1f5f9'}:undefined
    const gone=f.source?(['production','qc','qa'] as const).filter(r=>f.reuse&&f.source&&!f.source.carry_forward[r]&&f.source[({production:'production_user_id',qc:'qc_user_id',qa:'qa_user_id'} as const)[r]]):[]
    return <section className="operations-panel"><header><div><span className="operations-kicker">TEAM LEAD · REWORK ALLOCATION · CYCLE #{rw.cycle_number}</span><h2>Allocate Rework Area / Code / Quantity / Target Date</h2><p>{f.reuse?'Reused team: the Code, Area and assignees are carried forward automatically from the original work package. Only the new quantity, target date and instructions are entered.':'Adjusted team: enter the Code and Area for this rework; they are not forced to match the original.'} This creates a NEW rework work package linked to this rework cycle; the original delivered work package is not changed.</p></div></header>
      <form className="operations-form-grid" onSubmit={allocateRework}>
        <label className="operations-field operations-span-2"><span>Original work package {f.reuse&&f.sources.length?'*':'(optional link)'}</span><select value={f.sourceId} required={f.reuse&&f.sources.length>0} onChange={e=>setReworkAllocation({...draft,rework_of_package_id:e.target.value,...(f.reuse?{production_user_id:'',qc_user_id:'',qa_user_id:'',correct:false,correction_reason:'',package_code:'',area_name:''}:{})})}><option value="">{f.reuse&&f.sources.length?'Select the original work package first':'Not linked to a specific package'}</option>{f.sources.map(p=><option key={p.id} value={p.id}>{p.package_code} · {p.area_name} ({label(p.current_stage)})</option>)}</select></label>
        <label className="operations-field"><span>Code *{f.locked&&' (from original)'}</span><input value={f.code} readOnly={f.locked} style={lockedStyle} onChange={e=>setReworkAllocation({...draft,package_code:e.target.value})} required/></label>
        <label className="operations-field"><span>Area *{f.locked&&' (from original)'}</span><input value={f.area} readOnly={f.locked} style={lockedStyle} onChange={e=>setReworkAllocation({...draft,area_name:e.target.value})} required/></label>
        <label className="operations-field"><span>Quantity *</span><input type="number" step="0.001" min="0.001" value={draft.quantity} onChange={e=>setReworkAllocation({...draft,quantity:e.target.value})} required/></label>
        <label className="operations-field"><span>Unit *</span><input value={f.unit} readOnly={f.locked} style={lockedStyle} onChange={e=>setReworkAllocation({...draft,quantity_unit:e.target.value})} required/></label>
        <label className="operations-field"><span>Target Date *</span><input type="date" value={draft.target_date} onChange={e=>setReworkAllocation({...draft,target_date:e.target.value})} required/></label>
        <label className="operations-field"><span>Production *</span><select value={f.production} onChange={e=>setReworkAllocation({...draft,production_user_id:e.target.value})} required><option value="">Select</option>{tlProduction.map(m=><option key={m.user_id} value={m.user_id}>{m.employee_id?`${m.employee_id} · `:''}{m.full_name}</option>)}</select></label>
        <label className="operations-field"><span>QC *</span><select value={f.qc} onChange={e=>setReworkAllocation({...draft,qc_user_id:e.target.value})} required><option value="">Select</option>{tlQc.map(m=><option key={m.user_id} value={m.user_id}>{m.employee_id?`${m.employee_id} · `:''}{m.full_name}</option>)}</select></label>
        <label className="operations-field"><span>QA *</span><select value={f.qa} onChange={e=>setReworkAllocation({...draft,qa_user_id:e.target.value})} required><option value="">Select</option>{tlQa.map(m=><option key={m.user_id} value={m.user_id}>{m.employee_id?`${m.employee_id} · `:''}{m.full_name}</option>)}</select></label>
        {!!gone.length&&<div className="operations-note operations-span-2">The original {gone.join(' / ').toUpperCase()} assignee is no longer on the team. Select the assignee above.</div>}
        {f.reuse&&f.source&&<label className="operations-check operations-span-2"><input type="checkbox" checked={draft.correct} onChange={e=>setReworkAllocation(e.target.checked?{...draft,correct:true,package_code:f.source!.package_code,area_name:f.source!.area_name,quantity_unit:f.source!.quantity_unit||'unit'}:{...draft,correct:false,correction_reason:'',package_code:'',area_name:''})}/><span>Correct the carried-forward Code / Area / Unit (a written reason is required)</span></label>}
        {f.reuse&&draft.correct&&<label className="operations-field operations-span-2"><span>Correction reason *</span><input value={draft.correction_reason} onChange={e=>setReworkAllocation({...draft,correction_reason:e.target.value})} required/></label>}
        <label className="operations-field operations-span-2"><span>Instructions *</span><textarea value={draft.instructions} onChange={e=>setReworkAllocation({...draft,instructions:e.target.value})} required placeholder="What must be corrected / added in this rework"/></label>
        <div className="operations-actions operations-span-2"><button className="operations-button" disabled={busy||f.needsSource}>Assign Rework Work &amp; Notify</button></div>
      </form></section>
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
      <section className="operations-panel operations-current-project"><div className="operations-current-project-row"><label className="operations-field"><span>Project</span><select value={selectedId??''} onChange={e=>setSelectedId(Number(e.target.value))}>{data.projects.map(p=><option key={p.project_id} value={p.project_id}>{p.project_code} · Client ID {p.client_code||'—'}</option>)}</select></label>{selected&&<div className="operations-current-project-meta"><strong>{selected.project_code}</strong><span>Client ID: {selected.client_code||'—'}</span><span>{selected.start_date||'—'} → {selected.end_date||'—'}</span><span>My Role: {selected.my_roles.map(label).join(', ')||'Read only'}</span><span>Status: {label(selected.workflow_status)}</span>{(selected.can_manage_team||user?.role==='management'||user?.role==='admin')&&<Link className="operations-button secondary" to={`/ortho/project-360/${selected.project_id}`}>Project 360 · Feedback &amp; Chat</Link>}</div>}</div></section>

      {selected&&<section className="stats-grid">
        <StatCard icon={ClipboardList} label="Work Packages" value={selected.summary.packages}/><StatCard icon={Users} label="Production" value={selected.summary.production}/><StatCard icon={ShieldCheck} label="QC" value={selected.summary.qc} tone="purple"/><StatCard icon={CheckCircle2} label="QA" value={selected.summary.qa} tone="green"/><StatCard icon={Truck} label="Delivered" value={selected.summary.delivered} tone="green"/>
      </section>}

      {selected?.rework&&<section className="operations-panel"><header><div><span className="operations-kicker">REWORK CYCLE #{selected.rework.cycle_number}</span><h2>Client / Change Request Rework</h2><p>{selected.rework.cycle_label} on {selected.project_code} · Client ID {selected.client_code||'—'}. This is rework on the existing project, not a new project: the Project Manager, the Project ID and all original work stay unchanged.</p></div><span className="operations-status warning">{label(selected.rework.status)}</span></header>
        <div className="operations-instructions"><strong>Reason for rework:</strong> {selected.rework.reason}{selected.rework.change_request_code&&<> · <strong>Change Request:</strong> {selected.rework.change_request_code}</>}</div>
        {selected.rework.client_feedback&&<div className="operations-instructions"><strong>Client feedback:</strong> {selected.rework.client_feedback}</div>}
        <div className="operations-project-meta"><span>Project Manager: {selected.rework.project_manager_name||'—'}</span><span>Team Lead: {selected.rework.team_leader_name||'—'}</span><span>Original work preserved: {selected.rework.original_packages.map(p=>`${p.package_code} (${label(p.current_stage)})`).join(', ')||'—'}</span></div>
        {selected.rework.can_confirm_team&&<>
          <div className="operations-team-columns"><label className="operations-check"><input type="radio" name={`rework-mode-${selected.project_id}`} checked={(reworkMode[selected.project_id]??'reuse')==='reuse'} onChange={()=>setReworkMode(v=>({...v,[selected.project_id]:'reuse'}))}/><span><strong>Reuse existing team</strong> — Team Lead {selected.members?.find(m=>m.member_role==='team_leader')?.full_name||'—'} · Production {tlProduction.length} · QC {tlQc.length} · QA {tlQa.length}. Code, Area and assignees are carried forward automatically to the Team Lead.</span></label>
            <label className="operations-check"><input type="radio" name={`rework-mode-${selected.project_id}`} checked={reworkMode[selected.project_id]==='adjust'} onChange={()=>setReworkMode(v=>({...v,[selected.project_id]:'adjust'}))}/><span><strong>Adjust rework team</strong> — start from the current team and change members for this rework</span></label></div>
          {reworkMode[selected.project_id]==='adjust'&&<>
            <div className="operations-form-grid"><label className="operations-field"><span>Team Lead *</span><select value={draftFor(selected).team_leader_user_id} onChange={e=>patchTeam(selected,{team_leader_user_id:e.target.value})}><option value="">Select exactly one</option>{data?.employees.map(emp=><option key={emp.id} value={emp.id}>{emp.employee_id?`${emp.employee_id} · `:''}{emp.full_name}</option>)}</select></label></div>
            <div className="operations-team-columns">{(['production_user_ids','qc_user_ids','qa_user_ids'] as const).map(key=><div className="operations-team-box" key={key}><strong>{key.startsWith('production')?'Production Employees':key.startsWith('qc')?'QC Employees':'QA Employees'}</strong>{data?.employees.map(emp=><label className="operations-check" key={emp.id}><input type="checkbox" checked={draftFor(selected)[key].includes(emp.id)} onChange={()=>toggleTeam(selected,key,emp.id)}/><span>{emp.employee_id?`${emp.employee_id} · `:''}{emp.full_name}</span></label>)}</div>)}</div>
          </>}
          <label className="operations-field"><span>Remarks (optional)</span><input value={reworkRemarks[selected.project_id]||''} onChange={e=>setReworkRemarks(v=>({...v,[selected.project_id]:e.target.value}))}/></label>
          <div className="operations-actions"><button className="operations-button" disabled={busy} onClick={()=>confirmReworkTeam(selected)}><Send size={15}/> Confirm Rework Team &amp; Start Rework Production</button></div>
        </>}
        {selected.rework.status==='REWORK_OPEN'&&!selected.rework.can_confirm_team&&<div className="operations-note">Waiting for the Project Manager to confirm the rework team.</div>}
        {selected.rework.status==='REWORK_PRODUCTION'&&!selected.rework.can_allocate&&<div className="operations-note">Rework team confirmed. The Team Lead allocates the rework Area / Code / Quantity / Target Date.</div>}
        {(selected.rework.status==='REWORK_QC'||selected.rework.status==='REWORK_QA')&&<div className="operations-note">Rework is in {selected.rework.status==='REWORK_QC'?'QC':'QA'}. It moves forward automatically as the assigned employees complete each step; a rejection sends it back to Production.</div>}
        {selected.rework.status==='REWORK_DELIVERED'&&<div className="operations-note">The corrected delivery is complete. Waiting for BD to resubmit it to the client.</div>}
      </section>}

      {selected?.rework?.can_allocate&&reworkAllocationPanel(selected)}

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

      {selected&&selected.my_roles?.includes('project_manager')&&<PMBillingBasisPanel projectId={selected.project_id} projectCode={selected.project_code}/>}

      {selected&&<section className="operations-panel"><header><div><span className="operations-kicker">ASSIGNMENT TRACKER</span><h2>{selected.can_manage_team||selected.can_allocate_work?'Project Work Packages':'My Exact Assigned Work'}</h2><p>Daily progress is calculated from activity entries. Cumulative quantity and progress percentage cannot be manually overwritten.</p></div>{selected.can_complete_project&&<button className="operations-button success" disabled={busy} onClick={()=>completeProject(selected)}><CheckCircle2 size={15}/> Complete Project</button>}</header>
        {!selected.packages.length?<div className="operations-empty">No work package is visible for this assignment yet.</div>:<div className="operations-daily-list">{selected.packages.map(pkg=>{const d=daily[pkg.id]??emptyDaily;return <article className="operations-daily-card" key={pkg.id}>
          <div className="operations-daily-heading"><div><span className="operations-kicker">{pkg.package_code}</span><h3>{pkg.area_name}</h3><div className="operations-project-meta"><span>Project: {selected.project_code}</span><span>Client ID: {selected.client_code||'—'}</span><span>My Role: {pkg.my_roles.map(label).join(', ')||'Monitoring'}</span><span>Target: {pkg.target_date||'—'}</span></div></div><div>{pkg.rework_cycle_id&&<span className="operations-status warning">Rework Cycle #{pkg.rework_cycle_number}{pkg.rework_of_package_code?` · of ${pkg.rework_of_package_code}`:''}</span>} <span className="operations-status">{label(pkg.current_stage)}</span></div></div>
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
