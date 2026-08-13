import {
  ArrowLeft, CheckCircle2, ClipboardPlus, History, LockKeyhole, Play, Plus, Repeat2, Save, Search, Trash2,
} from 'lucide-react'
import { FormEvent, useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { DashboardHeader } from '../components/DashboardHeader'
import { useAuth } from '../context/AuthContext'
import { useITMonthUrl } from '../context/ITMonthContext'
import { apiFetch } from '../lib/api'
import { formatIndiaDateTime } from '../lib/date'
import { isFullAccessRole } from '../lib/roles'
import { monthLabel, withITMonth } from '../lib/itMonth'
import type {
  Asset, ComponentChangeBatchResponse, ComponentReplacementRecord, WorkRecord,
} from '../types'

const componentOptions = [
  'Monitor', 'Mouse', 'Keyboard', 'Processor', 'Memory', 'SSD', 'HDD', 'Graphics Card',
  'Network Type', 'IP Address', 'MAC Address', 'Operating System', 'Antivirus',
  'Used By', 'Department', 'Workstation No.', 'Price', 'Approved By', 'Asset Master Remarks',
]

const componentField: Record<string, keyof Asset> = {
  Monitor: 'monitor_asset_tags', Mouse: 'mouse_asset_tag', Keyboard: 'keyboard_asset_tag',
  Processor: 'processor', Memory: 'memory_gb', SSD: 'ssd', HDD: 'hdd',
  'Graphics Card': 'graphics_card', 'Network Type': 'network_type', 'IP Address': 'ip_address',
  'MAC Address': 'mac_address', 'Operating System': 'operating_system', Antivirus: 'antivirus',
  'Used By': 'used_by', Department: 'department', 'Workstation No.': 'workstation_no',
  Price: 'price', 'Approved By': 'approved_by', 'Asset Master Remarks': 'remarks',
}

type ChangeType = 'upgrade' | 'replacement' | 'downgrade' | 'upgrade_replacement'
type ChangeRow = {
  rowId: string
  component_type: string
  change_type: ChangeType
  old_value: string
  new_value: string
  reason: string
  old_condition: string
}

function newChangeRow(index = 0): ChangeRow {
  return {
    rowId: `${Date.now()}-${index}-${Math.random().toString(16).slice(2)}`,
    component_type: index === 0 ? 'Mouse' : 'Keyboard',
    change_type: 'replacement',
    old_value: '',
    new_value: '',
    reason: '',
    old_condition: 'Damaged / not working',
  }
}

function assetSearchText(asset: Asset): string {
  return [
    asset.cpu_asset_tag, asset.workstation_no, asset.used_by, asset.department,
    asset.system_name, asset.brand, asset.model, asset.serial_number, asset.connection_type, asset.asset_code,
  ].filter(Boolean).join(' ')
}

export function WorkFormPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { selectedMonth } = useITMonthUrl()
  const preselectedAssetId = searchParams.get('asset')
  const assetLockedFromRegister = Boolean(preselectedAssetId)
  const defaultModule = user?.role === 'drone' ? 'drone' : 'it'
  const [mode, setMode] = useState<'work' | 'component'>(searchParams.get('mode') === 'component' ? 'component' : 'work')
  const [assets, setAssets] = useState<Asset[]>([])
  const [records, setRecords] = useState<WorkRecord[]>([])
  const [componentRecords, setComponentRecords] = useState<ComponentReplacementRecord[]>([])
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState({
    module: defaultModule, asset_id: '', title: '', work_type: 'Inspection', project: '',
    assigned_to: '', technician: user?.full_name || '', priority: 'medium', issue_description: '',
    details: '', start_date: new Date().toISOString().slice(0, 10), expected_completion_date: '',
  })
  const [assetSearch, setAssetSearch] = useState('')
  const [showAssetResults, setShowAssetResults] = useState(false)
  const [changeForm, setChangeForm] = useState({
    asset_id: searchParams.get('asset') || '',
    change_type: 'replacement' as ChangeType,
    technician: user?.full_name || '',
    replacement_date: new Date().toISOString().slice(0, 10),
    approved_by: '', remarks: '',
  })
  const [changeRows, setChangeRows] = useState<ChangeRow[]>([newChangeRow()])

  const selectedChangeAsset = useMemo(
    () => assets.find(asset => asset.id === Number(changeForm.asset_id)),
    [assets, changeForm.asset_id],
  )
  const searchMatches = useMemo(() => {
    const query = assetSearch.trim().toLowerCase()
    return assets
      .filter(asset => !query || assetSearchText(asset).toLowerCase().includes(query))
      .sort((a, b) => {
        const aPrimary = `${a.cpu_asset_tag || ''} ${a.workstation_no || ''}`.toLowerCase()
        const bPrimary = `${b.cpu_asset_tag || ''} ${b.workstation_no || ''}`.toLowerCase()
        const priority = Number(bPrimary.startsWith(query)) - Number(aPrimary.startsWith(query))
        if (priority) return priority
        return aPrimary.localeCompare(bPrimary)
      })
  }, [assets, assetSearch])

  function currentValue(componentType: string): string {
    if (!selectedChangeAsset) return 'Select a system first'
    const key = componentField[componentType]
    const value = key ? selectedChangeAsset[key] : ''
    return value === undefined || value === null || value === '' ? 'Not Previously Recorded' : String(value)
  }

  function monitorChoices(): string[] {
    return selectedChangeAsset?.monitor_asset_tags?.split(',').map(tag => tag.trim()).filter(Boolean) || []
  }

  function selectAsset(asset: Asset) {
    setChangeForm(current => ({ ...current, asset_id: String(asset.id) }))
    setAssetSearch(`${asset.cpu_asset_tag || 'No CPU tag'} · ${asset.workstation_no || 'No workstation'} · ${asset.used_by || 'Unassigned'}`)
    setShowAssetResults(false)
    setChangeRows(rows => rows.map(row => ({
      ...row,
      old_value: row.component_type === 'Monitor'
        ? (asset.monitor_asset_tags?.split(',')[0]?.trim() || 'Not Previously Recorded')
        : (() => {
            const key = componentField[row.component_type]
            const value = key ? asset[key] : ''
            return value === undefined || value === null || value === '' ? 'Not Previously Recorded' : String(value)
          })(),
    })))
  }

  function updateRow(rowId: string, update: Partial<ChangeRow>) {
    setChangeRows(rows => rows.map(row => {
      if (row.rowId !== rowId) return row
      const next = { ...row, ...update }
      if (update.component_type) {
        const value = currentValue(update.component_type)
        next.old_value = update.component_type === 'Monitor' && monitorChoices().length
          ? monitorChoices()[0]
          : value
      }
      if (changeForm.change_type !== 'upgrade_replacement') next.change_type = changeForm.change_type
      return next
    }))
  }

  function addChangeRow() {
    const row = newChangeRow(changeRows.length)
    row.change_type = changeForm.change_type === 'upgrade_replacement' ? 'replacement' : changeForm.change_type
    row.old_value = currentValue(row.component_type)
    setChangeRows(rows => [...rows, row])
  }

  function removeChangeRow(rowId: string) {
    setChangeRows(rows => rows.length === 1 ? rows : rows.filter(row => row.rowId !== rowId))
  }

  useEffect(() => {
    if (!selectedChangeAsset && changeForm.asset_id && assets.length) {
      const asset = assets.find(item => item.id === Number(changeForm.asset_id))
      if (asset) selectAsset(asset)
    }
  }, [assets])

  async function load() {
    setError('')
    try {
      const workModule = user?.role === 'it' || user?.role === 'drone' ? user.role : form.module
      const [workData, assetData, replacementData] = await Promise.all([
        apiFetch<WorkRecord[]>(`/work-records?module=${workModule}`),
        workModule === 'it' ? apiFetch<Asset[]>('/assets?limit=1000') : Promise.resolve([]),
        workModule === 'it' ? apiFetch<ComponentReplacementRecord[]>('/component-replacements') : Promise.resolve([]),
      ])
      setRecords(workData)
      setAssets(assetData)
      setComponentRecords(replacementData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load work records')
    }
  }
  useEffect(() => { void load() }, [form.module])

  async function submit(event: FormEvent) {
    event.preventDefault(); setMessage(''); setError(''); setBusy(true)
    try {
      const payload = {
        ...form,
        reporting_month: form.module === 'it' ? selectedMonth : null,
        asset_id: form.asset_id ? Number(form.asset_id) : null,
        expected_completion_date: form.expected_completion_date || null,
      }
      const created = await apiFetch<WorkRecord>('/work-records', { method: 'POST', body: JSON.stringify(payload) })
      setMessage(`${created.work_code} created. Work status is Open.`)
      setForm({ ...form, asset_id: '', title: '', issue_description: '', details: '', expected_completion_date: '' })
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to save work record')
    } finally { setBusy(false) }
  }

  async function submitComponentChange(event: FormEvent) {
    event.preventDefault(); setMessage(''); setError(''); setBusy(true)
    try {
      if (!changeForm.asset_id) throw new Error('Search and select the system using CPU / Asset Tag and Workstation Number.')
      if (!changeRows.length) throw new Error('Add at least one component or field.')
      const created = await apiFetch<ComponentChangeBatchResponse>('/component-replacements/batch', {
        method: 'POST',
        body: JSON.stringify({
          ...changeForm,
          reporting_month: selectedMonth,
          asset_id: Number(changeForm.asset_id),
          approved_by: changeForm.approved_by || null,
          remarks: changeForm.remarks || null,
          items: changeRows.map(row => ({
            component_type: row.component_type,
            change_type: changeForm.change_type === 'upgrade_replacement' ? row.change_type : changeForm.change_type,
            old_value: row.old_value === 'Not Previously Recorded' ? null : row.old_value,
            new_value: row.new_value,
            reason: row.reason,
            old_condition: row.old_condition || null,
          })),
        }),
      })
      setMessage(`${created.batch_code} saved with ${created.records.length} change item(s). Work record ${created.work_code} was created, the live Asset Register was updated, and month-wise history is ready for Excel.`)
      setChangeRows([newChangeRow()])
      setChangeForm(current => ({ ...current, approved_by: '', remarks: '' }))
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to record component changes')
    } finally { setBusy(false) }
  }

  async function changeStatus(record: WorkRecord, status: string) {
    try {
      await apiFetch(`/work-records/${record.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ status, reporting_month: selectedMonth }),
      })
      setMessage(status === 'completed'
        ? `${record.work_code} completed by IT. No Management approval is required.`
        : `${record.work_code} updated to ${status.replaceAll('_', ' ')}.`)
      await load()
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to update work') }
  }

  return (
    <>
      <DashboardHeader
        eyebrow="CONTROLLED WORKFLOW"
        title="Work Records & Component Changes"
        description={`Identify every system by CPU / Asset Tag and Workstation. IT controls operational completion; activity saved here is reported in ${monthLabel(selectedMonth)} with actual server date and time preserved.`}
      />
      {message && <div className="success-message">{message}</div>}
      {error && <div className="error-message">{error}</div>}

      {defaultModule === 'it' && <div className="work-mode-switch panel">
        <button className={mode === 'work' ? 'active' : ''} onClick={() => setMode('work')}><ClipboardPlus size={17} /> Normal Work Record</button>
        <button className={mode === 'component' ? 'active' : ''} onClick={() => setMode('component')}><Repeat2 size={17} /> Component Changes</button>
        <p>{mode === 'work' ? 'Inspection, repair, installation, maintenance and general IT work.' : 'Search the system, select Upgrade, Replacement, Downgrade or Both, then add one or many component rows.'}</p>
      </div>}

      <section className={`dashboard-grid work-layout ${mode === 'component' ? 'multi-change-layout' : ''}`}>
        <article className="panel work-form-panel">
          {mode === 'work' || defaultModule === 'drone' ? <>
            <div className="panel-heading"><div><span className="section-kicker">NEW WORK RECORD</span><h2>Start Work</h2></div><ClipboardPlus /></div>
            <form className="data-form form-grid" onSubmit={submit}>
              {(user && isFullAccessRole(user.role)) && <label>Department Module<select value={form.module} onChange={e => setForm({ ...form, module: e.target.value })}><option value="it">IT</option><option value="drone">Drone</option></select></label>}
              <label>Work Type<select value={form.work_type} onChange={e => setForm({ ...form, work_type: e.target.value })}><option>Inspection</option><option>New System Installation</option><option>Hardware Repair</option><option>System Upgrade</option><option>Software Installation</option><option>Network Configuration</option><option>Asset Transfer</option><option>Employee Handover</option><option>Asset Return</option><option>Printer Installation</option><option>Printer Repair</option><option>Printer Maintenance</option><option>Print Quality Issue</option><option>Scanner Issue</option><option>Printer Network Configuration</option><option>Toner / Ink Replacement</option><option>Flight Planning</option><option>Drone Maintenance</option></select></label>
              {form.module === 'it' && <label className="full-span">System — CPU / Asset Tag + Workstation<select value={form.asset_id} onChange={e => { const asset = assets.find(item => item.id === Number(e.target.value)); setForm({ ...form, asset_id: e.target.value, assigned_to: asset?.used_by || form.assigned_to }) }}><option value="">Select the system</option>{assets.map(asset => <option key={asset.id} value={asset.id}>{asset.cpu_asset_tag || 'No CPU tag'} · {asset.workstation_no || 'No workstation'} · {asset.used_by || 'Unassigned'} · {asset.asset_code}</option>)}</select></label>}
              <label className="full-span">Work Title<input required value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="Example: Inspect system not powering on" /></label>
              <label>Assigned Employee / Team<input value={form.assigned_to} onChange={e => setForm({ ...form, assigned_to: e.target.value })} /></label>
              <label>Technician<input value={form.technician} onChange={e => setForm({ ...form, technician: e.target.value })} /></label>
              <label>Priority<select value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value })}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select></label>
              <label>Project<input value={form.project} onChange={e => setForm({ ...form, project: e.target.value })} /></label>
              <label>Start Date<input type="date" value={form.start_date} onChange={e => setForm({ ...form, start_date: e.target.value })} /></label>
              <label>Expected Completion<input type="date" value={form.expected_completion_date} onChange={e => setForm({ ...form, expected_completion_date: e.target.value })} /></label>
              <label className="full-span">Issue Description<textarea required rows={3} value={form.issue_description} onChange={e => setForm({ ...form, issue_description: e.target.value })} /></label>
              <label className="full-span">Initial Condition / Required Components<textarea rows={3} value={form.details} onChange={e => setForm({ ...form, details: e.target.value })} /></label>
              <button className="primary-button full-span" disabled={busy}><Save size={17} /> {busy ? 'Saving…' : 'Create Work Record'}</button>
            </form>
          </> : <>
            <div className="panel-heading"><div><span className="section-kicker">ONE WORK ACTIVITY · MULTIPLE CHANGES</span><h2>Record Component Change</h2></div><Repeat2 /></div>
            <div className="form-guidance component-rule">Search by CPU / Asset Tag, Workstation, employee, department or system name. Every saved row updates the current Asset Register. Old and new values remain in a separate month-wise history.</div>
            <form className="data-form multi-change-form" onSubmit={submitComponentChange}>
              {!assetLockedFromRegister && <div className="asset-search-block">
                <label>System — search and select from all {assets.length} assets</label>
                <div className="asset-search-input"><Search size={18} /><input required value={assetSearch} onFocus={() => setShowAssetResults(true)} onChange={e => { setAssetSearch(e.target.value); setShowAssetResults(true); if (!e.target.value) setChangeForm(current => ({ ...current, asset_id: '' })) }} placeholder="Type CPU / Asset Tag, Workstation, employee, department or system name…" /></div>
                {showAssetResults && <div className="asset-search-results full-asset-results">
                  <div className="asset-result-count">Showing {searchMatches.length} of {assets.length} assets</div>
                  {searchMatches.map(asset => <button type="button" key={asset.id} onClick={() => selectAsset(asset)}>
                    <strong>{asset.cpu_asset_tag || 'No CPU tag'} <span>·</span> {asset.workstation_no || 'No workstation'}</strong>
                    <small>{asset.used_by || 'Unassigned'} · {asset.department || 'No department'} · {asset.system_name || asset.asset_code} · {asset.status.replaceAll('_', ' ')}</small>
                  </button>)}
                  {!searchMatches.length && <div>No matching system found.</div>}
                </div>}
              </div>}

              {selectedChangeAsset && <div className={`selected-system-card ${assetLockedFromRegister ? 'locked' : ''}`}>
                <div>
                  <strong>{selectedChangeAsset.cpu_asset_tag || selectedChangeAsset.asset_code} / {selectedChangeAsset.workstation_no || 'Workstation not recorded'}</strong>
                  <span>{selectedChangeAsset.used_by || 'Unassigned'} · {selectedChangeAsset.department || 'Department not recorded'} · {selectedChangeAsset.system_name || 'System name not recorded'} · Internal {selectedChangeAsset.asset_code}</span>
                </div>
                {assetLockedFromRegister && <div className="locked-asset-actions"><span><LockKeyhole size={15} /> Preselected from Asset Register</span><button type="button" className="secondary-button" onClick={() => navigate(withITMonth('/assets', selectedMonth))}><ArrowLeft size={15} /> Change Selected Asset</button></div>}
              </div>}

              <div className="change-batch-header">
                <label>Overall Change Type<select value={changeForm.change_type} onChange={e => {
                  const value = e.target.value as ChangeType
                  setChangeForm({ ...changeForm, change_type: value })
                  setChangeRows(rows => rows.map(row => ({ ...row, change_type: value === 'upgrade_replacement' ? row.change_type : value })))
                }}><option value="upgrade">Upgrade</option><option value="replacement">Replacement</option><option value="downgrade">Downgrade</option><option value="upgrade_replacement">Upgrade + Replacement</option></select></label>
                <label>Technician<input value={changeForm.technician} onChange={e => setChangeForm({ ...changeForm, technician: e.target.value })} /></label>
                <label>Change Date<input type="date" value={changeForm.replacement_date} onChange={e => setChangeForm({ ...changeForm, replacement_date: e.target.value })} /></label>
                <label>Approved By<input value={changeForm.approved_by} onChange={e => setChangeForm({ ...changeForm, approved_by: e.target.value })} placeholder="Optional approver" /></label>
              </div>

              <div className="change-items-heading"><div><span className="section-kicker">CHANGE ITEMS</span><h3>Add every component or field changed in this work activity</h3></div><button type="button" className="secondary-button" onClick={addChangeRow}><Plus size={16} /> Add Component</button></div>

              <div className="change-item-list">
                {changeRows.map((row, index) => {
                  const monitors = monitorChoices()
                  const oldDisplay = row.old_value || currentValue(row.component_type)
                  return <article className="change-item-card" key={row.rowId}>
                    <div className="change-item-top"><div><span>Item {index + 1}</span><strong>{row.component_type}</strong></div><button type="button" className="icon-danger-button" disabled={changeRows.length === 1} onClick={() => removeChangeRow(row.rowId)} title="Remove component"><Trash2 size={16} /></button></div>
                    <div className="change-item-grid">
                      <label>Component / Field<select value={row.component_type} onChange={e => updateRow(row.rowId, { component_type: e.target.value })}>{componentOptions.map(item => <option key={item}>{item}</option>)}</select></label>
                      {changeForm.change_type === 'upgrade_replacement' && <label>Item Action<select value={row.change_type} onChange={e => updateRow(row.rowId, { change_type: e.target.value as ChangeType })}><option value="upgrade">Upgrade</option><option value="replacement">Replacement</option><option value="upgrade_replacement">Upgrade + Replacement</option></select></label>}
                      {row.component_type === 'Monitor' && monitors.length ? <label>Current / Old Monitor<select value={row.old_value || monitors[0]} onChange={e => updateRow(row.rowId, { old_value: e.target.value })}>{monitors.map(tag => <option key={tag}>{tag}</option>)}<option value="Not Previously Recorded">Add another newly tagged monitor</option></select></label> : <label>Current / Old Value<input readOnly value={oldDisplay} /></label>}
                      <label>New Value / New Tag<input required value={row.new_value} onChange={e => updateRow(row.rowId, { new_value: e.target.value })} placeholder="Enter new active tag, capacity, model or value" /></label>
                      <label>Old Condition<input value={row.old_condition} onChange={e => updateRow(row.rowId, { old_condition: e.target.value })} /></label>
                      <label className="wide-field">Reason for This Change<textarea required rows={2} value={row.reason} onChange={e => updateRow(row.rowId, { reason: e.target.value })} placeholder="Why was this component upgraded, replaced or downgraded?" /></label>
                    </div>
                    <div className="item-change-preview"><span>{row.change_type.replaceAll('_', ' ')}</span><strong>{row.component_type}: {oldDisplay} → {row.new_value || 'Enter new value'}</strong></div>
                  </article>
                })}
              </div>

              <label className="batch-remarks">Overall Remarks<textarea rows={3} value={changeForm.remarks} onChange={e => setChangeForm({ ...changeForm, remarks: e.target.value })} placeholder="Activity remark for this selected reporting month only; it will not carry forward" /></label>
              <div className="change-preview"><span>After Save</span><strong>{changeRows.length} item(s) will update the live register under {selectedChangeAsset?.cpu_asset_tag || 'selected CPU tag'} / {selectedChangeAsset?.workstation_no || 'selected workstation'}.</strong><small>One work record and one batch ID will group all changes. Month-wise Asset Register shows latest values; month-wise History Excel shows every old-to-new item.</small></div>
              <button className="primary-button batch-save-button" disabled={busy}><Save size={17} /> {busy ? 'Updating…' : `Save ${changeRows.length} Change Item${changeRows.length === 1 ? '' : 's'} & Update Asset Register`}</button>
            </form>
          </>}
        </article>

        <article className="panel work-record-panel">
          <div className="panel-heading"><div><span className="section-kicker">OPERATION HISTORY</span><h2>{mode === 'component' ? 'Component Change History' : 'Current Work Records'}</h2></div><span className="count-chip">{mode === 'component' ? componentRecords.length : records.length}</span></div>
          {mode === 'component' ? <div className="record-list detailed-records">
            {componentRecords.map(record => <article key={record.id}><div className="record-top"><div><strong>{record.batch_code || record.replacement_code} · {record.replacement_code}</strong><span>{record.cpu_asset_tag || record.asset_code} / {record.workstation_no || 'No workstation'}</span></div><span className="status completed">{record.change_type?.replaceAll('_', ' ') || 'replacement'}</span></div><h3>{record.component_type}</h3><p><strong>{record.old_value || 'Not Previously Recorded'}</strong> → <strong>{record.new_value}</strong></p><div className="record-meta"><span>{record.reason}</span><span>{record.technician || 'IT Department'}</span><span>{record.work_code || 'Work record linked'}</span><span>{formatIndiaDateTime(record.created_at)}</span><span>{record.performed_by || 'System'}{record.performed_by_role ? ` · ${record.performed_by_role.replaceAll('_', ' ')}` : ''}</span></div></article>)}
            {!componentRecords.length && <div className="empty-state">No upgrade, replacement or downgrade change has been recorded.</div>}
          </div> : <div className="record-list detailed-records">
            {records.map(record => <article key={record.id}>
              <div className="record-top"><div><strong>{record.work_code}</strong><span>{record.asset_code || record.project || record.module.toUpperCase()}</span></div><span className={`status ${record.status}`}>{record.status.replaceAll('_', ' ')}</span></div>
              <h3>{record.title}</h3><p>{record.issue_description || record.details}</p>
              <div className="record-meta"><span>{record.work_type}</span><span className={`priority ${record.priority}`}>{record.priority}</span><span>{record.technician || 'Unassigned technician'}</span><span>{new Date(record.created_at).toLocaleDateString()}</span></div>
              <div className="record-actions">
                {record.status === 'open' && (user?.role === 'it' || user?.role === 'admin') && <button className="secondary-button" onClick={() => void changeStatus(record, 'in_progress')}><Play size={15} /> Start</button>}
                {record.status === 'in_progress' && (user?.role === 'it' || user?.role === 'admin') && <button className="primary-button" onClick={() => void changeStatus(record, 'completed')}><CheckCircle2 size={15} /> Complete</button>}
                {record.status === 'completed' && <span className="approval-note"><CheckCircle2 size={15} /> Completed by IT · no Management approval required</span>}
                {record.status === 'closed' && <span className="approval-note"><CheckCircle2 size={15} /> Closed legacy work record</span>}
              </div>
            </article>)}
            {!records.length && <div className="empty-state">No work records have been created for this module.</div>}
          </div>}
          {mode === 'component' && <div className="history-download-note"><History size={18} /><span>Use Excel & Reports, select a month, then download IT Asset Changes to see component operations and Full Edit audits with user, exact date/time and old → new values.</span></div>}
        </article>
      </section>
    </>
  )
}
