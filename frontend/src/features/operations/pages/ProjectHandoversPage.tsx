import {
  ArrowRight,
  CheckCircle2,
  Database,
  Link2,
  RefreshCcw,
  RotateCcw,
  Send,
  Trash2,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import '../operations.css'
import '../project-handovers.css'

type Workstream = {
  id:number
  department_code:string
  department_label:string
  project_manager_user_id:number
  project_manager_name?:string|null
  project_manager_email?:string|null
  sequence_order:number
  status:string
  incoming_dependencies:number
  unresolved_incoming_dependencies:number
  outgoing_connections:number
}

type Handover = {
  id:number
  handover_code:string
  project_id:number
  project_code?:string|null
  project_name?:string|null
  from_workstream_id:number
  from_department_code?:string|null
  from_department_label?:string|null
  from_manager_name?:string|null
  to_workstream_id:number
  to_department_code?:string|null
  to_department_label?:string|null
  to_manager_name?:string|null
  title:string
  expected_output:string
  status:string
  current_attempt_no:number
  revision_feedback?:string|null
  accepted_at?:string|null
  latest_attempt?:{
    attempt_no:number
    output_reference:string
    notes?:string|null
    submitted_by_name?:string|null
    submitted_at:string
  }|null
  permissions:{can_submit:boolean;can_decide:boolean}
  updated_at?:string|null
}

type ProjectRow = {
  project_id:number
  project_code:string
  project_name:string
  client_name?:string|null
  workstreams:Workstream[]
  all_workstreams:Workstream[]
  handovers:Handover[]
}

type Dashboard = {
  viewer_mode:'bd_editor'|'department'|'read_only'
  current_role:string
  current_department_code?:string|null
  demo_mode:boolean
  routing_mode?:string
  live_technical_routing_enabled?:boolean
  projects:ProjectRow[]
}

type ConnectionDraft = {
  fromId:string
  toId:string
  title:string
  expectedOutput:string
}

type SubmissionDraft = { reference:string; notes:string }

const emptyConnection:ConnectionDraft={fromId:'',toId:'',title:'',expectedOutput:''}

function label(value:string){return value.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase())}

function statusClass(status:string){
  if(status==='accepted'||status==='completed')return 'success'
  if(status==='revision_requested'||status==='blocked')return 'warning'
  return ''
}

