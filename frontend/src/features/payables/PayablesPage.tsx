import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, CheckCircle2, Download, FilePlus2, ReceiptText, RefreshCw, ShieldCheck, Wallet } from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import { apiFetch, downloadFile } from '../../lib/api'
import './payables.css'

type Role = 'admin' | 'finance' | 'manager' | 'none'
type Approval = { decision: string; comment?: string | null; decided_at?: string | null }
type Payable = {
  id: number; code: string; origin: 'admin' | 'finance'; raised_by_id: number
  bill_name: string; bill_number: string; bill_category: string; vendor_name: string; vendor_gstin: string | null
  bill_date: string; due_date: string; billing_period: string | null; cost_center: string | null
  base_amount: number; gst_rate: number; gst_amount: number; total_amount: number
  paid_amount: number; balance_amount: number; progress: number; priority: string
  remarks: string | null; status: string; approval_version: number
  approvals: Record<string, Approval>
  payments: { id: number; amount: number; date: string; method: string; reference: string }[]
  documents: { id: number; kind: string; filename: string; payment_id: number | null }[]
}
type Current = { role: Role; email: string }
type FormFields = {
  bill_name: string; bill_number: string; bill_category: string; vendor_name: string; vendor_gstin: string
  bill_date: string; due_date: string; billing_period: string; cost_center: string
  base_amount: string; gst_rate: string; priority: string; remarks: string
}
const adminCategories = ['Electricity Bill','Water Bill','Internet / Broadband','Telephone / Mobile','Office Rent','AC Servicing','Electrical Repairs','Plumbing','Housekeeping','Office Repairs / Maintenance','Stationery','IT Equipment Maintenance','Other']
const financeCategories = ['Vendor Payment','Subcontractor Invoice','Software Licence','Cloud / Server Hosting','Professional / CA Fees','Equipment Purchase','Project Expenses','Subscription','Statutory Payment','Other']
const fmt = (n: number) => `₹${Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const labelStatus = (status: string) => ({ draft: 'Draft', pending_approval: 'Pending Management Approval', returned: 'Returned for Correction', approved: 'Approved - Awaiting Payment', partially_paid: 'Partially Paid', paid_closed: 'Paid & Closed' }[status] ?? status)
const today = () => { const d = new Date(); const pad = (v: number) => String(v).padStart(2,'0'); return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}` }
const EMPTY: FormFields = { bill_name:'', bill_number:'', bill_category:'', vendor_name:'', vendor_gstin:'', bill_date:today(), due_date:today(), billing_period:'', cost_center:'', base_amount:'', gst_rate:'0', priority:'normal', remarks:'' }
const toFields = (b: Payable): FormFields => ({ bill_name:b.bill_name, bill_number:b.bill_number, bill_category:b.bill_category, vendor_name:b.vendor_name, vendor_gstin:b.vendor_gstin || '', bill_date:b.bill_date, due_date:b.due_date, billing_period:b.billing_period || '', cost_center:b.cost_center || '', base_amount:String(b.base_amount), gst_rate:String(b.gst_rate), priority:b.priority, remarks:b.remarks || '' })
const payload = (f: FormFields) => ({ ...f, vendor_gstin:f.vendor_gstin || null, billing_period:f.billing_period || null, cost_center:f.cost_center || null, remarks:f.remarks || null, base_amount:f.base_amount, gst_rate:f.gst_rate })
const friendly = (err: unknown) => err instanceof Error ? err.message : 'Unexpected error'

function PaymentProgress({ bill }: { bill: Payable }) {
  const pct = Math.max(0, Math.min(100, bill.progress))
  return <div className="np-progress-card">
    <div className="np-row np-between"><strong>Payment Progress</strong><span className={`np-status np-status-${bill.status}`}>{labelStatus(bill.status)}</span></div>
    <div className="np-row np-between"><strong className="np-amount">{fmt(bill.total_amount)}</strong><strong className="np-pct">{pct}%</strong></div>
    <div className="np-track" role="progressbar" aria-label="Payment progress" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}><div className="np-fill" style={{width:`${pct}%`}} /></div>
    <div className="np-grid np-stats"><div><small>Already paid</small><strong className="np-paid">{fmt(bill.paid_amount)}</strong></div><div><small>Balance remaining</small><strong>{fmt(bill.balance_amount)}</strong></div></div>
  </div>
}

