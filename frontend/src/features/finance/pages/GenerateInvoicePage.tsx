import { Download, Eye, FilePlus2, Plus, Printer, RefreshCcw, Trash2, X } from 'lucide-react'
import { FormEvent, useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiBlob, apiFetch, downloadFile } from '../../../lib/api'
import type { InvoiceDocumentPayload } from '../../operations/lifecycle-types'
import { formatMoney } from '../../operations/lifecycle-types'
import { InvoiceA4Document } from '../components/InvoiceA4Document'
import '../finance-expenses.css'
import '../invoice-document.css'
import '../../operations/operations.css'

type PartyForm = { company_name: string; address: string; gstin: string; pan: string; email: string; phone: string }
type SellerForm = PartyForm & { msme_registration: string; website: string }
type BankForm = { bank_name: string; account_name: string; account_number: string; ifsc_code: string; swift_code: string; bank_address: string }
type ItemForm = { id: string; description: string; detail: string; hsn_sac: string; quantity: string; unit: string; rate: string }
type TaxMode = 'none' | 'cgst_sgst' | 'igst'
type HistoryRow = { id: number; invoice_number: string; invoice_date: string; party: string; total: number; created_by: string; created_at: string }

const blankParty = (): PartyForm => ({ company_name: '', address: '', gstin: '', pan: '', email: '', phone: '' })
const blankItem = (): ItemForm => ({ id: crypto.randomUUID(), description: '', detail: '', hsn_sac: '', quantity: '1', unit: 'Nos', rate: '0' })
const clean = (value: string) => value.trim() || null
const today = () => new Date().toISOString().slice(0, 10)

