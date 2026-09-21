import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { ProtectedRoute } from './components/ProtectedRoute'
import { StrictProtectedRoute } from './components/StrictProtectedRoute'
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
import { RentalAssetReturnsPage } from './pages/RentalAssetReturnsPage'
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
import { ExpenseClaimCreatePage } from './features/finance/pages/ExpenseClaimCreatePage'
import { ExpenseClaimsPage } from './features/finance/pages/ExpenseClaimsPage'
import { ExpenseClaimDetailPage } from './features/finance/pages/ExpenseClaimDetailPage'
import { AdvanceSettlementPage } from './features/finance/pages/AdvanceSettlementPage'
import { FinanceDashboardPage } from './features/finance/pages/FinanceDashboardPage'
import { FinanceClaimsPage } from './features/finance/pages/FinanceClaimsPage'
import { FinanceReportsPage } from './features/finance/pages/FinanceReportsPage'
import { ClientManagementPage } from './features/finance/pages/ClientManagementPage'
import { TravelKmClaimsPage } from './features/travel_km/pages/TravelKmClaimsPage'
import { TravelKmCreatePage } from './features/travel_km/pages/TravelKmCreatePage'
import { TravelKmDetailPage } from './features/travel_km/pages/TravelKmDetailPage'
import { TravelKmStaffDashboardPage } from './features/travel_km/pages/TravelKmStaffDashboardPage'
import { BDDashboardPage } from './features/operations/pages/BDDashboardPage'
import { BDClientManagementPage } from './features/operations/pages/BDClientManagementPage'
import { BDProjectManagementPage } from './features/operations/pages/BDProjectManagementPage'
import { NotificationsPage } from './features/operations/pages/NotificationsPage'
import { OrthoDashboardPage } from './features/operations/pages/OrthoDashboardPage'
import { ProjectWorkstreamsPage } from './features/operations/pages/ProjectWorkstreamsPage'
import { SampleRequestsPage } from './features/operations/pages/SampleRequestsPage'
import { ProjectHandoversPage } from './features/operations/pages/ProjectHandoversPage'
import { ProjectMonitoringPage } from './features/operations/pages/ProjectMonitoringPage'
import { ProjectCompletionPage } from './features/operations/pages/ProjectCompletionPage'
import { TechnicalTeamDirectoryPage } from './features/operations/pages/TechnicalTeamDirectoryPage'
import { ReportingDashboardPage } from './features/operations/pages/ReportingDashboardPage'
import { ProductionReadinessPage } from './features/operations/pages/ProductionReadinessPage'
import { ClientFeedbackPage } from './features/operations/pages/ClientFeedbackPage'
import { BDClientFeedbackPage } from './features/operations/pages/BDClientFeedbackPage'
import { FinanceBillingPage } from './features/finance/pages/FinanceBillingPage'
import { ManagementProject360Page } from './features/operations/pages/ManagementProject360Page'
import { FinanceClientRegisterPage } from './features/finance/pages/FinanceClientRegisterPage'
import { FinanceProjectRegisterPage } from './features/finance/pages/FinanceProjectRegisterPage'

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
      <Route path="/client-feedback/:token" element={<ClientFeedbackPage />} />
      <Route path="/travel-km" element={<ProtectedRoute roles={['employee']}><WithLayout><TravelKmClaimsPage /></WithLayout></ProtectedRoute>} />
      <Route path="/travel-km/new" element={<ProtectedRoute roles={['employee']}><WithLayout><TravelKmCreatePage /></WithLayout></ProtectedRoute>} />
      <Route path="/travel-km/:id" element={<ProtectedRoute roles={['employee', 'admin', 'hr', 'finance', 'management', 'software_team']}><WithLayout><TravelKmDetailPage /></WithLayout></ProtectedRoute>} />
      <Route path="/admin/travel-km" element={<ProtectedRoute roles={['admin']}><WithLayout><TravelKmStaffDashboardPage /></WithLayout></ProtectedRoute>} />
      <Route path="/hr/travel-km" element={<ProtectedRoute roles={['hr']}><WithLayout><TravelKmStaffDashboardPage /></WithLayout></ProtectedRoute>} />
      <Route path="/finance/travel-km" element={<ProtectedRoute roles={['finance']}><WithLayout><TravelKmStaffDashboardPage /></WithLayout></ProtectedRoute>} />
      <Route path="/management/travel-km" element={<ProtectedRoute roles={['management', 'admin']}><WithLayout><TravelKmStaffDashboardPage /></WithLayout></ProtectedRoute>} />
      <Route path="/support" element={<ProtectedRoute roles={['employee']}><WithLayout><EmployeeSupportDashboard /></WithLayout></ProtectedRoute>} />
      <Route path="/support/new" element={<ProtectedRoute roles={['employee']}><WithLayout><TicketCreatePage /></WithLayout></ProtectedRoute>} />
      <Route path="/expenses" element={<ProtectedRoute roles={['employee']}><WithLayout><ExpenseClaimsPage /></WithLayout></ProtectedRoute>} />
      <Route path="/expenses/new" element={<ProtectedRoute roles={['employee']}><WithLayout><ExpenseClaimCreatePage /></WithLayout></ProtectedRoute>} />
      <Route path="/expenses/:id/edit" element={<ProtectedRoute roles={['employee']}><WithLayout><ExpenseClaimCreatePage /></WithLayout></ProtectedRoute>} />
      <Route path="/expenses/:id/settle" element={<ProtectedRoute roles={['employee']}><WithLayout><AdvanceSettlementPage /></WithLayout></ProtectedRoute>} />
      <Route path="/expenses/:id" element={<ProtectedRoute roles={['employee']}><WithLayout><ExpenseClaimDetailPage /></WithLayout></ProtectedRoute>} />
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
      <Route path="/it/rental-returns" element={<ProtectedRoute roles={['it', 'management', 'admin']}><WithLayout><RentalAssetReturnsPage /></WithLayout></ProtectedRoute>} />
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
      <Route path="/bd" element={<StrictProtectedRoute roles={['bd', 'management', 'admin']}><WithLayout><BDDashboardPage /></WithLayout></StrictProtectedRoute>} />
      <Route path="/bd/clients" element={<StrictProtectedRoute roles={['bd', 'management', 'admin']}><WithLayout><BDClientManagementPage /></WithLayout></StrictProtectedRoute>} />
      <Route path="/bd/projects" element={<StrictProtectedRoute roles={['bd', 'management', 'admin']}><WithLayout><BDProjectManagementPage /></WithLayout></StrictProtectedRoute>} />
      <Route path="/bd/feedback" element={<StrictProtectedRoute roles={['bd', 'management', 'admin']}><WithLayout><BDClientFeedbackPage /></WithLayout></StrictProtectedRoute>} />
      <Route path="/notifications" element={<ProtectedRoute roles={['employee', 'it', 'drone', 'finance', 'hr', 'bd', 'ortho', 'lidar', 'civil', 'laser_scanning', 'bim', 'mobile_mapping', 'management', 'admin', 'software_team']}><WithLayout><NotificationsPage /></WithLayout></ProtectedRoute>} />
      <Route path="/ortho" element={<StrictProtectedRoute roles={['ortho', 'employee', 'management', 'admin']}><WithLayout><OrthoDashboardPage /></WithLayout></StrictProtectedRoute>} />
      <Route path="/ortho/project-360/:projectId" element={<StrictProtectedRoute roles={['ortho', 'management', 'admin']}><WithLayout><ManagementProject360Page /></WithLayout></StrictProtectedRoute>} />
      <Route path="/project-workstreams" element={<StrictProtectedRoute roles={['lidar', 'civil', 'laser_scanning', 'bim', 'mobile_mapping', 'management', 'admin']}><WithLayout><ProjectWorkstreamsPage /></WithLayout></StrictProtectedRoute>} />
      <Route path="/sample-requests" element={<StrictProtectedRoute roles={['lidar', 'civil', 'laser_scanning', 'bim', 'mobile_mapping', 'management', 'admin']}><WithLayout><SampleRequestsPage /></WithLayout></StrictProtectedRoute>} />
      <Route path="/project-handovers" element={<StrictProtectedRoute roles={['lidar', 'civil', 'laser_scanning', 'bim', 'mobile_mapping', 'management', 'admin']}><WithLayout><ProjectHandoversPage /></WithLayout></StrictProtectedRoute>} />
      <Route path="/project-monitoring" element={<StrictProtectedRoute roles={['lidar', 'civil', 'laser_scanning', 'bim', 'mobile_mapping', 'management', 'admin']}><WithLayout><ProjectMonitoringPage /></WithLayout></StrictProtectedRoute>} />
      <Route path="/project-completion" element={<StrictProtectedRoute roles={['lidar', 'civil', 'laser_scanning', 'bim', 'mobile_mapping', 'management', 'admin']}><WithLayout><ProjectCompletionPage /></WithLayout></StrictProtectedRoute>} />
      <Route path="/technical-team-directory" element={<StrictProtectedRoute roles={['admin', 'management', 'lidar', 'civil', 'laser_scanning', 'bim', 'mobile_mapping']}><WithLayout><TechnicalTeamDirectoryPage /></WithLayout></StrictProtectedRoute>} />
      <Route path="/reporting" element={<StrictProtectedRoute roles={['admin', 'management', 'lidar', 'civil', 'laser_scanning', 'bim', 'mobile_mapping']}><WithLayout><ReportingDashboardPage /></WithLayout></StrictProtectedRoute>} />
      <Route path="/production-readiness" element={<StrictProtectedRoute roles={['admin', 'management', 'software_team']}><WithLayout><ProductionReadinessPage /></WithLayout></StrictProtectedRoute>} />
      <Route path="/finance" element={<ProtectedRoute roles={['finance', 'admin', 'management']}><WithLayout><FinanceDashboardPage /></WithLayout></ProtectedRoute>} />
      <Route path="/finance/claims" element={<ProtectedRoute roles={['finance', 'admin', 'management']}><WithLayout><FinanceClaimsPage /></WithLayout></ProtectedRoute>} />
      <Route path="/finance/reports" element={<ProtectedRoute roles={['finance', 'admin', 'management']}><WithLayout><FinanceReportsPage /></WithLayout></ProtectedRoute>} />
      <Route path="/finance/clients" element={<ProtectedRoute roles={['finance', 'admin', 'management']}><WithLayout><FinanceClientRegisterPage /></WithLayout></ProtectedRoute>} />
      <Route path="/finance/projects" element={<ProtectedRoute roles={['finance', 'admin', 'management']}><WithLayout><FinanceProjectRegisterPage /></WithLayout></ProtectedRoute>} />
      <Route path="/finance/billing" element={<ProtectedRoute roles={['finance', 'admin', 'management']}><WithLayout><FinanceBillingPage /></WithLayout></ProtectedRoute>} />
      <Route path="/admin/client-master" element={<ProtectedRoute roles={['admin']}><WithLayout><ClientManagementPage /></WithLayout></ProtectedRoute>} />
      <Route path="/finance/claims/:id" element={<ProtectedRoute roles={['finance', 'admin', 'management']}><WithLayout><ExpenseClaimDetailPage /></WithLayout></ProtectedRoute>} />
      <Route path="/management" element={<ProtectedRoute roles={['management', 'admin']}><WithLayout><ManagementDashboard /></WithLayout></ProtectedRoute>} />
      <Route path="/management/approvals" element={<ProtectedRoute roles={['management']}><WithLayout><ManagementApprovalCenter /></WithLayout></ProtectedRoute>} />
      <Route path="/management/project-360" element={<ProtectedRoute roles={['management', 'admin']}><WithLayout><ManagementProject360Page /></WithLayout></ProtectedRoute>} />
      <Route path="/management/project-360/:projectId" element={<ProtectedRoute roles={['management', 'admin']}><WithLayout><ManagementProject360Page /></WithLayout></ProtectedRoute>} />
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
