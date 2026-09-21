import type { BusinessRecordStatus, BusinessViewer, Role } from '../../types'

export { formatInr } from '../finance/finance-utils'

export const BUSINESS_ENTER_ROLES: Role[] = ['finance', 'admin', 'software_team']
export const BUSINESS_TOTAL_ROLES: Role[] = ['finance', 'bd', 'management', 'admin', 'software_team']

export const businessDepartments: Array<{ code: string; label: string }> = [
  { code: 'ortho', label: 'Ortho' },
  { code: 'lidar', label: 'LiDAR' },
  { code: 'civil', label: 'Civil' },
  { code: 'laser_scanning', label: 'Laser Scanning' },
  { code: 'bim', label: 'BIM' },
  { code: 'mobile_mapping', label: 'Mobile Mapping' },
]

export function canEnterBusiness(role: Role | undefined): boolean {
  return !!role && BUSINESS_ENTER_ROLES.includes(role)
}

export function canSeeBusinessTotals(role: Role | undefined): boolean {
  return !!role && BUSINESS_TOTAL_ROLES.includes(role)
}

export function businessViewerLabel(viewer: BusinessViewer): string {
  const labels: Record<BusinessViewer, string> = {
    finance: 'Finance entry',
    management: 'Management oversight',
    bd: 'Business Development view',
    project_manager: 'My business',
    unavailable: 'No access',
  }
  return labels[viewer]
}

export function businessStatusTone(status: BusinessRecordStatus): string {
  return status === 'verified' ? 'success' : 'pending'
}

export function currentReportingMonth(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

export function monthLabel(month: string): string {
  const [year, monthPart] = month.split('-')
  const index = Number(monthPart) - 1
  const names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  if (!year || index < 0 || index > 11) return month
  return `${names[index]} ${year}`
}
