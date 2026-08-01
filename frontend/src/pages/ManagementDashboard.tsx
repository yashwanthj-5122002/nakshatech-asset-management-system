import { ArrowRight, ClipboardCheck, FileBarChart, HardDrive, Repeat2 } from 'lucide-react'
import { DroneIcon as Drone } from '../components/DroneIcon'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../components/DashboardHeader'
import { StatCard } from '../components/StatCard'
import { apiFetch } from '../lib/api'
import type { DashboardSummary } from '../types'

export function ManagementDashboard() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  useEffect(() => { void apiFetch<DashboardSummary>('/dashboard/summary').then(setSummary) }, [])
  return (
    <>
      <DashboardHeader eyebrow="MONITOR & MANAGE" title="Management Dashboard" description="A combined decision view for IT assets, drone operations, work progress, approvals and management reports." />
      <section className="stats-grid">
        <StatCard icon={HardDrive} label="IT Assets" value={summary?.assets_total ?? '—'} />
        <StatCard icon={Drone} label="Drone Fleet" value={summary?.drones_total ?? '—'} tone="cyan" />
        <StatCard icon={ClipboardCheck} label="Open Work" value={summary?.pending_work ?? '—'} tone="orange" />
        <StatCard icon={Repeat2} label="Approval Workflows" value="Active" tone="purple" />
      </section>
      <section className="management-cards">
        <Link to="/it"><HardDrive /><div><span className="section-kicker">IT OVERVIEW</span><h2>Open IT Dashboard</h2><p>Inventory condition, repairs, replacements, departments and work records.</p></div><ArrowRight /></Link>
        <Link to="/drone"><Drone /><div><span className="section-kicker">DRONE OVERVIEW</span><h2>Open Drone Dashboard</h2><p>Fleet deployment, pilot, projects, battery and last known location.</p></div><ArrowRight /></Link>
        <Link to="/replacements"><ClipboardCheck /><div><span className="section-kicker">APPROVALS</span><h2>Review Replacements</h2><p>Approve or reject replacement requests with full old/new asset linkage.</p></div><ArrowRight /></Link>
        <Link to="/reports"><FileBarChart /><div><span className="section-kicker">REPORTING</span><h2>Download Reports</h2><p>Export current asset and dashboard Excel workbooks.</p></div><ArrowRight /></Link>
      </section>
    </>
  )
}
