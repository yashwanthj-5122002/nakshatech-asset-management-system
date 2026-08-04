import { Building2, KeyRound, Mail, QrCode, ShieldCheck, UserRound } from 'lucide-react'
import { type FormEvent, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch } from '../../../lib/api'
import type { AuthLoginResponse, Branch } from '../../../types'
import { AuthFlowShell } from '../components/AuthFlowShell'

type Step = 'email' | 'otp' | 'details' | 'authenticator'

interface OTPResponse {
  message: string
  expires_in_seconds?: number
  development_otp?: string
}

interface RegistrationVerifyResponse { registration_token: string }
interface MFASetupResponse {
  mfa_setup_token: string
  otpauth_uri: string
  qr_code_data_uri: string
  issuer: string
  account_name: string
}

export function RegisterPage() {
  const navigate = useNavigate()
  const { acceptAuthResponse } = useAuth()
  const [step, setStep] = useState<Step>('email')
  const [branches, setBranches] = useState<Branch[]>([])
  const [email, setEmail] = useState('')
  const [otp, setOtp] = useState('')
  const [developmentOtp, setDevelopmentOtp] = useState('')
  const [registrationToken, setRegistrationToken] = useState('')
  const [mfaSetup, setMfaSetup] = useState<MFASetupResponse | null>(null)
  const [authenticatorCode, setAuthenticatorCode] = useState('')
  const [form, setForm] = useState({
    full_name: '',
    employee_id: '',
    department: '',
    designation: '',
    phone_number: '',
    branch_id: '',
    password: '',
    confirm_password: '',
  })
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    void apiFetch<Branch[]>('/auth/branches').then(items => {
      setBranches(items)
      if (items[0]) setForm(current => ({ ...current, branch_id: String(items[0].id) }))
    }).catch(err => setError(err instanceof Error ? err.message : 'Could not load branches'))
  }, [])

  async function requestOtp(event: FormEvent) {
    event.preventDefault()
    setLoading(true); setError(''); setNotice('')
    try {
      const result = await apiFetch<OTPResponse>('/auth/register/request-otp', {
        method: 'POST', body: JSON.stringify({ email: email.trim() }),
      })
      setDevelopmentOtp(result.development_otp || '')
      setNotice(result.message)
      setStep('otp')
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not send OTP') }
    finally { setLoading(false) }
  }

  async function verifyOtp(event: FormEvent) {
    event.preventDefault()
    setLoading(true); setError(''); setNotice('')
    try {
      const result = await apiFetch<RegistrationVerifyResponse>('/auth/register/verify-otp', {
        method: 'POST', body: JSON.stringify({ email: email.trim(), otp }),
      })
      setRegistrationToken(result.registration_token)
      setStep('details')
    } catch (err) { setError(err instanceof Error ? err.message : 'OTP verification failed') }
    finally { setLoading(false) }
  }

  async function completeRegistration(event: FormEvent) {
    event.preventDefault()
    setError(''); setNotice('')
    if (form.password !== form.confirm_password) { setError('Passwords do not match'); return }
    if (!form.branch_id) { setError('Select a branch'); return }
    setLoading(true)
    try {
      const result = await apiFetch<MFASetupResponse>('/auth/register/complete', {
        method: 'POST',
        body: JSON.stringify({
          registration_token: registrationToken,
          full_name: form.full_name,
          employee_id: form.employee_id,
          department: form.department,
          designation: form.designation || undefined,
          phone_number: form.phone_number || undefined,
          branch_id: Number(form.branch_id),
          password: form.password,
        }),
      })
      setMfaSetup(result)
      setStep('authenticator')
    } catch (err) { setError(err instanceof Error ? err.message : 'Account creation failed') }
    finally { setLoading(false) }
  }

  async function confirmAuthenticator(event: FormEvent) {
    event.preventDefault()
    if (!mfaSetup) return
    setLoading(true); setError(''); setNotice('')
    try {
      const result = await apiFetch<AuthLoginResponse>('/auth/mfa/confirm', {
        method: 'POST',
        body: JSON.stringify({ mfa_setup_token: mfaSetup.mfa_setup_token, code: authenticatorCode }),
      })
      acceptAuthResponse(result, false)
      navigate('/select-branch', { replace: true })
    } catch (err) { setError(err instanceof Error ? err.message : 'Authenticator verification failed') }
    finally { setLoading(false) }
  }

  return (
    <AuthFlowShell
      eyebrow={`FIRST-TIME ACCOUNT · STEP ${step === 'email' ? 1 : step === 'otp' ? 2 : step === 'details' ? 3 : 4} OF 4`}
      title={step === 'email' ? 'Create your CRM account' : step === 'otp' ? 'Verify organization email' : step === 'details' ? 'Complete employee profile' : 'Secure your account'}
      description={step === 'authenticator'
        ? 'Scan the QR code using a free Authenticator app, then enter the current six-digit code.'
        : 'Use only your official @nakshatech.com email. No Software Team approval is required for employee support access.'}
    >
      {step === 'email' && (
        <form className="auth-flow-form" onSubmit={requestOtp}>
          <label className="final-login-field"><span>Organization Email</span><div className="final-login-input-shell"><Mail size={19} /><input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="name@nakshatech.com" autoComplete="email" required /></div></label>
          <div className="auth-flow-info"><ShieldCheck size={18} /><span>A one-time code will be sent to this organization mailbox.</span></div>
          {error && <div className="error-message" role="alert">{error}</div>}
          <button className="final-login-submit" disabled={loading}><span>{loading ? 'Sending code...' : 'Send Email OTP'}</span><i>→</i></button>
        </form>
      )}

      {step === 'otp' && (
        <form className="auth-flow-form" onSubmit={verifyOtp}>
          <div className="auth-flow-info"><Mail size={18} /><span>Code sent to <strong>{email}</strong></span></div>
          {developmentOtp && <div className="auth-flow-dev-code">Local test OTP: <strong>{developmentOtp}</strong></div>}
          <label className="final-login-field"><span>6-digit Email OTP</span><div className="final-login-input-shell"><KeyRound size={19} /><input value={otp} onChange={e => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))} inputMode="numeric" autoComplete="one-time-code" placeholder="000000" required /></div></label>
          {notice && <div className="final-login-notice">{notice}</div>}
          {error && <div className="error-message" role="alert">{error}</div>}
          <button className="final-login-submit" disabled={loading || otp.length !== 6}><span>{loading ? 'Verifying...' : 'Verify Email'}</span><i>→</i></button>
          <button className="auth-flow-text-button" type="button" onClick={() => { setStep('email'); setOtp(''); setError('') }}>Use another email</button>
        </form>
      )}

      {step === 'details' && (
        <form className="auth-flow-form auth-flow-grid-form" onSubmit={completeRegistration}>
          <label className="final-login-field"><span>Full Name</span><div className="final-login-input-shell"><UserRound size={19} /><input value={form.full_name} onChange={e => setForm({ ...form, full_name: e.target.value })} required /></div></label>
          <label className="final-login-field"><span>Employee ID</span><div className="final-login-input-shell"><ShieldCheck size={19} /><input value={form.employee_id} onChange={e => setForm({ ...form, employee_id: e.target.value })} required /></div></label>
          <label className="final-login-field"><span>Department</span><div className="final-login-input-shell"><Building2 size={19} /><input value={form.department} onChange={e => setForm({ ...form, department: e.target.value })} placeholder="Operations / Survey / Accounts" required /></div></label>
          <label className="final-login-field"><span>Designation (optional)</span><div className="final-login-input-shell"><UserRound size={19} /><input value={form.designation} onChange={e => setForm({ ...form, designation: e.target.value })} /></div></label>
          <label className="final-login-field"><span>Mobile Number (optional)</span><div className="final-login-input-shell"><UserRound size={19} /><input value={form.phone_number} onChange={e => setForm({ ...form, phone_number: e.target.value })} placeholder="+91..." /></div></label>
          <label className="final-login-field"><span>Default Branch</span><div className="final-login-input-shell"><Building2 size={19} /><select value={form.branch_id} onChange={e => setForm({ ...form, branch_id: e.target.value })} required>{branches.map(branch => <option key={branch.id} value={branch.id}>{branch.name}</option>)}</select></div></label>
          <label className="final-login-field"><span>Create CRM Password</span><div className="final-login-input-shell"><KeyRound size={19} /><input type="password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} autoComplete="new-password" required /></div></label>
          <label className="final-login-field"><span>Confirm Password</span><div className="final-login-input-shell"><KeyRound size={19} /><input type="password" value={form.confirm_password} onChange={e => setForm({ ...form, confirm_password: e.target.value })} autoComplete="new-password" required /></div></label>
          <p className="auth-flow-password-rule">Use at least 10 characters with uppercase, lowercase, number, and special character.</p>
          {error && <div className="error-message auth-flow-span" role="alert">{error}</div>}
          <button className="final-login-submit auth-flow-span" disabled={loading}><span>{loading ? 'Creating account...' : 'Continue to Phone Authenticator'}</span><i>→</i></button>
        </form>
      )}

      {step === 'authenticator' && mfaSetup && (
        <form className="auth-flow-form" onSubmit={confirmAuthenticator}>
          <div className="auth-flow-qr-card">
            <img src={mfaSetup.qr_code_data_uri} alt="NakshaTech CRM Authenticator QR code" />
            <div><QrCode size={21} /><strong>Scan with Google Authenticator, Microsoft Authenticator, or 2FAS</strong><span>The code is generated on your phone for free. It is not an SMS.</span></div>
          </div>
          <label className="final-login-field"><span>Authenticator Code</span><div className="final-login-input-shell"><ShieldCheck size={19} /><input value={authenticatorCode} onChange={e => setAuthenticatorCode(e.target.value.replace(/\D/g, '').slice(0, 6))} inputMode="numeric" autoComplete="one-time-code" placeholder="000000" required /></div></label>
          {error && <div className="error-message" role="alert">{error}</div>}
          <button className="final-login-submit" disabled={loading || authenticatorCode.length !== 6}><span>{loading ? 'Activating...' : 'Activate Account'}</span><i>→</i></button>
        </form>
      )}
    </AuthFlowShell>
  )
}
