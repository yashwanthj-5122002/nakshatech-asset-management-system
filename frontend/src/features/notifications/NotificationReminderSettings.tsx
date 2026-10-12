/**
 * NotificationReminderSettings - Management-only reminder interval control.
 *
 * Visibility is driven by the BACKEND capability flag (`can_manage`), not by a
 * role or display-name check in the UI, and the backend re-checks the capability
 * on every write, so hiding this block is never the only protection.
 */
import { BellRing, Check, Save } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNotificationPopup } from './NotificationPopupProvider'

export function NotificationReminderSettings() {
  const { settings, updateSettings, busy, showFeedback } = useNotificationPopup()
  const [minutes, setMinutes] = useState<number>(10)

  useEffect(() => {
    if (settings) setMinutes(settings.overdue_popup_reminder_minutes)
  }, [settings])

  // Only the authorized Management accounts ever see this block.
  if (!settings?.can_manage) return null

  const options = settings.suggested_minutes?.length ? settings.suggested_minutes : [5, 10, 15, 30, 60]

  async function save() {
    try {
      await updateSettings(minutes)
      showFeedback({
        kind: 'success',
        eyebrow: 'Settings Saved',
        title: 'REMINDER INTERVAL UPDATED',
        message: `Overdue payment popups will now remind every ${minutes} minute${minutes === 1 ? '' : 's'}.`,
        facts: [
          { label: 'Previous', value: `${settings?.overdue_popup_reminder_minutes ?? '-'} min` },
          { label: 'New', value: `${minutes} min` },
        ],
      })
    } catch (error) {
      showFeedback({
        kind: 'error',
        eyebrow: 'Unable To Complete Action',
        title: 'SETTINGS NOT SAVED',
        message: error instanceof Error ? error.message : 'The reminder interval could not be updated.',
      })
    }
  }

  return (
    <section className="nk-notification-settings" aria-label="Notification reminder settings">
      <div>
        <h4><BellRing size={14} aria-hidden="true" /> Overdue Popup Reminder Interval</h4>
        <p>
          How often an unresolved overdue payment or advance popup is resurfaced.
          Reminders reuse the existing notification - they never create duplicates.
        </p>
      </div>
      <div className="nk-notification-settings-row">
        <label htmlFor="nk-reminder-interval">Remind every</label>
        <select
          id="nk-reminder-interval"
          value={minutes}
          disabled={busy}
          onChange={event => setMinutes(Number(event.target.value))}
        >
          {options.map(option => (
            <option key={option} value={option}>{option} minutes</option>
          ))}
        </select>
        <button type="button" onClick={() => void save()} disabled={busy}>
          {busy ? <Check size={14} aria-hidden="true" /> : <Save size={14} aria-hidden="true" />}
          Save interval
        </button>
      </div>
    </section>
  )
}