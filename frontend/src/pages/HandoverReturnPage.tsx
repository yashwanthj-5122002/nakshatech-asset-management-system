import { ArrowRightLeft, FileUp, Laptop, Monitor, PlusCircle, Search } from 'lucide-react'
import { ChangeEvent, FormEvent, useEffect, useRef, useState } from 'react'
import { DashboardHeader } from '../components/DashboardHeader'
import { useAuth } from '../context/AuthContext'
import { useITMonthUrl } from '../context/ITMonthContext'
import { apiFetch, uploadExcel } from '../lib/api'
import { CUSTODY_ACTIONS, custodyActionAllowed, custodyGuidance, defaultCustodyAction } from '../lib/assetCustody'
import { DEPARTMENT_OPTIONS, MANUAL_ENTRY_VALUE } from '../lib/assetOptions'
import { isFullAccessRole } from '../lib/roles'
import { monthLabel } from '../lib/itMonth'
import type { Asset, ITHandoverRecord } from '../types'

function today() { return new Date().toISOString().slice(0, 10) }

const initialForm = {
  asset_id: '', device_category: 'laptop', employee_name: '', dc_number: '', department: '', work_mode: 'office',
  internal_asset_no: '', specification: '', serial_number: '', accessories_provided: '', condition: 'Good',
  action_type: 'handover', return_status: 'available', activity_date: today(), issued_by: '', remarks: '', asset_updated_status: '', apply_to_asset: true,
}

function custodyMovement(record: ITHandoverRecord) {
  const from = record.from_employee_name
  const to = record.to_employee_name || record.employee_name
  if (record.action_type === 'transfer') return `${from || 'Previous custodian not recorded'} → ${to || 'New custodian not recorded'}`
  if (record.action_type === 'return') return `${from || record.employee_name || 'Custodian not recorded'} → IT / Company`
  if (record.action_type === 'handover') return `IT / Company → ${to || 'Custodian not recorded'}`
  return record.employee_name || '—'
}

function uniqueNames(values: Array<string | null | undefined>) {
  const seen = new Set<string>()
  const result: string[] = []
  for (const value of values) {
    const name = value?.trim()
    if (!name) continue
    const key = name.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    result.push(name)
  }
  return result
}

