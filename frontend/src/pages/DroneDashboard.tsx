import { BatteryCharging, MapPin, Navigation, Radio, Route } from 'lucide-react'
import { DroneIcon as Drone } from '../components/DroneIcon'
import { useEffect, useState } from 'react'
import { DashboardHeader } from '../components/DashboardHeader'
import { DroneMap } from '../components/DroneMap'
import { StatCard } from '../components/StatCard'
import { apiFetch } from '../lib/api'
import type { Drone as DroneType } from '../types'

export function DroneDashboard() {
  const [drones, setDrones] = useState<DroneType[]>([])
  const [error, setError] = useState('')
  useEffect(() => { void apiFetch<DroneType[]>('/drones').then(setDrones).catch(err => setError(err.message)) }, [])
  const active = drones.filter(drone => drone.status === 'deployed').length
  const first = drones[0]
  return (
    <>
      <DashboardHeader eyebrow="AERIAL OPERATIONS" title="Drone Dashboard" description="Fleet deployment, project allocation, pilot records and current or last-known GNSS location." />
      {error && <div className="error-message">{error}</div>}
      <section className="stats-grid">
        <StatCard icon={Drone} label="Total Drones" value={drones.length} />
        <StatCard icon={Radio} label="Deployed" value={active} tone="green" />
        <StatCard icon={BatteryCharging} label="Battery" value={first?.battery_percent ? `${first.battery_percent}%` : '—'} tone="cyan" />
        <StatCard icon={MapPin} label="Location Status" value={first?.latest_location ? 'Available' : 'No Signal'} tone="purple" />
      </section>
      <section className="dashboard-grid drone-layout">
        <article className="panel drone-map-card"><div className="panel-heading"><div><span className="section-kicker">LIVE / LAST KNOWN</span><h2>Drone Location</h2></div><Navigation /></div><div className="drone-map-visual"><DroneMap latitude={first?.latest_location?.latitude} longitude={first?.latest_location?.longitude} label={first ? `${first.asset_code} · ${first.project || first.name}` : 'Drone location'} /><div className="coordinate-card"><strong>{first?.latest_location ? `${first.latest_location.latitude.toFixed(6)}, ${first.latest_location.longitude.toFixed(6)}` : 'Location unavailable'}</strong><span>{first?.project || 'No active project'}</span><small>{first?.latest_location ? `Last update: ${new Date(first.latest_location.recorded_at).toLocaleString()}` : 'Waiting for telemetry or manual location'}</small></div></div></article>
        <article className="panel"><div className="panel-heading"><div><span className="section-kicker">FLEET REGISTER</span><h2>Drone Assets</h2></div><Route /></div><div className="drone-list">{drones.map(drone => <article key={drone.id}><div className="drone-icon"><Drone /></div><div><strong>{drone.asset_code} · {drone.name}</strong><span>{drone.model}</span><small>{drone.project || 'Available'} · Pilot: {drone.pilot || 'Unassigned'}</small></div><span className={`status ${drone.status}`}>{drone.status}</span></article>)}</div></article>
      </section>
    </>
  )
}
