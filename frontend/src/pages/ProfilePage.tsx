import { CalendarDays, CheckCircle2, KeyRound, Mail, RefreshCcw, ShieldCheck, UserRound, Briefcase, Building2 } from 'lucide-react'
import { type FormEvent, useEffect, useState } from 'react'
import { DashboardHeader } from '../components/DashboardHeader'
import { useAuth } from '../context/AuthContext'
import { apiFetch } from '../lib/api'
import { roleDisplayName } from '../lib/roles'
import type { AuthUser } from '../types'
import '../profile.css'

function formatDate(value?: string | null) {
  if (!value) return 'Not recorded'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Not recorded' : date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

export function ProfilePage() {
  const { user, updateUser } = useAuth()
  const [profile, setProfile] = useState<AuthUser | null>(user)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')

  const [fullName, setFullName] = useState('')
  const [phone, setPhone] = useState('')
  const [dob, setDob] = useState('')
  const [savingProfile, setSavingProfile] = useState(false)
  const [profileNotice, setProfileNotice] = useState('')
  const [profileError, setProfileError] = useState('')

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [savingPassword, setSavingPassword] = useState(false)
  const [passwordNotice, setPasswordNotice] = useState('')
  const [passwordError, setPasswordError] = useState('')

  function applyLoaded(next: AuthUser) {
    setProfile(next)
    setFullName(next.full_name ?? '')
    setPhone(next.phone_number ?? '')
    setDob(next.date_of_birth ? String(next.date_of_birth).slice(0, 10) : '')
  }

  function load() {
    setLoading(true); setLoadError('')
    void apiFetch<AuthUser>('/auth/profile')
      .then(applyLoaded)
      .catch(err => setLoadError(err instanceof Error ? err.message : 'Unable to load your profile'))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  useEffect(() => {
    if (!profileNotice) return
    const handle = window.setTimeout(() => setProfileNotice(''), 6000)
    return () => window.clearTimeout(handle)
  }, [profileNotice])

  useEffect(() => {
    if (!passwordNotice) return
    const handle = window.setTimeout(() => setPasswordNotice(''), 8000)
    return () => window.clearTimeout(handle)
  }, [passwordNotice])

  async function saveProfile(event: FormEvent) {
    event.preventDefault()
    setSavingProfile(true); setProfileError(''); setProfileNotice('')
    try {
      const updated = await apiFetch<AuthUser>('/auth/profile', {
        method: 'PATCH',
        body: JSON.stringify({ full_name: fullName.trim(), phone_number: phone.trim() || null, date_of_birth: dob || null }),
      })
      applyLoaded(updated)
      updateUser(updated)
      setProfileNotice('Profile updated.')
    } catch (err) {
      setProfileError(err instanceof Error ? err.message : 'Unable to update your profile')
    } finally {
      setSavingProfile(false)
    }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault()
    setPasswordError(''); setPasswordNotice('')
    if (newPassword !== confirmPassword) { setPasswordError('New password and confirmation do not match'); return }
    setSavingPassword(true)
    try {
      await apiFetch('/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword, confirm_password: confirmPassword }),
      })
      setCurrentPassword(''); setNewPassword(''); setConfirmPassword('')
      setPasswordNotice('Password changed. You will be signed out on your next action.')
    } catch (err) {
      setPasswordError(err instanceof Error ? err.message : 'Unable to change your password')
    } finally {
      setSavingPassword(false)
    }
  }

  const roleLabel = profile ? roleDisplayName(profile.role) : ''

  return <div className="profile-page">
    <DashboardHeader
      eyebrow="MY ACCOUNT"
      title="User Profile"
      description="Review your account details, keep your contact information current, and change your password."
      actions={<button className="secondary-button" onClick={load}><RefreshCcw size={16} /> Refresh</button>}
    />

    {loadError && <div className="profile-alert error" aria-live="polite">{loadError}<button className="secondary-button" onClick={load}>Retry</button></div>}
    {loading && <section className="panel"><div className="profile-empty"><span className="profile-spinner" /> Loading your profile…</div></section>}

    {profile && !loading && <>
      <section className="panel profile-identity">
        <div className="profile-avatar">{(profile.full_name || '?').charAt(0).toUpperCase()}</div>
        <div className="profile-identity-copy">
          <span className="section-kicker">{roleLabel.toUpperCase()}</span>
          <h2>{profile.full_name}</h2>
          <p>{profile.designation || roleLabel} · {profile.branch || 'Head Office'}</p>
        </div>
        <span className={`profile-status ${profile.email_verified ? 'verified' : 'pending'}`}>
          <ShieldCheck size={14} /> {profile.email_verified ? 'Email verified' : 'Email not verified'}
        </span>
      </section>

      <div className="profile-columns">
        <section className="panel">
          <div className="panel-heading"><div><span className="section-kicker">ACCOUNT DETAILS</span><h2>Your Information</h2></div></div>
          <div className="profile-detail-grid">
            <div><span><UserRound size={13} /> Full Name</span><strong>{profile.full_name || '—'}</strong></div>
            <div><span><Mail size={13} /> Official Email</span><strong>{profile.email}</strong></div>
            <div><span><Briefcase size={13} /> Employee ID</span><strong>{profile.employee_id || 'Not assigned'}</strong></div>
            <div><span><Building2 size={13} /> Department</span><strong>{profile.department || 'Not assigned'}</strong></div>
            <div><span>Designation</span><strong>{profile.designation || 'Not assigned'}</strong></div>
            <div><span>Branch</span><strong>{profile.selected_branch_name || profile.branch || 'Head Office'}</strong></div>
            <div><span><CalendarDays size={13} /> Joining Date</span><strong>{formatDate(profile.joining_date)}</strong></div>
            <div><span><CalendarDays size={13} /> Date of Birth</span><strong>{formatDate(profile.date_of_birth)}</strong></div>
            <div><span>Phone Number</span><strong>{profile.phone_number || 'Not recorded'}</strong></div>
            <div><span>Member Since</span><strong>{formatDate(profile.created_at)}</strong></div>
          </div>
          <p className="profile-hint">Email, Employee ID, Department, Designation, Branch and Joining Date are managed by your administrator. Contact IT Support to change them.</p>
        </section>

        <section className="panel">
          <div className="panel-heading"><div><span className="section-kicker">EDIT PROFILE</span><h2>Update Your Details</h2></div></div>
          {profileNotice && <div className="profile-alert success" aria-live="polite"><CheckCircle2 size={15} /> {profileNotice}</div>}
          {profileError && <div className="profile-alert error" aria-live="polite">{profileError}</div>}
          <form className="profile-form" onSubmit={saveProfile}>
            <label className="profile-field"><span>Full Name *</span>
              <input required value={fullName} onChange={e => setFullName(e.target.value)} />
            </label>
            <label className="profile-field"><span>Phone Number</span>
              <input value={phone} onChange={e => setPhone(e.target.value)} placeholder="Contact number" />
            </label>
            <label className="profile-field"><span>Date of Birth</span>
              <input type="date" value={dob} max={new Date().toISOString().slice(0, 10)} onChange={e => setDob(e.target.value)} />
            </label>
            <div className="profile-form-actions">
              <button className="primary-button" disabled={savingProfile}>{savingProfile ? 'Saving…' : 'Save Changes'}</button>
            </div>
          </form>
        </section>
      </div>

      <section className="panel">
        <div className="panel-heading"><div><span className="section-kicker">SECURITY</span><h2>Change Password</h2><p>Use at least 8 characters. You will be signed out after changing your password.</p></div></div>
        {passwordNotice && <div className="profile-alert success" aria-live="polite"><CheckCircle2 size={15} /> {passwordNotice}</div>}
        {passwordError && <div className="profile-alert error" aria-live="polite">{passwordError}</div>}
        <form className="profile-form" onSubmit={changePassword}>
          <label className="profile-field"><span>Current Password *</span>
            <input required type="password" autoComplete="current-password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} />
          </label>
          <label className="profile-field"><span>New Password *</span>
            <input required type="password" autoComplete="new-password" minLength={8} value={newPassword} onChange={e => setNewPassword(e.target.value)} />
          </label>
          <label className="profile-field"><span>Confirm New Password *</span>
            <input required type="password" autoComplete="new-password" minLength={8} value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} />
          </label>
          <div className="profile-form-actions">
            <button className="primary-button" disabled={savingPassword}><KeyRound size={15} /> {savingPassword ? 'Changing…' : 'Change Password'}</button>
          </div>
        </form>
      </section>
    </>}
  </div>
}
