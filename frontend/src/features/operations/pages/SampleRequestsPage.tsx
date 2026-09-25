import { CheckCircle2, FlaskConical, RefreshCcw, RotateCcw, Send, UploadCloud, UsersRound } from 'lucide-react'
import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch } from '../../../lib/api'
import '../operations.css'
import '../sample-requests.css'

type DepartmentSpec = { code:string; label:string; role:string }
type Opportunity = { id:number; opportunity_code:string; title:string; client_name?:string|null; requirement:string; stage:string }
type Submission = { id:number; attempt_no:number; sample_reference:string; notes?:string|null; submitted_by_name?:string|null; submitted_at:string }
type DepartmentRow = {
  id:number; department_code:string; department_label:string; status:string; revision_feedback?:string|null;
  started_at?:string|null; last_submitted_at?:string|null; attempt_count:number; latest_submission?:Submission|null
}
type SampleRequest = {
  id:number; request_code:string; opportunity_id:number; opportunity_code?:string|null; opportunity_title?:string|null;
  client_name?:string|null; requirement?:string|null; title:string; instructions:string; due_date?:string|null;
  status:string; client_feedback?:string|null; client_review_sent_at?:string|null; client_approved_at?:string|null;
  departments:DepartmentRow[]; created_at:string; updated_at:string
}
type Dashboard = {
  viewer_mode:'bd_editor'|'department'|'read_only'; current_role:string; current_department_code?:string|null; demo_mode:boolean; routing_mode?:string; live_technical_routing_enabled?:boolean;
  demo_recipient_emails:Record<string,string>; technical_recipient_emails?:Record<string,string[]>; technical_departments:DepartmentSpec[];
  eligible_opportunities:Opportunity[]; sample_requests:SampleRequest[]
}

function label(value:string){ return value.replaceAll('_',' ').replace(/\b\w/g, c=>c.toUpperCase()) }
function statusClass(value:string){ return value==='client_approved'?'success':value==='revision_requested'?'warning':'' }

