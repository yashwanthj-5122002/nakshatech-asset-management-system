import { Pencil, RefreshCcw, RefreshCw, Send, UserRoundCheck } from 'lucide-react'
import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import { ProjectDetailsPanel, ProjectRegisterFilters, ProjectRegisterTable } from '../components/ProjectRegister'
import { DepartmentChangeDialog } from '../components/DepartmentChangeDialog'
import { filterProjects, financeLabel } from '../components/register-utils'
import { useNotificationPopup } from '../../notifications/NotificationPopupProvider'
import { uploadRevisionDocuments, type PendingDocument } from '../../commercial/commercial-api'
import { commercialFormFromRevision, commercialFormProblems, commercialFormToPayload, emptyCommercialForm, type CommercialFormState } from '../../commercial/commercial-form'
import { CommercialDetailsSection } from '../../commercial/components/CommercialDetailsSection'
import { PendingDocumentsPicker, StoredDocumentsList } from '../../commercial/components/SupportingDocuments'
import type { CommercialEstimate, CommercialSummary, CurrencyPayload } from '../../commercial/types'
import { money, statusLabel } from '../../commercial/types'
import '../operations.css'

type EventRow={id:number;event_type:string;from_status?:string|null;to_status:string;comments?:string|null;actor_name?:string|null;actor_role?:string|null;created_at:string}
type PM={id:number;full_name:string;email:string;employee_id?:string|null}
type Project={
  id:number;client_id:number;project_code:string;project_name:string;client_code?:string|null;client_name?:string|null;start_date?:string|null;end_date?:string|null;
  description?:string|null;scope_text?:string|null;quantity?:number|null;quantity_unit?:string|null;priority?:string|null;commercial_value?:number|null;currency?:string|null;
  po_wo_number?:string|null;attachment_references?:string[];workflow_status:string;normalized_status?:string;finance_feedback?:string|null;project_manager_id?:number|null;project_manager_name?:string|null;
  performing_department_code?:string;performing_department_label?:string;
  submission_count?:number;finance_reviewer_name?:string|null;finance_reviewed_at?:string|null;events?:EventRow[];commercial_summary?:CommercialSummary
}
type Dashboard={projects:Project[];project_managers:PM[];project_managers_by_department?:Record<string,PM[]>;departments?:{code:string;label:string}[]}
type Form={client_id:number;project_code:string;project_name:string;start_date:string;end_date:string;scope_text:string;quantity:string;quantity_unit:string;priority:string;performing_department_code:string;commercial_value:string;currency:string;po_wo_number:string;description:string;attachment_references:string}

function bdFinanceDisplayLabel(row: Project): string {
  if (row.workflow_status === 'pending_finance_approval') return 'Under Finance Review'
  if (row.workflow_status === 'finance_approved') return 'Ready for PM Assignment'
  return financeLabel(row)
}

