import { Download, Monitor, PackageCheck, RotateCcw, Save } from 'lucide-react'
import { FormEvent, useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../components/DashboardHeader'
import { useAuth } from '../context/AuthContext'
import { useITMonthUrl } from '../context/ITMonthContext'
import { apiFetch, downloadFile } from '../lib/api'
import { formatIndiaDateTime } from '../lib/date'
import type { Asset } from '../types'

interface SpareMonitorRecord {
  id: number
  monitor_tag: string
  source_return_id: number
  source_asset_code: string
  status: string
  current_asset_id?: number | null
  current_asset_code?: string | null
  current_cpu_asset_tag?: string | null
  location: string
  retained_date: string
  assigned_at?: string | null
  assigned_by_name?: string | null
  remarks?: string | null
}

interface VendorReturnRecord {
  id: number
  return_code: string
  asset_id: number
  asset_code: string
  cpu_asset_tag?: string | null
  device_type: string
  return_mode: 'complete_return' | 'return_without_monitor'
  return_date: string
  vendor_name: string
  return_reference?: string | null
  condition?: string | null
  reason: string
  remarks?: string | null
  reporting_month?: string | null
  previous_status?: string | null
  previous_used_by?: string | null
  previous_department?: string | null
  previous_workstation_no?: string | null
  monitor_tags?: string | null
  retained_monitor_tags?: string | null
  performed_by: string
  performed_by_email: string
  performed_by_role: string
  created_at: string
  spare_monitors: SpareMonitorRecord[]
}

function pretty(value?: string | null) {
  return (value || 'Not recorded').replaceAll('_', ' ').replace(/\b\w/g, character => character.toUpperCase())
}

export function RentalAssetReturnsPage() {
  const { user } = useAuth()
  const { selectedMonth } = useITMonthUrl()
  const canReturn = user?.role === 'it' || user?.role === 'admin'
  const [assets, setAssets] = useState<Asset[]>([])
  const [returns, setReturns] = useState<VendorReturnRecord[]>([])
  const [spares, setSpares] = useState<SpareMonitorRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [form, setForm] = useState({
    asset_id: '',
    return_mode: 'complete_return' as 'complete_return' | 'return_without_monitor',
    return_date: new Date().toISOString().slice(0, 10),
    vendor_name: '',
    return_reference: '',
    condition: 'Good / working',
    reason: 'Rental period completed',
    remarks: '',
    spare_location: 'IT Store',
  })

  const selectedAsset = useMemo(
    () => assets.find(asset => asset.id === Number(form.asset_id)),
    [assets, form.asset_id],
  )

  async function load() {
    setLoading(true)
    setError('')
    try {
      const [assetRows, returnRows, spareRows] = await Promise.all([
        apiFetch<Asset[]>('/assets?device_type=Computer&limit=2000'),
        apiFetch<VendorReturnRecord[]>('/asset-vendor-returns'),
        apiFetch<SpareMonitorRecord[]>('/spare-monitors'),
      ])
      setAssets(assetRows)
      setReturns(returnRows)
      setSpares(spareRows)
      if (form.asset_id && !assetRows.some(asset => asset.id === Number(form.asset_id))) {
        setForm(current => ({ ...current, asset_id: '' }))
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load rental return data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!canReturn) return
    setMessage('')
    setError('')
    setBusy(true)
    try {
      if (!form.asset_id) throw new Error('Select the rental Desktop / Computer to return.')
      if (selectedAsset?.used_by) {
        throw new Error('This desktop is still assigned. Complete Handover & Return to IT before vendor return.')
      }
      if (form.return_mode === 'return_without_monitor' && !selectedAsset?.monitor_asset_tags?.trim()) {
        throw new Error('Return Without Monitor requires a Monitor Asset Tag on the selected desktop.')
      }
      const created = await apiFetch<VendorReturnRecord>(`/assets/${form.asset_id}/vendor-return`, {
        method: 'POST',
        body: JSON.stringify({
          return_mode: form.return_mode,
          return_date: form.return_date,
          vendor_name: form.vendor_name,
          return_reference: form.return_reference || null,
          condition: form.condition || null,
          reason: form.reason,
          remarks: form.remarks || null,
          reporting_month: selectedMonth,
          spare_location: form.return_mode === 'return_without_monitor' ? form.spare_location : null,
        }),
      })
      const retained = created.retained_monitor_tags ? ` Retained monitor(s): ${created.retained_monitor_tags}.` : ''
      setMessage(`${created.return_code} recorded. ${created.cpu_asset_tag || created.asset_code} is removed from active inventory.${retained}`)
      setForm(current => ({
        ...current,
        asset_id: '',
        return_mode: 'complete_return',
        vendor_name: '',
        return_reference: '',
        condition: 'Good / working',
        reason: 'Rental period completed',
        remarks: '',
        spare_location: 'IT Store',
      }))
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to record vendor return')
    } finally {
      setBusy(false)
    }
  }

  async function exportReturns() {
    setError('')
    try {
      await downloadFile('/reports/returned-assets.xlsx', 'NakshaTech Returned Rental Assets.xlsx')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to download Returned Asset Register')
    }
  }

  return (
    <>
      <DashboardHeader
        eyebrow="RENTAL ASSET CONTROL"
        title="Rental Returns & Spare Monitors"
        description="Remove returned rental desktops from active inventory without destroying audit history. Retained monitors remain available to IT for future component replacement."
        actions={<button className="secondary-button" onClick={() => void exportReturns()}><Download size={17} /> Returned Assets Excel</button>}
      />
      {message && <div className="success-message">{message}</div>}
      {error && <div className="error-message">{error}</div>}

      <section className="dashboard-grid work-layout">
        <article className="panel work-form-panel">
          <div className="panel-heading"><div><span className="section-kicker">VENDOR RETURN</span><h2>Return / Remove Rental Desktop</h2></div><RotateCcw /></div>
          {!canReturn && <div className="approval-note">Management has read-only visibility. IT/Admin records the physical vendor return.</div>}
          {canReturn && <form className="data-form form-grid" onSubmit={submit}>
            <label className="full-span">Desktop / Computer<select required value={form.asset_id} onChange={event => setForm({ ...form, asset_id: event.target.value })}><option value="">Select active desktop</option>{assets.map(asset => <option key={asset.id} value={asset.id}>{asset.cpu_asset_tag || asset.asset_code} · {asset.workstation_no || 'No workstation'} · {asset.used_by || 'Unassigned'} · Monitor {asset.monitor_asset_tags || 'not recorded'}</option>)}</select></label>

            {selectedAsset && <div className="selected-system-card full-span">
              <div><strong>{selectedAsset.cpu_asset_tag || selectedAsset.asset_code}</strong><span>{selectedAsset.asset_code} · {selectedAsset.department || 'No department'} · {pretty(selectedAsset.status)}</span></div>
              <div><strong>Monitor: {selectedAsset.monitor_asset_tags || 'Not recorded'}</strong><span>{selectedAsset.used_by ? `Currently assigned to ${selectedAsset.used_by}` : 'Currently in IT / unassigned custody'}</span></div>
            </div>}

            {selectedAsset?.used_by && <div className="error-message full-span">This desktop is still assigned to {selectedAsset.used_by}. Complete the normal Handover & Return first; vendor return is blocked until IT has custody.</div>}

            <label>Return Type<select value={form.return_mode} onChange={event => setForm({ ...form, return_mode: event.target.value as typeof form.return_mode })}><option value="complete_return">Complete Return — Desktop + Monitor</option><option value="return_without_monitor">Return Desktop Without Monitor — Monitor stays with NakshaTech</option></select></label>
            <label>Return Date<input required type="date" value={form.return_date} onChange={event => setForm({ ...form, return_date: event.target.value })} /></label>
            <label>Vendor / Rental Company<input required value={form.vendor_name} onChange={event => setForm({ ...form, vendor_name: event.target.value })} placeholder="Rental vendor name" /></label>
            <label>Return Reference / DC No.<input value={form.return_reference} onChange={event => setForm({ ...form, return_reference: event.target.value })} placeholder="Optional reference" /></label>
            <label>Condition at Return<input value={form.condition} onChange={event => setForm({ ...form, condition: event.target.value })} /></label>
            {form.return_mode === 'return_without_monitor' && <label>Retained Monitor Location<input required value={form.spare_location} onChange={event => setForm({ ...form, spare_location: event.target.value })} /></label>}
            <label className="full-span">Reason<textarea required rows={2} value={form.reason} onChange={event => setForm({ ...form, reason: event.target.value })} /></label>
            <label className="full-span">Remarks<textarea rows={2} value={form.remarks} onChange={event => setForm({ ...form, remarks: event.target.value })} placeholder="Return condition, vendor acknowledgement or other audit note" /></label>

            {form.return_mode === 'complete_return'
              ? <div className="form-guidance full-span">Complete Return removes the desktop from active inventory. The CPU/Desktop and its monitor tag(s) remain only in immutable return/audit history.</div>
              : <div className="form-guidance full-span">Return Without Monitor removes the desktop from active inventory and moves its monitor tag(s) into the Available Spare Monitor pool for later Component Changes.</div>}

            <button className="primary-button full-span" disabled={busy || Boolean(selectedAsset?.used_by)}><Save size={17} /> {busy ? 'Recording…' : 'Confirm Vendor Return'}</button>
          </form>}
        </article>

        <article className="panel work-record-panel">
          <div className="panel-heading"><div><span className="section-kicker">SPARE COMPONENT POOL</span><h2>Retained Monitors</h2></div><Monitor /></div>
          <div className="record-list detailed-records">
            {spares.map(spare => <article key={spare.id}>
              <div className="record-top"><div><strong>{spare.monitor_tag}</strong><span>From {spare.source_asset_code}</span></div><span className={`status ${spare.status}`}>{pretty(spare.status)}</span></div>
              <p>{spare.status === 'in_use' ? `Installed on ${spare.current_cpu_asset_tag || spare.current_asset_code || 'another desktop'}` : `Stored at ${spare.location}`}</p>
              <div className="record-meta"><span>Retained {spare.retained_date}</span>{spare.assigned_by_name && <span>Last handled by {spare.assigned_by_name}</span>}<span>{spare.remarks || 'No additional remarks'}</span></div>
            </article>)}
            {!spares.length && <div className="empty-state"><Monitor size={26} /><strong>No retained monitors</strong><span>Return Without Monitor will add the retained monitor here automatically.</span></div>}
          </div>
        </article>
      </section>

      <section className="panel">
        <div className="panel-heading"><div><span className="section-kicker">IMMUTABLE REGISTER</span><h2>Returned Rental Assets</h2></div><PackageCheck /></div>
        {loading ? <div className="empty-state">Loading returned assets…</div> : <div className="record-list detailed-records">
          {returns.map(record => <article key={record.id}>
            <div className="record-top"><div><strong>{record.return_code} · {record.cpu_asset_tag || record.asset_code}</strong><span>{record.vendor_name} · {record.return_date}</span></div><span className="status completed">{pretty(record.return_mode)}</span></div>
            <h3>{record.asset_code} · {record.device_type}</h3>
            <p>{record.reason}</p>
            <div className="record-meta"><span>Previous: {record.previous_used_by || 'Unassigned'} · {record.previous_department || 'No department'} · {record.previous_workstation_no || 'No workstation'}</span><span>Monitor before return: {record.monitor_tags || 'Not recorded'}</span>{record.retained_monitor_tags && <span>Retained: {record.retained_monitor_tags}</span>}<span>Recorded by {record.performed_by}</span><span>{formatIndiaDateTime(record.created_at)}</span></div>
          </article>)}
          {!returns.length && <div className="empty-state"><PackageCheck size={26} /><strong>No vendor returns recorded</strong><span>Completed rental returns will remain here even after the desktop disappears from active inventory.</span></div>}
        </div>}
      </section>
    </>
  )
}
