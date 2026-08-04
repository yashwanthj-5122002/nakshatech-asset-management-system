import { createContext, type ReactNode, useContext, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'
import type { AuthLoginResponse, AuthUser, Branch } from '../types'

interface PendingAuth {
  preAuthToken?: string
  mfaSetupToken?: string
  qrCodeDataUri?: string
  otpAuthUri?: string
  user?: AuthUser
  remember: boolean
}

interface AuthContextValue {
  user: AuthUser | null
  needsBranchSelection: boolean
  pendingAuth: PendingAuth | null
  login: (email: string, password: string, remember: boolean) => Promise<AuthLoginResponse>
  acceptAuthResponse: (result: AuthLoginResponse, remember?: boolean) => void
  verifyLoginMfa: (code: string) => Promise<AuthLoginResponse>
  confirmMfaSetup: (code: string) => Promise<AuthLoginResponse>
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

function readPendingAuth(): PendingAuth | null {
  const raw = sessionStorage.getItem('asset_pending_auth')
  if (!raw) return null
  try { return JSON.parse(raw) as PendingAuth } catch { return null }
}

function clearAuthStorage() {
  for (const storage of [localStorage, sessionStorage]) {
    storage.removeItem('asset_token')
    storage.removeItem('asset_user')
    storage.removeItem('asset_branch_required')
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(readStoredUser)
  const [needsBranchSelection, setNeedsBranchSelection] = useState(readBranchSelectionRequired)
  const [pendingAuth, setPendingAuth] = useState<PendingAuth | null>(readPendingAuth)

  function savePending(pending: PendingAuth | null) {
    setPendingAuth(pending)
    if (pending) sessionStorage.setItem('asset_pending_auth', JSON.stringify(pending))
    else sessionStorage.removeItem('asset_pending_auth')
  }

  function acceptAuthResponse(result: AuthLoginResponse, remember = pendingAuth?.remember ?? false) {
    if (result.requires_mfa || result.mfa_setup_required) {
      savePending({
        preAuthToken: result.pre_auth_token,
        mfaSetupToken: result.mfa_setup_token,
        qrCodeDataUri: result.qr_code_data_uri,
        otpAuthUri: result.otpauth_uri,
        user: result.user,
        remember,
      })
      return
    }
    if (!result.access_token || !result.user) throw new Error('Authentication response is incomplete')
    clearAuthStorage()
    const storage = remember ? localStorage : sessionStorage
    storage.setItem('asset_token', result.access_token)
    storage.setItem('asset_user', JSON.stringify(result.user))
    storage.setItem('asset_branch_required', String(result.branch_selection_required))
    setUser(result.user)
    setNeedsBranchSelection(result.branch_selection_required)
    savePending(null)
  }

  async function login(email: string, password: string, remember: boolean) {
    const result = await apiFetch<AuthLoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
    acceptAuthResponse(result, remember)
    return result
  }

  async function verifyLoginMfa(code: string) {
    if (!pendingAuth?.preAuthToken) throw new Error('The authenticator login session is missing. Sign in again.')
    const result = await apiFetch<AuthLoginResponse>('/auth/mfa/verify-login', {
      method: 'POST',
      body: JSON.stringify({ pre_auth_token: pendingAuth.preAuthToken, code }),
    })
    acceptAuthResponse(result, pendingAuth.remember)
    return result
  }

  async function confirmMfaSetup(code: string) {
    if (!pendingAuth?.mfaSetupToken) throw new Error('The authenticator setup session is missing. Start again.')
    const result = await apiFetch<AuthLoginResponse>('/auth/mfa/confirm', {
      method: 'POST',
      body: JSON.stringify({ mfa_setup_token: pendingAuth.mfaSetupToken, code }),
    })
    acceptAuthResponse(result, pendingAuth.remember)
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
    sessionStorage.removeItem('asset_pending_auth')
    setUser(null)
    setNeedsBranchSelection(false)
    setPendingAuth(null)
  }

  const value = useMemo(
    () => ({
      user,
      needsBranchSelection,
      pendingAuth,
      login,
      acceptAuthResponse,
      verifyLoginMfa,
      confirmMfaSetup,
      selectBranch,
      loadBranches,
      logout,
    }),
    [user, needsBranchSelection, pendingAuth],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
