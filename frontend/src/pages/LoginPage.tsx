import {
  ArrowLeft,
  Eye,
  EyeOff,
  Laptop,
  LockKeyhole,
  ShieldCheck,
  User,
  Users,
} from 'lucide-react'
import { type ChangeEvent, type FormEvent, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { DroneIcon as Drone, type AppIcon } from '../components/DroneIcon'
import { useAuth } from '../context/AuthContext'
import type { Role } from '../types'

const credentialMap: Record<Role, { email: string; password: string; label: string; icon: AppIcon }> = {
  admin: { email: 'admin@nakshatech.com', password: 'Admin@123', label: 'Admin', icon: ShieldCheck },
  management: { email: 'management@nakshatech.com', password: 'Manager@123', label: 'Management', icon: Users },
  it: { email: 'it@nakshatech.com', password: 'IT@123456', label: 'IT', icon: Laptop },
  drone: { email: 'drone@nakshatech.com', password: 'Drone@123', label: 'Drone', icon: Drone },
}

function isRole(value: string | null): value is Role {
  return value === 'admin' || value === 'management' || value === 'it' || value === 'drone'
}

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const requestedRole = searchParams.get('role')
  const initialRole: Role = isRole(requestedRole) ? requestedRole : 'admin'
  const [role, setRole] = useState<Role>(initialRole)
  const [email, setEmail] = useState(credentialMap[initialRole].email)
  const [password, setPassword] = useState(credentialMap[initialRole].password)
  const [showPassword, setShowPassword] = useState(false)
  const [remember, setRemember] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(false)
  const roleItems = useMemo(() => Object.entries(credentialMap) as Array<[Role, typeof credentialMap.admin]>, [])

  useEffect(() => {
    if (isRole(requestedRole)) selectRole(requestedRole)
    // requestedRole is stable for this route load.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedRole])

  function selectRole(nextRole: Role) {
    setRole(nextRole)
    setEmail(credentialMap[nextRole].email)
    setPassword(credentialMap[nextRole].password)
    setError('')
    setNotice('')
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    setError('')
    setNotice('')
    try {
      const user = await login(email.trim(), password, role)
      if (!remember) localStorage.removeItem('asset_user')
      navigate(`/${user.role}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="final-login-screen">
      <div className="final-login-shell">
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

        <section className="final-login-panel-zone" aria-label="Secure role login">
          <form className="final-login-panel" onSubmit={submit}>
            <Link className="final-login-back" to="/">
              <ArrowLeft size={17} aria-hidden="true" />
              <span>Back to welcome</span>
            </Link>

            <div className="final-login-heading">
              <span>Secure Role Access</span>
              <h2>Welcome Back</h2>
              <p>Sign in to continue to your account</p>
            </div>

            <fieldset className="final-login-role-fieldset">
              <legend>Select Role</legend>
              <div className="final-login-role-selector">
                {roleItems.map(([key, item]) => {
                  const Icon = item.icon
                  const selected = role === key
                  return (
                    <button
                      type="button"
                      key={key}
                      className={selected ? 'selected' : ''}
                      onClick={() => selectRole(key)}
                      aria-pressed={selected}
                    >
                      <Icon size={22} strokeWidth={1.8} aria-hidden="true" />
                      <span>{item.label}</span>
                    </button>
                  )
                })}
              </div>
            </fieldset>

            <label className="final-login-field" htmlFor="login-email">
              <span>Email or Username</span>
              <div className="final-login-input-shell">
                <User size={19} aria-hidden="true" />
                <input
                  id="login-email"
                  value={email}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => setEmail(event.target.value)}
                  placeholder="Enter your email or username"
                  autoComplete="username"
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
                <span>Remember me</span>
              </label>
              <button
                type="button"
                onClick={() => {
                  setError('')
                  setNotice('Please contact the NakshaTech system administrator to reset your password.')
                }}
              >
                Forgot password?
              </button>
            </div>

            {notice && <div className="final-login-notice" role="status">{notice}</div>}
            {error && <div className="error-message" role="alert">{error}</div>}

            <button className="final-login-submit" type="submit" disabled={loading}>
              <span>{loading ? 'Signing in...' : 'Login'}</span>
              <i aria-hidden="true">→</i>
            </button>

            <footer>© {new Date().getFullYear()} NakshaTech. All rights reserved.</footer>
          </form>
        </section>
      </div>
    </main>
  )
}
