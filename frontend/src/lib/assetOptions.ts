export const OFFICE_LOCATION_VALUE =
  'Naksha Tech Pvt. Ltd., R.K. Chambers, 4th Floor, 5th Main, Chamarajpet, Bengaluru, Karnataka, India – 560018'

export const WFH_LOCATION_VALUE = 'WFH – Work From Home'
export const MANUAL_ENTRY_VALUE = '__manual_entry__'

export const ASSET_LOCATION_OPTIONS = [
  { value: 'NT - 1st Floor', label: 'NT - 1st Floor' },
  { value: 'NT - 2nd Floor', label: 'NT - 2nd Floor' },
  { value: 'NT - 3rd Floor', label: 'NT - 3rd Floor' },
  { value: 'NT - 4th Floor', label: 'NT - 4th Floor' },
  {
    value: OFFICE_LOCATION_VALUE,
    label: 'Office – R.K. Chambers, Chamarajpet',
  },
  {
    value: WFH_LOCATION_VALUE,
    label: 'WFH – Work From Home',
  },
] as const

export const DEPARTMENT_OPTIONS = [
  'Administration',
  'Management',
  'Finance',
  'IT',
  'Software Development',
  'Business Development',
  'Civil',
  'GIS / Mobile Mapping',
  'Orthophoto',
  'Photogrammetry',
  'LiDAR',
  'Reality Capture',
  'Laser Scanning',
  'Drone',
] as const

export function normaliseAssetEditLocation(value: string | null | undefined): string {
  const current = value?.trim() ?? ''
  const comparable = current.toLowerCase()

  if (
    !current ||
    comparable === 'head office' ||
    comparable === 'office' ||
    comparable === OFFICE_LOCATION_VALUE.toLowerCase()
  ) {
    return OFFICE_LOCATION_VALUE
  }

  if (
    comparable === 'wfh' ||
    comparable === 'work from home' ||
    comparable === WFH_LOCATION_VALUE.toLowerCase()
  ) {
    return WFH_LOCATION_VALUE
  }

  // Preserve an unexpected legacy value so opening the edit form never
  // destroys historical data. The UI still allows only the two controlled
  // values for all new selections.
  return current
}
