import { ArrowRightLeft, FileUp, Laptop, Monitor, PlusCircle, Search } from 'lucide-react'
import { ChangeEvent, FormEvent, useEffect, useRef, useState } from 'react'
import { DashboardHeader } from '../components/DashboardHeader'
import { useAuth } from '../context/AuthContext'
import { useITMonthUrl } from '../context/ITMonthContext'
import { apiFetch, uploadExcel } from '../lib/api'
import { isFullAccessRole } from '../lib/roles'
import { monthLabel } from '../lib/itMonth'
import type { Asset, ITHandoverRecord } from '../types'

function today() { return new Date().toISOString().slice(0, 10) }

const initialForm = {
  asset_id: '', device_category: 'laptop', employee_name: '', dc_number: '', department: '', work_mode: 'office',
  internal_asset_no: '', specification: '', serial_number: '', accessories_provided: '', condition: 'Good',
  action_type: 'handover', activity_date: today(), issued_by: '', remarks: '', asset_updated_status: '', apply_to_asset: true,
}

export function HandoverReturnPage() {
  const { user } = useAuth()
  const { selectedMonth } = useITMonthUrl()
  const canEdit = !!user && (user.role === 'it' || isFullAccessRole(user.role))
  const [form, setForm] = useState(initialForm)
  const [records, setRecords] = useState<ITHandoverRecord[]>([])
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
      const result = await apiFetch<ITHandoverRecord[]>(`/it-activity/handover-records?month=${encodeURIComponent(requestedMonth)}&limit=300`)
      if (requestId !== requestSequence.current) return
      setRecords(result)
    } catch (err) {
      if (requestId !== requestSequence.current) return
      setError(err instanceof Error ? err.message : 'Unable to load handover records')
    }
  }
  useEffect(() => {
    const currentRequest = requestSequence.current + 1
    void loadRecords(true)
    return () => {
      if (requestSequence.current === currentRequest) requestSequence.current += 1
    }
  }, [selectedMonth])

  async function searchAssets() {
    if (!assetSearch.trim()) { setAssets([]); return }
    try { setAssets(await apiFetch<Asset[]>(`/assets?search=${encodeURIComponent(assetSearch)}&limit=30`)) }
    catch (err) { setError(err instanceof Error ? err.message : 'Unable to search assets') }
  }

  function selectAsset(asset: Asset) {
    setForm(current => ({
      ...current,
      asset_id: String(asset.id),
      device_category: asset.device_type.toLowerCase().includes('laptop') ? 'laptop' : 'desktop',
      employee_name: asset.used_by || current.employee_name,
      dc_number: asset.workstation_no || current.dc_number,
      department: asset.department || current.department,
      work_mode: asset.work_mode || current.work_mode,
      internal_asset_no: asset.cpu_asset_tag || asset.asset_code,
      specification: [asset.processor, asset.memory_gb, asset.ssd, asset.hdd].filter(Boolean).join(', '),
      accessories_provided: [asset.monitor_asset_tags, asset.mouse_asset_tag, asset.keyboard_asset_tag].filter(Boolean).join(', '),
    }))
    setAssets([]); setAssetSearch(asset.cpu_asset_tag || asset.asset_code)
  }

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy('save'); setError(''); setMessage('')
    try {
      const payload = { ...form, reporting_month: selectedMonth, asset_id: form.asset_id ? Number(form.asset_id) : null }
      const result = await apiFetch<ITHandoverRecord>('/it-activity/handover-records', { method: 'POST', body: JSON.stringify(payload) })
      setMessage(`${result.activity_code} saved successfully with date, time and user tracking.`)
      setForm(initialForm); setAssetSearch(''); await loadRecords()
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to save record') }
    finally { setBusy('') }
  }

  async function importWorkbook(event: ChangeEvent<HTMLInputElement>, category: 'laptop' | 'desktop') {
    const file = event.target.files?.[0]
    if (!file) return
    setBusy(`import-${category}`); setError(''); setMessage('')
    try {
      const result = await uploadExcel(`/it-activity/imports/handover.xlsx?device_category=${category}`, file)
      setMessage(`${category} import completed: ${result.created || 0} created, ${result.skipped || 0} already present, ${result.invalid || 0} invalid.`)
      await loadRecords()
    } catch (err) { setError(err instanceof Error ? err.message : 'Import failed') }
    finally { setBusy(''); event.target.value = '' }
  }

  return <>
    <DashboardHeader eyebrow="CUSTODY & ASSIGNMENT CONTROL" title="Laptop & Desktop Handover / Return" description={`Records saved now are reported in ${monthLabel(selectedMonth)}. The activity date and actual system entry timestamp remain separately preserved, and each remark belongs only to that activity.`} />
    {message && <div className="success-message">{message}</div>}{error && <div className="error-message">{error}</div>}

    {canEdit && <section className="panel activity-entry-panel">
      <div className="panel-title-row"><div><span className="section-kicker">NEW ACTIVITY</span><h2>Record Handover or Return</h2></div><ArrowRightLeft /></div>
      <div className="asset-lookup-block"><label><Search size={17} /><input value={assetSearch} onChange={event => setAssetSearch(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') void searchAssets() }} placeholder="Search CPU / Asset Tag, workstation, employee or system name" /><button onClick={() => void searchAssets()}>Search</button></label>{assets.length > 0 && <div className="asset-search-results">{assets.map(asset => <button key={asset.id} onClick={() => selectAsset(asset)}><b>{asset.cpu_asset_tag || asset.asset_code}</b><span>{asset.workstation_no || 'No workstation'} · {asset.used_by || 'Available'} · {asset.department || 'No department'}</span></button>)}</div>}</div>
      <form className="activity-form-grid" onSubmit={submit}>
        <label><span>Device Category</span><select value={form.device_category} onChange={event => setForm({ ...form, device_category: event.target.value })}><option value="laptop">Laptop</option><option value="desktop">Desktop</option></select></label>
        <label><span>Action</span><select value={form.action_type} onChange={event => setForm({ ...form, action_type: event.target.value })}><option value="handover">Handover</option><option value="return">Return</option><option value="transfer">Transfer</option><option value="hire">Hire</option><option value="upgrade">Upgrade note</option><option value="replacement">Replacement note</option><option value="downgrade">Downgrade note</option><option value="other">Other</option></select></label>
        <label><span>Employee / Custodian</span><input value={form.employee_name} onChange={event => setForm({ ...form, employee_name: event.target.value })} /></label>
        <label><span>Workstation / DC Number</span><input value={form.dc_number} onChange={event => setForm({ ...form, dc_number: event.target.value })} /></label>
        <label><span>Department</span><input value={form.department} onChange={event => setForm({ ...form, department: event.target.value })} /></label>
        <label><span>Work Mode</span><select value={form.work_mode} onChange={event => setForm({ ...form, work_mode: event.target.value })}><option value="office">Office</option><option value="wfh">WFH</option><option value="field">Field</option></select></label>
        <label><span>Internal / Meher Asset No.</span><input value={form.internal_asset_no} onChange={event => setForm({ ...form, internal_asset_no: event.target.value })} /></label>
        <label><span>Serial Number</span><input value={form.serial_number} onChange={event => setForm({ ...form, serial_number: event.target.value })} /></label>
        <label className="span-2"><span>Specification</span><textarea value={form.specification} onChange={event => setForm({ ...form, specification: event.target.value })} /></label>
        <label className="span-2"><span>Accessories Provided</span><textarea value={form.accessories_provided} onChange={event => setForm({ ...form, accessories_provided: event.target.value })} /></label>
        <label><span>Condition</span><input value={form.condition} onChange={event => setForm({ ...form, condition: event.target.value })} /></label>
        <label><span>Activity Date</span><input type="date" required value={form.activity_date} onChange={event => setForm({ ...form, activity_date: event.target.value })} /></label>
        <label><span>Issued By</span><input value={form.issued_by} onChange={event => setForm({ ...form, issued_by: event.target.value })} placeholder={user?.full_name} /></label>
        <label><span>Asset Updated Status</span><input value={form.asset_updated_status} onChange={event => setForm({ ...form, asset_updated_status: event.target.value })} /></label>
        <label className="span-2"><span>Activity Remarks / Reason — Selected Month Only</span><textarea value={form.remarks} onChange={event => setForm({ ...form, remarks: event.target.value })} /></label>
        <label className="checkbox-field span-2"><input type="checkbox" checked={form.apply_to_asset} onChange={event => setForm({ ...form, apply_to_asset: event.target.checked })} /><span>Update the linked Asset Register assignment/status for Handover, Return or Transfer</span></label>
        <div className="span-2 form-actions"><button className="primary-button" disabled={!!busy}><PlusCircle size={17} /> {busy === 'save' ? 'Saving…' : 'Save Handover / Return'}</button></div>
      </form>
      <div className="historical-import-strip"><span><FileUp size={18} /> Import the original historical workbooks safely and idempotently.</span><label className="secondary-button file-button"><Laptop size={17} /> {busy === 'import-laptop' ? 'Importing…' : 'Import Laptop Excel'}<input hidden type="file" accept=".xlsx" onChange={event => void importWorkbook(event, 'laptop')} /></label><label className="secondary-button file-button"><Monitor size={17} /> {busy === 'import-desktop' ? 'Importing…' : 'Import Desktop Excel'}<input hidden type="file" accept=".xlsx" onChange={event => void importWorkbook(event, 'desktop')} /></label></div>
    </section>}

    <section className="panel"><div className="panel-title-row"><div><span className="section-kicker">AUDIT REGISTER</span><h2>{monthLabel(selectedMonth)} Handover & Return History</h2></div><span className="record-count">{records.length}</span></div><div className="table-scroll"><table className="activity-table"><thead><tr><th>Date / Time</th><th>Device</th><th>Asset / DC</th><th>Employee</th><th>Department</th><th>Action</th><th>Condition</th><th>Performed By</th><th>Remarks</th><th>Source</th></tr></thead><tbody>{records.map(record => <tr key={record.id}><td>{record.activity_date}<small>{record.activity_time || 'Time not in source Excel'}</small></td><td>{record.device_category}</td><td>{record.internal_asset_no || record.asset_code_snapshot || '—'}<small>{record.dc_number}</small></td><td>{record.employee_name || '—'}</td><td>{record.department || '—'}</td><td><span className="activity-badge handover_return">{record.action_type}</span></td><td>{record.condition || '—'}</td><td>{record.performed_by || record.issued_by || 'Historical record'}</td><td>{record.remarks || '—'}</td><td>{record.imported ? `${record.source_sheet} row ${record.source_row}` : 'Software entry'}</td></tr>)}</tbody></table></div></section>
  </>
}
