export type CurrencyRef = { code: string; name?: string; symbol?: string }

export type CurrencyPayload = {
  base_currency: string
  currencies: CurrencyRef[]
  common_currencies?: string[]
  management_display_currencies?: string[]
}

export type EstimateMilestone = { id: number; sequence: number; milestone_name: string; percent: number | null; amount: number | null }

export type CommercialEstimate = {
  id: number
  project_id: number
  revision_no: number
  is_baseline: boolean
  status: string
  is_locked: boolean
  quotation_reference: string | null
  po_wo_reference: string | null
  scope_description: string
  billing_type: string
  billing_type_label?: string
  unit_rate?: number | null
  estimated_quantity?: number | null
  quantity_unit?: string | null
  milestones?: EstimateMilestone[]
  payment_terms: string | null
  expected_billing_milestone: string | null
  projected_payment_date: string | null
  notes: string | null
  currency_code: string
  estimated_amount: number
  taxable_base_amount: number
  tax_percent: number
  expected_tax: number
  expected_gross: number
  estimated_direct_cost_inr: number | null
  fx_snapshot_id: number | null
  fx_rate_to_inr: number
  fx_rate_date: string
  fx_rate_source: string
  fx_rate_mode: string
  estimated_inr: number
  base_inr: number
  tax_inr: number
  gross_inr: number
  estimate_date: string
  reason: string | null
  previous_currency_code: string | null
  previous_amount: number | null
  previous_base_inr: number | null
  submitted_at: string | null
  approved_at: string | null
  decision_comments: string | null
}

export type ProjectExpenseRow = {
  id: number
  expense_code: string
  project_id: number
  employee_id: number
  expense_date: string
  category: string
  purpose: string
  amount: number
  approved_amount: number | null
  currency: 'INR'
  payment_source: 'EMPLOYEE_PAID' | 'COMPANY_PAID'
  status: string
  remarks: string | null
  phase_key: string
  linked_vendor_invoice_id: number | null
  finance_comments: string | null
  adjustment_reason: string | null
  reimbursed_at: string | null
  reimbursement_reference: string | null
}

export type VendorInvoiceRow = {
  id: number
  project_id: number
  vendor_name: string
  vendor_gstin: string | null
  invoice_number: string
  invoice_date: string
  due_date: string | null
  po_wo_reference: string | null
  category: string
  description: string
  currency_code: string
  taxable_amount: number
  cgst: number
  sgst: number
  igst: number
  other_tax: number
  gross_amount: number
  fx_rate_to_inr: number
  fx_rate_date: string | null
  fx_rate_source: string | null
  fx_rate_mode: string
  taxable_inr: number
  tax_inr: number
  gross_inr: number
  paid_amount: number
  outstanding_amount: number
  payment_status: string
  payment_source: string
  linked_employee_expense_id: number | null
  status: string
  remarks: string | null
}

export type ProjectCostSummary = {
  project_id: number
  project_code: string
  client_code: string | null
  approved_estimate_base_inr: number | null
  estimated_direct_cost_inr: number | null
  billed_net_revenue_inr: number
  payment_realization_inr: number
  employee_cost_inr: number
  vendor_cost_inr: number
  total_direct_cost_inr: number
  actual_margin_inr: number
  projected_margin_inr: number | null
  fx_gain_loss_inr: number
}

export type RevisionBrief = {
  id: number
  revision_no: number
  status: string
  is_locked: boolean
  is_baseline: boolean
  currency_code: string
  estimated_amount: number
  billing_type_label: string
  payment_terms: string | null
}

export type CommercialSummary = {
  has_commercial: boolean
  baseline: RevisionBrief | null
  latest_approved: RevisionBrief | null
  revision_count: number
}

export type BillingEntry = {
  id: number
  entry_no: number
  billing_type: string
  cumulative_billable_quantity: number | null
  quantity_unit: string | null
  milestone_id: number | null
  milestone_name: string | null
  completion_percent: number | null
  delivery_accepted: boolean
  acceptance_reference: string | null
  pm_remarks: string | null
  billing_readiness_date: string | null
  confirmed_by_name: string | null
  confirmed_at: string
}

export type OperationalReference = {
  work_packages_total: number
  work_packages_delivered: number
  completion_percent_by_packages: number | null
  total_area: number | null
  delivered_area: number | null
  area_unit: string | null
  planned_quantity: number | null
  planned_quantity_unit: string | null
  operational_completed_at: string | null
  completion_date: string | null
}