function ApprovalGrid({ bill }: { bill: Payable }) {
  return <div className="np-grid np-two">
    {(['vinod@nakshatech.com','chethan@nakshatech.com'] as const).map(email => {
      const approval = bill.approvals[email]
      return <div className="np-approval" key={email}><strong>{email.startsWith('vinod') ? 'Vinod' : 'Chethan'}</strong><span className={`np-status np-status-${approval?.decision || 'pending'}`}>{(approval?.decision || 'pending').toUpperCase()}</span>{approval?.comment && <small>{approval.comment}</small>}</div>
    })}
  </div>
}

export function PayablesListPage() {
  const { user } = useAuth()
  const [who, setWho] = useState<Current | null>(null)
  const [bills, setBills] = useState<Payable[]>([])
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [tab, setTab] = useState('all')
  const [search, setSearch] = useState('')
  const reload = async () => {
    setBusy(true); setError('')
    try {
      const [self, rows] = await Promise.all([apiFetch<Current>('/payables/me'), apiFetch<Payable[]>('/payables')])
      setWho(self); setBills(rows)
    } catch (e) { setError(friendly(e)) } finally { setBusy(false) }
  }
  useEffect(() => { void reload() }, [])
  const filtered = useMemo(() => bills.filter(b => {
    if (tab === 'admin' && b.origin !== 'admin') return false
    if (tab === 'finance' && b.origin !== 'finance') return false
    if (tab === 'pending' && !['pending_approval','returned'].includes(b.status)) return false
    if (tab === 'payments' && !['approved','partially_paid'].includes(b.status)) return false
    if (tab === 'closed' && b.status !== 'paid_closed') return false
    return `${b.code} ${b.bill_name} ${b.vendor_name} ${b.bill_number}`.toLowerCase().includes(search.toLowerCase())
  }), [bills, tab, search])
  const totalBalance = bills.reduce((n,b) => n + b.balance_amount, 0)
  return <div className="np-page">
    <header className="np-header"><div><span className="np-eyebrow">FINANCE & OPERATIONS</span><h1>Payables</h1><p>Dual management approval, payment evidence, and bill settlement tracking.</p></div><div className="np-header-actions"><button type="button" className="np-button secondary" onClick={() => void reload()}><RefreshCw size={16}/> Refresh</button>{(who?.role === 'admin' || who?.role === 'finance') && <Link className="np-button" to="/payables/new"><FilePlus2 size={16}/> Raise {who?.role === 'admin' ? 'Admin' : 'Finance Team'} Bill</Link>}</div></header>
    {error && <div className="np-error" role="alert">{error}</div>}
    <div className="np-grid np-three">
      <div className="np-kpi"><small>Total Payables</small><strong>{bills.length}</strong></div>
      <div className="np-kpi"><small>Awaiting Approval</small><strong>{bills.filter(b=>b.status === 'pending_approval').length}</strong></div>
      <div className="np-kpi"><small>Outstanding Balance</small><strong>{fmt(totalBalance)}</strong></div>
    </div>
    <div className="np-panel"><div className="np-toolbar"><div className="np-tabs">{[ ['all','All Bills'], ...(who?.role !== 'admin' ? [['admin','Admin Bills'],['finance','Finance Team Bills']] : []), ['pending','Approval Queue'],['payments','Ready to Pay'],['closed','Paid & Closed'] ].map(([value,label])=><button type="button" key={value} className={tab === value?'active':''} onClick={()=>setTab(value)}>{label}</button>)}</div><input aria-label="Search payables" placeholder="Search bill, vendor or number" value={search} onChange={e=>setSearch(e.target.value)} /></div>
      {busy ? <p>Loading payables...</p> : filtered.length === 0 ? <p className="np-muted">No payables found for this view.</p> : <div className="np-table-wrap"><table className="np-table"><thead><tr><th>Bill / Number</th><th>Type</th><th>Vendor</th><th>Due Date</th><th>Approval</th><th>Payment Progress</th><th>Balance</th><th>Action</th></tr></thead><tbody>{filtered.map(b => <tr key={b.id}><td><strong>{b.bill_name}</strong><small>{b.code} · {b.bill_number}</small></td><td>{b.origin === 'admin'?'Admin Bill':'Finance Team Bill'}</td><td>{b.vendor_name}</td><td>{b.due_date}</td><td><span className={`np-status np-status-${b.status}`}>{labelStatus(b.status)}</span></td><td><div className="np-small-progress"><span style={{width:`${Math.max(0,Math.min(100,b.progress))}%`}}/></div><small>{b.progress}% · {fmt(b.paid_amount)} paid</small></td><td>{fmt(b.balance_amount)}</td><td><Link className="np-button small secondary" to={`/payables/${b.id}`}>Details</Link></td></tr>)}</tbody></table></div>}
    </div>
    <p className="np-muted">Only your authorized bill category and payment documents are displayed.</p>
    {user?.email && <span className="np-sr-only">Signed in: {user.email}</span>}
  </div>
}

