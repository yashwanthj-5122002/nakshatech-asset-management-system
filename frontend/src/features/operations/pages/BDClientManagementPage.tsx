import { ArrowLeft, Building2, FolderPlus, MapPin, Plus, RefreshCcw, Search, UserRound } from 'lucide-react'
import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import '../operations.css'

type Client = {
  id:number; client_code:string; client_name:string; client_email?:string|null; organization_email?:string|null;
  address?:string|null; location?:string|null; country?:string|null; gst_number?:string|null; contact_person_name:string;
  contact_person_email?:string|null; contact_person_phone?:string|null; bd_name?:string|null; source_person_name?:string|null;
  project_count:number; created_at:string; updated_at:string; created_by_name?:string|null; updated_by_name?:string|null; is_active:boolean
}
type Project = {id:number;client_id:number;project_code:string;project_name:string;scope_text?:string|null;workflow_status:string;start_date?:string|null;end_date?:string|null}
type Dashboard = {clients:Client[];projects:Project[]}
type ClientForm = {client_code:string;client_name:string;client_email:string;organization_email:string;address:string;gst_number:string;contact_person_name:string;contact_person_email:string;contact_person_phone:string;bd_name:string}
type ProjectForm = {project_code:string;project_name:string;scope_text:string;start_date:string;end_date:string;commercial_value:string;currency:string;po_wo_number:string;description:string;attachment_references:string}

const emptyClient:ClientForm={client_code:'',client_name:'',client_email:'',organization_email:'',address:'',gst_number:'',contact_person_name:'',contact_person_email:'',contact_person_phone:'',bd_name:''}
const emptyProject:ProjectForm={project_code:'',project_name:'',scope_text:'',start_date:'',end_date:'',commercial_value:'',currency:'INR',po_wo_number:'',description:'',attachment_references:''}
function label(value:string){return value.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase())}