export function BDProjectManagementPage(){
  // NAKSHA_BD_PROJECTS_PAGINATION_V1 - UI-only pagination; BD workflows are unchanged.
  const BD_PAGE_SIZE = 5;
  const [bdPage,setBdPage]=useState(1);
  const [data,setData]=useState<Dashboard|null>(null);const [query,setQuery]=useState('');const [financeFilter,setFinanceFilter]=useState('all');const [operationalFilter,setOperationalFilter]=useState('all')
  const [selectedId,setSelectedId]=useState<number|null>(null);const [editing,setEditing]=useState<Form|null>(null);const [pmChoice,setPmChoice]=useState<Record<number,string>>({})
  const [departmentEdit,setDepartmentEdit]=useState<{projectId:number;department:string;manager:string;reason:string}|null>(null)
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [notice,setNotice]=useState('');const [loading,setLoading]=useState(true)
  const [commercial,setCommercial]=useState<CommercialFormState>(emptyCommercialForm);const [rev1,setRev1]=useState<CommercialEstimate|null>(null);const [docs,setDocs]=useState<PendingDocument[]>([]);const [currencies,setCurrencies]=useState<CurrencyPayload|null>(null);const [docTick,setDocTick]=useState(0)
  // Centered success/error feedback popups for this important workflow submit.
  const {showFeedback}=useNotificationPopup()
  useEffect(()=>{void apiFetch<CurrencyPayload>('/commercial/currencies').then(setCurrencies).catch(()=>undefined)},[])
  function load(){setLoading(true);setError('');void apiFetch<Dashboard>('/operations/workflow/bd/dashboard').then(setData).catch(err=>setError(err instanceof Error?err.message:'Unable to load projects')).finally(()=>setLoading(false))}
  useEffect(load,[])

  const [searchParams] = useSearchParams()
  useEffect(() => {
    const requested = Number(searchParams.get('project'))
    if (Number.isInteger(requested) && requested > 0) { setSelectedId(requested); setEditing(null) }
  }, [searchParams])

  useEffect(() => {
    if (!notice) return
    const handle = window.setTimeout(() => setNotice(''), 6000)
    return () => window.clearTimeout(handle)
  }, [notice])
  const rows=useMemo(()=>filterProjects(data?.projects??[],query,financeFilter,operationalFilter),[data,query,financeFilter,operationalFilter])
  const bdTotalPages=Math.max(1,Math.ceil(rows.length/BD_PAGE_SIZE))
  const bdCurrentPage=Math.min(bdPage,bdTotalPages)
  const bdVisibleRows=rows.slice((bdCurrentPage-1)*BD_PAGE_SIZE,bdCurrentPage*BD_PAGE_SIZE)
  useEffect(()=>{setBdPage(page=>Math.min(page,bdTotalPages))},[bdTotalPages])
  const selected=data?.projects.find(row=>row.id===selectedId)??null
  function startEdit(row:Project){
    setSelectedId(row.id);setDocs([]);setRev1(null);setCommercial({...emptyCommercialForm(),scope_description:row.scope_text||'',currency_code:row.currency||'INR',estimated_amount:row.commercial_value==null?'':String(row.commercial_value),po_wo_reference:row.po_wo_number||''})
    setEditing({client_id:row.client_id,project_code:row.project_code,project_name:row.project_name,start_date:row.start_date||'',end_date:row.end_date||'',scope_text:row.scope_text||'',quantity:row.quantity==null?'':String(row.quantity),quantity_unit:row.quantity_unit||'unit',priority:row.priority||'medium',performing_department_code:row.performing_department_code||'ortho',commercial_value:row.commercial_value==null?'':String(row.commercial_value),currency:row.currency||'INR',po_wo_number:row.po_wo_number||'',description:row.description||'',attachment_references:(row.attachment_references||[]).join('\n')})
    void apiFetch<CommercialEstimate[]>(`/commercial/projects/${row.id}/estimates`).then(rows=>{const first=rows.find(item=>item.revision_no===1)??null;setRev1(first);if(first)setCommercial(commercialFormFromRevision(first))}).catch(()=>undefined)
  }
  async function saveEdit(event:FormEvent){
    event.preventDefault();if(!selected||!editing)return
    const wantsCommercial=commercial.estimated_amount.trim()!==''||commercial.payment_terms.trim()!==''||commercial.scope_description.trim()!==''
    if(wantsCommercial){const problems=commercialFormProblems(commercial);if(problems.length){setError(problems[0]);showFeedback({kind:'error',eyebrow:'Unable To Submit',title:'UNABLE TO SUBMIT',message:'Please correct the following:',issues:problems,firstIssueField:'commercial_estimated_amount'});return}}
    setBusy(true);setError('')
    try{
      const result=await apiFetch<{commercial?:{baseline?:{id:number}|null}}>(`/operations/workflow/bd/projects/${selected.id}`,{method:'PUT',body:JSON.stringify({...editing,quantity:editing.quantity===''?null:Number(editing.quantity),commercial_value:wantsCommercial?Number(commercial.estimated_amount):(editing.commercial_value===''?null:Number(editing.commercial_value)),currency:wantsCommercial?commercial.currency_code:editing.currency,po_wo_number:(wantsCommercial?commercial.po_wo_reference:editing.po_wo_number)||null,description:editing.description||null,attachment_references:editing.attachment_references.split('\n').map(value=>value.trim()).filter(Boolean),...(wantsCommercial?{commercial:commercialFormToPayload(commercial)}:{})})})
      const revisionId=result.commercial?.baseline?.id??rev1?.id
      if(docs.length&&revisionId){const failed=await uploadRevisionDocuments(selected.id,revisionId,docs);if(failed.length){setError(`Saved, but ${failed.length} document(s) could not be uploaded: ${failed.join(', ')}`);setDocs([]);setDocTick(v=>v+1);load();return}}
      setNotice(`${selected.project_code} updated without creating a duplicate project or a second Revision 1.`);setEditing(null);setDocs([]);load()
    }catch(err){setError(err instanceof Error?err.message:'Unable to update project')}finally{setBusy(false)}
  }
  async function submit(row:Project){if(!window.confirm(`Submit ${row.project_code} to Finance?`))return;setBusy(true);setError('');try{await apiFetch(`/operations/workflow/bd/projects/${row.id}/submit-finance`,{method:'POST'});showFeedback({kind:'success',eyebrow:'Submitted',title:'SUBMITTED SUCCESSFULLY',message:`${row.project_code} was submitted to Finance.`,facts:[{label:'Project',value:row.project_code},{label:'Submitted To',value:'Finance'},{label:'Current Status',value:'Ready for PM assignment — Finance review only'}]});load()}catch(err){const message=err instanceof Error?err.message:'Unable to submit project';setError(message);showFeedback({kind:'error',eyebrow:'Unable To Submit',title:'UNABLE TO SUBMIT',message})}finally{setBusy(false)}}
  async function assignPm(row:Project){const value=pmChoice[row.id]??(row.project_manager_id?String(row.project_manager_id):'');if(!value){setError('Select exactly one Project Manager for this project\'s Performing Department.');return}setBusy(true);setError('');try{await apiFetch(`/operations/workflow/bd/projects/${row.id}/assign-pm`,{method:'POST',body:JSON.stringify({project_manager_id:Number(value)})});setNotice(`${row.project_code}: Project Manager assigned.`);load()}catch(err){setError(err instanceof Error?err.message:'Unable to assign Project Manager')}finally{setBusy(false)}}

  async function saveDepartmentChange(event:FormEvent){
    event.preventDefault()
    if(!departmentEdit||busy)return
    if(!departmentEdit.department||!departmentEdit.manager||departmentEdit.reason.trim().length<5){setError('Select a new department, its manager, and enter a reason.');return}
    const row=data?.projects.find(p=>p.id===departmentEdit.projectId)
    if(!row||!window.confirm(`Change ${row.project_code} from ${row.performing_department_label} to ${departmentEdit.department}? The previous manager will lose this project assignment.`))return
    setBusy(true);setError('')
    try{
      await apiFetch(`/operations/bd/projects/${row.id}/change-department`,{method:'POST',body:JSON.stringify({performing_department_code:departmentEdit.department,project_manager_id:Number(departmentEdit.manager),reason:departmentEdit.reason.trim()})})
      setDepartmentEdit(null);setPmChoice(previous=>({...previous,[row.id]:''}))
      setNotice(`${row.project_code}: department and Project Manager changed. Both managers were notified.`)
      load()
    }catch(err){setError(err instanceof Error?err.message:'Unable to change department')}finally{setBusy(false)}
  }

  return <div className="operations-page">
    <DashboardHeader eyebrow="BUSINESS DEVELOPMENT · PORTFOLIO INTELLIGENCE" title="Project Management" description="Review project history, correct returned projects and resubmit the same record, then assign a PM without waiting for Finance approval." details={<>
      <div><span>Projects</span><strong>{data?.projects.length ?? 0}</strong></div>
      <div><span>Legacy Finance Queue</span><strong>{data?.projects.filter(row=>row.workflow_status==='pending_finance_approval').length ?? 0}</strong></div>
      <div><span>Returned</span><strong>{data?.projects.filter(row=>row.workflow_status==='finance_returned').length ?? 0}</strong></div>
      <div><span>Draft</span><strong>{data?.projects.filter(row=>row.workflow_status==='draft').length ?? 0}</strong></div>
    </>} actions={<><Link className="operations-button" to="/bd/tracking">View Project Tracking</Link><button className="operations-button secondary" onClick={load}><RefreshCcw size={16}/> Refresh</button></>} meta={<><span className="nk-meta-chip"><Send size={14}/> Review drafts and submit projects for Finance visibility</span><span className="nk-meta-chip"><UserRoundCheck size={14}/> PM assignment needs no Finance approval</span><span className="nk-meta-chip"><Pencil size={14}/> Draft → Finance → PM → Delivery</span></>}/>
    {notice&&<div className="operations-alert success" aria-live="polite">{notice}</div>}{error&&<div className="operations-alert error" aria-live="polite">{error}<button className="operations-button secondary" onClick={load} style={{marginLeft:'8px'}}><RefreshCw size={14}/> Retry</button></div>}
    {loading&&<section className="operations-panel"><div className="operations-empty"><span className="spinner"/> Loading projects…</div></section>}
    <section className="operations-panel">
      <ProjectRegisterFilters query={query} onQueryChange={value=>{setQuery(value);setBdPage(1)}} financeFilter={financeFilter} onFinanceFilterChange={value=>{setFinanceFilter(value);setBdPage(1)}} operationalFilter={operationalFilter} onOperationalFilterChange={value=>{setOperationalFilter(value);setBdPage(1)}}/>
      <ProjectRegisterTable rows={bdVisibleRows} renderFinanceStatusLabel={bdFinanceDisplayLabel} onDetails={row=>{setSelectedId(row.id);setEditing(null)}}
        renderProjectManager={row=>{if(!['finance_approved','pm_assigned','pending_finance_approval'].includes(row.workflow_status))return null;const candidates=(data?.project_managers_by_department?.[row.performing_department_code||'ortho'])??data?.project_managers??[];return <div className="operations-actions"><select value={pmChoice[row.id]??(row.project_manager_id?String(row.project_manager_id):'')} onChange={e=>setPmChoice({...pmChoice,[row.id]:e.target.value})}><option value="">Select {row.performing_department_label||'Ortho'} PM</option>{candidates.map(pm=><option key={pm.id} value={pm.id}>{pm.employee_id?`${pm.employee_id} · `:''}{pm.full_name}</option>)}</select><button className="operations-button secondary" disabled={busy} onClick={()=>void assignPm(row)}><UserRoundCheck size={14}/>{busy?'Assigning…':'Assign'}</button></div>}}
        renderActions={row=>{const correctable=['draft','finance_returned'].includes(row.workflow_status);const transferable=['finance_approved','pm_assigned','pending_finance_approval'].includes(row.workflow_status.toLowerCase());if(!correctable&&!transferable)return null;return <>{correctable&&<><button className="operations-button secondary" onClick={()=>startEdit(row)}><Pencil size={14}/> Edit</button><button className="operations-button" disabled={busy} onClick={()=>void submit(row)}><Send size={14}/>{busy?'Submitting…':'Submit'}</button></>}{transferable&&<button className="operations-button secondary" type="button" disabled={busy} onClick={()=>{setSelectedId(row.id);setEditing(null);setDepartmentEdit({projectId:row.id,department:'',manager:'',reason:''})}}>Change Department</button>}</>}}/>
      {rows.length > 0 && <nav aria-label="BD project pagination" style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:12,flexWrap:'wrap',marginTop:16}}>
        <span style={{fontSize:13}}>Showing {(bdCurrentPage-1)*BD_PAGE_SIZE+1}-{Math.min(bdCurrentPage*BD_PAGE_SIZE,rows.length)} of {rows.length} projects</span>
        <div style={{display:'flex',alignItems:'center',gap:8,flexWrap:'wrap'}}>
          <button type="button" className="operations-button secondary" disabled={bdCurrentPage===1} onClick={()=>setBdPage(page=>Math.max(1,page-1))}>Previous</button>
          <span aria-live="polite" style={{fontSize:13,whiteSpace:'nowrap'}}>Page {bdCurrentPage} of {bdTotalPages}</span>
          <button type="button" className="operations-button secondary" disabled={bdCurrentPage>=bdTotalPages} onClick={()=>setBdPage(page=>Math.min(bdTotalPages,page+1))}>Next</button>
        </div>
      </nav>}
    </section>

    {selected&&<ProjectDetailsPanel project={selected} financeStatusLabel={bdFinanceDisplayLabel(selected)}/>}
    {selected&&departmentEdit?.projectId===selected.id&&<DepartmentChangeDialog
      title={`Change Department - ${selected.project_code}`}
      description={`Current: ${selected.performing_department_label} / ${selected.project_manager_name||'Unassigned'}. The project ID and commercial details will not change.`}
      busy={busy} error={error} onClose={()=>setDepartmentEdit(null)}>
      <form className="operations-form-grid" style={{display:'grid',gridTemplateColumns:'repeat(auto-fit, minmax(min(100%, 220px), 1fr))',gap:14}} onSubmit={event=>void saveDepartmentChange(event)}>
        <label className="operations-field"><span>New Performing Department *</span><select required value={departmentEdit.department} onChange={e=>setDepartmentEdit({...departmentEdit,department:e.target.value,manager:''})}><option value="">Select a different department</option>{(data?.departments??[{code:'ortho',label:'ORTHO'},{code:'lidar',label:'LiDAR'},{code:'mobile_mapping',label:'Mobile Mapping'},{code:'laser_scanning',label:'Laser Scanning'},{code:'civil',label:'Civil'}]).filter(d=>d.code!==selected.performing_department_code).map(d=><option key={d.code} value={d.code}>{d.label}</option>)}</select></label>
        <label className="operations-field"><span>New Department Manager *</span><select required value={departmentEdit.manager} disabled={!departmentEdit.department} onChange={e=>setDepartmentEdit({...departmentEdit,manager:e.target.value})}><option value="">Select Project Manager</option>{(data?.project_managers_by_department?.[departmentEdit.department]??[]).map(pm=><option key={pm.id} value={pm.id}>{pm.full_name}</option>)}</select></label>
        <label className="operations-field operations-span-2" style={{gridColumn:"1 / -1"}}><span>Reason for Change *</span><textarea required minLength={5} maxLength={1000} value={departmentEdit.reason} onChange={e=>setDepartmentEdit({...departmentEdit,reason:e.target.value})}/></label>
        <div className="operations-actions operations-span-2" style={{gridColumn:"1 / -1",display:"flex",flexWrap:"wrap",gap:8}}><button type="submit" className="operations-button" disabled={busy||!departmentEdit.department||!departmentEdit.manager||departmentEdit.reason.trim().length<5}>Save Department Change</button><button type="button" className="operations-button secondary" onClick={()=>setDepartmentEdit(null)} disabled={busy}>Cancel</button></div>
      </form>
    </DepartmentChangeDialog>}

    {selected?.commercial_summary?.has_commercial&&<section className="operations-panel"><header><div><span className="operations-kicker">COMMERCIAL REVISION 1</span><h2>{selected.commercial_summary.baseline?money(selected.commercial_summary.baseline.estimated_amount,selected.commercial_summary.baseline.currency_code):'—'} · {selected.commercial_summary.baseline?.billing_type_label}</h2><p>Payment terms: {selected.commercial_summary.baseline?.payment_terms||'—'}</p></div>{selected.commercial_summary.baseline?.is_locked?<span className="cw-locked">Baseline locked</span>:<span className="cw-pending">{statusLabel(selected.commercial_summary.baseline?.status||'DRAFT')}</span>}</header><p className="operations-instructions">{selected.commercial_summary.baseline?.is_locked?'Finance approved Revision 1 as the locked baseline. Later scope or value changes are created as commercial revisions on the Commercial Estimates page.':'Revision 1 travels with this project to Finance. It can be corrected here while the project is a Draft or returned by Finance.'}</p></section>}
    {selected&&!selected.commercial_summary?.has_commercial&&['draft','finance_returned'].includes(selected.workflow_status)&&<div className="operations-note">No Commercial &amp; Billing Details (Revision 1) yet. Use Edit to add them — a new project cannot be submitted to Finance without them.</div>}

    {selected&&editing&&<section className="operations-panel"><header><div><span className="operations-kicker">EDIT SAME PROJECT RECORD</span><h2>{selected.project_code}</h2><p>Available only for Draft or Finance Returned projects. Project and commercial corrections stay on the same Project ID and Revision 1.</p></div></header><form className="operations-form-grid" onSubmit={saveEdit}>
      <div className="operations-span-2"><span className="operations-kicker">PROJECT INFORMATION</span></div>
      <label className="operations-field"><span>Project ID *</span><input required value={editing.project_code} onChange={e=>setEditing({...editing,project_code:e.target.value.toUpperCase()})}/></label><label className="operations-field"><span>Project Name *</span><input required value={editing.project_name} onChange={e=>setEditing({...editing,project_name:e.target.value})}/></label>
      <label className="operations-field"><span>Start Date *</span><input required type="date" value={editing.start_date} onChange={e=>setEditing({...editing,start_date:e.target.value})}/></label><label className="operations-field"><span>End Date *</span><input required type="date" min={editing.start_date||undefined} value={editing.end_date} onChange={e=>setEditing({...editing,end_date:e.target.value})}/></label>
      <label className="operations-field operations-span-2"><span>Project Scope *</span><textarea required value={editing.scope_text} onChange={e=>setEditing({...editing,scope_text:e.target.value})}/></label>
      <label className="operations-field operations-span-2"><span>Remarks</span><textarea value={editing.description} onChange={e=>setEditing({...editing,description:e.target.value})}/></label>
      <div className="operations-span-2"><span className="operations-kicker">DELIVERY / DEPARTMENT INFORMATION</span></div>
      <label className="operations-field"><span>Performing Department *</span><select required value={editing.performing_department_code} onChange={e=>setEditing({...editing,performing_department_code:e.target.value})}><option value="ortho">ORTHO</option><option value="lidar">LiDAR</option><option value="mobile_mapping">Mobile Mapping</option><option value="laser_scanning">Laser Scanning</option><option value="civil">Civil</option></select></label>
      <label className="operations-field"><span>Priority</span><select value={editing.priority} onChange={e=>setEditing({...editing,priority:e.target.value})}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="urgent">Urgent</option></select></label><label className="operations-field"><span>Planned quantity</span><input type="number" min="0" step="0.001" value={editing.quantity} onChange={e=>setEditing({...editing,quantity:e.target.value})}/></label><label className="operations-field"><span>Quantity unit</span><input value={editing.quantity_unit} onChange={e=>setEditing({...editing,quantity_unit:e.target.value})}/></label><label className="operations-field"><span>Attachments / References</span><textarea value={editing.attachment_references} onChange={e=>setEditing({...editing,attachment_references:e.target.value})}/></label>
      <div className="operations-span-2"><CommercialDetailsSection form={commercial} onChange={setCommercial} currencies={currencies} disabled={busy}/></div>
      <div className="operations-span-2"><span className="operations-kicker">SUPPORTING DOCUMENTS</span></div>
      {rev1&&<div className="operations-span-2"><StoredDocumentsList projectId={selected.id} revisionId={rev1.id} canDelete={!rev1.is_locked} refreshKey={docTick}/></div>}
      <div className="operations-span-2"><PendingDocumentsPicker docs={docs} onChange={setDocs} disabled={busy}/></div>
      <div className="operations-actions operations-span-2"><button className="operations-button" disabled={busy}>{busy?'Saving…':'Save Corrections'}</button><button type="button" className="operations-button secondary" onClick={()=>setEditing(null)}>Cancel</button></div>
    </form></section>}
  </div>
}
