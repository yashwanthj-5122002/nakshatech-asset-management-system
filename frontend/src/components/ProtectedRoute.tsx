import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import type { Role } from '../types'
import { canAccessRole, roleHomePath } from '../lib/roles'

export function ProtectedRoute({ children, roles }: { children: ReactNode; roles?: Role[] }) {
  const { user, needsBranchSelection } = useAuth()
  const location = useLocation()
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (needsBranchSelection) return <Navigate to="/select-branch" replace />
  if (!canAccessRole(user.role, roles)) return <Navigate to={roleHomePath(user.role)} replace />
  return <>{children}</>
}
