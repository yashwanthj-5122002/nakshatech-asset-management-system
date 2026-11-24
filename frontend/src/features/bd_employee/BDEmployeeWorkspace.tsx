import { Wallet } from 'lucide-react'
import type { ReactNode } from 'react'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, NavLink, Navigate, useLocation, useNavigate } from 'react-router-dom'
import {
  Activity, BarChart3, Bell, Building2, CalendarClock, ChevronDown,
  ClipboardList, FolderKanban, LifeBuoy, LogOut, Mail, Menu, MessageSquareText,
  MapPinned, FileCheck2, ShoppingCart, Plus, RefreshCw, Search, TrendingUp, UserRoundPlus, Users, X,
} from 'lucide-react'
import { apiFetch } from '../../lib/api'
import { useAuth } from '../../context/AuthContext'
import { Logo } from '../../components/Logo'
import { GlobalNotificationBell } from '../../components/GlobalNotificationBell'
import { NotificationsPage } from '../operations/pages/NotificationsPage'
import './bd-employee.css'
import { BDEmployeeProjectManagement } from './BDEmployeeProjectManagement'
import { BDClientFeedbackPage } from '../operations/pages/BDClientFeedbackPage'
import { BDEmployeeClientManagement } from './BDEmployeeClientManagement'
import { BDEmployeeProjectTracking } from './BDEmployeeProjectTracking'
import { BusinessDashboardPage } from '../business/BusinessDashboardPage'
import { FinanceCommandCenter } from '../finance/pages/FinanceCommandCenter'
import { EmployeeSupportDashboard } from '../employee_portal/pages/EmployeeSupportDashboard'
import { TicketListPage } from '../employee_portal/pages/TicketListPage'
import { TicketDetailPage } from '../employee_portal/pages/TicketDetailPage'
import { BDEmployeeTicketEntry } from './BDEmployeeTicketEntry'
import { BDEmployeeDailyDashboard } from './BDEmployeeDailyDashboard'
import { BDEmployeeProspectConversion } from './BDEmployeeProspectConversion'
import { ProfilePage } from '../../pages/ProfilePage'
import { ExpenseClaimsPage } from '../finance/pages/ExpenseClaimsPage'
import { ExpenseClaimCreatePage } from '../finance/pages/ExpenseClaimCreatePage'
import { ExpenseClaimDetailPage } from '../finance/pages/ExpenseClaimDetailPage'
import { AdvanceSettlementPage } from '../finance/pages/AdvanceSettlementPage'

type LeadSource = 'linkedin'|'google'|'email'|'phone'|'referral'|'website'|'other'
type LeadStatus = 'new'|'contacted'|'no_response'|'replied'|'interested'|'not_interested'|'enquiry'|'won'
type ActivityChannel = 'linkedin'|'email'|'phone'|'whatsapp'|'meeting'|'other'
type ActivityOutcome = 'no_response'|'replied'|'interested'|'not_interested'|'callback'|'enquiry'|'won'

