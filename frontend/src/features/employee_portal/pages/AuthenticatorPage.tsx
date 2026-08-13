import { Eye, EyeOff, LockKeyhole, QrCode, ShieldCheck } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../../../context/AuthContext'
import { roleDisplayName, roleHomePath } from '../../../lib/roles'
import { AuthFlowShell } from '../components/AuthFlowShell'
import '../../../management-auth.css'

export function AuthenticatorPage() {
  const navigate = useNavigate()
  const {
    pendingAuthenticatorSetup,
    user,
    needsBranchSelection,
    confirmRegistrationAuthenticator,
    completePrivilegedPasswordSetup,
  } = useAuth()
  const [code, setCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  if (user) return <Navigate to={needsBranchSelection ? '/select-branch' : roleHomePath(user.role)} replace />
  if (!pendingAuthenticatorSetup) return <Navigate to="/login" replace />

  const passwordStep = Boolean(pendingAuthenticatorSetup.passwordChangeRequired)
  const setupRole = pendingAuthenticatorSetup.user?.role
  const setupRoleName = setupRole ? roleDisplayName(setupRole) : 'Account'
  const privilegedActivation = setupRole === 'management' || setupRole === 'software_team' || setupRole === 'it'

  async function submitAuthenticator(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      const result = await confirmRegistrationAuthenticator(code)
      if (result.password_change_required) {
        setCode('')
        return
      }
      if (!result.user) throw new Error('Authentication response is incomplete')
      navigate(result.branch_selection_required ? '/select-branch' : roleHomePath(result.user.role), { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Authenticator verification failed')
    } finally {
      setLoading(false)
    }
  }

  async function submitPassword(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      const result = await completePrivilegedPasswordSetup(newPassword, confirmPassword)
      if (!result.user) throw new Error('Authentication response is incomplete')
      navigate(roleHomePath(result.user.role), { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Password setup failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthFlowShell
      eyebrow={passwordStep ? `FINAL ${setupRoleName.toUpperCase()} SETUP` : 'FIRST-TIME ACCOUNT ACTIVATION'}
      title={passwordStep ? 'Create your permanent password' : 'Complete Authenticator verification'}
      description={passwordStep
        ? `Authenticator verification is complete. Create the permanent password that will be used for all future ${setupRoleName} logins.`
        : privilegedActivation
          ? `Scan this QR code and enter one current six-digit code. Authenticator verification is required only once during first-time ${setupRoleName} activation.`
          : 'Scan this QR code and enter one current six-digit code to complete account activation.'}
    >
      {passwordStep ? (
        <form className="auth-flow-form" onSubmit={submitPassword}>
          <div className="auth-flow-info management-password-step-info">
            <ShieldCheck size={18} />
            <span>
              Account: <strong>{pendingAuthenticatorSetup.user?.email}</strong>. The temporary password will stop working immediately after this step.
            </span>
          </div>

          <label className="final-login-field" htmlFor="privileged-new-password">
            <span>New Permanent Password</span>
            <div className="final-login-input-shell">
              <LockKeyhole size={19} aria-hidden="true" />
              <input
                id="privileged-new-password"
                type={showPassword ? 'text' : 'password'}
                value={newPassword}
                onChange={event => setNewPassword(event.target.value)}
                autoComplete="new-password"
                placeholder="Create a strong permanent password"
                minLength={10}
                required
                autoFocus
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

          <label className="final-login-field" htmlFor="privileged-confirm-password">
            <span>Confirm New Password</span>
            <div className="final-login-input-shell">
              <LockKeyhole size={19} aria-hidden="true" />
              <input
                id="privileged-confirm-password"
                type={showPassword ? 'text' : 'password'}
                value={confirmPassword}
                onChange={event => setConfirmPassword(event.target.value)}
                autoComplete="new-password"
                placeholder="Re-enter the permanent password"
                minLength={10}
                required
              />
            </div>
          </label>

          <div className="management-password-rules">
            Use at least 10 characters with uppercase, lowercase, number, and special character.
          </div>
          {error && <div className="error-message" role="alert">{error}</div>}
          <button
            className="final-login-submit"
            disabled={loading || newPassword.length < 10 || confirmPassword.length < 10}
          >
            <span>{loading ? 'Completing setup...' : `Create Password & Open ${setupRoleName}`}</span>
            <i>→</i>
          </button>
        </form>
      ) : (
        <form className="auth-flow-form" onSubmit={submitAuthenticator}>
          {pendingAuthenticatorSetup.qrCodeDataUri && <div className="auth-flow-qr-card">
            <img src={pendingAuthenticatorSetup.qrCodeDataUri} alt={`NakshaTech ${setupRoleName} Authenticator QR code`} />
            <div>
              <QrCode size={21} />
              <strong>Scan this QR code</strong>
              <span>Use Google Authenticator, then enter the current six-digit code below.</span>
            </div>
          </div>}
          <label className="final-login-field">
            <span>6-digit Authenticator Code</span>
            <div className="final-login-input-shell">
              <ShieldCheck size={19} />
              <input
                value={code}
                onChange={event => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="000000"
                required
                autoFocus
              />
            </div>
          </label>
          <div className="auth-flow-info">
            <ShieldCheck size={18} />
            <span>
              {privilegedActivation
                ? `After this code is verified, you will create the new permanent ${setupRoleName} password.`
                : 'After this code is verified, your account activation will be completed.'}
            </span>
          </div>
          {error && <div className="error-message" role="alert">{error}</div>}
          <button className="final-login-submit" disabled={loading || code.length !== 6}>
            <span>{loading ? 'Verifying...' : 'Verify & Continue'}</span>
            <i>→</i>
          </button>
        </form>
      )}
    </AuthFlowShell>
  )
}
