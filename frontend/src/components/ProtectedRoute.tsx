import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import type { Role } from '../types'
import { canAccessRole, roleHomePath } from '../lib/roles'
import { RouteFallback } from './RouteFallback'

export function ProtectedRoute({ children, roles }: { children: ReactNode; roles?: Role[] }) {
  const { user, needsBranchSelection, identityChecked } = useAuth()
  const location = useLocation()
  // Hold the route until the server has confirmed who this session belongs to, so the
  // guard never decides on a role value that was read from (and could be edited in)
  // web storage.
  if (!identityChecked) return <RouteFallback />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (needsBranchSelection) return <Navigate to="/select-branch" replace />
  if (!canAccessRole(user.role, roles)) return <Navigate to={roleHomePath(user.role)} replace />
  return <>{children}</>
}
