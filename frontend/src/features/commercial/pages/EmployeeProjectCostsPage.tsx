import { FilePlus2, RefreshCcw, Send, ShieldCheck } from 'lucide-react'
import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import type { FinanceProject } from '../../../types'
import type { ProjectExpenseRow } from '../types'
import { money, statusLabel, statusTone } from '../types'
import '../commercial.css'

type ExpenseForm = {
  expense_date: string
  category: string
  purpose: string
  amount: string
  payment_source: 'EMPLOYEE_PAID' | 'COMPANY_PAID'
  remarks: string
  phase_key: string
}

const today = () => new Date().toISOString().slice(0, 10)
const blank = (): ExpenseForm => ({ expense_date: today(), category: 'Travel', purpose: '', amount: '', payment_source: 'EMPLOYEE_PAID', remarks: '', phase_key: 'ORIGINAL' })

export function EmployeeProjectCostsPage() {
  const [projects, setProjects] = useState<FinanceProject[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [expenses, setExpenses] = useState<ProjectExpenseRow[]>([])
  const [form, setForm] = useState<ExpenseForm>(blank)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [receipt, setReceipt] = useState<File | null>(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  function loadProjects() {
    setError('')
    void apiFetch<FinanceProject[]>('/finance/projects').then(rows => {
      setProjects(rows)
      if (!selectedId && rows.length) setSelectedId(rows[0].id)
    }).catch(err => setError(err instanceof Error ? err.message : 'Unable to load assigned projects'))
  }

  function loadExpenses(projectId: number) {
    setError('')
    void apiFetch<ProjectExpenseRow[]>(`/commercial/expenses?project_id=${projectId}`)
      .then(setExpenses)
      .catch(err => setError(err instanceof Error ? err.message : 'Unable to load project costs'))
  }

  useEffect(loadProjects, [])
  useEffect(() => { if (selectedId) loadExpenses(selectedId) }, [selectedId])

  const selected = useMemo(() => projects.find(row => row.id === selectedId) ?? null, [projects, selectedId])

  async function uploadReceipt(projectId: number, expenseId: number, file: File) {
    const body = new FormData()
    body.append('owner_type', 'EXPENSE')
    body.append('owner_id', String(expenseId))
    body.append('doc_type', 'RECEIPT')
    body.append('file', file)
    await apiFetch(`/commercial/projects/${projectId}/attachments`, { method: 'POST', body })
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!selectedId) return
    setBusy('save'); setError(''); setNotice('')
    try {
      const payload = {
        expense_date: form.expense_date,
        category: form.category,
        purpose: form.purpose.trim(),
        amount: Number(form.amount),
        payment_source: form.payment_source,
        remarks: form.remarks.trim() || null,
        phase_key: form.phase_key,
        linked_vendor_invoice_id: null,
      }
      const row = editingId
        ? await apiFetch<ProjectExpenseRow>(`/commercial/expenses/${editingId}`, { method: 'PUT', body: JSON.stringify(payload) })
        : await apiFetch<ProjectExpenseRow>(`/commercial/projects/${selectedId}/expenses`, { method: 'POST', body: JSON.stringify(payload) })
      if (receipt) await uploadReceipt(selectedId, row.id, receipt)
      setForm(blank()); setEditingId(null); setReceipt(null)
      setNotice(`Project cost ${row.expense_code} saved as Draft${receipt ? ' with receipt' : ''}.`)
      loadExpenses(selectedId)
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to save project cost') }
    finally { setBusy('') }
  }

  function edit(row: ProjectExpenseRow) {
    setEditingId(row.id)
    setForm({ expense_date: row.expense_date, category: row.category, purpose: row.purpose, amount: String(row.amount), payment_source: row.payment_source, remarks: row.remarks || '', phase_key: row.phase_key })
    setReceipt(null)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function submit(row: ProjectExpenseRow) {
    if (!selectedId) return
    setBusy(`submit-${row.id}`); setError(''); setNotice('')
    try {
      await apiFetch(`/commercial/expenses/${row.id}/submit`, { method: 'POST' })
      setNotice(`${row.expense_code} submitted to Finance.`)
      loadExpenses(selectedId)
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to submit expense') }
    finally { setBusy('') }
  }

  async function declareNoMore() {
    if (!selectedId) return
    if (!window.confirm('Declare that you have no more project expenses for this project phase? Creating a later expense will automatically reset this declaration.')) return
    setBusy('declare'); setError(''); setNotice('')
    try {
      await apiFetch(`/commercial/projects/${selectedId}/expenses/declaration`, { method: 'POST', body: JSON.stringify({ phase_key: 'ORIGINAL', declaration_status: 'NO_MORE_EXPENSES' }) })
      setNotice('No More Project Expenses declaration recorded for the selected Project ID.')
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to record declaration') }
    finally { setBusy('') }
  }

  return <div className="commercial-page">
    <DashboardHeader eyebrow="EMPLOYEE · PROJECT COSTS" title="Project Cost Entries" description="Record project-specific out-of-pocket or company-paid costs against only the Project IDs assigned to you. These entries are separate from the existing advance/reimbursement claim workflow." actions={<button className="commercial-button secondary" onClick={loadProjects}><RefreshCcw size={15}/> Refresh</button>}/>
    {error && <div className="commercial-alert error">{error}</div>}
    {notice && <div className="commercial-alert success">{notice}</div>}

    <div className="commercial-grid">
      <aside className="commercial-panel">
        <header><div><span className="commercial-kicker">ASSIGNED PROJECT IDs</span><h2>My Projects</h2></div></header>
        <div className="commercial-list">{projects.map(row => <button key={row.id} type="button" className={`commercial-project-button ${selectedId === row.id ? 'active' : ''}`} onClick={() => { setSelectedId(row.id); setEditingId(null); setForm(blank()) }}><strong>{row.project_code}</strong><span>{row.client_code || 'Client ID not recorded'}</span><span>{statusLabel(row.lifecycle_status || row.project_status)}</span></button>)}</div>
        {!projects.length && <div className="commercial-empty">No Project IDs are currently assigned to you.</div>}
      </aside>

      <main className="commercial-panel">
        {!selected ? <div className="commercial-empty">Select an assigned Project ID.</div> : <>
          <header><div><span className="commercial-kicker">{selected.project_code}</span><h2>{editingId ? 'Edit Returned / Draft Cost' : 'New Project Cost'}</h2><p>All employee project-cost entries are INR-only. Foreign-currency supplier bills belong in Finance Vendor Costs.</p></div><FilePlus2 size={22}/></header>
          {!selected.expense_allowed && selected.expense_block_reason && <div className="commercial-alert error">{selected.expense_block_reason}</div>}
          <form className="commercial-form" onSubmit={save}>
            <label className="commercial-field"><span>Expense Date *</span><input required type="date" value={form.expense_date} onChange={e => setForm({...form, expense_date:e.target.value})}/></label>
            <label className="commercial-field"><span>Category *</span><select value={form.category} onChange={e => setForm({...form, category:e.target.value})}><option>Travel</option><option>Accommodation</option><option>Food</option><option>Local Conveyance</option><option>Survey / Field Material</option><option>Printing</option><option>Rental</option><option>Other</option></select></label>
            <label className="commercial-field commercial-span-2"><span>Purpose / business justification *</span><textarea required value={form.purpose} onChange={e => setForm({...form, purpose:e.target.value})}/></label>
            <label className="commercial-field"><span>Amount (INR) *</span><input required type="number" min="0.01" step="0.01" value={form.amount} onChange={e => setForm({...form, amount:e.target.value})}/></label>
            <label className="commercial-field"><span>Payment Source</span><select value={form.payment_source} onChange={e => setForm({...form, payment_source:e.target.value as ExpenseForm['payment_source']})}><option value="EMPLOYEE_PAID">Paid by Employee · reimbursement due</option><option value="COMPANY_PAID">Paid directly by Company</option></select></label>
            <label className="commercial-field"><span>Receipt / proof</span><input type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" onChange={e => setReceipt(e.target.files?.[0] || null)}/><small className="commercial-help">PDF/JPG/PNG/WebP, max 15 MB.</small></label>
            <label className="commercial-field"><span>Phase</span><select value={form.phase_key} onChange={e => setForm({...form, phase_key:e.target.value})}><option value="ORIGINAL">Original Delivery</option><option value="REWORK">Rework</option></select></label>
            <label className="commercial-field commercial-span-2"><span>Remarks</span><textarea value={form.remarks} onChange={e => setForm({...form, remarks:e.target.value})}/></label>
            <div className="commercial-actions commercial-span-2"><button className="commercial-button" disabled={busy === 'save' || !selected.expense_allowed}>{editingId ? 'Save Changes' : 'Save Draft'}</button>{editingId && <button type="button" className="commercial-button secondary" onClick={() => { setEditingId(null); setForm(blank()); setReceipt(null) }}>Cancel Edit</button>}<button type="button" className="commercial-button secondary" disabled={busy === 'declare'} onClick={() => void declareNoMore()}><ShieldCheck size={15}/> No More Expenses</button></div>
          </form>
        </>}
      </main>
    </div>

    {selected && <section className="commercial-panel"><header><div><span className="commercial-kicker">MY COST HISTORY</span><h2>{selected.project_code}</h2><p>Finance adjustments and reimbursement references stay visible here for auditability.</p></div></header>{!expenses.length ? <div className="commercial-empty">No project-specific costs recorded yet.</div> : <div className="commercial-table-wrap"><table className="commercial-table"><thead><tr><th>Expense</th><th>Date / Category</th><th>Requested</th><th>Finance</th><th>Status</th><th>Action</th></tr></thead><tbody>{expenses.map(row => <tr key={row.id}><td><strong>{row.expense_code}</strong><br/><small>{row.purpose}</small></td><td>{row.expense_date}<br/><small>{row.category} · {statusLabel(row.payment_source)}</small></td><td>{money(row.amount)}</td><td>{row.approved_amount == null ? '—' : money(row.approved_amount)}<br/><small>{row.finance_comments || row.adjustment_reason || row.reimbursement_reference || '—'}</small></td><td><span className={`commercial-status ${statusTone(row.status)}`}>{statusLabel(row.status)}</span></td><td><div className="commercial-actions">{['DRAFT','RETURNED'].includes(row.status) && <button className="commercial-button secondary" onClick={() => edit(row)}>Edit</button>}{['DRAFT','RETURNED'].includes(row.status) && <button className="commercial-button" disabled={busy === `submit-${row.id}`} onClick={() => void submit(row)}><Send size={14}/> Submit</button>}</div></td></tr>)}</tbody></table></div>}</section>}
  </div>
}
