import { BatteryCharging, Boxes, CheckCircle2, ChevronDown, ChevronUp } from 'lucide-react'
import { useEffect, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import type { DroneKit } from '../../../types'

export function DroneKitsPage() {
  const [kits, setKits] = useState<DroneKit[]>([])
  const [open, setOpen] = useState<number | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { void apiFetch<DroneKit[]>('/drone/kits').then(setKits).catch(err => setError(err.message)) }, [])
  return <>
    <DashboardHeader eyebrow="KIT READINESS" title="Drone Kits & Components" description="Trinity units and future kits are parent records. Every battery, controller, camera and accessory remains an individually traceable component." meta={<><span className="nk-meta-chip"><Boxes size={14} /> Trinity units are parent kit records</span><span className="nk-meta-chip"><BatteryCharging size={14} /> Every component individually traceable</span><span className="nk-meta-chip"><CheckCircle2 size={14} /> Readiness computed from components</span></>} />
    {error && <div className="error-message">{error}</div>}
    <section className="kit-grid">
      {kits.map(kit => <article className="panel kit-card" key={kit.id}>
        <div className="kit-card-head"><div className="kit-icon"><Boxes /></div><div><span className="section-kicker">{kit.kit_tag}</span><h2>{kit.kit_name}</h2><p>{kit.model || 'Model not recorded'} · Unit {kit.unit_number || '—'}</p></div><span className={`status ${kit.current_status}`}>{kit.current_status.replaceAll('_', ' ')}</span></div>
        <div className="kit-readiness"><div><span>Readiness</span><strong>{kit.readiness_percentage}%</strong></div><div className="readiness-track"><div style={{ width: `${kit.readiness_percentage}%` }} /></div></div>
        <div className="kit-metrics"><article><BatteryCharging /><div><strong>{kit.available_components}</strong><span>Available</span></div></article><article><CheckCircle2 /><div><strong>{kit.component_count}</strong><span>Components</span></div></article><article><Boxes /><div><strong>{kit.missing_components}</strong><span>Unavailable</span></div></article></div>
        <div className="kit-context"><span>Project: <strong>{kit.current_project || 'Not deployed'}</strong></span><span>UIN: <strong>{kit.uin || 'Not recorded'}</strong></span></div>
        <button className="secondary-button full-button" onClick={() => setOpen(open === kit.id ? null : kit.id)}>{open === kit.id ? <ChevronUp size={16} /> : <ChevronDown size={16} />} {open === kit.id ? 'Hide Components' : 'View Components'}</button>
        {open === kit.id && <div className="kit-component-list">{kit.components.map(component => <div key={component.id}><div><strong>{component.asset_tag} · {component.component_name}</strong><span>{component.serial_number || 'Serial not recorded'} · Qty {component.quantity}</span></div><span className={`status ${component.status}`}>{component.status.replaceAll('_', ' ')}</span></div>)}</div>}
      </article>)}
      {kits.length === 0 && <div className="empty-state">Trinity kits will appear after the workbook import is approved.</div>}
    </section>
  </>
}
