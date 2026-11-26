import { ArrowRightLeft, History, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import type { DroneMovement } from '../../../types'

export function DroneMovementsPage() {
  const [rows, setRows] = useState<DroneMovement[]>([])
  const [error, setError] = useState('')
  useEffect(() => { void apiFetch<DroneMovement[]>('/drone/movements?limit=500').then(setRows).catch(err => setError(err.message)) }, [])
  return <>
    <DashboardHeader eyebrow="AUDITABLE CUSTODY HISTORY" title="Drone Movement History" description="Every dispatch, return, transfer and assignment is recorded here without replacing or deleting earlier custody history." meta={<><span className="nk-meta-chip"><History size={14} /> Append-only custody timeline</span><span className="nk-meta-chip"><ShieldCheck size={14} /> Earlier history is never replaced or deleted</span><span className="nk-meta-chip"><ArrowRightLeft size={14} /> Assets and kits in one audit trail</span></>} />
    {error && <div className="error-message">{error}</div>}
    <section className="panel">
      <div className="panel-heading"><div><span className="section-kicker">ALL MOVEMENTS</span><h2>Asset and Kit Timeline</h2></div><ArrowRightLeft /></div>
      <div className="movement-table-wrap"><table className="movement-table"><thead><tr><th>Movement ID</th><th>Date & Time</th><th>Type</th><th>Item</th><th>Quantity</th><th>Old State</th><th>New State</th><th>Custody / Location</th><th>Performed By</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td>{row.movement_code}</td><td>{new Date(row.occurred_at).toLocaleString()}</td><td>{row.movement_type.replaceAll('_',' ')}</td><td>{row.asset_tag || row.kit_tag}<small>{row.asset_name || row.kit_name}</small></td><td>{row.quantity}</td><td>{row.old_status?.replaceAll('_',' ') || '—'}<small>{row.old_project || row.old_location || ''}</small></td><td>{row.new_status?.replaceAll('_',' ') || '—'}<small>{row.new_project || row.new_location || ''}</small></td><td>{row.old_custodian || '—'} → {row.new_custodian || '—'}</td><td>{row.performed_by || 'System'}</td></tr>)}</tbody></table>{rows.length === 0 && <div className="empty-state">No Drone movements recorded yet.</div>}</div>
    </section>
  </>
}
