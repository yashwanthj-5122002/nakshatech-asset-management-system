import type { AdvanceProject, AdvanceStatus } from '../advancePaymentApi'

// Advance Alerts (Finance V8 Phase 4) — pure helpers for FinanceCommandCenter.
//
// Mirrors the backend notification rules in
// app/modules/finance/advance_notification_service.py so the section header
// counts always agree with the notifications produced by
// POST /finance/advance-payments/refresh-notifications:
//   1. Due            -> today >= expected_date AND status requested/pending
//   2. Overdue        -> today > final_date AND pending > 0
//   3. Partial        -> received > 0 AND received < expected
//   4. High value     -> pending > threshold (default Rs.10,00,000)
// Terminal statuses (not_required/received/adjusted/closed) never alert.

export type AdvanceAlertKind = 'due' | 'overdue' | 'partial' | 'high_value'

export interface AdvanceAlert {
  project_id: number
  project_name: string
  client: string | null
  kind: AdvanceAlertKind
  status: AdvanceStatus
  status_label: string
  pending_amount: number | null
  received_amount: number | null
  due_date: string | null
  days_overdue: number | null
  amounts_visible: boolean
}

export interface AdvanceAlertCounts {
  dueToday: number
  overdue: number
  pendingFollowUps: number
  highValue: number
  total: number
}

export const ADVANCE_HIGH_VALUE_THRESHOLD_INR = 1_000_000

// Same access matrix as backend resolve_advance_access: Finance/Admin full,
// Management high-value only, BD own projects (rows arrive pre-scoped from
// /finance/advance-payments/projects), technical PMs status-only. Production,
// QC, QA and other operational roles have no access to this section.
const ALERT_ACCESS_ROLES = new Set([
  'finance',
  'admin',
  'software_team',
  'management',
  'bd',
  'ortho',
  'lidar',
  'mobile_mapping',
  'laser_scanning',
  'civil',
])

const TERMINAL_STATUSES = new Set<AdvanceStatus>([
  'not_required',
  'received',
  'adjusted',
  'closed',
])

// One row per project; most severe condition wins for the Status column.
const KIND_PRIORITY: AdvanceAlertKind[] = ['overdue', 'due', 'partial', 'high_value']

export function canViewAdvanceAlerts(role: string | null | undefined): boolean {
  return Boolean(role && ALERT_ACCESS_ROLES.has(role))
}

function daysBetween(fromIso: string, toIso: string): number {
  const from = Date.parse(`${fromIso}T00:00:00Z`)
  const to = Date.parse(`${toIso}T00:00:00Z`)
  if (Number.isNaN(from) || Number.isNaN(to)) return 0
  return Math.round((to - from) / 86_400_000)
}

export function buildAdvanceAlerts(
  projects: AdvanceProject[],
  options: { role: string | null | undefined; today: string; thresholdInr?: number },
): AdvanceAlert[] {
  if (!canViewAdvanceAlerts(options.role)) return []
  const threshold = options.thresholdInr ?? ADVANCE_HIGH_VALUE_THRESHOLD_INR
  // Management only receives high-value escalation alerts (permission matrix).
  const managementOnly = options.role === 'management'

  const alerts: AdvanceAlert[] = []
  for (const row of projects) {
    if (TERMINAL_STATUSES.has(row.status)) continue
    const expected = row.advance_amount ?? 0
    const received = row.received_amount ?? 0
    const pending = row.pending_amount ?? 0
    const visible = row.financial_amounts_visible

    const isDue = Boolean(row.expected_date)
      && options.today >= row.expected_date!
      && (row.status === 'requested' || row.status === 'pending')
    const isOverdue = Boolean(row.final_date)
      && options.today > row.final_date!
      && pending > 0
    const isPartial = received > 0 && received < expected
    const isHighValue = pending > threshold

    if (managementOnly) {
      if (!isHighValue) continue
      alerts.push(toAlert(row, 'high_value', { visible, pending: visible ? pending : null, received: visible ? received : null }, options.today))
      continue
    }

    const kinds: AdvanceAlertKind[] = []
    if (isOverdue) kinds.push('overdue')
    if (isDue) kinds.push('due')
    if (isPartial) kinds.push('partial')
    if (isHighValue) kinds.push('high_value')
    if (kinds.length === 0) continue

    const kind = KIND_PRIORITY.find(candidate => kinds.includes(candidate)) ?? kinds[0]
    alerts.push(toAlert(row, kind, { visible, pending: visible ? pending : null, received: visible ? received : null }, options.today))
  }
  return alerts.sort((a, b) => {
    const rank = KIND_PRIORITY.indexOf(a.kind) - KIND_PRIORITY.indexOf(b.kind)
    return rank !== 0 ? rank : a.project_name.localeCompare(b.project_name)
  })
}

function toAlert(
  row: AdvanceProject,
  kind: AdvanceAlertKind,
  amounts: { visible: boolean; pending: number | null; received: number | null },
  today: string,
): AdvanceAlert {
  const dueDate = kind === 'overdue' ? row.final_date : (row.expected_date || row.final_date)
  const daysOverdue = kind === 'overdue' && row.final_date
    ? Math.max(daysBetween(row.final_date, today), 0)
    : null
  return {
    project_id: row.project_id,
    project_name: row.project_name,
    client: row.client,
    kind,
    status: row.status,
    status_label: row.status_label,
    pending_amount: amounts.pending,
    received_amount: amounts.received,
    due_date: dueDate,
    days_overdue: daysOverdue,
    amounts_visible: amounts.visible,
  }
}

export function summarizeAdvanceAlerts(alerts: AdvanceAlert[]): AdvanceAlertCounts {
  return {
    dueToday: alerts.filter(alert => alert.kind === 'due').length,
    overdue: alerts.filter(alert => alert.kind === 'overdue').length,
    pendingFollowUps: alerts.filter(alert => alert.kind === 'partial').length,
    highValue: alerts.filter(alert => alert.kind === 'high_value').length,
    total: alerts.length,
  }
}

// "15-10-2026" style display date for the alert rows.
export function formatAdvanceAlertDate(iso: string | null): string {
  if (!iso) return '—'
  const [year, month, day] = iso.split('-')
  if (!year || !month || !day) return iso
  return `${day}-${month}-${year}`
}
