import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import type { Role } from '../types'
import { roleHomePath } from '../lib/roles'
import { RouteFallback } from './RouteFallback'

/** Exact-role guard for new department modules.
 *
 * Existing ProtectedRoute intentionally preserves the legacy Software Team ->
 * Admin-equivalent behavior. BD/Ortho must not inherit that legacy elevation,
 * so these routes use exact membership instead.
 */
export function StrictProtectedRoute({ children, roles }: { children: ReactNode; roles: Role[] }) {
  const { user, needsBranchSelection, identityChecked } = useAuth()
  const location = useLocation()
  // Wait for the server-confirmed identity before trusting user.role (see AuthContext).
  if (!identityChecked) return <RouteFallback />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (needsBranchSelection) return <Navigate to="/select-branch" replace />
  if (!roles.includes(user.role)) return <Navigate to={roleHomePath(user.role)} replace />
  return <>{children}</>
}
