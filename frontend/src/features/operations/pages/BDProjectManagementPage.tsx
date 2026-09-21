import { Pencil, RefreshCcw, Send, UserRoundCheck } from 'lucide-react'
import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import { ProjectDetailsPanel, ProjectRegisterFilters, ProjectRegisterTable } from '../components/ProjectRegister'
import { filterProjects } from '../components/register-utils'
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
  submission_count?:number;finance_reviewer_name?:string|null;finance_reviewed_at?:string|null;events?:EventRow[];commercial_summary?:CommercialSummary
}
type Dashboard={projects:Project[];project_managers:PM[]}
type Form={client_id:number;project_code:string;project_name:string;start_date:string;end_date:string;scope_text:string;quantity:string;quantity_unit:string;priority:string;commercial_value:string;currency:string;po_wo_number:string;description:string;attachment_references:string}

export function BDProjectManagementPage(){
  const [data,setData]=useState<Dashboard|null>(null);const [query,setQuery]=useState('');const [financeFilter,setFinanceFilter]=useState('all');const [operationalFilter,setOperationalFilter]=useState('all')
  const [selectedId,setSelectedId]=useState<number|null>(null);const [editing,setEditing]=useState<Form|null>(null);const [pmChoice,setPmChoice]=useState<Record<number,string>>({})
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [notice,setNotice]=useState('')
  const [commercial,setCommercial]=useState<CommercialFormState>(emptyCommercialForm);const [rev1,setRev1]=useState<CommercialEstimate|null>(null);const [docs,setDocs]=useState<PendingDocument[]>([]);const [currencies,setCurrencies]=useState<CurrencyPayload|null>(null);const [docTick,setDocTick]=useState(0)
  useEffect(()=>{void apiFetch<CurrencyPayload>('/commercial/currencies').then(setCurrencies).catch(()=>undefined)},[])
  function load(){setError('');void apiFetch<Dashboard>('/operations/workflow/bd/dashboard').then(setData).catch(err=>setError(err instanceof Error?err.message:'Unable to load projects'))}
  useEffect(load,[])
  const rows=useMemo(()=>filterProjects(data?.projects??[],query,financeFilter,operationalFilter),[data,query,financeFilter,operationalFilter])
  const selected=data?.projects.find(row=>row.id===selectedId)??null
  function startEdit(row:Project){
    setSelectedId(row.id);setDocs([]);setRev1(null);setCommercial({...emptyCommercialForm(),scope_description:row.scope_text||'',currency_code:row.currency||'INR',estimated_amount:row.commercial_value==null?'':String(row.commercial_value),po_wo_reference:row.po_wo_number||''})
    setEditing({client_id:row.client_id,project_code:row.project_code,project_name:row.project_name,start_date:row.start_date||'',end_date:row.end_date||'',scope_text:row.scope_text||'',quantity:row.quantity==null?'':String(row.quantity),quantity_unit:row.quantity_unit||'unit',priority:row.priority||'medium',commercial_value:row.commercial_value==null?'':String(row.commercial_value),currency:row.currency||'INR',po_wo_number:row.po_wo_number||'',description:row.description||'',attachment_references:(row.attachment_references||[]).join('\n')})
    void apiFetch<CommercialEstimate[]>(`/commercial/projects/${row.id}/estimates`).then(rows=>{const first=rows.find(item=>item.revision_no===1)??null;setRev1(first);if(first)setCommercial(commercialFormFromRevision(first))}).catch(()=>undefined)
  }
  async function saveEdit(event:FormEvent){
    event.preventDefault();if(!selected||!editing)return
    const wantsCommercial=commercial.estimated_amount.trim()!==''||commercial.payment_terms.trim()!==''||commercial.scope_description.trim()!==''
    if(wantsCommercial){const problems=commercialFormProblems(commercial);if(problems.length){setError(problems[0]);return}}
    setBusy(true);setError('')
    try{
      const result=await apiFetch<{commercial?:{baseline?:{id:number}|null}}>(`/operations/workflow/bd/projects/${selected.id}`,{method:'PUT',body:JSON.stringify({...editing,quantity:editing.quantity===''?null:Number(editing.quantity),commercial_value:wantsCommercial?Number(commercial.estimated_amount):(editing.commercial_value===''?null:Number(editing.commercial_value)),currency:wantsCommercial?commercial.currency_code:editing.currency,po_wo_number:(wantsCommercial?commercial.po_wo_reference:editing.po_wo_number)||null,description:editing.description||null,attachment_references:editing.attachment_references.split('\n').map(value=>value.trim()).filter(Boolean),...(wantsCommercial?{commercial:commercialFormToPayload(commercial)}:{})})})
      const revisionId=result.commercial?.baseline?.id??rev1?.id
      if(docs.length&&revisionId){const failed=await uploadRevisionDocuments(selected.id,revisionId,docs);if(failed.length){setError(`Saved, but ${failed.length} document(s) could not be uploaded: ${failed.join(', ')}`);setDocs([]);setDocTick(v=>v+1);load();return}}
      setNotice(`${selected.project_code} updated without creating a duplicate project or a second Revision 1.`);setEditing(null);setDocs([]);load()
    }catch(err){setError(err instanceof Error?err.message:'Unable to update project')}finally{setBusy(false)}
  }
  async function submit(row:Project){if(!window.confirm(`Submit ${row.project_code} to Finance?`))return;setBusy(true);setError('');try{await apiFetch(`/operations/workflow/bd/projects/${row.id}/submit-finance`,{method:'POST'});setNotice(`${row.project_code} submitted to Finance.`);load()}catch(err){setError(err instanceof Error?err.message:'Unable to submit project')}finally{setBusy(false)}}
  async function assignPm(row:Project){const value=pmChoice[row.id]??(row.project_manager_id?String(row.project_manager_id):'');if(!value){setError('Select exactly one Ortho Project Manager.');return}setBusy(true);setError('');try{await apiFetch(`/operations/workflow/bd/projects/${row.id}/assign-pm`,{method:'POST',body:JSON.stringify({project_manager_id:Number(value)})});setNotice(`${row.project_code}: Project Manager assigned.`);load()}catch(err){setError(err instanceof Error?err.message:'Unable to assign Project Manager')}finally{setBusy(false)}}

  return <div className="operations-page">
    <DashboardHeader eyebrow="BUSINESS DEVELOPMENT" title="Project Management" description="Search the complete project register, review history, correct returned projects, resubmit the same record, and assign a PM only after Finance approval." actions={<button className="operations-button secondary" onClick={load}><RefreshCcw size={16}/> Refresh</button>}/>
    {notice&&<div className="operations-alert success">{notice}</div>}{error&&<div className="operations-alert error">{error}</div>}
    <section className="operations-panel">
      <ProjectRegisterFilters query={query} onQueryChange={setQuery} financeFilter={financeFilter} onFinanceFilterChange={setFinanceFilter} operationalFilter={operationalFilter} onOperationalFilterChange={setOperationalFilter}/>
      <ProjectRegisterTable rows={rows} onDetails={row=>{setSelectedId(row.id);setEditing(null)}}
        renderProjectManager={row=>{if(!['finance_approved','pm_assigned'].includes(row.workflow_status))return null;return <div className="operations-actions"><select value={pmChoice[row.id]??(row.project_manager_id?String(row.project_manager_id):'')} onChange={e=>setPmChoice({...pmChoice,[row.id]:e.target.value})}><option value="">Select Ortho PM</option>{data?.project_managers.map(pm=><option key={pm.id} value={pm.id}>{pm.employee_id?`${pm.employee_id} · `:''}{pm.full_name}</option>)}</select><button className="operations-button secondary" disabled={busy} onClick={()=>void assignPm(row)}><UserRoundCheck size={14}/> Assign</button></div>}}
        renderActions={row=>{if(!['draft','finance_returned'].includes(row.workflow_status))return null;return <><button className="operations-button secondary" onClick={()=>startEdit(row)}><Pencil size={14}/> Edit</button><button className="operations-button" disabled={busy} onClick={()=>void submit(row)}><Send size={14}/> Submit</button></>}}/>
    </section>

    {selected&&<ProjectDetailsPanel project={selected}/>}
    {selected?.commercial_summary?.has_commercial&&<section className="operations-panel"><header><div><span className="operations-kicker">COMMERCIAL REVISION 1</span><h2>{selected.commercial_summary.baseline?money(selected.commercial_summary.baseline.estimated_amount,selected.commercial_summary.baseline.currency_code):'—'} · {selected.commercial_summary.baseline?.billing_type_label}</h2><p>Payment terms: {selected.commercial_summary.baseline?.payment_terms||'—'}</p></div>{selected.commercial_summary.baseline?.is_locked?<span className="cw-locked">Baseline locked</span>:<span className="cw-pending">{statusLabel(selected.commercial_summary.baseline?.status||'DRAFT')}</span>}</header><p className="operations-instructions">{selected.commercial_summary.baseline?.is_locked?'Finance approved Revision 1 as the locked baseline. Later scope or value changes are created as commercial revisions on the Commercial Estimates page.':'Revision 1 travels with this project to Finance. It can be corrected here while the project is a Draft or returned by Finance.'}</p></section>}
    {selected&&!selected.commercial_summary?.has_commercial&&['draft','finance_returned'].includes(selected.workflow_status)&&<div className="operations-note">No Commercial &amp; Billing Details (Revision 1) yet. Use Edit to add them — a new project cannot be submitted to Finance without them.</div>}

    {selected&&editing&&<section className="operations-panel"><header><div><span className="operations-kicker">EDIT SAME PROJECT RECORD</span><h2>{selected.project_code}</h2><p>Available only for Draft or Finance Returned projects. Project and commercial corrections stay on the same Project ID and Revision 1.</p></div></header><form className="operations-form-grid" onSubmit={saveEdit}>
      <div className="operations-span-2"><span className="operations-kicker">PROJECT INFORMATION</span></div>
      <label className="operations-field"><span>Project ID *</span><input required value={editing.project_code} onChange={e=>setEditing({...editing,project_code:e.target.value.toUpperCase()})}/></label><label className="operations-field"><span>Project Name *</span><input required value={editing.project_name} onChange={e=>setEditing({...editing,project_name:e.target.value})}/></label>
      <label className="operations-field"><span>Start Date *</span><input required type="date" value={editing.start_date} onChange={e=>setEditing({...editing,start_date:e.target.value})}/></label><label className="operations-field"><span>End Date *</span><input required type="date" min={editing.start_date||undefined} value={editing.end_date} onChange={e=>setEditing({...editing,end_date:e.target.value})}/></label>
      <label className="operations-field operations-span-2"><span>Project Scope *</span><textarea required value={editing.scope_text} onChange={e=>setEditing({...editing,scope_text:e.target.value})}/></label>
      <label className="operations-field operations-span-2"><span>Remarks</span><textarea value={editing.description} onChange={e=>setEditing({...editing,description:e.target.value})}/></label>
      <div className="operations-span-2"><span className="operations-kicker">DELIVERY / DEPARTMENT INFORMATION</span></div>
      <label className="operations-field"><span>Priority</span><select value={editing.priority} onChange={e=>setEditing({...editing,priority:e.target.value})}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="urgent">Urgent</option></select></label><label className="operations-field"><span>Planned quantity</span><input type="number" min="0" step="0.001" value={editing.quantity} onChange={e=>setEditing({...editing,quantity:e.target.value})}/></label><label className="operations-field"><span>Quantity unit</span><input value={editing.quantity_unit} onChange={e=>setEditing({...editing,quantity_unit:e.target.value})}/></label><label className="operations-field"><span>Attachments / References</span><textarea value={editing.attachment_references} onChange={e=>setEditing({...editing,attachment_references:e.target.value})}/></label>
      <div className="operations-span-2"><CommercialDetailsSection form={commercial} onChange={setCommercial} currencies={currencies} disabled={busy}/></div>
      <div className="operations-span-2"><span className="operations-kicker">SUPPORTING DOCUMENTS</span></div>
      {rev1&&<div className="operations-span-2"><StoredDocumentsList projectId={selected.id} revisionId={rev1.id} canDelete={!rev1.is_locked} refreshKey={docTick}/></div>}
      <div className="operations-span-2"><PendingDocumentsPicker docs={docs} onChange={setDocs} disabled={busy}/></div>
      <div className="operations-actions operations-span-2"><button className="operations-button" disabled={busy}>Save Corrections</button><button type="button" className="operations-button secondary" onClick={()=>setEditing(null)}>Cancel</button></div>
    </form></section>}
  </div>
}
