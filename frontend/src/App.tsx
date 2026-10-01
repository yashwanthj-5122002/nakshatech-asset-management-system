import type { ReactNode } from 'react'
import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { RouteFallback } from './components/RouteFallback'

const AdminDashboard = lazy(() => import('./pages/AdminDashboard').then((m) => ({ default: m.AdminDashboard })))
const UAT2026ControlPage = lazy(() => import('./pages/UAT2026ControlPage').then((m) => ({ default: m.UAT2026ControlPage })))
const AssetsPage = lazy(() => import('./pages/AssetsPage').then((m) => ({ default: m.AssetsPage })))
const AssetFormPage = lazy(() => import('./pages/AssetFormPage').then((m) => ({ default: m.AssetFormPage })))
const DroneDashboardPage = lazy(() => import('./features/drone/pages/DroneDashboardPage').then((m) => ({ default: m.DroneDashboardPage })))
const DroneAssetsPage = lazy(() => import('./features/drone/pages/DroneAssetsPage').then((m) => ({ default: m.DroneAssetsPage })))
const DroneAssetFormPage = lazy(() => import('./features/drone/pages/DroneAssetFormPage').then((m) => ({ default: m.DroneAssetFormPage })))
const DroneAssetDetailPage = lazy(() => import('./features/drone/pages/DroneAssetDetailPage').then((m) => ({ default: m.DroneAssetDetailPage })))
const DroneProjectsPage = lazy(() => import('./features/drone/pages/DroneProjectsPage').then((m) => ({ default: m.DroneProjectsPage })))
const DroneKitsPage = lazy(() => import('./features/drone/pages/DroneKitsPage').then((m) => ({ default: m.DroneKitsPage })))
const DroneImportPage = lazy(() => import('./features/drone/pages/DroneImportPage').then((m) => ({ default: m.DroneImportPage })))
const DroneOperationsPage = lazy(() => import('./features/drone/pages/DroneOperationsPage').then((m) => ({ default: m.DroneOperationsPage })))
const DroneWorkRecordsPage = lazy(() => import('./features/drone/pages/DroneWorkRecordsPage').then((m) => ({ default: m.DroneWorkRecordsPage })))
const DroneMovementsPage = lazy(() => import('./features/drone/pages/DroneMovementsPage').then((m) => ({ default: m.DroneMovementsPage })))
const DroneProjectDetailPage = lazy(() => import('./features/drone/pages/DroneProjectDetailPage').then((m) => ({ default: m.DroneProjectDetailPage })))
const FutureFeaturesPage = lazy(() => import('./pages/FutureFeaturesPage').then((m) => ({ default: m.FutureFeaturesPage })))
const ITDashboard = lazy(() => import('./pages/ITDashboard').then((m) => ({ default: m.ITDashboard })))
const LoginPage = lazy(() => import('./pages/LoginPage').then((m) => ({ default: m.LoginPage })))
const ManagementDashboard = lazy(() => import('./pages/ManagementDashboard').then((m) => ({ default: m.ManagementDashboard })))
const ManagementApprovalCenter = lazy(() => import('./pages/ManagementApprovalCenter').then((m) => ({ default: m.ManagementApprovalCenter })))
const ManagementITWorkReadOnlyPage = lazy(() => import('./pages/ManagementITWorkReadOnlyPage').then((m) => ({ default: m.ManagementITWorkReadOnlyPage })))
const ReplacementsPage = lazy(() => import('./pages/ReplacementsPage').then((m) => ({ default: m.ReplacementsPage })))
const ReportsPage = lazy(() => import('./pages/ReportsPage').then((m) => ({ default: m.ReportsPage })))
const RentalAssetReturnsPage = lazy(() => import('./pages/RentalAssetReturnsPage').then((m) => ({ default: m.RentalAssetReturnsPage })))
const NakshaCopilotPage = lazy(() => import('./features/naksha_copilot/NakshaCopilotPage').then((m) => ({ default: m.NakshaCopilotPage })))
const DataQualityCentrePage = lazy(() => import('./features/data_quality/DataQualityCentrePage').then((m) => ({ default: m.DataQualityCentrePage })))
const WelcomePage = lazy(() => import('./pages/WelcomePage').then((m) => ({ default: m.WelcomePage })))
const ProfilePage = lazy(() => import('./pages/ProfilePage').then((m) => ({ default: m.ProfilePage })))
const WorkFormPage = lazy(() => import('./pages/WorkFormPage').then((m) => ({ default: m.WorkFormPage })))
const RecentChangesPage = lazy(() => import('./pages/RecentChangesPage').then((m) => ({ default: m.RecentChangesPage })))
const HandoverReturnPage = lazy(() => import('./pages/HandoverReturnPage').then((m) => ({ default: m.HandoverReturnPage })))
const PurchaseProcurementPage = lazy(() => import('./pages/PurchaseProcurementPage').then((m) => ({ default: m.PurchaseProcurementPage })))
const PurchaseRequestsPage = lazy(() => import('./pages/PurchaseRequestsPage').then((m) => ({ default: m.PurchaseRequestsPage })))
const BackupCenterPage = lazy(() => import('./pages/BackupCenterPage').then((m) => ({ default: m.BackupCenterPage })))
const RegisterPage = lazy(() => import('./features/employee_portal/pages/RegisterPage').then((m) => ({ default: m.RegisterPage })))
const ForgotPasswordPage = lazy(() => import('./features/employee_portal/pages/ForgotPasswordPage').then((m) => ({ default: m.ForgotPasswordPage })))
const AuthenticatorPage = lazy(() => import('./features/employee_portal/pages/AuthenticatorPage').then((m) => ({ default: m.AuthenticatorPage })))
const BranchSelectionPage = lazy(() => import('./features/employee_portal/pages/BranchSelectionPage').then((m) => ({ default: m.BranchSelectionPage })))
const EmployeeSupportDashboard = lazy(() => import('./features/employee_portal/pages/EmployeeSupportDashboard').then((m) => ({ default: m.EmployeeSupportDashboard })))
const TicketCreatePage = lazy(() => import('./features/employee_portal/pages/TicketCreatePage').then((m) => ({ default: m.TicketCreatePage })))
const TicketListPage = lazy(() => import('./features/employee_portal/pages/TicketListPage').then((m) => ({ default: m.TicketListPage })))
const TicketDetailPage = lazy(() => import('./features/employee_portal/pages/TicketDetailPage').then((m) => ({ default: m.TicketDetailPage })))
const SoftwareSecurityPage = lazy(() => import('./features/employee_portal/pages/SoftwareSecurityPage').then((m) => ({ default: m.SoftwareSecurityPage })))
const EmployeeMasterPage = lazy(() => import('./features/employee_portal/pages/EmployeeMasterPage').then((m) => ({ default: m.EmployeeMasterPage })))
const ManagementEmployeeMasterPage = lazy(() => import('./features/employee_portal/pages/ManagementEmployeeMasterPage').then((m) => ({ default: m.ManagementEmployeeMasterPage })))
const OnboardingPage = lazy(() => import('./features/employee_portal/pages/OnboardingPage').then((m) => ({ default: m.OnboardingPage })))
const AgentMonitorPage = lazy(() => import('./features/agent_monitor/AgentMonitorPage').then((m) => ({ default: m.AgentMonitorPage })))
const ExpenseClaimCreatePage = lazy(() => import('./features/finance/pages/ExpenseClaimCreatePage').then((m) => ({ default: m.ExpenseClaimCreatePage })))
const ExpenseClaimsPage = lazy(() => import('./features/finance/pages/ExpenseClaimsPage').then((m) => ({ default: m.ExpenseClaimsPage })))
const ExpenseClaimDetailPage = lazy(() => import('./features/finance/pages/ExpenseClaimDetailPage').then((m) => ({ default: m.ExpenseClaimDetailPage })))
const AdvanceSettlementPage = lazy(() => import('./features/finance/pages/AdvanceSettlementPage').then((m) => ({ default: m.AdvanceSettlementPage })))
const FinanceDashboardPage = lazy(() => import('./features/finance/pages/FinanceDashboardPage').then((m) => ({ default: m.FinanceDashboardPage })))
const FinanceClaimsPage = lazy(() => import('./features/finance/pages/FinanceClaimsPage').then((m) => ({ default: m.FinanceClaimsPage })))
const FinanceReportsPage = lazy(() => import('./features/finance/pages/FinanceReportsPage').then((m) => ({ default: m.FinanceReportsPage })))
const ClientManagementPage = lazy(() => import('./features/finance/pages/ClientManagementPage').then((m) => ({ default: m.ClientManagementPage })))
const TravelKmClaimsPage = lazy(() => import('./features/travel_km/pages/TravelKmClaimsPage').then((m) => ({ default: m.TravelKmClaimsPage })))
const TravelKmCreatePage = lazy(() => import('./features/travel_km/pages/TravelKmCreatePage').then((m) => ({ default: m.TravelKmCreatePage })))
const TravelKmDetailPage = lazy(() => import('./features/travel_km/pages/TravelKmDetailPage').then((m) => ({ default: m.TravelKmDetailPage })))
const TravelKmStaffDashboardPage = lazy(() => import('./features/travel_km/pages/TravelKmStaffDashboardPage').then((m) => ({ default: m.TravelKmStaffDashboardPage })))
const BDDashboardPage = lazy(() => import('./features/operations/pages/BDDashboardPage').then((m) => ({ default: m.BDDashboardPage })))
const BDClientManagementPage = lazy(() => import('./features/operations/pages/BDClientManagementPage').then((m) => ({ default: m.BDClientManagementPage })))
const BDProjectManagementPage = lazy(() => import('./features/operations/pages/BDProjectManagementPage').then((m) => ({ default: m.BDProjectManagementPage })))
const NotificationsPage = lazy(() => import('./features/operations/pages/NotificationsPage').then((m) => ({ default: m.NotificationsPage })))
const OrthoDashboardPage = lazy(() => import('./features/operations/pages/OrthoDashboardPage').then((m) => ({ default: m.OrthoDashboardPage })))
const ClientFeedbackPage = lazy(() => import('./features/operations/pages/ClientFeedbackPage').then((m) => ({ default: m.ClientFeedbackPage })))
const BDClientFeedbackPage = lazy(() => import('./features/operations/pages/BDClientFeedbackPage').then((m) => ({ default: m.BDClientFeedbackPage })))
const FinanceBillingPage = lazy(() => import('./features/finance/pages/FinanceBillingPage').then((m) => ({ default: m.FinanceBillingPage })))
const SalesRevenuePage = lazy(() => import('./features/finance/pages/SalesRevenuePage').then((m) => ({ default: m.SalesRevenuePage })))
const FinanceCommandCenter = lazy(() => import('./features/finance/pages/FinanceCommandCenter').then((m) => ({ default: m.FinanceCommandCenter })))
const ManagementProject360Page = lazy(() => import('./features/operations/pages/ManagementProject360Page').then((m) => ({ default: m.ManagementProject360Page })))
const FinanceClientRegisterPage = lazy(() => import('./features/finance/pages/FinanceClientRegisterPage').then((m) => ({ default: m.FinanceClientRegisterPage })))
const FinanceProjectRegisterPage = lazy(() => import('./features/finance/pages/FinanceProjectRegisterPage').then((m) => ({ default: m.FinanceProjectRegisterPage })))
const BusinessDashboardPage = lazy(() => import('./features/business/BusinessDashboardPage').then((m) => ({ default: m.BusinessDashboardPage })))
const BDCommercialPage = lazy(() => import('./features/commercial/pages/BDCommercialPage').then((m) => ({ default: m.BDCommercialPage })))
const EmployeeProjectCostsPage = lazy(() => import('./features/commercial/pages/EmployeeProjectCostsPage').then((m) => ({ default: m.EmployeeProjectCostsPage })))
const FinanceCommercialPage = lazy(() => import('./features/commercial/pages/FinanceCommercialPage').then((m) => ({ default: m.FinanceCommercialPage })))
const ManagementCommercialPage = lazy(() => import('./features/commercial/pages/ManagementCommercialPage').then((m) => ({ default: m.ManagementCommercialPage })))

