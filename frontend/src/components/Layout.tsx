import {
  ArrowLeft,
  ArrowRightLeft,
  BarChart3,
  Bell,
  Building2,
  Boxes,
  ChevronDown,
  ClipboardList,
  Code2,
  Database,
  FileCheck2,
  FileDown,
  FolderKanban,
  HardDrive,
  History,
  LayoutDashboard,
  LifeBuoy,
  MapPinned,
  MessageSquarePlus,
  Activity,
  LogOut,
  Menu,
  MonitorCheck,
  PackageCheck,
  PlaneTakeoff,
  Repeat2,
  SearchCheck,
  Settings,
  ShoppingCart,
  Sparkles,
  ShieldCheck,
  TrendingUp,
  UploadCloud,
  Users,
  X,
} from 'lucide-react'
import { DroneIcon as Drone, type AppIcon } from './DroneIcon'
import { useEffect, useState, type ReactNode } from 'react'
import { NavLink, Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useITMonth } from '../context/ITMonthContext'
import type { Role } from '../types'
import { Logo } from './Logo'
import { GlobalNotificationBell } from './GlobalNotificationBell'
import { GlobalSearch } from './GlobalSearch'
import { canAccessRole, isFullAccessRole, isTechnicalProjectManager, roleHomePath, TECHNICAL_PM_ROLES } from '../lib/roles'
import { monthLabel, withITMonth } from '../lib/itMonth'
import { apiFetch } from '../lib/api'

interface NavItem {
  to: string
  label: string
  icon: AppIcon
  roles: Role[]
  group: 'overview' | 'support' | 'management' | 'business' | 'ortho' | 'finance' | 'hr' | 'it' | 'drone' | 'system'
  managementGroup?: NavItem['group']
  managementLabel?: string
}

interface NavGroupDefinition {
  id: NavItem['group']
  label: string
}

const navGroups: NavGroupDefinition[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'support', label: 'Employee Support' },
  { id: 'management', label: 'Management' },
  { id: 'business', label: 'Business Development' },
  { id: 'ortho', label: 'Ortho' },
  { id: 'finance', label: 'Finance Department' },
  { id: 'hr', label: 'HR Department' },
  { id: 'it', label: 'IT Department' },
  { id: 'drone', label: 'Drone Department' },
  { id: 'system', label: 'System' },
]

