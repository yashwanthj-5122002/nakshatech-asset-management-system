import {
  ArrowLeft,
  Eye,
  EyeOff,
  LockKeyhole,
  ShieldCheck,
  User,
} from 'lucide-react'
import { Component, lazy, Suspense, type ChangeEvent, type FormEvent, type ReactNode, useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { NakshaGeoTourOverlay } from '../components/NakshaGeoTourOverlay'
import { useAuth } from '../context/AuthContext'
import { roleHomePath } from '../lib/roles'
import '../management-auth.css'
import '../login-interactive.css'
import '../login-globe.css'

const GEO_TOUR_REPLAY_DELAY_MS = 9000

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

export function LoginPage({ mode = 'privileged' }: { mode?: 'privileged' | 'employee' }) {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const employeeMode = mode === 'employee'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [remember, setRemember] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(false)
  const [showGeoTour, setShowGeoTour] = useState(true)
  const [geoTourRun, setGeoTourRun] = useState(0)
  const shellRef = useRef<HTMLDivElement | null>(null)
  const panelRef = useRef<HTMLFormElement | null>(null)

  useEffect(() => {
    if (showGeoTour) return
    const timer = window.setTimeout(() => {
      setGeoTourRun(run => run + 1)
      setShowGeoTour(true)
    }, GEO_TOUR_REPLAY_DELAY_MS)
    return () => window.clearTimeout(timer)
  }, [showGeoTour])

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

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!email.trim()) {
      setError('Enter your official email or Employee ID.')
      return
    }
    setLoading(true)
    setError('')
    setNotice('')
    try {
      const result = await login(employeeMode ? 'employee' : undefined, email.trim(), password, remember, employeeMode ? 'employee_support' : undefined)
      if (result.mfa_setup_required || result.password_change_required) {
        navigate('/verify-authenticator')
      } else if (result.branch_selection_required) {
        navigate('/select-branch')
      } else if (result.user) {
        const requestedFrom = (location.state as { from?: string } | null)?.from
        const safeRequestedPath = requestedFrom?.startsWith('/') && !requestedFrom.startsWith('//') ? requestedFrom : null
        navigate(safeRequestedPath || roleHomePath(result.user.role))
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
            <span>One Platform.</span>
            <strong>Complete Asset Control.</strong>
          </h1>
          <span className="final-login-copy-rule" aria-hidden="true" />
          <p>Track assets, ownership, operations, requests, and lifecycle activity across NakshaTech.</p>
        </section>

        {showGeoTour
          ? <NakshaGeoTourOverlay key={geoTourRun} onComplete={() => setShowGeoTour(false)} />
          : <LoginGlobeSlot />}

        <section className="final-login-panel-zone" aria-label={employeeMode ? 'Legacy Employee Support login' : 'NakshaTech organization login'}>
          <form className="final-login-panel" ref={panelRef} onSubmit={submit}>
            <Link className="final-login-back" to="/">
              <ArrowLeft size={17} aria-hidden="true" />
              <span>Back to welcome</span>
            </Link>

            <div className="final-login-heading">
              <span>{employeeMode ? 'Employee Support Access' : 'Secure Organization Access'}</span>
              <h2>{employeeMode ? 'Employee Login' : 'Welcome Back'}</h2>
              <p>
                {employeeMode
                  ? 'Legacy Employee Support access is retained for backward compatibility.'
                  : 'Use your NakshaTech email and password. Your workspace opens automatically from your assigned account role.'}
              </p>
            </div>

            <div className="final-login-notice" role="status">
              <ShieldCheck size={18} aria-hidden="true" />
              <span>
                {employeeMode
                  ? 'This compatibility login keeps the existing Employee Support access mode available for old bookmarks and workflows.'
                  : 'One secure login for Management, Admin, IT, Software Team, Drone, Finance, HR, Business Development, Ortho, LiDAR, Civil, Laser Scanning, BIM, Mobile Mapping and Employees. Access permissions are read from your authenticated account — no manual department selection.'}
              </span>
            </div>

            <label className="final-login-field" htmlFor="login-email">
              <span>Official Email or Employee ID</span>
              <div className="final-login-input-shell">
                <User size={19} aria-hidden="true" />
                <input
                  id="login-email"
                  type="text"
                  value={email}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => setEmail(event.target.value)}
                  placeholder="Email address or Employee ID"
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck={false}
                  required
                />
              </div>
            </label>

            <label className="final-login-field" htmlFor="login-password">
              <span>Password</span>
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

            <button className="final-login-submit" type="submit" disabled={loading}>
              <span>{loading ? 'Signing in...' : 'Login'}</span>
              <i aria-hidden="true">→</i>
            </button>

            <div className="final-login-create-account">
              <span>First time using NakshaTech?</span>
              <Link to="/register">Create employee account with organization email</Link>
            </div>

            <footer>© {new Date().getFullYear()} NakshaTech. All rights reserved.</footer>
          </form>
        </section>
      </div>
    </main>
  )
}
