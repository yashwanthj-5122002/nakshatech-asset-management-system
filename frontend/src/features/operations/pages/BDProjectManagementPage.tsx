import { Pencil, RefreshCcw, RefreshCw, Send, UserRoundCheck } from 'lucide-react'
import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import { ProjectDetailsPanel, ProjectRegisterFilters, ProjectRegisterTable } from '../components/ProjectRegister'
import { filterProjects } from '../components/register-utils'
import '../operations.css'

type EventRow={id:number;event_type:string;from_status?:string|null;to_status:string;comments?:string|null;actor_name?:string|null;actor_role?:string|null;created_at:string}
type PM={id:number;full_name:string;email:string;employee_id?:string|null}
type Project={
  id:number;client_id:number;project_code:string;project_name:string;client_code?:string|null;client_name?:string|null;start_date?:string|null;end_date?:string|null;
  description?:string|null;scope_text?:string|null;quantity?:number|null;quantity_unit?:string|null;priority?:string|null;commercial_value?:number|null;currency?:string|null;
  po_wo_number?:string|null;attachment_references?:string[];workflow_status:string;normalized_status?:string;finance_feedback?:string|null;project_manager_id?:number|null;project_manager_name?:string|null;
  submission_count?:number;finance_reviewer_name?:string|null;finance_reviewed_at?:string|null;events?:EventRow[]
}
type Dashboard={projects:Project[];project_managers:PM[]}
type Form={client_id:number;project_code:string;project_name:string;start_date:string;end_date:string;scope_text:string;quantity:string;quantity_unit:string;priority:string;commercial_value:string;currency:string;po_wo_number:string;description:string;attachment_references:string}

