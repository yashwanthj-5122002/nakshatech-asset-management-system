import {
  ArrowLeft,
  Eye,
  EyeOff,
  LockKeyhole,
  ShieldCheck,
  User,
} from 'lucide-react'
import { Component, lazy, Suspense, type ChangeEvent, type FormEvent, type ReactNode, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { apiFetch } from '../lib/api'
import { roleDisplayName, roleHomePath } from '../lib/roles'
import type { ManagementLoginAccount, Role } from '../types'
import '../management-auth.css'
import '../login-interactive.css'
import '../login-globe.css'

const PRIVILEGED_LOGIN_ROLES: Role[] = ['management', 'it', 'software_team', 'drone', 'admin']
const PROVISIONED_LOGIN_ROLES: Role[] = ['management', 'it', 'software_team']

const LazyNakshaInteractiveGlobe = lazy(async () => {
  const module = await import('../components/NakshaInteractiveGlobe')
  return { default: module.NakshaInteractiveGlobe }
})

class LoginGlobeLoadBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    if (this.state.failed) {
      return (
        <div className="naksha-login-globe-fallback" role="status">
          <strong>Interactive globe unavailable</strong>
          <span>The secure login form is still fully available.</span>
        </div>
      )
    }
    return this.props.children
  }
}

function LoginGlobeSlot() {
  return (
    <LoginGlobeLoadBoundary>
      <Suspense fallback={<div className="naksha-login-globe-fallback naksha-login-globe-fallback--loading" aria-hidden="true" />}>
        <LazyNakshaInteractiveGlobe />
      </Suspense>
    </LoginGlobeLoadBoundary>
  )
}

function usesProvisionedSelector(role: Role | ''): role is Role {
  return Boolean(role && PROVISIONED_LOGIN_ROLES.includes(role))
}