const navItems: NavItem[] = [
  { to: '/support', label: 'Support Dashboard', icon: LifeBuoy, roles: ['employee'], group: 'support' },
  { to: '/support/new', label: 'Raise New Ticket', icon: MessageSquarePlus, roles: ['employee'], group: 'support' },
  { to: '/expenses/new', label: 'New Project Expense', icon: FileCheck2, roles: ['employee'], group: 'support' },
  { to: '/expenses', label: 'My Expense Claims', icon: ShoppingCart, roles: ['employee'], group: 'support' },
  { to: '/project-costs', label: 'Project Cost Entries', icon: FileCheck2, roles: ['employee'], group: 'support' },
  { to: '/travel-km/new', label: 'Start Travel / KM Claim', icon: MapPinned, roles: ['employee'], group: 'support' },
  { to: '/travel-km', label: 'My Travel / KM Claims', icon: MapPinned, roles: ['employee'], group: 'support' },
  { to: '/admin/travel-km', label: 'Travel KM Verification', icon: MapPinned, roles: ['admin'], group: 'management' },
  { to: '/hr/travel-km', label: 'Travel KM Verification', icon: MapPinned, roles: ['hr'], group: 'hr' },
  { to: '/finance/travel-km', label: 'Travel KM Payments', icon: MapPinned, roles: ['finance'], group: 'finance' },
  { to: '/management/travel-km', label: 'Employee Travel Oversight', icon: MapPinned, roles: ['management'], group: 'management' },
  { to: '/tickets', label: 'Support Tickets', icon: ClipboardList, roles: ['employee', 'it', 'drone', 'management', 'software_team'], group: 'support' },
  { to: '/software-team/agents', label: 'Agent Monitoring', icon: MonitorCheck, roles: ['software_team'], group: 'system' },
  { to: '/software-team/security', label: 'Users & Audit', icon: Activity, roles: ['software_team'], group: 'system' },
  { to: '/management/activity', label: 'Users & Activity', icon: Activity, roles: ['management'], group: 'system' },
  { to: '/software-team', label: 'Software Team Overview', icon: Code2, roles: ['software_team'], group: 'overview' },
  { to: '/admin', label: 'Admin Overview', icon: ShieldCheck, roles: ['admin'], group: 'overview' },
  { to: '/admin/client-master', label: 'Client Master (Admin Edit)', icon: Building2, roles: ['admin'], group: 'overview' },
  { to: '/management', label: 'Management Dashboard', icon: BarChart3, roles: ['admin', 'management'], group: 'management', managementGroup: 'overview' },
  { to: '/management/project-360', label: 'Project 360 (Feedback, Rework, Billing)', icon: FolderKanban, roles: ['admin', 'management'], group: 'management', managementGroup: 'overview' },
  { to: '/management/commercial', label: 'Commercial Analytics', icon: BarChart3, roles: ['admin', 'management'], group: 'management', managementGroup: 'overview' },
  { to: '/bd', label: 'BD Dashboard', icon: Building2, roles: ['bd', 'admin', 'management'], group: 'business' },
  { to: '/bd/clients', label: 'Client Management', icon: Building2, roles: ['bd', 'admin', 'management'], group: 'business' },
  { to: '/bd/projects', label: 'Project Management', icon: FolderKanban, roles: ['bd', 'admin', 'management'], group: 'business' },
  { to: '/bd/commercial', label: 'Commercial Estimates', icon: BarChart3, roles: ['bd', 'admin'], group: 'business' },
  { to: '/bd/feedback', label: 'Client Feedback', icon: FileCheck2, roles: ['bd', 'admin', 'management'], group: 'business' },
  { to: '/notifications', label: 'Notifications', icon: Bell, roles: ['bd', 'admin', 'management'], group: 'business' },
  { to: '/ortho', label: 'Project Operations', icon: FolderKanban, roles: [...TECHNICAL_PM_ROLES, 'employee', 'admin', 'management'], group: 'ortho' },
  // Pre-V8.1 technical-workflow pages. Kept in the codebase for Management/Admin/BIM and any other
  // authorized role, but no longer shown to the five technical PM roles, which now use the single
  // shared Project Operations dashboard above instead.
  { to: '/project-workstreams', label: 'Project Workstreams', icon: FolderKanban, roles: ['bim', 'admin', 'management'], group: 'overview' },
  { to: '/sample-requests', label: 'Sample Requests', icon: FolderKanban, roles: ['bim', 'admin', 'management'], group: 'overview' },
  { to: '/project-handovers', label: 'Data Handovers', icon: ArrowRightLeft, roles: ['bim', 'admin', 'management'], group: 'overview' },
  { to: '/project-monitoring', label: 'Project Monitoring', icon: BarChart3, roles: ['bim', 'admin', 'management'], group: 'overview' },
  { to: '/project-completion', label: 'Final Delivery & Closure', icon: FileCheck2, roles: ['bim', 'admin', 'management'], group: 'overview' },
  { to: '/technical-team-directory', label: 'Technical Team Directory', icon: Users, roles: ['admin', 'management', 'bim'], group: 'overview' },
  { to: '/reporting', label: 'Executive & Manager Reporting', icon: Users, roles: ['admin', 'management', 'bim'], group: 'overview' },
  { to: '/production-readiness', label: 'Production Readiness', icon: Users, roles: ['admin', 'management', 'software_team'], group: 'overview' },
  { to: '/finance', label: 'Finance Dashboard', icon: BarChart3, roles: ['finance', 'admin', 'management'], group: 'finance' },
  { to: '/finance/claims', label: 'Expense Claims & Approvals', icon: FileCheck2, roles: ['finance', 'admin', 'management'], group: 'finance' },
  { to: '/finance/clients', label: 'Client Register', icon: Building2, roles: ['finance', 'admin', 'management'], group: 'finance' },
  { to: '/finance/projects', label: 'Project Register', icon: FolderKanban, roles: ['finance', 'admin', 'management'], group: 'finance' },
  { to: '/finance/billing', label: 'Billing & Invoices', icon: FileCheck2, roles: ['finance', 'admin', 'management'], group: 'finance' },
  { to: '/finance/commercial', label: 'Commercial Control', icon: BarChart3, roles: ['finance', 'admin'], group: 'finance' },
  { to: '/finance/reports', label: 'Finance Reports & Excel', icon: FileDown, roles: ['finance', 'admin', 'management'], group: 'finance' },
  { to: '/business', label: 'Business & Total Sell', icon: TrendingUp, roles: ['finance', 'bd', 'management', 'admin', 'software_team', 'bim', ...TECHNICAL_PM_ROLES], group: 'business', managementGroup: 'overview' },
  { to: '/finance/sales', label: 'Sales', icon: TrendingUp, roles: ['finance', 'admin', 'management'], group: 'finance' },
  { to: '/finance/revenue', label: 'Revenue', icon: BarChart3, roles: ['finance', 'admin', 'management'], group: 'finance' },
  { to: '/finance/command-center', label: 'Finance Command Center', icon: BarChart3, roles: ['finance', 'admin', 'management', ...TECHNICAL_PM_ROLES], group: 'finance' },
  { to: '/it', label: 'IT Dashboard', icon: LayoutDashboard, roles: ['admin', 'management', 'it'], group: 'it' },
  { to: '/assets', label: 'Asset Register', icon: HardDrive, roles: ['admin', 'management', 'it'], group: 'it' },
  { to: '/work', label: 'IT Work Records', icon: ClipboardList, roles: ['admin', 'management', 'it'], group: 'it' },
  { to: '/replacements', label: 'Component Changes', icon: Repeat2, roles: ['admin', 'management', 'it'], group: 'it' },
  { to: '/it/handover-return', label: 'Handover & Return', icon: ArrowRightLeft, roles: ['admin', 'management', 'it'], group: 'it' },
  { to: '/it/rental-returns', label: 'Returned Assets & Spares', icon: PackageCheck, roles: ['admin', 'management', 'it'], group: 'it' },
  { to: '/it/purchase-requests', label: 'Purchase Requests', icon: FileCheck2, roles: ['admin', 'management', 'it'], group: 'it', managementGroup: 'management', managementLabel: 'Purchase Order Approval' },
  { to: '/it/purchases', label: 'Purchase & Procurement', icon: ShoppingCart, roles: ['admin', 'management', 'it'], group: 'it', managementGroup: 'management' },
  { to: '/it/recent-changes', label: 'Recent Changes', icon: History, roles: ['admin', 'management', 'it'], group: 'it' },
  { to: '/data-quality', label: 'Data Quality Centre', icon: SearchCheck, roles: ['software_team', 'management', 'it'], group: 'it' },
  { to: '/reports', label: 'IT Excel & Reports', icon: FileDown, roles: ['admin', 'management', 'it'], group: 'it' },
  { to: '/naksha-copilot', label: 'Naksha Copilot', icon: Sparkles, roles: ['software_team', 'management', 'it'], group: 'it' },
  { to: '/drone', label: 'Drone Dashboard', icon: Drone, roles: ['admin', 'management', 'drone'], group: 'drone' },
  { to: '/drone/assets', label: 'Drone Assets', icon: Boxes, roles: ['admin', 'management', 'drone'], group: 'drone' },
  { to: '/drone/kits', label: 'Drone Kits', icon: PackageCheck, roles: ['admin', 'management', 'drone'], group: 'drone' },
  { to: '/drone/projects', label: 'Drone Projects', icon: FolderKanban, roles: ['admin', 'management', 'drone'], group: 'drone' },
  { to: '/drone/operations', label: 'Drone Operations', icon: PlaneTakeoff, roles: ['admin', 'management', 'drone'], group: 'drone' },
  { to: '/drone/work-records', label: 'Drone Work Records', icon: ClipboardList, roles: ['admin', 'management', 'drone'], group: 'drone' },
  { to: '/drone/movements', label: 'Movement History', icon: ArrowRightLeft, roles: ['admin', 'management', 'drone'], group: 'drone' },
  { to: '/drone/import', label: 'Drone Import', icon: UploadCloud, roles: ['admin'], group: 'drone' },
  { to: '/backups', label: 'Backups & History', icon: Database, roles: ['admin', 'management', 'it', 'drone'], group: 'system' },
  { to: '/future', label: 'Future Modules', icon: Settings, roles: ['admin'], group: 'system' },
]