import { Layout } from './components/Layout'
import { ProtectedRoute } from './components/ProtectedRoute'
import { StrictProtectedRoute } from './components/StrictProtectedRoute'
import { useAuth } from './context/AuthContext'
import { roleHomePath, TECHNICAL_PM_ROLES } from './lib/roles'

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
    <Suspense fallback={<RouteFallback />}>
      <Routes>
        <Route path="/" element={user ? <Navigate to={needsBranchSelection ? '/select-branch' : roleHomePath(user.role)} replace /> : <WelcomePage />} />
        <Route path="/login" element={user ? <Navigate to={needsBranchSelection ? '/select-branch' : roleHomePath(user.role)} replace /> : <LoginPage />} />
        <Route path="/employee-login" element={user ? <Navigate to={needsBranchSelection ? '/select-branch' : roleHomePath(user.role)} replace /> : <LoginPage mode="employee" />} />
        <Route path="/register" element={user ? <Navigate to={needsBranchSelection ? '/select-branch' : roleHomePath(user.role)} replace /> : <RegisterPage />} />
        <Route path="/forgot-password" element={user ? <Navigate to={needsBranchSelection ? '/select-branch' : roleHomePath(user.role)} replace /> : <ForgotPasswordPage />} />
        <Route path="/verify-authenticator" element={<AuthenticatorPage />} />
        <Route path="/select-branch" element={<BranchSelectionPage />} />
        <Route path="/profile" element={<ProtectedRoute roles={['software_team', 'admin', 'management', 'it', 'drone', 'finance', 'hr', 'bd', 'ortho', 'lidar', 'civil', 'laser_scanning', 'bim', 'mobile_mapping', 'employee']}><WithLayout><ProfilePage /></WithLayout></ProtectedRoute>} />
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
        <Route path="/project-costs" element={<ProtectedRoute roles={['employee']}><WithLayout><EmployeeProjectCostsPage /></WithLayout></ProtectedRoute>} />
        <Route path="/expenses/new" element={<ProtectedRoute roles={['employee']}><WithLayout><ExpenseClaimCreatePage /></WithLayout></ProtectedRoute>} />
        <Route path="/expenses/:id/edit" element={<ProtectedRoute roles={['employee']}><WithLayout><ExpenseClaimCreatePage /></WithLayout></ProtectedRoute>} />
        <Route path="/expenses/:id/settle" element={<ProtectedRoute roles={['employee']}><WithLayout><AdvanceSettlementPage /></WithLayout></ProtectedRoute>} />
        <Route path="/expenses/:id" element={<ProtectedRoute roles={['employee']}><WithLayout><ExpenseClaimDetailPage /></WithLayout></ProtectedRoute>} />
        <Route path="/tickets" element={<ProtectedRoute roles={['employee', 'it', 'drone', 'management', 'software_team']}><WithLayout><TicketListPage /></WithLayout></ProtectedRoute>} />
        <Route path="/tickets/:id" element={<ProtectedRoute roles={['employee', 'it', 'drone', 'management', 'software_team']}><WithLayout><TicketDetailPage /></WithLayout></ProtectedRoute>} />
        <Route path="/software-team/security" element={<ProtectedRoute roles={['software_team']}><WithLayout><SoftwareSecurityPage /></WithLayout></ProtectedRoute>} />
        <Route path="/software-team/employee-master" element={<ProtectedRoute roles={['software_team', 'admin']}><WithLayout><EmployeeMasterPage /></WithLayout></ProtectedRoute>} />
        <Route path="/management/employee-master" element={<ProtectedRoute roles={['management']}><WithLayout><ManagementEmployeeMasterPage /></WithLayout></ProtectedRoute>} />
        <Route path="/onboarding" element={<ProtectedRoute roles={['hr', 'it', 'management', 'software_team', 'admin']}><WithLayout><OnboardingPage /></WithLayout></ProtectedRoute>} />
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
        <Route path="/bd/commercial" element={<StrictProtectedRoute roles={['bd', 'admin', 'management']}><WithLayout><BDCommercialPage /></WithLayout></StrictProtectedRoute>} />
        <Route path="/notifications" element={<ProtectedRoute roles={['employee', 'it', 'drone', 'finance', 'hr', 'bd', 'ortho', 'lidar', 'civil', 'laser_scanning', 'bim', 'mobile_mapping', 'management', 'admin', 'software_team']}><WithLayout><NotificationsPage /></WithLayout></ProtectedRoute>} />
        <Route path="/ortho" element={<StrictProtectedRoute roles={['ortho', 'lidar', 'mobile_mapping', 'laser_scanning', 'civil', 'employee', 'management', 'admin']}><WithLayout><OrthoDashboardPage /></WithLayout></StrictProtectedRoute>} />
        <Route path="/ortho/project-360/:projectId" element={<StrictProtectedRoute roles={['ortho', 'lidar', 'mobile_mapping', 'laser_scanning', 'civil', 'management', 'admin']}><WithLayout><ManagementProject360Page /></WithLayout></StrictProtectedRoute>} />
        <Route path="/finance" element={<ProtectedRoute roles={['finance', 'admin', 'management']}><WithLayout><FinanceDashboardPage /></WithLayout></ProtectedRoute>} />
        <Route path="/finance/claims" element={<ProtectedRoute roles={['finance', 'admin', 'management']}><WithLayout><FinanceClaimsPage /></WithLayout></ProtectedRoute>} />
        <Route path="/finance/reports" element={<ProtectedRoute roles={['finance', 'admin', 'management']}><WithLayout><FinanceReportsPage /></WithLayout></ProtectedRoute>} />
        <Route path="/finance/clients" element={<ProtectedRoute roles={['finance', 'admin', 'management']}><WithLayout><FinanceClientRegisterPage /></WithLayout></ProtectedRoute>} />
        <Route path="/finance/projects" element={<ProtectedRoute roles={['finance', 'admin', 'management']}><WithLayout><FinanceProjectRegisterPage /></WithLayout></ProtectedRoute>} />
        <Route path="/finance/billing" element={<ProtectedRoute roles={['finance', 'admin', 'management']}><WithLayout><FinanceBillingPage /></WithLayout></ProtectedRoute>} />
        <Route path="/finance/sales" element={<ProtectedRoute roles={['finance', 'admin', 'management']}><WithLayout><SalesRevenuePage mode="sales" /></WithLayout></ProtectedRoute>} />
        <Route path="/finance/revenue" element={<ProtectedRoute roles={['finance', 'admin', 'management']}><WithLayout><SalesRevenuePage mode="revenue" /></WithLayout></ProtectedRoute>} />
        <Route path="/finance/command-center" element={<ProtectedRoute roles={['finance', 'admin', 'management', ...TECHNICAL_PM_ROLES]}><WithLayout><FinanceCommandCenter /></WithLayout></ProtectedRoute>} />
        <Route path="/finance/uat-2026" element={<ProtectedRoute roles={['finance']}><WithLayout><UAT2026ControlPage /></WithLayout></ProtectedRoute>} />
        <Route path="/business" element={<ProtectedRoute roles={['finance', 'bd', 'management', 'admin', 'software_team', 'ortho', 'lidar', 'civil', 'laser_scanning', 'bim', 'mobile_mapping']}><WithLayout><BusinessDashboardPage /></WithLayout></ProtectedRoute>} />
        <Route path="/finance/commercial" element={<ProtectedRoute roles={['finance', 'admin', 'management']}><WithLayout><FinanceCommercialPage /></WithLayout></ProtectedRoute>} />
        <Route path="/admin/client-master" element={<ProtectedRoute roles={['admin']}><WithLayout><ClientManagementPage /></WithLayout></ProtectedRoute>} />
        <Route path="/finance/claims/:id" element={<ProtectedRoute roles={['finance', 'admin', 'management']}><WithLayout><ExpenseClaimDetailPage /></WithLayout></ProtectedRoute>} />
        <Route path="/management" element={<ProtectedRoute roles={['management', 'admin']}><WithLayout><ManagementDashboard /></WithLayout></ProtectedRoute>} />
        <Route path="/management/approvals" element={<ProtectedRoute roles={['management', 'admin']}><WithLayout><ManagementApprovalCenter /></WithLayout></ProtectedRoute>} />
        <Route path="/management/project-360" element={<ProtectedRoute roles={['management', 'admin']}><WithLayout><ManagementProject360Page /></WithLayout></ProtectedRoute>} />
        <Route path="/management/commercial" element={<ProtectedRoute roles={['management', 'admin']}><WithLayout><ManagementCommercialPage /></WithLayout></ProtectedRoute>} />
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
    </Suspense>
  )
}
