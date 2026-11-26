/**
 * NotificationPopupHost - the single global mount for the centre popup.
 *
 * Rendered once by the app shell so a notification reaches the user on any page.
 * It renders AT MOST ONE modal at a time and performs no business action itself.
 */
import { useNavigate } from 'react-router-dom'
import { NotificationActionModal } from './NotificationActionModal'
import { useNotificationPopup } from './NotificationPopupProvider'
import { isSafeInternalPath } from './notificationTypes'

export function NotificationPopupHost() {
  const { current, feedback, queueRemaining, dismissCurrent, clearFeedback } = useNotificationPopup()
  const navigate = useNavigate()

  if (!current && !feedback) return null

  // TYPE A feedback is presentation only: closing it clears the popup, nothing else.
  const handleClose = () => {
    clearFeedback()
    if (current) dismissCurrent()
  }

  return (
    <NotificationActionModal
      notification={current}
      feedback={feedback}
      queueRemaining={queueRemaining}
      onClose={handleClose}
      actions={
        current && isSafeInternalPath(current.target_url)
          ? [
              {
                id: 'view',
                label: 'View Details',
                variant: 'primary',
                onSelect: notification => {
                  const url = notification?.target_url
                  handleClose()
                  if (isSafeInternalPath(url)) navigate(url)
                },
              },
              { id: 'later', label: 'Later', variant: 'default', onSelect: handleClose },
            ]
          : undefined
      }
    />
  )
}