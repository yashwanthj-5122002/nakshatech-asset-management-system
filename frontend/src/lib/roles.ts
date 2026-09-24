import type { Role } from '../types'

export const FULL_ACCESS_ROLES: Role[] = ['software_team', 'admin']

export function isFullAccessRole(role: Role): boolean {
  return FULL_ACCESS_ROLES.includes(role)
}

// One shared operational workflow (BD -> Finance -> PM -> Team Lead -> Production/QC/QA ->
// Delivery -> Billing) covers all five technical Project Manager roles. Use this helper instead
// of scattering role === 'lidar' / 'civil' / ... checks across components.
export const TECHNICAL_PM_ROLES: Role[] = ['ortho', 'lidar', 'mobile_mapping', 'laser_scanning', 'civil']

export function isTechnicalProjectManager(role: Role): boolean {
  return TECHNICAL_PM_ROLES.includes(role)
}

// Finance Command Center: management/admin/finance see all departments; technical PMs see only their department.
export const COMMAND_CENTER_ROLES: Role[] = ['finance', 'admin', 'management', ...TECHNICAL_PM_ROLES]

const ROLE_DEPARTMENT_CODE: Partial<Record<Role, string>> = {
  ortho: 'ortho',
  lidar: 'lidar',
  mobile_mapping: 'mobile_mapping',
  laser_scanning: 'laser_scanning',
  civil: 'civil',
}

export function departmentCodeForRole(role: Role): string | null {
  return ROLE_DEPARTMENT_CODE[role] ?? null
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
    // Same shared operational dashboard as Ortho (one workflow, department-aware inside).
    lidar: '/ortho',
    civil: '/ortho',
    laser_scanning: '/ortho',
    mobile_mapping: '/ortho',
    bim: '/project-workstreams',
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
