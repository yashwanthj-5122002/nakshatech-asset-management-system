import { Activity, BarChart3, FileCheck2, FileSpreadsheet, HardDrive, LifeBuoy, MonitorCheck, ReceiptIndianRupee, Settings, ShieldCheck, Users } from 'lucide-react'
import { useEffect, useState } from 'react'
import { DroneIcon as Drone } from '../components/DroneIcon'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../components/DashboardHeader'
import { StatCard } from '../components/StatCard'
import { apiFetch } from '../lib/api'
import type { DashboardSummary, ExpenseClaim } from '../types'
import { useAuth } from '../context/AuthContext'

export function AdminDashboard() {
  const { user } = useAuth()
  const softwareTeam = user?.role === 'software_team'
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [financeClaims, setFinanceClaims] = useState<ExpenseClaim[]>([])
  useEffect(() => {
    void apiFetch<DashboardSummary>('/dashboard/summary').then(setSummary)
    if (!softwareTeam) {
      void apiFetch<ExpenseClaim[]>('/finance/claims').then(setFinanceClaims).catch(() => setFinanceClaims([]))
    }
  }, [softwareTeam])
  const pendingExpenseApprovals = financeClaims.filter(claim => claim.status === 'submitted').length
  return (
    <>
      <DashboardHeader
        eyebrow={softwareTeam ? "SOFTWARE TEAM · FULL TECHNICAL ACCESS" : "ADMIN · ORGANIZATION CONTROL"}
        title={softwareTeam ? "Software Team Control Centre" : "Admin Control Centre"}
        description={softwareTeam
          ? "Maintain and support every IT, drone, management, reporting and backup module without changing department workflows."
          : "Review Management, IT, Drone and Finance operations through a clear department-wise workspace. Expense claims awaiting Admin verification are surfaced here directly."}
      />
      <section className="stats-grid">
        <StatCard icon={HardDrive} label="IT Assets" value={summary?.assets_total ?? '—'} />
        <StatCard icon={Drone} label="Drones" value={summary?.drones_total ?? '—'} tone="cyan" />
        <StatCard icon={BarChart3} label="Open Work" value={summary?.pending_work ?? '—'} tone="orange" />
        <StatCard icon={ShieldCheck} label="Access Level" value="Full" tone="green" />
        {!softwareTeam && <StatCard icon={ReceiptIndianRupee} label="Expense Approvals" value={pendingExpenseApprovals} tone={pendingExpenseApprovals > 0 ? "orange" : "green"} />}
      </section>
      <section className="module-grid admin-modules">
        <Link className="module-card" to="/it"><HardDrive /><h3>IT Operations</h3><p>Inventory, dashboard, work, repair and replacement records.</p></Link>
        <Link className="module-card" to="/drone"><Drone /><h3>Drone Operations</h3><p>Drone fleet, projects, pilot allocation and live location.</p></Link>
        <Link className="module-card" to="/management"><Users /><h3>Management View</h3><p>Combined oversight and approval workflows.</p></Link>
        {!softwareTeam && <Link className="module-card" to="/finance/claims"><FileCheck2 /><h3>Project Expense Approvals</h3><p>{pendingExpenseApprovals > 0 ? `${pendingExpenseApprovals} claim(s) are waiting for Admin verification. Review Project ID, purpose, amount and proof, then send valid claims to Finance.` : 'No expense claims are waiting right now. Employee submissions will appear here automatically for Admin verification.'}</p></Link>}
        {!softwareTeam && <Link className="module-card" to="/finance"><ReceiptIndianRupee /><h3>Finance Dashboard</h3><p>View project expenses, advances, reimbursements, approval status and Finance activity.</p></Link>}
        <Link className="module-card" to="/reports"><FileSpreadsheet /><h3>Excel Control</h3><p>Import or export NakshaTech monthly asset files.</p></Link>
        {softwareTeam && <Link className="module-card" to="/software-team/agents"><MonitorCheck /><h3>Agent Monitoring</h3><p>View live employee systems, endpoint status, users, applications and device details.</p></Link>}
        {softwareTeam && <Link className="module-card" to="/tickets"><LifeBuoy /><h3>All Ticket Monitoring</h3><p>Monitor every department ticket and directly handle Software Team issues.</p></Link>}
        {softwareTeam && <Link className="module-card" to="/software-team/security"><Activity /><h3>Users & Audit</h3><p>Review account creation, logins, branch selection, resets, and module activity.</p></Link>}
        <Link className="module-card" to="/future"><Settings /><h3>Future Modules</h3><p>Extend without changing the main architecture.</p></Link>
      </section>
    </>
  )
}