type Prospect = {
  id: number; company_name: string; contact_person: string|null; contact_email: string|null;
  contact_phone: string|null; source: LeadSource; service_interest: string|null;
  status: LeadStatus; notes: string|null; next_followup_date: string|null;
  created_at: string; updated_at: string; converted_client_id?: number|null; is_converted?: boolean;
}
type RegisteredClient = {
  id: number; client_code: string; client_name: string;
  contact_person_name: string | null; client_email: string | null;
}
type Activity = { id: number; channel: ActivityChannel; outcome: ActivityOutcome; remarks: string|null; contacted_at: string }
const sourceLabels: Record<LeadSource,string> = {
  linkedin:'LinkedIn', google:'Google', email:'Email', phone:'Phone', referral:'Referral', website:'Company Website', other:'Other',
}
const statusLabels: Record<LeadStatus,string> = {
  new:'New Prospect', contacted:'Contacted', no_response:'No Response', replied:'Replied',
  interested:'Interested', not_interested:'Not Interested', enquiry:'Project Enquiry', won:'Won (unverified)',
}
const outcomeLabels: Record<ActivityOutcome,string> = {
  no_response:'No response', replied:'Client replied', interested:'Interested', not_interested:'Not interested',
  callback:'Call back later', enquiry:'Project enquiry received', won:'Won — not yet linked to ERP project',
}
const channels: ActivityChannel[] = ['linkedin','email','phone','whatsapp','meeting','other']
const outcomes = Object.keys(outcomeLabels) as ActivityOutcome[]
// Employee-only routes; never point an employee directly at manager/Finance APIs.
// Preserve the BD Manager's menu order, replacing My Team with the combined Lead Hub.
const nav = [
  { to:'/bd-employee', label:'Support Dashboard', icon:LifeBuoy },
  { to:'/bd-employee/support/new', label:'Raise New Ticket', icon:MessageSquareText },
  { to:'/bd-employee/my-expenses', label:'My Expenses', icon:Wallet },
  { to:'/bd-employee/lead-hub', label:'Daily Activity Report', icon:Users },
  { to:'/bd-employee/clients', label:'Client Management', icon:Building2 },
  { to:'/bd-employee/projects', label:'Project Management', icon:FolderKanban },
  { to:'/bd-employee/feedback', label:'Client Feedback', icon:MessageSquareText },
  { to:'/bd-employee/tracking', label:'Project Tracking', icon:Activity },
  { to:'/bd-employee/commercial', label:'Commercial Estimates', icon:BarChart3 },
  { to:'/bd-employee/notifications', label:'Notifications', icon:Bell },
  { to:'/bd-employee/business', label:'Business & Total Sell', icon:TrendingUp },
  { to:'/expenses/new', label:'New Project Expense', icon:FileCheck2 },
  { to:'/expenses', label:'My Expense Claims', icon:ShoppingCart },
  { to:'/travel-km/new', label:'Start Travel / KM Claim', icon:MapPinned },
  { to:'/travel-km', label:'My Travel / KM Claims', icon:MapPinned },
  { to:'/bd-employee/finance', label:'Finance Command Center', icon:BarChart3 },
]
const bdeExpenseLabels = new Set([
  'New Project Expense', 'My Expense Claims', 'Start Travel / KM Claim', 'My Travel / KM Claims',
])
const bdeExpenseNav = nav.filter(item => bdeExpenseLabels.has(item.label))
function bdeExpenseActiveRoute(target: string, pathname: string): boolean {
  if (pathname === target) return true
  // /travel-km/new must not also highlight /travel-km (same for /expenses/new).
  if (target.endsWith('/new')) return false
  return pathname.startsWith(target + '/') && pathname !== target + '/new'
}
const leadHubTabs = [
  {to:'/bd-employee/lead-hub/dashboard',label:'My Dashboard',icon:BarChart3},
  {to:'/bd-employee/lead-hub/prospects',label:'Prospects & Clients',icon:Users},
  {to:'/bd-employee/lead-hub/activities',label:'Contact Activities',icon:MessageSquareText},
  {to:'/bd-employee/lead-hub/followups',label:'Follow-Up Tracker',icon:CalendarClock},
]
const pageTitles:Record<string,string> = {
  overview:'Support Dashboard', 'lead-hub':'Daily Activity Report', clients:'Client Management',
  projects:'Project Management', tracking:'Project Tracking', commercial:'Commercial Estimates',
  notifications:'Notifications', business:'Business & Total Sell',
  finance:'Finance Command Center',
}
const emptyLead = { company_name:'', contact_person:'', contact_email:'', contact_phone:'', source:'linkedin' as LeadSource, service_interest:'', notes:'', next_followup_date:'' }

function dayLabel(value?: string|null): string {
  if (!value) return 'Not scheduled'
  const parts = value.split('-').map(Number)
  return parts.length === 3 && parts.every(Number.isFinite)
    ? new Date(parts[0], parts[1]-1, parts[2]).toLocaleDateString('en-IN',{day:'2-digit',month:'short',year:'numeric'})
    : value
}

function LeadRows({ rows, onOpen, onConvert, onViewClient }: { rows:Prospect[]; onOpen:(lead:Prospect)=>void; onConvert:(lead:Prospect)=>void; onViewClient:(clientId:number)=>void }) {
  if (!rows.length) return <div className="bde-empty">No matching prospects yet. Add one to begin tracking your outreach.</div>
  return <div className="bde-table-wrap"><table className="bde-table">
    <thead><tr><th>Company / Contact</th><th>Source</th><th>Current Status</th><th>Next Follow-Up</th><th>Action</th></tr></thead>
    <tbody>{rows.map(item=><tr key={item.id}>
      <td><strong>{item.company_name}</strong><small>{item.contact_person || item.contact_email || 'No contact yet'}</small></td>
      <td>{sourceLabels[item.source]}</td>
      <td><span className={`bde-status bde-status--${item.status}`}>{statusLabels[item.status]}</span></td>
      <td>{dayLabel(item.next_followup_date)}</td>
      <td><div className="bde-convert-table-actions"><button className="bde-text-button" onClick={()=>onOpen(item)}>View / Log Contact</button>{item.converted_client_id ? <button className="bde-convert-mini" onClick={()=>onViewClient(item.converted_client_id!)}>View Client</button> : item.is_converted ? <span className="bde-muted">Linked</span> : <button className="bde-convert-mini" onClick={()=>onConvert(item)}><UserRoundPlus size={13}/> Convert to Client</button>}</div></td>
    </tr>)}</tbody>
  </table></div>
}

