import { BDProjectManagementPage } from '../operations/pages/BDProjectManagementPage'
import { NotificationPopupHost } from '../notifications/NotificationPopupHost'
import { NotificationPopupProvider } from '../notifications/NotificationPopupProvider'

/**
 * The employee workspace does not use the standard Layout shell. The manager
 * project page expects this notification context, so provide it locally.
 * Keep the existing manager page and employee-specific API routing unchanged.
 */
export function BDEmployeeProjectManagement() {
  return (
    <NotificationPopupProvider>
      <BDProjectManagementPage employeeMode />
      <NotificationPopupHost />
    </NotificationPopupProvider>
  )
}
