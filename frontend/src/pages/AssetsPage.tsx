import {
  Archive,
  ArrowRightLeft,
  CalendarDays,
  ChevronRight,
  Filter,
  Pencil,
  Plus,
  Repeat2,
  RotateCcw,
  Save,
  Search,
  Trash2,
  X,
} from 'lucide-react'
import { FormEvent, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { DashboardHeader } from '../components/DashboardHeader'
import { useAuth } from '../context/AuthContext'
import { useITMonthUrl } from '../context/ITMonthContext'
import { apiFetch } from '../lib/api'
import { formatIndiaDateTime, isCurrentIndiaMonth } from '../lib/date'
import { isFullAccessRole } from '../lib/roles'
import { withITMonth } from '../lib/itMonth'
import type { Asset, ReportMonth } from '../types'

const statusOptions = [
  'available', 'assigned', 'in_use', 'wfh', 'field_deployment', 'under_inspection', 'repair',
  'replacement_pending', 'replaced', 'damaged', 'beyond_repair', 'returned', 'missing', 'retired',
  'for_parts', 'disposal_pending', 'disposed',
]

const auditFieldLabels: Record<string, string> = {
  used_by: 'Used By', workstation_no: 'Workstation Number', department: 'Department',
  cpu_asset_tag: 'CPU / Asset Tag', monitor_asset_tags: 'Monitor Asset Tag(s)',
  mouse_asset_tag: 'Mouse Asset Tag', keyboard_asset_tag: 'Keyboard Asset Tag',
  system_name: 'System Name', device_type: 'Device Type', processor: 'Processor',
  memory_gb: 'Memory', ssd: 'SSD', hdd: 'HDD', ip_address: 'IP Address',
  mac_address: 'MAC Address', graphics_card: 'Graphics Card', operating_system: 'Operating System',
  antivirus: 'Antivirus', network_type: 'Network Type', approved_by: 'Approved By',
  price: 'Price', remarks: 'Remarks', asset_date: 'Asset Record Date', location: 'Location',
  work_mode: 'Work Mode', status: 'Status',
}

type AssetHistoryItem = NonNullable<Asset['history']>[number]

function parseAuditObject(raw?: string): Record<string, unknown> {
  if (!raw) return {}
  try {
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
  } catch {
    return {}
  }
}

function auditPairs(item: AssetHistoryItem) {
  const oldValues = parseAuditObject(item.old_value)
  const newValues = parseAuditObject(item.new_value)
  const keys = Array.from(new Set([...Object.keys(oldValues), ...Object.keys(newValues)]))
  if (!keys.length) return []
  return keys.map(key => ({
    field: auditFieldLabels[key] || key.replaceAll('_', ' '),
    oldValue: oldValues[key],
    newValue: newValues[key],
  })).filter(pair => String(pair.oldValue ?? '') !== String(pair.newValue ?? ''))
}

function formatAuditDate(value?: string) {
  return formatIndiaDateTime(value)
}

function changedThisMonth(value?: string) {
  return isCurrentIndiaMonth(value)
}

export function AssetsPage() {
  const { user } = useAuth()
  const canEdit = Boolean(user && (isFullAccessRole(user.role) || user.role === 'it'))
  const navigate = useNavigate()
  const location = useLocation()
  const { selectedMonth, presentMonth, returnToPresent } = useITMonthUrl()
  const [assets, setAssets] = useState<Asset[]>([])
  const [months, setMonths] = useState<ReportMonth[]>([])
  const [selected, setSelected] = useState<Asset | null>(null)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [device, setDevice] = useState('')
  const [assignmentOpen, setAssignmentOpen] = useState(false)
  const [returnOpen, setReturnOpen] = useState(false)
  const [assignment, setAssignment] = useState({ used_by: '', department: '', workstation_no: '', location: 'Head Office', work_mode: 'office', assigned_date: new Date().toISOString().slice(0, 10), remarks: '' })
  const [returnForm, setReturnForm] = useState({ final_status: 'available', return_date: new Date().toISOString().slice(0, 10), condition: 'working', all_components_returned: true, remarks: '' })
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const monthInfo = months.find(item => item.key === selectedMonth)
  const historicalReporting = selectedMonth !== presentMonth

  async function loadMonths() {
    try { setMonths(await apiFetch<ReportMonth[]>('/reports/months')) }
    catch (err) { setError(err instanceof Error ? err.message : 'Unable to load months') }
  }

  async function load(openAssetId?: number) {
    setError('')
    const params = new URLSearchParams()
    if (search.trim()) params.set('search', search.trim())
    if (status) params.set('status', status)
    if (device) params.set('device_type', device)
    params.set('limit', '1000')
    try {
      const data = await apiFetch<Asset[]>(`/assets?${params.toString()}`)
      setAssets(data)
      if (openAssetId) await openAsset(openAssetId)
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to load assets') }
  }

  useEffect(() => { void loadMonths() }, [])
  useEffect(() => { setSelected(null); void load() }, [status, device, selectedMonth])
  useEffect(() => {
    const state = location.state as { message?: string; openAssetId?: number } | null
    if (!state) return
    if (state.message) setMessage(state.message)
    if (state.openAssetId) void load(state.openAssetId)
    navigate(`${location.pathname}${location.search}`, { replace: true, state: null })
  }, [location.state])

  const departments = useMemo(() => Array.from(new Set(assets.map(asset => asset.department).filter(Boolean))).sort(), [assets])

  async function openAsset(id: number) {
    try { setSelected(await apiFetch<Asset>(`/assets/${id}`)) }
    catch (err) { setError(err instanceof Error ? err.message : 'Unable to open asset') }
  }

  async function assignAsset(event: FormEvent) {
    event.preventDefault()
    if (!selected) return
    setBusy(true); setError(''); setMessage('')
    try {
      const updated = await apiFetch<Asset>(`/assets/${selected.id}/assign`, { method: 'POST', body: JSON.stringify({ ...assignment, reporting_month: selectedMonth }) })
      setAssignmentOpen(false)
      setMessage(`${updated.cpu_asset_tag || updated.asset_code} assigned to ${updated.used_by} at ${updated.workstation_no || 'workstation not recorded'}.`)
      await load(); await openAsset(updated.id)
    } catch (err) { setError(err instanceof Error ? err.message : 'Assignment failed') }
    finally { setBusy(false) }
  }

  async function returnAsset(event: FormEvent) {
    event.preventDefault()
    if (!selected) return
    setBusy(true); setError(''); setMessage('')
    try {
      const updated = await apiFetch<Asset>(`/assets/${selected.id}/return`, { method: 'POST', body: JSON.stringify({ ...returnForm, reporting_month: selectedMonth }) })
      setReturnOpen(false)
      setMessage(`${updated.cpu_asset_tag || updated.asset_code} returned. Current status: ${updated.status.replaceAll('_', ' ')}.`)
      await load(); await openAsset(updated.id)
    } catch (err) { setError(err instanceof Error ? err.message : 'Return failed') }
    finally { setBusy(false) }
  }

  async function archiveAsset() {
    if (!selected || !window.confirm(`Retire CPU / Asset Tag ${selected.cpu_asset_tag || selected.asset_code}? The record and history will remain available.`)) return
    try {
      const updated = await apiFetch<Asset>(`/assets/${selected.id}/archive?reporting_month=${encodeURIComponent(selectedMonth)}`, { method: 'PATCH' })
      setMessage(`${updated.cpu_asset_tag || updated.asset_code} retired and preserved in history.`); await load(); await openAsset(updated.id)
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to retire asset') }
  }

  async function deleteTestAsset() {
    if (!selected || !window.confirm(`Permanently delete QA test asset ${selected.cpu_asset_tag || selected.asset_code}? This cannot be undone.`)) return
    try {
      await apiFetch<void>(`/assets/${selected.id}`, { method: 'DELETE' })
      setMessage(`${selected.cpu_asset_tag || selected.asset_code} test record deleted.`); setSelected(null); await load()
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to delete test asset') }
  }

  function openAssignment() {
    if (!selected) return
    setAssignment({
      used_by: selected.used_by || '', department: selected.department || '', workstation_no: selected.workstation_no || '',
      location: selected.location || 'Head Office', work_mode: selected.work_mode || 'office',
      assigned_date: new Date().toISOString().slice(0, 10), remarks: '',
    })
    setAssignmentOpen(true)
  }

  return (
    <>
      <DashboardHeader
        eyebrow="IT INVENTORY"
        title={`Asset Register${monthInfo ? ` — ${monthInfo.label}` : ''}`}
        description={`This is the live Asset Register. New edits are assigned to ${monthInfo?.label || selectedMonth}; the actual system date and time are also preserved separately.`}
        actions={<>
          {historicalReporting && <button className="secondary-button" onClick={returnToPresent}><RotateCcw size={17} /> Return to Present</button>}
          {canEdit && <button className="primary-button" onClick={() => navigate(withITMonth('/assets/new', selectedMonth))}><Plus size={17} /> Add IT Asset</button>}
        </>}
      />
      {monthInfo && <div className={`register-month-banner ${historicalReporting ? 'historical' : 'live'}`}><CalendarDays size={18} /><strong>Reporting activity to {monthInfo.label}</strong><span>Live asset values remain current; remarks stay only on the saved activity unless the Asset Master Remarks field itself is edited.</span></div>}
      {message && <div className="success-message">{message}</div>}
      {error && <div className="error-message">{error}</div>}

      <section className="panel filter-panel">
        <form onSubmit={event => { event.preventDefault(); void load() }} className="asset-filters">
          <div className="search-shell"><Search size={18} /><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search CPU / Asset Tag, workstation, employee, monitor, mouse, keyboard, system, IP or MAC..." /></div>
          <select value={device} onChange={event => setDevice(event.target.value)}><option value="">All device types</option><option>Computer</option><option>Laptop</option><option>Smartphone</option><option>Printer</option><option>Server</option><option>Network Device</option><option>Other</option></select>
          <select value={status} onChange={event => setStatus(event.target.value)}><option value="">All statuses</option>{statusOptions.map(item => <option key={item} value={item}>{item.replaceAll('_', ' ')}</option>)}</select>
          <button className="secondary-button"><Filter size={17} /> Apply</button>
        </form>
        <div className="filter-summary"><strong>{assets.length}</strong> matching records <span>·</span> {departments.length} departments</div>
      </section>

      <section className={`asset-register-layout ${selected ? 'with-detail' : ''}`}>
        <article className="panel asset-table-panel">
          <div className="table-wrap">
            <table className="asset-table">
              <thead><tr><th>CPU / Asset Tag</th><th>Workstation</th><th>Used By</th><th>Department</th><th>Device</th><th>System Name</th><th>Location</th><th>Status</th><th>Last Change</th><th /></tr></thead>
              <tbody>{assets.map(asset => <tr key={`${asset.id}-${asset.asset_code}`} onClick={() => void openAsset(asset.id)}><td><strong>{asset.cpu_asset_tag || 'Not recorded'}</strong><small>Internal: {asset.asset_code}</small></td><td><strong>{asset.workstation_no || '—'}</strong></td><td>{asset.used_by || <span className="muted">Unassigned</span>}</td><td>{asset.department || '—'}</td><td>{asset.device_type}</td><td>{asset.system_name || '—'}</td><td>{asset.location || '—'}</td><td><span className={`status ${asset.status}`}>{asset.status.replaceAll('_', ' ')}</span></td><td className="asset-last-change">{asset.last_change_at ? <><strong>{formatAuditDate(asset.last_change_at)}</strong><small>{asset.last_changed_by || 'System'}{changedThisMonth(asset.last_change_at) ? ' · Updated this month' : ''}</small></> : <span className="muted">No system edit</span>}</td><td><ChevronRight size={17} /></td></tr>)}</tbody>
            </table>
          </div>
        </article>

        {selected && <aside className="asset-detail panel">
          <button className="icon-button close-detail" onClick={() => setSelected(null)}><X size={19} /></button>
          <span className="section-kicker">CURRENT LIVE SYSTEM PROFILE</span><h2>{selected.cpu_asset_tag || selected.asset_code}</h2><p>Workstation: <strong>{selected.workstation_no || 'Not recorded'}</strong> · Internal reference: {selected.asset_code}</p>
          <div className="asset-detail-status"><span className={`status ${selected.status}`}>{selected.status.replaceAll('_', ' ')}</span><small>{selected.last_change_at ? `Last changed ${formatAuditDate(selected.last_change_at)} by ${selected.last_changed_by || 'System'}` : `Record updated ${formatAuditDate(selected.updated_at)}`}</small></div>
          {selected.last_change_at && <section className="asset-audit-summary">
            <div><strong>{selected.last_field_count || 1}</strong><span>field{selected.last_field_count === 1 ? '' : 's'} in last change</span></div>
            <p><b>{selected.last_change_type?.replaceAll('_', ' ') || 'Asset change'}</b>{selected.last_change_reason ? ` · ${selected.last_change_reason}` : ''}</p>
            <small>{selected.last_changed_by || 'System'} · {(selected.last_changed_by_role || '').replaceAll('_', ' ') || 'Role not recorded'} · {formatAuditDate(selected.last_change_at)}</small>
          </section>}
          {canEdit && <div className="asset-action-grid">
            <button className="secondary-button" onClick={() => navigate(withITMonth(`/assets/${selected.id}/edit`, selectedMonth))}><Pencil size={15} /> Edit Full Record</button>
            <button className="secondary-button" onClick={openAssignment}><ArrowRightLeft size={15} /> Assign / Transfer</button>
            <button className="secondary-button" onClick={() => navigate(withITMonth(`/work?mode=component&asset=${selected.id}`, selectedMonth))}><Repeat2 size={15} /> Change Component</button>
            <button className="secondary-button" onClick={() => setReturnOpen(true)} disabled={!selected.used_by}><RotateCcw size={15} /> Return</button>
            <button className="secondary-button" onClick={() => void archiveAsset()}><Archive size={15} /> Retire</button>
            {selected.can_delete_test_record && <button className="danger-button full-action" onClick={() => void deleteTestAsset()}><Trash2 size={15} /> Delete QA Test Record</button>}
          </div>}

          <h3>Current active details</h3>
          <dl className="details-list asset-details-complete">
            <div><dt>CPU / Asset Tag</dt><dd>{selected.cpu_asset_tag || '—'}</dd></div><div><dt>Workstation</dt><dd>{selected.workstation_no || '—'}</dd></div>
            <div><dt>Employee</dt><dd>{selected.used_by || 'Unassigned'}</dd></div><div><dt>Department</dt><dd>{selected.department || '—'}</dd></div>
            <div><dt>Monitor tags</dt><dd>{selected.monitor_asset_tags || '—'}</dd></div><div><dt>Mouse tag</dt><dd>{selected.mouse_asset_tag || '—'}</dd></div>
            <div><dt>Keyboard tag</dt><dd>{selected.keyboard_asset_tag || '—'}</dd></div><div><dt>Processor</dt><dd>{selected.processor || '—'}</dd></div>
            <div><dt>Memory</dt><dd>{selected.memory_gb || '—'}</dd></div><div><dt>SSD</dt><dd>{selected.ssd || '—'}</dd></div>
            <div><dt>HDD</dt><dd>{selected.hdd || '—'}</dd></div><div><dt>Graphics card</dt><dd>{selected.graphics_card || '—'}</dd></div>
            <div><dt>Network</dt><dd>{selected.network_type || '—'}</dd></div><div><dt>IP address</dt><dd>{selected.ip_address || '—'}</dd></div>
            <div><dt>MAC address</dt><dd>{selected.mac_address || '—'}</dd></div><div><dt>Operating system</dt><dd>{selected.operating_system || '—'}</dd></div>
            <div><dt>Antivirus</dt><dd>{selected.antivirus || '—'}</dd></div><div><dt>Location</dt><dd>{selected.location || '—'}</dd></div>
            <div><dt>Price</dt><dd>{selected.price === undefined || selected.price === null ? '—' : `₹${selected.price.toLocaleString('en-IN')}`}</dd></div><div><dt>Approved by</dt><dd>{selected.approved_by || 'Pending / not recorded'}</dd></div>
            <div><dt>Performed by</dt><dd>{selected.performed_by || '—'}</dd></div><div><dt>Asset Master Remarks</dt><dd>{selected.remarks || '—'}</dd></div>
            <div><dt>Original asset date</dt><dd>{selected.original_asset_date || selected.asset_date || '—'}</dd></div><div><dt>Last successful change</dt><dd>{selected.last_change_at ? formatAuditDate(selected.last_change_at) : 'No system edit recorded'}</dd></div>
          </dl>

          <><h3>Component and configuration changes</h3>
          <div className="linked-records">{selected.component_replacements?.length ? selected.component_replacements.map(record => <div key={record.id}><strong>{record.replacement_code} · {record.change_type.replaceAll('_', ' ')} · {record.component_type}</strong><span>{record.old_value || 'Not Previously Recorded'} → {record.new_value}</span><small>{record.workstation_no || 'No workstation'} · {record.work_code || 'No work code'} · {formatAuditDate(record.created_at)} · {record.performed_by || 'System'}</small><em>{record.reason}</em></div>) : <div className="empty-state">No component or configuration change recorded yet.</div>}</div>

          <h3>Linked work records</h3>
          <div className="linked-records">{selected.work_records?.length ? selected.work_records.map(work => <div key={work.id}><strong>{work.work_code}</strong><span>{work.title}</span><small>{work.status.replaceAll('_', ' ')} · {new Date(work.created_at).toLocaleDateString()}</small></div>) : <div className="empty-state">No work record linked to this asset.</div>}</div>

          <h3>Asset timeline</h3>
          <div className="timeline">{selected.history?.length ? selected.history.map((item, index) => {
            const pairs = auditPairs(item)
            return <div key={`${item.batch_code || index}-${item.created_at}`}><i /><p><strong>{item.action}{item.field_count ? ` · ${item.field_count} field${item.field_count === 1 ? '' : 's'}` : ''}</strong><span>{item.reason || item.remarks || 'No reason recorded'}</span>{pairs.length > 0 && <ul className="audit-pair-list">{pairs.map(pair => <li key={pair.field}><b>{pair.field}</b><code>{String(pair.oldValue ?? '—')}</code><span>→</span><code>{String(pair.newValue ?? '—')}</code></li>)}</ul>}<small>Effective {item.reporting_month || selectedMonth} · Recorded {formatAuditDate(item.created_at)} · {item.changed_by_name || item.changed_by || 'System'} · {(item.changed_by_role || '').replaceAll('_', ' ') || 'Role not recorded'}{item.batch_code ? ` · ${item.batch_code}` : ''}</small></p></div>
          }) : <div className="empty-state">No manual change history yet. Imported from {selected.source_sheet || 'manual entry'}.</div>}</div></>
        </aside>}
      </section>

      {assignmentOpen && selected && <div className="modal-backdrop"><section className="modal-card workflow-modal"><button className="icon-button modal-close" onClick={() => setAssignmentOpen(false)}><X /></button><div className="modal-heading"><ArrowRightLeft /><div><span className="section-kicker">CONTROLLED ASSIGNMENT</span><h2>{selected.cpu_asset_tag || selected.asset_code} / {selected.workstation_no || 'No workstation'}</h2></div></div>{error && <div className="error-message modal-error">{error}</div>}<form className="data-form form-grid" onSubmit={assignAsset}>
        <label>Used By<input required value={assignment.used_by} onChange={e => setAssignment({ ...assignment, used_by: e.target.value })} /></label>
        <label>Department<input required value={assignment.department} onChange={e => setAssignment({ ...assignment, department: e.target.value })} /></label>
        <label>Workstation No.<input required value={assignment.workstation_no} onChange={e => setAssignment({ ...assignment, workstation_no: e.target.value })} /></label>
        <label>Location<input value={assignment.location} onChange={e => setAssignment({ ...assignment, location: e.target.value })} /></label>
        <label>Work Mode<select value={assignment.work_mode} onChange={e => setAssignment({ ...assignment, work_mode: e.target.value })}><option value="office">Office</option><option value="wfh">Work From Home</option><option value="field">Field</option></select></label>
        <label>Assignment Date<input type="date" value={assignment.assigned_date} onChange={e => setAssignment({ ...assignment, assigned_date: e.target.value })} /></label>
        <label className="full-span">Assignment Activity Remarks — Selected Month Only<textarea rows={3} value={assignment.remarks} onChange={e => setAssignment({ ...assignment, remarks: e.target.value })} /></label>
        <button className="primary-button full-span" disabled={busy}><Save size={17} /> {busy ? 'Assigning...' : 'Confirm Assignment'}</button>
      </form></section></div>}

      {returnOpen && selected && <div className="modal-backdrop"><section className="modal-card workflow-modal"><button className="icon-button modal-close" onClick={() => setReturnOpen(false)}><X /></button><div className="modal-heading"><RotateCcw /><div><span className="section-kicker">ASSET RETURN</span><h2>{selected.cpu_asset_tag || selected.asset_code} / {selected.workstation_no || 'No workstation'}</h2></div></div>{error && <div className="error-message modal-error">{error}</div>}<form className="data-form form-grid" onSubmit={returnAsset}>
        <label>Final Status<select value={returnForm.final_status} onChange={e => setReturnForm({ ...returnForm, final_status: e.target.value })}><option value="available">Available after inspection</option><option value="repair">Under repair</option><option value="damaged">Damaged</option><option value="returned">Returned, awaiting inspection</option></select></label>
        <label>Return Date<input type="date" value={returnForm.return_date} onChange={e => setReturnForm({ ...returnForm, return_date: e.target.value })} /></label>
        <label>Condition<select value={returnForm.condition} onChange={e => setReturnForm({ ...returnForm, condition: e.target.value })}><option value="working">Working</option><option value="minor_damage">Minor damage</option><option value="not_working">Not working</option><option value="destroyed">Destroyed</option></select></label>
        <label className="checkbox-label"><input type="checkbox" checked={returnForm.all_components_returned} onChange={e => setReturnForm({ ...returnForm, all_components_returned: e.target.checked })} /> All components returned</label>
        <label className="full-span">Return Activity Remarks — Selected Month Only<textarea rows={3} value={returnForm.remarks} onChange={e => setReturnForm({ ...returnForm, remarks: e.target.value })} /></label>
        <button className="primary-button full-span" disabled={busy}><Save size={17} /> {busy ? 'Saving...' : 'Complete Return'}</button>
      </form></section></div>}
    </>
  )
}
