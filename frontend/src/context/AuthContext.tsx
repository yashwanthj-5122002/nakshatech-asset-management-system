import { createContext, type ReactNode, useContext, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'
import type { AuthUser, Role } from '../types'

interface AuthContextValue {
  user: AuthUser | null
  login: (email: string, password: string, role: Role) => Promise<AuthUser>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => {
    const raw = localStorage.getItem('asset_user')
    if (!raw) return null
    try { return JSON.parse(raw) as AuthUser } catch { return null }
  })

  async function login(email: string, password: string, role: Role) {
    const result = await apiFetch<{ access_token: string; user: AuthUser }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password, role }),
    })
    localStorage.setItem('asset_token', result.access_token)
    localStorage.setItem('asset_user', JSON.stringify(result.user))
    setUser(result.user)
    return result.user
  }

  function logout() {
    localStorage.removeItem('asset_token')
    localStorage.removeItem('asset_user')
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