export function HandoverReturnPage() {
  const { user } = useAuth()
  const { selectedMonth } = useITMonthUrl()
  const canEdit = !!user && (user.role === 'it' || isFullAccessRole(user.role))
  const [form, setForm] = useState(initialForm)
  const [records, setRecords] = useState<ITHandoverRecord[]>([])
  const [assetSearch, setAssetSearch] = useState('')
  const [assets, setAssets] = useState<Asset[]>([])
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null)
  const [employeeSuggestions, setEmployeeSuggestions] = useState<string[]>([])
  const [manualDepartmentEntry, setManualDepartmentEntry] = useState(false)
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

  useEffect(() => {
    const query = assetSearch.trim()
    const selectedKey = selectedAsset ? (selectedAsset.cpu_asset_tag || selectedAsset.asset_code) : ''
    if (!query || query === selectedKey) {
      setAssets([])
      return
    }
    if (query.length < 2) {
      setAssets([])
      return
    }

    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      void apiFetch<Asset[]>(`/assets?search=${encodeURIComponent(query)}&limit=30`, { signal: controller.signal })
        .then(setAssets)
        .catch(err => {
          if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Unable to search assets')
        })
    }, 275)

    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [assetSearch, selectedAsset])

  useEffect(() => {
    if (!['handover', 'transfer'].includes(form.action_type)) {
      setEmployeeSuggestions([])
      return
    }
    const query = form.employee_name.trim()
    if (query.length < 2) {
      setEmployeeSuggestions([])
      return
    }

    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      void apiFetch<Asset[]>(`/assets?search=${encodeURIComponent(query)}&limit=50`, { signal: controller.signal })
        .then(result => {
          const names = uniqueNames([
            ...result.map(asset => asset.used_by),
            ...records.flatMap(record => [record.employee_name, record.from_employee_name, record.to_employee_name]),
          ])
            .filter(name => name.toLowerCase().includes(query.toLowerCase()))
            .filter(name => form.action_type !== 'transfer' || name.toLowerCase() !== selectedAsset?.used_by?.trim().toLowerCase())
            .slice(0, 10)
          setEmployeeSuggestions(names)
        })
        .catch(() => {
          if (!controller.signal.aborted) setEmployeeSuggestions([])
        })
    }, 275)

    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [form.action_type, form.employee_name, records, selectedAsset])

  function changeAssetSearch(value: string) {
    setAssetSearch(value)
    setError('')
    setMessage('')
    if (!selectedAsset) return
    const selectedKey = selectedAsset.cpu_asset_tag || selectedAsset.asset_code
    if (value.trim() === selectedKey) return
    setSelectedAsset(null)
    setAssets([])
    setEmployeeSuggestions([])
    setManualDepartmentEntry(false)
    setForm(current => ({ ...initialForm, activity_date: current.activity_date || today(), issued_by: current.issued_by }))
  }

  function selectAsset(asset: Asset) {
    const action_type = defaultCustodyAction(asset)
    setSelectedAsset(asset)
    setError('')
    setMessage('')
    setManualDepartmentEntry(Boolean(asset.department && !DEPARTMENT_OPTIONS.some(option => option === asset.department)))
    setForm(current => ({
      ...initialForm,
      activity_date: current.activity_date || today(),
      issued_by: current.issued_by,
      asset_id: String(asset.id),
      device_category: asset.device_type.toLowerCase().includes('laptop') ? 'laptop' : 'desktop',
      action_type,
      employee_name: action_type === 'return' ? (asset.used_by || '') : '',
      dc_number: asset.workstation_no || '',
      department: asset.department || '',
      work_mode: asset.work_mode || 'office',
      internal_asset_no: asset.cpu_asset_tag || asset.asset_code,
      serial_number: asset.serial_number || '',
      specification: [asset.processor, asset.memory_gb, asset.ssd, asset.hdd].filter(Boolean).join(', '),
      accessories_provided: [asset.monitor_asset_tags, asset.mouse_asset_tag, asset.keyboard_asset_tag].filter(Boolean).join(', '),
      return_status: 'available',
    }))
    setAssets([])
    setEmployeeSuggestions([])
    setAssetSearch(asset.cpu_asset_tag || asset.asset_code)
  }

  function changeAction(action_type: string) {
    setError('')
    setMessage('')
    if (selectedAsset && !custodyActionAllowed(selectedAsset, action_type)) return
    setEmployeeSuggestions([])
    setForm(current => ({
      ...current,
      action_type,
      return_status: 'available',
      employee_name: action_type === 'return' ? (selectedAsset?.used_by || '') : '',
      dc_number: selectedAsset?.workstation_no || '',
      department: selectedAsset?.department || '',
      work_mode: selectedAsset?.work_mode || 'office',
      asset_updated_status: '',
      apply_to_asset: true,
    }))
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError('')
    setMessage('')
    if (selectedAsset && !custodyActionAllowed(selectedAsset, form.action_type)) {
      setError(custodyGuidance(selectedAsset))
      return
    }
    if (selectedAsset && form.action_type === 'transfer' && selectedAsset.used_by?.trim().toLowerCase() === form.employee_name.trim().toLowerCase()) {
      setError('Transfer To / New Custodian must be different from the current custodian.')
      return
    }
    setBusy('save')
    try {
      const payload = {
        ...form,
        return_status: 'available',
        employee_name: form.action_type === 'return' ? (selectedAsset?.used_by || form.employee_name) : form.employee_name,
        dc_number: form.action_type === 'return' ? (selectedAsset?.workstation_no || form.dc_number) : form.dc_number,
        department: form.action_type === 'return' ? (selectedAsset?.department || form.department) : form.department,
        work_mode: form.action_type === 'return' ? (selectedAsset?.work_mode || form.work_mode) : form.work_mode,
        reporting_month: selectedMonth,
        asset_id: form.asset_id ? Number(form.asset_id) : null,
        apply_to_asset: true,
      }
      const result = await apiFetch<ITHandoverRecord>('/it-activity/handover-records', { method: 'POST', body: JSON.stringify(payload) })
      const movement = custodyMovement(result)
      setMessage(`${result.activity_code} saved successfully. ${movement}.`)
      setForm(initialForm)
      setAssetSearch('')
      setSelectedAsset(null)
      setAssets([])
      setEmployeeSuggestions([])
      setManualDepartmentEntry(false)
      await loadRecords()
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

  const destinationLabel = form.action_type === 'transfer' ? 'Transfer To / New Custodian' : 'Handover To / Custodian'
  const currentCustodyActionAllowed = custodyActionAllowed(selectedAsset, form.action_type)

  return <>
    <DashboardHeader eyebrow="CUSTODY & ASSIGNMENT CONTROL" title="Laptop & Desktop Handover / Return" description={`Records saved now are reported in ${monthLabel(selectedMonth)}. Handover, Transfer and Return are custody movements only; repair and component work remain in their dedicated IT workflows.`} />
    {message && <div className="success-message">{message}</div>}{error && <div className="error-message">{error}</div>}

    {canEdit && <section className="panel activity-entry-panel">
      <div className="panel-title-row"><div><span className="section-kicker">NEW CUSTODY ACTIVITY</span><h2>Record Handover, Transfer or Return</h2></div><ArrowRightLeft /></div>
      <div className="asset-lookup-block">
        <label><Search size={17} /><input value={assetSearch} onChange={event => changeAssetSearch(event.target.value)} placeholder="Start typing asset tag, workstation, employee or system name" autoComplete="off" /></label>
        {assetSearch.trim().length > 0 && assetSearch.trim().length < 2 && !selectedAsset && <small>Type at least 2 characters to search automatically.</small>}
        {assets.length > 0 && <div className="asset-search-results">{assets.map(asset => <button type="button" key={asset.id} onClick={() => selectAsset(asset)}><b>{asset.cpu_asset_tag || asset.asset_code}</b><span>{asset.workstation_no || 'No workstation'} · {asset.used_by || 'Available'} · {asset.department || 'No department'}</span></button>)}</div>}
      </div>

      {selectedAsset && <div className="full-span form-guidance"><strong>Current custody:</strong> {selectedAsset.used_by || 'IT / Company (unassigned)'} · {selectedAsset.department || 'No department'} · {selectedAsset.workstation_no || 'No workstation'} · {(selectedAsset.work_mode || 'office').replaceAll('_', ' ')} · Status {(selectedAsset.status || 'unknown').replaceAll('_', ' ')}<br /><strong>Allowed now:</strong> {custodyGuidance(selectedAsset)}</div>}

      <form className="activity-form-grid" onSubmit={submit}>
        <label><span>Device Category</span><select value={form.device_category} disabled={!!selectedAsset} onChange={event => setForm({ ...form, device_category: event.target.value })}><option value="laptop">Laptop</option><option value="desktop">Desktop</option></select></label>
        <label><span>Action</span><select value={form.action_type} onChange={event => changeAction(event.target.value)}><option value="handover" disabled={!!selectedAsset && !custodyActionAllowed(selectedAsset, 'handover')}>Handover{selectedAsset && !custodyActionAllowed(selectedAsset, 'handover') ? ' — unavailable' : ''}</option><option value="transfer" disabled={!!selectedAsset && !custodyActionAllowed(selectedAsset, 'transfer')}>Transfer{selectedAsset && !custodyActionAllowed(selectedAsset, 'transfer') ? ' — unavailable' : ''}</option><option value="return" disabled={!!selectedAsset && !custodyActionAllowed(selectedAsset, 'return')}>Return{selectedAsset && !custodyActionAllowed(selectedAsset, 'return') ? ' — unavailable' : ''}</option></select></label>
        {form.action_type === 'return' && <label><span>Return Outcome</span><select value="available" disabled><option value="available">Available after inspection</option></select></label>}
        {form.action_type === 'return'
          ? <label><span>Returning From</span><input value={selectedAsset?.used_by || form.employee_name || ''} readOnly placeholder="Select an assigned asset" /></label>
          : <label className="asset-lookup-block"><span>{destinationLabel}</span><input required value={form.employee_name} onChange={event => setForm({ ...form, employee_name: event.target.value })} placeholder={form.action_type === 'transfer' ? 'Start typing new employee / custodian' : 'Start typing employee / custodian'} autoComplete="off" />{employeeSuggestions.length > 0 && <div className="asset-search-results">{employeeSuggestions.map(name => <button type="button" key={name} onClick={() => { setForm(current => ({ ...current, employee_name: name })); setEmployeeSuggestions([]) }}>{name}</button>)}</div>}<small>Select a suggestion when available, or continue typing to enter a valid employee/custodian manually.</small></label>}
        <label><span>{form.action_type === 'transfer' ? 'New Workstation / DC Number' : form.action_type === 'return' ? 'Current Workstation / DC Number' : 'Workstation / DC Number'}</span><input readOnly={form.action_type === 'return'} value={form.dc_number} onChange={event => setForm({ ...form, dc_number: event.target.value })} /></label>
        {form.action_type === 'return'
          ? <label><span>Current Department</span><input readOnly value={form.department} /></label>
          : <label><span>{form.action_type === 'transfer' ? 'New Department' : 'Department'}</span><select value={manualDepartmentEntry ? MANUAL_ENTRY_VALUE : form.department} onChange={event => { const value = event.target.value; if (value === MANUAL_ENTRY_VALUE) { setManualDepartmentEntry(true); setForm(current => ({ ...current, department: '' })) } else { setManualDepartmentEntry(false); setForm(current => ({ ...current, department: value })) } }}><option value="">Select department</option>{!manualDepartmentEntry && form.department && !DEPARTMENT_OPTIONS.some(option => option === form.department) && <option value={form.department}>Current value — {form.department}</option>}{DEPARTMENT_OPTIONS.map(option => <option key={option} value={option}>{option}</option>)}<option value={MANUAL_ENTRY_VALUE}>Other / Enter Manually</option></select>{manualDepartmentEntry && <input autoFocus value={form.department} onChange={event => setForm(current => ({ ...current, department: event.target.value }))} placeholder="Enter department" />}</label>}
        <label><span>{form.action_type === 'transfer' ? 'New Work Mode' : form.action_type === 'return' ? 'Current Work Mode' : 'Work Mode'}</span><select disabled={form.action_type === 'return'} value={form.work_mode} onChange={event => setForm({ ...form, work_mode: event.target.value })}><option value="office">Office</option><option value="wfh">WFH</option><option value="field">Field</option></select></label>
        <label><span>Internal / Meher Asset No.</span><input readOnly={!!selectedAsset} value={form.internal_asset_no} onChange={event => setForm({ ...form, internal_asset_no: event.target.value })} /></label>
        <label><span>Serial Number</span><input readOnly={!!selectedAsset} value={form.serial_number} onChange={event => setForm({ ...form, serial_number: event.target.value })} /></label>
        <label className="span-2"><span>Specification</span><textarea value={form.specification} onChange={event => setForm({ ...form, specification: event.target.value })} /></label>
        <label className="span-2"><span>Accessories Provided</span><textarea value={form.accessories_provided} onChange={event => setForm({ ...form, accessories_provided: event.target.value })} /></label>
        <label><span>Condition</span><input value={form.condition} onChange={event => setForm({ ...form, condition: event.target.value })} /></label>
        <label><span>Activity Date</span><input type="date" required value={form.activity_date} onChange={event => setForm({ ...form, activity_date: event.target.value })} /></label>
        <label><span>Issued By</span><input value={form.issued_by} onChange={event => setForm({ ...form, issued_by: event.target.value })} placeholder={user?.full_name} /></label>
        <label><span>Asset Updated Status</span><input value={form.asset_updated_status} onChange={event => setForm({ ...form, asset_updated_status: event.target.value })} /></label>
        <label className="span-2"><span>Activity Remarks / Reason — Selected Month Only</span><textarea value={form.remarks} onChange={event => setForm({ ...form, remarks: event.target.value })} /></label>
        <label className="checkbox-field span-2"><input type="checkbox" checked disabled /><span>Linked Asset Register update is required for live Handover, Transfer and Return.</span></label>
        <div className="span-2 form-actions"><button className="primary-button" disabled={!!busy || (!!selectedAsset && !currentCustodyActionAllowed)}><PlusCircle size={17} /> {busy === 'save' ? 'Saving…' : `Save ${form.action_type === 'transfer' ? 'Transfer' : form.action_type === 'return' ? 'Return' : 'Handover'}`}</button></div>
      </form>
      <div className="historical-import-strip"><span><FileUp size={18} /> Historical Excel imports remain available and do not change the simplified live custody workflow.</span><label className="secondary-button file-button"><Laptop size={17} /> {busy === 'import-laptop' ? 'Importing…' : 'Import Laptop Excel'}<input hidden type="file" accept=".xlsx" onChange={event => void importWorkbook(event, 'laptop')} /></label><label className="secondary-button file-button"><Monitor size={17} /> {busy === 'import-desktop' ? 'Importing…' : 'Import Desktop Excel'}<input hidden type="file" accept=".xlsx" onChange={event => void importWorkbook(event, 'desktop')} /></label></div>
    </section>}

    <section className="panel"><div className="panel-title-row"><div><span className="section-kicker">AUDIT REGISTER</span><h2>{monthLabel(selectedMonth)} Handover & Return History</h2></div><span className="record-count">{records.length}</span></div><div className="table-scroll"><table className="activity-table"><thead><tr><th>Date / Time</th><th>Device</th><th>Asset / DC</th><th>Custody Movement</th><th>Department</th><th>Action</th><th>Condition</th><th>Performed By</th><th>Remarks</th><th>Source</th></tr></thead><tbody>{records.map(record => <tr key={record.id}><td>{record.activity_date}<small>{record.activity_time || 'Time not in source Excel'}</small></td><td>{record.device_category}</td><td>{record.internal_asset_no || record.asset_code_snapshot || '—'}<small>{record.dc_number}</small></td><td>{custodyMovement(record)}</td><td>{record.department || '—'}</td><td><span className="activity-badge handover_return">{record.action_type}</span></td><td>{record.condition || '—'}</td><td>{record.performed_by || record.issued_by || 'Historical record'}</td><td>{record.remarks || '—'}</td><td>{record.imported ? `${record.source_sheet} row ${record.source_row}` : 'Software entry'}</td></tr>)}</tbody></table></div></section>
  </>
}
