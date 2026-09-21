// Shared types and helpers for the V8.1 client feedback, rework and billing
// lifecycle screens (BD feedback, Finance billing, Management Project 360).
// Mirrors backend/app/modules/operations/lifecycle_service.py payload shapes.

export type LifecycleProjectSummary = {
  id: number
  project_code: string
  project_name: string
  client_id: string | null
  client_name: string | null
  workflow_status: string
  project_manager_id: number | null
  project_manager_name: string | null
  team_leader_id: number | null
  team_leader_name: string | null
  current_stage: string
  progress_percent: number
  operational_completed_at: string | null
  rework_count: number
  latest_rework_status: string | null
  latest_rework_cycle_type: 'CORRECTION_REWORK' | 'APPROVED_CHANGE_REQUEST' | null
  invoice_count: number
  invoice_balance: number
  has_overdue_invoice: boolean
}

export type LifecycleDashboardSummary = {
  total_projects: number
  active_projects: number
  completed_projects: number
  awaiting_feedback: number
  rework: number
  ready_for_billing: number
  payment_pending: number
  overdue: number
  closed: number
}

export type LifecycleDashboard = {
  summary: LifecycleDashboardSummary
  projects: LifecycleProjectSummary[]
  department_overview?: Record<string, Record<string, number>>
}

export type TimelineEvent = {
  id: string
  event_type: string
  title: string
  details: string | null
  status: string | null
  actor_name: string | null
  occurred_at: string
  source: 'workflow' | 'lifecycle'
}

export type FeedbackRequestRow = {
  id: number
  request_code: string
  cycle_number: number
  recipient_email: string | null
  status: string
  expires_at: string
  sent_at: string
  reminder_count: number
  responded_at: string | null
  message_thread_id: string
}

export type FeedbackResponseRow = {
  id: number
  feedback_request_id: number
  response_type: 'accepted' | 'correction' | 'additional_scope'
  comments: string | null
  correction_description: string | null
  classification_status: string
  classified_as: string | null
  responded_at: string
}

export type ReworkCycleRow = {
  id: number
  cycle_number: number
  cycle_type: 'CORRECTION_REWORK' | 'APPROVED_CHANGE_REQUEST'
  source_change_request_id: number | null
  status: string
  correction_scope: string
  opened_at: string
  delivered_at: string | null
  resubmitted_at: string | null
  /** Status the cycle must have given where its rework work packages are; null when not applicable. */
  expected_status?: string | null
  /** True when the cycle is behind its work packages (e.g. work finished before automatic sync existed). */
  out_of_sync?: boolean
}

export function reworkCycleTypeLabel(cycleType: string): string {
  return cycleType === 'APPROVED_CHANGE_REQUEST' ? 'Approved Change Request' : 'Correction / Rework'
}

export type DeliveryVersionRow = {
  id: number
  version_number: number
  rework_cycle_id: number | null
  delivery_reference: string
  notes: string | null
  delivered_at: string
}

export type ChangeRequestRow = {
  id: number
  request_code: string
  description: string
  status: 'pending' | 'approved' | 'rejected'
  commercial_impact: number | null
  currency: string
  decision_comments: string | null
  created_at: string
}

export type InvoicePaymentRow = {
  id: number
  payment_reference: string
  payment_date: string
  amount: number
  payment_mode: string
  comments: string | null
  created_at: string
}

export type InvoiceRow = {
  id: number
  invoice_number: string
  status: string
  stored_status: string
  invoice_date: string
  due_date: string
  amount: number
  tax_amount: number
  total_amount: number
  paid_amount: number
  balance: number
  currency: string
  notes: string | null
  raised_at: string | null
  closed_at: string | null
  payments: InvoicePaymentRow[]
}

export type Project360 = LifecycleProjectSummary & {
  scope: string | null
  selected_team: Array<{ user_id: number; name: string | null; role: string }>
  timeline: TimelineEvent[]
  feedback_requests: FeedbackRequestRow[]
  feedback_responses: FeedbackResponseRow[]
  rework_cycles: ReworkCycleRow[]
  delivery_versions: DeliveryVersionRow[]
  change_requests: ChangeRequestRow[]
  invoices: InvoiceRow[]
}

export type ProjectMessageRow = {
  id: number
  sender_user_id: number
  sender_name: string | null
  recipient_user_id: number
  recipient_name: string | null
  message: string
  is_read: boolean
  created_at: string
}

export function lifecycleStatusLabel(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase())
}

const TONE_MAP: Record<string, string> = {
  FEEDBACK_NOT_SENT: 'warning',
  FEEDBACK_REQUESTED: 'warning',
  FEEDBACK_REMINDER_SENT: 'warning',
  AWAITING_CLIENT_FEEDBACK: 'warning',
  FEEDBACK_NEGATIVE: 'danger',
  REWORK_OPEN: 'danger',
  REWORK_PRODUCTION: 'danger',
  REWORK_QC: 'danger',
  REWORK_QA: 'danger',
  REWORK_DELIVERED: 'danger',
  REWORK_RESUBMITTED: 'warning',
  CLIENT_ACCEPTED: 'success',
  NO_FEEDBACK_CLOSURE_RECOMMENDED: 'warning',
  DEEMED_ACCEPTED: 'success',
  CHANGE_REQUEST_PENDING: 'danger',
  READY_FOR_BILLING: 'success',
  INVOICE_DRAFT: 'warning',
  INVOICE_RAISED: 'warning',
  PAYMENT_PENDING: 'warning',
  PARTIALLY_PAID: 'warning',
  PAYMENT_OVERDUE: 'danger',
  PAYMENT_RECEIVED: 'success',
  INVOICE_CLOSED: 'success',
  FINANCE_CLOSURE_PENDING: 'success',
  CLOSED: 'success',
}

export function lifecycleStatusTone(status: string): string {
  return TONE_MAP[status] || 'warning'
}

export function formatMoney(amount: number, currency = 'INR'): string {
  try {
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: 2 }).format(amount)
  } catch {
    return `${currency} ${amount.toFixed(2)}`
  }
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return 'Not recorded'
  return new Date(value).toLocaleString('en-IN')
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return 'Not recorded'
  return new Date(value).toLocaleDateString('en-IN')
}
