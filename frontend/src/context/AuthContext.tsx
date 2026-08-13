import { createContext, type ReactNode, useContext, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'
import type { AuthLoginResponse, AuthUser, Branch, Role } from '../types'

interface PendingAuthenticatorSetup {
  mfaSetupToken?: string
  passwordChangeRequired?: boolean
  passwordChangeToken?: string
  qrCodeDataUri?: string
  otpAuthUri?: string
  user?: AuthUser
  remember: boolean
}

interface AuthContextValue {
  user: AuthUser | null
  needsBranchSelection: boolean
  pendingAuthenticatorSetup: PendingAuthenticatorSetup | null
  login: (role: Role, email: string, password: string, remember: boolean, accessMode?: 'employee_support') => Promise<AuthLoginResponse>
  acceptAuthResponse: (result: AuthLoginResponse, remember?: boolean) => void
  confirmRegistrationAuthenticator: (code: string) => Promise<AuthLoginResponse>
  completePrivilegedPasswordSetup: (newPassword: string, confirmPassword: string) => Promise<AuthLoginResponse>
  selectBranch: (branchId: number) => Promise<AuthLoginResponse>
  loadBranches: () => Promise<Branch[]>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

function readStoredUser(): AuthUser | null {
  const raw = localStorage.getItem('asset_user') ?? sessionStorage.getItem('asset_user')
  if (!raw) return null
  try { return JSON.parse(raw) as AuthUser } catch { return null }
}

function readBranchSelectionRequired(): boolean {
  const raw = localStorage.getItem('asset_branch_required') ?? sessionStorage.getItem('asset_branch_required')
  return raw === 'true'
}

function readPendingAuthenticatorSetup(): PendingAuthenticatorSetup | null {
  const raw = sessionStorage.getItem('asset_pending_authenticator_setup')
  if (!raw) return null
  try { return JSON.parse(raw) as PendingAuthenticatorSetup } catch { return null }
}

function clearAuthStorage() {
  for (const storage of [localStorage, sessionStorage]) {
    storage.removeItem('asset_token')
    storage.removeItem('asset_user')
    storage.removeItem('asset_branch_required')
  }
  sessionStorage.removeItem('asset_pending_auth')
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(readStoredUser)
  const [needsBranchSelection, setNeedsBranchSelection] = useState(readBranchSelectionRequired)
  const [pendingAuthenticatorSetup, setPendingAuthenticatorSetup] = useState<PendingAuthenticatorSetup | null>(readPendingAuthenticatorSetup)

  function savePendingAuthenticatorSetup(pending: PendingAuthenticatorSetup | null) {
    setPendingAuthenticatorSetup(pending)
    if (pending) sessionStorage.setItem('asset_pending_authenticator_setup', JSON.stringify(pending))
    else sessionStorage.removeItem('asset_pending_authenticator_setup')
  }

  function acceptAuthResponse(result: AuthLoginResponse, remember = false) {
    if (result.mfa_setup_required || result.password_change_required) {
      if (result.mfa_setup_required && !result.mfa_setup_token) {
        throw new Error('Authenticator setup response is incomplete')
      }
      if (result.password_change_required && !result.password_change_token) {
        throw new Error('Password setup response is incomplete')
      }
      savePendingAuthenticatorSetup({
        ...pendingAuthenticatorSetup,
        mfaSetupToken: result.mfa_setup_token ?? pendingAuthenticatorSetup?.mfaSetupToken,
        passwordChangeRequired: result.password_change_required,
        passwordChangeToken: result.password_change_token ?? pendingAuthenticatorSetup?.passwordChangeToken,
        qrCodeDataUri: result.qr_code_data_uri ?? pendingAuthenticatorSetup?.qrCodeDataUri,
        otpAuthUri: result.otpauth_uri ?? pendingAuthenticatorSetup?.otpAuthUri,
        user: result.user ?? pendingAuthenticatorSetup?.user,
        remember,
      })
      return
    }

    if (result.requires_mfa) {
      throw new Error('Authenticator codes are not required for normal sign-in. Please refresh and sign in again.')
    }

    if (!result.access_token || !result.user) throw new Error('Authentication response is incomplete')
    clearAuthStorage()
    const storage = remember ? localStorage : sessionStorage
    storage.setItem('asset_token', result.access_token)
    storage.setItem('asset_user', JSON.stringify(result.user))
    storage.setItem('asset_branch_required', String(result.branch_selection_required))
    setUser(result.user)
    setNeedsBranchSelection(result.branch_selection_required)
    savePendingAuthenticatorSetup(null)
  }

  async function login(role: Role, email: string, password: string, remember: boolean, accessMode?: 'employee_support') {
    const result = await apiFetch<AuthLoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ role, email, password, access_mode: accessMode }),
    })
    acceptAuthResponse(result, remember)
    return result
  }

  async function confirmRegistrationAuthenticator(code: string) {
    if (!pendingAuthenticatorSetup?.mfaSetupToken) {
      throw new Error('The account activation session is missing. Sign in again to resume setup.')
    }
    const result = await apiFetch<AuthLoginResponse>('/auth/mfa/confirm', {
      method: 'POST',
      body: JSON.stringify({ mfa_setup_token: pendingAuthenticatorSetup.mfaSetupToken, code }),
    })
    acceptAuthResponse(result, pendingAuthenticatorSetup.remember)
    return result
  }

  async function completePrivilegedPasswordSetup(newPassword: string, confirmPassword: string) {
    if (!pendingAuthenticatorSetup?.passwordChangeToken) {
      throw new Error('The privileged account password setup session is missing. Sign in again to resume setup.')
    }
    const result = await apiFetch<AuthLoginResponse>('/auth/privileged/complete-setup', {
      method: 'POST',
      body: JSON.stringify({
        password_change_token: pendingAuthenticatorSetup.passwordChangeToken,
        new_password: newPassword,
        confirm_password: confirmPassword,
      }),
    })
    acceptAuthResponse(result, pendingAuthenticatorSetup.remember)
    return result
  }

  async function selectBranch(branchId: number) {
    const result = await apiFetch<AuthLoginResponse>('/auth/select-branch', {
      method: 'POST',
      body: JSON.stringify({ branch_id: branchId }),
    })
    acceptAuthResponse(result, localStorage.getItem('asset_token') !== null)
    return result
  }

  async function loadBranches() {
    return apiFetch<Branch[]>(user ? '/auth/my-branches' : '/auth/branches')
  }

  function logout() {
    void apiFetch('/auth/logout', { method: 'POST' }).catch(() => undefined)
    clearAuthStorage()
    sessionStorage.removeItem('asset_pending_authenticator_setup')
    setUser(null)
    setNeedsBranchSelection(false)
    setPendingAuthenticatorSetup(null)
  }

  const value = useMemo(
    () => ({
      user,
      needsBranchSelection,
      pendingAuthenticatorSetup,
      login,
      acceptAuthResponse,
      confirmRegistrationAuthenticator,
      completePrivilegedPasswordSetup,
      selectBranch,
      loadBranches,
      logout,
    }),
    [user, needsBranchSelection, pendingAuthenticatorSetup],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