export function LoginPage({ mode = 'privileged' }: { mode?: 'privileged' | 'employee' }) {
  const { login } = useAuth()
  const navigate = useNavigate()
  const employeeMode = mode === 'employee'
  const [selectedRole, setSelectedRole] = useState<Role | ''>(employeeMode ? 'employee' : '')
  const [privilegedAccounts, setPrivilegedAccounts] = useState<ManagementLoginAccount[]>([])
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [remember, setRemember] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(false)
  const shellRef = useRef<HTMLDivElement | null>(null)
  const panelRef = useRef<HTMLFormElement | null>(null)

  useEffect(() => {
    const shell = shellRef.current
    const panel = panelRef.current
    if (!shell || !panel || typeof window === 'undefined') return

    const finePointer = window.matchMedia('(pointer: fine)')
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (!finePointer.matches || reducedMotion.matches) return

    let animationFrame = 0
    const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))

    const updateInteraction = (event: PointerEvent) => {
      const target = event.target instanceof Element ? event.target : null
      if (target?.closest('.naksha-login-globe')) {
        if (animationFrame) {
          window.cancelAnimationFrame(animationFrame)
          animationFrame = 0
        }
        panel.style.setProperty('--login-panel-x', '50%')
        panel.style.setProperty('--login-panel-y', '50%')
        panel.style.setProperty('--login-tilt-x', '0deg')
        panel.style.setProperty('--login-tilt-y', '0deg')
        return
      }
      if (animationFrame) window.cancelAnimationFrame(animationFrame)
      animationFrame = window.requestAnimationFrame(() => {
        const shellRect = shell.getBoundingClientRect()
        const shellX = clamp(event.clientX - shellRect.left, 0, shellRect.width)
        const shellY = clamp(event.clientY - shellRect.top, 0, shellRect.height)
        const normalizedX = shellRect.width ? (shellX / shellRect.width) * 2 - 1 : 0
        const normalizedY = shellRect.height ? (shellY / shellRect.height) * 2 - 1 : 0

        const panelRect = panel.getBoundingClientRect()
        const panelX = panelRect.width ? clamp(((event.clientX - panelRect.left) / panelRect.width) * 100, 0, 100) : 50
        const panelY = panelRect.height ? clamp(((event.clientY - panelRect.top) / panelRect.height) * 100, 0, 100) : 50
        const panelNX = panelRect.width ? clamp((event.clientX - (panelRect.left + panelRect.width / 2)) / (panelRect.width / 2), -1, 1) : 0
        const panelNY = panelRect.height ? clamp((event.clientY - (panelRect.top + panelRect.height / 2)) / (panelRect.height / 2), -1, 1) : 0

        shell.style.setProperty('--login-shift-x', `${normalizedX * 7}px`)
        shell.style.setProperty('--login-shift-y', `${normalizedY * 4}px`)
        shell.style.setProperty('--login-panel-x', `${panelX}%`)
        shell.style.setProperty('--login-panel-y', `${panelY}%`)
        shell.style.setProperty('--login-tilt-x', `${panelNY * -0.8}deg`)
        shell.style.setProperty('--login-tilt-y', `${panelNX * 1.15}deg`)
      })
    }

    const resetInteraction = () => {
      shell.style.setProperty('--login-shift-x', '0px')
      shell.style.setProperty('--login-shift-y', '0px')
      shell.style.setProperty('--login-panel-x', '50%')
      shell.style.setProperty('--login-panel-y', '50%')
      shell.style.setProperty('--login-tilt-x', '0deg')
      shell.style.setProperty('--login-tilt-y', '0deg')
    }

    shell.addEventListener('pointermove', updateInteraction, { passive: true })
    shell.addEventListener('pointerleave', resetInteraction)

    return () => {
      if (animationFrame) window.cancelAnimationFrame(animationFrame)
      shell.removeEventListener('pointermove', updateInteraction)
      shell.removeEventListener('pointerleave', resetInteraction)
    }
  }, [employeeMode])

  useEffect(() => {
    setSelectedRole(employeeMode ? 'employee' : '')
    setEmail('')
    setPassword('')
    setError('')
  }, [employeeMode])

  useEffect(() => {
    const message = sessionStorage.getItem('management_password_changed')
    if (message) {
      setNotice(message)
      sessionStorage.removeItem('management_password_changed')
    }
  }, [])

  useEffect(() => {
    setPrivilegedAccounts([])
    if (!usesProvisionedSelector(selectedRole)) return
    const role = selectedRole
    let cancelled = false
    void apiFetch<{ accounts: ManagementLoginAccount[] }>(`/auth/privileged/accounts?role=${encodeURIComponent(role)}`)
      .then(result => { if (!cancelled) setPrivilegedAccounts(result.accounts) })
      .catch(err => {
        if (!cancelled) setError(err instanceof Error ? err.message : `Unable to load ${roleDisplayName(role)} account`)
      })
    return () => { cancelled = true }
  }, [selectedRole])

  function selectRole(role: Role) {
    setSelectedRole(role)
    setEmail('')
    setPassword('')
    setError('')
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!selectedRole) {
      setError('Select your access role before signing in.')
      return
    }
    if (!email.trim()) {
      setError(usesProvisionedSelector(selectedRole) ? `Select the ${roleDisplayName(selectedRole)} user.` : 'Enter your official email.')
      return
    }
    setLoading(true)
    setError('')
    setNotice('')
    try {
      const result = await login(selectedRole, email.trim(), password, remember, employeeMode ? 'employee_support' : undefined)
      if (result.mfa_setup_required || result.password_change_required) {
        navigate('/verify-authenticator')
      } else if (result.branch_selection_required) {
        navigate('/select-branch')
      } else if (result.user) {
        navigate(roleHomePath(result.user.role))
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="final-login-screen">
      <div className="final-login-shell final-login-shell--globe" ref={shellRef}>
        <header className="final-login-header">
          <Link className="final-login-brand" to="/" aria-label="Return to NakshaTech Asset Management welcome page">
            <img src="/nakshatech-horizontal-light.png" alt="NakshaTech" />
            <span className="final-login-brand-divider" aria-hidden="true" />
            <span className="final-login-product-name">Asset Management System</span>
          </Link>
        </header>

        <section className="final-login-copy" aria-labelledby="login-page-title">
          <h1 id="login-page-title">
            <span>Smart Internal</span>
            <strong>Asset Management</strong>
          </h1>
          <span className="final-login-copy-rule" aria-hidden="true" />
          <p>Manage IT assets, drone operations, workflows, and admin visibility — all in one intelligent platform.</p>
        </section>

        <LoginGlobeSlot />

        <section className="final-login-panel-zone" aria-label={employeeMode ? 'Employee Support login' : 'Authorized employee login'}>
          <form className="final-login-panel" ref={panelRef} onSubmit={submit}>
            <Link className="final-login-back" to="/">
              <ArrowLeft size={17} aria-hidden="true" />
              <span>Back to welcome</span>
            </Link>

            <div className="final-login-heading">
              <span>{employeeMode ? 'Employee Support Access' : 'Authorized Employee Access'}</span>
              <h2>{employeeMode ? 'Employee Login' : 'Welcome Back'}</h2>
              <p>{employeeMode ? 'Sign in to raise and track your own support tickets.' : 'Select your assigned role, then use the credentials issued for that role.'}</p>
            </div>

            {!employeeMode && (
              <fieldset className="management-role-picker">
                <legend>Select Access Role</legend>
                <div>
                  {PRIVILEGED_LOGIN_ROLES.map(role => (
                    <button
                      key={role}
                      type="button"
                      className={selectedRole === role ? 'selected' : ''}
                      onClick={() => selectRole(role)}
                      aria-pressed={selectedRole === role}
                    >
                      {roleDisplayName(role)}
                    </button>
                  ))}
                </div>
              </fieldset>
            )}

            <div className="final-login-notice" role="status">
              <ShieldCheck size={18} aria-hidden="true" />
              <span>
                {employeeMode
                  ? 'Employee Support sign-in uses your organization email and password. Authorized Management users may also sign in here to raise their own support tickets with Employee-level permissions.'
                  : selectedRole === 'management'
                  ? 'Management access is restricted to Vinod and Chethan. First login uses the issued temporary password, one Authenticator verification, and then a new permanent password.'
                  : selectedRole === 'software_team'
                    ? 'Software Team access is restricted to software.team@nakshatech.com and uses the same controlled first-login activation.'
                    : selectedRole === 'it'
                      ? 'IT access is restricted to it-support@nakshatech.com and uses the same controlled first-login activation.'
                      : 'Normal sign-in uses your organization email and password. Account creation is available only for Employee Support users.'}
              </span>
            </div>

            {usesProvisionedSelector(selectedRole) ? (
              <label className="final-login-field" htmlFor="privileged-login-email">
                <span>Select User</span>
                <div className="final-login-input-shell management-account-select">
                  <User size={19} aria-hidden="true" />
                  <select
                    id="privileged-login-email"
                    value={email}
                    onChange={(event: ChangeEvent<HTMLSelectElement>) => setEmail(event.target.value)}
                    required
                  >
                    <option value="">Select User</option>
                    {privilegedAccounts.map(account => (
                      <option key={account.email} value={account.email}>
                        {account.display_name} — {account.email}
                      </option>
                    ))}
                  </select>
                </div>
              </label>
            ) : (
              <label className="final-login-field" htmlFor="login-email">
                <span>Official Email</span>
                <div className="final-login-input-shell">
                  <User size={19} aria-hidden="true" />
                  <input
                    id="login-email"
                    type="email"
                    value={email}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => setEmail(event.target.value)}
                    placeholder="Enter your official email"
                    autoComplete="username"
                    autoCapitalize="none"
                    spellCheck={false}
                    required
                    disabled={!selectedRole}
                  />
                </div>
              </label>
            )}

            <label className="final-login-field" htmlFor="login-password">
              <span>{usesProvisionedSelector(selectedRole) ? 'Temporary or Permanent Password' : 'Password'}</span>
              <div className="final-login-input-shell">
                <LockKeyhole size={19} aria-hidden="true" />
                <input
                  id="login-password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => setPassword(event.target.value)}
                  placeholder="Enter your password"
                  autoComplete="current-password"
                  required
                  disabled={!selectedRole}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(value => !value)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </label>

            <div className="final-login-options">
              <label>
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => setRemember(event.target.checked)}
                />
                <span>Remember me on this device</span>
              </label>
              <Link to="/forgot-password">Forgot password?</Link>
            </div>

            {notice && <div className="final-login-notice management-success-notice" role="status">{notice}</div>}
            {error && <div className="error-message" role="alert">{error}</div>}

            <button className="final-login-submit" type="submit" disabled={loading || !selectedRole}>
              <span>{loading ? 'Signing in...' : 'Login'}</span>
              <i aria-hidden="true">→</i>
            </button>

            {employeeMode ? (
              <div className="final-login-create-account">
                <span>First time using Employee Support?</span>
                <Link to="/register">Create account with organization email</Link>
              </div>
            ) : selectedRole ? (
              <div className="management-provisioned-note">This role is provisioned by NakshaTech. Public sign-up is disabled.</div>
            ) : null}

            <footer>© {new Date().getFullYear()} NakshaTech. All rights reserved.</footer>
          </form>
        </section>
      </div>
    </main>
  )
}