export function BDClientManagementPage(){
  const [data,setData]=useState<Dashboard|null>(null);const [query,setQuery]=useState('');const [selectedId,setSelectedId]=useState<number|null>(null)
  const [showClientForm,setShowClientForm]=useState(false);const [showProjectForm,setShowProjectForm]=useState(false)
  const [clientForm,setClientForm]=useState<ClientForm>(emptyClient);const [projectForm,setProjectForm]=useState<ProjectForm>(emptyProject)
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [notice,setNotice]=useState('')
  function load(){setError('');void apiFetch<Dashboard>('/operations/workflow/bd/dashboard').then(setData).catch(err=>setError(err instanceof Error?err.message:'Unable to load clients'))}
  useEffect(load,[])
  const clients=useMemo(()=>{const needle=query.trim().toLowerCase();return (data?.clients??[]).filter(row=>!needle||row.client_code.toLowerCase().includes(needle)||row.client_name.toLowerCase().includes(needle))},[data,query])
  const selected=data?.clients.find(row=>row.id===selectedId)??null
  const projects=(data?.projects??[]).filter(row=>row.client_id===selectedId)

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
    setBusy(true);setError('');setNotice('')
    try{
      const result=await apiFetch<{project_id:number;project_code:string}>('/operations/workflow/bd/projects',{method:'POST',body:JSON.stringify({
        client_id:selected.id,project_code:projectForm.project_code,project_name:projectForm.project_name,start_date:projectForm.start_date,end_date:projectForm.end_date,
        scope_text:projectForm.scope_text,quantity:null,quantity_unit:'unit',priority:'medium',commercial_value:projectForm.commercial_value===''?null:Number(projectForm.commercial_value),
        currency:projectForm.currency,po_wo_number:projectForm.po_wo_number||null,description:projectForm.description||null,
        attachment_references:projectForm.attachment_references.split('\n').map(value=>value.trim()).filter(Boolean),
      })})
      if(submit)await apiFetch(`/operations/workflow/bd/projects/${result.project_id}/submit-finance`,{method:'POST'})
      setProjectForm(emptyProject);setShowProjectForm(false);setNotice(`${result.project_code} ${submit?'submitted to Finance':'saved as Draft'}.`);load()
    }catch(err){setError(err instanceof Error?err.message:'Unable to create project')}finally{setBusy(false)}
  }

  return <div className="operations-page">
    <DashboardHeader eyebrow="BUSINESS DEVELOPMENT" title="Client Management" description="Find an existing client before creating a new one. Project creation always starts from the selected Client ID." actions={<><button className="operations-button secondary" onClick={load}><RefreshCcw size={16}/> Refresh</button><button className="operations-button" onClick={()=>setShowClientForm(true)}><Plus size={16}/> New Client</button></>}/>
    {notice&&<div className="operations-alert success">{notice}</div>}{error&&<div className="operations-alert error">{error}</div>}

    {showClientForm&&<section className="operations-panel"><header><div><span className="operations-kicker">NEW CLIENT</span><h2>Client Details</h2><p>Client ID is manually entered and duplicate IDs are rejected by the backend.</p></div></header><form className="operations-form-grid" onSubmit={createClient}>
      <label className="operations-field"><span>Client Organization Name *</span><input required value={clientForm.client_name} onChange={e=>setClientForm({...clientForm,client_name:e.target.value})}/></label>
      <label className="operations-field"><span>Client ID * (manual)</span><input required value={clientForm.client_code} onChange={e=>setClientForm({...clientForm,client_code:e.target.value.toUpperCase()})}/></label>
      <label className="operations-field"><span>Client Email ID</span><input type="email" value={clientForm.client_email} onChange={e=>setClientForm({...clientForm,client_email:e.target.value})}/></label>
      <label className="operations-field"><span>Organization Email ID</span><input type="email" value={clientForm.organization_email} onChange={e=>setClientForm({...clientForm,organization_email:e.target.value})}/></label>
      <label className="operations-field"><span>Location</span><input value={clientForm.address} onChange={e=>setClientForm({...clientForm,address:e.target.value})}/></label>
      <label className="operations-field"><span>GST Number</span><input value={clientForm.gst_number} onChange={e=>setClientForm({...clientForm,gst_number:e.target.value.toUpperCase()})}/></label>
      <label className="operations-field"><span>Contact Person Name *</span><input required value={clientForm.contact_person_name} onChange={e=>setClientForm({...clientForm,contact_person_name:e.target.value})}/></label>
      <label className="operations-field"><span>Contact Person Email ID</span><input type="email" value={clientForm.contact_person_email} onChange={e=>setClientForm({...clientForm,contact_person_email:e.target.value})}/></label>
      <label className="operations-field"><span>Contact Person Phone Number</span><input value={clientForm.contact_person_phone} onChange={e=>setClientForm({...clientForm,contact_person_phone:e.target.value})}/></label>
      <label className="operations-field"><span>BD Person Name</span><input value={clientForm.bd_name} onChange={e=>setClientForm({...clientForm,bd_name:e.target.value})}/></label>
      <div className="operations-actions operations-span-2"><button className="operations-button" disabled={busy}>Create Client</button><button type="button" className="operations-button secondary" onClick={()=>setShowClientForm(false)}>Cancel</button></div>
    </form></section>}

    {!selected&&<section className="operations-panel"><header><div><span className="operations-kicker">CLIENT REGISTER</span><h2>Existing Clients</h2></div><label className="operations-search"><Search size={16}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search Client ID / Client Name"/></label></header>
      <div className="operations-client-grid">{clients.map(row=><article key={row.id} className="operations-client-card"><div><Building2 size={22}/><span className="operations-status">{row.client_code}</span></div><h3>{row.client_name}</h3><p><MapPin size={14}/>{row.location||row.country||'Location not recorded'}</p><p><UserRound size={14}/>{row.contact_person_name||'Contact not recorded'}</p><strong>{row.project_count} Project{row.project_count===1?'':'s'}</strong><div className="operations-actions"><button className="operations-button secondary" onClick={()=>setSelectedId(row.id)}>View Client</button><button className="operations-button" onClick={()=>{setSelectedId(row.id);setShowProjectForm(true)}}><FolderPlus size={15}/> Create Project</button></div></article>)}</div>
      {!clients.length&&<div className="operations-empty">No client matches that Client ID or Organization Name.</div>}
    </section>}

    {selected&&<>
      <button className="operations-button secondary" onClick={()=>{setSelectedId(null);setShowProjectForm(false)}}><ArrowLeft size={15}/> Back to Clients</button>
      <section className="operations-panel"><header><div><span className="operations-kicker">{selected.client_code}</span><h2>{selected.client_name}</h2><p>{selected.location||selected.country||'Location not recorded'}</p></div><button className="operations-button" onClick={()=>setShowProjectForm(true)}><FolderPlus size={15}/> Create Project</button></header>
        <div className="operations-detail-grid"><div><span>GST</span><strong>{selected.gst_number||'—'}</strong></div><div><span>Client Email</span><strong>{selected.client_email||'—'}</strong></div><div><span>Organization Email</span><strong>{selected.organization_email||'—'}</strong></div><div><span>Contact Person</span><strong>{selected.contact_person_name||'—'}</strong></div><div><span>Contact Email</span><strong>{selected.contact_person_email||'—'}</strong></div><div><span>Contact Phone</span><strong>{selected.contact_person_phone||'—'}</strong></div><div><span>BD Person</span><strong>{selected.bd_name||selected.source_person_name||'—'}</strong></div><div><span>Audit</span><strong>Created by {selected.created_by_name||'System'} · Updated by {selected.updated_by_name||'System'}</strong></div></div>
      </section>

      {showProjectForm&&<section className="operations-panel"><header><div><span className="operations-kicker">NEW PROJECT · {selected.client_code}</span><h2>{selected.client_name}</h2><p>Client context is fixed for this Project draft.</p></div></header><form className="operations-form-grid" onSubmit={event=>{event.preventDefault();void createProject(false)}}>
        <label className="operations-field"><span>Project ID * (manual)</span><input required value={projectForm.project_code} onChange={e=>setProjectForm({...projectForm,project_code:e.target.value.toUpperCase()})}/></label>
        <label className="operations-field"><span>Project Name / Short Title *</span><input required value={projectForm.project_name} onChange={e=>setProjectForm({...projectForm,project_name:e.target.value})}/></label>
        <label className="operations-field"><span>Start Date *</span><input required type="date" value={projectForm.start_date} onChange={e=>setProjectForm({...projectForm,start_date:e.target.value})}/></label>
        <label className="operations-field"><span>End Date *</span><input required type="date" min={projectForm.start_date||undefined} value={projectForm.end_date} onChange={e=>setProjectForm({...projectForm,end_date:e.target.value})}/></label>
        <label className="operations-field operations-span-2"><span>Project Scope *</span><textarea required value={projectForm.scope_text} onChange={e=>setProjectForm({...projectForm,scope_text:e.target.value})}/></label>
        <label className="operations-field"><span>Project Value</span><input type="number" min="0" step="0.01" value={projectForm.commercial_value} onChange={e=>setProjectForm({...projectForm,commercial_value:e.target.value})}/></label>
        <label className="operations-field"><span>Currency</span><input value={projectForm.currency} onChange={e=>setProjectForm({...projectForm,currency:e.target.value.toUpperCase()})}/></label>
        <label className="operations-field"><span>PO / WO</span><input value={projectForm.po_wo_number} onChange={e=>setProjectForm({...projectForm,po_wo_number:e.target.value})}/></label>
        <label className="operations-field"><span>Attachments / References</span><textarea value={projectForm.attachment_references} onChange={e=>setProjectForm({...projectForm,attachment_references:e.target.value})} placeholder="One file or document reference per line"/></label>
        <label className="operations-field operations-span-2"><span>Remarks</span><textarea value={projectForm.description} onChange={e=>setProjectForm({...projectForm,description:e.target.value})}/></label>
        <div className="operations-actions operations-span-2"><button className="operations-button secondary" disabled={busy}>Save Draft</button><button type="button" className="operations-button" disabled={busy} onClick={()=>void createProject(true)}>Submit to Finance</button><button type="button" className="operations-button secondary" onClick={()=>setShowProjectForm(false)}>Cancel</button></div>
      </form></section>}

      <section className="operations-panel"><header><div><span className="operations-kicker">CLIENT PROJECTS</span><h2>Projects for {selected.client_code}</h2></div></header>{!projects.length?<div className="operations-empty">No projects exist for this client.</div>:<div className="operations-table-wrap"><table className="operations-table"><thead><tr><th>Project ID</th><th>Name / Scope</th><th>Dates</th><th>Status</th></tr></thead><tbody>{projects.map(row=><tr key={row.id}><td><strong>{row.project_code}</strong></td><td>{row.project_name}<small>{row.scope_text}</small></td><td>{row.start_date||'—'} → {row.end_date||'—'}</td><td><span className="operations-status">{label(row.workflow_status)}</span></td></tr>)}</tbody></table></div>}</section>
    </>}
  </div>
}
