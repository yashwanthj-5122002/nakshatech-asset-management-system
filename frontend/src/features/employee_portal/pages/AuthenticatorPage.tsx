import { QrCode, ShieldCheck } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../../../context/AuthContext'
import { roleHomePath } from '../../../lib/roles'
import { AuthFlowShell } from '../components/AuthFlowShell'

export function AuthenticatorPage() {
  const navigate = useNavigate()
  const { pendingAuth, user, needsBranchSelection, verifyLoginMfa, confirmMfaSetup } = useAuth()
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  if (user) return <Navigate to={needsBranchSelection ? '/select-branch' : roleHomePath(user.role)} replace />
  if (!pendingAuth) return <Navigate to="/login" replace />

  const setupMode = Boolean(pendingAuth.mfaSetupToken)

  async function submit(event: FormEvent) {
    event.preventDefault(); setLoading(true); setError('')
    try {
      const result = setupMode ? await confirmMfaSetup(code) : await verifyLoginMfa(code)
      if (!result.user) throw new Error('Authentication response is incomplete')
      navigate(result.branch_selection_required ? '/select-branch' : roleHomePath(result.user.role), { replace: true })
    } catch (err) { setError(err instanceof Error ? err.message : 'Authenticator verification failed') }
    finally { setLoading(false) }
  }

  return (
    <AuthFlowShell
      eyebrow={setupMode ? 'FREE PHONE AUTHENTICATOR SETUP' : 'TWO-STEP VERIFICATION'}
      title={setupMode ? 'Connect your phone' : 'Enter your phone code'}
      description={setupMode
        ? 'Scan once using an Authenticator app. Future codes are generated on your phone without SMS charges.'
        : `Open the Authenticator app connected to ${pendingAuth.user?.email || 'your account'} and enter the current code.`}
    >
      <form className="auth-flow-form" onSubmit={submit}>
        {setupMode && pendingAuth.qrCodeDataUri && <div className="auth-flow-qr-card">
          <img src={pendingAuth.qrCodeDataUri} alt="NakshaTech CRM Authenticator QR code" />
          <div><QrCode size={21} /><strong>Scan this QR code</strong><span>Google Authenticator, Microsoft Authenticator, and 2FAS are supported.</span></div>
        </div>}
        <label className="final-login-field"><span>6-digit Authenticator Code</span><div className="final-login-input-shell"><ShieldCheck size={19} /><input value={code} onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} inputMode="numeric" autoComplete="one-time-code" placeholder="000000" required autoFocus /></div></label>
        <div className="auth-flow-info"><ShieldCheck size={18} /><span>No SMS is sent. The code refreshes directly inside your phone app.</span></div>
        {error && <div className="error-message" role="alert">{error}</div>}
        <button className="final-login-submit" disabled={loading || code.length !== 6}><span>{loading ? 'Verifying...' : setupMode ? 'Activate Authenticator' : 'Verify & Continue'}</span><i>→</i></button>
      </form>
    </AuthFlowShell>
  )
}
