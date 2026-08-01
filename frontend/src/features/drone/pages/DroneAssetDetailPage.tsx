import { ArrowRightLeft, Edit3, PlaneTakeoff } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import type { DroneMovement, DroneSurveyAsset } from '../../../types'

export function DroneAssetDetailPage() {
  const { id } = useParams()
  const [asset, setAsset] = useState<DroneSurveyAsset | null>(null)
  const [error, setError] = useState('')
  const [movements, setMovements] = useState<DroneMovement[]>([])
  useEffect(() => { void Promise.all([apiFetch<DroneSurveyAsset>(`/drone/assets/${id}`), apiFetch<DroneMovement[]>(`/drone/movements?asset_id=${id}`)]).then(([record, rows]) => { setAsset(record); setMovements(rows) }).catch(err => setError(err.message)) }, [id])
  if (error) return <div className="error-message">{error}</div>
  if (!asset) return <div className="loading-state">Loading permanent asset record…</div>
  const identity = [
    ['Asset Tag', asset.asset_tag], ['Imported Equipment ID', asset.imported_equipment_id], ['Equipment', asset.asset_name], ['Category', asset.category],
    ['Manufacturer', asset.manufacturer], ['Model', asset.model_number], ['Serial Number', asset.serial_number || asset.raw_serial_number], ['Quantity', `${asset.quantity} ${asset.unit_of_measure || ''}`],
  ]
  const state = [
    ['Status', asset.current_status.replaceAll('_', ' ')], ['Working Condition', asset.working_condition], ['Custodian', asset.current_custodian], ['Associated People', asset.associated_people.join(', ')],
    ['Project', asset.current_project], ['Location', asset.current_location], ['Parent Kit', asset.parent_kit], ['Telemetry', asset.is_telemetry_capable ? 'Enabled' : 'Not applicable'],
  ]
  return <>
    <DashboardHeader eyebrow="PERMANENT ASSET PROFILE" title={`${asset.asset_tag} · ${asset.asset_name}`} description="Current state and lossless source information are shown together without mixing this asset into the IT register." actions={<><Link className="secondary-button" to="/drone/assets">Back to Register</Link><Link className="secondary-button" to="/drone/operations"><PlaneTakeoff size={17} /> Operate</Link><Link className="primary-button" to={`/drone/assets/${asset.id}/edit`}><Edit3 size={17} /> Edit</Link></>} />
    <section className="detail-grid">
      <article className="panel"><div className="panel-heading"><div><span className="section-kicker">IDENTITY</span><h2>Permanent Asset Master</h2></div></div><div className="detail-list">{identity.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value || 'Not recorded'}</strong></div>)}</div></article>
      <article className="panel"><div className="panel-heading"><div><span className="section-kicker">CURRENT STATE</span><h2>Custody and Condition</h2></div></div><div className="detail-list">{state.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value || 'Not recorded'}</strong></div>)}</div></article>
      <article className="panel"><div className="panel-heading"><div><span className="section-kicker">SOURCE TRACEABILITY</span><h2>Original Workbook Record</h2></div></div><div className="detail-list"><div><span>Workbook</span><strong>{asset.source_workbook || 'Manual entry'}</strong></div><div><span>Sheet</span><strong>{asset.source_sheet || 'Manual entry'}</strong></div><div><span>Source Row</span><strong>{asset.source_row || '—'}</strong></div><div><span>Reconciliation</span><strong>{asset.reconciliation_status}</strong></div></div><details className="raw-source-details"><summary>View original raw values</summary><pre>{JSON.stringify(asset.original_raw_payload || {}, null, 2)}</pre></details></article>
      <article className="panel"><div className="panel-heading"><div><span className="section-kicker">TECHNICAL</span><h2>Maintenance and Calibration</h2></div></div><div className="detail-list"><div><span>Maintenance Required</span><strong>{asset.maintenance_required || 'Not recorded'}</strong></div><div><span>Calibration Required</span><strong>{asset.calibration_required || 'Not recorded'}</strong></div><div><span>Technical Frequency</span><strong>{asset.technical_frequency || 'Not recorded'}</strong></div><div><span>Next Calibration</span><strong>{asset.next_calibration_date || 'Not recorded'}</strong></div><div><span>Responsible Function</span><strong>{asset.responsible_function || 'Not recorded'}</strong></div><div><span>Tolerance</span><strong>{asset.equipment_tolerance || 'Not recorded'}</strong></div></div></article>
    </section>
    <section className="panel project-movement-panel"><div className="panel-heading"><div><span className="section-kicker">CUSTODY HISTORY</span><h2>Movement Timeline</h2></div><ArrowRightLeft /></div><div className="movement-table-wrap"><table className="movement-table"><thead><tr><th>Date</th><th>Movement</th><th>Old State</th><th>New State</th><th>Project / Location</th><th>Custodian</th></tr></thead><tbody>{movements.map(row => <tr key={row.id}><td>{new Date(row.occurred_at).toLocaleString()}</td><td>{row.movement_type.replaceAll('_',' ')}</td><td>{row.old_status?.replaceAll('_',' ') || '—'}</td><td>{row.new_status?.replaceAll('_',' ') || '—'}</td><td>{row.old_project || row.old_location || '—'} → {row.new_project || row.new_location || '—'}</td><td>{row.old_custodian || '—'} → {row.new_custodian || '—'}</td></tr>)}</tbody></table>{movements.length === 0 && <div className="empty-state">No controlled movement has been recorded for this asset yet.</div>}</div></section>
  </>
}
