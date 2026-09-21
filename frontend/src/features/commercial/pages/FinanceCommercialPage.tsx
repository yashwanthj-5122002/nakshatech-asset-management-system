import { BadgeIndianRupee, RefreshCcw, Scale, WalletCards } from 'lucide-react'
import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import type { FinanceProject } from '../../../types'
import type { CommercialEstimate, CurrencyPayload, ProjectCostSummary, ProjectExpenseRow, VendorInvoiceRow } from '../types'
import { money, statusLabel, statusTone } from '../types'
import '../commercial.css'

type VendorForm = {
  vendor_name:string; vendor_gstin:string; invoice_number:string; invoice_date:string; due_date:string; po_wo_reference:string; category:string; description:string;
  currency_code:string; taxable_amount:string; cgst:string; sgst:string; igst:string; other_tax:string; payment_source:'COMPANY_PAID'|'EMPLOYEE_PAID'; linked_employee_expense_id:string;
  remarks:string; fx_rate_to_inr:string; fx_rate_mode:string; fx_override_reason:string
}
type VendorPaymentForm = { payment_date:string; amount:string; payment_reference:string; payment_mode:string; fx_rate_to_inr:string; fx_rate_mode:string; fx_override_reason:string }
const today = () => new Date().toISOString().slice(0,10)
const blankVendor = ():VendorForm => ({vendor_name:'',vendor_gstin:'',invoice_number:'',invoice_date:today(),due_date:'',po_wo_reference:'',category:'Subcontractor',description:'',currency_code:'INR',taxable_amount:'',cgst:'0',sgst:'0',igst:'0',other_tax:'0',payment_source:'COMPANY_PAID',linked_employee_expense_id:'',remarks:'',fx_rate_to_inr:'',fx_rate_mode:'MANUAL_OVERRIDE',fx_override_reason:''})
const blankPayment = ():VendorPaymentForm => ({payment_date:today(),amount:'',payment_reference:'',payment_mode:'bank_transfer',fx_rate_to_inr:'',fx_rate_mode:'BANK_REALIZATION_RATE',fx_override_reason:''})

