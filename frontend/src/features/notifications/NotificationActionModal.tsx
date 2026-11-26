/**
 * NotificationActionModal - the ONE reusable centre popup for the whole ERP.
 *
 * TYPE B (business notification): `notification` is set. Closing the popup NEVER
 * resolves it; the bell item stays pending until the real workflow action runs.
 *
 * TYPE A (immediate feedback): `feedback` is set. Pure presentation only - no
 * notification record is created and no business state changes.
 *
 * Actions are opt-in through `actions`; the modal never invents an approve or
 * reject endpoint and never mutates business state by itself.
 */
import {
  AlertTriangle,
  BellRing,
  CalendarClock,
  CheckCircle2,
  CircleAlert,
  ClipboardList,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useRef } from 'react'
import './notification-popup.css'
import {
  isSafeInternalPath,
  type FeedbackPayload,
  type NotificationSeverity,
  type PopupAction,
  type PopupFact,
  type PopupNotification,
} from './notificationTypes'

interface Props {
  notification?: PopupNotification | null
  feedback?: FeedbackPayload | null
  actions?: PopupAction[]
  onClose: () => void
  queueRemaining?: number
  busy?: boolean
}

function severityOf(notification?: PopupNotification | null, feedback?: FeedbackPayload | null): NotificationSeverity {
  // TYPE A 'error' maps onto the 'danger' visual severity.
  if (feedback) return feedback.kind === 'error' ? 'danger' : feedback.kind
  const raw = (notification?.severity ?? 'info').toLowerCase()
  return raw === 'success' || raw === 'warning' || raw === 'danger' ? raw : 'info'
}

const SEVERITY_ICON: Record<NotificationSeverity, typeof BellRing> = {
  info: BellRing,
  success: CheckCircle2,
  warning: CalendarClock,
  danger: CircleAlert,
}

function businessFacts(notification: PopupNotification): PopupFact[] {
  const meta = notification.metadata ?? {}
  const facts: PopupFact[] = []
  if (meta.project_name) facts.push({ label: 'Project', value: String(meta.project_name) })
  if (meta.client_name) facts.push({ label: 'Client', value: String(meta.client_name) })
  if (meta.submitted_by) facts.push({ label: 'Submitted By', value: String(meta.submitted_by) })
  if (meta.submitted_at) facts.push({ label: 'Submitted At', value: String(meta.submitted_at) })
  if (meta.current_stage) facts.push({ label: 'Current Stage', value: String(meta.current_stage) })
  if (meta.amount != null) facts.push({ label: 'Amount', value: `${meta.currency ?? ''} ${meta.amount}`.trim() })
  if (meta.due_date) facts.push({ label: 'Due Date', value: String(meta.due_date) })
  if (meta.days_overdue != null) facts.push({ label: 'Days Overdue', value: String(meta.days_overdue), tone: 'danger' })
  return facts
}
export function NotificationActionModal({
  notification,
  feedback,
  actions = [],
  onClose,
  queueRemaining = 0,
  busy = false,
}: Props) {
  const cardRef = useRef<HTMLDivElement | null>(null)
  const closeRef = useRef<HTMLButtonElement | null>(null)
  const severity = severityOf(notification, feedback)
  const Icon = feedback?.kind === 'error' ? AlertTriangle : SEVERITY_ICON[severity]
  const isBusiness = Boolean(notification)
  const metadata = notification?.metadata ?? {}

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeRef.current?.focus()

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) {
        event.stopPropagation()
        onClose()
        return
      }
      if (event.key !== 'Tab') return
      // Focus trap: keyboard focus can never land on an approval action by accident.
      const focusables = cardRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), a[href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      )
      if (!focusables || focusables.length === 0) return
      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown, true)
    return () => {
      document.removeEventListener('keydown', onKeyDown, true)
      document.body.style.overflow = previousOverflow
      previouslyFocused?.focus?.()
    }
  }, [busy, onClose])

  const goToFirstIssue = useCallback(() => {
    const field = feedback?.firstIssueField
    if (!field) return
    const element =
      document.querySelector<HTMLElement>(`#${CSS.escape(field)}`) ??
      document.querySelector<HTMLElement>(`[name="${CSS.escape(field)}"]`)
    if (!element) return
    element.classList.add('nk-notification-field-error')
    element.scrollIntoView({ behavior: 'smooth', block: 'center' })
    element.focus({ preventScroll: true })
    window.setTimeout(() => element.classList.remove('nk-notification-field-error'), 4000)
  }, [feedback?.firstIssueField])

  const defaultActions: PopupAction[] = isBusiness
    ? [
        ...(isSafeInternalPath(notification?.target_url)
          ? [{ id: 'view', label: 'View Details', variant: 'default' as const }]
          : []),
        { id: 'later', label: 'Later', variant: 'default' as const },
      ]
    : feedback?.issues?.length
      ? [{ id: 'fix', label: 'Go To First Issue', variant: 'primary' as const }]
      : [{ id: 'done', label: 'Done', variant: 'primary' as const }]

  const resolvedActions = actions.length > 0 ? actions : defaultActions

  const handleAction = (action: PopupAction) => {
    if (action.onSelect) {
      void action.onSelect(notification ?? undefined)
      return
    }
    if (action.id === 'fix') {
      goToFirstIssue()
      return
    }
    onClose()
  }

  const title = feedback?.title ?? notification?.title ?? 'Notification'
  const eyebrow = feedback?.eyebrow ?? (notification?.requires_action ? 'Action Required' : 'Notification')
  const message = feedback?.message ?? notification?.message ?? ''
  const facts = feedback?.facts ?? (isBusiness && notification ? businessFacts(notification) : [])
