/**
 * Shared helpers for the Client Register / Project Register presentation used
 * by Business Development (mutating) and Finance (read-only).
 */

export type StatusOption = { value: string; label: string }

export function label(value: string) { return value.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase()) }

export const FINANCE_STATUS_OPTIONS: StatusOption[] = [
  { value: 'draft', label: 'Draft' },
  { value: 'pending', label: 'Pending Finance' },
  { value: 'returned', label: 'Returned' },
  { value: 'approved', label: 'Approved' },
]

export const OPERATIONAL_STATUS_OPTIONS: StatusOption[] = [
  { value: 'not_started', label: 'Not Started' },
  { value: 'active', label: 'Active' },
  { value: 'closure', label: 'Closure Pending' },
  { value: 'closed', label: 'Closed' },
]

/** Fields the register filters read. `workflow_status` is null for projects that never entered the BD workflow. */
export type ProjectFilterFields = {
  project_code: string
  client_code?: string | null
  workflow_status?: string | null
  /** Backend-normalized status (case-folded across the legacy and V8.1 lifecycle spellings). */
  normalized_status?: string | null
  lifecycle_status?: string | null
}

/** The status every register decision keys on. Null only for legacy Project Master rows with no workflow. */
export function statusKey(row: Pick<ProjectFilterFields, 'workflow_status' | 'normalized_status'>): string | null {
  return row.normalized_status ?? row.workflow_status ?? null
}

export function financeBucket(status?: string | null) {
  if (!status) return 'legacy'
  if (status === 'draft') return 'draft'
  if (status === 'pending_finance_approval') return 'pending'
  if (status === 'finance_returned') return 'returned'
  return 'approved'
}

export function operationalBucket(status?: string | null, lifecycle?: string | null) {
  if (!status) {
    // Legacy Project Master record: fall back to its master lifecycle. Anything
    // that does not map cleanly is left out of the operational filters (still
    // listed under "All") rather than being assigned a workflow stage it never had.
    if (lifecycle === 'active') return 'active'
    if (lifecycle === 'upcoming') return 'not_started'
    return 'other'
  }
  if (status === 'closed') return 'closed'
  if (status === 'finance_closure_pending') return 'closure'
  if (['pm_assigned', 'team_assigned', 'in_progress'].includes(status)) return 'active'
  return 'not_started'
}

export function financeLabel(row: Pick<ProjectFilterFields, 'workflow_status' | 'normalized_status'>) {
  return row.workflow_status ? label(row.workflow_status) : statusKey(row) ? label(statusKey(row)!) : 'Legacy Record'
}

export function operationalLabel(row: Pick<ProjectFilterFields, 'workflow_status' | 'normalized_status' | 'lifecycle_status'>) {
  const key = statusKey(row)
  return key ? label(operationalBucket(key)) : label(row.lifecycle_status || 'not_recorded')
}

export function filterProjects<T extends ProjectFilterFields>(rows: T[], query: string, financeFilter: string, operationalFilter: string): T[] {
  const needle = query.trim().toLowerCase()
  return rows.filter(row =>
    (!needle || row.project_code.toLowerCase().includes(needle) || (row.client_code || '').toLowerCase().includes(needle)) &&
    (financeFilter === 'all' || financeBucket(statusKey(row)) === financeFilter) &&
    (operationalFilter === 'all' || operationalBucket(statusKey(row), row.lifecycle_status) === operationalFilter))
}
