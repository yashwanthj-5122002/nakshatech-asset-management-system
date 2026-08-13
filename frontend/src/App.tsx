import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { ProtectedRoute } from './components/ProtectedRoute'
import { useAuth } from './context/AuthContext'
import { AdminDashboard } from './pages/AdminDashboard'
import { AssetsPage } from './pages/AssetsPage'
import { AssetFormPage } from './pages/AssetFormPage'
import { DroneDashboardPage } from './features/drone/pages/DroneDashboardPage'
import { DroneAssetsPage } from './features/drone/pages/DroneAssetsPage'
import { DroneAssetFormPage } from './features/drone/pages/DroneAssetFormPage'
import { DroneAssetDetailPage } from './features/drone/pages/DroneAssetDetailPage'
import { DroneProjectsPage } from './features/drone/pages/DroneProjectsPage'
import { DroneKitsPage } from './features/drone/pages/DroneKitsPage'
import { DroneImportPage } from './features/drone/pages/DroneImportPage'
import { DroneOperationsPage } from './features/drone/pages/DroneOperationsPage'
import { DroneWorkRecordsPage } from './features/drone/pages/DroneWorkRecordsPage'
import { DroneMovementsPage } from './features/drone/pages/DroneMovementsPage'
import { DroneProjectDetailPage } from './features/drone/pages/DroneProjectDetailPage'
import { FutureFeaturesPage } from './pages/FutureFeaturesPage'
import { ITDashboard } from './pages/ITDashboard'
import { LoginPage } from './pages/LoginPage'
import { ManagementDashboard } from './pages/ManagementDashboard'
import { ManagementApprovalCenter } from './pages/ManagementApprovalCenter'
import { ManagementITWorkReadOnlyPage } from './pages/ManagementITWorkReadOnlyPage'
import { ReplacementsPage } from './pages/ReplacementsPage'
import { ReportsPage } from './pages/ReportsPage'
import { NakshaCopilotPage } from './features/naksha_copilot/NakshaCopilotPage'
import { DataQualityCentrePage } from './features/data_quality/DataQualityCentrePage'
import { WelcomePage } from './pages/WelcomePage'
import { WorkFormPage } from './pages/WorkFormPage'
import { RecentChangesPage } from './pages/RecentChangesPage'
import { HandoverReturnPage } from './pages/HandoverReturnPage'
import { PurchaseProcurementPage } from './pages/PurchaseProcurementPage'
import { PurchaseRequestsPage } from './pages/PurchaseRequestsPage'
import { BackupCenterPage } from './pages/BackupCenterPage'
import { roleHomePath } from './lib/roles'
import { RegisterPage } from './features/employee_portal/pages/RegisterPage'
import { ForgotPasswordPage } from './features/employee_portal/pages/ForgotPasswordPage'
import { AuthenticatorPage } from './features/employee_portal/pages/AuthenticatorPage'
import { BranchSelectionPage } from './features/employee_portal/pages/BranchSelectionPage'
import { EmployeeSupportDashboard } from './features/employee_portal/pages/EmployeeSupportDashboard'
import { TicketCreatePage } from './features/employee_portal/pages/TicketCreatePage'
import { TicketListPage } from './features/employee_portal/pages/TicketListPage'
import { TicketDetailPage } from './features/employee_portal/pages/TicketDetailPage'
import { SoftwareSecurityPage } from './features/employee_portal/pages/SoftwareSecurityPage'
import { AgentMonitorPage } from './features/agent_monitor/AgentMonitorPage'

function WithLayout({ children }: { children: ReactNode }) {
  return <Layout>{children}</Layout>
}

function ITWorkRoute() {
  const { user } = useAuth()
  return user?.role === 'management' ? <ManagementITWorkReadOnlyPage /> : <WorkFormPage />
}

