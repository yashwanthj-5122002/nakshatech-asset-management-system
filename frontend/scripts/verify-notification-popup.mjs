import fs from 'node:fs'
import path from 'node:path'

const root = process.cwd()
const read = (relative) => fs.readFileSync(path.join(root, relative), 'utf8')
const exists = (relative) => fs.existsSync(path.join(root, relative))

function assert(condition, message) {
  if (!condition) throw new Error(`Assertion failed: ${message}`)
}

// ---------------------------------------------------------------------------
// 1. Global popup architecture exists and is mounted in the app shell
// ---------------------------------------------------------------------------
for (const file of [
  'src/features/notifications/NotificationActionModal.tsx',
  'src/features/notifications/NotificationPopupProvider.tsx',
  'src/features/notifications/NotificationPopupHost.tsx',
  'src/features/notifications/NotificationReminderSettings.tsx',
  'src/features/notifications/notificationTypes.ts',
  'src/features/notifications/notification-popup.css',
]) {
  assert(exists(file), `notification popup module must exist: ${file}`)
}

const layout = read('src/components/Layout.tsx')
assert(layout.includes('NotificationPopupProvider'), 'the app shell must mount the notification provider')
assert(layout.includes('NotificationPopupHost'), 'the app shell must render the global popup host')
assert(layout.includes('GlobalNotificationBell'), 'the existing notification bell must remain in the shell')

const provider = read('src/features/notifications/NotificationPopupProvider.tsx')
const modal = read('src/features/notifications/NotificationActionModal.tsx')
const host = read('src/features/notifications/NotificationPopupHost.tsx')
const types = read('src/features/notifications/notificationTypes.ts')
const popupCss = read('src/features/notifications/notification-popup.css')
const bell = read('src/components/GlobalNotificationBell.tsx')
const settings = read('src/features/notifications/NotificationReminderSettings.tsx')
const managementDashboard = read('src/pages/ManagementDashboard.tsx')

