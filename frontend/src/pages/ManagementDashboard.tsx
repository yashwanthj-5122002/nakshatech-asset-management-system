import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  FolderKanban,
  HardDrive,
  IndianRupee,
  KeyRound,
  ShieldAlert,
  ShieldCheck,
  X,
  Building2,
  Activity,
  RefreshCw,
} from 'lucide-react'
import { DroneIcon as Drone, type AppIcon } from '../components/DroneIcon'
import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { DashboardHeader } from '../components/DashboardHeader'
import { DonutChart, HorizontalBars } from '../components/Charts'
import { useAuth } from '../context/AuthContext'
import { useITMonthUrl } from '../context/ITMonthContext'
import { apiFetch } from '../lib/api'
import { monthLabel } from '../lib/itMonth'
import type { DistributionItem } from '../types'
import type { LifecycleDashboard } from '../features/operations/lifecycle-types'
import '../management-auth.css'
import '../management-control.css'

type PurchaseStatus = 'pending_approval' | 'approved' | 'sent_back' | 'rejected' | 'purchase_completed'

type PurchaseRequestPreview = {
  id: number
  code: string
  title: string
  submitted_by?: string
  amount?: number
  department?: string
  status: PurchaseStatus
  target_url: string
  metadata?: {
    requested_employee?: string
    quantity?: number
    item_type?: string
    required_by_date?: string
    it_remarks?: string
  }
}

type RiskTicketPreview = {
  id: number
  ticket_code: string
  title: string
  department: string
  priority: string
  status: string
  sla_status?: string
  sla_due_at?: string
  sla_breached: boolean
  sla_warning: boolean
  target_url: string
}

type ManagementControlSummary = {
  authority_model: string
  month?: string
  generated_at?: string
  executive: {
    primary_assets: number
    assigned_assets: number
    available_assets: number
    repair_assets: number
    replacement_pending_assets: number
    active_it_work: number
    active_replacements: number
    pending_approvals: number
    pending_purchase_requests: number
    approved_purchase_value: number
    open_critical_tickets: number
    sla_warnings: number
    sla_breaches: number
  }
  purchase_summary?: {
    total: number
    pending_approval: number
    approved: number
    sent_back: number
    rejected: number
    purchase_completed: number
    approved_purchase_value: number
  }
  approvals?: PurchaseRequestPreview[]
  risk_tickets?: RiskTicketPreview[]
}

type SalesRevenueProjectRow = {
  project_id: number
  project_code: string
  project_name: string
  client_code: string | null
  client_name: string
  department_label: string
  sales_status: string
  projected_payment_date: string | null
  open_sales_inr: number
  received_against_open_sales_inr: number
  outstanding_inr: number
  sales_visible: boolean
}

type SalesRevenueEventRow = {
  project_id: number
  project_code: string
  project_name: string
  client_name: string
  department_label: string
  revenue_amount_inr: number
  revenue_date: string
  finance_invoice_number: string
  invoice_closed_at: string | null
}

type SalesRevenueOverview = {
  projects: SalesRevenueProjectRow[]
  revenue_events: SalesRevenueEventRow[]
}

type DepartmentPulseConfig = {
  key: string
  label: string
  href: string
  icon: AppIcon
  metrics: Array<{ key: string; label: string }>
}

const departmentPulseConfig: DepartmentPulseConfig[] = [
  { key: 'bd', label: 'Business Development', href: '/bd', icon: Building2, metrics: [{ key: 'projects', label: 'Projects' }, { key: 'clients', label: 'Clients' }] },
  { key: 'finance', label: 'Finance', href: '/finance', icon: IndianRupee, metrics: [{ key: 'payment_pending', label: 'Payments pending' }, { key: 'overdue', label: 'Overdue' }] },
  { key: 'ortho', label: 'Project Operations', href: '/ortho', icon: FolderKanban, metrics: [{ key: 'active_projects', label: 'Active projects' }, { key: 'rework', label: 'In rework' }] },
  { key: 'drone', label: 'Drone Operations', href: '/drone', icon: Drone, metrics: [{ key: 'active_projects', label: 'Active projects' }] },
  { key: 'it', label: 'IT & Support', href: '/it', icon: HardDrive, metrics: [{ key: 'active_assets', label: 'Active assets' }, { key: 'active_support_tickets', label: 'Open tickets' }] },
  { key: 'hr', label: 'People & Travel', href: '/management/travel-km', icon: Activity, metrics: [{ key: 'active_employees', label: 'Active employees' }] },
  { key: 'employee_support', label: 'Employee Support', href: '/tickets', icon: ClipboardCheck, metrics: [{ key: 'open_tickets', label: 'Open tickets' }] },
]

type WorkspaceLink = {
  to: string
  label: string
  description: string
  managementOnly?: boolean
}

type WorkspaceGroup = {
  label: string
  icon: AppIcon
  links: WorkspaceLink[]
}

const workspaceGroups: WorkspaceGroup[] = [
  {
    label: 'Executive & Governance',
    icon: ClipboardCheck,
    links: [
      { to: '/management/approvals', label: 'Purchase approvals', description: 'Decide pending procurement requests', managementOnly: true },
      { to: '/management/project-360', label: 'Project 360', description: 'Feedback, rework, billing and closure' },
      { to: '/management/commercial', label: 'Commercial analytics', description: 'Revenue, cost and margin analysis' },
      { to: '/reports', label: 'Executive reports', description: 'Download management workbooks and exports' },
    ],
  },
  {
    label: 'IT & Infrastructure',
    icon: HardDrive,
    links: [
      { to: '/assets', label: 'Asset register', description: 'Custody, assignment and specifications' },
      { to: '/it', label: 'IT dashboard', description: 'Asset readiness and operational work' },
      { to: '/work', label: 'IT work records', description: 'Maintenance and diagnostic history' },
      { to: '/replacements', label: 'Component changes', description: 'Replacement lifecycle records' },
    ],
  },
  {
    label: 'Risk, Field & Audit',
    icon: Activity,
    links: [
      { to: '/it/recent-changes', label: 'Recent changes', description: 'Traceable system activity and changes' },
      { to: '/tickets', label: 'Support & SLA', description: 'Critical tickets and service risk' },
      { to: '/it/purchases', label: 'Procurement records', description: 'Purchases, invoices and vendors' },
      { to: '/drone', label: 'Drone operations', description: 'Fleet, kits, projects and field work' },
    ],
  },
]