export function ProjectHandoversPage(){
  const [data,setData]=useState<Dashboard|null>(null)
  const [error,setError]=useState('')
  const [notice,setNotice]=useState('')
  const [busy,setBusy]=useState('')
  const [connections,setConnections]=useState<Record<number,ConnectionDraft>>({})
  const [submissions,setSubmissions]=useState<Record<number,SubmissionDraft>>({})
  const [feedback,setFeedback]=useState<Record<number,string>>({})

  function load(){
    setError('')
    void apiFetch<Dashboard>('/operations/project-handovers/dashboard')
      .then(setData)
      .catch(err=>setError(err instanceof Error?err.message:'Could not load Project Data Handovers'))
  }
  useEffect(load,[])

  const title=useMemo(()=>{
    if(data?.viewer_mode==='department'&&data.current_department_code)return `${label(data.current_department_code)} Data Handovers`
    return 'Project Data Handovers'
  },[data])

  function connectionFor(projectId:number){return connections[projectId]||emptyConnection}
  function patchConnection(projectId:number,patch:Partial<ConnectionDraft>){
    setConnections(current=>({...current,[projectId]:{...connectionFor(projectId),...patch}}))
  }

  async function createConnection(project:ProjectRow){
    const draft=connectionFor(project.project_id)
    if(!draft.fromId||!draft.toId){setError('Select both the sending and receiving departments.');return}
    if(draft.fromId===draft.toId){setError('Sending and receiving departments must be different.');return}
    if(!draft.title.trim()||!draft.expectedOutput.trim()){setError('Enter the handover title and expected output.');return}
    setBusy(`create-${project.project_id}`);setError('');setNotice('')
    try{
      await apiFetch('/operations/bd/project-handovers',{
        method:'POST',
        body:JSON.stringify({
          project_id:project.project_id,
          from_workstream_id:Number(draft.fromId),
          to_workstream_id:Number(draft.toId),
          title:draft.title.trim(),
          expected_output:draft.expectedOutput.trim(),
        }),
      })
      setConnections(current=>({...current,[project.project_id]:{...emptyConnection}}))
      setNotice(`${project.project_code}: department data connection created.`)
      load()
    }catch(err){setError(err instanceof Error?err.message:'Could not create department connection')}
    finally{setBusy('')}
  }

  async function removeConnection(row:Handover){
    if(!window.confirm(`Remove ${row.handover_code}? This is allowed only before the first transfer.`))return
    setBusy(`remove-${row.id}`);setError('');setNotice('')
    try{
      await apiFetch(`/operations/bd/project-handovers/${row.id}`,{method:'DELETE'})
      setNotice(`${row.handover_code} removed.`);load()
    }catch(err){setError(err instanceof Error?err.message:'Could not remove data connection')}
    finally{setBusy('')}
  }

  async function submitHandover(row:Handover){
    const draft=submissions[row.id]||{reference:'',notes:''}
    if(!draft.reference.trim()){setError('Enter the output folder / shared link / data reference before handover.');return}
    setBusy(`submit-${row.id}`);setError('');setNotice('')
    try{
      await apiFetch(`/operations/project-handovers/${row.id}/submit`,{
        method:'POST',
        body:JSON.stringify({output_reference:draft.reference.trim(),notes:draft.notes.trim()||null}),
      })
      setSubmissions(current=>({...current,[row.id]:{reference:'',notes:''}}))
      setNotice(`${row.handover_code}: data sent to ${row.to_department_label}.`);load()
    }catch(err){setError(err instanceof Error?err.message:'Could not submit data handover')}
    finally{setBusy('')}
  }

  async function decide(row:Handover,decision:'accepted'|'revision_requested'){
    const text=(feedback[row.id]||'').trim()
    if(decision==='revision_requested'&&!text){setError('Enter correction feedback before requesting a revision.');return}
    setBusy(`decision-${row.id}`);setError('');setNotice('')
    try{
      await apiFetch(`/operations/project-handovers/${row.id}/decision`,{
        method:'POST',
        body:JSON.stringify({decision,feedback:text||null}),
      })
      setFeedback(current=>({...current,[row.id]:''}))
      setNotice(decision==='accepted'?`${row.handover_code}: data accepted. Your workstream dependency is cleared.`:`${row.handover_code}: correction sent back to ${row.from_department_label}.`)
      load()
    }catch(err){setError(err instanceof Error?err.message:'Could not record handover decision')}
    finally{setBusy('')}
  }

  return <div className="operations-page handovers-page">
    <DashboardHeader
      eyebrow="MASTER PROJECT · CROSS-TEAM DATA FLOW"
      title={title}
      description={data?.viewer_mode==='bd_editor'
        ? 'Connect peer technical departments under the same Project ID. BD defines the direction; the sending team transfers the output and the receiving team formally accepts it.'
        : data?.viewer_mode==='department'
          ? 'Incoming and outgoing project data linked to your department. A receiving workstream becomes ready only after its required upstream handovers are accepted.'
          : 'Read-only oversight of department-to-department project data movement.'}
      actions={<button className="operations-button secondary" type="button" onClick={load}><RefreshCcw size={16}/> Refresh</button>}
    />

    {data&&<div className="handovers-demo-banner"><Database size={16}/><strong>{data.live_technical_routing_enabled?'Phase 7 LIVE:':'Phase 3 UAT:'}</strong> {data.live_technical_routing_enabled?'assigned real PMs own send/receive decisions and configured real handover recipients receive notifications/emails.':'technical notifications and emails use reserved demo department accounts only.'}</div>}
    {notice&&<div className="success-message">{notice}</div>}
    {error&&<div className="error-message">{error}</div>}

    <section className="operations-panel handovers-explainer">
      <header><div><span className="operations-kicker">CONNECTED WORKSTREAM RULE</span><h2>Departments are peers. Data dependency is not department hierarchy.</h2><p>Example: Mobile Mapping sends data to LiDAR, then LiDAR sends processed output to BIM. All three remain independent teams under the same Master Project.</p></div></header>
      <div className="handovers-example-flow"><span>Mobile Mapping</span><ArrowRight/><span>LiDAR</span><ArrowRight/><span>BIM</span></div>
    </section>

    {!data?<section className="operations-panel"><div className="operations-empty">Loading project data handovers...</div></section>
    :data.projects.length===0?<section className="operations-panel"><div className="operations-empty">No linked technical projects are available for this login.</div></section>
    :<div className="handovers-project-list">{data.projects.map(project=>{
      const all=data.viewer_mode==='bd_editor'?project.all_workstreams:project.workstreams
      const draft=connectionFor(project.project_id)
      return <section className="operations-panel handovers-project" key={project.project_id}>
        <header><div><span className="operations-kicker">MASTER PROJECT</span><h2>{project.project_code} · {project.project_name}</h2><p>{project.client_name||'Client not recorded'} · {project.handovers.length} active connection{project.handovers.length===1?'':'s'}</p></div></header>

        <div className="handovers-workstream-strip">{all.map(item=><article key={item.id} className={item.unresolved_incoming_dependencies>0?'waiting':''}>
          <span>#{item.sequence_order}</span><strong>{item.department_label}</strong><small>{label(item.status)}</small>
          {item.unresolved_incoming_dependencies>0&&<em>{item.unresolved_incoming_dependencies} upstream pending</em>}
        </article>)}</div>

        {data.viewer_mode==='bd_editor'&&<div className="handover-create-box">
          <div><span className="operations-kicker">BD · DEFINE TEAM CONNECTION</span><h3>Connect Department Output to Next Department</h3></div>
          <label><span>Sending Department</span><select value={draft.fromId} onChange={event=>patchConnection(project.project_id,{fromId:event.target.value})}><option value="">Select sender</option>{all.map(item=><option value={item.id} key={item.id}>#{item.sequence_order} · {item.department_label} · {item.project_manager_name||'PM'}</option>)}</select></label>
          <ArrowRight className="handover-form-arrow" aria-hidden="true"/>
          <label><span>Receiving Department</span><select value={draft.toId} onChange={event=>patchConnection(project.project_id,{toId:event.target.value})}><option value="">Select receiver</option>{all.map(item=><option value={item.id} key={item.id}>#{item.sequence_order} · {item.department_label} · {item.project_manager_name||'PM'}</option>)}</select></label>
          <label><span>Handover Title</span><input value={draft.title} onChange={event=>patchConnection(project.project_id,{title:event.target.value})} placeholder="Example: Registered point cloud for LiDAR processing"/></label>
          <label><span>Expected Data / Output</span><textarea value={draft.expectedOutput} onChange={event=>patchConnection(project.project_id,{expectedOutput:event.target.value})} placeholder="Describe the folder, dataset, deliverable or processed output the receiving team needs."/></label>
          <div className="operations-actions"><button className="operations-button" type="button" disabled={busy===`create-${project.project_id}`} onClick={()=>void createConnection(project)}><Link2 size={16}/> Create Data Connection</button></div>
        </div>}

        {project.handovers.length===0?<div className="operations-empty">No department-to-department data connections configured yet.</div>
        :<div className="handover-card-list">{project.handovers.map(row=><article className="handover-card" key={row.id}>
          <div className="handover-card-head">
            <div><span className="operations-kicker">{row.handover_code}</span><h3>{row.title}</h3></div>
            <span className={`operations-status ${statusClass(row.status)}`}>{label(row.status)}</span>
          </div>
          <div className="handover-route"><strong>{row.from_department_label}</strong><span>{row.from_manager_name||'Sender PM'}</span><ArrowRight/><strong>{row.to_department_label}</strong><span>{row.to_manager_name||'Receiver PM'}</span></div>
          <div className="handover-expected"><strong>Expected output</strong><p>{row.expected_output}</p></div>
          {row.latest_attempt&&<div className="handover-latest"><strong>Latest transfer · Attempt {row.latest_attempt.attempt_no}</strong><p>{row.latest_attempt.output_reference}</p>{row.latest_attempt.notes&&<small>{row.latest_attempt.notes}</small>}<small>{row.latest_attempt.submitted_by_name||'Sender'} · {new Date(row.latest_attempt.submitted_at).toLocaleString('en-IN')}</small></div>}
          {row.revision_feedback&&<div className="handover-revision"><RotateCcw size={16}/><div><strong>Correction requested</strong><p>{row.revision_feedback}</p></div></div>}
          {row.status==='accepted'&&<div className="handover-accepted"><CheckCircle2 size={16}/><span>Accepted by receiving department{row.accepted_at?` · ${new Date(row.accepted_at).toLocaleString('en-IN')}`:''}</span></div>}

          {row.permissions.can_submit&&<div className="handover-action-box">
            <strong>{row.status==='revision_requested'?'Resubmit corrected data':'Send project data to receiving team'}</strong>
            <label><span>Output Reference / Folder / Shared Link</span><input value={submissions[row.id]?.reference||''} onChange={event=>setSubmissions(current=>({...current,[row.id]:{reference:event.target.value,notes:current[row.id]?.notes||''}}))} placeholder="Example: \\server\\project\\mobile_mapping\\final or secure shared link"/></label>
            <label><span>Transfer Notes</span><textarea value={submissions[row.id]?.notes||''} onChange={event=>setSubmissions(current=>({...current,[row.id]:{reference:current[row.id]?.reference||'',notes:event.target.value}}))} placeholder="Version, coverage, coordinate system, checks completed, or other handover notes"/></label>
            <button className="operations-button" type="button" disabled={busy===`submit-${row.id}`} onClick={()=>void submitHandover(row)}><Send size={16}/>{row.status==='revision_requested'?'Resubmit Data':'Send Data Handover'}</button>
          </div>}

          {row.permissions.can_decide&&<div className="handover-action-box receiver">
            <strong>Receiving Department Review</strong>
            <label><span>Feedback / Acceptance Notes</span><textarea value={feedback[row.id]||''} onChange={event=>setFeedback(current=>({...current,[row.id]:event.target.value}))} placeholder="Required only when requesting correction"/></label>
            <div className="operations-actions"><button className="operations-button secondary" type="button" disabled={busy===`decision-${row.id}`} onClick={()=>void decide(row,'revision_requested')}><RotateCcw size={16}/> Request Correction</button><button className="operations-button" type="button" disabled={busy===`decision-${row.id}`} onClick={()=>void decide(row,'accepted')}><CheckCircle2 size={16}/> Accept Handover</button></div>
          </div>}

          {data.viewer_mode==='bd_editor'&&row.current_attempt_no===0&&<div className="handover-admin-actions"><button className="operations-button secondary" type="button" disabled={busy===`remove-${row.id}`} onClick={()=>void removeConnection(row)}><Trash2 size={15}/> Remove Connection</button></div>}
        </article>)}</div>}
      </section>
    })}</div>}
  </div>
}