function isPathInItem(pathname: string, item: NavItem): boolean {
  if (item.to === '/drone') return pathname === '/drone'
  if (item.to === '/finance') return pathname === '/finance'
  if (item.to === '/bd') return pathname === '/bd'
  if (item.to === '/ortho') return pathname === '/ortho'
  if (item.to === '/expenses') return pathname === '/expenses'
  if (item.to === '/it') return pathname === '/it'
  if (item.to === '/admin') return pathname === '/admin'
  if (item.to === '/software-team') return pathname === '/software-team'
  return pathname === item.to || pathname.startsWith(`${item.to}/`)
}

function canViewItem(role: Role, item: NavItem): boolean {
  // Keep the two full-access home pages separate while sharing all Admin permissions elsewhere.
  if (item.to === '/software-team') return role === 'software_team'
  if (item.to === '/admin') return role === 'admin'
  // New department modules use exact-role access. Do not inherit the legacy Software Team -> Admin elevation.
  if (item.to.startsWith('/bd') || item.to === '/notifications' || item.to === '/ortho' || item.to === '/project-workstreams' || item.to === '/sample-requests' || item.to === '/project-handovers' || item.to === '/project-monitoring' || item.to === '/project-completion' || item.to === '/technical-team-directory' || item.to === '/reporting' || item.to === '/production-readiness') return item.roles.includes(role)
  return canAccessRole(role, item.roles)
}

