export type NotificationSeverity = 'info' | 'success' | 'warning' | 'danger'

export interface NotificationMetadata {
  project_name?: string | null
  client_name?: string | null
  submitted_by?: string | null
  submitted_at?: string | null
  returned_by?: string | null
  status?: string | null
  reason?: string | null
  required_action?: string | null
  due_date?: string | null
  days_overdue?: number | null
  current_stage?: string | null
  decided_by?: string | null
  amount?: string | number | null
  currency?: string | null
  [key: string]: unknown
}

/** A persisted business notification queued for the centre popup (TYPE B). */
export interface PopupNotification {
  id: number
  title: string
  message: string
  severity?: string
  requires_action?: boolean
  is_resolved?: boolean
  is_read?: boolean
  is_reminder?: boolean
  metadata?: NotificationMetadata
  target_url?: string | null
}

/** Immediate UI feedback after a form submits (TYPE A - no DB record). */
export interface FeedbackPayload {
  kind: 'success' | 'error' | 'warning'
  eyebrow: string
  title: string
  message?: string
  issues?: string[]
  firstIssueField?: string
  facts?: PopupFact[]
  viewUrl?: string | null
}

export interface PopupFact {
  label: string
  value: string
  tone?: 'danger' | 'warning'
}

export interface PopupAction {
  id: string
  label: string
  variant?: 'default' | 'primary' | 'danger' | 'success'
  onSelect?: (notification?: PopupNotification) => void | Promise<void>
}

export interface NotificationSettings {
  overdue_popup_reminder_minutes: number
  suggested_minutes: number[]
  default_minutes: number
  can_manage: boolean
  capability: string
}

export function isSafeInternalPath(value: string | null | undefined): value is string {
  return Boolean(value && value.startsWith('/') && !value.startsWith('//'))
}