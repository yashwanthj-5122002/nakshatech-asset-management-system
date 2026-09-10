export type TravelKmStatus =
  | 'draft'
  | 'submitted'
  | 'admin_approved'
  | 'admin_sent_back'
  | 'admin_rejected'
  | 'hr_approved'
  | 'hr_sent_back'
  | 'hr_rejected'
  | 'finance_rejected'
  | 'finance_approved'
  | 'paid'

export interface TravelKmAttachment {
  id: number
  phase: 'start' | 'end'
  original_filename: string
  mime_type: string
  file_size: number
  content_sha256: string
  device_latitude: number
  device_longitude: number
  device_accuracy_m?: number | null
  device_captured_at: string
  exif_gps_present: boolean
  exif_latitude?: number | null
  exif_longitude?: number | null
  exif_captured_at?: string | null
  exif_device_distance_m?: number | null
  verification_flag: string
  created_at: string
}

export interface TravelKmEvent {
  id: number
  action: string
  actor_user_id?: number | null
  actor_name: string
  actor_email: string
  actor_role: string
  from_status?: string | null
  to_status?: string | null
  comments?: string | null
  event_metadata?: Record<string, unknown> | null
  created_at: string
}


export interface TravelKmEmailRouting {
  reporting_manager_email: string
  to_emails: string[]
  cc_emails: string[]
  created_at: string
  updated_at: string
}

export interface TravelKmEmailDelivery {
  id: number
  event_type: string
  subject: string
  to_emails: string[]
  cc_emails: string[]
  delivery_mode: string
  status: 'pending' | 'sent' | 'console' | 'failed' | string
  error_message?: string | null
  attempted_at: string
  sent_at?: string | null
}

export interface TravelKmPermissions {
  can_edit: boolean
  can_submit: boolean
  can_edit_email_routing?: boolean
  can_retry_email?: boolean
  can_admin_decide: boolean
  can_hr_decide: boolean
  can_finance_decide?: boolean
  can_finance_pay: boolean
  read_only_management: boolean
}

export interface TravelKmClaim {
  id: number
  claim_code: string
  requester_id: number
  employee_name: string
  employee_email?: string | null
  employee_id?: string | null
  department?: string | null
  project_id: number
  project_code: string
  project_name?: string | null
  client_name?: string | null
  travel_date: string
  purpose_description: string
  start_km: number
  end_km?: number | null
  odometer_km?: number | null
  start_latitude: number
  start_longitude: number
  start_accuracy_m?: number | null
  start_captured_at: string
  end_latitude?: number | null
  end_longitude?: number | null
  end_accuracy_m?: number | null
  end_captured_at?: string | null
  gps_straight_line_km?: number | null
  distance_variance_km?: number | null
  distance_variance_percent?: number | null
  rate_per_km: number
  calculated_allowance?: number | null
  admin_eligible_km?: number | null
  hr_eligible_km?: number | null
  final_eligible_km?: number | null
  final_allowance?: number | null
  status: TravelKmStatus
  admin_decision_at?: string | null
  admin_comments?: string | null
  hr_decision_at?: string | null
  hr_comments?: string | null
  finance_decision_at?: string | null
  finance_comments?: string | null
  payment_reference?: string | null
  payment_mode?: string | null
  paid_amount?: number | null
  paid_at?: string | null
  submitted_at?: string | null
  created_at: string
  updated_at: string
  email_routing?: TravelKmEmailRouting | null
  email_history: TravelKmEmailDelivery[]
  attachments: TravelKmAttachment[]
  events: TravelKmEvent[]
  permissions: TravelKmPermissions
}

export interface TravelKmSummaryRow {
  name: string
  claims: number
  km: number
  allowance: number
}

export interface TravelKmDashboard {
  total_claims: number
  total_km: number
  approved_allowance: number
  paid_amount: number
  salary_approved_amount?: number
  pending_admin: number
  pending_hr: number
  pending_finance: number
  paid_count: number
  finance_approved_count?: number
  rejected_count: number
  sent_back_count: number
  status_counts: Record<string, number>
  smart_verification_counts?: Record<string, number>
  verified_journeys?: number
  journeys_needing_review?: number
  high_variance_journeys?: number
  geofence_confirmed_journeys?: number
  project_summary: TravelKmSummaryRow[]
  employee_summary: TravelKmSummaryRow[]
  monthly_summary: TravelKmSummaryRow[]
}

export interface CapturedGps {
  latitude: number
  longitude: number
  accuracy: number | null
  capturedAt: string
}

export interface TravelKmTrackPoint {
  id: number
  latitude: number
  longitude: number
  accuracy_m?: number | null
  speed_mps?: number | null
  heading_deg?: number | null
  captured_at: string
  received_at: string
}

export interface TravelKmTrackingSnapshot {
  tracking_active: boolean
  live_now: boolean
  started_at?: string | null
  stopped_at?: string | null
  point_count: number
  route_distance_km: number
  last_point?: TravelKmTrackPoint | null
  points: TravelKmTrackPoint[]
  foreground_tracking_note: string
}



export interface TravelKmProjectGeofence {
  configured: boolean
  active: boolean
  project_id: number
  project_code?: string
  project_name?: string
  site_name?: string | null
  center_latitude?: number | null
  center_longitude?: number | null
  radius_m?: number | null
  updated_at?: string | null
}

export interface TravelKmVerificationComponent {
  key: string
  label: string
  earned: number
  available: number
  status: string
}

export interface TravelKmVerificationFlag {
  code: string
  severity: 'high' | 'medium' | 'info' | string
  message: string
}

export interface TravelKmSmartVerification {
  source: 'live_preview' | 'submission_snapshot' | string
  source_version: string
  generated_at: string
  snapshot_locked: boolean
  advisory_only: boolean
  score?: number | null
  outcome: string
  outcome_label: string
  route: {
    point_count: number
    route_distance_km: number
    odometer_km?: number | null
    variance_km?: number | null
    variance_percent?: number | null
    max_gap_seconds?: number | null
    median_accuracy_m?: number | null
    discarded_segments: number
  }
  evidence: {
    photo_count: number
    start_photo: boolean
    end_photo: boolean
  }
  geofence: TravelKmProjectGeofence & {
    site_entered: boolean
    nearest_distance_m?: number | null
    first_entry_at?: string | null
    last_presence_at?: string | null
    onsite_minutes: number
  }
  components: TravelKmVerificationComponent[]
  flags: TravelKmVerificationFlag[]
  scoring_note: string
}
