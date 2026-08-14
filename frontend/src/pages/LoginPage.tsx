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
import { NakshaGeoTourOverlay } from '../components/NakshaGeoTourOverlay'
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
  const [showPassword, setShowPassword] = useState(false)
  const [remember, setRemember] = useState(false)
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(false)
  const [privilegedAccounts, setPrivilegedAccounts] = useState<ManagementLoginAccount[]>([])
  const [showGeoTour, setShowGeoTour] = useState(true)
  const shellRef = useRef<HTMLDivElement | null>(null)
  const panelRef = useRef<HTMLFormElement | null>(null)

  useEffect(() => {
    if (!showGeoTour) return
  }, [showGeoTour])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!selectedRole) {
      setError('Select your access role before signing in.')
      return
    }
    setLoading(true)
    setError('')
    try {
      const result = await login(selectedRole, email.trim(), password, remember, employeeMode ? 'employee_support' : undefined)
      if (result.mfa_setup_required || result.password_change_required) navigate('/verify-authenticator')
      else if (result.branch_selection_required) navigate('/select-branch')
      else if (result.user) navigate(roleHomePath(result.user.role))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="final-login-screen">
      <div className="final-login-shell final-login-shell--globe" ref={shellRef}>
        {showGeoTour && <NakshaGeoTourOverlay onComplete={() => setShowGeoTour(false)} />}
        <header className="final-login-header">
          <Link className="final-login-brand" to="/">
            <img src="/nakshatech-horizontal-light.png" alt="NakshaTech" />
            <span className="final-login-brand-divider" />
            <span className="final-login-product-name">Asset Management System</span>
          </Link>
        </header>

        <section className="final-login-copy">
          <h1 id="login-page-title"><span>One Platform.</span><strong>Complete Asset Control.</strong></h1>
          <span className="final-login-copy-rule" />
          <p>Track assets, ownership, operations, requests, and lifecycle activity across NakshaTech.</p>
        </section>

        <LoginGlobeSlot />

        <section className="final-login-panel-zone">
          <form className="final-login-panel" ref={panelRef} onSubmit={submit}>
            <Link className="final-login-back" to="/"><ArrowLeft size={17} /> Back to welcome</Link>
            <div className="final-login-heading">
              <span>{employeeMode ? 'Employee Support Access' : 'Authorized Employee Access'}</span>
              <h2>{employeeMode ? 'Employee Login' : 'Welcome Back'}</h2>
            </div>
            <div className="final-login-notice"><ShieldCheck size={18} /><span>Secure NakshaTech access.</span></div>
            <label className="final-login-field"><span>Email</span><div className="final-login-input-shell"><User size={19}/><input value={email} onChange={(event: ChangeEvent<HTMLInputElement>) => setEmail(event.target.value)} /></div></label>
            <label className="final-login-field"><span>Password</span><div className="final-login-input-shell"><LockKeyhole size={19}/><input type={showPassword ? 'text':'password'} value={password} onChange={(event: ChangeEvent<HTMLInputElement>) => setPassword(event.target.value)} /><button type="button" onClick={() => setShowPassword(!showPassword)}>{showPassword ? <EyeOff/>:<Eye/>}</button></div></label>
            <label><input type="checkbox" checked={remember} onChange={(event) => setRemember(event.target.checked)} /> Remember me</label>
            {notice && <div>{notice}</div>}
            {error && <div className="error-message">{error}</div>}
            <button className="final-login-submit" disabled={loading}>{loading ? 'Signing in...' : 'Login'}</button>
          </form>
        </section>
      </div>
    </main>
  )
}
