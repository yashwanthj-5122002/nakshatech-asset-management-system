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
import { ReplacementsPage } from './pages/ReplacementsPage'
import { ReportsPage } from './pages/ReportsPage'
import { WelcomePage } from './pages/WelcomePage'
import { WorkFormPage } from './pages/WorkFormPage'
import { RecentChangesPage } from './pages/RecentChangesPage'
import { HandoverReturnPage } from './pages/HandoverReturnPage'
import { PurchaseProcurementPage } from './pages/PurchaseProcurementPage'
import { BackupCenterPage } from './pages/BackupCenterPage'
import { roleHomePath } from './lib/roles'

function WithLayout({ children }: { children: ReactNode }) {
  return <Layout>{children}</Layout>
}

export default function App() {
  const { user } = useAuth()
  return (
    <Routes>
      <Route path="/" element={user ? <Navigate to={roleHomePath(user.role)} replace /> : <WelcomePage />} />
      <Route path="/login" element={user ? <Navigate to={roleHomePath(user.role)} replace /> : <LoginPage />} />
      <Route path="/it" element={<ProtectedRoute roles={['it', 'management', 'admin']}><WithLayout><ITDashboard /></WithLayout></ProtectedRoute>} />
      <Route path="/assets" element={<ProtectedRoute roles={['it', 'management', 'admin']}><WithLayout><AssetsPage /></WithLayout></ProtectedRoute>} />
      <Route path="/assets/new" element={<ProtectedRoute roles={['it', 'admin']}><WithLayout><AssetFormPage /></WithLayout></ProtectedRoute>} />
      <Route path="/assets/:id/edit" element={<ProtectedRoute roles={['it', 'admin']}><WithLayout><AssetFormPage /></WithLayout></ProtectedRoute>} />
      <Route path="/replacements" element={<ProtectedRoute roles={['it', 'management', 'admin']}><WithLayout><ReplacementsPage /></WithLayout></ProtectedRoute>} />
      <Route path="/it/handover-return" element={<ProtectedRoute roles={['it', 'management', 'admin']}><WithLayout><HandoverReturnPage /></WithLayout></ProtectedRoute>} />
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
      <Route path="/software-team" element={<ProtectedRoute roles={['software_team']}><WithLayout><AdminDashboard /></WithLayout></ProtectedRoute>} />
      <Route path="/admin" element={<ProtectedRoute roles={['admin']}><WithLayout><AdminDashboard /></WithLayout></ProtectedRoute>} />
      <Route path="/work" element={<ProtectedRoute><WithLayout><WorkFormPage /></WithLayout></ProtectedRoute>} />
      <Route path="/reports" element={<ProtectedRoute roles={['it', 'management', 'admin']}><WithLayout><ReportsPage /></WithLayout></ProtectedRoute>} />
      <Route path="/backups" element={<ProtectedRoute roles={['admin', 'management', 'it', 'drone']}><WithLayout><BackupCenterPage /></WithLayout></ProtectedRoute>} />
      <Route path="/future" element={<ProtectedRoute roles={['admin']}><WithLayout><FutureFeaturesPage /></WithLayout></ProtectedRoute>} />
      <Route path="*" element={<Navigate to={user ? roleHomePath(user.role) : '/'} replace />} />
    </Routes>
  )
}
