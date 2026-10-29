import { Building2, FolderKanban, Plus, RefreshCcw, RefreshCw, ShieldCheck } from 'lucide-react'
import { type FormEvent, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import { BackToClientsButton, ClientDetailPanel, ClientProjectsPanel, ClientRegisterPanel } from '../components/ClientRegister'
import { useClientRegister } from '../components/useClientRegister'
import { uploadRevisionDocuments, type PendingDocument } from '../../commercial/commercial-api'
import { commercialFormProblems, commercialFormToPayload, emptyCommercialForm, type CommercialFormState } from '../../commercial/commercial-form'
import { CommercialDetailsSection } from '../../commercial/components/CommercialDetailsSection'
import { PendingDocumentsPicker } from '../../commercial/components/SupportingDocuments'
import type { CurrencyPayload } from '../../commercial/types'
import '../operations.css'

type Client = {
  id:number; client_code:string; client_name:string; client_email?:string|null; organization_email?:string|null;
  address?:string|null; location?:string|null; country?:string|null; gst_number?:string|null; contact_person_name:string;
  contact_person_email?:string|null; contact_person_phone?:string|null; bd_name?:string|null; source_person_name?:string|null;
  project_count:number; created_at:string; updated_at:string; created_by_name?:string|null; updated_by_name?:string|null; is_active:boolean
}
type Project = {id:number;client_id:number;project_code:string;project_name:string;scope_text?:string|null;workflow_status:string;start_date?:string|null;end_date?:string|null}
type Dashboard = {clients:Client[];projects:Project[]}

type Pilot = { id:number;project_id:number;client_id:number;project_code:string;project_name:string;client_data_percentage:number;
  workflow_status:string;operational_completed_at:string|null;delivered_at:string|null;delivery_reference:string|null;
  satisfaction:string|null;feedback_note:string|null;paid_project_id:number|null;conversion_eligible:boolean;
  conversion_deferred:boolean;status:string }

type ClientForm = {client_code:string;client_name:string;client_email:string;organization_email:string;address:string;gst_number:string;contact_person_name:string;contact_person_email:string;contact_person_phone:string;bd_name:string}
type ProjectForm = {project_code:string;project_name:string;scope_text:string;start_date:string;end_date:string;description:string}

const emptyClient:ClientForm={client_code:'',client_name:'',client_email:'',organization_email:'',address:'',gst_number:'',contact_person_name:'',contact_person_email:'',contact_person_phone:'',bd_name:''}
const emptyProject:ProjectForm={project_code:'',project_name:'',scope_text:'',start_date:'',end_date:'',description:''}

export function BDClientManagementPage(){
  const [data,setData]=useState<Dashboard|null>(null);const [selectedId,setSelectedId]=useState<number|null>(null)
  const register=useClientRegister(data?.clients??[])
  const [showClientForm,setShowClientForm]=useState(false);const [showProjectForm,setShowProjectForm]=useState(false)
  const [clientForm,setClientForm]=useState<ClientForm>(emptyClient);const [projectForm,setProjectForm]=useState<ProjectForm>(emptyProject)
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [notice,setNotice]=useState('')
  const [commercial,setCommercial]=useState<CommercialFormState>(emptyCommercialForm);const [docs,setDocs]=useState<PendingDocument[]>([]);const [currencies,setCurrencies]=useState<CurrencyPayload|null>(null)
  const [delivery,setDelivery]=useState({priority:'medium',quantity:'',quantity_unit:'',performing_department_code:''})
  useEffect(()=>{void apiFetch<CurrencyPayload>('/commercial/currencies').then(setCurrencies).catch(()=>undefined)},[])
  function load(){setError('');void apiFetch<Dashboard>('/operations/workflow/bd/dashboard').then(setData).catch(err=>setError(err instanceof Error?err.message:'Unable to load clients'))}
  useEffect(load,[])


  const [pilots,setPilots]=useState<Pilot[]>([])
  const [showPilotForm,setShowPilotForm]=useState(false)
  const [pilotPercentage,setPilotPercentage]=useState('2')
  const [pilotDataRef,setPilotDataRef]=useState('Client-provided sample')
  const [conversionPilotId,setConversionPilotId]=useState<number|null>(null)
  const [pilotFeedback,setPilotFeedback]=useState<Record<number,{satisfaction:string;note:string}>>({})
  const [pilotDelivery,setPilotDelivery]=useState<Record<number,string>>({})
  function loadPilots(){void apiFetch<Pilot[]>('/operations/pilots').then(setPilots).catch(()=>undefined)}
  useEffect(loadPilots,[])
  function openPilot(id:number){setSelectedId(id);setShowProjectForm(false);setConversionPilotId(null);setShowPilotForm(true);setProjectForm(emptyProject)}
  function openPaidProject(id:number,conversion:number|null=null){setSelectedId(id);setShowPilotForm(false);setConversionPilotId(conversion);setShowProjectForm(true);setProjectForm(emptyProject);setCommercial(emptyCommercialForm())}
  const conversionPrompt=conversionPilotId===null?pilots.find(p=>p.conversion_eligible&&!p.conversion_deferred)??null:null
  async function createPilot(){
    if(!selected)return
    if(!delivery.performing_department_code){setError('Select the performing department.');return}
    setBusy(true);setError('');setNotice('')
    try{
      const result=await apiFetch<Pilot>('/operations/pilots',{method:'POST',body:JSON.stringify({
        client_id:selected.id,project_code:projectForm.project_code,project_name:projectForm.project_name,
        start_date:projectForm.start_date,end_date:projectForm.end_date,scope_text:projectForm.scope_text,
        description:projectForm.description||null,quantity:delivery.quantity===''?null:Number(delivery.quantity),
        quantity_unit:delivery.quantity_unit||'unit',priority:delivery.priority,
        performing_department_code:delivery.performing_department_code,
        commercial_value:0,currency:'INR',po_wo_number:null,attachment_references:[],commercial:null,
        client_data_percentage:Number(pilotPercentage),client_data_reference:pilotDataRef.trim()
      })})
      setShowPilotForm(false);setProjectForm(emptyProject);setPilotDataRef('Client-provided sample');setPilotPercentage('2')
      setNotice(`${result.project_code} created as a non-billable pilot. Assign a Project Manager from BD Project Management.`)
      load();loadPilots()
    }catch(err){setError(err instanceof Error?err.message:'Unable to create pilot')}finally{setBusy(false)}
  }
  async function pilotAction(id:number,action:'deliver'|'feedback'|'defer',body?:unknown){
    setBusy(true);setError('')
    try{await apiFetch(`/operations/pilots/${id}/${action}`,{method:'POST',...(body!==undefined?{body:JSON.stringify(body)}:{})})
      setNotice(action==='deliver'?'Pilot delivery recorded. You can now record client feedback.':action==='feedback'?'Client feedback recorded.':'Conversion postponed; pilot remains available.')
      loadPilots()
    }catch(err){setError(err instanceof Error?err.message:'Pilot operation failed')}finally{setBusy(false)}
  }

  const [searchParams] = useSearchParams()
  useEffect(() => {
    const requested = Number(searchParams.get('client'))
    if (Number.isInteger(requested) && requested > 0) { setSelectedId(requested); setShowProjectForm(false) }
  }, [searchParams])

  useEffect(() => {
   if (!notice) return
   const handle = window.setTimeout(() => setNotice(''), 6000)
   return () => window.clearTimeout(handle)
  }, [notice])
  const selected=data?.clients.find(row=>row.id===selectedId)??null
  const projects=(data?.projects??[]).filter(row=>row.client_id===selectedId).map(row=>({...row,status:row.workflow_status}))

  async function createClient(event:FormEvent){
    event.preventDefault();setBusy(true);setError('');setNotice('')
    try{
      const saved=await apiFetch<Client>('/operations/workflow/bd/clients',{method:'POST',body:JSON.stringify({
        client_code:clientForm.client_code,client_name:clientForm.client_name,client_email:clientForm.client_email||null,
        organization_email:clientForm.organization_email||null,address:clientForm.address||null,gst_number:clientForm.gst_number||null,
        contact_person_name:clientForm.contact_person_name,contact_person_email:clientForm.contact_person_email||null,
        contact_person_phone:clientForm.contact_person_phone||null,bd_name:clientForm.bd_name||null,country:'India',source_team:'bd_team',is_active:true,
      })})
      setClientForm(emptyClient);setShowClientForm(false);setSelectedId(saved.id);setNotice(`Client ID ${saved.client_code} created.`);load()
    }catch(err){setError(err instanceof Error?err.message:'Unable to create client')}finally{setBusy(false)}
  }

  async function createProject(submit:boolean){
    if(!selected)return
    setError('');setNotice('')
    if(!delivery.performing_department_code){setError('Select the Performing Department before saving or submitting this project.');return}
    const problems=commercialFormProblems(commercial)
    if(problems.length){setError(problems[0]);return}
    setBusy(true)
    try{
      // Project + Commercial Revision 1 are created in ONE request/transaction: either both exist or neither does.
      const result=await apiFetch<{project_id:number;project_code:string;commercial?:{baseline?:{id:number}|null}}>('/operations/workflow/bd/projects',{method:'POST',body:JSON.stringify({
        client_id:selected.id,project_code:projectForm.project_code,project_name:projectForm.project_name,start_date:projectForm.start_date,end_date:projectForm.end_date,
        scope_text:projectForm.scope_text,quantity:delivery.quantity===''?null:Number(delivery.quantity),quantity_unit:delivery.quantity_unit||'unit',priority:delivery.priority,
        performing_department_code:delivery.performing_department_code,
        commercial_value:Number(commercial.estimated_amount),currency:commercial.currency_code,po_wo_number:commercial.po_wo_reference.trim()||null,
        attachment_references:[],description:projectForm.description||null,
        commercial:commercialFormToPayload(commercial),
      })})
      if(conversionPilotId!==null){
        try{
          await apiFetch(`/operations/pilots/${conversionPilotId}/link-paid`,{method:'POST',body:JSON.stringify({paid_project_id:result.project_id})})
          setConversionPilotId(null);loadPilots()
        }catch(linkErr){
          setError(`${result.project_code} was CREATED as a paid project, but its pilot link failed. Paid Project ID: ${result.project_id}. Reason: ${linkErr instanceof Error?linkErr.message:'Unknown error'}. Do not create a duplicate project.`)
          load();return
        }
      }
      const revisionId=result.commercial?.baseline?.id
      let failed:string[]=[]
      if(docs.length&&revisionId)failed=await uploadRevisionDocuments(result.project_id,revisionId,docs)
      if(failed.length){
        setProjectForm(emptyProject);setCommercial(emptyCommercialForm());setDocs([]);setShowProjectForm(false);load()
        setError(`${result.project_code} was saved as a Draft with its commercial details, but ${failed.length} document(s) could not be uploaded (${failed.join(', ')}). Attach them from Project Management, then submit to Finance.`)
        return
      }
      if(submit)await apiFetch(`/operations/workflow/bd/projects/${result.project_id}/submit-finance`,{method:'POST'})
      setProjectForm(emptyProject);setCommercial(emptyCommercialForm());setDocs([]);setDelivery({priority:'medium',quantity:'',quantity_unit:'',performing_department_code:''});setShowProjectForm(false)
      setNotice(`${result.project_code} ${submit?'and its Commercial Revision 1 were submitted to Finance':'saved as Draft with Commercial Revision 1'}.`);load()
    }catch(err){setError(err instanceof Error?err.message:'Unable to create project')}finally{setBusy(false)}
  }

  return <div className="operations-page">
    <DashboardHeader eyebrow="BUSINESS DEVELOPMENT · CLIENT INTELLIGENCE" title="Client Management" description="Find an existing client before creating a new one — search the Client Register first. Project creation always starts from the selected Client ID." details={<>
      <div><span>Clients on record</span><strong>{data?.clients.length ?? 0}</strong></div>
      <div><span>Projects linked</span><strong>{data?.projects.length ?? 0}</strong></div>
    </>} actions={<><button className="operations-button secondary" onClick={load}><RefreshCcw size={16}/> Refresh</button><button className="operations-button" onClick={()=>setShowClientForm(true)}><Plus size={16}/> New Client</button></>} meta={<><span className="nk-meta-chip"><Building2 size={14}/> {data?.clients.length ?? 0} clients on record</span><span className="nk-meta-chip"><FolderKanban size={14}/> Project creation starts from a selected Client ID</span><span className="nk-meta-chip"><ShieldCheck size={14}/> Client ID entered manually · duplicates rejected</span></>}/>
    {notice&&<div className="operations-alert success" aria-live="polite">{notice}</div>}{error&&<div className="operations-alert error" aria-live="polite">{error}<button className="operations-button secondary" onClick={load} style={{marginLeft:'8px'}}><RefreshCw size={14}/> Retry</button></div>}

    {showClientForm&&<section className="operations-panel"><header><div><span className="operations-kicker">NEW CLIENT</span><h2>Client Details</h2><p>Client ID is manually entered and duplicate IDs are rejected by the backend.</p></div></header><form className="operations-form-grid" onSubmit={createClient}>
      <label className="operations-field"><span>Client Organization Name </span><input required value={clientForm.client_name} onChange={e=>setClientForm({...clientForm,client_name:e.target.value})}/></label>
      <label className="operations-field"><span>Client ID  (manual)</span><input required value={clientForm.client_code} onChange={e=>setClientForm({...clientForm,client_code:e.target.value.toUpperCase()})}/></label>
      <label className="operations-field"><span>Client Email ID</span><input type="email" value={clientForm.client_email} onChange={e=>setClientForm({...clientForm,client_email:e.target.value})}/></label>
      <label className="operations-field"><span>Organization Email ID</span><input type="email" value={clientForm.organization_email} onChange={e=>setClientForm({...clientForm,organization_email:e.target.value})}/></label>
      <label className="operations-field"><span>Country</span><input value={clientForm.address} onChange={e=>setClientForm({...clientForm,address:e.target.value})}/></label>
      <label className="operations-field"><span>GST /VAT/SUT</span><input value={clientForm.gst_number} onChange={e=>setClientForm({...clientForm,gst_number:e.target.value.toUpperCase()})}/></label>
      <label className="operations-field"><span>Contact Person Name </span><input required value={clientForm.contact_person_name} onChange={e=>setClientForm({...clientForm,contact_person_name:e.target.value})}/></label>
      <label className="operations-field"><span>Contact Person Email ID</span><input type="email" value={clientForm.contact_person_email} onChange={e=>setClientForm({...clientForm,contact_person_email:e.target.value})}/></label>
      <label className="operations-field"><span>Contact Person Ph/no</span><input value={clientForm.contact_person_phone} onChange={e=>setClientForm({...clientForm,contact_person_phone:e.target.value})}/></label>
      <label className="operations-field"><span>BD Person Name</span><input value={clientForm.bd_name} onChange={e=>setClientForm({...clientForm,bd_name:e.target.value})}/></label>
      <div className="operations-actions operations-span-2"><button className="operations-button" disabled={busy}>{busy?'Creating…':'Create Client'}</button><button type="button" className="operations-button secondary" onClick={()=>setShowClientForm(false)}>Cancel</button></div>
    </form></section>}

    {!selected&&<ClientRegisterPanel register={register} loading={!data&&!error} onView={setSelectedId} onCreateClient={()=>setShowClientForm(true)} onCreateProject={id=>openPaidProject(id)} onCreatePilot={openPilot}/>}

    {selected&&<>
      <BackToClientsButton onClick={()=>{setSelectedId(null);setShowProjectForm(false)}}/>
      <ClientDetailPanel client={selected} onCreateProject={()=>openPaidProject(selected.id)} onCreatePilot={()=>openPilot(selected.id)}/>


      {showPilotForm&&<section className="operations-panel"><header><div><span className="operations-kicker">FREE PILOT · {selected.client_code}</span><h2>Create Pilot Demonstration</h2><p>Client provides a small data sample, approximately 2%. The normal technical workflow runs in full. No Finance approval, client invoice, payment or expenses.</p></div></header>
        <form className="operations-form-grid" onSubmit={event=>{event.preventDefault();void createPilot()}}>
          <label className="operations-field"><span>Pilot Project ID *</span><input required value={projectForm.project_code} onChange={e=>setProjectForm({...projectForm,project_code:e.target.value.toUpperCase()})} placeholder="PILOT-001"/></label>
          <label className="operations-field"><span>Project Name *</span><input required value={projectForm.project_name} onChange={e=>setProjectForm({...projectForm,project_name:e.target.value})}/></label>
          <label className="operations-field"><span>Start Date *</span><input required type="date" value={projectForm.start_date} onChange={e=>setProjectForm({...projectForm,start_date:e.target.value})}/></label>
          <label className="operations-field"><span>End Date *</span><input required type="date" min={projectForm.start_date||undefined} value={projectForm.end_date} onChange={e=>setProjectForm({...projectForm,end_date:e.target.value})}/></label>
          <label className="operations-field operations-span-2"><span>Pilot Scope *</span><textarea required value={projectForm.scope_text} onChange={e=>setProjectForm({...projectForm,scope_text:e.target.value})}/></label>
          <label className="operations-field"><span>Client-provided data percentage *</span><input required type="number" min="0.01" max="100" step="0.01" value={pilotPercentage} onChange={e=>setPilotPercentage(e.target.value)}/></label>
          <label className="operations-field"><span>Client data reference *</span><input required minLength={3} value={pilotDataRef} onChange={e=>setPilotDataRef(e.target.value)}/></label>
          <label className="operations-field"><span>Performing Department *</span><select required value={delivery.performing_department_code} onChange={e=>setDelivery({...delivery,performing_department_code:e.target.value})}><option value="" disabled>Select Department</option><option value="ortho">ORTHO</option><option value="lidar">LiDAR</option><option value="mobile_mapping">Mobile Mapping</option><option value="laser_scanning">Laser Scanning</option><option value="civil">Civil</option></select></label>
          <label className="operations-field"><span>Priority</span><select value={delivery.priority} onChange={e=>setDelivery({...delivery,priority:e.target.value})}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="urgent">Urgent</option></select></label>
          <label className="operations-field"><span>Sample quantity (optional)</span><input type="number" min="0" step="0.001" value={delivery.quantity} onChange={e=>setDelivery({...delivery,quantity:e.target.value})}/></label>
          <label className="operations-field"><span>Quantity Unit</span><input value={delivery.quantity_unit} onChange={e=>setDelivery({...delivery,quantity_unit:e.target.value})}/></label>
          <label className="operations-field operations-span-2"><span>Remarks</span><textarea value={projectForm.description} onChange={e=>setProjectForm({...projectForm,description:e.target.value})}/></label>
          <div className="operations-note operations-span-2">Non-billable pilot: ₹0 client payment and no internal expense transactions. Finance and Software receive informational notifications. The standard PM assignment, processing and QA/QC follow the existing workflow.</div>
          <div className="operations-actions operations-span-2"><button className="operations-button" disabled={busy}>{busy?'Creating…':'Create Pilot'}</button><button type="button" className="operations-button secondary" disabled={busy} onClick={()=>setShowPilotForm(false)}>Cancel</button></div>
        </form>
      </section>}
      {pilots.filter(p=>p.client_id===selected.id).length>0&&<section className="operations-panel"><header><div><span className="operations-kicker">CLIENT PILOTS</span><h2>Sample Demonstrations</h2><p>Full operational completion is required before sample delivery; only positive feedback makes a pilot eligible for BD conversion.</p></div></header>
        {pilots.filter(p=>p.client_id===selected.id).map(p=><div key={p.id} className="operations-panel" style={{margin:'12px 0',padding:16}}>
          <strong>{p.project_code} — {p.project_name}</strong><div className="operations-note">Client sample: {p.client_data_percentage}% · Workflow: {p.workflow_status} · Pilot: {p.status} · Client feedback: {p.satisfaction||'Pending'} · Paid project: {p.paid_project_id??'None'}</div>
          {p.operational_completed_at&&!p.delivered_at&&<div className="operations-actions"><input aria-label="Delivery reference" placeholder="Client sample delivery link/reference" value={pilotDelivery[p.id]||''} onChange={e=>setPilotDelivery({...pilotDelivery,[p.id]:e.target.value})}/><button type="button" disabled={busy||!(pilotDelivery[p.id]||'').trim()} className="operations-button" onClick={()=>void pilotAction(p.id,'deliver',{delivery_reference:pilotDelivery[p.id]})}>Record Client Delivery</button></div>}
          {p.delivered_at&&!p.satisfaction&&<div className="operations-actions"><select aria-label="Client satisfaction" value={pilotFeedback[p.id]?.satisfaction||''} onChange={e=>setPilotFeedback({...pilotFeedback,[p.id]:{satisfaction:e.target.value,note:pilotFeedback[p.id]?.note||''}})}><option value="">Client feedback</option><option value="satisfied">Satisfied</option><option value="not_satisfied">Not Satisfied</option></select><input aria-label="Client feedback evidence" placeholder="Client feedback received (email/call/letter)" value={pilotFeedback[p.id]?.note||''} onChange={e=>setPilotFeedback({...pilotFeedback,[p.id]:{satisfaction:pilotFeedback[p.id]?.satisfaction||'',note:e.target.value}})}/><button type="button" className="operations-button" disabled={busy||!pilotFeedback[p.id]?.satisfaction||(pilotFeedback[p.id]?.note||'').trim().length<5} onClick={()=>void pilotAction(p.id,'feedback',pilotFeedback[p.id])}>Record Client Feedback</button></div>}
          {p.conversion_eligible&&<div className="operations-actions"><button type="button" className="operations-button" onClick={()=>openPaidProject(selected.id,p.id)}>Convert to Paid Project</button><button type="button" className="operations-button secondary" onClick={()=>void pilotAction(p.id,'defer')}>Not Now</button></div>}
        </div>)}
      </section>}

      {showProjectForm&&<section className="operations-panel"><header><div><span className="operations-kicker">{conversionPilotId?`PAID PROJECT FROM PILOT ${conversionPilotId}`:`NEW PROJECT · ${selected.client_code}`}</span><h2>{selected.client_name}</h2><p>One process: project information, delivery details, commercial &amp; billing details and supporting documents are submitted to Finance together. Client context is fixed for this Project.</p></div></header><form className="operations-form-grid" onSubmit={event=>{event.preventDefault();void createProject(false)}}>
        <div className="operations-span-2"><span className="operations-kicker">PROJECT INFORMATION</span></div>
        <label className="operations-field"><span>Project ID * (manual)</span><input required value={projectForm.project_code} onChange={e=>setProjectForm({...projectForm,project_code:e.target.value.toUpperCase()})}/></label>
        <label className="operations-field"><span>Project Name / Short Title *</span><input required value={projectForm.project_name} onChange={e=>setProjectForm({...projectForm,project_name:e.target.value})}/></label>
        <label className="operations-field"><span>Start Date *</span><input required type="date" value={projectForm.start_date} onChange={e=>setProjectForm({...projectForm,start_date:e.target.value})}/></label>
        <label className="operations-field"><span>End Date *</span><input required type="date" min={projectForm.start_date||undefined} value={projectForm.end_date} onChange={e=>setProjectForm({...projectForm,end_date:e.target.value})}/></label>
        <label className="operations-field operations-span-2"><span>Project Scope *</span><textarea required value={projectForm.scope_text} onChange={e=>setProjectForm({...projectForm,scope_text:e.target.value})}/></label>
        <label className="operations-field operations-span-2"><span>Remarks</span><textarea value={projectForm.description} onChange={e=>setProjectForm({...projectForm,description:e.target.value})}/></label>

        <div className="operations-span-2"><span className="operations-kicker">DELIVERY / DEPARTMENT INFORMATION</span></div>
        <label className="operations-field"><span>Performing Department *</span><select required value={delivery.performing_department_code} onChange={e=>setDelivery({...delivery,performing_department_code:e.target.value})}>
          <option value="" disabled>Select Performing Department</option><option value="ortho">ORTHO</option><option value="lidar">LiDAR</option><option value="mobile_mapping">Mobile Mapping</option><option value="laser_scanning">Laser Scanning</option><option value="civil">Civil</option>
        </select></label>
        <label className="operations-field"><span>Priority</span><select value={delivery.priority} onChange={e=>setDelivery({...delivery,priority:e.target.value})}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="urgent">Urgent</option></select></label>
        <label className="operations-field"><span>Planned quantity (optional)</span><input type="number" min="0" step="0.001" value={delivery.quantity} onChange={e=>setDelivery({...delivery,quantity:e.target.value})}/></label>
        <label className="operations-field"><span>Quantity unit</span><input value={delivery.quantity_unit} onChange={e=>setDelivery({...delivery,quantity_unit:e.target.value})} placeholder="e.g. sq.km, sites"/></label>
        <div className="operations-note operations-span-2">Finance approves first; you then assign the matching technical Project Manager for the selected Performing Department, who selects the project team.</div>

        <div className="operations-span-2"><CommercialDetailsSection form={commercial} onChange={setCommercial} currencies={currencies} disabled={busy}/></div>

        <div className="operations-span-2"><span className="operations-kicker">SUPPORTING DOCUMENTS</span></div>
        <div className="operations-span-2"><PendingDocumentsPicker docs={docs} onChange={setDocs} disabled={busy}/></div>

        <div className="operations-span-2"><span className="operations-kicker">SUBMIT TO FINANCE</span></div>
        <div className="operations-actions operations-span-2"><button className="operations-button secondary" disabled={busy}>{busy?'Saving…':'Save Draft'}</button><button type="button" className="operations-button" disabled={busy} onClick={()=>void createProject(true)}>{busy?'Submitting…':'Submit to Finance'}</button><button type="button" className="operations-button secondary" onClick={()=>setShowProjectForm(false)}>Cancel</button></div>
      </form></section>}

      <ClientProjectsPanel clientCode={selected.client_code} projects={projects}/>
    </>}

    {conversionPrompt&&<div role="dialog" aria-modal="true" aria-label="Pilot conversion decision" style={{position:'fixed',inset:0,zIndex:9999,background:'rgba(5,18,32,0.65)',display:'flex',alignItems:'center',justifyContent:'center',padding:16}}>
      <div className="operations-panel" style={{width:'min(540px,100%)',maxHeight:'85vh',overflowY:'auto',padding:24}}>
        <span className="operations-kicker">BD ACTION REQUIRED · CLIENT SATISFIED</span><h2>Convert Pilot to Paid Project?</h2>
        <p>{conversionPrompt.project_code} completed its operational workflow, was delivered to the client, and received positive client feedback.</p>
        <p>Only BD can decide. Conversion opens the normal paid-project form; no paid project is created until you submit its commercial details.</p>
        <div className="operations-actions"><button className="operations-button" onClick={()=>openPaidProject(conversionPrompt.client_id,conversionPrompt.id)}>Convert to Paid Project</button><button className="operations-button secondary" onClick={()=>void pilotAction(conversionPrompt.id,'defer')}>Not Now</button></div>
      </div>
    </div>}
  </div>
}