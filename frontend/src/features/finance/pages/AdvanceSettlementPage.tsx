import { ArrowLeft, FileText, Plus, Send, Trash2, UploadCloud, X } from 'lucide-react'
import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import type { ExpenseClaim, ExpenseSettlement, FinancePaymentMode } from '../../../types'
import { financeExpenseCategories, formatInr } from '../finance-utils'
import '../finance-expenses.css'

interface DraftSettlementItem {
  id: string
  category: string
  otherCategory: string
  description: string
  amount: string
  paymentMode: FinancePaymentMode
  expenseDate: string
}

function todayIso() { return new Date().toISOString().slice(0, 10) }
function blankItem(): DraftSettlementItem { return { id: crypto.randomUUID(), category: 'travel', otherCategory: '', description: '', amount: '', paymentMode: 'upi', expenseDate: todayIso() } }

export function AdvanceSettlementPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [claim, setClaim] = useState<ExpenseClaim | null>(null)
  const [settlement, setSettlement] = useState<ExpenseSettlement | null>(null)
  const [items, setItems] = useState<DraftSettlementItem[]>([blankItem()])
  const [files, setFiles] = useState<File[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!id) return
    setLoading(true); setError('')
    void apiFetch<ExpenseClaim>(`/finance/claims/${id}`)
      .then(result => {
        setClaim(result)
        if (result.claim_type !== 'advance') throw new Error('Settlement is available only for the original Advance Request.')
        if (!result.can_settle_advance && !result.settlement) throw new Error('Finance must release the advance before settlement can be prepared.')
        if (result.settlement) {
          setSettlement(result.settlement)
          if (result.settlement.items.length > 0) setItems(result.settlement.items.map(item => ({ id: `existing-${item.id}-${crypto.randomUUID()}`, category: item.category, otherCategory: item.other_category || '', description: item.description, amount: String(item.amount), paymentMode: item.payment_mode, expenseDate: item.expense_date || todayIso() })))
        }
      })
      .catch(err => setError(err instanceof Error ? err.message : 'Could not load advance settlement'))
      .finally(() => setLoading(false))
  }, [id])

  const total = useMemo(() => items.reduce((sum, item) => sum + (Number(item.amount) || 0), 0), [items])
  const advanceReceived = settlement?.total_advance_received ?? claim?.paid_amount ?? 0
  const difference = advanceReceived - total
  const canEdit = !settlement || settlement.can_edit
  const adminRejected = settlement?.status === 'admin_rejected'

  function updateItem(itemId: string, patch: Partial<DraftSettlementItem>) { setItems(current => current.map(item => item.id === itemId ? { ...item, ...patch } : item)) }
  function removeItem(itemId: string) { setItems(current => current.length === 1 ? current : current.filter(item => item.id !== itemId)) }

  function validate(): string | null {
    if (!claim) return 'Advance claim is unavailable.'
    if (!canEdit) return 'This settlement is no longer editable.'
    for (const item of items) {
      if (!item.description.trim()) return 'Describe every actual expense.'
      if (!(Number(item.amount) > 0)) return 'Every actual expense amount must be greater than zero.'
      if (item.category === 'other' && !item.otherCategory.trim()) return 'Describe every Other expense category.'
      if (!item.paymentMode) return 'Select the payment mode for every actual expense.'
    }
    const existingCount = settlement?.attachments.length || 0
    if (existingCount + files.length === 0) return 'Upload the supporting bills / proof before submitting settlement.'
    if (existingCount + files.length > 50) return 'A settlement can contain at most 50 bill/proof files.'
    const tooLarge = files.find(file => file.size > 15 * 1024 * 1024)
    if (tooLarge) return `${tooLarge.name} is larger than 15 MB.`
    return null
  }

  async function saveSettlement(uploadNewFiles: boolean): Promise<ExpenseSettlement> {
    if (!claim) throw new Error('Advance claim is unavailable.')
    const saved = await apiFetch<ExpenseSettlement>(`/finance/claims/${claim.id}/settlement`, {
      method: 'PUT',
      body: JSON.stringify({ items: items.map(item => ({ category: item.category, other_category: item.category === 'other' ? item.otherCategory.trim() : null, description: item.description.trim(), amount: Number(item.amount), payment_mode: item.paymentMode, expense_date: item.expenseDate || null })) }),
    })
    if (uploadNewFiles && files.length > 0) {
      const data = new FormData(); files.forEach(file => data.append('files', file))
      await apiFetch(`/finance/settlements/${saved.id}/attachments`, { method: 'POST', body: data })
      const refreshed = await apiFetch<ExpenseSettlement>(`/finance/claims/${claim.id}/settlement`)
      setSettlement(refreshed); setFiles([]); return refreshed
    }
    setSettlement(saved)
    return saved
  }

  async function saveDraft(event?: FormEvent) {
    event?.preventDefault()
    if (!canEdit) return
    setSaving(true); setError('')
    try { await saveSettlement(true) } catch (err) { setError(err instanceof Error ? err.message : 'Could not save settlement') } finally { setSaving(false) }
  }

  async function submitSettlement() {
    const validation = validate(); if (validation) { setError(validation); return }
    setSaving(true); setError('')
    try {
      const saved = await saveSettlement(true)
      const submitted = await apiFetch<ExpenseSettlement>(`/finance/settlements/${saved.id}/submit`, { method: 'POST' })
      setSettlement(submitted)
      navigate(`/expenses/${claim!.id}`)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not submit settlement') } finally { setSaving(false) }
  }

  async function removeExistingAttachment(attachmentId: number) {
    if (!settlement || !canEdit || saving) return
    setSaving(true); setError('')
    try {
      await apiFetch(`/finance/settlements/${settlement.id}/attachments/${attachmentId}`, { method: 'DELETE' })
      setSettlement({ ...settlement, attachments: settlement.attachments.filter(item => item.id !== attachmentId) })
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not remove bill') } finally { setSaving(false) }
  }

  if (loading) return <div className="finance-empty-state">Loading settlement...</div>
  if (!claim) return <div className="finance-page"><div className="finance-error">{error || 'Advance not found.'}</div></div>

  return <div className="finance-page">
    <DashboardHeader eyebrow="ADVANCE SETTLEMENT" title={`Settle ${claim.claim_code}`} description={`${claim.project.project_code} · Company advance actually released ${formatInr(advanceReceived)}. Add the actual expenses and bills used for the completed work.`} actions={<Link className="finance-secondary-button" to={`/expenses/${claim.id}`}><ArrowLeft size={16}/> Back to Advance</Link>} />
    {error && <div className="finance-error">{error}</div>}
    {adminRejected && <div className="finance-panel"><div className="finance-decision-box"><span className="finance-panel-kicker">ADMIN REJECTED - CORRECTION REQUIRED</span><strong>Correct this same settlement and re-raise it to Admin.</strong><span className="finance-help-text">Admin reason: {settlement?.admin_comments || 'Review the settlement audit trail for the rejection reason.'}</span><span className="finance-help-text">Update the actual expense lines and/or supporting bills below. The previous rejection remains preserved in the settlement audit history.</span></div></div>}
    {!canEdit && <div className="finance-panel finance-empty-state">This settlement has already entered verification. Return to the advance detail to see its Admin → Finance status.</div>}
    <form className="finance-form-card" onSubmit={saveDraft}>
      <section className="finance-form-section"><header><span>ADVANCE CHAIN</span><h2>Released amount & approved work timeline</h2></header><div className="finance-detail-facts">
        <div className="finance-fact"><span>Advance Released</span><strong>{formatInr(advanceReceived)}</strong></div>
        <div className="finance-fact"><span>Approved Work</span><strong>{claim.approved_work_start_date || claim.requested_work_start_date} → {claim.approved_work_end_date || claim.requested_work_end_date}</strong></div>
        <div className="finance-fact"><span>Settlement Due</span><strong>{claim.settlement_due_date || 'Not set'}</strong></div>
        <div className="finance-fact"><span>Linked Additional Advances</span><strong>{claim.linked_additional_advance_ids.length}</strong></div>
      </div></section>

      <section className="finance-form-section"><header><span>STEP 1</span><h2>Actual expenses</h2><p>Add every actual expense separately with its payment mode and date.</p></header><div className="finance-line-items">{items.map((item, index) => <div className="finance-line-item" key={item.id}>
        <label className="finance-field"><span>Category {index + 1}</span><select disabled={!canEdit} value={item.category} onChange={event => updateItem(item.id,{category:event.target.value})}>{financeExpenseCategories.map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="finance-field"><span>Actual expense / usage *</span><input disabled={!canEdit} value={item.description} onChange={event => updateItem(item.id,{description:event.target.value})} placeholder="Example: Hotel bill for site work"/></label>
        <label className="finance-field"><span>Amount *</span><input disabled={!canEdit} type="number" min="0" step="0.01" value={item.amount} onChange={event => updateItem(item.id,{amount:event.target.value})}/></label>
        <button disabled={!canEdit} className="finance-icon-button" type="button" onClick={() => removeItem(item.id)}><Trash2 size={17}/></button>
        <label className="finance-field"><span>Payment Mode *</span><select disabled={!canEdit} value={item.paymentMode} onChange={event => updateItem(item.id,{paymentMode:event.target.value as FinancePaymentMode})}><option value="upi">UPI</option><option value="cash">Cash</option><option value="card">Card</option><option value="bank_transfer">Bank Transfer</option><option value="cheque">Cheque</option><option value="other">Other</option></select></label>
        <label className="finance-field"><span>Expense Date</span><input disabled={!canEdit} type="date" value={item.expenseDate} onChange={event => updateItem(item.id,{expenseDate:event.target.value})}/></label>
        {item.category === 'other' && <label className="finance-field finance-line-item-other"><span>Other Category *</span><input disabled={!canEdit} value={item.otherCategory} onChange={event => updateItem(item.id,{otherCategory:event.target.value})}/></label>}
      </div>)}</div>{canEdit && <button className="finance-secondary-button" type="button" onClick={() => setItems(current => [...current, blankItem()])}><Plus size={16}/> Add Actual Expense</button>}</section>

      <section className="finance-form-section"><header><span>AUTOMATIC TALLY</span><h2>Advance vs actual bills</h2></header><div className="finance-tally-grid"><div><span>Total Advance Received</span><strong>{formatInr(advanceReceived)}</strong></div><div><span>Total Actual Expenses</span><strong>{formatInr(total)}</strong></div><div className={difference === 0 ? 'tally-ok' : 'tally-warning'}><span>{difference >= 0 ? 'Balance To Return' : 'Shortage'}</span><strong>{formatInr(Math.abs(difference))}</strong></div><div><span>Tally</span><strong>{difference === 0 ? 'FULLY TALLIED' : difference > 0 ? 'BALANCE PENDING' : 'SHORTAGE'}</strong></div></div></section>

      <section className="finance-form-section"><header><span>STEP 2</span><h2>Supporting bills / proof</h2><p>Upload all bills used for this settlement. Original files remain available to Admin and Finance.</p></header>
        {settlement && settlement.attachments.length > 0 && <div className="finance-existing-files">{settlement.attachments.map(file => <div className="finance-existing-file" key={file.id}><FileText size={16}/><span>{file.original_filename}</span>{canEdit && <button type="button" onClick={() => void removeExistingAttachment(file.id)}><X size={15}/></button>}</div>)}</div>}
        {canEdit && <div className="finance-upload-zone"><UploadCloud size={22}/><input type="file" multiple accept="application/pdf,image/jpeg,image/png,image/webp" onChange={event => setFiles(Array.from(event.target.files || []))}/><p>PDF, JPG, PNG or WebP · up to 50 settlement bills · 15 MB per file.</p>{files.length > 0 && <p>{files.length} new bill(s): {files.map(file => file.name).join(', ')}</p>}</div>}
      </section>

      {canEdit && <div className="finance-toolbar"><button className="finance-secondary-button" type="submit" disabled={saving}><FileText size={16}/> {saving ? 'Saving...' : adminRejected ? 'Save Corrected Settlement' : 'Save Settlement Draft'}</button><button className="finance-primary-button" type="button" onClick={() => void submitSettlement()} disabled={saving}><Send size={16}/> {adminRejected ? 'Correct & Re-raise to Admin' : 'Submit Settlement to Admin'}</button></div>}
    </form>
  </div>
}