/** What the assigned Project Manager receives: type, unit and milestone NAMES only. Never a rate, value, FX or margin. */
export type PMBillingBasisView = {
  project_id: number
  project_code: string
  project_name: string
  workflow_status: string | null
  billing_type: string | null
  billing_type_label: string | null
  quantity_unit: string | null
  milestones: Array<{ id: number; sequence: number; name: string }>
  entries: BillingEntry[]
  operational_reference: OperationalReference
  can_submit: boolean
  cannot_submit_reason: string | null
  commercial_values_visible: false
}

export type BillingRecommendation = {
  project_id: number
  project_code: string
  workflow_status: string | null
  commercial_basis: CommercialEstimate | null
  pm_basis: BillingEntry | null
  pm_basis_entries: BillingEntry[]
  invoiced_to_date: { base_amount: number; quantity: number; milestone_ids: number[]; invoice_count: number }
  recommendation: null | {
    method: 'UNIT_RATE' | 'FIXED_PRICE' | 'MILESTONE'
    currency_code: string
    base_amount: number
    tax_percent: number
    tax_amount: number
    gross_amount: number
    formula: string
    estimate_revision_id: number
    billing_basis_id: number | null
    quantity?: number
    quantity_unit?: string
    unit_rate?: number
    milestone_id?: number
    milestone_name?: string
    completion_percent?: number
    other_confirmed_milestones?: Array<{ id: number; name: string }>
  }
  warnings: string[]
  operational_reference: OperationalReference
}

export const BILLING_TYPE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'fixed_price', label: 'Fixed Price' },
  { value: 'per_site', label: 'Per Site' },
  { value: 'per_sq_km', label: 'Per Sq.Km' },
  { value: 'per_km', label: 'Per Km' },
  { value: 'per_deliverable', label: 'Per Deliverable' },
  { value: 'milestone', label: 'Milestone' },
  { value: 'time_material', label: 'Time & Material' },
  { value: 'other', label: 'Other' },
]
export const UNIT_RATE_TYPES = new Set(['per_site', 'per_sq_km', 'per_km', 'per_deliverable', 'unit_rate'])
export const DEFAULT_UNIT: Record<string, string> = { per_site: 'site', per_sq_km: 'sq.km', per_km: 'km', per_deliverable: 'deliverable', unit_rate: 'unit', time_material: 'hour' }

export type CommercialAnalytics = {
  filters: { date_from: string | null; date_to: string | null; project_id: number | null; display_currency: string }
  summary_inr: Record<string, number>
  display_conversion: null | {
    currency: string
    rate_from_inr: number
    rate_date: string
    source: string
    mode: string
    summary: Record<string, number>
  }
  projects: Array<{
    project_id: number
    project_code: string
    client_code: string | null
    estimate_base_inr: number | null
    estimate_gross_inr: number | null
    baseline_revision_base_inr?: number | null
    latest_approved_revision_no?: number | null
    latest_approved_base_inr?: number | null
    commercial_variance_inr?: number | null
    fx_variance_inr?: number | null
    billed_net_inr: number
    payments_realized_inr: number
    employee_cost_inr: number
    vendor_cost_inr: number
    total_direct_cost_inr: number
    margin_inr: number
    fx_gain_loss_inr: number
  }>
  employee_costs: Array<{ employee_id: number; employee_name: string; cost_inr: number }>
  monthly: Array<{
    month: string
    billing_inr: number
    payments_inr: number
    employee_cost_inr: number
    vendor_cost_inr: number
    total_cost_inr: number
    margin_inr: number
  }>
}

export type SimpleProject = {
  id: number
  project_code: string
  project_name: string
  client_code?: string | null
  client_name?: string | null
  workflow_status?: string
  normalized_status?: string
}

export function money(value: number | null | undefined, currency = 'INR'): string {
  if (value == null || Number.isNaN(value)) return '—'
  try {
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: 2 }).format(value)
  } catch {
    return `${currency} ${value.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
  }
}

export function statusLabel(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase())
}

export function statusTone(value: string): string {
  const normalized = value.toUpperCase()
  if (['APPROVED', 'REIMBURSED', 'PAID'].includes(normalized)) return 'success'
  if (['REJECTED', 'CANCELLED'].includes(normalized)) return 'danger'
  if (['RETURNED', 'PENDING_APPROVAL', 'SUBMITTED', 'PARTIALLY_PAID'].includes(normalized)) return 'warning'
  return 'neutral'
}
