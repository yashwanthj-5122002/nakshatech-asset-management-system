import { FileUp, PlusCircle, ReceiptIndianRupee, Search, ShoppingCart } from 'lucide-react'
import { ChangeEvent, FormEvent, useEffect, useRef, useState } from 'react'
import { DashboardHeader } from '../components/DashboardHeader'
import { useAuth } from '../context/AuthContext'
import { useITMonthUrl } from '../context/ITMonthContext'
import { apiFetch, uploadExcel } from '../lib/api'
import { isFullAccessRole } from '../lib/roles'
import { monthLabel } from '../lib/itMonth'
import type { Asset, ITPurchaseRecord } from '../types'

function today() { return new Date().toISOString().slice(0, 10) }
const initialForm = { linked_asset_id: '', purchase_date: today(), po_number: '', asset_number: '', supplier_name: '', supplier_contact: '', item_description: '', warranty_number: '', quantity: '1', unit_price: '', total_price: '', received_date: '', inspection_status: 'Passed', approved_by: '', department: '', remarks: '' }

export function PurchaseProcurementPage() {
  const { user } = useAuth()
  const { selectedMonth } = useITMonthUrl()
  const canEdit = !!user && (user.role === 'it' || isFullAccessRole(user.role))
  const [form, setForm] = useState(initialForm)
  const [records, setRecords] = useState<ITPurchaseRecord[]>([])
  const [assetSearch, setAssetSearch] = useState('')
  const [assets, setAssets] = useState<Asset[]>([])
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const requestSequence = useRef(0)

  async function loadRecords(clearExisting = false) {
    const requestedMonth = selectedMonth
    const requestId = ++requestSequence.current
    if (clearExisting) setRecords([])
    try {
      const result = await apiFetch<ITPurchaseRecord[]>(`/it-activity/purchases?month=${encodeURIComponent(requestedMonth)}&limit=300`)
      if (requestId !== requestSequence.current) return
      setRecords(result)
    } catch (err) {
      if (requestId !== requestSequence.current) return
      setError(err instanceof Error ? err.message : 'Unable to load purchases')
    }
  }
  useEffect(() => {
    const currentRequest = requestSequence.current + 1
    void loadRecords(true)
    return () => {
      if (requestSequence.current === currentRequest) requestSequence.current += 1
    }
  }, [selectedMonth])
  async function searchAssets() { if (!assetSearch.trim()) return; try { setAssets(await apiFetch<Asset[]>(`/assets?search=${encodeURIComponent(assetSearch)}&limit=30`)) } catch (err) { setError(err instanceof Error ? err.message : 'Unable to search assets') } }
  function selectAsset(asset: Asset) { setForm(current => ({ ...current, linked_asset_id: String(asset.id), asset_number: asset.cpu_asset_tag || asset.asset_code, department: asset.department || current.department })); setAssetSearch(asset.cpu_asset_tag || asset.asset_code); setAssets([]) }

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy('save'); setMessage(''); setError('')
    try {
      const payload = { ...form, reporting_month: selectedMonth, linked_asset_id: form.linked_asset_id ? Number(form.linked_asset_id) : null, quantity: Number(form.quantity), unit_price: form.unit_price ? Number(form.unit_price) : null, total_price: form.total_price ? Number(form.total_price) : null, received_date: form.received_date || null }
      const result = await apiFetch<ITPurchaseRecord>('/it-activity/purchases', { method: 'POST', body: JSON.stringify(payload) })
      setMessage(`${result.purchase_code} saved successfully with user, date and time tracking.`); setForm(initialForm); setAssetSearch(''); await loadRecords()
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to save purchase') }
    finally { setBusy('') }
  }

  async function importWorkbook(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; if (!file) return
    setBusy('import'); setMessage(''); setError('')
    try { const result = await uploadExcel('/it-activity/imports/purchases.xlsx', file); setMessage(`Purchase import completed: ${result.created || 0} created, ${result.skipped || 0} already present, ${result.invalid || 0} invalid.`); await loadRecords() }
    catch (err) { setError(err instanceof Error ? err.message : 'Import failed') }
    finally { setBusy(''); event.target.value = '' }
  }

  return <>
    <DashboardHeader eyebrow="PURCHASE TRACEABILITY" title="IT Purchase & Procurement" description={`Purchases saved now are reported in ${monthLabel(selectedMonth)}. Purchase date and actual system entry time remain separate, and purchase remarks never carry automatically to another month.`} />
    {message && <div className="success-message">{message}</div>}{error && <div className="error-message">{error}</div>}
    {canEdit && <section className="panel activity-entry-panel"><div className="panel-title-row"><div><span className="section-kicker">NEW PURCHASE</span><h2>Create Purchase Record</h2></div><ShoppingCart /></div>
      <div className="asset-lookup-block"><label><Search size={17} /><input value={assetSearch} onChange={event => setAssetSearch(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') void searchAssets() }} placeholder="Optionally search and link an existing asset" /><button onClick={() => void searchAssets()}>Search</button></label>{assets.length > 0 && <div className="asset-search-results">{assets.map(asset => <button key={asset.id} onClick={() => selectAsset(asset)}><b>{asset.cpu_asset_tag || asset.asset_code}</b><span>{asset.device_type} · {asset.department || 'No department'}</span></button>)}</div>}</div>
      <form className="activity-form-grid" onSubmit={submit}>
        <label><span>Purchase Date</span><input required type="date" value={form.purchase_date} onChange={event => setForm({ ...form, purchase_date: event.target.value })} /></label>
        <label><span>PO Number</span><input value={form.po_number} onChange={event => setForm({ ...form, po_number: event.target.value })} /></label>
        <label><span>Asset Number</span><input value={form.asset_number} onChange={event => setForm({ ...form, asset_number: event.target.value })} /></label>
        <label><span>Warranty / Serial Number</span><input value={form.warranty_number} onChange={event => setForm({ ...form, warranty_number: event.target.value })} /></label>
        <label><span>Supplier Name</span><input required value={form.supplier_name} onChange={event => setForm({ ...form, supplier_name: event.target.value })} /></label>
        <label><span>Supplier Contact</span><input value={form.supplier_contact} onChange={event => setForm({ ...form, supplier_contact: event.target.value })} /></label>
        <label className="span-2"><span>Item Description</span><textarea required value={form.item_description} onChange={event => setForm({ ...form, item_description: event.target.value })} /></label>
        <label><span>Quantity</span><input required type="number" min="0.01" step="0.01" value={form.quantity} onChange={event => setForm({ ...form, quantity: event.target.value })} /></label>
        <label><span>Unit Price (INR)</span><input type="number" min="0" step="0.01" value={form.unit_price} onChange={event => setForm({ ...form, unit_price: event.target.value })} /></label>
        <label><span>Total Price (INR)</span><input type="number" min="0" step="0.01" value={form.total_price} onChange={event => setForm({ ...form, total_price: event.target.value })} placeholder="Calculated if left blank" /></label>
        <label><span>Received Date</span><input type="date" value={form.received_date} onChange={event => setForm({ ...form, received_date: event.target.value })} /></label>
        <label><span>Inspection Status</span><select value={form.inspection_status} onChange={event => setForm({ ...form, inspection_status: event.target.value })}><option>Passed</option><option>Pending</option><option>Failed</option><option>Not Required</option></select></label>
        <label><span>Approved By</span><input value={form.approved_by} onChange={event => setForm({ ...form, approved_by: event.target.value })} /></label>
        <label><span>Department</span><input value={form.department} onChange={event => setForm({ ...form, department: event.target.value })} /></label>
        <label className="span-2"><span>Purchase Activity Remarks — Selected Month Only</span><textarea value={form.remarks} onChange={event => setForm({ ...form, remarks: event.target.value })} /></label>
        <div className="span-2 form-actions"><button className="primary-button" disabled={!!busy}><PlusCircle size={17} /> {busy === 'save' ? 'Saving…' : 'Save Purchase Record'}</button></div>
      </form>
      <div className="historical-import-strip"><span><FileUp size={18} /> Import the supplied Purchase Details workbook.</span><label className="secondary-button file-button"><ReceiptIndianRupee size={17} /> {busy === 'import' ? 'Importing…' : 'Import Purchase Excel'}<input hidden type="file" accept=".xlsx" onChange={event => void importWorkbook(event)} /></label></div>
    </section>}
    <section className="panel"><div className="panel-title-row"><div><span className="section-kicker">PURCHASE REGISTER</span><h2>{monthLabel(selectedMonth)} Purchase History</h2></div><span className="record-count">{records.length}</span></div><div className="table-scroll"><table className="activity-table"><thead><tr><th>Date</th><th>Purchase / PO</th><th>Supplier</th><th>Item</th><th>Qty</th><th>Unit Price</th><th>Total</th><th>Inspection</th><th>Department</th><th>Recorded By</th><th>Source</th></tr></thead><tbody>{records.map(record => <tr key={record.id}><td>{record.purchase_date}</td><td>{record.purchase_code}<small>{record.po_number || record.asset_number}</small></td><td>{record.supplier_name}<small>{record.supplier_contact}</small></td><td>{record.item_description}<small>{record.warranty_number}</small></td><td>{record.quantity}</td><td>{record.unit_price == null ? '—' : `₹${record.unit_price.toLocaleString('en-IN')}`}</td><td>{record.total_price == null ? '—' : `₹${record.total_price.toLocaleString('en-IN')}`}</td><td>{record.inspection_status || '—'}</td><td>{record.department || '—'}</td><td>{record.created_by || record.approved_by || 'Historical record'}</td><td>{record.imported ? `${record.source_sheet} row ${record.source_row}` : 'Software entry'}</td></tr>)}</tbody></table></div></section>
  </>
}