function navigationGroupForItem(role: Role, item: NavItem): NavItem['group'] {
  return role === 'management' && item.managementGroup ? item.managementGroup : item.group
}

function navigationLabelForItem(role: Role, item: NavItem): string {
  return role === 'management' && item.managementLabel ? item.managementLabel : item.label
}

export function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()
  const { selectedMonth } = useITMonth()
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()
  // The account card in the sidebar footer can be collapsed by the user; the choice is remembered
  // per browser so people who only want the nav are not forced to look at it.
  const [footerOpen, setFooterOpen] = useState(() => {
    try { return window.localStorage.getItem('naksha.sidebarAccount') !== 'collapsed' } catch { return true }
  })

  function toggleFooterOpen() {
    setFooterOpen(current => {
      const next = !current
      try { window.localStorage.setItem('naksha.sidebarAccount', next ? 'open' : 'collapsed') } catch { /* storage blocked: preference simply is not remembered */ }
      return next
    })
  }
  const [openGroups, setOpenGroups] = useState<Record<NavItem['group'], boolean>>({
    overview: true,
    management: false,
    business: true,
    ortho: true,
    finance: true,
    hr: true,
    it: false,
    drone: false,
    support: true,
    system: false,
  })

  useEffect(() => {
    if (!user || (!isFullAccessRole(user.role) && user.role !== 'management')) return
    const activeItem = navItems.find(item => canViewItem(user.role, item) && isPathInItem(location.pathname, item))
    if (activeItem) {
      const activeGroup = navigationGroupForItem(user.role, activeItem)
      setOpenGroups(current => ({ ...current, [activeGroup]: true }))
    }
  }, [location.pathname, user])

  useEffect(() => {
    if (!user) return
    void apiFetch('/audit/page-view', {
      method: 'POST',
      body: JSON.stringify({ path: location.pathname, title: document.title }),
    }).catch(() => undefined)
  }, [location.pathname, user])

  if (!user) return null
  const currentUser = user

  const visibleItems = navItems.filter(item => canViewItem(currentUser.role, item))

  const available = currentUser.role === 'it'
    ? [
        ...visibleItems.filter(item => item.to !== '/tickets'),
        ...visibleItems.filter(item => item.to === '/tickets'),
      ]
    : visibleItems
  const groupedNavigation = isFullAccessRole(currentUser.role) || currentUser.role === 'management'

  // Only surface topbar context that is not already stated elsewhere on screen. The department
  // workspace labels were a third repeat of the sidebar footer role, so they are not shown here.
  const workspaceContext =
    currentUser.role === 'employee' ? `Branch: ${currentUser.selected_branch_name || currentUser.branch}`
      : currentUser.role === 'it' ? `IT reporting month: ${monthLabel(selectedMonth)}`
        : location.pathname.includes('/travel-km') ? 'Employee travel & KM workflow'
          : null

  function renderNavItem(item: NavItem) {
    const Icon = item.icon
    return (
      <NavLink
        key={item.to}
        to={item.group === 'it' ? withITMonth(item.to, selectedMonth) : item.to}
        onClick={() => setMobileOpen(false)}
        className={() => isPathInItem(location.pathname, item) ? 'active' : ''}
      >
        <Icon size={18} />
        <span>{navigationLabelForItem(currentUser.role, item)}</span>
      </NavLink>
    )
  }

  return (
    <div className="app-shell">
      <button className="mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Open menu"><Menu /></button>
      <aside className={`sidebar ${mobileOpen ? 'open' : ''}`}>
        <button className="mobile-close" onClick={() => setMobileOpen(false)} aria-label="Close menu"><X /></button>
        <Logo inverse compact />
        <div className="sidebar-title">
          <strong>Asset Management</strong>
          <span>Unified operations platform</span>
        </div>
        <span className="sidebar-section-label">Asset Operations</span>
        <nav className={groupedNavigation ? 'grouped-navigation' : ''}>
          {groupedNavigation
            ? navGroups.map(group => {
                const items = available.filter(item => navigationGroupForItem(currentUser.role, item) === group.id)
                if (items.length === 0) return null
                const isOpen = openGroups[group.id]
                return (
                  <section className={`sidebar-nav-group ${isOpen ? 'open' : ''}`} key={group.id}>
                    <button
                      type="button"
                      className="sidebar-group-toggle"
                      onClick={() => setOpenGroups(current => ({ ...current, [group.id]: !current[group.id] }))}
                      aria-expanded={isOpen}
                    >
                      <span>{group.label}</span>
                      <ChevronDown size={16} aria-hidden="true" />
                    </button>
                    {isOpen && <div className="sidebar-group-items">{items.map(renderNavItem)}</div>}
                  </section>
                )
              })
            : available.map(renderNavItem)}
        </nav>
        <div className="sidebar-footer">
          <button
            type="button"
            className="sidebar-footer-toggle"
            onClick={toggleFooterOpen}
            aria-expanded={footerOpen}
            aria-controls="sidebar-account-card"
          >
            <span>My account</span>
            <ChevronDown size={15} aria-hidden="true" className={footerOpen ? 'open' : ''} />
          </button>
          {footerOpen && <NavLink id="sidebar-account-card" className="sidebar-department-card" to="/profile" onClick={() => setMobileOpen(false)} title="Open your profile">
            <div className="user-avatar">{currentUser.full_name.charAt(0)}</div>
            <div>
              <strong>{currentUser.full_name}</strong>
              <span>{currentUser.designation || currentUser.branch || 'Head Office'}</span>
            </div>
          </NavLink>}
          <button className="ghost-button" onClick={logout}><LogOut size={17} /> Logout</button>
        </div>
      </aside>
      {mobileOpen && <button className="sidebar-backdrop" onClick={() => setMobileOpen(false)} aria-label="Close menu" />}
      <main className="main-content" key={location.pathname}>
        <div className="topbar">
          <div className="topbar-left">
            <button
              type="button"
              className="topbar-back"
              onClick={() => { if (window.history.length > 1) navigate(-1); else navigate(roleHomePath(currentUser.role)) }}
              aria-label="Go back to the previous page"
              title="Back"
            >
              <ArrowLeft size={17} aria-hidden="true" />
              <span>Back</span>
            </button>
            <div className="topbar-status"><span className="system-indicator" /><span>System online</span></div>
          </div>
          <div className="topbar-right">
            {['bd', 'management', 'admin'].includes(currentUser.role) && <GlobalSearch />}
            <GlobalNotificationBell />
            {workspaceContext && <div className="topbar-actions">
              <span className="topbar-context"><PackageCheck size={17} />{workspaceContext}</span>
            </div>}
          </div>
        </div>
        <div className="internal-page-content">{children}</div>
      </main>
    </div>
  )
}
