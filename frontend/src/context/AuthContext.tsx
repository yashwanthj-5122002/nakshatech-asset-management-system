import { createContext, type ReactNode, useContext, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'
import type { AuthUser } from '../types'

interface AuthContextValue {
  user: AuthUser | null
  login: (email: string, password: string, remember: boolean) => Promise<AuthUser>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

function readStoredUser(): AuthUser | null {
  const raw = localStorage.getItem('asset_user') ?? sessionStorage.getItem('asset_user')
  if (!raw) return null
  try { return JSON.parse(raw) as AuthUser } catch { return null }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(readStoredUser)

  async function login(email: string, password: string, remember: boolean) {
    const result = await apiFetch<{ access_token: string; user: AuthUser }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })

    localStorage.removeItem('asset_token')
    localStorage.removeItem('asset_user')
    sessionStorage.removeItem('asset_token')
    sessionStorage.removeItem('asset_user')

    const storage = remember ? localStorage : sessionStorage
    storage.setItem('asset_token', result.access_token)
    storage.setItem('asset_user', JSON.stringify(result.user))
    setUser(result.user)
    return result.user
  }

  function logout() {
    localStorage.removeItem('asset_token')
    localStorage.removeItem('asset_user')
    sessionStorage.removeItem('asset_token')
    sessionStorage.removeItem('asset_user')
    setUser(null)
  }

  const value = useMemo(() => ({ user, login, logout }), [user])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