export function PayableNewPage() {
  const navigate = useNavigate()
  const [who, setWho] = useState<Current | null>(null)
  const [values, setValues] = useState<FormFields>(EMPTY)
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { void apiFetch<Current>('/payables/me').then(setWho).catch(e=>setError(friendly(e))) }, [])
  const categories = who?.role === 'admin' ? adminCategories : financeCategories
  const total = (Number(values.base_amount) || 0) * (1+(Number(values.gst_rate)||0)/100)
  const change = (field: keyof FormFields, value: string) => setValues(old=>({...old,[field]:value}))
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      if (!file) throw new Error('Select an original bill PDF or image')
      const bill = await apiFetch<Payable>('/payables', { method:'POST', body: JSON.stringify(payload(values)) })
      try {
        const form = new FormData(); form.append('file', file)
        await apiFetch(`/payables/${bill.id}/bill-document`, {method:'POST',body:form})
        await apiFetch(`/payables/${bill.id}/submit`,{method:'POST'})
      } catch(e) { navigate(`/payables/${bill.id}`); return }
      navigate(`/payables/${bill.id}`)
    } catch(e) { setError(friendly(e)) } finally { setBusy(false) }
  }
  return <div className="np-page"><Link to="/payables" className="np-back"><ArrowLeft size={16}/> Back to Payables</Link><header className="np-header"><div><span className="np-eyebrow">NEW PAYABLE</span><h1>Raise {who?.role === 'admin'?'Admin Bill':'Finance Team Bill'}</h1><p>Invoice and GST details are reviewed independently by both managers.</p></div></header>
    {error && <div className="np-error">{error}</div>}
    <form className="np-panel np-form" onSubmit={e=>void submit(e)}>
      <div className="np-grid np-two"><label>Bill Name *<input required maxLength={220} value={values.bill_name} onChange={e=>change('bill_name',e.target.value)} placeholder="Electricity bill - October"/></label><label>Bill Number *<input required value={values.bill_number} onChange={e=>change('bill_number',e.target.value)}/></label>
      <label>Bill Category *<select required value={values.bill_category} onChange={e=>change('bill_category',e.target.value)}><option value="">Select category</option>{categories.map(c=><option key={c}>{c}</option>)}</select></label><label>Vendor / Supplier *<input required value={values.vendor_name} onChange={e=>change('vendor_name',e.target.value)}/></label>
      <label>Vendor GSTIN<input value={values.vendor_gstin} onChange={e=>change('vendor_gstin',e.target.value)} maxLength={15} placeholder="If applicable"/></label><label>Billing Period<input value={values.billing_period} onChange={e=>change('billing_period',e.target.value)} placeholder="October 2026"/></label>
      <label>Bill Date *<input required type="date" value={values.bill_date} onChange={e=>change('bill_date',e.target.value)}/></label><label>Due Date *<input required type="date" value={values.due_date} onChange={e=>change('due_date',e.target.value)}/></label>
      <label>Base Amount (₹) *<input required type="number" min="0.01" step="0.01" value={values.base_amount} onChange={e=>change('base_amount',e.target.value)}/></label><label>GST Rate (%)<select value={values.gst_rate} onChange={e=>change('gst_rate',e.target.value)}>{['0','5','12','18','28'].map(rate=><option key={rate} value={rate}>{rate}%</option>)}</select></label>
      <label>Priority<select value={values.priority} onChange={e=>change('priority',e.target.value)}><option value="normal">Normal</option><option value="urgent">Urgent</option></select></label><label>Project / Cost Centre<input value={values.cost_center} onChange={e=>change('cost_center',e.target.value)}/></label></div>
      <label>Remarks<textarea rows={3} value={values.remarks} onChange={e=>change('remarks',e.target.value)}/></label><label>Original Bill / Invoice (PDF, JPG or PNG; 10 MB max) *<input required type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={e=>setFile(e.target.files?.[0]||null)}/></label>
      <div className="np-summary"><span>Estimated Total (inclusive of GST)</span><strong>{fmt(total)}</strong></div><button className="np-button" type="submit" disabled={busy || !who || !['admin','finance'].includes(who.role)}><ReceiptText size={17}/>{busy?'Submitting...':'Save & Request Both Approvals'}</button>
    </form>
  </div>
}