function cssRule(source, selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return source.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`, 's'))?.[1] ?? ''
}

// ---------------------------------------------------------------------------
// 2. Popup theme matches the ERP
// ---------------------------------------------------------------------------
for (const token of ['--navy', '--cyan', '--line']) {
  assert(popupCss.includes(token), `popup CSS must use the ERP design token ${token}`)
}
for (const cls of [
  'nk-notification-popup-backdrop',
  'nk-notification-popup',
  'nk-notification-popup-header',
  'nk-notification-popup-body',
  'nk-notification-popup-footer',
  'severity-warning',
  'severity-danger',
  'severity-success',
]) {
  assert(popupCss.includes(cls), `popup theme class must exist: ${cls}`)
}
assert(modal.includes("import './notification-popup.css'"), 'NotificationActionModal must load its popup stylesheet')
const backdropRule = cssRule(popupCss, '.nk-notification-popup-backdrop')
const cardRule = cssRule(popupCss, '.nk-notification-popup')
const bodyRule = cssRule(popupCss, '.nk-notification-popup-body')
assert(backdropRule, 'the unscoped popup backdrop selector must exist for the global sibling host')
assert(/position\s*:\s*fixed/.test(backdropRule), 'the popup backdrop must use fixed positioning')
assert(/inset\s*:\s*0/.test(backdropRule), 'the popup backdrop must cover the viewport with inset: 0')
assert(/width\s*:\s*100vw/.test(backdropRule) && /height\s*:\s*100vh/.test(backdropRule), 'the popup backdrop must explicitly cover the full viewport')
assert(/display\s*:\s*(flex|grid)/.test(backdropRule), 'the popup backdrop must establish a centering layout')
assert(
  (/align-items\s*:\s*center/.test(backdropRule) && /justify-content\s*:\s*center/.test(backdropRule)) || /place-items\s*:\s*center/.test(backdropRule),
  'the popup backdrop must center the modal card',
)
assert(/z-index\s*:\s*(1[0-9]{3}|[2-9][0-9]{3,})/.test(backdropRule), 'the popup backdrop must sit above the ERP shell and page overlays')
assert(cardRule, 'the unscoped popup card selector must exist')
assert(/max-height\s*:/.test(cardRule), 'the popup card must cap its height within the viewport')
assert(/overflow\s*:\s*hidden/.test(cardRule), 'the popup card must contain long content without expanding the page')
assert(/overflow-y\s*:\s*auto/.test(bodyRule), 'a long popup body must scroll while header/actions stay usable')
// ---------------------------------------------------------------------------
// 3. Accessibility
// ---------------------------------------------------------------------------
assert(modal.includes('role="dialog"'), 'the popup must be a dialog')
assert(modal.includes('aria-modal="true"'), 'the popup must be an aria-modal dialog')
assert(modal.includes('aria-labelledby'), 'the popup must be labelled')
assert(modal.includes("event.key !== 'Tab'"), 'the popup must trap keyboard focus')
assert(modal.includes("event.key === 'Escape'"), 'Escape must close the popup')
assert(modal.includes('previouslyFocused'), 'focus must return to the triggering context')
assert(modal.includes('document.body.style.overflow'), 'the background must not scroll while a modal is open')

// ---------------------------------------------------------------------------
// 4. CORE RULE: closing the popup never resolves the notification
// ---------------------------------------------------------------------------
assert(modal.includes('Closing this popup keeps the item pending'), 'the popup must state that closing does not resolve')
assert(!/\/resolve|\/complete|\/approve|\/reject/.test(host), 'the popup host must never call a resolve/approve/reject endpoint')
assert(
  !/window\.confirm\(|\bconfirm\(|window\.alert\(|\balert\(/.test(modal + host + provider),
  'the popup experience must not use browser alert()/confirm()',
)

// ---------------------------------------------------------------------------
// 5. Read vs Resolved are independent
// ---------------------------------------------------------------------------
assert(types.includes('is_resolved'), 'the popup type must expose the resolved flag')
assert(provider.includes('/read'), 'surfacing a popup may mark the item read')
assert(!/resolved_at\s*:/.test(provider), 'the client must never mark a notification resolved')
assert(bell.includes('notificationStatus'), 'the bell must distinguish notification status')
for (const label of ['Pending Action', 'Overdue', 'Resolved', 'Information']) {
  assert(bell.includes(label), `the bell must show the "${label}" status`)
}

// ---------------------------------------------------------------------------
// 6. Popup queue + session dedupe
// ---------------------------------------------------------------------------
assert(provider.includes('/popup-queue'), 'the provider must consume the popup queue endpoint')
assert(provider.includes('SESSION_KEY'), 'session popup tracking must exist')
assert(provider.includes('writeSession'), 'session popup tracking must persist')
assert(host.includes('queueRemaining'), 'the popup must show how many notifications remain queued')
assert(provider.includes('eligible[0]'), 'only one popup may be shown at a time from the queue')

// ---------------------------------------------------------------------------
// 7. Overdue reminder uses ONE timer and the configured interval
// ---------------------------------------------------------------------------
assert(provider.includes('setInterval'), 'the reminder scheduler must use a timer')
assert(provider.includes('overdue_popup_reminder_minutes'), 'the scheduler must read the configured interval')
assert(provider.includes('clearInterval'), 'the reminder timer must be cleaned up')
assert((provider.match(/setInterval\(/g) || []).length <= 2, 'the shell must not create one timer per notification')
assert(provider.includes('if (!isAuthenticated) return'), 'the reminder timer must stop when signed out')
assert(provider.includes('writeSession({})'), 'logout must clear session popup tracking')

// ---------------------------------------------------------------------------
// 8. Management setting is capability driven, never display-name driven
// ---------------------------------------------------------------------------
assert(settings.includes('can_manage'), 'the settings block must be gated on the backend capability flag')
assert(settings.includes('overdue_popup_reminder_minutes'), 'the settings block must edit the reminder interval')
assert(!/full_name|display_name/.test(settings), 'authorization must never match a display name')
assert(managementDashboard.includes('NotificationReminderSettings'), 'Management must host the reminder setting')

console.log('NOTIFICATION POPUP / CENTRE MODAL / MANAGEMENT REMINDER VERIFICATION PASSED')
