import {
  ArrowLeft,
  Eye,
  EyeOff,
  LockKeyhole,
  ShieldCheck,
  User,
} from 'lucide-react'
import { type ChangeEvent, type FormEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { roleHomePath } from '../lib/roles'

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [remember, setRemember] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    setError('')
    setNotice('')
    try {
      const result = await login(email.trim(), password, remember)
      if (result.requires_mfa || result.mfa_setup_required) {
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

        <section className="final-login-panel-zone" aria-label="Authorized employee login">
          <form className="final-login-panel" onSubmit={submit}>
            <Link className="final-login-back" to="/">
              <ArrowLeft size={17} aria-hidden="true" />
              <span>Back to welcome</span>
            </Link>

            <div className="final-login-heading">
              <span>Authorized Employee Access</span>
              <h2>Welcome Back</h2>
              <p>Use your organization email and CRM password. New employees can create an account using email OTP.</p>
            </div>

            <div className="final-login-notice" role="status">
              <ShieldCheck size={18} aria-hidden="true" />
              <span>Organization email access is protected by role permissions and optional phone Authenticator verification.</span>
            </div>

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

            {notice && <div className="final-login-notice" role="status">{notice}</div>}
            {error && <div className="error-message" role="alert">{error}</div>}

            <button className="final-login-submit" type="submit" disabled={loading}>
              <span>{loading ? 'Signing in...' : 'Login'}</span>
              <i aria-hidden="true">→</i>
            </button>

            <div className="final-login-create-account">
              <span>First time using the CRM?</span>
              <Link to="/register">Create account with organization email</Link>
            </div>

            <footer>© {new Date().getFullYear()} NakshaTech. All rights reserved.</footer>
          </form>
        </section>
      </div>
    </main>
  )
}
