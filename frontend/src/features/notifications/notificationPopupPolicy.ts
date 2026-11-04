/**
 * Presentation-only popup policy for BD, Finance, Chethan and Vinod.
 *
 * Never mutates notifications, changes approvals, or affects the bell inbox.
 * The backend popup-queue endpoint must already return notifications scoped to
 * the signed-in user; this filter is NOT an authorization mechanism.
 */
import type { PopupNotification } from './notificationTypes'

type Viewer = {
  role?: string | null
  full_name?: string | null
  email?: string | null
  username?: string | null
  id?: string | number | null
} | null | undefined

const norm = (value: unknown): string => String(value ?? '').trim().toLowerCase()

function restrictedViewer(viewer: Viewer): boolean {
  if (!viewer) return false
  const role = norm(viewer.role)
  if (role === 'bd' || role === 'finance') return true
  const name = norm(viewer.full_name)
  const emailLocal = norm(viewer.email).split('@')[0]
  const username = norm(viewer.username)
  // These are named accounts, not all users with the management/admin role.
  return ['chethan', 'vinod'].some(person =>
    name === person || name.startsWith(`${person} `) ||
    emailLocal === person || emailLocal.startsWith(`${person}.`) ||
    username === person,
  )
}

function isApprovalRequest(notification: PopupNotification): boolean {
  if (notification.is_resolved || notification.requires_action !== true) return false
  const meta = notification.metadata ?? {}
  const typeFields = [
    meta.notification_type, meta.action_type, meta.event_type,
    meta.workflow_type, meta.category, meta.kind,
  ].map(norm)
  if (typeFields.some(type => /(^|[_\s-])approv(?:al|e)([_\s-]|$)/.test(type))) return true
  const requiredAction = norm(meta.required_action)
  if (/\b(approve|approval)\b/.test(requiredAction)) return true
  // Titles are allowed only with requires_action=true. Past-tense informational
  // notifications such as "Billing basis confirmed" never match.
  return /\b(approve|approval)\b/.test(norm(notification.title))
}

function addressedToViewer(notification: PopupNotification, viewer: NonNullable<Viewer>): boolean {
  const meta = notification.metadata ?? {}
  const identityKeys = [
    'assigned_to_user_id', 'assigned_user_id', 'approver_user_id',
    'approver_id', 'recipient_user_id', 'recipient_id',
    'assigned_to_email', 'approver_email', 'recipient_email',
    'assigned_to', 'assigned_approver', 'approver_name', 'recipient_name',
  ]
  const targets = identityKeys
    .map(key => meta[key])
    .filter((value): value is string | number =>
      (typeof value === 'string' && value.trim() !== '') || typeof value === 'number',
    )
    .map(norm)

  // The API must scope rows to the logged-in recipient. If explicit recipient
  // identity exists in metadata, additionally reject other people's approvals.
  if (targets.length === 0) return true
  const viewerValues = [viewer.id, viewer.email, viewer.full_name, viewer.username]
    .map(norm).filter(Boolean)
  const name = norm(viewer.full_name)
  if (name) viewerValues.push(name.split(/\s+/)[0])
  return targets.some(target => viewerValues.includes(target))
}

export function filterAutomaticPopupQueue(
  queue: PopupNotification[],
  viewer: Viewer,
): PopupNotification[] {
  if (!restrictedViewer(viewer)) return queue
  return queue.filter(item => isApprovalRequest(item) && addressedToViewer(item, viewer!))
}