export function GenerateInvoicePage() {
  const [invoice, setInvoice] = useState({ invoice_number: '', invoice_date: today(), terms: '', due_date: '', reference_work_order: '', place_of_supply: '' })
  const [seller, setSeller] = useState<SellerForm>({ ...blankParty(), company_name: 'NAKSHA TECH PRIVATE LIMITED', msme_registration: '', website: '' })
  const [billTo, setBillTo] = useState<PartyForm>(blankParty)
  const [shipTo, setShipTo] = useState<PartyForm>(blankParty)
  const [sameAsBill, setSameAsBill] = useState(true)
  const [bank, setBank] = useState<BankForm>({ bank_name: '', account_name: '', account_number: '', ifsc_code: '', swift_code: '', bank_address: '' })
  const [items, setItems] = useState<ItemForm[]>([blankItem()])
  const [taxMode, setTaxMode] = useState<TaxMode>('none')
  const [taxes, setTaxes] = useState({ cgst: '9', sgst: '9', igst: '18' })
  const [notes, setNotes] = useState('')
  const [termsConditions, setTermsConditions] = useState('')
  const [signatory, setSignatory] = useState('')
  const [qrData, setQrData] = useState('')
  const [history, setHistory] = useState<HistoryRow[]>([])
  const [preview, setPreview] = useState<InvoiceDocumentPayload | null>(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const taxRate = taxMode === 'cgst_sgst' ? Number(taxes.cgst || 0) + Number(taxes.sgst || 0) : taxMode === 'igst' ? Number(taxes.igst || 0) : 0
  const subtotal = useMemo(() => items.reduce((sum, item) => sum + (Number(item.quantity) || 0) * (Number(item.rate) || 0), 0), [items])
  const taxTotal = Math.round(subtotal * taxRate) / 100

  async function loadHistory() {
    try {
      const result = await apiFetch<{ invoices: HistoryRow[] }>('/finance/generated-invoices')
      setHistory(result.invoices)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invoice history could not be loaded')
    }
  }

  useEffect(() => { void loadHistory() }, [])

  function partyFields(value: PartyForm, change: (next: PartyForm) => void, prefix: string) {
    return <div className="finance-form-grid">
      <label className="finance-field"><span>Company / Party Name *</span><input required value={value.company_name} onChange={event => change({ ...value, company_name: event.target.value })} name={`${prefix}-company`}/></label>
      <label className="finance-field"><span>GSTIN</span><input value={value.gstin} onChange={event => change({ ...value, gstin: event.target.value })}/></label>
      <label className="finance-field full"><span>Address *</span><textarea required value={value.address} onChange={event => change({ ...value, address: event.target.value })}/></label>
      <label className="finance-field"><span>PAN</span><input value={value.pan} onChange={event => change({ ...value, pan: event.target.value })}/></label>
      <label className="finance-field"><span>Email</span><input type="email" value={value.email} onChange={event => change({ ...value, email: event.target.value })}/></label>
      <label className="finance-field"><span>Phone</span><input value={value.phone} onChange={event => change({ ...value, phone: event.target.value })}/></label>
    </div>
  }

  function updateItem(id: string, patch: Partial<ItemForm>) {
    setItems(current => current.map(item => item.id === id ? { ...item, ...patch } : item))
  }

  async function generate(event: FormEvent) {
    event.preventDefault()
    setError(''); setNotice('')
    if (!items.length || items.some(item => !item.description.trim() || Number(item.quantity) <= 0 || Number(item.rate) < 0)) {
      setError('Complete every line item with a description, positive quantity and valid rate.')
      return
    }
    setBusy('generate')
    try {
      const targetShip = sameAsBill ? billTo : shipTo
      const body = {
        invoice_number: invoice.invoice_number.trim(), invoice_date: invoice.invoice_date,
        terms: clean(invoice.terms), due_date: invoice.due_date || null,
        reference_work_order: clean(invoice.reference_work_order), place_of_supply: clean(invoice.place_of_supply),
        seller: { ...seller, gstin: clean(seller.gstin), pan: clean(seller.pan), email: clean(seller.email), phone: clean(seller.phone), msme_registration: clean(seller.msme_registration), website: clean(seller.website) },
        bill_to: { ...billTo, gstin: clean(billTo.gstin), pan: clean(billTo.pan), email: clean(billTo.email), phone: clean(billTo.phone) },
        ship_to: { ...targetShip, gstin: clean(targetShip.gstin), pan: clean(targetShip.pan), email: clean(targetShip.email), phone: clean(targetShip.phone) },
        bank: Object.fromEntries(Object.entries(bank).map(([key, value]) => [key, clean(value)])),
        line_items: items.map((item, index) => {
          const amount = Math.round(Number(item.quantity) * Number(item.rate) * 100) / 100
          return { sequence: index + 1, description: item.description.trim(), detail: clean(item.detail), hsn_sac: clean(item.hsn_sac), quantity: Number(item.quantity), unit: item.unit.trim(), rate: Number(item.rate), tax_percent: taxRate, tax_amount: Math.round(amount * taxRate) / 100, amount }
        }),
        tax_mode: taxMode, cgst_percent: taxMode === 'cgst_sgst' ? Number(taxes.cgst) : 0,
        sgst_percent: taxMode === 'cgst_sgst' ? Number(taxes.sgst) : 0, igst_percent: taxMode === 'igst' ? Number(taxes.igst) : 0,
        notes: clean(notes), terms_conditions: clean(termsConditions), authorized_signatory_name: clean(signatory), qr_data: clean(qrData),
      }
      const result = await apiFetch<InvoiceDocumentPayload>('/finance/generated-invoices', { method: 'POST', body: JSON.stringify(body) })
      setPreview(result)
      setNotice(`Invoice ${result.invoice.invoice_number} generated and saved in standalone history.`)
      await loadHistory()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invoice could not be generated')
    } finally { setBusy('') }
  }

  async function viewInvoice(id: number) {
    setBusy(`view-${id}`); setError('')
    try { setPreview(await apiFetch<InvoiceDocumentPayload>(`/finance/generated-invoices/${id}/document`)) }
    catch (err) { setError(err instanceof Error ? err.message : 'Invoice preview could not be loaded') }
    finally { setBusy('') }
  }

  async function downloadInvoice(id: number, number: string) {
    setBusy(`download-${id}`); setError('')
    try { await downloadFile(`/finance/generated-invoices/${id}/document.pdf?download=true`, `${number}_A4_Invoice.pdf`) }
    catch (err) { setError(err instanceof Error ? err.message : 'Invoice PDF could not be downloaded') }
    finally { setBusy('') }
  }

  async function printInvoice(id: number) {
    const printWindow = window.open('', '_blank')
    if (!printWindow) { setError('Allow pop-ups for this site to print the invoice.'); return }
    printWindow.opener = null; printWindow.document.body.textContent = 'Preparing A4 invoice for print...'
    setBusy(`print-${id}`); setError('')
    try {
      const blob = await apiBlob(`/finance/generated-invoices/${id}/document.pdf`)
      const url = URL.createObjectURL(blob)
      printWindow.onload = () => { printWindow.focus(); printWindow.print(); window.setTimeout(() => URL.revokeObjectURL(url), 60_000) }
      printWindow.location.href = url
    } catch (err) { printWindow.close(); setError(err instanceof Error ? err.message : 'Invoice PDF could not be prepared for printing') }
    finally { setBusy('') }
  }

  return <div className="finance-page generate-invoice-page">
    <DashboardHeader eyebrow="FINANCE · STANDALONE DOCUMENT" title="Generate Invoice" description="Create a professional A4 tax invoice without linking it to projects, advances, payments or accounting KPIs." actions={<button className="operations-button secondary" type="button" onClick={() => void loadHistory()}><RefreshCcw size={16}/> Refresh History</button>} meta={<><span className="nk-meta-chip"><FilePlus2 size={14}/> Finance-only manual invoice</span><span className="nk-meta-chip">Standalone history · no accounting impact</span></>}/>
    {error && <div className="operations-alert error">{error}</div>}
    {notice && <div className="operations-alert success">{notice}</div>}
    <form className="finance-form-card standalone-invoice-form" onSubmit={generate}>
      <section className="finance-form-section"><header><span>INVOICE DETAILS</span><h2>Document identity</h2><p>Enter the invoice number, dates, commercial terms and supply reference.</p></header><div className="finance-form-grid">
        <label className="finance-field"><span>Invoice Number *</span><input required value={invoice.invoice_number} onChange={event => setInvoice({ ...invoice, invoice_number: event.target.value })}/></label>
        <label className="finance-field"><span>Invoice Date *</span><input required type="date" value={invoice.invoice_date} onChange={event => setInvoice({ ...invoice, invoice_date: event.target.value })}/></label>
        <label className="finance-field"><span>Payment Terms</span><input value={invoice.terms} onChange={event => setInvoice({ ...invoice, terms: event.target.value })} placeholder="e.g. Due on receipt"/></label>
        <label className="finance-field"><span>Due Date</span><input type="date" value={invoice.due_date} onChange={event => setInvoice({ ...invoice, due_date: event.target.value })}/></label>
        <label className="finance-field"><span>Reference / Work Order</span><input value={invoice.reference_work_order} onChange={event => setInvoice({ ...invoice, reference_work_order: event.target.value })}/></label>
        <label className="finance-field"><span>Place of Supply</span><input value={invoice.place_of_supply} onChange={event => setInvoice({ ...invoice, place_of_supply: event.target.value })}/></label>
      </div></section>
      <section className="finance-form-section"><header><span>SELLER</span><h2>NakshaTech details</h2></header>{partyFields(seller, next => setSeller({ ...seller, ...next }), 'seller')}<div className="finance-form-grid">
        <label className="finance-field"><span>MSME Registration</span><input value={seller.msme_registration} onChange={event => setSeller({ ...seller, msme_registration: event.target.value })}/></label>
        <label className="finance-field"><span>Website</span><input value={seller.website} onChange={event => setSeller({ ...seller, website: event.target.value })}/></label>
      </div></section>
      <section className="finance-form-section"><header><span>BILL TO</span><h2>Customer billing details</h2></header>{partyFields(billTo, setBillTo, 'bill')}</section>
      <section className="finance-form-section"><header><span>SHIP TO</span><h2>Delivery details</h2><label className="standalone-checkbox"><input type="checkbox" checked={sameAsBill} onChange={event => setSameAsBill(event.target.checked)}/> Same as Bill To</label></header>{!sameAsBill && partyFields(shipTo, setShipTo, 'ship')}</section>
      <section className="finance-form-section"><header><span>LINE ITEMS</span><h2>Invoice particulars</h2><p>Description, HSN/SAC, quantity, unit, rate and GST are preserved in the saved invoice.</p></header>
        <div className="standalone-line-items">{items.map((item, index) => <div className="standalone-line-item" key={item.id}>
          <span className="standalone-line-number">{index + 1}</span>
          <label className="finance-field standalone-description"><span>Description *</span><input required value={item.description} onChange={event => updateItem(item.id, { description: event.target.value })}/></label>
          <label className="finance-field"><span>HSN/SAC</span><input value={item.hsn_sac} onChange={event => updateItem(item.id, { hsn_sac: event.target.value })}/></label>
          <label className="finance-field"><span>Qty *</span><input required type="number" min="0.001" step="0.001" value={item.quantity} onChange={event => updateItem(item.id, { quantity: event.target.value })}/></label>
          <label className="finance-field"><span>Unit *</span><input required value={item.unit} onChange={event => updateItem(item.id, { unit: event.target.value })}/></label>
          <label className="finance-field"><span>Rate *</span><input required type="number" min="0" step="0.01" value={item.rate} onChange={event => updateItem(item.id, { rate: event.target.value })}/></label>
          <label className="finance-field standalone-detail"><span>Details</span><input value={item.detail} onChange={event => updateItem(item.id, { detail: event.target.value })}/></label>
          <strong className="standalone-line-total">{formatMoney((Number(item.quantity) || 0) * (Number(item.rate) || 0))}</strong>
          <button type="button" className="standalone-remove-line" disabled={items.length === 1} onClick={() => setItems(current => current.filter(value => value.id !== item.id))} aria-label={`Remove line ${index + 1}`}><Trash2 size={16}/></button>
        </div>)}</div>
        <button className="operations-button secondary" type="button" onClick={() => setItems(current => [...current, blankItem()])}><Plus size={16}/> Add Line Item</button>
      </section>
      <section className="finance-form-section"><header><span>TAX & TOTALS</span><h2>GST treatment</h2></header><div className="finance-form-grid">
        <label className="finance-field"><span>Tax Mode</span><select value={taxMode} onChange={event => setTaxMode(event.target.value as TaxMode)}><option value="none">No GST</option><option value="cgst_sgst">CGST + SGST</option><option value="igst">IGST</option></select></label>
        {taxMode === 'cgst_sgst' && <><label className="finance-field"><span>CGST %</span><input type="number" min="0" max="100" step="0.01" value={taxes.cgst} onChange={event => setTaxes({ ...taxes, cgst: event.target.value })}/></label><label className="finance-field"><span>SGST %</span><input type="number" min="0" max="100" step="0.01" value={taxes.sgst} onChange={event => setTaxes({ ...taxes, sgst: event.target.value })}/></label></>}
        {taxMode === 'igst' && <label className="finance-field"><span>IGST %</span><input type="number" min="0" max="100" step="0.01" value={taxes.igst} onChange={event => setTaxes({ ...taxes, igst: event.target.value })}/></label>}
      </div><div className="standalone-live-totals"><span>Subtotal <strong>{formatMoney(subtotal)}</strong></span><span>Tax <strong>{formatMoney(taxTotal)}</strong></span><span>Total / Balance Due <strong>{formatMoney(subtotal + taxTotal)}</strong></span></div></section>
      <section className="finance-form-section"><header><span>BANK DETAILS</span><h2>Remittance instructions</h2></header><div className="finance-form-grid">
        {Object.entries({ bank_name: 'Bank Name', account_name: 'Account Name', account_number: 'Account Number', ifsc_code: 'IFSC Code', swift_code: 'SWIFT Code', bank_address: 'Bank Address' }).map(([key, label]) => <label className={`finance-field ${key === 'bank_address' ? 'full' : ''}`} key={key}><span>{label}</span><input value={bank[key as keyof BankForm]} onChange={event => setBank({ ...bank, [key]: event.target.value })}/></label>)}
      </div></section>
      <section className="finance-form-section"><header><span>FINAL DETAILS</span><h2>Notes, terms and authorization</h2></header><div className="finance-form-grid">
        <label className="finance-field full"><span>Notes</span><textarea value={notes} onChange={event => setNotes(event.target.value)}/></label>
        <label className="finance-field full"><span>Terms & Conditions</span><textarea value={termsConditions} onChange={event => setTermsConditions(event.target.value)}/></label>
        <label className="finance-field"><span>Authorized Signatory Name</span><input value={signatory} onChange={event => setSignatory(event.target.value)}/></label>
        <label className="finance-field"><span>Optional QR Data</span><input value={qrData} onChange={event => setQrData(event.target.value)} placeholder="Payment URL, UPI or reference text"/></label>
      </div></section>
      <div className="standalone-form-actions"><button className="operations-button" type="submit" disabled={busy === 'generate'}><FilePlus2 size={16}/> {busy === 'generate' ? 'Generating…' : 'Generate & Preview Invoice'}</button></div>
    </form>
    <section className="finance-panel"><div className="finance-panel-header"><div><span className="finance-panel-kicker">STANDALONE HISTORY</span><h2>Previously generated invoices</h2><p>These documents stay separate from project billing and all accounting calculations.</p></div></div>
      {history.length === 0 ? <div className="finance-empty-state">No standalone invoices have been generated yet.</div> : <div className="finance-table-wrap"><table className="finance-table"><thead><tr><th>Invoice</th><th>Date</th><th>Party</th><th>Total</th><th>Created By</th><th>Created At</th><th>Actions</th></tr></thead><tbody>{history.map(row => <tr key={row.id}><td><strong>{row.invoice_number}</strong></td><td>{row.invoice_date}</td><td>{row.party}</td><td><strong>{formatMoney(row.total)}</strong></td><td>{row.created_by}</td><td>{new Date(row.created_at).toLocaleString('en-IN')}</td><td><div className="finance-inline-actions"><button type="button" onClick={() => void viewInvoice(row.id)} disabled={busy === `view-${row.id}`}><Eye size={14}/> View</button><button type="button" onClick={() => void downloadInvoice(row.id, row.invoice_number)}><Download size={14}/> PDF</button><button type="button" onClick={() => void printInvoice(row.id)}><Printer size={14}/> Print</button></div></td></tr>)}</tbody></table></div>}
    </section>
    {preview && <div className="invoice-preview-backdrop" role="presentation" onMouseDown={() => setPreview(null)}><section className="invoice-preview-dialog" role="dialog" aria-modal="true" aria-labelledby="standalone-preview-title" onMouseDown={event => event.stopPropagation()}><header className="invoice-preview-toolbar"><div><span>A4 STANDALONE INVOICE PREVIEW</span><h2 id="standalone-preview-title">{preview.invoice.invoice_number}</h2><p>Saved Finance-only document · no project or accounting links</p></div><div className="invoice-preview-actions"><button type="button" onClick={() => void downloadInvoice(preview.invoice.id, preview.invoice.invoice_number)}><Download size={16}/> Download PDF</button><button type="button" onClick={() => void printInvoice(preview.invoice.id)}><Printer size={16}/> Print</button><button type="button" className="invoice-preview-close" onClick={() => setPreview(null)} aria-label="Close invoice preview"><X size={19}/></button></div></header><div className="invoice-preview-scroll-area"><InvoiceA4Document invoice={preview}/></div></section></div>}
  </div>
}
