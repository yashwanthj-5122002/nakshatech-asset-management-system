import { KeyRound, Mail, ShieldCheck } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../../../lib/api'
import { AuthFlowShell } from '../components/AuthFlowShell'

type Step = 'email' | 'otp' | 'reset' | 'done'

export function ForgotPasswordPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState<Step>('email')
  const [email, setEmail] = useState('')
  const [otp, setOtp] = useState('')
  const [developmentOtp, setDevelopmentOtp] = useState('')
  const [resetToken, setResetToken] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function requestOtp(event: FormEvent) {
    event.preventDefault(); setLoading(true); setError('')
    try {
      const result = await apiFetch<{ message: string; development_otp?: string }>('/auth/forgot-password/request-otp', {
        method: 'POST', body: JSON.stringify({ email: email.trim() }),
      })
      setNotice(result.message); setDevelopmentOtp(result.development_otp || ''); setStep('otp')
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not request reset code') }
    finally { setLoading(false) }
  }

  async function verifyOtp(event: FormEvent) {
    event.preventDefault(); setLoading(true); setError('')
    try {
      const result = await apiFetch<{ reset_token: string }>('/auth/forgot-password/verify-otp', {
        method: 'POST', body: JSON.stringify({ email: email.trim(), otp }),
      })
      setResetToken(result.reset_token); setStep('reset')
    } catch (err) { setError(err instanceof Error ? err.message : 'OTP verification failed') }
    finally { setLoading(false) }
  }

  async function resetPassword(event: FormEvent) {
    event.preventDefault(); setError('')
    if (password !== confirmPassword) { setError('Passwords do not match'); return }
    setLoading(true)
    try {
      const result = await apiFetch<{ message: string }>('/auth/forgot-password/reset', {
        method: 'POST', body: JSON.stringify({ reset_token: resetToken, new_password: password }),
      })
      setNotice(result.message); setStep('done')
    } catch (err) { setError(err instanceof Error ? err.message : 'Password reset failed') }
    finally { setLoading(false) }
  }

  return (
    <AuthFlowShell eyebrow="ACCOUNT RECOVERY" title={step === 'done' ? 'Password changed' : 'Reset your CRM password'} description="Verification uses your NakshaTech organization email. Your existing phone Authenticator remains connected.">
      {step === 'email' && <form className="auth-flow-form" onSubmit={requestOtp}>
        <label className="final-login-field"><span>Organization Email</span><div className="final-login-input-shell"><Mail size={19} /><input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="name@nakshatech.com" required /></div></label>
        {error && <div className="error-message">{error}</div>}
        <button className="final-login-submit" disabled={loading}><span>{loading ? 'Sending...' : 'Send Reset OTP'}</span><i>→</i></button>
      </form>}
      {step === 'otp' && <form className="auth-flow-form" onSubmit={verifyOtp}>
        <div className="auth-flow-info"><Mail size={18} /><span>{notice}</span></div>
        {developmentOtp && <div className="auth-flow-dev-code">Local test OTP: <strong>{developmentOtp}</strong></div>}
        <label className="final-login-field"><span>6-digit Email OTP</span><div className="final-login-input-shell"><KeyRound size={19} /><input value={otp} onChange={e => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))} inputMode="numeric" required /></div></label>
        {error && <div className="error-message">{error}</div>}
        <button className="final-login-submit" disabled={loading || otp.length !== 6}><span>{loading ? 'Verifying...' : 'Verify OTP'}</span><i>→</i></button>
      </form>}
      {step === 'reset' && <form className="auth-flow-form" onSubmit={resetPassword}>
        <label className="final-login-field"><span>New CRM Password</span><div className="final-login-input-shell"><KeyRound size={19} /><input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="new-password" required /></div></label>
        <label className="final-login-field"><span>Confirm New Password</span><div className="final-login-input-shell"><ShieldCheck size={19} /><input type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} autoComplete="new-password" required /></div></label>
        <p className="auth-flow-password-rule">At least 10 characters with uppercase, lowercase, number, and special character.</p>
        {error && <div className="error-message">{error}</div>}
        <button className="final-login-submit" disabled={loading}><span>{loading ? 'Updating...' : 'Set New Password'}</span><i>→</i></button>
      </form>}
      {step === 'done' && <div className="auth-flow-form">
        <div className="auth-flow-success"><ShieldCheck size={26} /><div><strong>Password reset completed</strong><span>All previous CRM sessions were closed. Sign in using your new password and Authenticator code.</span></div></div>
        <button className="final-login-submit" onClick={() => navigate('/login', { replace: true })}><span>Return to Login</span><i>→</i></button>
      </div>}
    </AuthFlowShell>
  )
}