export function BDProjectManagementPage(){
  const [data,setData]=useState<Dashboard|null>(null);const [query,setQuery]=useState('');const [financeFilter,setFinanceFilter]=useState('all');const [operationalFilter,setOperationalFilter]=useState('all')
  const [selectedId,setSelectedId]=useState<number|null>(null);const [editing,setEditing]=useState<Form|null>(null);const [pmChoice,setPmChoice]=useState<Record<number,string>>({})
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [notice,setNotice]=useState('');const [loading,setLoading]=useState(true)
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
  const selected=data?.projects.find(row=>row.id===selectedId)??null
  function startEdit(row:Project){setSelectedId(row.id);setEditing({client_id:row.client_id,project_code:row.project_code,project_name:row.project_name,start_date:row.start_date||'',end_date:row.end_date||'',scope_text:row.scope_text||'',quantity:row.quantity==null?'':String(row.quantity),quantity_unit:row.quantity_unit||'unit',priority:row.priority||'medium',commercial_value:row.commercial_value==null?'':String(row.commercial_value),currency:row.currency||'INR',po_wo_number:row.po_wo_number||'',description:row.description||'',attachment_references:(row.attachment_references||[]).join('\n')})}
  async function saveEdit(event:FormEvent){event.preventDefault();if(!selected||!editing)return;setBusy(true);setError('');try{await apiFetch(`/operations/workflow/bd/projects/${selected.id}`,{method:'PUT',body:JSON.stringify({...editing,quantity:editing.quantity===''?null:Number(editing.quantity),commercial_value:editing.commercial_value===''?null:Number(editing.commercial_value),po_wo_number:editing.po_wo_number||null,description:editing.description||null,attachment_references:editing.attachment_references.split('\n').map(value=>value.trim()).filter(Boolean)})});setNotice(`${selected.project_code} updated without creating a duplicate.`);setEditing(null);load()}catch(err){setError(err instanceof Error?err.message:'Unable to update project')}finally{setBusy(false)}}
  async function submit(row:Project){if(!window.confirm(`Submit ${row.project_code} to Finance?`))return;setBusy(true);setError('');try{await apiFetch(`/operations/workflow/bd/projects/${row.id}/submit-finance`,{method:'POST'});setNotice(`${row.project_code} submitted to Finance.`);load()}catch(err){setError(err instanceof Error?err.message:'Unable to submit project')}finally{setBusy(false)}}
  async function assignPm(row:Project){const value=pmChoice[row.id]??(row.project_manager_id?String(row.project_manager_id):'');if(!value){setError('Select exactly one Ortho Project Manager.');return}setBusy(true);setError('');try{await apiFetch(`/operations/workflow/bd/projects/${row.id}/assign-pm`,{method:'POST',body:JSON.stringify({project_manager_id:Number(value)})});setNotice(`${row.project_code}: Project Manager assigned.`);load()}catch(err){setError(err instanceof Error?err.message:'Unable to assign Project Manager')}finally{setBusy(false)}}

  return <div className="operations-page">
    <DashboardHeader eyebrow="PROJECT REGISTER" title="Project Management" description="Review history, correct returned projects, resubmit the same record, and assign a PM only after Finance approval." details={<>
      <div><span>Projects</span><strong>{data?.projects.length ?? 0}</strong></div>
      <div><span>Awaiting Finance</span><strong>{data?.projects.filter(row=>row.workflow_status==='pending_finance_approval').length ?? 0}</strong></div>
      <div><span>Returned</span><strong>{data?.projects.filter(row=>row.workflow_status==='finance_returned').length ?? 0}</strong></div>
      <div><span>Draft</span><strong>{data?.projects.filter(row=>row.workflow_status==='draft').length ?? 0}</strong></div>
    </>} actions={<button className="operations-button secondary" onClick={load}><RefreshCcw size={16}/> Refresh</button>}/>
    {notice&&<div className="operations-alert success" aria-live="polite">{notice}</div>}{error&&<div className="operations-alert error" aria-live="polite">{error}<button className="operations-button secondary" onClick={load} style={{marginLeft:'8px'}}><RefreshCw size={14}/> Retry</button></div>}
    {loading&&<section className="operations-panel"><div className="operations-empty"><span className="spinner"/> Loading projects…</div></section>}
    <section className="operations-panel">
      <ProjectRegisterFilters query={query} onQueryChange={setQuery} financeFilter={financeFilter} onFinanceFilterChange={setFinanceFilter} operationalFilter={operationalFilter} onOperationalFilterChange={setOperationalFilter}/>
      <ProjectRegisterTable rows={rows} onDetails={row=>{setSelectedId(row.id);setEditing(null)}}
        renderProjectManager={row=>{if(!['finance_approved','pm_assigned'].includes(row.workflow_status))return null;return <div className="operations-actions"><select value={pmChoice[row.id]??(row.project_manager_id?String(row.project_manager_id):'')} onChange={e=>setPmChoice({...pmChoice,[row.id]:e.target.value})}><option value="">Select Ortho PM</option>{data?.project_managers.map(pm=><option key={pm.id} value={pm.id}>{pm.employee_id?`${pm.employee_id} · `:''}{pm.full_name}</option>)}</select><button className="operations-button secondary" disabled={busy} onClick={()=>void assignPm(row)}><UserRoundCheck size={14}/>{busy?'Assigning…':'Assign'}</button></div>}}
        renderActions={row=>{if(!['draft','finance_returned'].includes(row.workflow_status))return null;return <><button className="operations-button secondary" onClick={()=>startEdit(row)}><Pencil size={14}/> Edit</button><button className="operations-button" disabled={busy} onClick={()=>void submit(row)}><Send size={14}/>{busy?'Submitting…':'Submit'}</button></>}}/>
    </section>

    {selected&&<ProjectDetailsPanel project={selected}/>}

    {selected&&editing&&<section className="operations-panel"><header><div><span className="operations-kicker">EDIT SAME PROJECT RECORD</span><h2>{selected.project_code}</h2><p>Available only for Draft or Finance Returned projects.</p></div></header><form className="operations-form-grid" onSubmit={saveEdit}>
      <label className="operations-field"><span>Project ID *</span><input required value={editing.project_code} onChange={e=>setEditing({...editing,project_code:e.target.value.toUpperCase()})}/></label><label className="operations-field"><span>Project Name *</span><input required value={editing.project_name} onChange={e=>setEditing({...editing,project_name:e.target.value})}/></label>
      <label className="operations-field"><span>Start Date *</span><input required type="date" value={editing.start_date} onChange={e=>setEditing({...editing,start_date:e.target.value})}/></label><label className="operations-field"><span>End Date *</span><input required type="date" min={editing.start_date||undefined} value={editing.end_date} onChange={e=>setEditing({...editing,end_date:e.target.value})}/></label>
      <label className="operations-field operations-span-2"><span>Project Scope *</span><textarea required value={editing.scope_text} onChange={e=>setEditing({...editing,scope_text:e.target.value})}/></label><label className="operations-field"><span>Project Value</span><input type="number" min="0" value={editing.commercial_value} onChange={e=>setEditing({...editing,commercial_value:e.target.value})}/></label><label className="operations-field"><span>Currency</span><input value={editing.currency} onChange={e=>setEditing({...editing,currency:e.target.value})}/></label><label className="operations-field"><span>PO / WO</span><input value={editing.po_wo_number} onChange={e=>setEditing({...editing,po_wo_number:e.target.value})}/></label><label className="operations-field"><span>Attachments / References</span><textarea value={editing.attachment_references} onChange={e=>setEditing({...editing,attachment_references:e.target.value})}/></label><label className="operations-field operations-span-2"><span>Remarks</span><textarea value={editing.description} onChange={e=>setEditing({...editing,description:e.target.value})}/></label><div className="operations-actions operations-span-2"><button className="operations-button" disabled={busy}>{busy?'Saving…':'Save Corrections'}</button><button type="button" className="operations-button secondary" onClick={()=>setEditing(null)}>Cancel</button></div>
    </form></section>}
  </div>
}
