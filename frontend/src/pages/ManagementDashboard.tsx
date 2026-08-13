import { ArrowRight, ClipboardCheck, FileBarChart, HardDrive, KeyRound, Repeat2, X } from 'lucide-react'
import { DroneIcon as Drone } from '../components/DroneIcon'
import { type FormEvent, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { DashboardHeader } from '../components/DashboardHeader'
import { StatCard } from '../components/StatCard'
import { useAuth } from '../context/AuthContext'
import { apiFetch } from '../lib/api'
import type { DashboardSummary } from '../types'
import '../management-auth.css'

export function ManagementDashboard() {
  const navigate = useNavigate()
  const { logout } = useAuth()
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [showPasswordDialog, setShowPasswordDialog] = useState(false)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordError, setPasswordError] = useState('')
  const [changingPassword, setChangingPassword] = useState(false)

  useEffect(() => { void apiFetch<DashboardSummary>('/dashboard/summary').then(setSummary) }, [])

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

  return (
    <>
      <DashboardHeader
        eyebrow="MONITOR & MANAGE"
        title="Management Dashboard"
        description="A combined decision view for IT assets, drone operations, work progress, approvals and management reports."
        actions={(
          <button className="management-change-password-button" type="button" onClick={() => setShowPasswordDialog(true)}>
            <KeyRound size={18} />
            <span>Change Password</span>
          </button>
        )}
      />
      <section className="stats-grid">
        <StatCard icon={HardDrive} label="IT Assets" value={summary?.assets_total ?? '—'} />
        <StatCard icon={Drone} label="Drone Fleet" value={summary?.drones_total ?? '—'} tone="cyan" />
        <StatCard icon={ClipboardCheck} label="Open Work" value={summary?.pending_work ?? '—'} tone="orange" />
        <StatCard icon={Repeat2} label="Approval Workflows" value="Active" tone="purple" />
      </section>
      <section className="management-cards">
        <Link to="/it"><HardDrive /><div><span className="section-kicker">IT OVERVIEW</span><h2>Open IT Dashboard</h2><p>Inventory condition, repairs, replacements, departments and work records.</p></div><ArrowRight /></Link>
        <Link to="/drone"><Drone /><div><span className="section-kicker">DRONE OVERVIEW</span><h2>Open Drone Dashboard</h2><p>Fleet deployment, pilot, projects, battery and last known location.</p></div><ArrowRight /></Link>
        <Link to="/it/purchase-requests"><ClipboardCheck /><div><span className="section-kicker">PURCHASE APPROVAL</span><h2>Purchase Order Approval</h2><p>Review, approve, reject, or send back purchase requests with complete decision history.</p></div><ArrowRight /></Link>
        <Link to="/reports"><FileBarChart /><div><span className="section-kicker">REPORTING</span><h2>Download Reports</h2><p>Export current asset and dashboard Excel workbooks.</p></div><ArrowRight /></Link>
      </section>

      {showPasswordDialog && (
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
              <button type="button" onClick={closePasswordDialog} aria-label="Close password dialog">
                <X size={20} />
              </button>
            </header>

            <form onSubmit={changePassword}>
              <label>
                <span>Current Password</span>
                <input
                  type="password"
                  value={currentPassword}
                  onChange={event => setCurrentPassword(event.target.value)}
                  autoComplete="current-password"
                  required
                  autoFocus
                />
              </label>
              <label>
                <span>New Password</span>
                <input
                  type="password"
                  value={newPassword}
                  onChange={event => setNewPassword(event.target.value)}
                  autoComplete="new-password"
                  minLength={10}
                  required
                />
              </label>
              <label>
                <span>Confirm New Password</span>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={event => setConfirmPassword(event.target.value)}
                  autoComplete="new-password"
                  minLength={10}
                  required
                />
              </label>
              <p className="management-password-rules">At least 10 characters with uppercase, lowercase, number, and special character.</p>
              {passwordError && <div className="error-message" role="alert">{passwordError}</div>}
              <div className="management-password-dialog-actions">
                <button type="button" onClick={closePasswordDialog} disabled={changingPassword}>Cancel</button>
                <button type="submit" disabled={changingPassword}>
                  {changingPassword ? 'Changing...' : 'Change Password'}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </>
  )
}
