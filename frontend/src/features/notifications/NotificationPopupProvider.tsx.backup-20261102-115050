/**
 * NotificationPopupProvider - ONE application-level notification experience.
 *
 * Mounted in the app shell so a popup reaches the user regardless of the page
 * they are viewing. It owns:
 *
 *  - a single polling loop for the popup queue (no per-page timers);
 *  - a queue that shows ONE modal at a time;
 *  - session-level popup acknowledgement, so a dismissed popup does not
 *    reappear on every render/poll while the bell item stays pending;
 *  - ONE centralised overdue reminder timer that resurfaces existing persisted
 *    reminder rows on the configured interval. It NEVER inserts a notification.
 *
 * Closing a popup is intentionally side-effect free with respect to business
 * state: it only records that the popup was seen in this session.
 */
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { useAuth } from '../../context/AuthContext'
import { apiFetch } from '../../lib/api'
import {
  type FeedbackPayload,
  type NotificationSettings,
  type PopupNotification,
} from './notificationTypes'

const POPUP_POLL_MS = 30_000
const SESSION_KEY = 'nk_notification_popup_seen'

interface PopupContextValue {
  current: PopupNotification | null
  queueRemaining: number
  feedback: FeedbackPayload | null
  busy: boolean
  settings: NotificationSettings | null
  showFeedback: (payload: FeedbackPayload) => void
  clearFeedback: () => void
  dismissCurrent: () => void
  refresh: () => void
  updateSettings: (minutes: number) => Promise<void>
}

const PopupContext = createContext<PopupContextValue | undefined>(undefined)

function readSession(): Record<string, number> {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY)
    const parsed = raw ? JSON.parse(raw) : {}
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, number>) : {}
  } catch {
    return {}
  }
}

function writeSession(map: Record<string, number>) {
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(map))
  } catch {
    /* storage unavailable - dedupe degrades, never breaks */
  }
}

export function NotificationPopupProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const [queue, setQueue] = useState<PopupNotification[]>([])
  const [feedback, setFeedback] = useState<FeedbackPayload | null>(null)
  const [busy, setBusy] = useState(false)
  const [settings, setSettings] = useState<NotificationSettings | null>(null)
  const seenRef = useRef<Record<string, number>>(readSession())
  const reminderRef = useRef<number | null>(null)

  const isAuthenticated = Boolean(user)

  // ---- logout / login: never leak one user's popups into another's session ----
  useEffect(() => {
    if (isAuthenticated) return
    seenRef.current = {}
    writeSession({})
    setQueue([])
    setFeedback(null)
    if (reminderRef.current !== null) {
      window.clearInterval(reminderRef.current)
      reminderRef.current = null
    }
  }, [isAuthenticated])

  const load = useCallback(async () => {
    if (!isAuthenticated) return
    try {
      const rows = await apiFetch<PopupNotification[]>('/notifications/global/popup-queue?limit=5')
      setQueue(Array.isArray(rows) ? rows : [])
    } catch {
      // A failed popup fetch must never break the ERP.
      setQueue([])
    }
  }, [isAuthenticated])

  useEffect(() => {
    if (!isAuthenticated) return
    void load()
    const timer = window.setInterval(() => void load(), POPUP_POLL_MS)
    return () => window.clearInterval(timer)
  }, [isAuthenticated, load])

  const loadSettings = useCallback(async () => {
    if (!isAuthenticated) return
    try {
      setSettings(
        await apiFetch<NotificationSettings>('/notifications/global/settings/notification-settings'),
      )
    } catch {
      setSettings(null)
    }
  }, [isAuthenticated])

  useEffect(() => {
    if (!isAuthenticated) {
      setSettings(null)
      return
    }
    seenRef.current = readSession()
    void loadSettings()
  }, [isAuthenticated, loadSettings])

  // ---- ONE centralised overdue reminder timer (never one per notification) ----
  useEffect(() => {
    if (!isAuthenticated || !settings) return
    const minutes = settings.overdue_popup_reminder_minutes || settings.default_minutes || 10
    if (reminderRef.current !== null) window.clearInterval(reminderRef.current)
    reminderRef.current = window.setInterval(() => {
      // Resurface reminders by letting their session popup entry expire.
      const now = Date.now()
      const next = { ...seenRef.current }
      let changed = false
      for (const [id, stamp] of Object.entries(next)) {
        if (now - stamp >= minutes * 60_000) {
          delete next[id]
          changed = true
        }
      }
      if (changed) {
        seenRef.current = next
        writeSession(next)
      }
      void load()
    }, minutes * 60_000)
    return () => {
      if (reminderRef.current !== null) {
        window.clearInterval(reminderRef.current)
        reminderRef.current = null
      }
    }
  }, [isAuthenticated, settings, load])

  const current = useMemo(() => {
    const now = Date.now()
    const eligible = queue.filter(item => {
      if (item.is_resolved) return false
      const stamp = seenRef.current[String(item.id)]
      return stamp === undefined || now - stamp >= 24 * 60 * 60_000
    })
    return eligible[0] ?? null
  }, [queue])

  const queueRemaining = useMemo(() => queue.filter(item => !item.is_resolved).length, [queue])

  // Record that the popup was surfaced this session (read, never resolved).
  useEffect(() => {
    if (!current || seenRef.current[String(current.id)]) return
    seenRef.current = { ...seenRef.current, [String(current.id)]: Date.now() }
    writeSession(seenRef.current)
    void apiFetch(`/notifications/global/${current.id}/read`, { method: 'POST' }).catch(() => undefined)
  }, [current])

  const dismissCurrent = useCallback(() => {
    setQueue(rows => rows.filter(item => item.id !== current?.id))
    void load()
  }, [current?.id, load])

  const showFeedback = useCallback((payload: FeedbackPayload) => setFeedback(payload), [])
  const clearFeedback = useCallback(() => setFeedback(null), [])

  const updateSettings = useCallback(async (minutes: number) => {
    setBusy(true)
    try {
      const updated = await apiFetch<NotificationSettings>(
        '/notifications/global/settings/notification-settings',
        { method: 'PUT', body: JSON.stringify({ overdue_popup_reminder_minutes: minutes }) },
      )
      setSettings(updated)
    } finally {
      setBusy(false)
    }
  }, [])

  const value = useMemo<PopupContextValue>(() => ({
    current,
    queueRemaining,
    feedback,
    busy,
    settings,
    showFeedback,
    clearFeedback,
    dismissCurrent,
    refresh: () => void load(),
    updateSettings,
  }), [current, queueRemaining, feedback, busy, settings, showFeedback, clearFeedback, dismissCurrent, load, updateSettings])

  return <PopupContext.Provider value={value}>{children}</PopupContext.Provider>
}

export function useNotificationPopup(): PopupContextValue {
  const context = useContext(PopupContext)
  if (!context) throw new Error('useNotificationPopup must be used inside NotificationPopupProvider')
  return context
}