import type { Role } from '../types'

export const FULL_ACCESS_ROLES: Role[] = ['software_team', 'admin']

export function isFullAccessRole(role: Role): boolean {
  return FULL_ACCESS_ROLES.includes(role)
}

export function canAccessRole(userRole: Role, allowedRoles?: Role[]): boolean {
  if (!allowedRoles || allowedRoles.length === 0) return true
  if (allowedRoles.includes(userRole)) return true
  return userRole === 'software_team' && allowedRoles.includes('admin')
}

export function roleHomePath(role: Role): string {
  const paths: Record<Role, string> = {
    software_team: '/software-team',
    admin: '/admin',
    management: '/management',
    it: '/it',
    drone: '/drone',
    finance: '/finance',
    hr: '/hr/travel-km',
    bd: '/bd',
    ortho: '/ortho',
    lidar: '/project-workstreams',
    civil: '/project-workstreams',
    laser_scanning: '/project-workstreams',
    bim: '/project-workstreams',
    mobile_mapping: '/project-workstreams',
    employee: '/support',
  }
  return paths[role]
}

export function roleDisplayName(role: Role): string {
  const labels: Record<Role, string> = {
    software_team: 'Software Team',
    admin: 'Admin',
    management: 'Management',
    it: 'IT Department',
    drone: 'Drone Department',
    finance: 'Finance Department',
    hr: 'HR Department',
    bd: 'Business Development',
    ortho: 'Ortho',
    lidar: 'LiDAR',
    civil: 'Civil Department',
    laser_scanning: 'Laser Scanning',
    bim: 'BIM Department',
    mobile_mapping: 'Mobile Mapping',
    employee: 'Employee Support',
  }
  return labels[role]
}