export function SampleRequestsPage(){
  const { user } = useAuth()
  const [data,setData]=useState<Dashboard|null>(null)
  const [error,setError]=useState('')
  const [notice,setNotice]=useState('')
  const [busy,setBusy]=useState('')
  const [opportunityId,setOpportunityId]=useState('')
  const [title,setTitle]=useState('Technical Sample')
  const [instructions,setInstructions]=useState('')
  const [dueDate,setDueDate]=useState('')
  const [selectedDepartments,setSelectedDepartments]=useState<string[]>([])
  const [submissionReference,setSubmissionReference]=useState<Record<number,string>>({})
  const [submissionNotes,setSubmissionNotes]=useState<Record<number,string>>({})
  const [clientFeedback,setClientFeedback]=useState<Record<number,string>>({})
  const [revisionDepartments,setRevisionDepartments]=useState<Record<number,string[]>>({})

  function load(){
    setError('')
    void apiFetch<Dashboard>('/operations/samples/dashboard')
      .then(setData)
      .catch(err=>setError(err instanceof Error?err.message:'Unable to load Sample Requests'))
  }
  useEffect(load,[])

  const bdEditor=data?.viewer_mode==='bd_editor'
  const departmentViewer=data?.viewer_mode==='department'
  const currentDepartment=useMemo(
    ()=>data?.technical_departments.find(item=>item.code===data.current_department_code),
    [data],
  )

  function toggleDepartment(code:string){
    setSelectedDepartments(current=>current.includes(code)?current.filter(item=>item!==code):[...current,code])
  }

  async function createRequest(event:FormEvent){
    event.preventDefault()
    if(!opportunityId){setError('Select a BD opportunity.');return}
    if(selectedDepartments.length===0){setError('Select at least one technical department.');return}
    setBusy('create');setError('');setNotice('')
    try{
      const result=await apiFetch<{technical_notifications_created:number;technical_email_sent:number;technical_email_failed:number;routing_mode?:string;demo_notifications_created?:number;demo_email_sent?:number;demo_email_failed?:number}>(`/operations/bd/opportunities/${opportunityId}/samples`,{
        method:'POST',body:JSON.stringify({title,instructions,department_codes:selectedDepartments,due_date:dueDate||null}),
      })
      setNotice(`Sample request created for ${selectedDepartments.length} department(s). ${result.technical_notifications_created} technical dashboard notification(s) created using ${result.routing_mode==='production_live'?'REAL production':'UAT demo'} routing. Email delivery is non-blocking.`)
      setOpportunityId('');setTitle('Technical Sample');setInstructions('');setDueDate('');setSelectedDepartments([]);load()
    }catch(err){setError(err instanceof Error?err.message:'Unable to create sample request')}finally{setBusy('')}
  }

  async function startSample(item:SampleRequest){
    setBusy(`start-${item.id}`);setError('');setNotice('')
    try{await apiFetch(`/operations/samples/${item.id}/start`,{method:'POST'});setNotice(`${item.request_code} started for ${currentDepartment?.label||'your department'}.`);load()}
    catch(err){setError(err instanceof Error?err.message:'Unable to start sample')}finally{setBusy('')}
  }

  async function submitSample(item:SampleRequest){
    const reference=(submissionReference[item.id]||'').trim()
    if(reference.length<3){setError('Enter the sample output reference / folder / shared link.');return}
    setBusy(`submit-${item.id}`);setError('');setNotice('')
    try{
      await apiFetch(`/operations/samples/${item.id}/submit`,{method:'POST',body:JSON.stringify({sample_reference:reference,notes:submissionNotes[item.id]||null})})
      setNotice(`${item.request_code} submitted to BD.`)
      setSubmissionReference(current=>({...current,[item.id]:''}));setSubmissionNotes(current=>({...current,[item.id]:''}));load()
    }catch(err){setError(err instanceof Error?err.message:'Unable to submit sample')}finally{setBusy('')}
  }

  async function sendClientReview(item:SampleRequest){
    setBusy(`client-${item.id}`);setError('');setNotice('')
    try{await apiFetch(`/operations/samples/${item.id}/client-review`,{method:'POST'});setNotice(`${item.request_code} moved to Client Review.`);load()}
    catch(err){setError(err instanceof Error?err.message:'Unable to move sample to client review')}finally{setBusy('')}
  }

  function toggleRevision(itemId:number,code:string){
    setRevisionDepartments(current=>{
      const selected=current[itemId]||[]
      return {...current,[itemId]:selected.includes(code)?selected.filter(item=>item!==code):[...selected,code]}
    })
  }

  async function clientDecision(item:SampleRequest,decision:'approved'|'revision'){
    const feedback=(clientFeedback[item.id]||'').trim()
    const revisions=revisionDepartments[item.id]||[]
    if(decision==='revision'&&revisions.length===0){setError('Select the department(s) that need client revision.');return}
    if(decision==='revision'&&!feedback){setError('Enter the client revision feedback.');return}
    setBusy(`decision-${item.id}`);setError('');setNotice('')
    try{
      const result=await apiFetch<{finance_notifications_created:number;revision_notifications_created:number}>(`/operations/samples/${item.id}/client-decision`,{
        method:'POST',body:JSON.stringify({decision,feedback:feedback||null,revision_department_codes:decision==='revision'?revisions:[]}),
      })
      if(decision==='approved') setNotice(`${item.request_code}: client approved. Finance handoff notification created for Client ID + Project ID creation (${result.finance_notifications_created}).`)
      else setNotice(`${item.request_code}: revision sent back only to the selected technical department(s) (${result.revision_notifications_created} notification(s)).`)
      setClientFeedback(current=>({...current,[item.id]:''}));setRevisionDepartments(current=>({...current,[item.id]:[]}));load()
    }catch(err){setError(err instanceof Error?err.message:'Unable to record client decision')}finally{setBusy('')}
  }

  return <div className="operations-page sample-requests-page">
    <DashboardHeader
      eyebrow="BD · MULTI-TEAM SAMPLE COORDINATION"
      title={bdEditor?'Technical Sample Requests':departmentViewer?`${currentDepartment?.label||'Technical Team'} Sample Inbox`:'Technical Sample Oversight'}
      description="BD can request one sample from multiple peer technical departments. Teams submit independently; BD sends the complete sample to the client. Finance is notified only after client approval."
      actions={<button className="operations-button secondary" onClick={load}><RefreshCcw size={16}/> Refresh</button>}
      meta={<>
        <span className="nk-meta-chip"><FlaskConical size={14}/> One sample requested from multiple peer teams</span>
        <span className="nk-meta-chip"><UsersRound size={14}/> Teams submit independently · BD sends to client</span>
        <span className="nk-meta-chip"><Send size={14}/> Finance notified only after client approval</span>
      </>}
    />
    {data&&<div className="operations-readonly sample-demo-banner"><FlaskConical size={16}/> <strong>{data.live_technical_routing_enabled?'Phase 7 LIVE:':'Phase 2 UAT:'}</strong> {data.live_technical_routing_enabled?'sample actions, notifications and emails use configured real Technical Team Directory recipients.':'reserved demo technical accounts are still used; real team emails remain locked.'}</div>}
    {notice&&<div className="success-message">{notice}</div>}{error&&<div className="error-message">{error}</div>}

    {bdEditor&&<section className="operations-panel sample-create-panel">
      <header><div><span className="operations-kicker">PHASE 2 · BEFORE FINANCE PROJECT CREATION</span><h2>Request Technical Sample</h2><p>Select any combination of the six separate peer technical departments.</p></div></header>
      <form className="operations-form-grid" onSubmit={createRequest}>
        <label className="operations-field"><span>BD Opportunity</span><select value={opportunityId} onChange={e=>setOpportunityId(e.target.value)} required><option value="">Select opportunity</option>{data?.eligible_opportunities.map(item=><option key={item.id} value={item.id}>{item.opportunity_code} · {item.client_name||item.title}</option>)}</select></label>
        <label className="operations-field"><span>Sample Title</span><input value={title} onChange={e=>setTitle(e.target.value)} required minLength={3}/></label>
        <label className="operations-field"><span>Due Date (optional)</span><input type="date" value={dueDate} onChange={e=>setDueDate(e.target.value)}/></label>
        <div className="operations-field operations-span-2"><span>Technical Departments</span><div className="sample-department-grid">{data?.technical_departments.map(department=><label key={department.code} className={`sample-department-choice ${selectedDepartments.includes(department.code)?'selected':''}`}><input type="checkbox" checked={selectedDepartments.includes(department.code)} onChange={()=>toggleDepartment(department.code)}/><strong>{department.label}</strong><small>{data.live_technical_routing_enabled ? ((data.technical_recipient_emails?.[department.code]||[]).join(', ')||'No live sample recipient') : (data.demo_recipient_emails[department.code]||'Demo recipient')}</small></label>)}</div></div>
        <label className="operations-field operations-span-2"><span>Sample Instructions / Expected Output</span><textarea value={instructions} onChange={e=>setInstructions(e.target.value)} minLength={5} required placeholder="Describe what the client wants to see in the sample."/></label>
        <div className="operations-note operations-span-2"><strong>Important:</strong> Sample team selection is independent from final project execution team selection. After client approval, Finance creates Client ID + Project ID; BD then configures actual project workstreams.</div>
        <div className="operations-actions operations-span-2"><button className="operations-button" disabled={busy==='create'}><Send size={16}/> Create & Notify Technical Teams</button></div>
      </form>
    </section>}

    <section className="operations-panel">
      <header><div><span className="operations-kicker">{departmentViewer?'MY SAMPLE INBOX':'LIVE SAMPLE PIPELINE'}</span><h2>{departmentViewer?'Requests Assigned to My Department':'Sample Requests & Client Decisions'}</h2><p>{data?.sample_requests.length||0} request(s).</p></div></header>
      {!data?<div className="operations-empty">Loading sample workflow…</div>:data.sample_requests.length===0?<div className="operations-empty">No sample requests available.</div>:<div className="sample-request-list">{data.sample_requests.map(item=><article className="sample-request-card" key={item.id}>
        <div className="sample-request-heading"><div><span>{item.request_code}</span><h3>{item.title}</h3><small>{item.opportunity_code} · {item.client_name||'Prospect'} · Due {item.due_date||'not specified'}</small></div><span className={`operations-status ${statusClass(item.status)}`}>{label(item.status)}</span></div>
        <div className="sample-request-copy"><strong>Requirement</strong><p>{item.requirement||'—'}</p><strong>Sample Instructions</strong><p>{item.instructions}</p></div>

        <div className="sample-team-grid">{item.departments.map(department=><div className="sample-team-card" key={department.id}><div className="sample-team-title"><strong>{department.department_label}</strong><span className={`operations-status ${statusClass(department.status)}`}>{label(department.status)}</span></div>{department.revision_feedback&&<div className="sample-feedback"><RotateCcw size={14}/><span>{department.revision_feedback}</span></div>}{department.latest_submission?<div className="sample-submission"><small>Latest attempt #{department.latest_submission.attempt_no}</small><strong>{department.latest_submission.sample_reference}</strong>{department.latest_submission.notes&&<p>{department.latest_submission.notes}</p>}<small>{department.latest_submission.submitted_by_name||'Technical team'} · {new Date(department.latest_submission.submitted_at).toLocaleString()}</small></div>:<small>No sample submitted yet.</small>}</div>)}</div>

        {departmentViewer&&item.departments[0]&&<div className="sample-team-actions">{['requested','revision_requested'].includes(item.departments[0].status)&&<button className="operations-button secondary" onClick={()=>void startSample(item)} disabled={!!busy}><UsersRound size={16}/> Start {item.departments[0].status==='revision_requested'?'Revision':'Sample'}</button>}{['requested','in_progress','revision_requested'].includes(item.departments[0].status)&&<><label className="operations-field"><span>Sample Output Reference / Folder / Shared Link</span><input value={submissionReference[item.id]||''} onChange={e=>setSubmissionReference(current=>({...current,[item.id]:e.target.value}))} placeholder="Example: DEMO-LIDAR-SAMPLE-v1 or shared folder path"/></label><label className="operations-field"><span>Submission Notes</span><textarea value={submissionNotes[item.id]||''} onChange={e=>setSubmissionNotes(current=>({...current,[item.id]:e.target.value}))}/></label><button className="operations-button" onClick={()=>void submitSample(item)} disabled={!!busy}><UploadCloud size={16}/> Submit to BD</button></>}</div>}

        {bdEditor&&item.status==='ready_for_client_review'&&<div className="operations-actions sample-client-actions"><button className="operations-button" onClick={()=>void sendClientReview(item)} disabled={!!busy}><Send size={16}/> Send Complete Sample to Client Review</button></div>}

        {bdEditor&&item.status==='client_review'&&<div className="sample-client-decision"><h4>Record Client Decision</h4><label className="operations-field"><span>Client Feedback / Approval Notes</span><textarea value={clientFeedback[item.id]||''} onChange={e=>setClientFeedback(current=>({...current,[item.id]:e.target.value}))} placeholder="For revision, feedback is required."/></label><div><strong>If revision is required, select only the department(s) that must revise:</strong><div className="sample-department-grid compact">{item.departments.map(department=><label key={department.department_code} className={`sample-department-choice ${(revisionDepartments[item.id]||[]).includes(department.department_code)?'selected':''}`}><input type="checkbox" checked={(revisionDepartments[item.id]||[]).includes(department.department_code)} onChange={()=>toggleRevision(item.id,department.department_code)}/><strong>{department.department_label}</strong></label>)}</div></div><div className="operations-actions"><button className="operations-button secondary" onClick={()=>void clientDecision(item,'revision')} disabled={!!busy}><RotateCcw size={16}/> Client Needs Revision</button><button className="operations-button" onClick={()=>void clientDecision(item,'approved')} disabled={!!busy}><CheckCircle2 size={16}/> Client Approved → Notify Finance</button></div></div>}

        {item.status==='client_approved'&&<div className="sample-approved-banner"><CheckCircle2 size={18}/><div><strong>Client Approved</strong><span>Finance has been notified to create/confirm the official Client ID and Project ID. BD will configure actual execution departments afterward.</span></div></div>}
      </article>)}</div>}
    </section>
  </div>
}
