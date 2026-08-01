import {
  ArrowRightLeft,
  BarChart3,
  Boxes,
  ClipboardList,
  FileDown,
  FolderKanban,
  HardDrive,
  LayoutDashboard,
  LogOut,
  Menu,
  PackageCheck,
  PlaneTakeoff,
  Repeat2,
  Settings,
  ShieldCheck,
  UploadCloud,
  Users,
  X,
} from 'lucide-react'
import { DroneIcon as Drone, type AppIcon } from './DroneIcon'
import { useState, type ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import type { Role } from '../types'
import { Logo } from './Logo'

interface NavItem {
  to: string
  label: string
  icon: AppIcon
  roles: Role[]
}

const navItems: NavItem[] = [
  { to: '/admin', label: 'Admin Overview', icon: ShieldCheck, roles: ['admin'] },
  { to: '/management', label: 'Management', icon: BarChart3, roles: ['admin', 'management'] },
  { to: '/it', label: 'IT Dashboard', icon: LayoutDashboard, roles: ['admin', 'management', 'it'] },
  { to: '/assets', label: 'Asset Register', icon: HardDrive, roles: ['admin', 'management', 'it'] },
  { to: '/work', label: 'IT Work Records', icon: ClipboardList, roles: ['admin', 'management', 'it'] },
  { to: '/replacements', label: 'Replacements', icon: Repeat2, roles: ['admin', 'management', 'it'] },
  { to: '/drone', label: 'Drone Dashboard', icon: Drone, roles: ['admin', 'management', 'drone'] },
  { to: '/drone/assets', label: 'Drone Assets', icon: Boxes, roles: ['admin', 'management', 'drone'] },
  { to: '/drone/kits', label: 'Drone Kits', icon: PackageCheck, roles: ['admin', 'management', 'drone'] },
  { to: '/drone/projects', label: 'Drone Projects', icon: FolderKanban, roles: ['admin', 'management', 'drone'] },
  { to: '/drone/operations', label: 'Drone Operations', icon: PlaneTakeoff, roles: ['admin', 'management', 'drone'] },
  { to: '/drone/work-records', label: 'Drone Work Records', icon: ClipboardList, roles: ['admin', 'management', 'drone'] },
  { to: '/drone/movements', label: 'Movement History', icon: ArrowRightLeft, roles: ['admin', 'management', 'drone'] },
  { to: '/drone/import', label: 'Drone Import', icon: UploadCloud, roles: ['admin'] },
  { to: '/reports', label: 'Excel & Reports', icon: FileDown, roles: ['admin', 'management', 'it'] },
  { to: '/future', label: 'Future Modules', icon: Settings, roles: ['admin'] },
]

const roleLabels: Record<Role, { name: string; subtitle: string }> = {
  admin: { name: 'Admin Workspace', subtitle: 'Full system control' },
  management: { name: 'Management', subtitle: 'Oversight & approvals' },
  it: { name: 'IT Department', subtitle: 'Head Office' },
  drone: { name: 'Drone Department', subtitle: 'Survey operations' },
}

export function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()
  if (!user) return null

  const available = navItems.filter(item => item.roles.includes(user.role))
  const roleMeta = roleLabels[user.role]

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
        <nav>
          {available.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} onClick={() => setMobileOpen(false)} className={({ isActive }) => isActive ? 'active' : ''}>
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="sidebar-department-card">
            <div className="user-avatar">{user.full_name.charAt(0)}</div>
            <div>
              <small>{roleMeta.name}</small>
              <strong>{user.full_name}</strong>
              <span>{roleMeta.subtitle} · {user.branch}</span>
            </div>
          </div>
          <button className="ghost-button" onClick={logout}><LogOut size={17} /> Logout</button>
        </div>
      </aside>
      {mobileOpen && <button className="sidebar-backdrop" onClick={() => setMobileOpen(false)} aria-label="Close menu" />}
      <main className="main-content" key={location.pathname}>
        <div className="topbar">
          <div className="topbar-status"><span className="system-indicator" /><span>System online</span></div>
          <div className="topbar-actions">
            <span className="topbar-context"><PackageCheck size={17} />{user.role === 'drone' ? 'Drone operations workspace' : 'July 2026 inventory loaded'}</span>
            <span className="topbar-user"><Users size={17} /><b>{user.role.toUpperCase()}</b><small>{roleMeta.name}</small></span>
          </div>
        </div>
        <div className="internal-page-content">{children}</div>
      </main>
    </div>
  )
}