function displayMetric(value: number | null | undefined, loading: boolean, error: string): string {
  if (loading) return 'Loading'
  if (error) return 'Unavailable'
  return (value ?? 0).toLocaleString('en-IN')
}

function displayMoney(value: number | null | undefined, loading: boolean, error: string): string {
  if (loading) return 'Loading'
  if (error) return 'Unavailable'
  return `₹${(value ?? 0).toLocaleString('en-IN')}`
}

function displaySourceTime(value: string | null | undefined): string {
  if (!value) return 'Source time unavailable'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? 'Source time unavailable' : parsed.toLocaleString('en-IN')
}

function compactInr(value: number): string {
  const amount = value || 0
  const absolute = Math.abs(amount)
  const sign = amount < 0 ? '-' : ''
  if (absolute >= 1e7) return `${sign}₹${(absolute / 1e7).toFixed(absolute >= 1e9 ? 0 : 1)} Cr`
  if (absolute >= 1e5) return `${sign}₹${(absolute / 1e5).toFixed(1)} L`
  if (absolute >= 1e3) return `${sign}₹${(absolute / 1e3).toFixed(1)}K`
  return `${sign}₹${absolute.toFixed(0)}`
}

export function ManagementDashboard() {
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const { selectedMonth, setSelectedMonth } = useITMonthUrl()
  const [summary, setSummary] = useState<ManagementControlSummary | null>(null)
  const [summaryError, setSummaryError] = useState('')
  const [summaryLoading, setSummaryLoading] = useState(true)
  const [lifecycleData, setLifecycleData] = useState<LifecycleDashboard | null>(null)
  const [lifecycleError, setLifecycleError] = useState('')
  const [lifecycleLoading, setLifecycleLoading] = useState(true)
  const [financeData, setFinanceData] = useState<SalesRevenueOverview | null>(null)
  const [financeError, setFinanceError] = useState('')
  const [financeLoading, setFinanceLoading] = useState(true)
  const [financeView, setFinanceView] = useState<'revenue' | 'sales' | 'compare'>('revenue')
  const [refreshKey, setRefreshKey] = useState(0)
  const [showPasswordDialog, setShowPasswordDialog] = useState(false)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordError, setPasswordError] = useState('')
  const [changingPassword, setChangingPassword] = useState(false)

  useEffect(() => {
    let active = true
    setSummaryError('')
    setSummaryLoading(true)
    void apiFetch<ManagementControlSummary>(`/management/control-center?month=${encodeURIComponent(selectedMonth)}`)
      .then(payload => {
        if (!active) return
        setSummary(payload)
      })
      .catch(err => {
        if (!active) return
        setSummary(null)
        setSummaryError(err instanceof Error ? err.message : 'Unable to load executive control summary')
      })
      .finally(() => {
        if (active) setSummaryLoading(false)
      })
    return () => {
      active = false
    }
  }, [selectedMonth, refreshKey])

  useEffect(() => {
    let active = true
    setLifecycleError('')
    setLifecycleLoading(true)
    void apiFetch<LifecycleDashboard>('/operations/lifecycle/dashboard')
      .then(payload => {
        if (!active) return
        setLifecycleData(payload)
      })
      .catch(err => {
        if (!active) return
        setLifecycleData(null)
        setLifecycleError(err instanceof Error ? err.message : 'Unable to load project lifecycle data')
      })
      .finally(() => {
        if (active) setLifecycleLoading(false)
      })
    return () => {
      active = false
    }
  }, [refreshKey])

  useEffect(() => {
    let active = true
    setFinanceError('')
    setFinanceLoading(true)
    void apiFetch<SalesRevenueOverview>('/finance/sales-revenue')
      .then(payload => {
        if (!active) return
        setFinanceData(payload)
      })
      .catch(err => {
        if (!active) return
        setFinanceData(null)
        setFinanceError(err instanceof Error ? err.message : 'Unable to load Finance and Revenue data')
      })
      .finally(() => {
        if (active) setFinanceLoading(false)
      })
    return () => {
      active = false
    }
  }, [refreshKey])

  function closePasswordDialog() {
    if (changingPassword) return
    setShowPasswordDialog(false)
    setCurrentPassword('')
    setNewPassword('')
    setConfirmPassword('')
    setPasswordError('')
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault()
    setChangingPassword(true)
    setPasswordError('')
    try {
      const result = await apiFetch<{ message: string }>('/auth/management/change-password', {
        method: 'POST',
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
          confirm_password: confirmPassword,
        }),
      })
      sessionStorage.setItem('management_password_changed', result.message)
      logout()
      navigate('/login', { replace: true })
    } catch (err) {
      setPasswordError(err instanceof Error ? err.message : 'Password change failed')
    } finally {
      setChangingPassword(false)
    }
  }

  const executive = summary?.executive
  const lifecycle = lifecycleData?.summary

  // Asset Metrics
  const totalAssets = executive?.primary_assets ?? 0
  const assignedAssets = executive?.assigned_assets ?? 0
  const availableAssets = executive?.available_assets ?? 0
  const repairAssets = executive?.repair_assets ?? 0
  const replacementAssets = executive?.replacement_pending_assets ?? 0

  const utilizationRate = totalAssets > 0 ? Math.round((assignedAssets / totalAssets) * 100) : 0
  const availableRate = totalAssets > 0 ? Math.round((availableAssets / totalAssets) * 100) : 0
  const maintenanceRate = totalAssets > 0 ? Math.round(((repairAssets + replacementAssets) / totalAssets) * 100) : 0

  const assetDistributionData: DistributionItem[] = [
    { name: 'Assigned / In Use', value: assignedAssets, key: 'assigned' },
    { name: 'Available in Stock', value: availableAssets, key: 'available' },
    { name: 'Under Repair', value: repairAssets, key: 'repair' },
    { name: 'Replacement Pending', value: replacementAssets, key: 'replacement_pending' },
  ]

  // Commercial / Lifecycle Metrics
  const totalProjects = lifecycle?.total_projects ?? 0
  const activeProjects = lifecycle?.active_projects ?? 0
  const awaitingFeedback = lifecycle?.awaiting_feedback ?? 0
  const reworkCount = lifecycle?.rework ?? 0
  const readyForBilling = lifecycle?.ready_for_billing ?? 0
  const paymentPending = lifecycle?.payment_pending ?? 0
  const overdueInvoices = lifecycle?.overdue ?? 0
  const closedProjects = lifecycle?.closed ?? 0

  // Decision & Risk Metrics
  const pendingApprovalsCount = executive?.pending_purchase_requests ?? 0
  const approvedPurchaseValue = executive?.approved_purchase_value ?? 0
  const slaBreachesCount = executive?.sla_breaches ?? 0
  const criticalTicketsCount = executive?.open_critical_tickets ?? 0
  const slaWarningsCount = executive?.sla_warnings ?? 0
  const departmentOverview = lifecycleData?.department_overview
  const departmentOverviewUnavailable = lifecycleError || (!lifecycleLoading && !departmentOverview ? 'Department overview unavailable' : '')
  const workforceCount = departmentOverview?.hr?.active_employees
  const summaryUnavailable = Boolean(summaryError || (!summaryLoading && !summary))
  const lifecycleUnavailable = Boolean(lifecycleError || (!lifecycleLoading && !lifecycleData))
  const companyLoading = summaryLoading || lifecycleLoading
  const companySourceError = summaryUnavailable || lifecycleUnavailable || departmentOverviewUnavailable ? 'One or more source views are unavailable' : ''
  const companyDecisionCount = pendingApprovalsCount
  const companyFinancialAttention = overdueInvoices
  const companyOperationalRisk = criticalTicketsCount + slaBreachesCount + reworkCount
  const companyAttentionCount = companyDecisionCount + companyFinancialAttention + companyOperationalRisk
  const financeUnavailable = Boolean(financeError || (!financeLoading && !financeData))
  const financeProjects = financeData?.projects ?? []
  const revenueEvents = financeData?.revenue_events ?? []
  const openSalesProjects = financeProjects.filter(row => row.sales_visible && row.open_sales_inr > 0)
  const monthRevenueEvents = useMemo(
    () => revenueEvents.filter(row => row.revenue_date.slice(0, 7) === selectedMonth),
    [revenueEvents, selectedMonth],
  )
  const realizedRevenue = monthRevenueEvents.reduce((sum, row) => sum + row.revenue_amount_inr, 0)
  const openSalesTotal = openSalesProjects.reduce((sum, row) => sum + row.open_sales_inr, 0)
  const receivedAgainstSales = openSalesProjects.reduce((sum, row) => sum + row.received_against_open_sales_inr, 0)
  const outstandingCollections = openSalesProjects.reduce((sum, row) => sum + row.outstanding_inr, 0)
  const collectionRate = openSalesTotal + receivedAgainstSales > 0
    ? Math.round((receivedAgainstSales / (openSalesTotal + receivedAgainstSales)) * 100)
    : 0

  const revenueTrend = useMemo(() => {
    const totals = new Map<string, number>()
    for (const event of revenueEvents) {
      const key = event.revenue_date.slice(0, 7)
      totals.set(key, (totals.get(key) || 0) + event.revenue_amount_inr)
    }
    const [year, month] = selectedMonth.split('-').map(Number)
    return Array.from({ length: 6 }, (_, index) => {
      const date = new Date(Date.UTC(year, month - 1 - (5 - index), 1))
      const key = `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`
      return { key, label: monthLabel(key), value: totals.get(key) || 0 }
    })
  }, [revenueEvents, selectedMonth])

  const revenueByDepartment = useMemo(() => {
    const totals = new Map<string, number>()
    for (const event of monthRevenueEvents) {
      totals.set(event.department_label, (totals.get(event.department_label) || 0) + event.revenue_amount_inr)
    }
    return [...totals.entries()]
      .sort((left, right) => right[1] - left[1])
      .map(([name, value]): DistributionItem => ({ name, value }))
  }, [monthRevenueEvents])

  const salesStatusMix = useMemo(() => {
    const totals = new Map<string, number>()
    for (const project of openSalesProjects) {
      totals.set(project.sales_status, (totals.get(project.sales_status) || 0) + project.open_sales_inr)
    }
    return [...totals.entries()]
      .sort((left, right) => right[1] - left[1])
      .map(([name, value]): DistributionItem => ({ name, value }))
  }, [openSalesProjects])

  const maxRevenueTrend = Math.max(...revenueTrend.map(point => point.value), 1)
  const revenueProjects = new Set(monthRevenueEvents.map(row => row.project_id)).size
  const averageClosedInvoice = monthRevenueEvents.length ? realizedRevenue / monthRevenueEvents.length : 0
  const overdueSalesProjects = openSalesProjects.filter(row => row.sales_status === 'Overdue').length

  const salesDepartmentMix = useMemo(() => {
    const totals = new Map<string, number>()
    for (const project of openSalesProjects) {
      totals.set(project.department_label, (totals.get(project.department_label) || 0) + project.open_sales_inr)
    }
    return [...totals.entries()]
      .sort((left, right) => right[1] - left[1])
      .map(([name, value]): DistributionItem => ({ name, value }))
  }, [openSalesProjects])

  const comparisonMax = Math.max(openSalesTotal, realizedRevenue, 1)
  const attentionTone = companyLoading ? 'is-loading' : companySourceError ? 'is-loading' : companyAttentionCount > 0 ? 'has-attention' : 'all-clear'
  const attentionTitle = companyLoading
    ? 'Loading company pulse'
    : companySourceError
      ? 'Company pulse partially unavailable'
      : companyAttentionCount > 0
        ? `${companyAttentionCount} item${companyAttentionCount === 1 ? '' : 's'} need attention`
        : 'No recorded exceptions in the available data'
  const attentionDescription = companyLoading
    ? 'Loading management, project and service signals. The page will not show a clean state until the sources respond.'
    : companySourceError
      ? 'One or more source views could not be loaded. Review the available data before making a company-wide decision.'
      : companyAttentionCount > 0
        ? 'Purchase decisions, overdue payments and operational risks are grouped here so management can act from one view.'
        : 'No recorded exceptions are available in the loaded management, lifecycle and service sources.'
  const attentionHref = companyDecisionCount > 0 ? '/management/approvals' : '/management/project-360'
  const attentionAction = companyDecisionCount > 0 ? 'Open decision queue' : 'Open project controls'

  const pipelineStages = [
    { key: 'feedback', label: 'Awaiting Client Feedback', count: awaitingFeedback, color: '#f59e0b', desc: 'Pending acceptance' },
    { key: 'rework', label: 'Rework / BD Classification', count: reworkCount, color: '#8b5cf6', desc: 'Active revision cycles' },
    { key: 'billing', label: 'Ready for Billing', count: readyForBilling, color: '#10b981', desc: 'Accepted milestones' },
    { key: 'payment', label: 'Payment Pending', count: paymentPending, color: '#3b82f6', desc: 'Invoices issued to clients' },
    { key: 'overdue', label: 'Overdue Invoices', count: overdueInvoices, color: '#ef4444', isAlert: overdueInvoices > 0, desc: 'Payment past due date' },
    { key: 'closed', label: 'Closed / Settled', count: closedProjects, color: '#64748b', desc: 'Completed & settled' },
  ]

  const maxPipelineCount = Math.max(...pipelineStages.map(s => s.count), 1)

  return (
    <>
      <DashboardHeader
        variant="compact"
        eyebrow="EXECUTIVE COMPANY PULSE"
        title="Management Dashboard"
        description="Company-wide decisions, delivery, finance, people and operational risk for the selected reporting month."
        actions={<>
          <label className="management-month-field">
            <span>Reporting month</span>
            <input type="month" value={selectedMonth} onChange={event => setSelectedMonth(event.target.value)} />
          </label>
          <button className="management-refresh-button" type="button" onClick={() => setRefreshKey(key => key + 1)} disabled={companyLoading}>
            <RefreshCw size={16} /> {companyLoading ? 'Refreshing' : 'Refresh'}
          </button>
          {user?.role === 'management' && (
            <button className="management-change-password-button" type="button" onClick={() => setShowPasswordDialog(true)}>
              <KeyRound size={17} />
              <span>Change Password</span>
            </button>
          )}
        </>}
      />

      {summaryError && <div className="error-message" role="alert">Management control data: {summaryError}</div>}
      {lifecycleError && <div className="error-message" role="alert">Project lifecycle data: {lifecycleError}</div>}
      {financeError && <div className="error-message" role="alert">Finance and Revenue data: {financeError}</div>}

      <section className="management-finance-section" aria-labelledby="finance-priority-heading">
        <div className="management-section-heading">
          <div>
            <span className="section-kicker">FINANCE · SALES &amp; REVENUE</span>
            <h2 id="finance-priority-heading">Finance performance</h2>
            <p>Sales is open pipeline. Revenue is realised closed invoices. They are different measures and are never added together.</p>
          </div>
          <div className="management-finance-tabs" role="tablist" aria-label="Finance view">
            <button type="button" role="tab" aria-selected={financeView === 'revenue'} className={financeView === 'revenue' ? 'active' : ''} onClick={() => setFinanceView('revenue')}>Revenue</button>
            <button type="button" role="tab" aria-selected={financeView === 'sales'} className={financeView === 'sales' ? 'active' : ''} onClick={() => setFinanceView('sales')}>Sales</button>
            <button type="button" role="tab" aria-selected={financeView === 'compare'} className={financeView === 'compare' ? 'active' : ''} onClick={() => setFinanceView('compare')}>Compare</button>
          </div>
        </div>

        {financeLoading || financeUnavailable ? (
          <p className="management-panel-state">{financeLoading ? 'Loading Finance and Revenue intelligence…' : 'Finance and Revenue data is unavailable for this source.'}</p>
        ) : financeView === 'revenue' ? (
          <>
            <div className="management-finance-kpis">
              <Link to="/finance/revenue" className="management-finance-kpi tone-green">
                <span>Realised revenue · {monthLabel(selectedMonth)}</span>
                <strong>{compactInr(realizedRevenue)}</strong>
                <small>Fully paid and closed Finance invoices only</small>
              </Link>
              <Link to="/finance/revenue" className="management-finance-kpi tone-teal">
                <span>Closed invoices</span>
                <strong>{monthRevenueEvents.length}</strong>
                <small>Revenue events in {monthLabel(selectedMonth)}</small>
              </Link>
              <Link to="/finance/revenue" className="management-finance-kpi tone-blue">
                <span>Average closed invoice</span>
                <strong>{compactInr(averageClosedInvoice)}</strong>
                <small>Realised average for this month</small>
              </Link>
              <Link to="/finance/revenue" className="management-finance-kpi tone-purple">
                <span>Revenue projects</span>
                <strong>{revenueProjects}</strong>
                <small>Distinct projects realised</small>
              </Link>
            </div>

            <div className="management-finance-charts">
              <article className="panel chart-panel management-finance-trend-panel">
                <div className="panel-heading">
                  <div>
                    <span className="section-kicker">REVENUE TREND</span>
                    <h2>Realised revenue · last 6 months</h2>
                    <p>Closed Finance invoices only. No forecast or open pipeline value is included.</p>
                  </div>
                  <Link to="/finance/revenue"><span>Open Revenue</span><ArrowRight size={14} /></Link>
                </div>
                <div className="management-finance-trend" role="img" aria-label="Realised revenue for the last six months">
                  {revenueTrend.map(point => (
                    <div className="management-finance-trend-col" key={point.key}>
                      <span className="management-finance-trend-value">{compactInr(point.value)}</span>
                      <div className="management-finance-trend-track">
                        <i style={{ height: `${point.value > 0 ? Math.max((point.value / maxRevenueTrend) * 100, 6) : 0}%` }} />
                      </div>
                      <small>{point.label}</small>
                    </div>
                  ))}
                </div>
              </article>

              <div className="management-finance-side">
                <article className="panel">
                  <div className="panel-heading">
                    <div>
                      <span className="section-kicker">REVENUE BY DEPARTMENT</span>
                      <h2>{monthLabel(selectedMonth)} realised mix</h2>
                    </div>
                  </div>
                  {revenueByDepartment.length ? <HorizontalBars data={revenueByDepartment} maxItems={8} /> : <p className="management-panel-state">No realised revenue for this month yet.</p>}
                </article>
              </div>
            </div>
          </>
        ) : financeView === 'sales' ? (
          <>
            <div className="management-finance-kpis">
              <Link to="/finance/sales" className="management-finance-kpi tone-blue">
                <span>Open sales pipeline</span>
                <strong>{compactInr(openSalesTotal)}</strong>
                <small>{openSalesProjects.length} project{openSalesProjects.length === 1 ? '' : 's'} still open in Sales</small>
              </Link>
              <Link to="/finance/sales" className="management-finance-kpi tone-teal">
                <span>Received on open sales</span>
                <strong>{compactInr(receivedAgainstSales)}</strong>
                <small>{collectionRate}% of open + received value</small>
              </Link>
              <Link to="/finance/sales" className={`management-finance-kpi ${outstandingCollections > 0 ? 'tone-orange' : 'tone-green'}`}>
                <span>Outstanding collections</span>
                <strong>{compactInr(outstandingCollections)}</strong>
                <small>Still to collect before revenue recognition</small>
              </Link>
              <Link to="/finance/sales" className={`management-finance-kpi ${overdueSalesProjects > 0 ? 'tone-red' : 'tone-green'}`}>
                <span>Overdue sales projects</span>
                <strong>{overdueSalesProjects}</strong>
                <small>Open projects with overdue collection state</small>
              </Link>
            </div>

            <div className="management-finance-charts">
              <article className="panel">
                <div className="panel-heading">
                  <div>
                    <span className="section-kicker">SALES BY DEPARTMENT</span>
                    <h2>Open pipeline mix</h2>
                    <p>Value still open in the commercial pipeline, not yet revenue.</p>
                  </div>
                  <Link to="/finance/sales"><span>Open Sales</span><ArrowRight size={14} /></Link>
                </div>
                {salesDepartmentMix.length ? <HorizontalBars data={salesDepartmentMix} maxItems={8} /> : <p className="management-panel-state">No open sales pipeline is currently recorded.</p>}
              </article>
              <div className="management-finance-side">
                <article className="panel">
                  <div className="panel-heading">
                    <div>
                      <span className="section-kicker">OPEN SALES STATUS</span>
                      <h2>Collection state</h2>
                    </div>
                  </div>
                  {salesStatusMix.length ? <DonutChart data={salesStatusMix} centerLabel="Open Sales" ariaLabel="Open sales value by collection state" /> : <p className="management-panel-state">No open sales pipeline is currently recorded.</p>}
                </article>
              </div>
            </div>
          </>
        ) : (
          <>
            <div className="management-finance-compare">
              <article className="management-compare-card sales">
                <span>Sales pipeline · open value</span>
                <strong>{compactInr(openSalesTotal)}</strong>
                <small>Current open pipeline snapshot. Not revenue yet: the value leaves Sales only after the Finance invoice is fully paid and closed.</small>
                <ul>
                  <li>{openSalesProjects.length} open project{openSalesProjects.length === 1 ? '' : 's'}</li>
                  <li>{compactInr(receivedAgainstSales)} received against open sales</li>
                  <li>{compactInr(outstandingCollections)} still outstanding</li>
                </ul>
              </article>
              <article className="management-compare-card revenue">
                <span>Realised revenue · {monthLabel(selectedMonth)}</span>
                <strong>{compactInr(realizedRevenue)}</strong>
                <small>Actual recognised money for {monthLabel(selectedMonth)} from fully paid, closed Finance invoices only.</small>
                <ul>
                  <li>{monthRevenueEvents.length} closed invoice{monthRevenueEvents.length === 1 ? '' : 's'}</li>
                  <li>{revenueProjects} project{revenueProjects === 1 ? '' : 's'} realised</li>
                  <li>{compactInr(averageClosedInvoice)} average closed invoice</li>
                </ul>
              </article>
            </div>
            <article className="panel management-compare-panel">
              <div className="panel-heading">
                <div>
                  <span className="section-kicker">SIDE-BY-SIDE VALUE</span>
                  <h2>Sales pipeline vs realised revenue</h2>
                </div>
              </div>
              <div className="management-compare-bars">
                <div>
                  <div className="management-compare-bar-label"><span>Open sales pipeline</span><strong>{compactInr(openSalesTotal)}</strong></div>
                  <div className="management-compare-bar-track"><i className="sales" style={{ width: `${(openSalesTotal / comparisonMax) * 100}%` }} /></div>
                </div>
                <div>
                  <div className="management-compare-bar-label"><span>Realised revenue · {monthLabel(selectedMonth)}</span><strong>{compactInr(realizedRevenue)}</strong></div>
                  <div className="management-compare-bar-track"><i className="revenue" style={{ width: `${(realizedRevenue / comparisonMax) * 100}%` }} /></div>
                </div>
              </div>
              <p className="management-compare-note">These two numbers are different measures and different time scopes: Sales is the current open pipeline, while Revenue is only realised money from fully paid, closed invoices in {monthLabel(selectedMonth)}. They must not be added together.</p>
            </article>
          </>
        )}
      </section>

      <section className="management-freshness-row" aria-label="Data freshness">
        <span><span className="management-freshness-dot" /> Company pulse</span>
        <span>Management source: {displaySourceTime(summary?.generated_at)}</span>
        <span>Selected month decisions · current operational snapshots</span>
        <span>{companySourceError ? 'Partial source availability' : companyLoading ? 'Refreshing sources' : 'Sources loaded'}</span>
      </section>

      <section className={`management-attention-strip ${attentionTone}`} aria-live="polite">
        <div className="management-attention-copy">
          <div className="management-attention-icon">
            {companyLoading ? <RefreshCw size={20} /> : companySourceError ? <AlertTriangle size={20} /> : companyAttentionCount > 0 ? <ClipboardCheck size={20} /> : <ShieldCheck size={20} />}
          </div>
          <div>
            <h2>{attentionTitle}</h2>
            <p>{attentionDescription}</p>
          </div>
        </div>
        <Link to={attentionHref} className="management-attention-action">{attentionAction} <ArrowRight size={16} /></Link>
      </section>

      <section className="management-company-kpis" aria-label="Company key performance indicators">
        <Link to="/management/project-360" className="management-company-kpi tone-purple">
          <span className="management-company-kpi-label">Active projects</span>
          <strong>{displayMetric(activeProjects, lifecycleLoading, lifecycleUnavailable ? 'Project source unavailable' : '')}</strong>
          <small>{lifecycleLoading ? 'Loading project pipeline' : lifecycleUnavailable ? 'Project source unavailable' : `${displayMetric(totalProjects, false, '')} total project records`}</small>
        </Link>
        <Link to="/management/approvals" className="management-company-kpi tone-orange">
          <span className="management-company-kpi-label">Decisions pending</span>
          <strong>{displayMetric(companyDecisionCount, summaryLoading, summaryUnavailable ? 'Decision source unavailable' : '')}</strong>
          <small>{summaryLoading ? 'Loading approval queue' : summaryUnavailable ? 'Decision source unavailable' : 'Management approvals only'}</small>
        </Link>
        <Link to="/management/travel-km" className="management-company-kpi tone-blue">
          <span className="management-company-kpi-label">Active employees</span>
          <strong>{displayMetric(workforceCount, lifecycleLoading, departmentOverviewUnavailable || (!departmentOverview ? 'Workforce data unavailable' : ''))}</strong>
          <small>{lifecycleLoading ? 'Loading workforce' : departmentOverviewUnavailable ? 'Workforce source unavailable' : 'Active employees across the company'}</small>
        </Link>
        <Link to="/tickets" className={`management-company-kpi ${companyOperationalRisk > 0 ? 'tone-red' : 'tone-green'}`}>
          <span className="management-company-kpi-label">Operational risk</span>
          <strong>{displayMetric(companyOperationalRisk, companyLoading, companySourceError)}</strong>
          <small>{summaryLoading ? 'Loading operational risk' : summaryUnavailable ? 'Control source unavailable' : `${displayMetric(criticalTicketsCount, false, '')} critical tickets · ${displayMetric(slaBreachesCount, false, '')} SLA breaches`}</small>
        </Link>
      </section>

      <section className="management-department-section" aria-labelledby="department-pulse-heading">
        <div className="management-section-heading">
          <div>
            <span className="section-kicker">COMPANY COVERAGE</span>
            <h2 id="department-pulse-heading">Department pulse</h2>
            <p>Start with the team or area that needs attention, then open its existing workspace.</p>
          </div>
          <span className="management-section-status">{lifecycleLoading ? 'Loading departments' : departmentOverviewUnavailable ? 'Partially unavailable' : `${departmentPulseConfig.length} departments`}</span>
        </div>
        <div className="management-department-grid">
          {departmentPulseConfig.map(department => {
            const Icon = department.icon
            const metrics = departmentOverview?.[department.key]
            const unavailable = lifecycleLoading || departmentOverviewUnavailable || !metrics
            return (
              <Link to={department.href} className="management-department-card" key={department.key}>
                <div className="management-department-card-head">
                  <span className="management-department-icon"><Icon size={18} /></span>
                  <ArrowRight size={15} className="management-department-arrow" />
                </div>
                <strong>{department.label}</strong>
                <div className="management-department-metrics">
                  {department.metrics.map(metric => <span key={metric.key}><b>{displayMetric(metrics?.[metric.key], lifecycleLoading, departmentOverviewUnavailable || (!metrics ? 'Department counts unavailable' : ''))}</b>{metric.label}</span>)}
                </div>
                {unavailable && <small className="management-department-unavailable">Counts unavailable</small>}
              </Link>
            )
          })}
        </div>
      </section>

      {/* Visual Analytics Row 1: Asset Portfolio Donut + Project 360 Lifecycle Pipeline */}
      <section className="dashboard-grid two-column">
        {/* Panel 1: IT Asset Portfolio Distribution */}
        <article className="panel chart-panel">
          <div className="panel-heading">
            <div>
              <span className="section-kicker">INFRASTRUCTURE ALLOCATION</span>
              <h2>IT Asset Portfolio &amp; Readiness</h2>
              <p>Current snapshot across {summaryLoading ? 'loading IT assets' : `${totalAssets} primary computing assets`}.</p>
            </div>
            <Link to="/assets" title="View complete asset register">
              <span>Inspect Assets</span>
              <ArrowRight size={14} />
            </Link>
          </div>

          {summaryLoading || summaryUnavailable ? (
            <p className="management-panel-state">{summaryLoading ? 'Loading IT inventory…' : 'IT inventory is unavailable for this source.'}</p>
          ) : (
            <>
              <DonutChart
                data={assetDistributionData}
                centerLabel="Primary Assets"
                ariaLabel="IT assets allocation by operational status"
              />

              <div className="management-stacked-bar" role="img" aria-label="Visual asset distribution bar">
                <span style={{ width: `${utilizationRate}%`, background: '#0b4f8a' }} title={`Assigned: ${assignedAssets} (${utilizationRate}%)`} />
                <span style={{ width: `${availableRate}%`, background: '#12aabd' }} title={`Available: ${availableAssets} (${availableRate}%)`} />
                <span style={{ width: `${maintenanceRate}%`, background: '#cf5b68' }} title={`Under Maintenance: ${repairAssets + replacementAssets}`} />
              </div>

              <div className="mini-metrics">
                <span><strong>{utilizationRate}%</strong> Utilization</span>
                <span><strong>{availableRate}%</strong> Reserve Stock</span>
                <span><strong>{repairAssets + replacementAssets}</strong> In Maintenance</span>
                <span><strong>{displayMetric(executive?.active_it_work, summaryLoading, summaryUnavailable ? 'Control source unavailable' : '')}</strong> Active Tasks</span>
              </div>
            </>
          )}
        </article>

        {/* Panel 2: Commercial Lifecycle Pipeline */}
        <article className="panel chart-panel">
          <div className="panel-heading">
            <div>
              <span className="section-kicker">COMMERCIAL LIFECYCLE · V8.1</span>
              <h2>Project 360 Pipeline Breakdown</h2>
              <p>Real-time lifecycle tracking from delivery to client feedback, rework &amp; payment</p>
            </div>
            <Link to="/management/project-360" title="Open Project 360 Command Center">
              <span>Open Project 360</span>
              <ArrowRight size={14} />
            </Link>
          </div>

          {lifecycleLoading || lifecycleUnavailable ? (
            <p className="management-panel-state">{lifecycleLoading ? 'Loading project lifecycle…' : 'Project lifecycle is unavailable for this source.'}</p>
          ) : (
            <>
          <div className="management-pipeline-list">
            {pipelineStages.map(stage => {
              const fillPercent = maxPipelineCount > 0 ? (stage.count / maxPipelineCount) * 100 : 0
              return (
                <div key={stage.key} className={`management-pipeline-stage ${stage.isAlert ? 'is-alert' : ''}`}>
                  <div className="management-pipeline-label">
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: stage.color, display: 'inline-block' }} />
                    <span>{stage.label}</span>
                  </div>
                  <div className="management-pipeline-track">
                    <div
                      className="management-pipeline-fill"
                      style={{ width: `${Math.max(fillPercent, stage.count > 0 ? 8 : 0)}%`, background: stage.color }}
                    />
                  </div>
                  <span className="management-pipeline-count">{stage.count}</span>
                </div>
              )
            })}
          </div>

          {overdueInvoices > 0 ? (
            <div className="alert-row severity-high" style={{ marginTop: 14 }}>
              <AlertTriangle size={18} />
              <div>
                <strong>Commercial Attention: {overdueInvoices} Overdue Invoice(s)</strong>
                <small>Client payment overdue past agreed credit terms. Action required in Project 360.</small>
              </div>
              <Link to="/management/project-360" className="ghost-link" style={{ padding: '4px 8px', fontSize: '0.74rem', fontWeight: 700 }}>
                View Invoices
              </Link>
            </div>
          ) : (
            <div className="mini-metrics" style={{ marginTop: 14 }}>
              <span><strong>{totalProjects}</strong> Total Projects</span>
              <span><strong>{readyForBilling}</strong> Billable Milestones</span>
              <span><strong>{paymentPending}</strong> Outstanding Payments</span>
              <span><strong>{closedProjects}</strong> Settled Projects</span>
            </div>
          )}
           </>
         )}
       </article>
      </section>

      {/* Visual Analytics Row 2: Service SLA Health + Purchase Order Governance */}
      <section className="dashboard-grid two-column">
        {/* Panel 3: SLA & Helpdesk Service Radar */}
        <article className="panel">
          <div className="panel-heading">
            <div>
              <span className="section-kicker">SERVICE LEVEL AGREEMENT</span>
              <h2>Support SLA &amp; Service Reliability</h2>
              <p>Proactive monitoring of operational tickets, resolution times, and service breaches</p>
            </div>
            <Link to="/tickets" title="View all support tickets">
              <span>View Tickets</span>
              <ArrowRight size={14} />
            </Link>
          </div>

          <div className={`management-sla-header-card ${summaryLoading ? 'loading' : slaBreachesCount === 0 ? 'healthy' : 'unhealthy'}`}>
            <div>
              <strong style={{ fontSize: '1rem', display: 'block' }}>
                {summaryLoading ? 'Loading service health' : summaryUnavailable ? 'Service health unavailable' : slaBreachesCount === 0 ? 'No SLA breach recorded' : `${slaBreachesCount} SLA breach${slaBreachesCount === 1 ? '' : 'es'} active`}
              </strong>
              <span style={{ fontSize: '0.76rem', opacity: 0.85 }}>
                {summaryLoading
                  ? 'Checking open support tickets against their response and resolution targets.'
                  : summaryUnavailable
                    ? 'The management control source could not be loaded. Open Support & SLA for the latest ticket view.'
                    : slaBreachesCount === 0
                      ? 'No current breach was returned. Warnings and critical tickets may still need review.'
                      : 'Tickets have exceeded their recorded resolution timeframe and require escalation.'}
              </span>
            </div>
            {summaryLoading ? <RefreshCw size={28} /> : summaryUnavailable ? <AlertTriangle size={28} /> : slaBreachesCount === 0 ? <ShieldCheck size={28} /> : <ShieldAlert size={28} />}
          </div>

          {summaryLoading || summaryUnavailable ? (
            <p className="management-panel-state">{summaryLoading ? 'Loading SLA metrics…' : 'SLA metrics are unavailable for this source.'}</p>
          ) : (
            <div className="management-sla-metric-grid">
              <div className="management-sla-metric-item">
                <strong style={{ color: criticalTicketsCount > 0 ? '#ef4444' : '#0f172a' }}>{criticalTicketsCount}</strong>
                <span>Critical Open</span>
              </div>
              <div className="management-sla-metric-item">
                <strong style={{ color: slaWarningsCount > 0 ? '#f59e0b' : '#0f172a' }}>{slaWarningsCount}</strong>
                <span>SLA Warnings</span>
              </div>
              <div className="management-sla-metric-item">
                <strong>{executive?.active_it_work ?? 0}</strong>
                <span>Active Work</span>
              </div>
              <div className="management-sla-metric-item">
                <strong>{executive?.active_replacements ?? 0}</strong>
                <span>Replacements</span>
              </div>
            </div>
          )}

            {summaryLoading && <p className="management-panel-state">Loading risk tickets…</p>}
            {!summaryLoading && summaryError && <p className="management-panel-state">Ticket risk data is unavailable. <Link to="/tickets">Open Support & SLA</Link></p>}
            {!summaryLoading && !summaryError && summary?.risk_tickets && summary.risk_tickets.length > 0 ? (
            <div className="management-risk-list" style={{ marginTop: 10 }}>
              {summary.risk_tickets.slice(0, 3).map(ticket => (
                <Link to={ticket.target_url} key={ticket.id} className={ticket.sla_breached ? 'breached' : ticket.sla_warning ? 'warning' : ''}>
                  <div>
                    <strong style={{ fontSize: '0.8rem' }}>{ticket.ticket_code}: {ticket.title}</strong>
                    <small>{ticket.department} · Priority: {ticket.priority} · Status: {ticket.status}</small>
                  </div>
                  <span style={{ fontSize: '0.72rem', fontWeight: 700, color: ticket.sla_breached ? '#dc2626' : '#d97706' }}>
                    {ticket.sla_status || (ticket.sla_breached ? 'BREACHED' : 'WARNING')}
                  </span>
                </Link>
              ))}
            </div>
          ) : (
            <p className="management-panel-state">No current ticket risks were returned. Open Support & SLA for the complete queue.</p>
          )}
        </article>

        {/* Panel 4: Purchase Order Governance & Decision Queue */}
        <article className="panel">
          <div className="panel-heading">
            <div>
              <span className="section-kicker">DECISION GATE &amp; PROCUREMENT</span>
              <h2>Purchase Order Governance</h2>
              <p>Hardware, software, and operational procurement decisions for {monthLabel(selectedMonth)}</p>
            </div>
            <Link to="/management/approvals" title="Open Purchase Approval Centre">
              <span>Approval Centre</span>
              <ArrowRight size={14} />
            </Link>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 18px', background: '#f8fafc', borderRadius: 12, border: '1px solid #e2e8f0', marginBottom: 14 }}>
            <div>
              <span style={{ fontSize: '0.68rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.05em' }}>Approved Capital Outlay</span>
              <div style={{ fontSize: '1.45rem', fontWeight: 800, color: '#0f172a', marginTop: 2 }}>
                {displayMoney(approvedPurchaseValue, summaryLoading, summaryUnavailable ? 'Procurement source unavailable' : '')}
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <span style={{ fontSize: '0.68rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.05em' }}>Total Requests</span>
              <div style={{ fontSize: '1.45rem', fontWeight: 800, color: '#0f172a', marginTop: 2 }}>
                {displayMetric(summary?.purchase_summary?.total, summaryLoading, summaryUnavailable ? 'Procurement source unavailable' : '')}
              </div>
            </div>
          </div>

          {summaryLoading || summaryUnavailable ? (
            <p className="management-panel-state">{summaryLoading ? 'Loading procurement decisions…' : 'Procurement data is unavailable for this source.'}</p>
          ) : (
            <div className="management-purchase-pills">
              <span className="management-purchase-pill">Pending: <strong>{summary?.purchase_summary?.pending_approval ?? 0}</strong></span>
              <span className="management-purchase-pill">Approved: <strong>{summary?.purchase_summary?.approved ?? 0}</strong></span>
              <span className="management-purchase-pill">Sent Back: <strong>{summary?.purchase_summary?.sent_back ?? 0}</strong></span>
              <span className="management-purchase-pill">Rejected: <strong>{summary?.purchase_summary?.rejected ?? 0}</strong></span>
              <span className="management-purchase-pill">Completed: <strong>{summary?.purchase_summary?.purchase_completed ?? 0}</strong></span>
            </div>
          )}

          {summaryLoading && <p className="management-panel-state">Loading pending approvals…</p>}
          {!summaryLoading && summaryUnavailable && <p className="management-panel-state">Approval queue is unavailable. <Link to="/management/approvals">Open Approval Centre</Link></p>}
          {!summaryLoading && !summaryUnavailable && summary?.approvals && summary.approvals.length > 0 && (
            <div style={{ display: 'grid', gap: 8, marginTop: 10 }}>
              {summary.approvals.slice(0, 2).map(req => (
                <div key={req.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px', borderRadius: 10, background: '#fffbeb', border: '1px solid #fef3c7' }}>
                  <div>
                    <strong style={{ fontSize: '0.8rem', display: 'block', color: '#92400e' }}>{req.code}: {req.title}</strong>
                    <small style={{ color: '#b45309' }}>{req.department} · {req.submitted_by || 'IT Staff'}</small>
                  </div>
                  <Link to="/management/approvals" className="management-hero-button" style={{ padding: '5px 12px', fontSize: '0.74rem' }}>
                    Decide Now
                  </Link>
                </div>
              ))}
            </div>
          )}
          {!summaryLoading && !summaryUnavailable && (!summary?.approvals || summary.approvals.length === 0) && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px', background: '#f0fdf4', borderRadius: 10, border: '1px solid #dcfce7', marginTop: 10 }}>
              <CheckCircle2 size={18} style={{ color: '#16a34a', flexShrink: 0 }} />
              <span style={{ fontSize: '0.78rem', color: '#166534' }}>No pending purchase approvals are currently listed.</span>
            </div>
          )}
        </article>
      </section>

      <section className="management-workspace-section" aria-labelledby="workspace-heading">
        <div className="management-section-heading">
          <div>
            <span className="section-kicker">ALL WORKSPACES</span>
            <h2 id="workspace-heading">Open a workspace</h2>
            <p>Every existing management destination is preserved in one compact directory.</p>
          </div>
          <span className="management-section-status">{workspaceGroups.reduce((count, group) => count + group.links.length, 0)} destinations</span>
        </div>
        <div className="management-workspace-groups">
          {workspaceGroups.map(group => {
            const GroupIcon = group.icon
            return (
              <div className="management-workspace-group" key={group.label}>
                <div className="management-workspace-group-title"><GroupIcon size={16} /><strong>{group.label}</strong></div>
                <div className="management-workspace-links">
                  {group.links.filter(link => !link.managementOnly || user?.role === 'management').map(link => (
                    <Link to={link.to} className="management-workspace-link" key={link.to}>
                      <span><strong>{link.label}</strong><small>{link.description}</small></span>
                      <ArrowRight size={15} />
                    </Link>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </section>

      {/* Password Change Dialog */}
      {showPasswordDialog && user?.role === 'management' && (
        <div
          className="management-password-overlay"
          role="presentation"
          onMouseDown={event => {
            if (event.target === event.currentTarget) closePasswordDialog()
          }}
        >
          <section className="management-password-dialog" role="dialog" aria-modal="true" aria-labelledby="management-password-title">
            <header>
              <div>
                <span>MANAGEMENT SECURITY</span>
                <h2 id="management-password-title">Change Password</h2>
                <p>Changing the password signs this Management account out of all active sessions.</p>
              </div>
              <button type="button" onClick={closePasswordDialog} aria-label="Close password dialog"><X size={20} /></button>
            </header>
            <form onSubmit={changePassword}>
              <label>
                <span>Current Password</span>
                <input
                  type="password"
                  value={currentPassword}
                  onChange={event => setCurrentPassword(event.target.value)}
                  autoComplete="current-password"
                  required
                  autoFocus
                />
              </label>
              <label>
                <span>New Password</span>
                <input
                  type="password"
                  value={newPassword}
                  onChange={event => setNewPassword(event.target.value)}
                  autoComplete="new-password"
                  minLength={10}
                  required
                />
              </label>
              <label>
                <span>Confirm New Password</span>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={event => setConfirmPassword(event.target.value)}
                  autoComplete="new-password"
                  minLength={10}
                  required
                />
              </label>
              <p className="management-password-rules">At least 10 characters with uppercase, lowercase, number, and special character.</p>
              {passwordError && <div className="error-message" role="alert">{passwordError}</div>}
              <div className="management-password-dialog-actions">
                <button type="button" onClick={closePasswordDialog} disabled={changingPassword}>Cancel</button>
                <button type="submit" disabled={changingPassword}>{changingPassword ? 'Changing...' : 'Change Password'}</button>
              </div>
            </form>
          </section>
        </div>
      )}
    </>
  )
}
