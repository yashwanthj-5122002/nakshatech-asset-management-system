import { useEffect, useState } from 'react'
import { CheckCircle2, Inbox, RotateCcw } from 'lucide-react'
import { apiFetch } from '../../../lib/api'

type Client = {id:number;client_code:string;client_name:string}
type Request = {id:number;employee_id:string|null;employee_name:string|null;company_name:string;contact_person:string;contact_email:string|null;contact_phone:string|null;country:string;address:string|null;lead_source:string;service_interest:string|null;remarks:string|null;status:string;manager_note:string|null;registered_client_id:number|null;created_at:string}

/** Read-only on load. Manager alone may register/link the official client. */
export function BDClientRequestsPanel({clients,onApproved}:{clients:Client[];onApproved:()=>void}) {
  const [items,setItems]=useState<Request[]>([])
  const [filter,setFilter]=useState('pending')
  const [selected,setSelected]=useState<number|null>(null)
  const [approvalMode,setApprovalMode]=useState<'new'|'existing'>('new')
  const [clientCode,setClientCode]=useState('')
  const [existingClientId,setExistingClientId]=useState('')
  const [note,setNote]=useState('')
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const [notice,setNotice]=useState('')
  function load(){
    setError('')
    void apiFetch<{items:Request[]}>(`/bd-employee/client-handoff/manager/requests?request_status=${filter}`)
      .then(data=>{setItems(data.items);setSelected(id=>data.items.some(r=>r.id===id)?id:null)})
      .catch(exc=>setError(exc instanceof Error?exc.message:'Unable to load employee client requests'))
  }
  useEffect(()=>{load()},[filter])
  const active=items.find(r=>r.id===selected)
  async function approve(){
    if(!active)return
    if(approvalMode==='new'&&!clientCode.trim()){setError('Enter a new unique Client ID.');return}
    if(approvalMode==='existing'&&!existingClientId){setError('Choose the existing BD client.');return}
    if(!window.confirm(`Approve ${active.company_name} for ${active.employee_id||active.employee_name}?`))return
    setBusy(true);setError('');setNotice('')
    try{
      await apiFetch(`/bd-employee/client-handoff/manager/requests/${active.id}/approve`,{
        method:'POST',body:JSON.stringify({
          client_code:approvalMode==='new'?clientCode.trim().toUpperCase():null,
          existing_client_id:approvalMode==='existing'?Number(existingClientId):null,
          note:note||null,
        }),
      })
      setSelected(null);setClientCode('');setExistingClientId('');setNote('');setNotice('Client approved and attributed to employee.')
      load();onApproved()
    }catch(exc){setError(exc instanceof Error?exc.message:'Unable to approve client')}
    finally{setBusy(false)}
  }
  async function returnForCorrection(){
    if(!active||note.trim().length<3){setError('Enter a reason (minimum 3 characters) before returning.');return}
    if(!window.confirm(`Return ${active.company_name} to the employee for correction?`))return
    setBusy(true);setError('');setNotice('')
    try{
      await apiFetch(`/bd-employee/client-handoff/manager/requests/${active.id}/return`,{
        method:'POST',body:JSON.stringify({note:note.trim()}),
      })
      setSelected(null);setNote('');setNotice('Request returned to employee.');load()
    }catch(exc){setError(exc instanceof Error?exc.message:'Unable to return request')}
    finally{setBusy(false)}
  }
  return <section className="operations-panel" id="bd-client-request-inbox"><header><div><span className="operations-kicker">BD TEAM · CLIENT INTAKE</span><h2>Employee Requests</h2><p>Verify client details and duplicates. Only the BD Manager can register the client and later create projects.</p></div><Inbox size={22}/></header>
    <div className="operations-actions"><label className="operations-field"><span>Request Status</span><select value={filter} onChange={e=>setFilter(e.target.value)}><option value="pending">Pending</option><option value="approved">Approved</option><option value="returned">Returned</option><option value="all">All</option></select></label><button type="button" className="operations-button secondary" onClick={load}><RotateCcw size={15}/> Refresh Requests</button></div>
    {error&&<div className="operations-alert error" role="alert">{error}</div>}
    {notice&&<div className="operations-alert success" role="status">{notice}</div>}
    <div className="operations-table-wrap"><table className="operations-table"><thead><tr><th>Employee</th><th>Company</th><th>Contact</th><th>Source</th><th>Status</th><th>Action</th></tr></thead><tbody>{items.map(row=><tr key={row.id}><td><strong>{row.employee_id||'BD Employee'}</strong><small>{row.employee_name}</small></td><td>{row.company_name}</td><td>{row.contact_person}<small>{row.contact_email||row.contact_phone}</small></td><td>{row.lead_source}</td><td>{row.status}</td><td><button type="button" className="operations-button secondary" onClick={()=>{setSelected(row.id);setApprovalMode('new');setClientCode('');setExistingClientId('');setNote('')}}>Review</button></td></tr>)}{!items.length&&<tr><td colSpan={6}>No requests match this status.</td></tr>}</tbody></table></div>
    {active&&<div className="operations-panel" style={{marginTop:16}}><header><div><span className="operations-kicker">REQUEST #{active.id} · {active.employee_id}</span><h2>{active.company_name}</h2><p>{active.contact_person} · {active.contact_email||'No email'} · {active.contact_phone||'No phone'}</p></div></header>
      <p><strong>Country:</strong> {active.country} <strong>Source:</strong> {active.lead_source}</p><p><strong>Address:</strong> {active.address||'—'} <strong>Services:</strong> {active.service_interest||'—'}</p><p><strong>Notes:</strong> {active.remarks||'—'}</p>
      {active.status==='pending'?<><p className="operations-note">Check the existing Client Register for duplicates. You can create a new official BD Client ID or link an existing BD client. Any linked existing client must not be attributed to another employee.</p>
        <div className="operations-form-grid"><label className="operations-field"><span>Approval Action</span><select value={approvalMode} onChange={e=>setApprovalMode(e.target.value as 'new'|'existing')}><option value="new">Register New BD Client</option><option value="existing">Link Existing BD Client</option></select></label>
        {approvalMode==='new'?<label className="operations-field"><span>New Client ID (manual) *</span><input value={clientCode} onChange={e=>setClientCode(e.target.value)} placeholder="Unique Client ID" maxLength={32}/></label>
        :<label className="operations-field"><span>Existing BD Client *</span><select value={existingClientId} onChange={e=>setExistingClientId(e.target.value)}><option value="">Select an existing client</option>{clients.map(c=><option key={c.id} value={c.id}>{c.client_code} · {c.client_name}</option>)}</select></label>}
        <label className="operations-field operations-span-2"><span>Manager Notes / Return Reason</span><textarea value={note} onChange={e=>setNote(e.target.value)} maxLength={2000}/></label>
        <div className="operations-actions operations-span-2"><button className="operations-button" type="button" disabled={busy} onClick={()=>void approve()}><CheckCircle2 size={16}/> {busy?'Saving…':'Approve & Register'}</button><button type="button" className="operations-button secondary" disabled={busy} onClick={()=>void returnForCorrection()}>Return for Correction</button><button type="button" className="operations-button secondary" onClick={()=>setSelected(null)}>Close</button></div></div></>
        :<div className="operations-note">Reviewed: {active.status}. {active.manager_note||''} {active.registered_client_id?`Client record ID: ${active.registered_client_id}`:''}<button type="button" className="operations-button secondary" onClick={()=>setSelected(null)}>Close</button></div>}
    </div>}
  </section>
}
