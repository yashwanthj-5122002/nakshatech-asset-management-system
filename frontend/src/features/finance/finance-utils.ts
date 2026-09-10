import type { FinanceClaimStatus, FinanceClaimType } from '../../types'

export const financeClaimTypeLabels: Record<FinanceClaimType, string> = {
  advance: 'Advance Request',
  reimbursement: 'Reimbursement',
  additional_advance: 'Additional Advance',
}

export const financeStatusLabels: Record<FinanceClaimStatus, string> = {
  draft: 'Draft',
  submitted: 'Pending Admin Verification',
  admin_approved: 'Pending Finance Verification',
  admin_rejected: 'Rejected by Admin',
  admin_sent_back: 'Sent Back by Admin',
  finance_approved: 'Finance Approved / Payment Pending',
  partially_paid: 'Partially Paid',
  finance_rejected: 'Rejected by Finance',
  finance_sent_back: 'Sent Back by Finance',
  paid: 'Paid / Amount Released',
}

export const financeExpenseCategories = [
  ['hotel', 'Hotel / Accommodation'],
  ['food', 'Food / Daily Allowance'],
  ['travel', 'Travel / Tickets'],
  ['fuel', 'Fuel / Vehicle'],
  ['machine_parts', 'Machine / Equipment Parts'],
  ['equipment_rental', 'Equipment Rental'],
  ['site_expense', 'Site Expense'],
  ['material', 'Material / Consumables'],
  ['vendor_payment', 'Vendor Payment'],
  ['software', 'Software / License'],
  ['other', 'Other'],
] as const

export function formatInr(value: number | undefined | null): string {
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(value || 0)
}

export function financeStatusTone(status: FinanceClaimStatus): string {
  if (status === 'paid' || status === 'finance_approved') return 'success'
  if (status === 'partially_paid') return 'warning'
  if (status === 'admin_rejected' || status === 'finance_rejected') return 'danger'
  if (status === 'admin_sent_back' || status === 'finance_sent_back') return 'warning'
  if (status === 'submitted' || status === 'admin_approved') return 'pending'
  return 'draft'
}

export function financeClaimTypeTone(type: FinanceClaimType): string {
  if (type === 'advance') return 'advance'
  if (type === 'reimbursement') return 'reimbursement'
  return 'additional'
}
