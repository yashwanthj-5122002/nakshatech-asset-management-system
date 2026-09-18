import { CheckCircle2, FolderKanban, RefreshCcw, Save, ShieldCheck, ShieldAlert, UsersRound } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch } from '../../../lib/api'
import '../operations.css'
import '../project-workstreams.css'

type DepartmentSpec = { code:string; label:string; role:string }
type ManagerOption = { id:number; full_name:string; email:string; role:string; department_code:string; department?:string|null; designation?:string|null }
type Workstream = {
  id:number; project_id:number; project_code?:string|null; project_name?:string|null; client_name?:string|null;
  department_code:string; department_label:string; department_role:string; project_manager_user_id:number;
  project_manager_name?:string|null; project_manager_email?:string|null; sequence_order:number; status:string;
  notes?:string|null; is_active:boolean; completed_at?:string|null; updated_at?:string|null
}
type ProjectRow = {
  opportunity_id?:number|null; opportunity_code?:string|null; opportunity_title?:string|null;
  project_id:number; project_code:string; project_name:string; client_name?:string|null; project_status:string; workstreams:Workstream[]
}
type Dashboard = {
  viewer_mode:'bd_editor'|'department'|'read_only'; current_role:string; routing_mode?:string; live_technical_routing_enabled?:boolean; demo_mode?:boolean;
  technical_departments:DepartmentSpec[]; project_manager_directory:ManagerOption[]; projects:ProjectRow[]
}
type DraftRow = { enabled:boolean; managerId:string; sequence:number; notes:string }
type DraftMap = Record<number, Record<string, DraftRow>>

const statusOptions = ['planned','ready','in_progress','blocked','completed']
function label(value:string){ return value.replaceAll('_',' ').replace(/\b\w/g, c=>c.toUpperCase()) }