export default function App() {
  const { user, needsBranchSelection } = useAuth()
  return (
    <Routes>
      <Route path="/" element={user ? <Navigate to={needsBranchSelection ? '/select-branch' : roleHomePath(user.role)} replace /> : <WelcomePage />} />
      <Route path="/login" element={user ? <Navigate to={needsBranchSelection ? '/select-branch' : roleHomePath(user.role)} replace /> : <LoginPage />} />
      <Route path="/employee-login" element={user ? <Navigate to={needsBranchSelection ? '/select-branch' : roleHomePath(user.role)} replace /> : <LoginPage mode="employee" />} />
      <Route path="/register" element={user ? <Navigate to={needsBranchSelection ? '/select-branch' : roleHomePath(user.role)} replace /> : <RegisterPage />} />
      <Route path="/forgot-password" element={user ? <Navigate to={needsBranchSelection ? '/select-branch' : roleHomePath(user.role)} replace /> : <ForgotPasswordPage />} />
      <Route path="/verify-authenticator" element={<AuthenticatorPage />} />
      <Route path="/select-branch" element={<BranchSelectionPage />} />
      <Route path="/support" element={<ProtectedRoute roles={['employee']}><WithLayout><EmployeeSupportDashboard /></WithLayout></ProtectedRoute>} />
      <Route path="/support/new" element={<ProtectedRoute roles={['employee']}><WithLayout><TicketCreatePage /></WithLayout></ProtectedRoute>} />
      <Route path="/tickets" element={<ProtectedRoute roles={['employee', 'it', 'drone', 'management', 'software_team']}><WithLayout><TicketListPage /></WithLayout></ProtectedRoute>} />
      <Route path="/tickets/:id" element={<ProtectedRoute roles={['employee', 'it', 'drone', 'management', 'software_team']}><WithLayout><TicketDetailPage /></WithLayout></ProtectedRoute>} />
      <Route path="/software-team/security" element={<ProtectedRoute roles={['software_team']}><WithLayout><SoftwareSecurityPage /></WithLayout></ProtectedRoute>} />
      <Route path="/software-team/agents" element={<ProtectedRoute roles={['software_team']}><WithLayout><AgentMonitorPage /></WithLayout></ProtectedRoute>} />
      <Route path="/management/activity" element={<ProtectedRoute roles={['management']}><WithLayout><SoftwareSecurityPage /></WithLayout></ProtectedRoute>} />
      <Route path="/it" element={<ProtectedRoute roles={['it', 'management', 'admin']}><WithLayout><ITDashboard /></WithLayout></ProtectedRoute>} />
      <Route path="/assets" element={<ProtectedRoute roles={['it', 'management', 'admin']}><WithLayout><AssetsPage /></WithLayout></ProtectedRoute>} />
      <Route path="/assets/new" element={<ProtectedRoute roles={['it', 'admin']}><WithLayout><AssetFormPage /></WithLayout></ProtectedRoute>} />
      <Route path="/assets/:id/edit" element={<ProtectedRoute roles={['it', 'admin']}><WithLayout><AssetFormPage /></WithLayout></ProtectedRoute>} />
      <Route path="/replacements" element={<ProtectedRoute roles={['it', 'management', 'admin']}><WithLayout><ReplacementsPage /></WithLayout></ProtectedRoute>} />
      <Route path="/it/handover-return" element={<ProtectedRoute roles={['it', 'management', 'admin']}><WithLayout><HandoverReturnPage /></WithLayout></ProtectedRoute>} />
      <Route path="/it/purchase-requests" element={<ProtectedRoute roles={['it', 'management', 'admin']}><WithLayout><PurchaseRequestsPage /></WithLayout></ProtectedRoute>} />
      <Route path="/it/purchases" element={<ProtectedRoute roles={['it', 'management', 'admin']}><WithLayout><PurchaseProcurementPage /></WithLayout></ProtectedRoute>} />
      <Route path="/it/recent-changes" element={<ProtectedRoute roles={['it', 'management', 'admin']}><WithLayout><RecentChangesPage /></WithLayout></ProtectedRoute>} />
      <Route path="/drone" element={<ProtectedRoute roles={['drone', 'management', 'admin']}><WithLayout><DroneDashboardPage /></WithLayout></ProtectedRoute>} />
      <Route path="/drone/assets" element={<ProtectedRoute roles={['drone', 'management', 'admin']}><WithLayout><DroneAssetsPage /></WithLayout></ProtectedRoute>} />
      <Route path="/drone/assets/new" element={<ProtectedRoute roles={['drone', 'admin']}><WithLayout><DroneAssetFormPage /></WithLayout></ProtectedRoute>} />
      <Route path="/drone/assets/:id" element={<ProtectedRoute roles={['drone', 'management', 'admin']}><WithLayout><DroneAssetDetailPage /></WithLayout></ProtectedRoute>} />
      <Route path="/drone/assets/:id/edit" element={<ProtectedRoute roles={['drone', 'admin']}><WithLayout><DroneAssetFormPage /></WithLayout></ProtectedRoute>} />
      <Route path="/drone/projects" element={<ProtectedRoute roles={['drone', 'management', 'admin']}><WithLayout><DroneProjectsPage /></WithLayout></ProtectedRoute>} />
      <Route path="/drone/projects/:id" element={<ProtectedRoute roles={['drone', 'management', 'admin']}><WithLayout><DroneProjectDetailPage /></WithLayout></ProtectedRoute>} />
      <Route path="/drone/operations" element={<ProtectedRoute roles={['drone', 'management', 'admin']}><WithLayout><DroneOperationsPage /></WithLayout></ProtectedRoute>} />
      <Route path="/drone/work-records" element={<ProtectedRoute roles={['drone', 'management', 'admin']}><WithLayout><DroneWorkRecordsPage /></WithLayout></ProtectedRoute>} />
      <Route path="/drone/movements" element={<ProtectedRoute roles={['drone', 'management', 'admin']}><WithLayout><DroneMovementsPage /></WithLayout></ProtectedRoute>} />
      <Route path="/drone/kits" element={<ProtectedRoute roles={['drone', 'management', 'admin']}><WithLayout><DroneKitsPage /></WithLayout></ProtectedRoute>} />
      <Route path="/drone/import" element={<ProtectedRoute roles={['drone', 'management', 'admin']}><WithLayout><DroneImportPage /></WithLayout></ProtectedRoute>} />
      <Route path="/management" element={<ProtectedRoute roles={['management', 'admin']}><WithLayout><ManagementDashboard /></WithLayout></ProtectedRoute>} />
      <Route path="/management/approvals" element={<ProtectedRoute roles={['management']}><WithLayout><ManagementApprovalCenter /></WithLayout></ProtectedRoute>} />
      <Route path="/software-team" element={<ProtectedRoute roles={['software_team']}><WithLayout><AdminDashboard /></WithLayout></ProtectedRoute>} />
      <Route path="/admin" element={<ProtectedRoute roles={['admin']}><WithLayout><AdminDashboard /></WithLayout></ProtectedRoute>} />
      <Route path="/work" element={<ProtectedRoute roles={['it', 'drone', 'management', 'admin']}><WithLayout><ITWorkRoute /></WithLayout></ProtectedRoute>} />
      <Route path="/reports" element={<ProtectedRoute roles={['it', 'management', 'admin']}><WithLayout><ReportsPage /></WithLayout></ProtectedRoute>} />
      <Route path="/data-quality" element={<ProtectedRoute roles={['it', 'management', 'software_team']}><WithLayout><DataQualityCentrePage /></WithLayout></ProtectedRoute>} />
      <Route path="/naksha-copilot" element={<ProtectedRoute roles={['it', 'management', 'software_team']}><WithLayout><NakshaCopilotPage /></WithLayout></ProtectedRoute>} />
      <Route path="/backups" element={<ProtectedRoute roles={['admin', 'management', 'it', 'drone']}><WithLayout><BackupCenterPage /></WithLayout></ProtectedRoute>} />
      <Route path="/future" element={<ProtectedRoute roles={['admin']}><WithLayout><FutureFeaturesPage /></WithLayout></ProtectedRoute>} />
      <Route path="*" element={<Navigate to={user ? (needsBranchSelection ? '/select-branch' : roleHomePath(user.role)) : '/'} replace />} />
    </Routes>
  )
}
