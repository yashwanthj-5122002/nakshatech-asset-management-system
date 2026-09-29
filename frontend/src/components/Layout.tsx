import {
  ArrowLeft,
  ArrowRightLeft,
  BarChart3,
  Bell,
  Building2,
  Boxes,
  ChevronDown,
  ClipboardCheck,
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
  UserRound,
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
  group: string
  managementGroup?: 'executive' | 'operations' | 'finance' | 'governance'
  managementLabel?: string
}

interface NavGroupDefinition {
  id: string
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

const managementNavGroups: NavGroupDefinition[] = [
  { id: 'executive', label: 'Executive Suite' },
  { id: 'operations', label: 'Operations & Fleet' },
  { id: 'finance', label: 'Finance & Revenue' },
  { id: 'governance', label: 'Governance & Audit' },
]

const adminNavGroups: NavGroupDefinition[] = [
  { id: 'executive', label: 'Executive Suite' },
  { id: 'operations', label: 'Operations & Fleet' },
  { id: 'finance', label: 'Finance & Revenue' },
  { id: 'governance', label: 'Governance & Audit' },
  { id: 'admin', label: 'System Administration' },
]

const navItems: NavItem[] = [
  { to: '/support', label: 'Support Dashboard', icon: LifeBuoy, roles: ['employee'], group: 'support' },
  { to: '/support/new', label: 'Raise New Ticket', icon: MessageSquarePlus, roles: ['employee'], group: 'support' },
  { to: '/expenses/new', label: 'New Project Expense', icon: FileCheck2, roles: ['employee'], group: 'support' },
  { to: '/expenses', label: 'My Expense Claims', icon: ShoppingCart, roles: ['employee'], group: 'support' },
  { to: '/project-costs', label: 'Project Cost Entries', icon: FileCheck2, roles: ['employee'], group: 'support' },
  { to: '/travel-km/new', label: 'Start Travel / KM Claim', icon: MapPinned, roles: ['employee'], group: 'support' },
  { to: '/travel-km', label: 'My Travel / KM Claims', icon: MapPinned, roles: ['employee'], group: 'support' },
  { to: '/admin/travel-km', label: 'Travel KM Verification', icon: MapPinned, roles: ['admin'], group: 'management', managementGroup: 'governance', managementLabel: 'Travel KM Verification' },
  { to: '/hr/travel-km', label: 'Travel KM Verification', icon: MapPinned, roles: ['hr'], group: 'hr' },
  { to: '/finance/travel-km', label: 'Travel KM Payments', icon: MapPinned, roles: ['finance'], group: 'finance' },
  { to: '/management/travel-km', label: 'Employee Travel Oversight', icon: MapPinned, roles: ['management'], group: 'management', managementGroup: 'governance', managementLabel: 'Employee Travel' },
  { to: '/tickets', label: 'Support Tickets', icon: ClipboardList, roles: ['employee', 'it', 'drone', 'management', 'software_team'], group: 'support', managementGroup: 'operations', managementLabel: 'Support Tickets & SLA' },
  { to: '/software-team/agents', label: 'Agent Monitoring', icon: MonitorCheck, roles: ['software_team'], group: 'system' },
  { to: '/software-team/security', label: 'Users & Audit', icon: Activity, roles: ['software_team'], group: 'system' },
  { to: '/management/activity', label: 'Users & Activity', icon: Activity, roles: ['management'], group: 'system', managementGroup: 'governance', managementLabel: 'Users & Audit Trail' },
  { to: '/software-team', label: 'Software Team Overview', icon: Code2, roles: ['software_team'], group: 'overview' },
  { to: '/admin', label: 'Admin Overview', icon: ShieldCheck, roles: ['admin'], group: 'overview', managementLabel: 'Admin Overview' },
  { to: '/software-team/security', label: 'Software Security', icon: ShieldCheck, roles: ['software_team'], group: 'overview' },
  { to: '/software-team/employee-master', label: 'Employee Master', icon: Users, roles: ['software_team', 'admin'], group: 'overview' },
  { to: '/management/employee-master', label: 'Employee Data Control', icon: Users, roles: ['management'], group: 'management', managementGroup: 'governance', managementLabel: 'Employee Data Control' },
  { to: '/onboarding', label: 'New Joiner Onboarding', icon: UserRound, roles: ['hr', 'it', 'management', 'software_team', 'admin'], group: 'overview', managementGroup: 'executive', managementLabel: 'New Joiner Onboarding' },
  { to: '/admin/client-master', label: 'Client Master (Admin Edit)', icon: Building2, roles: ['admin'], group: 'overview', managementLabel: 'Client Master' },
  { to: '/management', label: 'Management Dashboard', icon: BarChart3, roles: ['admin', 'management'], group: 'management', managementGroup: 'executive', managementLabel: 'Dashboard' },
  { to: '/management/approvals', label: 'Purchase Approval Centre', icon: ClipboardCheck, roles: ['admin', 'management'], group: 'management', managementGroup: 'executive', managementLabel: 'Purchase Approvals' },
  { to: '/management/project-360', label: 'Project 360', icon: FolderKanban, roles: ['admin', 'management'], group: 'management', managementGroup: 'executive', managementLabel: 'Project 360' },
  { to: '/management/commercial', label: 'Commercial Analytics', icon: BarChart3, roles: ['admin', 'management'], group: 'management', managementGroup: 'executive', managementLabel: 'Commercial Analytics' },
  { to: '/bd', label: 'BD Dashboard', icon: Building2, roles: ['bd', 'admin', 'management'], group: 'business' },
  { to: '/bd/clients', label: 'Client Management', icon: Building2, roles: ['bd', 'admin', 'management'], group: 'business' },
  { to: '/bd/projects', label: 'Project Management', icon: FolderKanban, roles: ['bd', 'admin', 'management'], group: 'business' },
  { to: '/bd/commercial', label: 'Commercial Estimates', icon: BarChart3, roles: ['bd', 'admin', 'management'], group: 'business', managementGroup: 'finance', managementLabel: 'Commercial Estimates' },
  { to: '/bd/feedback', label: 'Client Feedback', icon: FileCheck2, roles: ['bd', 'admin', 'management'], group: 'business' },
  { to: '/notifications', label: 'Notifications', icon: Bell, roles: ['bd', 'admin', 'management'], group: 'business' },
  { to: '/ortho', label: 'Project Operations', icon: FolderKanban, roles: [...TECHNICAL_PM_ROLES, 'employee', 'admin', 'management'], group: 'ortho' },
  { to: '/finance', label: 'Finance Dashboard', icon: BarChart3, roles: ['finance', 'admin', 'management'], group: 'finance', managementGroup: 'finance', managementLabel: 'Finance Dashboard' },
  { to: '/finance/claims', label: 'Expense Claims & Approvals', icon: FileCheck2, roles: ['finance', 'admin', 'management'], group: 'finance' },
  { to: '/finance/clients', label: 'Client Register', icon: Building2, roles: ['finance', 'admin', 'management'], group: 'finance' },
  { to: '/finance/projects', label: 'Project Register', icon: FolderKanban, roles: ['finance', 'admin', 'management'], group: 'finance', managementGroup: 'finance', managementLabel: 'Project Register' },
  { to: '/finance/billing', label: 'Billing & Invoices', icon: FileCheck2, roles: ['finance', 'admin', 'management'], group: 'finance', managementGroup: 'finance', managementLabel: 'Billing & Invoices' },
  { to: '/finance/commercial', label: 'Commercial Control', icon: BarChart3, roles: ['finance', 'admin', 'management'], group: 'finance', managementGroup: 'finance', managementLabel: 'Commercial Control' },
  { to: '/finance/reports', label: 'Finance Reports & Excel', icon: FileDown, roles: ['finance', 'admin', 'management'], group: 'finance' },
  { to: '/business', label: 'Business & Total Sell', icon: TrendingUp, roles: ['finance', 'bd', 'management', 'admin', 'software_team', 'bim', ...TECHNICAL_PM_ROLES], group: 'business', managementGroup: 'executive', managementLabel: 'Business & Total Sell' },
  { to: '/finance/sales', label: 'Sales', icon: TrendingUp, roles: ['finance', 'admin', 'management'], group: 'finance', managementGroup: 'finance', managementLabel: 'Sales Pipeline' },
  { to: '/finance/revenue', label: 'Revenue', icon: BarChart3, roles: ['finance', 'admin', 'management'], group: 'finance', managementGroup: 'finance', managementLabel: 'Revenue' },
  { to: '/finance/command-center', label: 'Finance Command Center', icon: BarChart3, roles: ['finance', 'admin', 'management', ...TECHNICAL_PM_ROLES], group: 'finance', managementGroup: 'finance', managementLabel: 'Finance Command Center' },
  { to: '/it', label: 'IT Dashboard', icon: LayoutDashboard, roles: ['admin', 'management', 'it'], group: 'it', managementGroup: 'operations', managementLabel: 'IT Infrastructure' },
  { to: '/assets', label: 'Asset Register', icon: HardDrive, roles: ['admin', 'management', 'it'], group: 'it', managementGroup: 'operations', managementLabel: 'Asset Register' },
  { to: '/work', label: 'IT Work Records', icon: ClipboardList, roles: ['admin', 'management', 'it'], group: 'it' },
  { to: '/replacements', label: 'Component Changes', icon: Repeat2, roles: ['admin', 'management', 'it'], group: 'it' },
  { to: '/it/handover-return', label: 'Handover & Return', icon: ArrowRightLeft, roles: ['admin', 'management', 'it'], group: 'it' },
  { to: '/it/rental-returns', label: 'Returned Assets & Spares', icon: PackageCheck, roles: ['admin', 'management', 'it'], group: 'it' },
  { to: '/it/purchase-requests', label: 'Purchase Requests', icon: FileCheck2, roles: ['admin', 'management', 'it'], group: 'it' },
  { to: '/it/purchases', label: 'Purchase & Procurement', icon: ShoppingCart, roles: ['admin', 'management', 'it'], group: 'it' },
  { to: '/it/recent-changes', label: 'Recent Changes', icon: History, roles: ['admin', 'management', 'it'], group: 'it' },
  { to: '/data-quality', label: 'Data Quality Centre', icon: SearchCheck, roles: ['software_team', 'management', 'it'], group: 'it' },
  { to: '/reports', label: 'IT Excel & Reports', icon: FileDown, roles: ['admin', 'management', 'it'], group: 'it', managementGroup: 'governance', managementLabel: 'Executive Reports' },
  { to: '/naksha-copilot', label: 'Naksha Copilot', icon: Sparkles, roles: ['software_team', 'management', 'it'], group: 'it' },
  { to: '/drone', label: 'Drone Dashboard', icon: Drone, roles: ['admin', 'management', 'drone'], group: 'drone', managementGroup: 'operations', managementLabel: 'Drone Fleet' },
  { to: '/drone/assets', label: 'Drone Assets', icon: Boxes, roles: ['admin', 'management', 'drone'], group: 'drone' },
  { to: '/drone/kits', label: 'Drone Kits', icon: PackageCheck, roles: ['admin', 'management', 'drone'], group: 'drone' },
  { to: '/drone/projects', label: 'Drone Projects', icon: FolderKanban, roles: ['admin', 'management', 'drone'], group: 'drone' },
  { to: '/drone/operations', label: 'Drone Operations', icon: PlaneTakeoff, roles: ['admin', 'management', 'drone'], group: 'drone' },
  { to: '/drone/work-records', label: 'Drone Work Records', icon: ClipboardList, roles: ['admin', 'management', 'drone'], group: 'drone' },
  { to: '/drone/movements', label: 'Movement History', icon: ArrowRightLeft, roles: ['admin', 'management', 'drone'], group: 'drone' },
  { to: '/drone/import', label: 'Drone Import', icon: UploadCloud, roles: ['admin'], group: 'drone' },
  { to: '/backups', label: 'Backups & History', icon: Database, roles: ['admin', 'management', 'it', 'drone'], group: 'system', managementGroup: 'governance', managementLabel: 'System Backups' },
  { to: '/future', label: 'Future Modules', icon: Settings, roles: ['admin'], group: 'system', managementLabel: 'System Settings & Future' },
]

function isPathInItem(pathname: string, item: NavItem): boolean {
  if (item.to === '/management') return pathname === '/management'
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
  if (item.to === '/software-team') return role === 'software_team'
  if (item.to === '/admin') return role === 'admin'
  if (item.to.startsWith('/bd') || item.to === '/notifications' || item.to === '/ortho') return item.roles.includes(role)
  return canAccessRole(role, item.roles)
}

const ADMIN_SIDEBAR_PATHS = ['/admin', '/admin/client-master', '/future', '/software-team/employee-master']

/** Sidebar must never advertise a link the route guard will bounce back to the role home. */
function canShowInSidebar(role: Role, item: NavItem): boolean {
  if (role === 'management' || role === 'admin') {
    const inManagementSuite = Boolean(item.managementGroup) || (role === 'admin' && ADMIN_SIDEBAR_PATHS.includes(item.to))
    return inManagementSuite && canViewItem(role, item)
  }
  return canViewItem(role, item)
}

function navigationGroupForItem(role: Role, item: NavItem): string {
  if (role === 'management' || role === 'admin') {
    if (item.managementGroup) return item.managementGroup
    if (role === 'admin') return 'admin'
  }
  return item.group
}

function navigationLabelForItem(role: Role, item: NavItem): string {
  if ((role === 'management' || role === 'admin') && item.managementLabel) {
    return item.managementLabel
  }
  return item.label
}

/** Visual-only department accent key for the design system (no access changes). */
function deptAccentForRole(role: Role): string {
  switch (role) {
    case 'finance': return 'finance'
    case 'hr': return 'hr'
    case 'it': return 'it'
    case 'drone': return 'drone'
    case 'ortho': return 'ortho'
    case 'lidar': return 'lidar'
    case 'mobile_mapping': return 'mobile_mapping'
    case 'laser_scanning': return 'laser_scanning'
    case 'civil': return 'civil'
    case 'management': return 'management'
    case 'bd': return 'bd'
    case 'bim': return 'bim'
    case 'employee': return 'employee'
    case 'admin': return 'admin'
    case 'software_team': return 'software_team'
    default: return 'finance'
  }
}

/**
 * Visual workspace identity follows the page being viewed, not only the
 * signed-in role. This keeps cross-department Admin/Management views themed
 * like the department they are inspecting without changing access rules.
 */
function deptAccentForWorkspace(pathname: string, role: Role): string {
  if (pathname === '/finance/sales') return 'sales'
  if (pathname === '/finance/revenue') return 'revenue'
  if (pathname === '/finance' || pathname.startsWith('/finance/')) return 'finance'
  if (pathname === '/bd' || pathname.startsWith('/bd/')) return 'bd'
  if (pathname === '/ortho' || pathname.startsWith('/ortho/')) {
    return TECHNICAL_PM_ROLES.includes(role) ? deptAccentForRole(role) : 'ortho'
  }
  if (pathname === '/drone' || pathname.startsWith('/drone/')) return 'drone'
  if (pathname === '/it' || pathname.startsWith('/it/')) return 'it'
  // IT register + IT workbenches share the IT technology theme
  if (['/assets', '/work', '/replacements', '/data-quality'].some(p => pathname === p || pathname.startsWith(`${p}/`))) return 'it'
  if (['/it/handover-return', '/it/rental-returns', '/it/purchase-requests', '/it/purchases'].some(p => pathname === p || pathname.startsWith(`${p}/`))) return 'it'
  if (pathname === '/management' || pathname.startsWith('/management/')) return 'management'
  if (pathname === '/admin' || pathname.startsWith('/admin/')) return 'admin'
  if (pathname === '/software-team' || pathname.startsWith('/software-team/')) return 'software_team'
  // Management-owned intelligence pages keep the executive theme
  if (pathname === '/reporting' || pathname.startsWith('/reporting/') || pathname === '/business' || pathname.startsWith('/business/')) return 'management'
  // People / process theme for HR travel workspaces and the employee portal
  if (pathname === '/travel-km' || pathname.startsWith('/travel-km/') || pathname.startsWith('/portal/') || pathname.startsWith('/agent-monitor')) return 'hr'
  if (pathname.startsWith('/commercial') || pathname.endsWith('/commercial')) return 'commercial'
  return deptAccentForRole(role)
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
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {}
    const currentRole = user?.role
    const targetGroups = currentRole === 'management' ? managementNavGroups : currentRole === 'admin' ? adminNavGroups : navGroups
    targetGroups.forEach(g => { initial[g.id] = false })
    if (currentRole) {
      const activeItem = navItems.find(item => canShowInSidebar(currentRole, item) && isPathInItem(location.pathname, item))
      if (activeItem) {
        const activeGroup = navigationGroupForItem(currentRole, activeItem)
        initial[activeGroup] = true
        return initial
      }
    }
    initial[targetGroups[0]?.id || 'executive'] = true
    return initial
  })

  useEffect(() => {
    if (!user || (!isFullAccessRole(user.role) && user.role !== 'management')) return
    const activeItem = navItems.find(item => canShowInSidebar(user.role, item) && isPathInItem(location.pathname, item))
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

  useEffect(() => {
    if ('scrollRestoration' in window.history) window.history.scrollRestoration = 'manual'
    window.scrollTo({ top: 0, left: 0 })
  }, [location.pathname])

  if (!user) return null
  const currentUser = user
  const isManagement = currentUser.role === 'management'
  const isAdmin = currentUser.role === 'admin'
  const activeNavGroups = isManagement ? managementNavGroups : isAdmin ? adminNavGroups : navGroups

  const visibleItems = navItems.filter(item => canShowInSidebar(currentUser.role, item))

  const available = currentUser.role === 'it'
    ? [
        ...visibleItems.filter(item => item.to !== '/tickets'),
        ...visibleItems.filter(item => item.to === '/tickets'),
      ]
    : visibleItems
  const groupedNavigation = isFullAccessRole(currentUser.role) || isManagement

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
    <div className="app-shell" data-dept={deptAccentForWorkspace(location.pathname, currentUser.role)}>
      <button className="mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Open menu"><Menu /></button>
      <aside className={`sidebar ${mobileOpen ? 'open' : ''}`}>
        <button className="mobile-close" onClick={() => setMobileOpen(false)} aria-label="Close menu"><X /></button>
        <Logo inverse compact />
        <div className="sidebar-title">
          <strong>NakshaTech ERP</strong>
          <span>Inspiring geospatial standards</span>
        </div>
        <span className="sidebar-section-label">
          {isManagement || location.pathname.startsWith('/management')
            ? 'Management Suite'
            : isAdmin
            ? 'Unified Operations & Admin'
            : 'Asset Operations'}
        </span>
        <nav className={groupedNavigation ? 'grouped-navigation' : ''}>
          {groupedNavigation
            ? activeNavGroups.map(group => {
                const items = available.filter(item => navigationGroupForItem(currentUser.role, item) === group.id)
                if (items.length === 0) return null
                const isOpen = openGroups[group.id]
                const hasActive = items.some(item => isPathInItem(location.pathname, item))
                return (
                  <section className={`sidebar-nav-group ${isOpen ? 'open' : ''} ${hasActive ? 'has-active' : ''}`} key={group.id}>
                    <button
                      type="button"
                      className="sidebar-group-toggle"
                      onClick={() => setOpenGroups(current => ({ ...current, [group.id]: !current[group.id] }))}
                      aria-expanded={isOpen}
                    >
                      <span>{group.label}</span>
                      <div className="sidebar-group-meta">
                        <span className="sidebar-group-count">{items.length}</span>
                        <ChevronDown size={14} aria-hidden="true" />
                      </div>
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