return (
    <div
      className="nk-notification-popup-backdrop"
      onMouseDown={event => {
        if (event.target === event.currentTarget && !busy) onClose()
      }}
    >
      <div
        className="nk-notification-popup"
        ref={cardRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="nk-notification-popup-title"
      >
        <header className={`nk-notification-popup-header severity-${severity}`}>
          <span className="nk-notification-popup-header-icon">
            <Icon size={19} aria-hidden="true" />
          </span>
          <div>
            <span className="nk-notification-popup-eyebrow">{eyebrow}</span>
            <h2 className="nk-notification-popup-title" id="nk-notification-popup-title">{title}</h2>
          </div>
          <button
            type="button"
            className="nk-notification-popup-close"
            ref={closeRef}
            onClick={onClose}
            disabled={busy}
            aria-label="Close notification"
          >
            <X size={17} aria-hidden="true" />
          </button>
        </header>

        <div className="nk-notification-popup-body">
          {message && <p className="nk-notification-popup-message">{message}</p>}

          {!!feedback?.issues?.length && (
            <>
              <p className="nk-notification-popup-message">Please correct the following:</p>
              <ul className="nk-notification-popup-issues">
                {feedback.issues.map((issue, index) => (
                  <li key={`${issue}-${index}`}>{issue}</li>
                ))}
              </ul>
            </>
          )}

          {!!facts.length && (
            <dl className="nk-notification-popup-facts">
              {facts.map(fact => (
                <div
                  key={fact.label}
                  className={`nk-notification-popup-fact${fact.tone ? ` is-${fact.tone}` : ''}`}
                >
                  <dt>{fact.label}</dt>
                  <dd>{fact.value}</dd>
                </div>
              ))}
            </dl>
          )}

          {metadata.reason && (
            <div className="nk-notification-popup-reason">
              <strong>
                {metadata.returned_by ? `Returned By: ${metadata.returned_by}` : 'Reason'}
              </strong>
              {metadata.reason}
              {metadata.required_action && (
                <>
                  <br />
                  <strong>Required Action</strong>
                  {metadata.required_action}
                </>
              )}
            </div>
          )}

          {isBusiness && (
            <div className="nk-notification-popup-reason">
              <strong>Closing this popup keeps the item pending.</strong>
              It stays in your notifications until the required action is completed.
            </div>
          )}
        </div>

        <footer className="nk-notification-popup-footer">
          {queueRemaining > 0 && (
            <span className="nk-notification-popup-queue-hint">
              <ClipboardList size={12} aria-hidden="true" /> {queueRemaining} more pending
            </span>
          )}
          {resolvedActions.map(action => (
            <button
              key={action.id}
              type="button"
              className={action.variant && action.variant !== 'default' ? `is-${action.variant}` : undefined}
              disabled={busy}
              onClick={() => handleAction(action)}
            >
              {action.label}
            </button>
          ))}
        </footer>
      </div>
    </div>
  )
}