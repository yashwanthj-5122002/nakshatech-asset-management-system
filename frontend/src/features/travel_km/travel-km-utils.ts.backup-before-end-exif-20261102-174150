import type { CapturedGps, TravelKmStatus } from './travel-km-types'

export const travelStatusLabels: Record<string, string> = {
  draft: 'Draft',
  submitted: 'Pending Admin Verification',
  admin_approved: 'Admin Verified · Pending HR',
  admin_sent_back: 'Admin Sent Back',
  admin_rejected: 'Rejected by Admin',
  hr_approved: 'HR Approved · Pending Finance',
  hr_sent_back: 'HR Sent Back',
  hr_rejected: 'Rejected by HR',
  finance_rejected: 'Rejected by Finance',
  finance_approved: 'Finance Approved · Monthly Salary',
  paid: 'Finance Approved · Completed (Legacy)',
}

export function statusTone(status: string): string {
  if (status === 'finance_approved' || status === 'paid') return 'success'
  if (status.includes('rejected')) return 'danger'
  if (status.includes('sent_back')) return 'warning'
  if (status === 'draft') return 'neutral'
  return 'active'
}

export function money(value?: number | null): string {
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(value || 0)
}

export function km(value?: number | null): string {
  return `${Number(value || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })} KM`
}

export function displayDate(value?: string | null): string {
  if (!value) return 'Not recorded'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('en-IN')
}

export function verificationLabel(flag: string): string {
  const labels: Record<string, string> = {
    exif_matches_live_gps: 'EXIF + Live GPS Match',
    exif_live_gps_mismatch: 'EXIF / Live GPS Mismatch',
    low_gps_accuracy: 'Low GPS Accuracy',
    live_gps_captured: 'Live GPS Captured',
  }
  return labels[flag] || flag.replaceAll('_', ' ')
}

export function workflowStage(status: TravelKmStatus): number {
  if (status === 'finance_approved' || status === 'paid') return 5
  if (status === 'hr_approved' || status === 'finance_rejected') return 4
  if (status === 'admin_approved' || status === 'hr_sent_back' || status === 'hr_rejected') return 3
  if (status === 'submitted' || status === 'admin_sent_back' || status === 'admin_rejected') return 2
  return 1
}

export async function captureLiveGps(): Promise<CapturedGps> {
  if (!navigator.geolocation) throw new Error('This browser/device does not provide GPS location access.')
  const position = await new Promise<GeolocationPosition>((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(resolve, error => {
      const reason = error.code === error.PERMISSION_DENIED
        ? 'Location permission was denied. Allow precise location access and try again.'
        : error.code === error.POSITION_UNAVAILABLE
          ? 'This device could not determine the current location. Check GPS/location services and try again.'
          : 'Location capture timed out. Move to an area with better GPS reception and try again.'
      reject(new Error(reason))
    }, {
      enableHighAccuracy: true,
      timeout: 20_000,
      maximumAge: 0,
    })
  })
  return {
    latitude: position.coords.latitude,
    longitude: position.coords.longitude,
    accuracy: Number.isFinite(position.coords.accuracy) ? position.coords.accuracy : null,
    capturedAt: new Date(position.timestamp || Date.now()).toISOString(),
  }
}