/** Registered clients are not inferred from prospect status; IDs come from the employee-scoped API. */
function ClientRows({ rows, onView }: { rows: RegisteredClient[]; onView: (id: number) => void }) {
  if (!rows.length) return <div className="bde-empty">No registered clients found. Convert a prospect or open Client Management.</div>
  return <div className="bde-table-wrap"><table className="bde-table">
    <thead><tr><th>Client ID</th><th>Company / Contact</th><th>Email</th><th>Status</th><th>Action</th></tr></thead>
    <tbody>{rows.map(client => <tr key={client.id}>
      <td><strong>{client.client_code}</strong></td>
      <td><strong>{client.client_name}</strong><small>{client.contact_person_name || 'No contact provided'}</small></td>
      <td>{client.client_email || '—'}</td>
      <td><span className="bde-status bde-status--interested">Registered Client</span></td>
      <td><button type="button" className="bde-convert-mini" onClick={() => onView(client.id)}>View Client</button></td>
    </tr>)}</tbody>
  </table></div>
}

export function BDEmployeeWorkspace({ travelContent }: { travelContent?: ReactNode } = {}) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const route = location.pathname.startsWith('/expenses') ? 'expense' : (location.pathname.split('/')[2] || 'overview')
  const tab = travelContent ? 'travel' : (['prospects','activities','followups'].includes(route) ? 'lead-hub' : route)
  const leadHubPart = location.pathname.split('/')[3]
  const ticketId = location.pathname.split('/')[3]
  const hubTab = ['dashboard','prospects','activities','followups'].includes(leadHubPart)
    ? leadHubPart : ['prospects','activities','followups'].includes(route) ? route : 'dashboard'
  const [leads, setLeads] = useState<Prospect[]>([])
  const [clients, setClients] = useState<RegisteredClient[]>([])
  const [recordType, setRecordType] = useState<'all' | 'prospects' | 'clients'>('all')
  const [loadingClients, setLoadingClients] = useState(false)
  const [selected, setSelected] = useState<Prospect|null>(null)
  const [convertLead, setConvertLead] = useState<Prospect|null>(null)
  const [history, setHistory] = useState<Activity[]>([])
  const [search, setSearch] = useState('')
  const [showNew, setShowNew] = useState(false)
  const [editingLead, setEditingLead] = useState<number|null>(null)
  const [followupFilter, setFollowupFilter] = useState<'all'|'today'|'overdue'|'upcoming'>('all')
  const [draft, setDraft] = useState(emptyLead)
  const [editStatus, setEditStatus] = useState<LeadStatus>('new')
  const [channel, setChannel] = useState<ActivityChannel>('linkedin')
  const [outcome, setOutcome] = useState<ActivityOutcome>('no_response')
  const [remarks, setRemarks] = useState('')
  const [followup, setFollowup] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [mobileOpen, setMobileOpen] = useState(false)
  const [accountOpen, setAccountOpen] = useState(true)
  const [expensesOpen, setExpensesOpen] = useState(() =>
    bdeExpenseNav.some(item => bdeExpenseActiveRoute(item.to, location.pathname))
  )

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const p = await apiFetch<{items:Prospect[]}>('/bd-employee/prospects')
      setLeads(p.items)
      setSelected(old => old ? p.items.find(item=>item.id === old.id) || null : null)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Unable to load BD workspace')
    } finally { setLoading(false) }
  }, [])

  useEffect(()=>{ if (!travelContent && (!['overview','support','tickets','expense','profile'].includes(tab))) void refresh() },[refresh,tab, travelContent])

  const loadClients = useCallback(async () => {
    setLoadingClients(true)
    setClients([])
    setError('')
    try {
      const result = await apiFetch<{ items: RegisteredClient[] }>('/bd-employee/direct/clients/list')
      setClients(result.items)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Unable to load registered clients')
    } finally {
      setLoadingClients(false)
    }
  }, [])

  useEffect(() => {
    if (!travelContent && tab === 'lead-hub' && hubTab === 'prospects' && recordType === 'clients') {
      void loadClients()
    }
  }, [travelContent, tab, hubTab, recordType, loadClients])

  const openLead = useCallback(async (lead:Prospect) => {
    setSelected(lead)
    setFollowup(lead.next_followup_date || '')
    setRemarks('')
    setNotice('')
    try {
      const data = await apiFetch<{items:Activity[]}>(`/bd-employee/prospects/${lead.id}/activities`)
      setHistory(data.items)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Unable to load contact history')
    }
  }, [])

  // Deep-link to an authorized prospect record from dashboard drill-downs.
  useEffect(() => {
    const id = Number(new URLSearchParams(location.search).get('prospect'))
    if (!Number.isSafeInteger(id) || id <= 0) return
    const lead = leads.find(item => item.id === id)
    if (lead) void openLead(lead)
  }, [leads, location.search, openLead])

  async function createLead(event:FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('')
    try {
      await apiFetch(editingLead ? `/bd-employee/prospects/${editingLead}` : '/bd-employee/prospects', {method:editingLead ? 'PATCH' : 'POST', body:JSON.stringify({
        ...draft,
        company_name:draft.company_name.trim(),
        contact_email:draft.contact_email || null,
        contact_person:draft.contact_person || null,
        contact_phone:draft.contact_phone || null,
        service_interest:draft.service_interest || null,
        notes:draft.notes || null,
        next_followup_date:draft.next_followup_date || null,
        ...(editingLead ? {status:editStatus} : {}),
      })})
      setDraft(emptyLead); setShowNew(false); setEditingLead(null); setNotice(editingLead ? 'Client record updated.' : 'Prospect added successfully.')
      await refresh()
    } catch (exc) { setError(exc instanceof Error ? exc.message : 'Unable to save prospect') }
    finally { setBusy(false) }
  }

  async function addActivity(event:FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selected) return
    setBusy(true); setError(''); setNotice('')
    try {
      await apiFetch(`/bd-employee/prospects/${selected.id}/activities`, {method:'POST',body:JSON.stringify({
        channel, outcome, remarks:remarks || null, next_followup_date:followup || null,
      })})
      setNotice('Contact result and follow-up saved.')
      setRemarks('')
      const [data] = await Promise.all([
        apiFetch<{items:Activity[]}>(`/bd-employee/prospects/${selected.id}/activities`),
        refresh(),
      ])
      setHistory(data.items)
    } catch (exc) { setError(exc instanceof Error ? exc.message : 'Unable to log activity') }
    finally { setBusy(false) }
  }

  function beginCreate(){setEditingLead(null);setDraft(emptyLead);setEditStatus('new');setShowNew(true)}
  function beginEdit(p:Prospect){
    setSelected(null);setEditingLead(p.id);setEditStatus(p.status)
    setDraft({company_name:p.company_name,contact_person:p.contact_person||'',contact_email:p.contact_email||'',
      contact_phone:p.contact_phone||'',source:p.source,service_interest:p.service_interest||'',
      notes:p.notes||'',next_followup_date:p.next_followup_date||''});setShowNew(true)
  }
  function beginConvert(p: Prospect) { setSelected(null); setConvertLead(p); setError('') }
  function openConvertedClient(clientId:number, createProject=false) {
    setConvertLead(null)
    navigate(`/bd-employee/clients?client=${clientId}${createProject ? '&createProject=1' : ''}`)
  }
  function signOut() { logout(); navigate('/login',{replace:true}) }
  const today = new Date()
  const todayDate = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`
  const filtered = leads.filter(p=>[p.company_name,p.contact_person,p.service_interest,p.status].join(' ').toLowerCase().includes(search.toLowerCase()))
  const filteredProspects = filtered.filter(p => !p.is_converted && !p.converted_client_id)
  const clientSearch = search.trim().toLowerCase()
  const filteredClients = clients.filter(client =>
    [client.client_code, client.client_name, client.contact_person_name, client.client_email]
      .join(' ').toLowerCase().includes(clientSearch))
  const openEnquiries = filtered.filter(p=>p.status==='enquiry' || p.status==='won')
  const followups = filtered.filter(p=>p.next_followup_date && !['won','not_interested'].includes(p.status)).sort((a,b)=>(a.next_followup_date||'').localeCompare(b.next_followup_date||''))
  const selectedFollowups = followups.filter(p=>followupFilter==='all' ? true
    : followupFilter==='today' ? p.next_followup_date===todayDate
    : followupFilter==='overdue' ? (p.next_followup_date||'')<todayDate
    : (p.next_followup_date||'')>todayDate)

  // Reuse the manager feedback UI through the employee-only, backend-scoped lifecycle APIs.
  if (route === 'expenses') return <Navigate to="/bd-employee" replace />

  return <div className="app-shell bde-shell">
    <button type="button" className="mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Open BD employee menu"><Menu size={21}/></button>
    <aside className={`sidebar bde-sidebar ${mobileOpen ? 'open' : ''}`}>
      <button type="button" className="mobile-close" onClick={() => setMobileOpen(false)} aria-label="Close BD employee menu"><X size={20}/></button>
      <Logo inverse compact />
      <div className="sidebar-title">
        <strong>NakshaTech ERP</strong>
        <span>Inspiring geospatial standards</span>
      </div>
      <span className="sidebar-section-label">My Workspace</span>
      <nav aria-label="BD employee workspace">
        {nav.filter(item => !bdeExpenseLabels.has(item.label)).map(item=>{ const Icon = item.icon; const isTravelNav = item.to === '/travel-km' || item.to === '/travel-km/new'; const active = isTravelNav ? (item.to === '/travel-km/new' ? location.pathname === '/travel-km/new' : (location.pathname === '/travel-km' || (location.pathname.startsWith('/travel-km/') && location.pathname !== '/travel-km/new'))) : item.to==='/bd-employee' ? tab==='overview' : item.to==='/expenses' ? (location.pathname==='/expenses' || /^\/expenses\/\d+(?:\/(?:edit|settle))?$/.test(location.pathname)) : location.pathname===item.to || location.pathname.startsWith(item.to+'/') || (item.to==='/bd-employee/lead-hub' && ['prospects','activities','followups'].includes(route)); if (item.label === 'My Expenses') return (
          <section className={`sidebar-nav-group bde-expenses-dropdown ${expensesOpen ? 'open' : ''}`} key={item.to}>
            <button type="button" className="sidebar-group-toggle" aria-expanded={expensesOpen}
              onClick={() => setExpensesOpen(open => !open)}>
              <Icon size={18}/><span>My Expenses</span><ChevronDown size={14} className={expensesOpen ? 'open' : ''}/>
            </button>
            {expensesOpen && <div className="sidebar-group-items" style={{ paddingLeft: 12 }}>
              {bdeExpenseNav.map(child => {
                const ChildIcon = child.icon
                return <NavLink key={child.to} to={child.to} onClick={() => setMobileOpen(false)}
                  className={() => bdeExpenseActiveRoute(child.to, location.pathname) ? 'active' : ''}>
                  <ChildIcon size={16}/><span>{child.label}</span>
                </NavLink>
              })}
            </div>}
          </section>
        );
        return <NavLink to={item.to} end={item.to==='/bd-employee' || item.to==='/expenses'} key={item.to} onClick={() => setMobileOpen(false)} className={isTravelNav ? (() => active ? 'active' : '') : (active?'active':'')}><Icon size={18}/><span>{item.label}</span>{item.to==='/bd-employee/lead-hub'&&<ChevronDown className="bde-nav-chevron" size={13}/>}</NavLink> })}
      </nav>
      <div className="sidebar-footer">
        <button type="button" className="sidebar-footer-toggle" onClick={() => setAccountOpen(open => !open)} aria-expanded={accountOpen} aria-controls="bd-employee-account-card">
          <span>My Account</span><ChevronDown size={15} aria-hidden="true" className={accountOpen?'open':''}/>
        </button>
        {accountOpen && <NavLink id="bd-employee-account-card" className="sidebar-department-card" to="/bd-employee/profile" onClick={() => setMobileOpen(false)} title="Open your profile">
          <div className="user-avatar">{(user?.full_name||'BD').slice(0,1).toUpperCase()}</div>
          <div><strong>{user?.full_name || 'BD Employee'}</strong><span>{user?.employee_id || 'BD Employee'}</span></div>
        </NavLink>}
        <button type="button" className="ghost-button" onClick={signOut}><LogOut size={17}/> Logout</button>
      </div>
    </aside>
    {mobileOpen && <button type="button" className="sidebar-backdrop" onClick={() => setMobileOpen(false)} aria-label="Close BD employee menu"/>}
    <main className="bde-main"><div className="bde-notification-bell"><GlobalNotificationBell /></div>{travelContent ? travelContent : <>
      {!['overview', 'support', 'tickets', 'projects', 'clients', 'tracking', 'business', 'expense', 'finance', 'notifications', 'profile', 'feedback'].includes(tab) && tab!=='lead-hub' && <header className="bde-topbar"><div><span className="bde-overline">BUSINESS DEVELOPMENT · PERSONAL WORKSPACE</span><h1>{pageTitles[tab]||'My BD Workspace'}</h1><p>{tab==='lead-hub'?'Manage your prospects, client communications and follow-ups in one place.':'Your private BD workspace — only your own records are shown.'}</p></div><button className="bde-outline" onClick={()=>void refresh()} disabled={loading}><RefreshCw size={16}/> Refresh</button></header>}
      {error && <p className="bde-error" role="alert">{error}</p>}
      {notice && <p className="bde-success" role="status">{notice}</p>}
      {loading && <p className="bde-muted">Loading your BD records…</p>}
      {tab==='expense' && (
        location.pathname === '/expenses' ? <ExpenseClaimsPage /> :
        (location.pathname === '/expenses/new' || location.pathname.endsWith('/edit')) ? <ExpenseClaimCreatePage /> :
        location.pathname.endsWith('/settle') ? <AdvanceSettlementPage /> :
        <ExpenseClaimDetailPage />
      )}
      {tab==='profile' && <ProfilePage />}
      {tab==='overview' && <EmployeeSupportDashboard bdEmployee />}
      {tab==='support' && (ticketId === 'new' ? <BDEmployeeTicketEntry /> : <Navigate to="/bd-employee" replace />)}
      {tab==='tickets' && (ticketId ? <TicketDetailPage /> : <TicketListPage />)}
      {tab==='lead-hub' && <>
        <header className="bde-daily-page-heading">
          <span>BUSINESS DEVELOPMENT</span>
          <h1>Daily Activity Report</h1>
          <p>Client interactions, follow-ups and business activity in one place.</p>
        </header>
        <nav className="bde-hub-tabs" aria-label="Lead Hub features">
          {leadHubTabs.map(item=>{ const Icon=item.icon; const part=item.to.split('/').at(-1); return <NavLink to={item.to} key={item.to} className={hubTab===part?'bde-hub-tab active':'bde-hub-tab'}><Icon size={18}/>{item.label}</NavLink> })}
        </nav>
        {hubTab==='dashboard' && <BDEmployeeDailyDashboard />}
        {hubTab==='prospects'&& <>
          <div className="bde-section-head"><div><h2>Prospects & Clients</h2><p className="bde-muted">Manage your own business contacts and clients.</p></div>
            {recordType !== 'clients'
              ? <button className="bde-primary" onClick={beginCreate}><Plus size={18}/> Add Prospect</button>
              : <button className="bde-outline" onClick={() => navigate('/bd-employee/clients')}><Building2 size={16}/> Client Management</button>}
          </div>
          <div className="bde-record-switch" role="group" aria-label="Record type">
            <button type="button" className={recordType === 'all' ? 'active' : ''}
              aria-pressed={recordType === 'all'} onClick={() => { setRecordType('all'); setSearch('') }}>
              <Users size={14}/> All
            </button>
            <button type="button" className={recordType === 'prospects' ? 'active' : ''}
              aria-pressed={recordType === 'prospects'} onClick={() => { setRecordType('prospects'); setSearch('') }}>
              <Users size={14}/> Prospects
            </button>
            <button type="button" className={recordType === 'clients' ? 'active' : ''}
              aria-pressed={recordType === 'clients'} onClick={() => { setRecordType('clients'); setSearch('') }}>
              <Building2 size={14}/> Clients
            </button>
          </div>
          <div className="bde-toolbar"><Search size={18}/><input value={search} onChange={e=>setSearch(e.target.value)}
            aria-label={recordType === 'all' ? 'Search all prospects and clients' : recordType === 'prospects' ? 'Search prospects' : 'Search registered clients'}
            placeholder={recordType === 'all' ? 'Search company, contact or service…' : recordType === 'prospects' ? 'Search prospects by company, contact or service…' : 'Search registered clients by name, ID or contact…'} /></div>
          <section className="bde-card">
            {recordType === 'all'
              ? <LeadRows rows={filtered} onOpen={p=>void openLead(p)} onConvert={beginConvert} onViewClient={id=>openConvertedClient(id)} />
              : recordType === 'prospects'
              ? <LeadRows rows={filteredProspects} onOpen={p=>void openLead(p)} onConvert={beginConvert} onViewClient={id=>openConvertedClient(id)} />
              : loadingClients ? <p className="bde-muted">Loading your clients…</p>
              : <ClientRows rows={filteredClients} onView={id=>openConvertedClient(id)} />}
          </section>
        </>}
        {hubTab==='activities' && <>
          <section className="bde-card"><h2>Contact Activities</h2><p className="bde-muted">Choose a client to log a call, email, LinkedIn message or meeting. Contact history stays attached to the client.</p>
            <div className="bde-toolbar"><UserRoundPlus size={18}/><select value="" onChange={e=>{const found=leads.find(p=>p.id===Number(e.target.value));if(found)void openLead(found)}}><option value="">Choose client to log activity</option>{leads.map(p=><option key={p.id} value={p.id}>{p.company_name}</option>)}</select></div>
          </section>
          <section className="bde-card"><h2>Clients & Contact Records</h2><LeadRows rows={filtered} onOpen={p=>void openLead(p)} onConvert={beginConvert} onViewClient={id=>openConvertedClient(id)} /></section>
        </>}
        {hubTab==='followups' && <>
          <div className="bde-section-head"><div><h2>Follow-Up Tracker</h2><p className="bde-muted">Open a client to reschedule or record the outcome.</p></div>
            <select className="bde-small-select" value={followupFilter} onChange={e=>setFollowupFilter(e.target.value as typeof followupFilter)} aria-label="Follow-up date filter"><option value="all">All Follow-Ups</option><option value="today">Due Today</option><option value="overdue">Overdue</option><option value="upcoming">Upcoming</option></select>
          </div><section className="bde-card"><LeadRows rows={selectedFollowups} onOpen={p=>void openLead(p)} onConvert={beginConvert} onViewClient={id=>openConvertedClient(id)} /></section>
        </>}
      </>}
      {tab==='clients' && <BDEmployeeClientManagement />}
      {tab==='projects' && <BDEmployeeProjectManagement />}
      {tab==='feedback' && <BDClientFeedbackPage />}
      {tab==='tracking' && <BDEmployeeProjectTracking />}
      {tab==='commercial' && <>
        <section className="bde-card"><h2>Commercial Estimates</h2><p className="bde-muted">Your requested services are listed below. Official quotes, revision controls and pricing require a verified project link and BD Manager/Finance authorization; no financial totals are fabricated.</p><LeadRows rows={openEnquiries} onOpen={p=>void openLead(p)} onConvert={beginConvert} onViewClient={id=>openConvertedClient(id)} /></section>
      </>}
      {tab==='notifications' && <NotificationsPage bdEmployee />}
      {tab==='business' && <BusinessDashboardPage employeeScoped />}
      {tab==='finance' && <FinanceCommandCenter />}
      {showNew && <div className="bde-modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)setShowNew(false)}}><section className="bde-modal" role="dialog" aria-modal="true" aria-label="Add prospect"><div className="bde-section-head"><h2>{editingLead ? 'Edit Client Prospect' : 'Add New Prospect'}</h2><button className="bde-icon-button" onClick={()=>setShowNew(false)} aria-label="Close"><X/></button></div><form className="bde-form bde-two" onSubmit={createLead}>
        <label>Company Name *<input required minLength={2} maxLength={255} value={draft.company_name} onChange={e=>setDraft({...draft,company_name:e.target.value})}/></label>
        <label>Lead Source *<select value={draft.source} onChange={e=>setDraft({...draft,source:e.target.value as LeadSource})}>{Object.entries(sourceLabels).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>
        {editingLead && <label>Current Status<select value={editStatus} onChange={e=>setEditStatus(e.target.value as LeadStatus)}>{Object.entries(statusLabels).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>}
        <label>Contact Person<input maxLength={255} value={draft.contact_person} onChange={e=>setDraft({...draft,contact_person:e.target.value})}/></label>
        <label>Contact Email<input type="email" maxLength={255} value={draft.contact_email} onChange={e=>setDraft({...draft,contact_email:e.target.value})}/></label>
        <label>Phone / WhatsApp<input maxLength={80} value={draft.contact_phone} onChange={e=>setDraft({...draft,contact_phone:e.target.value})}/></label>
        <label>Interested Service<input maxLength={255} placeholder="LiDAR, Photogrammetry, GIS…" value={draft.service_interest} onChange={e=>setDraft({...draft,service_interest:e.target.value})}/></label>
        <label>Next Follow-Up Date<input type="date" value={draft.next_followup_date} onChange={e=>setDraft({...draft,next_followup_date:e.target.value})}/></label>
        <label className="bde-wide">Notes<textarea maxLength={4000} rows={3} value={draft.notes} onChange={e=>setDraft({...draft,notes:e.target.value})}/></label>
        <div className="bde-wide bde-actions"><button type="button" className="bde-outline" onClick={()=>setShowNew(false)}>Cancel</button><button className="bde-primary" type="submit" disabled={busy}>{busy?'Saving…':editingLead?'Save Client Changes':'Save Prospect'}</button></div>
      </form></section></div>}
      {selected && <div className="bde-modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)setSelected(null)}}><section className="bde-modal" role="dialog" aria-modal="true" aria-label="Prospect details"><div className="bde-section-head"><div><span className="bde-overline">CONTACT RECORD</span><h2>{selected.company_name}</h2><p className="bde-muted">{selected.contact_person || 'Contact not provided'} · {sourceLabels[selected.source]}</p></div><button className="bde-icon-button" onClick={()=>setSelected(null)} aria-label="Close"><X/></button></div>
        <p className="bde-muted">{selected.contact_email||'No email'} · {selected.contact_phone||'No phone'} · {selected.service_interest||'Service not specified'}</p>
        <span className={`bde-status bde-status--${selected.status}`}>{statusLabels[selected.status]}</span>
        <div className="bde-actions"><button type="button" className="bde-outline" onClick={()=>beginEdit(selected)}>Edit Client Details</button>{selected.converted_client_id ? <button type="button" className="bde-primary" onClick={()=>openConvertedClient(selected.converted_client_id!)}>View Registered Client</button> : !selected.is_converted && <button type="button" className="bde-primary" onClick={()=>beginConvert(selected)}><UserRoundPlus size={16}/> Convert to Client</button>}</div>
        <h3>Log Contact Outcome</h3><form className="bde-form bde-two" onSubmit={addActivity}>
          <label>Contact Channel<select value={channel} onChange={e=>setChannel(e.target.value as ActivityChannel)}>{channels.map(c=><option key={c} value={c}>{c[0].toUpperCase()+c.slice(1)}</option>)}</select></label>
          <label>Client Response<select value={outcome} onChange={e=>setOutcome(e.target.value as ActivityOutcome)}>{outcomes.map(o=><option key={o} value={o}>{outcomeLabels[o]}</option>)}</select></label>
          <label>Next Follow-Up<input type="date" value={followup} onChange={e=>setFollowup(e.target.value)}/></label>
          <label className="bde-wide">Discussion Notes<textarea rows={3} maxLength={4000} value={remarks} onChange={e=>setRemarks(e.target.value)}/></label>
          <div className="bde-wide bde-actions"><button className="bde-primary" type="submit" disabled={busy}>{busy?'Saving…':'Save Contact Activity'}</button></div>
        </form><h3>Communication History</h3>{history.length ? <ol className="bde-history">{history.map(a=><li key={a.id}><strong>{a.channel} · {outcomeLabels[a.outcome]}</strong><small>{new Date(a.contacted_at).toLocaleString('en-IN')}</small><p>{a.remarks||'No notes'}</p></li>)}</ol> : <p className="bde-muted">No contacts logged yet.</p>}
      </section></div>}
      {convertLead && <BDEmployeeProspectConversion
        key={convertLead.id} prospect={convertLead}
        onClose={()=>setConvertLead(null)}
        onConverted={()=>void refresh()}
        onViewClient={id=>openConvertedClient(id)}
        onCreateProject={id=>openConvertedClient(id,true)}
      />}
      <footer className="bde-footer"><ClipboardList size={14}/> Employee-scoped records only. Official financial and project privileges remain restricted.</footer>
      </>}
    </main>
  </div>
}
