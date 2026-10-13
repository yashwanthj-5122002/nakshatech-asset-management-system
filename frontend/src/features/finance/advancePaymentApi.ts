import { apiFetch } from '../../lib/api'

export const ADVANCE_STATUS_OPTIONS = [
  ['not_required', 'Not Required'],
  ['requested', 'Requested'],
  ['pending', 'Pending'],
  ['partial_received', 'Partial Received'],
  ['received', 'Received'],
  ['overdue', 'Overdue'],
  ['adjusted', 'Adjusted'],
  ['closed', 'Closed'],
] as const

export type AdvanceStatus = typeof ADVANCE_STATUS_OPTIONS[number][0]

export interface AdvanceSummary {
  currency: string | null
  financial_amounts_visible: boolean
  total_advance_expected: number | null
  total_advance_received: number | null
  total_advance_pending: number | null
  total_overdue_advance: number | null
  counts_by_status: Record<AdvanceStatus, number>
}

export interface AdvanceProject {
  project_id: number
  project_name: string
  client: string | null
  department: string
  department_code: string
  bd_person: string | null
  project_manager: string | null
  project_value: number | null
  advance_required: boolean
  advance_amount: number | null
  received_amount: number | null
  pending_amount: number | null
  adjusted_amount: number | null
  advance_currency: string | null
  expected_date: string | null
  final_date: string | null
  status: AdvanceStatus
  status_label: string
  financial_amounts_visible: boolean
}

export interface AdvanceTransaction {
  id: number
  amount: number
  currency: string
  amount_inr: number
  fx_rate: number | null
  payment_date: string
  payment_mode: string
  reference_number: string | null
  bank_reference: string | null
  attachment: string | null
  adjusted_amount_inr: number
  adjusted_invoice_id: number | null
  recorded_by: string | null
  verified_by: string | null
  is_reversed: boolean
  created_at: string
}

export interface AdvanceFollowUp {
  id: number
  contact_person: string
  communication_type: string
  remarks: string
  followup_date: string
  next_followup_date: string | null
  created_by: string | null
  created_at: string
}

export interface AdvanceStatusHistory {
  id: number
  old_status: AdvanceStatus | null
  old_status_label: string | null
  new_status: AdvanceStatus
  new_status_label: string
  remarks: string | null
  created_by: string | null
  created_at: string
}

export interface AdvanceProjectDetail extends AdvanceProject {
  payment_terms: string | null
  transactions: AdvanceTransaction[]
  followups: AdvanceFollowUp[]
  status_history: AdvanceStatusHistory[]
}

interface AdvanceProjectsResponse {
  projects: AdvanceProject[]
}

export function getAdvanceSummary() {
  return apiFetch<AdvanceSummary>('/finance/advance-payments/summary')
}

export async function getAdvanceProjects() {
  const response = await apiFetch<AdvanceProjectsResponse>('/finance/advance-payments/projects')
  return response.projects
}

export function getAdvanceProjectDetail(projectId: number) {
  return apiFetch<AdvanceProjectDetail>(`/finance/advance-payments/${projectId}`)
}

export interface AdvanceNotificationsRefreshResponse {
  created: number
  matched: Record<'due' | 'overdue' | 'partial' | 'high_value', number>
  evaluated_projects: number
  financial_amounts_visible: boolean
  high_value_threshold_inr: number
  as_of: string
}

export interface AdvanceTransactionCreate {
  amount: number
  currency: string
  payment_date: string
  payment_mode: string
  reference_number?: string | null
  bank_reference?: string | null
  attachment?: string | null
}

export interface AdvanceTransactionCreateResponse {
  transaction: AdvanceTransaction
  status: AdvanceStatus
  status_label: string
}

/** Finance-only: record money actually received from the client against the advance terms. */
export function recordAdvanceTransaction(projectId: number, payload: AdvanceTransactionCreate) {
  return apiFetch<AdvanceTransactionCreateResponse>(`/finance/advance-payments/${projectId}/transactions`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export interface AdvanceCollectionInvoice {
  invoice_id: number
  invoice_number: string
  status: string
  currency: string
  invoice_total: number | null
  cash_payments: number | null
  advance_applied: number | null
  settled_total: number | null
  balance: number | null
}

/**
 * Central project collection read model (backend advance_settlement_service).
 *
 * total_collected = advance received + invoice cash payments. An advance already
 * applied to an invoice is counted exactly once, so nothing is ever double counted.
 */
export interface AdvanceCollection {
  project_id: number
  project_name: string
  financial_amounts_visible: boolean
  advance_expected_inr: number | null
  advance_received_inr: number | null
  advance_pending_inr: number | null
  advance_status: AdvanceStatus
  advance_status_label: string
  project_value_inr: number | null
  advance_applied_inr: number | null
  advance_unapplied_inr: number | null
  invoice_cash_payments_inr: number | null
  total_collected_inr: number | null
  remaining_project_balance_inr: number | null
  collection_status: string
  invoice_status: string
  invoice_count: number
  invoices: AdvanceCollectionInvoice[]
}

export interface AdvanceApplyAllocation {
  transaction_id: number
  sequence: number
  amount_inr: number
  amount_original: number
}

export interface AdvanceApplyToInvoiceResponse {
  invoice_id: number
  invoice_number: string
  invoice_total: number
  currency: string
  applied_inr: number
  allocations: AdvanceApplyAllocation[]
  previous_invoice_status: string | null
  invoice_status: string
  invoice_settled_total: number
  invoice_balance: number
  advance_status: AdvanceStatus
  advance_status_label: string
  advance_applied_inr: number
  collection: AdvanceCollection
}

export function getAdvanceCollection(projectId: number) {
  return apiFetch<AdvanceCollection>(`/finance/advance-payments/${projectId}/collection`)
}

/**
 * Settle an invoice with money already received as a client advance. The allocation is
 * stored on the existing advance receipts, so no duplicate invoice payment is created.
 */
export function applyAdvanceToInvoice(projectId: number, payload: { invoice_id: number; amount: number; remarks?: string }) {
  return apiFetch<AdvanceApplyToInvoiceResponse>(`/finance/advance-payments/${projectId}/apply-to-invoice`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

// Idempotent per project/rule/day (backend dedupe keys). Called on Command Center
// load so Due/Overdue/Partial/High-Value alerts reach Finance and Management
// without any background scheduler.
export function refreshAdvanceNotifications() {
  return apiFetch<AdvanceNotificationsRefreshResponse>('/finance/advance-payments/refresh-notifications', {
    method: 'POST',
  })
}
