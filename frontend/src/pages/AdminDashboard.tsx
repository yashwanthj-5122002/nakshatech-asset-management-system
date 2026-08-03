import { BarChart3, FileSpreadsheet, HardDrive, Settings, ShieldCheck, Users } from 'lucide-react'
import { useEffect, useState } from 'react'
import { DroneIcon as Drone } from '../components/DroneIcon'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../components/DashboardHeader'
import { StatCard } from '../components/StatCard'
import { apiFetch } from '../lib/api'
import type { DashboardSummary } from '../types'
import { useAuth } from '../context/AuthContext'

export function AdminDashboard() {
  const { user } = useAuth()
  const softwareTeam = user?.role === 'software_team'
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  useEffect(() => { void apiFetch<DashboardSummary>('/dashboard/summary').then(setSummary) }, [])
  return (
    <>
      <DashboardHeader
        eyebrow={softwareTeam ? "SOFTWARE TEAM · FULL TECHNICAL ACCESS" : "ADMIN · ORGANIZATION CONTROL"}
        title={softwareTeam ? "Software Team Control Centre" : "Admin Control Centre"}
        description={softwareTeam
          ? "Maintain and support every IT, drone, management, reporting and backup module without changing department workflows."
          : "Review Management, IT and Drone operations through a clear department-wise workspace."}
      />
      <section className="stats-grid">
        <StatCard icon={HardDrive} label="IT Assets" value={summary?.assets_total ?? '—'} />
        <StatCard icon={Drone} label="Drones" value={summary?.drones_total ?? '—'} tone="cyan" />
        <StatCard icon={BarChart3} label="Open Work" value={summary?.pending_work ?? '—'} tone="orange" />
        <StatCard icon={ShieldCheck} label="Access Level" value="Full" tone="green" />
      </section>
      <section className="module-grid admin-modules">
        <Link className="module-card" to="/it"><HardDrive /><h3>IT Operations</h3><p>Inventory, dashboard, work, repair and replacement records.</p></Link>
        <Link className="module-card" to="/drone"><Drone /><h3>Drone Operations</h3><p>Drone fleet, projects, pilot allocation and live location.</p></Link>
        <Link className="module-card" to="/management"><Users /><h3>Management View</h3><p>Combined oversight and approval workflows.</p></Link>
        <Link className="module-card" to="/reports"><FileSpreadsheet /><h3>Excel Control</h3><p>Import or export NakshaTech monthly asset files.</p></Link>
        <Link className="module-card" to="/future"><Settings /><h3>Future Modules</h3><p>Extend without changing the main architecture.</p></Link>
      </section>
    </>
  )
}
