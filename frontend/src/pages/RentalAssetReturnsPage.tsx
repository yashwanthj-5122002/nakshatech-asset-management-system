import {
  CheckCircle2,
  Download,
  Monitor,
  PackageCheck,
  PackageOpen,
  RotateCcw,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../components/DashboardHeader'
import { StatCard } from '../components/StatCard'
import { apiFetch, downloadFile } from '../lib/api'
import { formatIndiaDateTime } from '../lib/date'

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

function returnModeLabel(mode: VendorReturnRecord['return_mode']) {
  return mode === 'complete_return'
    ? 'Complete Return — Desktop + Monitor'
    : 'Desktop Returned — Monitor Retained'
}

function displayDate(value?: string | null) {
  if (!value) return 'Not recorded'
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  return match ? `${match[3]}/${match[2]}/${match[1]}` : value
}

export function RentalAssetReturnsPage() {
  const [returns, setReturns] = useState<VendorReturnRecord[]>([])
  const [spares, setSpares] = useState<SpareMonitorRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true)
    setError('')
    try {
      const [returnRows, spareRows] = await Promise.all([
        apiFetch<VendorReturnRecord[]>('/asset-vendor-returns'),
        apiFetch<SpareMonitorRecord[]>('/spare-monitors'),
      ])
      setReturns(returnRows)
      setSpares(spareRows)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load returned asset data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  const summary = useMemo(() => ({
    returned: returns.length,
    complete: returns.filter(record => record.return_mode === 'complete_return').length,
    monitorRetained: returns.filter(record => record.return_mode === 'return_without_monitor').length,
    spares: spares.length,
    available: spares.filter(spare => spare.status === 'available').length,
    inUse: spares.filter(spare => spare.status === 'in_use').length,
  }), [returns, spares])

  async function exportReturns() {
    setError('')
    try {
      await downloadFile('/reports/returned-assets.xlsx', 'NakshaTech Returned Assets and Spare Monitors.xlsx')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to download Returned Assets and Spare Monitors Excel')
    }
  }

  return (
    <>
      <DashboardHeader
        eyebrow="ASSET RETURN REGISTER"
        title="Returned Assets & Spare Monitors"
        description="Read-only visualization of computers removed through Asset Register → Return / Remove and monitors retained for reuse through Component Changes. Return actions remain in Asset Register only."
        actions={<button className="secondary-button" onClick={() => void exportReturns()}><Download size={17} /> Returned Assets & Spares Excel</button>}
      />
      {error && <div className="error-message">{error}</div>}

      <section className="stats-grid" aria-label="Returned asset and spare monitor summaries">
        <StatCard icon={PackageCheck} label="Returned Assets" value={summary.returned} tone="navy" note="Removed from active IT inventory" />
        <StatCard icon={RotateCcw} label="Complete Returns" value={summary.complete} tone="blue" note="Desktop and monitor returned" />
        <StatCard icon={Monitor} label="Monitor Retained" value={summary.monitorRetained} tone="cyan" note="Desktop returned, monitor kept" />
        <StatCard icon={Monitor} label="Spare Monitors" value={summary.spares} tone="purple" note="Current retained monitor register" />
        <StatCard icon={PackageOpen} label="Available Spares" value={summary.available} tone="teal" note="Ready for Component Changes" />
        <StatCard icon={CheckCircle2} label="Monitors In Use" value={summary.inUse} tone="green" note="Reused through Component Changes" />
      </section>

      <section className="dashboard-grid two-column">
        <article className="panel">
          <div className="panel-heading">
            <div>
              <span className="section-kicker">IMMUTABLE RETURN HISTORY</span>
              <h2>Returned Assets</h2>
              <small className="panel-helper">This register is populated only by Asset Register → Return / Remove.</small>
            </div>
            <PackageCheck />
          </div>
          {loading ? <div className="empty-state">Loading returned assets…</div> : <div className="record-list detailed-records">
            {returns.map(record => <article key={record.id}>
              <div className="record-top">
                <div>
                  <strong>{record.cpu_asset_tag || record.asset_code}</strong>
                  <span>{record.return_code} · Returned {displayDate(record.return_date)}</span>
                </div>
                <span className="status completed">Returned / Removed</span>
              </div>
              <h3>{returnModeLabel(record.return_mode)}</h3>
              <p>{record.remarks || record.reason || 'No return remarks recorded.'}</p>
              <div className="record-meta">
                <span>Asset ID: {record.asset_code}</span>
                <span>Previous user: {record.previous_used_by || 'Unassigned'}</span>
                <span>Previous department: {record.previous_department || 'Not recorded'}</span>
                <span>Previous workstation: {record.previous_workstation_no || 'Not recorded'}</span>
                <span>Monitor before return: {record.monitor_tags || 'Not recorded'}</span>
                {record.retained_monitor_tags && <span>Retained monitor: {record.retained_monitor_tags}</span>}
                {record.vendor_name && <span>Vendor / return source: {record.vendor_name}</span>}
                {record.return_reference && <span>Reference / DC: {record.return_reference}</span>}
                <span>Recorded by {record.performed_by} · {formatIndiaDateTime(record.created_at)}</span>
              </div>
            </article>)}
            {!returns.length && <div className="empty-state"><PackageCheck size={26} /><strong>No returned assets yet</strong><span>Assets removed through Asset Register → Return / Remove will appear here automatically.</span></div>}
          </div>}
        </article>

        <article className="panel">
          <div className="panel-heading">
            <div>
              <span className="section-kicker">SPARE COMPONENT REGISTER</span>
              <h2>Spare Monitors</h2>
              <small className="panel-helper">Retained monitors are reused only through Component Changes.</small>
            </div>
            <Monitor />
          </div>
          {loading ? <div className="empty-state">Loading spare monitors…</div> : <div className="record-list detailed-records">
            {spares.map(spare => <article key={spare.id}>
              <div className="record-top">
                <div>
                  <strong>{spare.monitor_tag}</strong>
                  <span>Source asset {spare.source_asset_code} · Retained {displayDate(spare.retained_date)}</span>
                </div>
                <span className={`status ${spare.status}`}>{pretty(spare.status)}</span>
              </div>
              <h3>{spare.status === 'in_use'
                ? `Installed on ${spare.current_cpu_asset_tag || spare.current_asset_code || 'another desktop'}`
                : `Stored at ${spare.location || 'IT Store'}`}</h3>
              <p>{spare.remarks || 'No additional remarks recorded.'}</p>
              <div className="record-meta">
                <span>Source return ID: {spare.source_return_id}</span>
                <span>Status: {pretty(spare.status)}</span>
                {spare.current_asset_code && <span>Current asset: {spare.current_cpu_asset_tag || spare.current_asset_code}</span>}
                {spare.assigned_at && <span>Installed / assigned: {formatIndiaDateTime(spare.assigned_at)}</span>}
                {spare.assigned_by_name && <span>Last handled by {spare.assigned_by_name}</span>}
              </div>
            </article>)}
            {!spares.length && <div className="empty-state"><Monitor size={26} /><strong>No spare monitors yet</strong><span>Choosing “Return Desktop — Keep Monitor” in Asset Register will add the retained monitor here automatically.</span></div>}
          </div>}
        </article>
      </section>
    </>
  )
}
