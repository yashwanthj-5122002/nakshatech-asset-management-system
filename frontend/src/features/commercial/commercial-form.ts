import type { CommercialEstimate } from './types'
import { DEFAULT_UNIT, UNIT_RATE_TYPES } from './types'

/** Editable state of the "Commercial & Billing Details" (Revision 1) section. All money stays a string until submit. */
export type CommercialFormState = {
  scope_description: string
  billing_type: string
  currency_code: string
  estimated_amount: string
  taxable_base_amount: string
  tax_percent: string
  payment_terms: string
  expected_billing_milestone: string
  projected_payment_date: string
  quotation_reference: string
  po_wo_reference: string
  notes: string
  unit_rate: string
  estimated_quantity: string
  quantity_unit: string
  milestones: Array<{ milestone_name: string; percent: string }>
  estimated_direct_cost_inr: string
  fx_rate_to_inr: string
  fx_rate_mode: string
  fx_override_reason: string
}

export const emptyCommercialForm = (): CommercialFormState => ({
  scope_description: '', billing_type: 'fixed_price', currency_code: 'INR', estimated_amount: '', taxable_base_amount: '', tax_percent: '18',
  payment_terms: '', expected_billing_milestone: '', projected_payment_date: '', quotation_reference: '', po_wo_reference: '', notes: '',
  unit_rate: '', estimated_quantity: '', quantity_unit: '', milestones: [], estimated_direct_cost_inr: '',
  fx_rate_to_inr: '', fx_rate_mode: 'MANUAL_OVERRIDE', fx_override_reason: '',
})

export function commercialFormFromRevision(rev: CommercialEstimate): CommercialFormState {
  return {
    scope_description: rev.scope_description, billing_type: rev.billing_type, currency_code: rev.currency_code,
    estimated_amount: String(rev.estimated_amount), taxable_base_amount: String(rev.taxable_base_amount), tax_percent: String(rev.tax_percent),
    payment_terms: rev.payment_terms || '', expected_billing_milestone: rev.expected_billing_milestone || '',
    projected_payment_date: rev.projected_payment_date || '',
    quotation_reference: rev.quotation_reference || '', po_wo_reference: rev.po_wo_reference || '', notes: rev.notes || '',
    unit_rate: rev.unit_rate == null ? '' : String(rev.unit_rate), estimated_quantity: rev.estimated_quantity == null ? '' : String(rev.estimated_quantity),
    quantity_unit: rev.quantity_unit || '',
    milestones: (rev.milestones ?? []).map(m => ({ milestone_name: m.milestone_name, percent: m.percent == null ? '' : String(m.percent) })),
    estimated_direct_cost_inr: rev.estimated_direct_cost_inr == null ? '' : String(rev.estimated_direct_cost_inr),
    fx_rate_to_inr: '', fx_rate_mode: 'MANUAL_OVERRIDE', fx_override_reason: '',
  }
}

const num = (value: string) => (value.trim() === '' ? null : Number(value))

export function commercialFormProblems(form: CommercialFormState): string[] {
  const problems: string[] = []
  if (form.scope_description.trim().length < 2) problems.push('Scope / Commercial Basis is required.')
  if (form.payment_terms.trim().length < 2) problems.push('Payment Terms are required (for example: 30 days).')
  const amount = num(form.estimated_amount)
  if (amount == null || !(amount > 0)) problems.push('Estimated Contract Amount must be greater than zero.')
  const base = num(form.taxable_base_amount)
  if (base != null && amount != null && base > amount) problems.push('Taxable / Base Amount cannot exceed the Estimated Contract Amount.')
  if (UNIT_RATE_TYPES.has(form.billing_type)) {
    const rate = num(form.unit_rate)
    if (rate == null || !(rate > 0)) problems.push('A rate per unit is required for this billing type.')
  }
  if (form.billing_type === 'milestone') {
    if (!form.milestones.length) problems.push('Add at least one billing milestone.')
    const total = form.milestones.reduce((sum, m) => sum + (Number(m.percent) || 0), 0)
    if (form.milestones.some(m => m.milestone_name.trim().length < 2 || !(Number(m.percent) > 0))) problems.push('Each milestone needs a name and a percentage.')
    if (total > 100) problems.push('Milestone percentages cannot add up to more than 100%.')
  }
  if (form.currency_code !== 'INR' && form.fx_rate_to_inr.trim() && form.fx_override_reason.trim().length < 3) problems.push('A reason is required when entering the exchange rate manually.')
  return problems
}

export function commercialFormToPayload(form: CommercialFormState, estimateDate?: string) {
  const foreign = form.currency_code !== 'INR'
  const manual = foreign && form.fx_rate_to_inr.trim() ? Number(form.fx_rate_to_inr) : null
  const unitBased = UNIT_RATE_TYPES.has(form.billing_type) || (form.billing_type === 'time_material' && form.unit_rate.trim() !== '')
  return {
    scope_description: form.scope_description.trim(),
    billing_type: form.billing_type,
    currency_code: form.currency_code,
    estimated_amount: Number(form.estimated_amount),
    taxable_base_amount: form.taxable_base_amount.trim() ? Number(form.taxable_base_amount) : Number(form.estimated_amount),
    tax_percent: Number(form.tax_percent || 0),
    payment_terms: form.payment_terms.trim(),
    expected_billing_milestone: form.expected_billing_milestone.trim() || null,
    projected_payment_date: form.projected_payment_date || null,
    quotation_reference: form.quotation_reference.trim() || null,
    po_wo_reference: form.po_wo_reference.trim() || null,
    notes: form.notes.trim() || null,
    unit_rate: unitBased ? num(form.unit_rate) : null,
    estimated_quantity: unitBased ? num(form.estimated_quantity) : null,
    quantity_unit: unitBased ? (form.quantity_unit.trim() || DEFAULT_UNIT[form.billing_type] || null) : null,
    milestones: form.billing_type === 'milestone' ? form.milestones.map(m => ({ milestone_name: m.milestone_name.trim(), percent: Number(m.percent) })) : [],
    estimated_direct_cost_inr: num(form.estimated_direct_cost_inr),
    ...(estimateDate ? { estimate_date: estimateDate } : {}),
    fx_rate_to_inr: manual,
    fx_rate_mode: manual ? form.fx_rate_mode : null,
    fx_override_reason: manual ? form.fx_override_reason.trim() || null : null,
  }
}
