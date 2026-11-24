import { BDClientManagementPage } from '../operations/pages/BDClientManagementPage'

/** Manager-identical UI. All data/mutations use employee-scoped APIs. */
export function BDEmployeeClientManagement(){
  return <BDClientManagementPage employeeMode />
}
