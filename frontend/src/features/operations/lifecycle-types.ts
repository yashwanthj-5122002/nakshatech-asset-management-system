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
  feedback_request_id: number | null
  response_type: 'accepted' | 'correction' | 'additional_scope'
  comments: string | null
  correction_description: string | null
  classification_status: string
  classified_as: string | null
  source: 'client_portal' | 'bd_manual'
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
  payment_currency: string
  fx_snapshot_id: number | null
  fx_rate_to_inr: number | null
  fx_rate_date: string | null
  fx_rate_source: string | null
  fx_rate_mode: string | null
  inr_equivalent: number | null
  invoice_inr_equivalent: number | null
  fx_gain_loss_inr: number | null
  payment_mode: string
  comments: string | null
  created_at: string
}

export type BadDebtRow = {
  id: number
  project_id?: number
  project_code?: string
  project_name?: string
  client_name?: string | null
  invoice_id?: number
  invoice_number?: string
  invoice_total?: number
  paid_amount?: number
  cash_balance?: number
  status: 'PROPOSED' | 'APPROVED' | 'REJECTED' | 'RECOVERED'
  proposed_amount: number
  approved_amount: number | null
  recovered_amount: number
  net_bad_debt: number
  unrecovered_amount?: number
  currency?: string
  reason: string
  collection_attempts: string
  last_followup_date: string | null
  finance_remarks: string | null
  proposed_at: string
  proposed_by_name?: string | null
  reviewed_at: string | null
  reviewed_by_name?: string | null
  decision_reason: string | null
}

export type InvoiceRow = {
  id: number
  invoice_number: string
  status: string
  stored_status: string
  can_close_invoice?: boolean
  invoice_date: string
  due_date: string
  amount: number
  tax_amount: number
  total_amount: number
  paid_amount: number
  balance: number
  collectible_balance: number
  days_overdue?: number
  bad_debt: BadDebtRow | null
  // V8.7 invoice presentation theme + authorised signature state.
  theme?: string | null
  signed?: boolean
  signed_by_name?: string | null
  signed_at?: string | null
  signature_invalidated_at?: string | null
  currency: string
  tax_percent: number | null
  payment_terms: string | null
  po_wo_reference: string | null
  fx_snapshot_id: number | null
  fx_rate_to_inr: number | null
  fx_rate_date: string | null
  fx_rate_source: string | null
  fx_rate_mode: string | null
  base_inr: number | null
  tax_inr: number | null
  total_inr: number | null
  fx_locked: boolean
  notes: string | null
  raised_at: string | null
  closed_at: string | null
  payments: InvoicePaymentRow[]
}

export type InvoiceDocumentPayload = {
  document_type: string
  document_version: number
  document_source: 'project_invoice' | 'standalone_invoice'
  entry_mode: 'auto_fill' | 'manual' | null
  company: {
    name: string
    address: string | null
    gstin: string | null
    pan: string | null
    phone: string | null
    email: string | null
    website: string | null
    msme_registration?: string | null
    hsn_sac: string | null
    bank_name: string | null
    bank_account_name: string | null
    bank_account_number: string | null
    bank_ifsc: string | null
    bank_swift: string | null
    bank_branch: string | null
    data_source: string
  }
  client: {
    code: string | null
    name: string
    address: string | null
    country: string | null
    gstin: string | null
    pan: string | null
    contact_person: string | null
    phone: string | null
    email: string | null
    data_source: string
  }
  ship_to?: {
    name: string
    address: string | null
    gstin: string | null
    pan: string | null
    phone: string | null
    email: string | null
  } | null
  project: { id: number; code: string; name: string; description: string | null } | null
  /**
   * ERP-only settlement snapshot (STEP 12). It is returned by the project-invoice
   * document payload for Finance screens and is never rendered onto the printable
   * A4 tax invoice or its PDF. Standalone invoices carry no settlement data.
   */
  settlement?: {
    advance_applied: number
    cash_received: number
    total_settled: number
    outstanding: number
    status: string
  } | null
  invoice: Partial<InvoiceRow> & {
    id: number
    invoice_number: string
    invoice_date: string
    due_date: string | null
    payment_terms: string | null
    po_wo_reference: string | null
    notes: string | null
    created_at: string
    project_id?: number
    work_order_date: string | null
    dispatch_details: string | null
    dispatch_date: string | null
    place_of_supply: string | null
  }
  line_items: Array<{
    sequence: number
    description: string
    detail: string | null
    hsn_sac: string | null
    quantity: number
    unit: string
    rate: number
    taxable_amount: number
    tax_percent?: number
    tax_amount?: number
    source: string
  }>
  tax_lines: Array<{ label: string; rate_percent: number | null; amount: number; source: string }>
  totals: {
    subtotal?: number
    taxable_amount: number
    tax_amount: number
    invoice_total: number
    amount_in_words: string
    currency: string
    balance_due?: number
  }
  notes?: string | null
  terms_conditions?: string | null
  authorized_signatory_name?: string | null
  qr_data?: string | null
  qr_image_data_uri?: string | null
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
