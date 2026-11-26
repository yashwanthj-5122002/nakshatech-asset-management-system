import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { BriefcaseBusiness, Eye, EyeOff, LockKeyhole, UserRound } from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import './bd-employee.css'

export function BDEmployeeLoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [remember, setRemember] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setPending(true)
    try {
      const result = await login('bd_employee', identifier.trim(), password, remember)
      if (result.user?.role !== 'bd_employee') {
        setError('This login is reserved for BD employees.')
        return
      }
      if (result.password_change_required || result.mfa_setup_required) {
        navigate('/verify-authenticator')
      } else if (result.branch_selection_required) {
        navigate('/select-branch')
      } else {
        navigate('/bd-employee', { replace: true })
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Unable to sign in')
    } finally {
      setPending(false)
    }
  }

  return <main className="bde-login-screen">
    <div className="bde-login-card">
      <Link to="/" className="bde-login-brand"><BriefcaseBusiness size={26} /> NakshaTech ERP</Link>
      <span className="bde-overline">BUSINESS DEVELOPMENT · EMPLOYEE PORTAL</span>
      <h1>Welcome to your BD workspace.</h1>
      <p>Track every prospect, conversation, reply and follow-up in one place.</p>
      <form onSubmit={signIn} className="bde-form">
        <label>Employee ID or internal login email
          <span className="bde-input-icon"><UserRound size={18} /><input autoComplete="username" placeholder="BD001 or bd001@nakshatech.com" value={identifier} onChange={e => setIdentifier(e.target.value)} required maxLength={255} /></span>
        </label>
        <label>Password
          <span className="bde-input-icon"><LockKeyhole size={18} /><input autoComplete="current-password" type={showPassword ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)} required minLength={6} />
            <button type="button" className="bde-show" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? 'Hide password' : 'Show password'}>{showPassword ? <EyeOff size={18}/> : <Eye size={18}/>}</button></span>
        </label>
        <label className="bde-check"><input type="checkbox" checked={remember} onChange={e=>setRemember(e.target.checked)}/> Remember on this device</label>
        {error && <p className="bde-error" role="alert">{error}</p>}
        <button className="bde-primary" disabled={pending} type="submit">{pending ? 'Signing in…' : 'Sign in to BD workspace'}</button>
      </form>
      <Link className="bde-back" to="/login">Other department login</Link>
    </div>
  </main>
}
