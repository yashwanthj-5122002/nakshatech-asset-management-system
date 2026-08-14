import {
  ArrowRightLeft,
  BarChart3,
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
  UploadCloud,
  Users,
  X,
} from 'lucide-react'
import { DroneIcon as Drone, type AppIcon } from './DroneIcon'
import { useEffect, useState, type ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useITMonth } from '../context/ITMonthContext'
import type { Role } from '../types'
import { Logo } from './Logo'
import { GlobalNotificationBell } from './GlobalNotificationBell'
import { canAccessRole, isFullAccessRole, roleDisplayName } from '../lib/roles'
import { monthLabel, withITMonth } from '../lib/itMonth'
import { apiFetch } from '../lib/api'

interface NavItem {
  to: string
  label: string
  icon: AppIcon
  roles: Role[]
  group: 'overview' | 'support' | 'management' | 'it' | 'drone' | 'system'
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
  { id: 'it', label: 'IT Department' },
  { id: 'drone', label: 'Drone Department' },
  { id: 'system', label: 'System' },
]

const navItems: NavItem[] = [
  { to: '/support', label: 'Support Dashboard', icon: LifeBuoy, roles: ['employee'], group: 'support' },
  { to: '/support/new', label: 'Raise New Ticket', icon: MessageSquarePlus, roles: ['employee'], group: 'support' },
  { to: '/tickets', label: 'Support Tickets', icon: ClipboardList, roles: ['employee', 'it', 'drone', 'management', 'software_team'], group: 'support' },
  { to: '/software-team/agents', label: 'Agent Monitoring', icon: MonitorCheck, roles: ['software_team'], group: 'system' },
  { to: '/software-team/security', label: 'Users & Audit', icon: Activity, roles: ['software_team'], group: 'system' },
  { to: '/management/activity', label: 'Users & Activity', icon: Activity, roles: ['management'], group: 'system' },
  { to: '/software-team', label: 'Software Team Overview', icon: Code2, roles: ['software_team'], group: 'overview' },
  { to: '/admin', label: 'Admin Overview', icon: ShieldCheck, roles: ['admin'], group: 'overview' },
  { to: '/management', label: 'Management Dashboard', icon: BarChart3, roles: ['admin', 'management'], group: 'management', managementGroup: 'overview' },
  { to: '/it', label: 'IT Dashboard', icon: LayoutDashboard, roles: ['admin', 'management', 'it'], group: 'it' },
  { to: '/assets', label: 'Asset Register', icon: HardDrive, roles: ['admin', 'management', 'it'], group: 'it' },
  { to: '/work', label: 'IT Work Records', icon: ClipboardList, roles: ['admin', 'management', 'it'], group: 'it' },
  { to: '/replacements', label: 'Component Changes', icon: Repeat2, roles: ['admin', 'management', 'it'], group: 'it' },
  { to: '/it/handover-return', label: 'Handover & Return', icon: ArrowRightLeft, roles: ['admin', 'management', 'it'], group: 'it' },
  { to: '/it/rental-returns', label: 'Rental Returns & Spares', icon: PackageCheck, roles: ['admin', 'management', 'it'], group: 'it' },
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

const roleLabels: Record<Role, { name: string; subtitle: string }> = {
  software_team: { name: 'Software Team', subtitle: 'Full technical access' },
  admin: { name: 'Admin Workspace', subtitle: 'Organization administration' },
  management: { name: 'Management', subtitle: 'Oversight & approvals' },
  it: { name: 'IT Department', subtitle: 'Head Office' },
  drone: { name: 'Drone Department', subtitle: 'Survey operations' },
  employee: { name: 'Employee Support', subtitle: 'Organization ticket access' },
}

function isPathInItem(pathname: string, item: NavItem): boolean {
  if (item.to === '/drone') return pathname === '/drone'
  if (item.to === '/it') return pathname === '/it'
  if (item.to === '/admin') return pathname === '/admin'
  if (item.to === '/software-team') return pathname === '/software-team'
  return pathname === item.to || pathname.startsWith(`${item.to}/`)
}

function canViewItem(role: Role, item: NavItem): boolean {
  // Keep the two full-access home pages separate while sharing all Admin permissions elsewhere.
  if (item.to === '/software-team') return role === 'software_team'
  if (item.to === '/admin') return role === 'admin'
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
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()
  const [openGroups, setOpenGroups] = useState<Record<NavItem['group'], boolean>>({
    overview: true,
    management: false,
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
  const roleMeta = roleLabels[currentUser.role]
  const groupedNavigation = isFullAccessRole(currentUser.role) || currentUser.role === 'management'

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
          <div className="sidebar-department-card">
            <div className="user-avatar">{currentUser.full_name.charAt(0)}</div>
            <div>
              <small>{roleMeta.name}</small>
              <strong>{currentUser.full_name}</strong>
              <span>{roleMeta.subtitle} · {currentUser.branch}</span>
            </div>
          </div>
          <button className="ghost-button" onClick={logout}><LogOut size={17} /> Logout</button>
        </div>
      </aside>
      {mobileOpen && <button className="sidebar-backdrop" onClick={() => setMobileOpen(false)} aria-label="Close menu" />}
      <main className="main-content" key={location.pathname}>
        <div className="topbar">
          <div className="topbar-status"><span className="system-indicator" /><span>System online</span></div>
          <div className="topbar-right">
            <GlobalNotificationBell />
            <div className="topbar-actions">
              <span className="topbar-context"><PackageCheck size={17} />{currentUser.role === 'drone' ? 'Drone operations workspace' : currentUser.role === 'employee' ? `Branch: ${currentUser.selected_branch_name || currentUser.branch}` : `IT reporting month: ${monthLabel(selectedMonth)}`}</span>
              <span className="topbar-user"><Users size={17} /><b>{roleDisplayName(currentUser.role).toUpperCase()}</b><small>{roleMeta.name}</small></span>
            </div>
          </div>
        </div>
        <div className="internal-page-content">{children}</div>
      </main>
    </div>
  )
}
