import { useEffect, useMemo, useState } from 'react'
import { CalendarDays, CheckCircle2, Clock3, FileText, FolderKanban, Mail, PhoneCall, Plus, RefreshCw, Search, Users, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../../lib/api'
import './bd-daily-dashboard.css'

type Prospect = {
  id: number; company_name: string; status: string; service_interest: string | null;
  created_at: string; next_followup_date: string | null
}
type ActivityRow = {
  id: number; prospect_id: number; company_name: string; service_interest: string | null;
  channel: string; outcome: string; remarks: string | null; contacted_at: string
}
type BdProject = Record<string, unknown>
type Report = { prospects: Prospect[]; activities: ActivityRow[] }
type Period = 'today' | 'yesterday' | 'week' | 'month' | 'custom'
type Metric = 'calls' | 'connected' | 'meetings' | 'enquiries' | 'quotes' | 'projects'

const kolkata = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit' })
const dateKey = (date: Date): string => {
  const parts = kolkata.formatToParts(date)
  const value = (kind: string) => parts.find(part => part.type === kind)?.value || ''
  return `${value('year')}-${value('month')}-${value('day')}`
}
const parseTime = (value: string): Date => {
  // The existing Python API sends UTC-naive timestamps. Interpret these as UTC,
  // just as its own date-based reporting does; never use the browser time zone.
  const normalized = /(?:Z|[+-]\d\d:\d\d)$/i.test(value) ? value : `${value}Z`
  return new Date(normalized)
}
const activityDate = (value: string) => {
  const date = parseTime(value)
  return Number.isNaN(date.getTime()) ? '' : dateKey(date)
}
const showDate = (value: string) => {
  const date = parseTime(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('en-IN', {
    timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'
  })
}
const dateBounds = (period: Period, start: string, end: string): [string, string] => {
  const today = dateKey(new Date())
  if (period === 'today') return [today, today]
  const anchor = new Date(`${today}T12:00:00+05:30`)
  if (period === 'yesterday') { anchor.setUTCDate(anchor.getUTCDate() - 1); const day = dateKey(anchor); return [day, day] }
  if (period === 'week') { const day = (anchor.getUTCDay() + 6) % 7; anchor.setUTCDate(anchor.getUTCDate() - day); return [dateKey(anchor), today] }
  if (period === 'month') return [`${today.slice(0, 7)}-01`, today]
  return [start, end]
}
const text = (row: BdProject, keys: string[], fallback = '—'): string => {
  for (const key of keys) {
    const value = row[key]
    if (typeof value === 'string' && value.trim()) return value
    if (typeof value === 'number') return String(value)
  }
  return fallback
}
const metrics: { key: Metric; title: string; icon: typeof PhoneCall }[] = [
  { key: 'calls', title: 'Calls Made', icon: PhoneCall },
  { key: 'connected', title: 'Clients Connected', icon: Users },
  { key: 'meetings', title: 'Meetings', icon: CalendarDays },
  { key: 'enquiries', title: 'New Enquiries', icon: FileText },
  { key: 'quotes', title: 'Quotations Sent', icon: Mail },
  { key: 'projects', title: 'Projects Converted', icon: FolderKanban },
]
const connectedOutcomes = new Set(['replied', 'interested', 'enquiry', 'won', 'callback'])
const formatMoney = (amount: number) => new Intl.NumberFormat('en-IN', {
  style: 'currency', currency: 'INR', maximumFractionDigits: 0
}).format(amount)

export function BDEmployeeDailyDashboard() {
  const [period, setPeriod] = useState<Period>('today')
  const [start, setStart] = useState(dateKey(new Date()))
  const [end, setEnd] = useState(dateKey(new Date()))
  const [search, setSearch] = useState('')
  const [report, setReport] = useState<Report | null>(null)
  const [projects, setProjects] = useState<BdProject[] | null>(null)
  const [invoiced, setInvoiced] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [projectError, setProjectError] = useState('')
  const [financeError, setFinanceError] = useState('')
  const [metric, setMetric] = useState<Metric | null>(null)
  const [reload, setReload] = useState(0)
  const [from, to] = dateBounds(period, start, end)
  const invalidDates = !from || !to || from > to
  const currentMonth = dateKey(new Date()).slice(0, 7)

  useEffect(() => {
    if (invalidDates) { setLoading(false); setError('End date must be on or after start date.'); setReport(null); return }
    let cancelled = false
    setLoading(true)
    setError('')
    setProjectError('')
    setFinanceError('')
    setReport(null)
    // Finance figures are independent of the date filter: the API records them by month.
    void Promise.allSettled([
      apiFetch<Report>(`/bd-employee/activity-report?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`),
      apiFetch<{ projects: BdProject[] }>('/bd-employee/direct/dashboard'),
      apiFetch<{ totals: { total: number | string } }>(`/bd-employee/direct/business/overview?month=${currentMonth}`),
    ]).then(([activitiesResult, projectsResult, financeResult]) => {
      if (cancelled) return
      if (activitiesResult.status === 'fulfilled') setReport(activitiesResult.value)
      else setError(activitiesResult.reason instanceof Error ? activitiesResult.reason.message : 'Activity records could not be loaded.')
      if (projectsResult.status === 'fulfilled') setProjects(projectsResult.value.projects || [])
      else { setProjects(null); setProjectError('Authorized project list is temporarily unavailable.') }
      if (financeResult.status === 'fulfilled') {
        const value = Number(financeResult.value.totals.total)
        setInvoiced(Number.isFinite(value) ? value : null)
      } else { setInvoiced(null); setFinanceError('Invoiced figures are temporarily unavailable.') }
    }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [from, to, invalidDates, reload, currentMonth])

  useEffect(() => {
    if (!metric) return
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') setMetric(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [metric])

  const query = search.trim().toLocaleLowerCase()
  const matches = (value: string) => !query || value.toLocaleLowerCase().includes(query)
  const prospects = report?.prospects || []
  const activities = report?.activities || []
  const filteredProspects = useMemo(() => prospects.filter(p => matches(`${p.company_name} ${p.service_interest || ''} ${p.status}`)), [prospects, query])
  const filteredActivities = useMemo(() => activities.filter(a => matches(`${a.company_name} ${a.service_interest || ''} ${a.channel} ${a.outcome} ${a.remarks || ''}`)), [activities, query])
  const calls = filteredActivities.filter(a => a.channel === 'phone')
  const connectedCalls = calls.filter(a => connectedOutcomes.has(a.outcome))
  const uniqueConnected = connectedCalls.filter((row, index, rows) => rows.findIndex(a => a.prospect_id === row.prospect_id) === index)
  const meetings = filteredActivities.filter(a => a.channel === 'meeting')
  const matchingEnquiryActivities = filteredActivities.filter(a => a.outcome === 'enquiry')
  const enquiryIds = new Set(matchingEnquiryActivities.map(a => a.prospect_id))
  const inSelectedRange = (stamp: string) => { const day = activityDate(stamp); return !!day && day >= from && day <= to }
  filteredProspects.filter(p => p.status === 'enquiry' && inSelectedRange(p.created_at)).forEach(p => enquiryIds.add(p.id))
  const enquiries = prospects.filter(p => enquiryIds.has(p.id) && (matches(`${p.company_name} ${p.service_interest || ''} ${p.status}`) || matchingEnquiryActivities.some(a => a.prospect_id === p.id)))
  const values: Record<Metric, number | null> = {
    calls: calls.length, connected: uniqueConnected.length, meetings: meetings.length,
    enquiries: enquiries.length, quotes: null, projects: null,
  }
  const currentLeads = filteredProspects.filter(p => inSelectedRange(p.created_at))
  const followed = filteredProspects.filter(p => p.next_followup_date && !['won', 'not_interested'].includes(p.status))
  const today = dateKey(new Date())
  const overdue = followed.filter(p => (p.next_followup_date || '') < today)
  const due = followed.filter(p => p.next_followup_date === today)
  const upcoming = followed.filter(p => (p.next_followup_date || '') > today)
  const recent = filteredActivities.slice().sort((a, b) => b.contacted_at.localeCompare(a.contacted_at)).slice(0, 8)
  const activeProjects = (projects || []).filter(p => p.is_active !== false && !['closed', 'cancelled', 'canceled', 'finance_closure_pending'].includes(text(p, ['normalized_status', 'status', 'project_status'], '').toLowerCase()))
  const matchedProjects = activeProjects.filter(p => matches(`${text(p, ['project_name', 'name'])} ${text(p, ['client_name'])} ${text(p, ['project_code', 'project_number'])}`))
  const selected = metrics.find(m => m.key === metric)
  const detailActivities = metric === 'calls' ? calls : metric === 'connected' ? uniqueConnected : metric === 'meetings' ? meetings : []

  return <section className="bd-daily" aria-label="BD Daily Activity Dashboard">
    <div className="bd-daily-filters">
      <label>Date range <select value={period} onChange={event => setPeriod(event.target.value as Period)} aria-label="Activity date range">
        <option value="today">Today</option><option value="yesterday">Yesterday</option>
        <option value="week">This Week</option><option value="month">This Month</option>
        <option value="custom">Custom Range</option>
      </select></label>
      {period === 'custom' && <><label>From <input type="date" value={start} onChange={event => setStart(event.target.value)} /></label><label>To <input type="date" min={start} value={end} onChange={event => setEnd(event.target.value)} /></label></>}
      <label className="bd-daily-search"><Search size={16}/><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search client, activity or project" aria-label="Search dashboard records" /></label>
      <button type="button" className="bd-daily-button" onClick={() => setReload(value => value + 1)} disabled={loading}><RefreshCw size={15}/> Refresh</button>
    </div>
    {error && <p className="bd-daily-error" role="alert">Activity report unavailable: {error} <button type="button" onClick={() => setReload(value => value + 1)}>Retry</button></p>}
    {loading ? <p className="bd-daily-muted" role="status">Loading authorized BD activity records...</p> : report && <>
      <div className="bd-daily-metrics">{metrics.map(({ key, title, icon: Icon }) => <button key={key} className="bd-daily-metric" type="button" onClick={() => setMetric(key)} title={values[key] === null ? 'Requires a separately verified ERP source' : `View ${title.toLowerCase()} details`}>
        <Icon size={20}/><strong>{values[key] ?? '—'}</strong><span>{title}</span><small>{values[key] === null ? 'Not yet connected' : 'View records'}</small>
      </button>)}</div>
      <div className="bd-daily-main-grid">
        <section className="bd-daily-panel"><h3>Business Funnel</h3><p className="bd-daily-muted">Current stages of prospects created in the selected date range; historical stage changes are not inferred.</p>
          <div className="bd-daily-funnel">{[
            ['New Prospects', currentLeads.length],
            ['Project Enquiries', currentLeads.filter(p => p.status === 'enquiry').length],
            ['Interested', currentLeads.filter(p => p.status === 'interested').length],
            ['Won (Unverified)', currentLeads.filter(p => p.status === 'won').length],
          ].map(([name, count], index) => <div className={`bd-daily-funnel-stage stage-${index}`} key={String(name)}><span>{name}</span><strong>{count}</strong></div>)}</div>
        </section>
        <section className="bd-daily-panel"><h3>Business Generated</h3><p className="bd-daily-muted">Verified Finance figures are monthly invoiced business, not confirmed order value.</p>
          <div className="bd-daily-revenue">{invoiced === null ? '—' : formatMoney(invoiced)}</div><p className="bd-daily-muted">Invoiced business · {currentMonth} · separate from activity date filter</p>
          {financeError && <p className="bd-daily-muted">{financeError}</p>}
          <div className="bd-daily-tiny"><strong>{projects === null ? '—' : activeProjects.length}</strong><span>Current authorized active BD projects (all dates)</span></div>
          <Link className="bd-daily-action-link" to="/bd-employee/business">View verified Business & Total Sell</Link>
        </section>
        <section className="bd-daily-panel bd-daily-activity-panel"><div className="bd-daily-heading"><h3>Activities in Selected Period</h3><Link to="/bd-employee/lead-hub/activities" className="bd-daily-button"><Plus size={15}/> Log Activity</Link></div>
          {recent.slice(0, 5).map(a => <button key={a.id} type="button" className="bd-daily-timeline-item" onClick={() => setMetric(a.channel === 'meeting' ? 'meetings' : a.channel === 'phone' ? 'calls' : null)}>
            <span>{showDate(a.contacted_at)}</span><strong>{a.channel} · {a.company_name}</strong><small>{a.remarks || a.outcome}</small>
          </button>)}
          {recent.length === 0 && <p className="bd-daily-muted">No matching activities were recorded in the selected period.</p>}
        </section>
      </div>
      <div className="bd-daily-bottom-grid"><div className="bd-daily-left">
        <section className="bd-daily-panel"><h3>Tasks & Follow-ups <small className="bd-daily-subtle">(current, independent of activity date range)</small></h3>
          <div className="bd-daily-follow-grid">{[
            { name: 'Overdue', count: overdue.length }, { name: 'Due Today', count: due.length }, { name: 'Upcoming', count: upcoming.length },
          ].map((item, index) => <Link to="/bd-employee/lead-hub/followups" key={item.name} className={`bd-daily-follow follow-${index}`}><Clock3 size={19}/><strong>{item.count}</strong><span>{item.name}</span></Link>)}
            <Link to="/bd-employee/lead-hub/followups" className="bd-daily-follow follow-3"><CheckCircle2 size={19}/><strong>View</strong><span>Follow-up Tracker</span></Link>
          </div>
        </section>
        <section className="bd-daily-panel"><div className="bd-daily-heading"><h3>Recent Activities</h3><Link to="/bd-employee/lead-hub/activities">View All</Link></div>
          <div className="bd-daily-table-wrap"><table><thead><tr><th>Date & Time</th><th>Type</th><th>Client / Company</th><th>Details</th><th>Outcome</th><th>Action</th></tr></thead><tbody>{recent.map(a => <tr key={a.id}><td>{showDate(a.contacted_at)}</td><td>{a.channel}</td><td>{a.company_name}</td><td>{a.remarks || '—'}</td><td>{a.outcome}</td><td><Link to={`/bd-employee/lead-hub/activities?prospect=${a.prospect_id}`}>View</Link></td></tr>)}</tbody></table>
            {recent.length === 0 && <p className="bd-daily-muted">No records match the selected date and search.</p>}
          </div>
        </section>
      </div><section className="bd-daily-panel"><div className="bd-daily-heading"><h3>Active Projects (BD)</h3><Link to="/bd-employee/projects">View All</Link></div><p className="bd-daily-muted">Only projects authorized for your BD Employee account. No photos or duplicates.</p>
        {projectError && <p role="alert" className="bd-daily-muted">{projectError}</p>}
        <div className="bd-daily-table-wrap"><table><thead><tr><th>Project</th><th>Client</th><th>Status</th></tr></thead><tbody>{matchedProjects.slice(0, 10).map((project, index) => <tr key={String(project.id ?? index)}><td>{text(project, ['project_name', 'name', 'project_code'], 'Project')}</td><td>{text(project, ['client_name'])}</td><td>{text(project, ['normalized_status', 'status', 'project_status']).replaceAll('_', ' ')}</td></tr>)}</tbody></table>
          {projects !== null && matchedProjects.length === 0 && <p className="bd-daily-muted">No authorized active projects match your search.</p>}
        </div>
      </section></div>
    </>}
    {metric && <div className="bd-daily-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) setMetric(null) }}>
      <section role="dialog" aria-modal="true" aria-label={`${selected?.title || ''} details`} className="bd-daily-dialog">
        <div className="bd-daily-heading"><h3>{selected?.title} — Details</h3><button type="button" aria-label="Close details" onClick={() => setMetric(null)}><X size={20}/></button></div>
        <p className="bd-daily-muted">{from} to {to} · Searched records from your account only</p>
        {metric === 'quotes' || metric === 'projects' ? <><p className="bd-daily-muted">{metric === 'quotes' ? 'The quotation total needs a verified estimate history for this employee.' : 'Confirmed project conversion requires an authorized purchase order or work-order record.'} No count will be guessed from other project statuses.</p>
          <Link className="bd-daily-action-link" to={metric === 'quotes' ? '/bd-employee/commercial' : '/bd-employee/projects'} onClick={() => setMetric(null)}>Open original {metric === 'quotes' ? 'commercial' : 'project'} records</Link></>
          : metric === 'enquiries' ? <div className="bd-daily-table-wrap"><table><thead><tr><th>Prospect</th><th>Service</th><th>Current stage</th><th>Action</th></tr></thead><tbody>{enquiries.map(p => <tr key={p.id}><td>{p.company_name}</td><td>{p.service_interest || '—'}</td><td>{p.status}</td><td><Link to={`/bd-employee/lead-hub/prospects?prospect=${p.id}`} onClick={() => setMetric(null)}>View full details</Link></td></tr>)}</tbody></table></div>
          : <div className="bd-daily-table-wrap"><table><thead><tr><th>Date & Time</th><th>Client</th><th>Outcome</th><th>Discussion</th><th>Action</th></tr></thead><tbody>{detailActivities.map(a => <tr key={a.id}><td>{showDate(a.contacted_at)}</td><td>{a.company_name}</td><td>{a.outcome}</td><td>{a.remarks || '—'}</td><td><Link to={`/bd-employee/lead-hub/activities?prospect=${a.prospect_id}`} onClick={() => setMetric(null)}>View full details</Link></td></tr>)}</tbody></table></div>}
        {metric !== 'quotes' && metric !== 'projects' && (metric === 'enquiries' ? enquiries.length : detailActivities.length) === 0 && <p className="bd-daily-muted">No matching records for the selected date and search.</p>}
      </section>
    </div>}
  </section>
}