export function PayableDetailPage() {
  const { id } = useParams()
  const { user } = useAuth()
  const [who, setWho] = useState<Current | null>(null)
  const [bill, setBill] = useState<Payable | null>(null)
  const [editing, setEditing] = useState(false)
  const [fields, setFields] = useState<FormFields>(EMPTY)
  const [extraBill, setExtraBill] = useState<File | null>(null)
  const [comment, setComment] = useState('')
  const [payAmount, setPayAmount] = useState('')
  const [payMethod, setPayMethod] = useState('bank_transfer')
  const [payDate, setPayDate] = useState(today())
  const [reference, setReference] = useState('')
  const [proof, setProof] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const load = async () => {
    try { const [self,b] = await Promise.all([apiFetch<Current>('/payables/me'),apiFetch<Payable>(`/payables/${id}`)]);setWho(self);setBill(b);setFields(toFields(b));setPayAmount(String(b.balance_amount)) }
    catch(e){setError(friendly(e))}
  }
  useEffect(()=>{void load()},[id])
  async function act(action: ()=>Promise<unknown>, message: string) {
    setBusy(true);setError('');setNote('')
    try { await action(); await load();setEditing(false);setNote(message) } catch(e){setError(friendly(e))} finally {setBusy(false)}
  }
  if (!bill) return <div className="np-page"><Link to="/payables" className="np-back">Back to Payables</Link>{error ? <div className="np-error">{error}</div> : <p>Loading bill...</p>}</div>
  const myDecision = who?.role === 'manager' ? bill.approvals[who.email.toLowerCase()]?.decision : null
  const canEdit = bill.paid_amount === 0 && (who?.role === 'finance' && bill.status !== 'paid_closed' || who?.role === 'admin' && bill.raised_by_id === user?.id && ['draft','returned'].includes(bill.status))
  const canSubmit = ['draft','returned'].includes(bill.status) && (who?.role === 'finance' || (who?.role === 'admin' && canEdit))
  const currentCategories = who?.role === 'admin' ? adminCategories : financeCategories
  return <div className="np-page"><Link to="/payables" className="np-back"><ArrowLeft size={16}/> Back to Payables</Link><header className="np-header"><div><span className="np-eyebrow">{bill.code} · {bill.origin === 'admin'?'ADMIN BILL':'FINANCE TEAM BILL'}</span><h1>{bill.bill_name}</h1><p>{bill.vendor_name} · Bill No. {bill.bill_number} · Due {bill.due_date}</p></div><div className="np-header-actions">{canEdit && <button className="np-button secondary" type="button" onClick={()=>setEditing(v=>!v)}>{editing?'Cancel Edit':'Edit Bill'}</button>}<button className="np-button secondary" onClick={()=>void load()}><RefreshCw size={16}/> Refresh</button></div></header>
    {error && <div className="np-error" role="alert">{error}</div>}{note && <div className="np-note">{note}</div>}
    <div className="np-grid np-two"><PaymentProgress bill={bill}/><div className="np-panel"><h2><ShieldCheck size={19}/> Management Approvals · v{bill.approval_version}</h2><ApprovalGrid bill={bill}/><p className="np-muted">Both Vinod and Chethan must approve this version before Finance can pay.</p></div></div>
    {editing && <form className="np-panel np-form" onSubmit={e=>{e.preventDefault();void act(async()=>{
      await apiFetch(`/payables/${id}`,{method:'PUT',body:JSON.stringify(payload(fields))});if(extraBill){const data=new FormData();data.append('file',extraBill);await apiFetch(`/payables/${id}/bill-document`,{method:'POST',body:data})}
    },'Bill updated. Previous management approvals are reset. Submit again to request approvals.')}}><h2>Edit Bill — Reapproval Required</h2><div className="np-grid np-two">{(['bill_name','bill_number','vendor_name','vendor_gstin','billing_period','cost_center'] as const).map(k=><label key={k}>{k.replaceAll('_',' ')}<input value={fields[k]} onChange={e=>setFields(v=>({...v,[k]:e.target.value}))}/></label>)}<label>Category<select value={fields.bill_category} onChange={e=>setFields(v=>({...v,bill_category:e.target.value}))}>{Array.from(new Set([...currentCategories,fields.bill_category])).map(c=><option key={c}>{c}</option>)}</select></label><label>Base Amount<input required type="number" step="0.01" min="0.01" value={fields.base_amount} onChange={e=>setFields(v=>({...v,base_amount:e.target.value}))}/></label><label>GST %<input type="number" min="0" max="28" step="0.01" value={fields.gst_rate} onChange={e=>setFields(v=>({...v,gst_rate:e.target.value}))}/></label><label>Bill Date<input type="date" value={fields.bill_date} onChange={e=>setFields(v=>({...v,bill_date:e.target.value}))}/></label><label>Due Date<input type="date" value={fields.due_date} onChange={e=>setFields(v=>({...v,due_date:e.target.value}))}/></label></div><label>Remarks<textarea value={fields.remarks} onChange={e=>setFields(v=>({...v,remarks:e.target.value}))}/></label><label>Replace / add invoice (optional)<input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={e=>setExtraBill(e.target.files?.[0]||null)}/></label><button disabled={busy} className="np-button" type="submit">Save Changes & Reset Approvals</button></form>}
    {canSubmit && bill.documents.every(d=>d.kind !== 'bill') && <section className="np-panel np-form"><h2>Upload Missing Original Invoice</h2><label>Bill PDF or image<input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={e=>setExtraBill(e.target.files?.[0]||null)}/></label><button className="np-button" disabled={!extraBill || busy} onClick={()=>void act(async()=>{if(!extraBill)throw new Error('Select a bill file');const f=new FormData();f.append('file',extraBill);await apiFetch(`/payables/${id}/bill-document`,{method:'POST',body:f})},'Original invoice uploaded')}>Upload Invoice</button></section>}
    {canSubmit && <section className="np-panel"><h2>Send for Approval</h2><p>Bill must include an invoice. The two managers will receive notification-bell approval requests.</p><button disabled={busy} className="np-button" onClick={()=>void act(()=>apiFetch(`/payables/${id}/submit`,{method:'POST'}),'Approval requests sent to Vinod and Chethan')}>Submit / Resubmit for Dual Approval</button>{bill.status === 'returned' && <p className="np-muted">Correct the bill before resubmitting.</p>}</section>}
    {who?.role === 'manager' && bill.status === 'pending_approval' && myDecision === 'pending' && <section className="np-panel"><h2>My Management Decision</h2><label>Comments / rejection reason<textarea value={comment} onChange={e=>setComment(e.target.value)} placeholder="Reason required for rejection"/></label><div className="np-row"><button disabled={busy} className="np-button" onClick={()=>void act(()=>apiFetch(`/payables/${id}/decision`,{method:'POST',body:JSON.stringify({decision:'approved',comment:comment || null})}),'Approval recorded')}><CheckCircle2 size={16}/> Approve</button><button disabled={busy || !comment.trim()} className="np-button secondary" onClick={()=>void act(()=>apiFetch(`/payables/${id}/decision`,{method:'POST',body:JSON.stringify({decision:'rejected',comment})}),'Bill returned for correction')}>Return for Correction</button></div></section>}
    {who?.role === 'finance' && ['approved','partially_paid'].includes(bill.status) && <form className="np-panel np-form" onSubmit={e=>{e.preventDefault();void act(async()=>{if(!proof)throw new Error('Payment challan is mandatory');const data=new FormData();data.append('amount',payAmount);data.append('payment_date',payDate);data.append('method',payMethod);data.append('reference',reference);data.append('proof',proof);await apiFetch(`/payables/${id}/payments`,{method:'POST',body:data});setReference('');setProof(null)},'Payment recorded and notifications updated')}}><h2><Wallet size={18}/> Record Payment</h2><div className="np-grid np-two"><label>Payment Amount (₹)<input required type="number" min="0.01" max={bill.balance_amount} step="0.01" value={payAmount} onChange={e=>setPayAmount(e.target.value)}/></label><label>Payment Date<input type="date" required max={today()} value={payDate} onChange={e=>setPayDate(e.target.value)}/></label><label>Payment Method<select value={payMethod} onChange={e=>setPayMethod(e.target.value)}><option value="bank_transfer">Bank Transfer</option><option value="upi">UPI</option><option value="cheque">Cheque</option><option value="cash">Cash</option><option value="other">Other</option></select></label><label>Transaction Reference *<input required minLength={3} value={reference} onChange={e=>setReference(e.target.value)}/></label></div><label>Payment Challan / Proof * (PDF, JPG or PNG)<input type="file" required accept=".pdf,.jpg,.jpeg,.png" onChange={e=>setProof(e.target.files?.[0]||null)}/></label><button disabled={busy} className="np-button" type="submit">Record Payment & Upload Challan</button><p className="np-muted">This records a payment; it does not initiate a bank transfer. Payment cannot exceed the outstanding balance.</p></form>}
    <div className="np-grid np-two"><section className="np-panel"><h2>Bill Details</h2><dl className="np-details"><dt>Category</dt><dd>{bill.bill_category}</dd><dt>Bill Date</dt><dd>{bill.bill_date}</dd><dt>Billing Period</dt><dd>{bill.billing_period || '-'}</dd><dt>GST</dt><dd>{bill.gst_rate}% ({fmt(bill.gst_amount)})</dd><dt>Base Amount</dt><dd>{fmt(bill.base_amount)}</dd><dt>Total</dt><dd>{fmt(bill.total_amount)}</dd><dt>Remarks</dt><dd>{bill.remarks || '-'}</dd></dl></section><section className="np-panel"><h2><Download size={18}/> Bills & Challans</h2>{bill.documents.length === 0 ? <p className="np-muted">No documents uploaded yet.</p>:bill.documents.map(doc=><div className="np-doc" key={doc.id}><div><strong>{doc.kind === 'bill'?'Original Bill':'Payment Challan'}</strong><small>{doc.filename}</small></div><button type="button" className="np-button small secondary" onClick={()=>void downloadFile(`/payables/${id}/documents/${doc.id}`, doc.filename).catch(e=>setError(friendly(e)))}><Download size={14}/> Download</button></div>)}<p className="np-muted">Document access follows the same bill permissions as your login.</p></section></div>
    <section className="np-panel"><h2>Installment / Payment History</h2>{bill.payments.length === 0?<p className="np-muted">No payment recorded.</p>:<div className="np-table-wrap"><table className="np-table"><thead><tr><th>Date</th><th>Amount</th><th>Method</th><th>Transaction Reference</th><th>Challan</th></tr></thead><tbody>{bill.payments.map(payment=>{const doc=bill.documents.find(d=>d.payment_id === payment.id);return <tr key={payment.id}><td>{payment.date}</td><td>{fmt(payment.amount)}</td><td>{payment.method.replaceAll('_',' ')}</td><td>{payment.reference}</td><td>{doc?<button type="button" className="np-button small secondary" onClick={()=>void downloadFile(`/payables/${id}/documents/${doc.id}`,doc.filename).catch(e=>setError(friendly(e)))}><Download size={14}/> Download</button>:'—'}</td></tr>})}</tbody></table></div>}</section>
  </div>
}
