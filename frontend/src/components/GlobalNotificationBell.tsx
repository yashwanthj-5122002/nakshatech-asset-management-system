import {
  Bell,
  Check,
  CheckCheck,
  CircleAlert,
  FileCheck2,
  LifeBuoy,
  Sparkles,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { apiFetch } from '../lib/api'
import { formatNotificationTimestamp } from '../lib/dateTime'

type NotificationCategory = 'approval' | 'ticket' | 'system'
type NotificationFilter = 'all' | 'unread' | 'approval' | 'ticket'

interface GlobalNotification {
  id: number
  recipient_role?: string | null
  event_type: string
  category: NotificationCategory | string
  title: string
  message: string
  target_url?: string | null
  is_read: boolean
  read_at?: string | null
  created_at: string
}

interface UnreadCountResponse {
  unread_count: number
}

const FILTERS: Array<{ id: NotificationFilter; label: string }> = [
  { id: 'all', label: 'All' },
  { id: 'unread', label: 'Unread' },
  { id: 'approval', label: 'Approvals' },
  { id: 'ticket', label: 'Tickets' },
]

const POLL_INTERVAL_MS = 30_000
const SLA_REFRESH_INTERVAL_MS = 60_000
const SLA_REFRESH_ROLES = new Set(['admin', 'it', 'drone', 'software_team', 'management'])

function categoryLabel(category: string): string {
  if (category === 'approval') return 'Approval'
  if (category === 'ticket') return 'Ticket'
  return 'System'
}

function NotificationCategoryIcon({ category }: { category: string }) {
  if (category === 'approval') return <FileCheck2 size={15} aria-hidden="true" />
  if (category === 'ticket') return <LifeBuoy size={15} aria-hidden="true" />
  return <Sparkles size={15} aria-hidden="true" />
}

function listPath(filter: NotificationFilter): string {
  const params = new URLSearchParams({ limit: '100' })
  if (filter === 'unread') params.set('unread_only', 'true')
  if (filter === 'approval' || filter === 'ticket') params.set('category', filter)
  return `/notifications/global?${params.toString()}`
}

function isSafeInternalPath(value: string | null | undefined): value is string {
  return Boolean(value && value.startsWith('/') && !value.startsWith('//'))
}

export function GlobalNotificationBell() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const location = useLocation()
  const rootRef = useRef<HTMLDivElement | null>(null)
  const listRequestIdRef = useRef(0)
  const lastSlaRefreshRef = useRef(0)
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState<NotificationFilter>('all')
  const [notifications, setNotifications] = useState<GlobalNotification[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [markingAll, setMarkingAll] = useState(false)

  const refreshUnreadCount = useCallback(async () => {
    try {
      const role = user?.role || ''
      const now = Date.now()
      if (SLA_REFRESH_ROLES.has(role) && now - lastSlaRefreshRef.current >= SLA_REFRESH_INTERVAL_MS) {
        lastSlaRefreshRef.current = now
        try {
          await apiFetch<{ created: number }>('/notifications/global/refresh-ticket-sla', { method: 'POST' })
        } catch {
          // SLA refresh is best-effort and must never break notification polling.
        }
      }
      const response = await apiFetch<UnreadCountResponse>('/notifications/global/unread-count')
      setUnreadCount(Math.max(0, response.unread_count || 0))
    } catch {
      // Notification polling must never interrupt the surrounding application UI.
    }
  }, [user?.role])

  const loadNotifications = useCallback(async (selectedFilter: NotificationFilter) => {
    const requestId = ++listRequestIdRef.current
    setLoading(true)
    setError('')
    try {
      const response = await apiFetch<GlobalNotification[]>(listPath(selectedFilter))
      if (requestId === listRequestIdRef.current) setNotifications(response)
    } catch {
      if (requestId === listRequestIdRef.current) setError('Notifications are temporarily unavailable.')
    } finally {
      if (requestId === listRequestIdRef.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refreshUnreadCount()
    const timer = window.setInterval(() => void refreshUnreadCount(), POLL_INTERVAL_MS)
    const handleFocus = () => void refreshUnreadCount()
    window.addEventListener('focus', handleFocus)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('focus', handleFocus)
    }
  }, [refreshUnreadCount])

  useEffect(() => {
    if (!open) return
    void loadNotifications(filter)
    void refreshUnreadCount()
  }, [filter, loadNotifications, open, refreshUnreadCount])

  useEffect(() => {
    if (!open) return

    const handlePointerDown = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false)
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }

    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  useEffect(() => {
    setOpen(false)
  }, [location.pathname, location.search])

  const markRead = useCallback(async (notification: GlobalNotification) => {
    if (notification.is_read) return notification
    const updated = await apiFetch<GlobalNotification>(`/notifications/global/${notification.id}/read`, {
      method: 'POST',
    })
    setNotifications(current => current.map(item => item.id === updated.id ? updated : item))
    setUnreadCount(current => Math.max(0, current - 1))
    return updated
  }, [])

  async function openNotification(notification: GlobalNotification) {
    try {
      await markRead(notification)
    } catch {
      // A transient read-state error should not block a valid deep link.
    }

    setOpen(false)
    if (isSafeInternalPath(notification.target_url)) navigate(notification.target_url)
  }

  async function markAllRead() {
    if (unreadCount === 0 || markingAll) return
    setMarkingAll(true)
    setError('')
    try {
      await apiFetch<{ updated: number }>('/notifications/global/read-all', { method: 'POST' })
      setUnreadCount(0)
      if (filter === 'unread') {
        setNotifications([])
      } else {
        const readAt = new Date().toISOString()
        setNotifications(current => current.map(item => ({ ...item, is_read: true, read_at: item.read_at || readAt })))
      }
    } catch {
      setError('Could not mark notifications as read. Please try again.')
    } finally {
      setMarkingAll(false)
    }
  }

  const badgeText = unreadCount > 99 ? '99+' : String(unreadCount)

  return (
    <div className="notification-bell-shell" ref={rootRef}>
      <button
        type="button"
        className={`notification-bell-button ${open ? 'active' : ''}`}
        onClick={() => setOpen(current => !current)}
        aria-label={unreadCount > 0 ? `Notifications, ${unreadCount} unread` : 'Notifications'}
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        <Bell size={18} aria-hidden="true" />
        {unreadCount > 0 && <span className="notification-unread-badge" aria-hidden="true">{badgeText}</span>}
      </button>

      {open && (
        <section className="notification-drawer" role="dialog" aria-label="Notifications">
          <header className="notification-drawer-header">
            <div>
              <span className="notification-eyebrow">Activity centre</span>
              <h2>Notifications</h2>
            </div>
            <div className="notification-header-actions">
              <button
                type="button"
                className="notification-mark-all"
                onClick={() => void markAllRead()}
                disabled={unreadCount === 0 || markingAll}
                title="Mark all notifications as read"
              >
                <CheckCheck size={16} aria-hidden="true" />
                <span>{markingAll ? 'Updating...' : 'Mark all read'}</span>
              </button>
              <button type="button" className="notification-close" onClick={() => setOpen(false)} aria-label="Close notifications">
                <X size={18} aria-hidden="true" />
              </button>
            </div>
          </header>

          <div className="notification-filters" role="tablist" aria-label="Notification filters">
            {FILTERS.map(item => (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={filter === item.id}
                className={filter === item.id ? 'active' : ''}
                onClick={() => setFilter(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>

          <div className="notification-list" aria-live="polite">
            {loading && (
              <div className="notification-state">
                <span className="notification-loading-dot" />
                <span>Loading notifications...</span>
              </div>
            )}

            {!loading && error && (
              <div className="notification-state error">
                <CircleAlert size={18} aria-hidden="true" />
                <span>{error}</span>
                <button type="button" onClick={() => void loadNotifications(filter)}>Retry</button>
              </div>
            )}

            {!loading && !error && notifications.length === 0 && (
              <div className="notification-empty">
                <Bell size={22} aria-hidden="true" />
                <strong>{filter === 'unread' ? 'You are all caught up' : 'No notifications yet'}</strong>
                <span>{filter === 'approval' ? 'Approval updates will appear here.' : filter === 'ticket' ? 'Ticket updates will appear here.' : 'New activity will appear here when it arrives.'}</span>
              </div>
            )}

            {!loading && !error && notifications.map(notification => (
              <button
                type="button"
                key={notification.id}
                className={`notification-item ${notification.is_read ? 'read' : 'unread'}`}
                onClick={() => void openNotification(notification)}
              >
                <span className={`notification-category-icon ${notification.category}`}>
                  <NotificationCategoryIcon category={notification.category} />
                </span>
                <span className="notification-item-copy">
                  <span className="notification-item-meta">
                    <span className={`notification-category-chip ${notification.category}`}>{categoryLabel(notification.category)}</span>
                    <span className="notification-item-time">{formatNotificationTimestamp(notification.created_at)}</span>
                  </span>
                  <strong>{notification.title}</strong>
                  <span className="notification-message">{notification.message}</span>
                </span>
                <span
                  className={`notification-item-status ${notification.is_read ? 'read' : 'unread'}`}
                  aria-label={notification.is_read ? 'Read' : 'Unread'}
                >
                  {notification.is_read ? <Check size={12} aria-hidden="true" /> : <span className="notification-unread-dot" aria-hidden="true" />}
                  <span>{notification.is_read ? 'Read' : 'New'}</span>
                </span>
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