export function FinanceCommercialPage(){
  const [projects,setProjects]=useState<FinanceProject[]>([])
  const [currencies,setCurrencies]=useState<CurrencyPayload|null>(null)
  const [selectedId,setSelectedId]=useState<number|null>(null)
  const [estimateQueue,setEstimateQueue]=useState<CommercialEstimate[]>([])
  const [expenses,setExpenses]=useState<ProjectExpenseRow[]>([])
  const [vendors,setVendors]=useState<VendorInvoiceRow[]>([])
  const [summary,setSummary]=useState<ProjectCostSummary|null>(null)
  const [vendorForm,setVendorForm]=useState<VendorForm>(blankVendor)
  const [vendorFile,setVendorFile]=useState<File|null>(null)
  const [payments,setPayments]=useState<Record<number,VendorPaymentForm>>({})
  const [search,setSearch]=useState('')
  const [busy,setBusy]=useState('')
  const [error,setError]=useState('')
  const [notice,setNotice]=useState('')

  async function loadBase(){
    setError('')
    try{
      const [projectRows,refs,queue,expenseRows]=await Promise.all([
        apiFetch<FinanceProject[]>('/finance/report-projects'), apiFetch<CurrencyPayload>('/commercial/currencies'),
        apiFetch<CommercialEstimate[]>('/commercial/estimates/revisions/queue?status=PENDING_APPROVAL'), apiFetch<ProjectExpenseRow[]>('/commercial/expenses'),
      ])
      setProjects(projectRows);setCurrencies(refs);setEstimateQueue(queue);setExpenses(expenseRows)
      if(!selectedId&&projectRows.length)setSelectedId(projectRows[0].id)
    }catch(err){setError(err instanceof Error?err.message:'Unable to load Finance commercial control')}
  }
  async function loadProject(id:number){
    try{
      const [vendorRows,cost]=await Promise.all([apiFetch<VendorInvoiceRow[]>(`/commercial/vendor-invoices?project_id=${id}`),apiFetch<ProjectCostSummary>(`/commercial/projects/${id}/cost-summary`)])
      setVendors(vendorRows);setSummary(cost)
    }catch(err){setError(err instanceof Error?err.message:'Unable to load project commercial detail')}
  }
  useEffect(()=>{void loadBase()},[])
  useEffect(()=>{if(selectedId)void loadProject(selectedId)},[selectedId])

  const projectMap=useMemo(()=>new Map(projects.map(row=>[row.id,row])),[projects])
  const selected=selectedId?projectMap.get(selectedId)||null:null
  const selectedExpenses=expenses.filter(row=>row.project_id===selectedId)
  const submitted=expenses.filter(row=>row.status==='SUBMITTED')
  const approvedEmployeePaid=expenses.filter(row=>row.status==='APPROVED'&&row.payment_source==='EMPLOYEE_PAID')
  const filteredProjects=projects.filter(row=>!search.trim()||[row.project_code,row.project_name,row.client_code||'',row.client_name||''].some(v=>v.toLowerCase().includes(search.toLowerCase())))

  async function run(key:string,action:()=>Promise<unknown>,message:string){setBusy(key);setError('');setNotice('');try{await action();setNotice(message);await loadBase();if(selectedId)await loadProject(selectedId)}catch(err){setError(err instanceof Error?err.message:'Commercial action failed')}finally{setBusy('')}}

  async function decideEstimate(row:CommercialEstimate,decision:'approve'|'return'|'reject'){
    const comments=window.prompt(`${statusLabel(decision)} R${row.revision_no} for ${projectMap.get(row.project_id)?.project_code||`Project ${row.project_id}`} — enter Finance comments:`,'')
    if(comments===null||!comments.trim())return
    await run(`est-${row.id}`,()=>apiFetch(`/commercial/estimates/revisions/${row.id}/decision`,{method:'POST',body:JSON.stringify({decision,comments})}),`Commercial revision R${row.revision_no} ${decision}d.`)
  }
  async function decideExpense(row:ProjectExpenseRow,decision:'approve'|'return'|'reject'){
    let approved_amount:number|null=null;let adjustment_reason:string|null=null
    if(decision==='approve'){
      const raw=window.prompt(`Approved amount for ${row.expense_code}:`,String(row.amount));if(raw===null)return;approved_amount=Number(raw);if(!Number.isFinite(approved_amount)||approved_amount<0){setError('Enter a valid approved amount.');return}
      if(approved_amount!==row.amount){adjustment_reason=window.prompt('Reason for adjusting the employee amount:','')||'';if(!adjustment_reason.trim()){setError('Adjustment reason is required when approved amount differs.');return}}
    }
    const comments=window.prompt(`Finance comments for ${row.expense_code}:`,'')
    if(comments===null||!comments.trim())return
    await run(`exp-${row.id}`,()=>apiFetch(`/commercial/expenses/${row.id}/finance-decision`,{method:'POST',body:JSON.stringify({decision,approved_amount,comments,adjustment_reason})}),`${row.expense_code} ${decision}d.`)
  }
  async function reimburse(row:ProjectExpenseRow){
    const reference=window.prompt(`Reimbursement reference for ${row.expense_code}:`,'');if(reference===null||!reference.trim())return
    await run(`reim-${row.id}`,()=>apiFetch(`/commercial/expenses/${row.id}/reimburse`,{method:'POST',body:JSON.stringify({reimbursement_reference:reference.trim(),comments:null})}),`${row.expense_code} marked reimbursed.`)
  }

  async function uploadVendorInvoice(projectId:number,vendorId:number,file:File){const body=new FormData();body.append('owner_type','VENDOR_INVOICE');body.append('owner_id',String(vendorId));body.append('doc_type','INVOICE');body.append('file',file);await apiFetch(`/commercial/projects/${projectId}/attachments`,{method:'POST',body})}
  async function createVendor(event:FormEvent){
    event.preventDefault();if(!selectedId)return
    await run('vendor',async()=>{
      const manual=vendorForm.fx_rate_to_inr.trim()?Number(vendorForm.fx_rate_to_inr):null
      const row=await apiFetch<VendorInvoiceRow>(`/commercial/projects/${selectedId}/vendor-invoices`,{method:'POST',body:JSON.stringify({
        vendor_name:vendorForm.vendor_name.trim(),vendor_gstin:vendorForm.vendor_gstin.trim()||null,invoice_number:vendorForm.invoice_number.trim(),invoice_date:vendorForm.invoice_date,due_date:vendorForm.due_date||null,po_wo_reference:vendorForm.po_wo_reference.trim()||null,
        category:vendorForm.category,description:vendorForm.description.trim(),currency_code:vendorForm.currency_code,taxable_amount:Number(vendorForm.taxable_amount),cgst:Number(vendorForm.cgst||0),sgst:Number(vendorForm.sgst||0),igst:Number(vendorForm.igst||0),other_tax:Number(vendorForm.other_tax||0),
        payment_source:vendorForm.payment_source,linked_employee_expense_id:vendorForm.linked_employee_expense_id?Number(vendorForm.linked_employee_expense_id):null,remarks:vendorForm.remarks.trim()||null,fx_rate_to_inr:manual,fx_rate_mode:manual?vendorForm.fx_rate_mode:null,fx_override_reason:manual?vendorForm.fx_override_reason.trim()||null:null,
      })})
      if(vendorFile)await uploadVendorInvoice(selectedId,row.id,vendorFile)
      setVendorForm(blankVendor());setVendorFile(null)
    },'Vendor/subcontractor cost recorded with a locked invoice-date FX snapshot.')
  }
  async function payVendor(row:VendorInvoiceRow){
    const form=payments[row.id]||blankPayment();const manual=form.fx_rate_to_inr.trim()?Number(form.fx_rate_to_inr):null
    if(!form.amount||!form.payment_date){setError('Payment date and amount are required.');return}
    await run(`vp-${row.id}`,()=>apiFetch(`/commercial/vendor-invoices/${row.id}/payments`,{method:'POST',body:JSON.stringify({payment_date:form.payment_date,amount:Number(form.amount),payment_reference:form.payment_reference.trim()||null,payment_mode:form.payment_mode,currency_code:row.currency_code,fx_rate_to_inr:manual,fx_rate_mode:manual?form.fx_rate_mode:null,fx_override_reason:manual?form.fx_override_reason.trim()||null:null})}),`Vendor payment recorded for ${row.invoice_number}.`)
    setPayments(current=>({...current,[row.id]:blankPayment()}))
  }

  return <div className="commercial-page">
    <DashboardHeader eyebrow="FINANCE · COMMERCIAL CONTROL" title="Commercial Approvals & Project Costs" description="Review BD commercial revisions, approve employee project costs, control vendor/subcontractor liabilities, and monitor project margin without replacing the existing expense-claim or billing lifecycle." actions={<button className="commercial-button secondary" onClick={()=>void loadBase()}><RefreshCcw size={15}/> Refresh</button>}/>
    {error&&<div className="commercial-alert error">{error}</div>}{notice&&<div className="commercial-alert success">{notice}</div>}
    <section className="commercial-kpis"><div className="commercial-kpi"><span>Commercial Revisions Pending</span><strong>{estimateQueue.length}</strong></div><div className="commercial-kpi"><span>Employee Costs Pending</span><strong>{submitted.length}</strong></div><div className="commercial-kpi"><span>Reimbursements Due</span><strong>{approvedEmployeePaid.length}</strong></div><div className="commercial-kpi"><span>Selected Project Vendor Bills</span><strong>{vendors.length}</strong></div></section>

    {!!estimateQueue.length&&<section className="commercial-panel"><header><div><span className="commercial-kicker">BD → FINANCE</span><h2>Commercial Revision Approval Queue</h2><p>Approval locks the revision; prior approved history is never overwritten.</p></div><Scale size={22}/></header><div className="commercial-table-wrap"><table className="commercial-table"><thead><tr><th>Project</th><th>Revision</th><th>Commercial</th><th>INR Base</th><th>FX Snapshot</th><th>Reason</th><th>Decision</th></tr></thead><tbody>{estimateQueue.map(row=><tr key={row.id}><td><strong>{projectMap.get(row.project_id)?.project_code||row.project_id}</strong></td><td>R{row.revision_no}</td><td>{money(row.estimated_amount,row.currency_code)}<br/><small>Gross {money(row.expected_gross,row.currency_code)}</small></td><td>{money(row.base_inr)}</td><td>1 {row.currency_code} = ₹{row.fx_rate_to_inr.toLocaleString('en-IN',{maximumFractionDigits:8})}<br/><small>{row.fx_rate_date} · {row.fx_rate_source}</small></td><td>{row.reason||'Initial baseline'}</td><td><div className="commercial-actions"><button className="commercial-button" disabled={busy===`est-${row.id}`} onClick={()=>void decideEstimate(row,'approve')}>Approve</button><button className="commercial-button secondary" onClick={()=>void decideEstimate(row,'return')}>Return</button><button className="commercial-button danger" onClick={()=>void decideEstimate(row,'reject')}>Reject</button></div></td></tr>)}</tbody></table></div></section>}

    {!!submitted.length&&<section className="commercial-panel"><header><div><span className="commercial-kicker">EMPLOYEE → FINANCE</span><h2>Project Cost Approval Queue</h2></div><BadgeIndianRupee size={22}/></header><div className="commercial-table-wrap"><table className="commercial-table"><thead><tr><th>Expense</th><th>Project</th><th>Purpose</th><th>Amount</th><th>Source</th><th>Decision</th></tr></thead><tbody>{submitted.map(row=><tr key={row.id}><td><strong>{row.expense_code}</strong><br/><small>{row.expense_date}</small></td><td>{projectMap.get(row.project_id)?.project_code||row.project_id}</td><td>{row.category}<br/><small>{row.purpose}</small></td><td>{money(row.amount)}</td><td>{statusLabel(row.payment_source)}</td><td><div className="commercial-actions"><button className="commercial-button" disabled={busy===`exp-${row.id}`} onClick={()=>void decideExpense(row,'approve')}>Approve</button><button className="commercial-button secondary" onClick={()=>void decideExpense(row,'return')}>Return</button><button className="commercial-button danger" onClick={()=>void decideExpense(row,'reject')}>Reject</button></div></td></tr>)}</tbody></table></div></section>}

    {!!approvedEmployeePaid.length&&<section className="commercial-panel"><header><div><span className="commercial-kicker">FINANCE LIABILITY</span><h2>Approved Employee Reimbursements</h2></div></header><div className="commercial-table-wrap"><table className="commercial-table"><thead><tr><th>Expense</th><th>Project</th><th>Approved</th><th>Action</th></tr></thead><tbody>{approvedEmployeePaid.map(row=><tr key={row.id}><td>{row.expense_code}</td><td>{projectMap.get(row.project_id)?.project_code||row.project_id}</td><td>{money(row.approved_amount)}</td><td><button className="commercial-button" disabled={busy===`reim-${row.id}`} onClick={()=>void reimburse(row)}>Mark Reimbursed</button></td></tr>)}</tbody></table></div></section>}

    <div className="commercial-grid">
      <aside className="commercial-panel"><header><div><span className="commercial-kicker">PROJECT REGISTER</span><h2>Cost Control</h2></div></header><label className="commercial-field"><span>Search</span><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Project ID / client"/></label><div className="commercial-list" style={{marginTop:12}}>{filteredProjects.map(row=><button key={row.id} type="button" className={`commercial-project-button ${selectedId===row.id?'active':''}`} onClick={()=>setSelectedId(row.id)}><strong>{row.project_code}</strong><span>{row.project_name}</span><span>{row.client_code||row.client_name||'Client not linked'}</span></button>)}</div></aside>
      <main className="commercial-panel">{!selected?<div className="commercial-empty">Select a project.</div>:<><header><div><span className="commercial-kicker">{selected.project_code}</span><h2>Project Cost Snapshot</h2></div><WalletCards size={22}/></header>{summary&&<div className="commercial-kpis"><div className="commercial-kpi"><span>Approved Estimate</span><strong>{money(summary.approved_estimate_base_inr)}</strong></div><div className="commercial-kpi"><span>Billed Net</span><strong>{money(summary.billed_net_revenue_inr)}</strong></div><div className="commercial-kpi"><span>Direct Cost</span><strong>{money(summary.total_direct_cost_inr)}</strong></div><div className="commercial-kpi"><span>Actual Margin</span><strong>{money(summary.actual_margin_inr)}</strong></div></div>}<div className="commercial-note" style={{marginTop:12}}>Employee project cost: {money(summary?.employee_cost_inr)} · Vendor/subcontractor cost: {money(summary?.vendor_cost_inr)} · Realized FX G/L: {money(summary?.fx_gain_loss_inr)}</div></>}</main>
    </div>

    {selected&&<section className="commercial-panel"><header><div><span className="commercial-kicker">VENDOR / SUBCONTRACTOR COST</span><h2>Record Supplier Invoice</h2><p>Foreign-currency invoices capture an immutable invoice-date FX snapshot. Employee-paid supplier bills must link to the corresponding employee cost so the expense is counted once.</p></div></header><form className="commercial-form" onSubmit={createVendor}>
      <label className="commercial-field"><span>Vendor Name *</span><input required value={vendorForm.vendor_name} onChange={e=>setVendorForm({...vendorForm,vendor_name:e.target.value})}/></label><label className="commercial-field"><span>GSTIN</span><input value={vendorForm.vendor_gstin} onChange={e=>setVendorForm({...vendorForm,vendor_gstin:e.target.value})}/></label>
      <label className="commercial-field"><span>Invoice Number *</span><input required value={vendorForm.invoice_number} onChange={e=>setVendorForm({...vendorForm,invoice_number:e.target.value})}/></label><label className="commercial-field"><span>Invoice Date *</span><input required type="date" value={vendorForm.invoice_date} onChange={e=>setVendorForm({...vendorForm,invoice_date:e.target.value})}/></label>
      <label className="commercial-field"><span>Due Date</span><input type="date" value={vendorForm.due_date} onChange={e=>setVendorForm({...vendorForm,due_date:e.target.value})}/></label><label className="commercial-field"><span>PO / WO</span><input value={vendorForm.po_wo_reference} onChange={e=>setVendorForm({...vendorForm,po_wo_reference:e.target.value})}/></label>
      <label className="commercial-field"><span>Category *</span><select value={vendorForm.category} onChange={e=>setVendorForm({...vendorForm,category:e.target.value})}><option>Subcontractor</option><option>Survey Vendor</option><option>Rental</option><option>Material</option><option>Travel Vendor</option><option>Other</option></select></label><label className="commercial-field"><span>Currency *</span><select value={vendorForm.currency_code} onChange={e=>setVendorForm({...vendorForm,currency_code:e.target.value,fx_rate_to_inr:e.target.value==='INR'?'':vendorForm.fx_rate_to_inr})}>{(currencies?.currencies??[{code:'INR',name:'Indian Rupee'}]).map(c=><option key={c.code} value={c.code}>{c.code} · {c.name}</option>)}</select></label>
      <label className="commercial-field commercial-span-2"><span>Description *</span><textarea required value={vendorForm.description} onChange={e=>setVendorForm({...vendorForm,description:e.target.value})}/></label>
      <label className="commercial-field"><span>Taxable Amount *</span><input required type="number" min="0" step="0.01" value={vendorForm.taxable_amount} onChange={e=>setVendorForm({...vendorForm,taxable_amount:e.target.value})}/></label><label className="commercial-field"><span>CGST</span><input type="number" min="0" step="0.01" value={vendorForm.cgst} onChange={e=>setVendorForm({...vendorForm,cgst:e.target.value})}/></label><label className="commercial-field"><span>SGST</span><input type="number" min="0" step="0.01" value={vendorForm.sgst} onChange={e=>setVendorForm({...vendorForm,sgst:e.target.value})}/></label><label className="commercial-field"><span>IGST</span><input type="number" min="0" step="0.01" value={vendorForm.igst} onChange={e=>setVendorForm({...vendorForm,igst:e.target.value})}/></label><label className="commercial-field"><span>Other Tax</span><input type="number" min="0" step="0.01" value={vendorForm.other_tax} onChange={e=>setVendorForm({...vendorForm,other_tax:e.target.value})}/></label>
      <label className="commercial-field"><span>Payment Source</span><select value={vendorForm.payment_source} onChange={e=>setVendorForm({...vendorForm,payment_source:e.target.value as VendorForm['payment_source'],linked_employee_expense_id:e.target.value==='COMPANY_PAID'?'':vendorForm.linked_employee_expense_id})}><option value="COMPANY_PAID">Company pays vendor</option><option value="EMPLOYEE_PAID">Employee already paid vendor</option></select></label>
      {vendorForm.payment_source==='EMPLOYEE_PAID'&&<label className="commercial-field"><span>Linked Employee Expense *</span><select required value={vendorForm.linked_employee_expense_id} onChange={e=>setVendorForm({...vendorForm,linked_employee_expense_id:e.target.value})}><option value="">Select expense</option>{selectedExpenses.filter(row=>row.payment_source==='EMPLOYEE_PAID'&&!row.linked_vendor_invoice_id).map(row=><option key={row.id} value={row.id}>{row.expense_code} · {money(row.amount)}</option>)}</select></label>}
      <label className="commercial-field"><span>Invoice File</span><input type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" onChange={e=>setVendorFile(e.target.files?.[0]||null)}/></label>
      {vendorForm.currency_code!=='INR'&&<div className="commercial-fx commercial-span-2"><label className="commercial-field"><span>Manual FX to INR (optional)</span><input type="number" min="0.00000001" step="0.00000001" value={vendorForm.fx_rate_to_inr} onChange={e=>setVendorForm({...vendorForm,fx_rate_to_inr:e.target.value})}/><small className="commercial-help">Blank = dated automatic reference rate.</small></label><label className="commercial-field"><span>Override Mode</span><select value={vendorForm.fx_rate_mode} onChange={e=>setVendorForm({...vendorForm,fx_rate_mode:e.target.value})}><option value="MANUAL_OVERRIDE">Manual Override</option><option value="CONTRACT_RATE">Contract Rate</option><option value="BANK_REALIZATION_RATE">Bank Rate</option><option value="OTHER">Other</option></select></label><label className="commercial-field"><span>Override Reason</span><input required={Boolean(vendorForm.fx_rate_to_inr)} value={vendorForm.fx_override_reason} onChange={e=>setVendorForm({...vendorForm,fx_override_reason:e.target.value})}/></label></div>}
      <label className="commercial-field commercial-span-2"><span>Remarks</span><textarea value={vendorForm.remarks} onChange={e=>setVendorForm({...vendorForm,remarks:e.target.value})}/></label><div className="commercial-actions commercial-span-2"><button className="commercial-button" disabled={busy==='vendor'}>Record Vendor Invoice</button></div>
    </form></section>}

    {selected&&<section className="commercial-panel"><header><div><span className="commercial-kicker">SUPPLIER LIABILITY REGISTER</span><h2>{selected.project_code} Vendor Costs</h2></div></header>{!vendors.length?<div className="commercial-empty">No vendor/subcontractor invoices recorded.</div>:<div className="commercial-table-wrap"><table className="commercial-table"><thead><tr><th>Vendor / Invoice</th><th>Invoice Value</th><th>INR Cost</th><th>Payment</th><th>Settle</th></tr></thead><tbody>{vendors.map(row=>{const pay=payments[row.id]||blankPayment();return <tr key={row.id}><td><strong>{row.vendor_name}</strong><br/><small>{row.invoice_number} · {row.invoice_date}</small></td><td>{money(row.gross_amount,row.currency_code)}<br/><small>1 {row.currency_code} = ₹{row.fx_rate_to_inr.toLocaleString('en-IN',{maximumFractionDigits:8})}</small></td><td>{money(row.gross_inr)}</td><td><span className={`commercial-status ${statusTone(row.payment_status)}`}>{statusLabel(row.payment_status)}</span><br/><small>Outstanding {money(row.outstanding_amount,row.currency_code)}</small></td><td>{row.payment_source==='EMPLOYEE_PAID'?<small>Settled to vendor by employee; reimburse linked expense.</small>:row.payment_status==='PAID'?<span className="commercial-status success">Paid</span>:<div className="commercial-subpanel"><label className="commercial-field"><span>Payment Date</span><input type="date" value={pay.payment_date} onChange={e=>setPayments({...payments,[row.id]:{...pay,payment_date:e.target.value}})}/></label><label className="commercial-field"><span>Amount ({row.currency_code})</span><input type="number" min="0.01" max={row.outstanding_amount} step="0.01" value={pay.amount} onChange={e=>setPayments({...payments,[row.id]:{...pay,amount:e.target.value}})}/></label><label className="commercial-field"><span>Reference</span><input value={pay.payment_reference} onChange={e=>setPayments({...payments,[row.id]:{...pay,payment_reference:e.target.value}})}/></label>{row.currency_code!=='INR'&&<><label className="commercial-field"><span>Manual realization FX (optional)</span><input type="number" min="0.00000001" step="0.00000001" value={pay.fx_rate_to_inr} onChange={e=>setPayments({...payments,[row.id]:{...pay,fx_rate_to_inr:e.target.value}})}/></label>{pay.fx_rate_to_inr&&<label className="commercial-field"><span>FX reason</span><input value={pay.fx_override_reason} onChange={e=>setPayments({...payments,[row.id]:{...pay,fx_override_reason:e.target.value}})}/></label>}</>}<button className="commercial-button" disabled={busy===`vp-${row.id}`} onClick={()=>void payVendor(row)}>Record Payment</button></div>}</td></tr>})}</tbody></table></div>}</section>}
  </div>
}
