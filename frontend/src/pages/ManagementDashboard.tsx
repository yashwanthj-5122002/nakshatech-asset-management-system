import {
  AlertTriangle,
  ArrowRight,
  Boxes,
  CheckCircle2,
  ClipboardCheck,
  Clock3,
  FileBarChart,
  HardDrive,
  History,
  IndianRupee,
  KeyRound,
  RotateCcw,
  Repeat2,
  ShieldCheck,
  Wallet,
  Wrench,
  X,
} from 'lucide-react'
import { DroneIcon as Drone } from '../components/DroneIcon'
import { type FormEvent, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { DashboardHeader } from '../components/DashboardHeader'
import { StatCard } from '../components/StatCard'
import { useAuth } from '../context/AuthContext'
import { useITMonthUrl } from '../context/ITMonthContext'
import { apiFetch } from '../lib/api'
import { monthLabel } from '../lib/itMonth'
import type { LifecycleDashboardSummary } from '../features/operations/lifecycle-types'
import '../management-auth.css'
import '../management-control.css'

type ManagementControlSummary = {
  authority_model: string
  executive: {
    primary_assets: number
    assigned_assets: number
    available_assets: number
    repair_assets: number
    replacement_pending_assets: number
    active_it_work: number
    active_replacements: number
    pending_approvals: number
    pending_purchase_requests: number
    approved_purchase_value: number
    open_critical_tickets: number
    sla_warnings: number
    sla_breaches: number
  }
}

export function ManagementDashboard() {
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const { selectedMonth } = useITMonthUrl()
  const [summary, setSummary] = useState<ManagementControlSummary | null>(null)
  const [summaryError, setSummaryError] = useState('')
  const [lifecycle, setLifecycle] = useState<LifecycleDashboardSummary | null>(null)
  const [showPasswordDialog, setShowPasswordDialog] = useState(false)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordError, setPasswordError] = useState('')
  const [changingPassword, setChangingPassword] = useState(false)

  useEffect(() => {
    setSummaryError('')
    void apiFetch<ManagementControlSummary>(`/management/control-center?month=${encodeURIComponent(selectedMonth)}`)
      .then(setSummary)
      .catch(err => setSummaryError(err instanceof Error ? err.message : 'Unable to load executive control summary'))
  }, [selectedMonth])

  useEffect(() => {
    void apiFetch<{ summary: LifecycleDashboardSummary }>('/operations/lifecycle/dashboard')
      .then(data => setLifecycle(data.summary))
      .catch(() => setLifecycle(null))
  }, [])

  function closePasswordDialog() {
    if (changingPassword) return
    setShowPasswordDialog(false)
    setCurrentPassword('')
    setNewPassword('')
    setConfirmPassword('')
    setPasswordError('')
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault()
    setChangingPassword(true)
    setPasswordError('')
    try {
      const result = await apiFetch<{ message: string }>('/auth/management/change-password', {
        method: 'POST',
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
          confirm_password: confirmPassword,
        }),
      })
      sessionStorage.setItem('management_password_changed', result.message)
      logout()
      navigate('/login', { replace: true })
    } catch (err) {
      setPasswordError(err instanceof Error ? err.message : 'Password change failed')
    } finally {
      setChangingPassword(false)
    }
  }

  const executive = summary?.executive

  return (
    <>
      <DashboardHeader
        eyebrow="READ · MONITOR · APPROVE PURCHASES"
        title="Management Dashboard"
        description={`Executive oversight for ${monthLabel(selectedMonth)}. Management can inspect IT assets and operations in read-only mode; only Purchase Requests require a Management decision.`}
        actions={user?.role === 'management' ? (
          <button className="management-change-password-button" type="button" onClick={() => setShowPasswordDialog(true)}>
            <KeyRound size={18} />
            <span>Change Password</span>
          </button>
        ) : undefined}
      />
      {summaryError && <div className="error-message">{summaryError}</div>}
      <div className="approval-note"><ShieldCheck size={16} /> Management can see the complete IT picture, but operational edits remain with IT. Purchase approval is the only Management permission gate.</div>

      <section className="stats-grid management-control-kpis">
        <StatCard icon={ClipboardCheck} label="Pending Purchase Approvals" value={executive?.pending_purchase_requests ?? '—'} tone="purple" />
        <StatCard icon={HardDrive} label="Primary IT Assets" value={executive?.primary_assets ?? '—'} />
        <StatCard icon={Boxes} label="Assigned Assets" value={executive?.assigned_assets ?? '—'} tone="blue" />
        <StatCard icon={Boxes} label="Available Assets" value={executive?.available_assets ?? '—'} tone="green" />
        <StatCard icon={Wrench} label="Under Repair" value={executive?.repair_assets ?? '—'} tone="orange" />
        <StatCard icon={Repeat2} label="Replacement Pending" value={executive?.replacement_pending_assets ?? '—'} tone="orange" />
        <StatCard icon={AlertTriangle} label="SLA Breaches" value={executive?.sla_breaches ?? '—'} tone="red" />
        <StatCard icon={ShieldCheck} label="Critical Tickets" value={executive?.open_critical_tickets ?? '—'} tone="red" />
        <StatCard icon={IndianRupee} label="Approved Purchase Value" value={executive ? `₹${executive.approved_purchase_value.toLocaleString('en-IN')}` : '—'} tone="green" />
      </section>

      {lifecycle && <section className="stats-grid management-control-kpis">
        <StatCard icon={Clock3} label="Awaiting Client Feedback" value={lifecycle.awaiting_feedback} tone="orange" />
        <StatCard icon={RotateCcw} label="Rework / BD Classification" value={lifecycle.rework} tone="purple" />
        <StatCard icon={CheckCircle2} label="Ready For Billing" value={lifecycle.ready_for_billing} tone="green" />
        <StatCard icon={Wallet} label="Payment Pending" value={lifecycle.payment_pending} tone="blue" />
        <StatCard icon={AlertTriangle} label="Overdue Invoices" value={lifecycle.overdue} tone="red" />
      </section>}

      <section className="management-cards">
        {user?.role === 'management' && <Link to="/management/approvals"><ClipboardCheck /><div><span className="section-kicker">ONLY PERMISSION QUEUE</span><h2>Purchase Approval Centre</h2><p>{executive?.pending_purchase_requests ?? 0} Purchase Request(s) waiting for Management permission.</p></div><ArrowRight /></Link>}
        <Link to="/management/project-360"><ClipboardCheck /><div><span className="section-kicker">V8.1 LIFECYCLE COMMAND CENTER</span><h2>Client Feedback, Rework &amp; Billing</h2><p>{lifecycle ? `${lifecycle.awaiting_feedback} awaiting feedback · ${lifecycle.rework} in rework · ${lifecycle.overdue} overdue.` : 'Full Project 360, deemed acceptance authorization, change request decisions and PM chat.'}</p></div><ArrowRight /></Link>
        <Link to="/assets"><HardDrive /><div><span className="section-kicker">READ-ONLY ASSET REGISTER</span><h2>View Every IT Asset</h2><p>Inspect asset tag, employee, workstation, department, device details, lifecycle, work history and replacement history.</p></div><ArrowRight /></Link>
        <Link to="/it"><Boxes /><div><span className="section-kicker">IT EXECUTIVE VIEW</span><h2>Open IT Dashboard</h2><p>{executive?.repair_assets ?? 0} under repair · {executive?.replacement_pending_assets ?? 0} replacement pending · {executive?.available_assets ?? 0} available.</p></div><ArrowRight /></Link>
        <Link to="/work"><Wrench /><div><span className="section-kicker">READ-ONLY OPERATIONS</span><h2>IT Work & Component History</h2><p>{executive?.active_it_work ?? 0} active IT work item(s). Management monitors progress without approving operational completion.</p></div><ArrowRight /></Link>
        <Link to="/replacements"><Repeat2 /><div><span className="section-kicker">READ-ONLY LIFECYCLE</span><h2>Replacement History</h2><p>{executive?.active_replacements ?? 0} active replacement workflow(s). IT uses spare stock first; only required procurement comes for purchase approval.</p></div><ArrowRight /></Link>
        <Link to="/it/recent-changes"><History /><div><span className="section-kicker">AUDIT VISIBILITY</span><h2>Recent Changes</h2><p>Review asset, custody, replacement, purchase and operational history with actor and timestamps.</p></div><ArrowRight /></Link>
        <Link to="/tickets"><AlertTriangle /><div><span className="section-kicker">SERVICE RISK</span><h2>Critical Tickets & SLA</h2><p>{executive?.open_critical_tickets ?? 0} critical open · {executive?.sla_warnings ?? 0} SLA warnings · {executive?.sla_breaches ?? 0} breaches.</p></div><ArrowRight /></Link>
        <Link to="/it/purchases"><IndianRupee /><div><span className="section-kicker">PROCUREMENT VISIBILITY</span><h2>Purchase & Procurement Records</h2><p>Read-only visibility of approved requests, procurement execution and completed purchases.</p></div><ArrowRight /></Link>
        <Link to="/drone"><Drone /><div><span className="section-kicker">DRONE OVERVIEW</span><h2>Open Drone Dashboard</h2><p>Fleet deployment, pilot, projects, battery and last known location.</p></div><ArrowRight /></Link>
        <Link to="/reports"><FileBarChart /><div><span className="section-kicker">REPORTING</span><h2>Download Reports</h2><p>Operational Excel reports plus the Management purchase-control workbook.</p></div><ArrowRight /></Link>
      </section>

      {showPasswordDialog && user?.role === 'management' && (
        <div className="management-password-overlay" role="presentation" onMouseDown={event => {
          if (event.target === event.currentTarget) closePasswordDialog()
        }}>
          <section className="management-password-dialog" role="dialog" aria-modal="true" aria-labelledby="management-password-title">
            <header>
              <div>
                <span>MANAGEMENT SECURITY</span>
                <h2 id="management-password-title">Change Password</h2>
                <p>Changing the password signs this Management account out of all active sessions.</p>
              </div>
              <button type="button" onClick={closePasswordDialog} aria-label="Close password dialog"><X size={20} /></button>
            </header>
            <form onSubmit={changePassword}>
              <label><span>Current Password</span><input type="password" value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} autoComplete="current-password" required autoFocus /></label>
              <label><span>New Password</span><input type="password" value={newPassword} onChange={event => setNewPassword(event.target.value)} autoComplete="new-password" minLength={10} required /></label>
              <label><span>Confirm New Password</span><input type="password" value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} autoComplete="new-password" minLength={10} required /></label>
              <p className="management-password-rules">At least 10 characters with uppercase, lowercase, number, and special character.</p>
              {passwordError && <div className="error-message" role="alert">{passwordError}</div>}
              <div className="management-password-dialog-actions">
                <button type="button" onClick={closePasswordDialog} disabled={changingPassword}>Cancel</button>
                <button type="submit" disabled={changingPassword}>{changingPassword ? 'Changing...' : 'Change Password'}</button>
              </div>
            </form>
          </section>
        </div>
      )}
    </>
  )
}