export function ProjectWorkstreamsPage(){
  const { user } = useAuth()
  const [data,setData]=useState<Dashboard|null>(null)
  const [drafts,setDrafts]=useState<DraftMap>({})
  const [busy,setBusy]=useState('')
  const [error,setError]=useState('')
  const [notice,setNotice]=useState('')

  function buildDrafts(result:Dashboard){
    const next:DraftMap={}
    for(const project of result.projects){
      next[project.project_id]={}
      for(const department of result.technical_departments){
        const existing=project.workstreams.find(item=>item.department_code===department.code)
        next[project.project_id][department.code]={
          enabled:!!existing,
          managerId:existing?String(existing.project_manager_user_id):'',
          sequence:existing?.sequence_order ?? (result.technical_departments.findIndex(item=>item.code===department.code)+1),
          notes:existing?.notes || '',
        }
      }
    }
    setDrafts(next)
  }

  function load(){
    setError('')
    void apiFetch<Dashboard>('/operations/project-workstreams/dashboard')
      .then(result=>{setData(result);if(result.viewer_mode==='bd_editor')buildDrafts(result)})
      .catch(err=>setError(err instanceof Error?err.message:'Could not load Project Workstreams'))
  }
  useEffect(load,[])

  const roleTitle=useMemo(()=>{
    const map:Record<string,string>={ortho:'Ortho',lidar:'LiDAR',civil:'Civil',laser_scanning:'Laser Scanning',bim:'BIM',mobile_mapping:'Mobile Mapping'}
    return map[data?.current_role || user?.role || ''] || 'Project Coordination'
  },[data?.current_role,user?.role])

  function patchDraft(projectId:number,departmentCode:string,patch:Partial<DraftRow>){
    setDrafts(current=>({
      ...current,
      [projectId]:{
        ...(current[projectId]||{}),
        [departmentCode]:{...(current[projectId]?.[departmentCode]||{enabled:false,managerId:'',sequence:1,notes:''}),...patch},
      },
    }))
  }

  async function saveProject(project:ProjectRow){
    if(!project.opportunity_id){setError('This Project ID is not linked to a BD opportunity.');return}
    const projectDraft=drafts[project.project_id]||{}
    const selected=data?.technical_departments.filter(dept=>projectDraft[dept.code]?.enabled)||[]
    if(!selected.length){setError('Select at least one technical department.');return}
    const missing=selected.find(dept=>!projectDraft[dept.code]?.managerId)
    if(missing){setError(`Select the ${missing.label} Project Manager.`);return}
    setBusy(`save-${project.project_id}`);setError('');setNotice('')
    try{
      await apiFetch(`/operations/bd/opportunities/${project.opportunity_id}/workstreams`,{
        method:'PUT',
        body:JSON.stringify({workstreams:selected.map(dept=>({
          department_code:dept.code,
          project_manager_user_id:Number(projectDraft[dept.code].managerId),
          sequence_order:Number(projectDraft[dept.code].sequence)||1,
          notes:projectDraft[dept.code].notes.trim()||null,
        }))}),
      })
      setNotice(`${project.project_code}: department workstreams saved.`)
      load()
    }catch(err){setError(err instanceof Error?err.message:'Could not save project workstreams')}
    finally{setBusy('')}
  }

  async function changeStatus(workstream:Workstream,status:string){
    setBusy(`status-${workstream.id}`);setError('');setNotice('')
    try{
      await apiFetch(`/operations/project-workstreams/${workstream.id}/status`,{method:'PATCH',body:JSON.stringify({status})})
      setNotice(`${workstream.project_code} · ${workstream.department_label}: ${label(status)}.`)
      load()
    }catch(err){setError(err instanceof Error?err.message:'Could not update workstream status')}
    finally{setBusy('')}
  }

  return <div className="operations-page workstreams-page">
    <DashboardHeader
      eyebrow="MASTER PROJECT · TECHNICAL WORKSTREAMS"
      title={data?.viewer_mode==='department'?`${roleTitle} Dashboard`:'Project Workstreams'}
      description={data?.viewer_mode==='bd_editor'
        ? 'After Finance creates and BD links the official Project ID, select one or more technical departments and assign each department Project Manager. All teams remain under the same master Project ID.'
        : data?.viewer_mode==='department'
          ? 'Projects assigned to your department. Phase 1 tracks department ownership and progress under the shared master Project ID.'
          : 'Read-only oversight across all technical department workstreams under each master Project ID.'}
      actions={<button className="operations-button secondary" type="button" onClick={load}><RefreshCcw size={16}/> Refresh</button>}
    />

    {data&&<div className="operations-readonly">{data.live_technical_routing_enabled?<ShieldCheck size={16}/>:<ShieldAlert size={16}/>} <strong>{data.live_technical_routing_enabled?'Phase 7 LIVE:':'UAT Demo:'}</strong> {data.live_technical_routing_enabled?'Project Manager selection uses only PM-eligible real Technical Team Directory members. Assignment email is sent after the workstream save commits.':'Reserved demo PM routing remains active until Admin performs the Phase 7 cutover.'}</div>}
    {notice&&<div className="success-message">{notice}</div>}
    {error&&<div className="error-message">{error}</div>}

    <section className="operations-panel workstreams-foundation">
      <header><div><span className="operations-kicker">PHASE 1 FOUNDATION</span><h2>One Project ID · Multiple Connected Department Workstreams</h2><p>Ortho, LiDAR, Civil, Laser Scanning, BIM and Mobile Mapping are child workstreams of the same official project. Sample requests and cross-team data handovers will build on this foundation in the next phases.</p></div></header>
      <div className="workstreams-department-strip">{data?.technical_departments.map(item=><span key={item.code}>{item.label}</span>)}</div>
    </section>

    {!data?<section className="operations-panel"><div className="operations-empty">Loading project workstreams…</div></section>
    :data.projects.length===0?<section className="operations-panel"><div className="operations-empty">No linked/assigned master projects are available for this login yet.</div></section>
    :<div className="workstreams-project-list">{data.projects.map(project=><section className="operations-panel workstreams-project" key={project.project_id}>
      <header><div><span className="operations-kicker">{project.opportunity_code||'MASTER PROJECT'}</span><h2>{project.project_code} · {project.project_name}</h2><p>{project.client_name||'Client not recorded'} · Project status: {label(project.project_status)}</p></div><div className="workstreams-project-count"><FolderKanban size={18}/><strong>{project.workstreams.length}</strong><span>active team{project.workstreams.length===1?'':'s'}</span></div></header>

      {data.viewer_mode==='bd_editor'?<div className="workstreams-config-grid">{data.technical_departments.map(department=>{
        const draft=drafts[project.project_id]?.[department.code]||{enabled:false,managerId:'',sequence:1,notes:''}
        const managers=data.project_manager_directory.filter(item=>item.department_code===department.code)
        return <article className={`workstream-config-card ${draft.enabled?'selected':''}`} key={department.code}>
          <label className="workstream-check"><input type="checkbox" checked={draft.enabled} onChange={event=>patchDraft(project.project_id,department.code,{enabled:event.target.checked})}/><span>{department.label}</span></label>
          <label><span>Department Project Manager</span><select disabled={!draft.enabled} value={draft.managerId} onChange={event=>patchDraft(project.project_id,department.code,{managerId:event.target.value})}><option value="">{data.live_technical_routing_enabled?'Select real production PM':'Select demo/department PM'}</option>{managers.map(manager=><option key={manager.id} value={manager.id}>{manager.full_name} · {manager.email}</option>)}</select></label>
          <label><span>Workflow Order</span><input disabled={!draft.enabled} type="number" min={1} max={50} value={draft.sequence} onChange={event=>patchDraft(project.project_id,department.code,{sequence:Number(event.target.value)||1})}/></label>
          <label><span>Phase 1 Notes</span><input disabled={!draft.enabled} value={draft.notes} onChange={event=>patchDraft(project.project_id,department.code,{notes:event.target.value})} placeholder="Optional"/></label>
        </article>
      })}<div className="operations-actions workstreams-save"><button className="operations-button" type="button" disabled={busy===`save-${project.project_id}`} onClick={()=>void saveProject(project)}><Save size={16}/>{busy===`save-${project.project_id}`?'Saving…':'Save Department Workstreams'}</button></div></div>
      :<div className="workstreams-table-wrap"><table className="operations-table"><thead><tr><th>Order</th><th>Department</th><th>Project Manager</th><th>Status</th><th>Notes</th><th>Updated</th></tr></thead><tbody>{project.workstreams.map(workstream=><tr key={workstream.id}>
        <td><strong>#{workstream.sequence_order}</strong></td><td><strong>{workstream.department_label}</strong><small>{workstream.department_role}</small></td><td><UsersRound size={14}/> {workstream.project_manager_name||'Not assigned'}<small>{workstream.project_manager_email}</small></td>
        <td>{data.viewer_mode==='department'?<select value={workstream.status} disabled={busy===`status-${workstream.id}`} onChange={event=>void changeStatus(workstream,event.target.value)}>{statusOptions.map(status=><option value={status} key={status}>{label(status)}</option>)}</select>:<span className={`operations-status ${workstream.status==='completed'?'success':workstream.status==='blocked'?'warning':''}`}>{label(workstream.status)}</span>}</td>
        <td>{workstream.notes||'—'}</td><td>{workstream.completed_at?<><CheckCircle2 size={14}/> Completed</>:workstream.updated_at?new Date(workstream.updated_at).toLocaleString('en-IN'):'—'}</td>
      </tr>)}</tbody></table></div>}
    </section>)}</div>}
  </div>
}
