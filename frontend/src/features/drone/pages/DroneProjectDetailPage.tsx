import { ArrowLeft, ArrowRightLeft, CheckCircle2, ClipboardList, PackageCheck, PlaneTakeoff } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import type { DroneProjectDetail } from '../../../types'

export function DroneProjectDetailPage() {
  const { id } = useParams()
  const [project, setProject] = useState<DroneProjectDetail | null>(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const load = () => apiFetch<DroneProjectDetail>(`/drone/projects/${id}`).then(setProject).catch(err => setError(err.message))
  useEffect(() => { void load() }, [id])

  const changeStatus = async (status: string) => {
    setSaving(true); setError('')
    try { await apiFetch(`/drone/projects/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) }); await load() }
    catch (err) { setError(err instanceof Error ? err.message : 'Unable to update project') }
    finally { setSaving(false) }
  }

  if (error && !project) return <div className="error-message">{error}</div>
  if (!project) return <div className="loading-state">Loading Drone project…</div>

  return <>
    <DashboardHeader
      eyebrow={project.project_code}
      title={project.project_name}
      description={project.description || 'Drone and Survey project master, custody, operations and work history.'}
      actions={<><Link className="secondary-button" to="/drone/projects"><ArrowLeft size={16} /> Projects</Link><Link className="primary-button" to={`/drone/operations?project=${project.id}`}><PlaneTakeoff size={16} /> Dispatch / Operate</Link></>}
    />
    {error && <div className="error-message">{error}</div>}
    <section className="project-detail-summary">
      <article className="panel"><span>Project Status</span><strong className={`status ${project.status}`}>{project.status.replaceAll('_',' ')}</strong></article>
      <article className="panel"><span>Current Assets</span><strong>{project.summary.asset_count}</strong></article>
      <article className="panel"><span>Current Kits</span><strong>{project.summary.kit_count}</strong></article>
      <article className="panel"><span>Open Dispatches</span><strong>{project.summary.open_operations}</strong></article>
      <article className="panel"><span>Overdue Returns</span><strong>{project.summary.overdue_returns}</strong></article>
      <article className="panel"><span>Work Records</span><strong>{project.summary.work_records}</strong></article>
    </section>

    <section className="dashboard-grid project-detail-grid">
      <article className="panel">
        <div className="panel-heading"><div><span className="section-kicker">PROJECT MASTER</span><h2>Project Information</h2></div></div>
        <div className="detail-list"><div><span>Client</span><strong>{project.client || 'Not recorded'}</strong></div><div><span>Project Manager</span><strong>{project.project_manager || 'Not assigned'}</strong></div><div><span>Period</span><strong>{project.start_date || 'Not set'} → {project.expected_end_date || 'Open'}</strong></div><div><span>Financial Year</span><strong>{project.financial_year || 'Not recorded'}</strong></div><div><span>Location</span><strong>{project.location || 'Not recorded'}</strong></div><div><span>Project Area</span><strong>{project.project_area || 'Not recorded'}</strong></div></div>
        <div className="project-status-actions"><button className="secondary-button" disabled={saving} onClick={() => void changeStatus('active')}>Mark Active</button><button className="secondary-button" disabled={saving} onClick={() => void changeStatus('completed')}>Mark Completed</button><button className="primary-button" disabled={saving} onClick={() => void changeStatus('closed')}><CheckCircle2 size={16} /> Close Project</button></div>
      </article>
      <article className="panel">
        <div className="panel-heading"><div><span className="section-kicker">CURRENT CUSTODY</span><h2>Assets at Project</h2></div><span className="count-chip">{project.assets.length}</span></div>
        <div className="compact-record-list">{project.assets.map(asset => <Link key={asset.id} to={`/drone/assets/${asset.id}`}><div><strong>{asset.asset_tag} · {asset.asset_name}</strong><span>{asset.current_custodian || 'No custodian'} · {asset.current_location || 'No location'}</span></div><span className={`status ${asset.current_status}`}>{asset.current_status.replaceAll('_',' ')}</span></Link>)}{project.assets.length === 0 && <div className="empty-state">No individual assets currently assigned.</div>}</div>
      </article>
      <article className="panel">
        <div className="panel-heading"><div><span className="section-kicker">KIT CUSTODY</span><h2>Kits at Project</h2></div><PackageCheck /></div>
        <div className="compact-record-list">{project.kits.map(kit => <div key={kit.id}><div><strong>{kit.kit_tag} · {kit.kit_name}</strong><span>{kit.current_custodian || 'No custodian'} · {kit.readiness_percentage}% ready</span></div><span className={`status ${kit.current_status}`}>{kit.current_status.replaceAll('_',' ')}</span></div>)}{project.kits.length === 0 && <div className="empty-state">No kits currently assigned.</div>}</div>
      </article>
      <article className="panel">
        <div className="panel-heading"><div><span className="section-kicker">WORK RECORDS</span><h2>Project Tasks</h2></div><ClipboardList /></div>
        <div className="compact-record-list">{project.work_records.slice(0, 8).map(record => <div key={record.id}><div><strong>{record.work_code} · {record.title}</strong><span>{record.work_type.replaceAll('_',' ')} · {record.created_at.slice(0,10)}</span></div><span className={`status ${record.status}`}>{record.status}</span></div>)}{project.work_records.length === 0 && <div className="empty-state">No work records linked to this project.</div>}</div>
      </article>
    </section>

    <section className="panel project-operations-panel">
      <div className="panel-heading"><div><span className="section-kicker">OPERATION TIMELINE</span><h2>Dispatch, Return, Transfer & Assignment</h2></div><ArrowRightLeft /></div>
      <div className="operation-history-list">{project.operations.map(operation => <article key={operation.id}><div><strong>{operation.operation_code} · {operation.operation_type.replaceAll('_',' ')}</strong><span>{operation.operation_date} · {operation.to_custodian || 'No custodian'} · {operation.destination || 'No destination'}</span></div><div><span className={`status ${operation.status}`}>{operation.status}</span><small>{operation.items.length} item records</small></div></article>)}{project.operations.length === 0 && <div className="empty-state">No project operations recorded yet.</div>}</div>
    </section>

    <section className="panel project-movement-panel">
      <div className="panel-heading"><div><span className="section-kicker">MOVEMENT HISTORY</span><h2>Asset and Kit Timeline</h2></div></div>
      <div className="movement-table-wrap"><table className="movement-table"><thead><tr><th>Date</th><th>Movement</th><th>Item</th><th>From</th><th>To</th><th>Custody</th></tr></thead><tbody>{project.movements.map(movement => <tr key={movement.id}><td>{new Date(movement.occurred_at).toLocaleString()}</td><td>{movement.movement_type.replaceAll('_',' ')}</td><td>{movement.asset_tag || movement.kit_tag} · {movement.asset_name || movement.kit_name}</td><td>{movement.old_project || movement.old_location || '—'}</td><td>{movement.new_project || movement.new_location || '—'}</td><td>{movement.old_custodian || '—'} → {movement.new_custodian || '—'}</td></tr>)}</tbody></table>{project.movements.length === 0 && <div className="empty-state">No movement records yet.</div>}</div>
    </section>
  </>
}
