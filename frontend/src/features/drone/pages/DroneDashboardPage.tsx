import { AlertTriangle, ArrowRightLeft, BatteryCharging, Boxes, ClipboardCheck, Clock3, FolderKanban, HardDrive, MapPin, PlaneTakeoff, RefreshCw, Wrench } from 'lucide-react'
import { DroneIcon as Drone } from '../../../components/DroneIcon'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { DonutChart, HorizontalBars } from '../../../components/Charts'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { DroneMap } from '../../../components/DroneMap'
import { StatCard } from '../../../components/StatCard'
import { apiFetch } from '../../../lib/api'
import type { DroneDashboardData } from '../../../types'

export function DroneDashboardPage() {
  const [data, setData] = useState<DroneDashboardData | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    setError('')
    try { setData(await apiFetch<DroneDashboardData>('/drone/dashboard')) }
    catch (err) { setError(err instanceof Error ? err.message : 'Unable to load Drone dashboard') }
    finally { setLoading(false) }
  }

  useEffect(() => { void load() }, [])
  const mapped = useMemo(() => data?.telemetry.find(item => item.latest_location), [data])

  if (loading) return <div className="loading-state">Loading Drone and Survey operations…</div>
  if (!data) return <div className="error-message">{error || 'Drone dashboard is unavailable.'}</div>

  return (
    <>
      <DashboardHeader
        eyebrow="DRONE & SURVEY OPERATIONS"
        title="Drone Asset Management"
        description="Permanent equipment master, Trinity kits, project custody, workbook reconciliation and honest telemetry status—kept fully separate from IT assets."
        actions={<>
          <button className="secondary-button" onClick={() => void load()}><RefreshCw size={17} /> Refresh</button>
          <Link className="secondary-button" to="/drone/work-records">Work Records</Link>
          <Link className="secondary-button" to="/drone/assets">Asset Master</Link>
          <Link className="primary-button" to="/drone/operations"><PlaneTakeoff size={17} /> New Operation</Link>
        </>}
      />
      {error && <div className="error-message">{error}</div>}

      <section className="stats-grid drone-kpi-grid">
        <StatCard icon={Boxes} label="Permanent Assets" value={data.kpis.total_assets} />
        <StatCard icon={Drone} label="Flight-Capable Drones" value={data.kpis.flight_capable_drones} tone="cyan" />
        <StatCard icon={FolderKanban} label="At Projects" value={data.kpis.assets_at_projects} tone="purple" />
        <StatCard icon={BatteryCharging} label="Flight-Ready Kits" value={data.kpis.flight_ready_kits} tone="green" />
        <StatCard icon={Wrench} label="Maintenance / Service" value={data.kpis.under_maintenance} tone="orange" />
        <StatCard icon={ClipboardCheck} label="Pending Verification" value={data.kpis.pending_verification} />
        <StatCard icon={HardDrive} label="HDD Deliveries" value={data.kpis.hdd_deliveries} tone="cyan" />
        <StatCard icon={PlaneTakeoff} label="Active Operations" value={data.kpis.active_operations || 0} tone="purple" />
        <StatCard icon={Clock3} label="Overdue Returns" value={data.kpis.overdue_returns || 0} tone="orange" />
        <StatCard icon={AlertTriangle} label="Unresolved Import Issues" value={data.import_quality.unresolved_import_exceptions} tone="orange" />
      </section>

      <section className="dashboard-grid three-column-dashboard">
        <article className="panel">
          <div className="panel-heading"><div><span className="section-kicker">ASSET MIX</span><h2>Assets by Category</h2></div></div>
          <DonutChart data={data.category_distribution} centerLabel="Assets" />
        </article>
        <article className="panel">
          <div className="panel-heading"><div><span className="section-kicker">CURRENT STATE</span><h2>Status Distribution</h2></div></div>
          <HorizontalBars data={data.status_distribution} />
        </article>
        <article className="panel">
          <div className="panel-heading"><div><span className="section-kicker">PROJECT CUSTODY</span><h2>Assets by Project</h2></div></div>
          <HorizontalBars data={data.project_distribution} />
        </article>
      </section>

      <section className="dashboard-grid drone-layout">
        <article className="panel drone-map-card">
          <div className="panel-heading"><div><span className="section-kicker">LIVE / LAST KNOWN</span><h2>Telemetry-Capable Drones</h2></div><MapPin /></div>
          <div className="drone-map-visual">
            <DroneMap latitude={mapped?.latest_location?.latitude} longitude={mapped?.latest_location?.longitude} label={mapped ? `${mapped.asset_code} · ${mapped.name}` : 'No telemetry location'} />
            <div className="coordinate-card">
              <strong>{mapped?.latest_location ? `${mapped.latest_location.latitude.toFixed(6)}, ${mapped.latest_location.longitude.toFixed(6)}` : 'No telemetry received'}</strong>
              <span>{mapped ? `${mapped.asset_code} · ${mapped.freshness}` : 'Imported assets are not assigned fake GPS data'}</span>
              <small>{mapped?.latest_location ? `Recorded ${new Date(mapped.latest_location.recorded_at).toLocaleString()} · ${mapped.latest_location.source}` : 'Use the existing telemetry API for compatible drones.'}</small>
            </div>
          </div>
        </article>
        <article className="panel">
          <div className="panel-heading"><div><span className="section-kicker">RECENT MASTER RECORDS</span><h2>Recently Added Assets</h2></div><Link className="text-button" to="/drone/assets">View all</Link></div>
          <div className="drone-asset-list">
            {data.recent_assets.length === 0 && <div className="empty-state">Import the supplied workbook or add a new Drone/Survey asset.</div>}
            {data.recent_assets.map(asset => (
              <Link key={asset.id} to={`/drone/assets/${asset.id}`} className="drone-asset-row">
                <div><strong>{asset.asset_tag} · {asset.asset_name}</strong><span>{asset.manufacturer || 'Manufacturer not recorded'} · {asset.model_number || 'Model not recorded'}</span><small>{asset.serial_number || 'Serial not recorded'} · {asset.current_project || asset.current_custodian || 'Available master record'}</small></div>
                <span className={`status ${asset.current_status}`}>{asset.current_status.replaceAll('_', ' ')}</span>
              </Link>
            ))}
          </div>
        </article>
      </section>

      <section className="dashboard-grid project-detail-grid">
        <article className="panel"><div className="panel-heading"><div><span className="section-kicker">ACTIVE OPERATIONS</span><h2>Open Dispatches and Assignments</h2></div><Link className="text-button" to="/drone/operations">Open operations</Link></div><div className="operation-history-list">{(data.active_operations || []).map(operation => <article key={operation.id}><div><strong>{operation.operation_code} · {operation.operation_type}</strong><span>{operation.project || operation.to_custodian || 'No project'} · Expected {operation.expected_return_date || 'open'}</span></div><div><span className={`status ${operation.status}`}>{operation.status}</span></div></article>)}{(data.active_operations || []).length === 0 && <div className="empty-state">No open Drone dispatches or assignments.</div>}</div></article>
        <article className="panel"><div className="panel-heading"><div><span className="section-kicker">RECENT MOVEMENTS</span><h2>Latest Custody Changes</h2></div><ArrowRightLeft /></div><div className="compact-record-list">{(data.recent_movements || []).map(row => <div key={row.id}><div><strong>{row.asset_tag || row.kit_tag} · {row.asset_name || row.kit_name}</strong><span>{row.movement_type.replaceAll('_',' ')} · {new Date(row.occurred_at).toLocaleString()}</span></div><span className={`status ${row.new_status || 'available'}`}>{row.new_status?.replaceAll('_',' ') || 'recorded'}</span></div>)}{(data.recent_movements || []).length === 0 && <div className="empty-state">No controlled movements recorded yet.</div>}</div></article>
      </section>

      <section className="panel data-quality-panel">
        <div className="panel-heading"><div><span className="section-kicker">IMPORT QUALITY</span><h2>Workbook Reconciliation Signals</h2></div><Link className="secondary-button" to="/drone/import">Review Imports</Link></div>
        <div className="quality-grid">
          <article><span>Missing serial numbers</span><strong>{data.import_quality.missing_serial_numbers}</strong></article>
          <article><span>Duplicate imported IDs</span><strong>{data.import_quality.duplicate_imported_ids}</strong></article>
          <article><span>Unresolved exceptions</span><strong>{data.import_quality.unresolved_import_exceptions}</strong></article>
          <article><span>Active projects</span><strong>{data.kpis.active_projects}</strong></article>
        </div>
      </section>
    </>
  )
}
