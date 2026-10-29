import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { LogIn, LogOut, ChevronLeft, ChevronRight, ArrowUpRight, CalendarDays, Bell, History } from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import { governmentHolidays2026, KARNATAKA_GOV_CALENDAR_URL } from './karnatakaGovernmentCalendar'
import { apiFetch } from '../../lib/api'
import './hrms.css'

type Punch = { id: number; work_date: string; check_in_utc: string; check_out_utc: string | null }
type Explanation = { id: number; work_date: string; reason: string; status: string; hr_note: string | null; employee_name?: string; user_id?: number }
type Leave = { id: number; user_id: number; leave_type: string; from_date: string; to_date: string; requested_calendar_days: number; reason: string; status: string; decision_note: string | null; employee_name?: string; duration?: 'full_day' | 'half_day'; half_day_session?: 'morning' | 'afternoon' | null; office_time?: string | null; cancellation_status?: 'pending' | 'approved' | 'rejected' | null }
type Balance = { leave_type: string; entitled: number | null; approved_calendar_days: number; pending_calendar_days: number; approved_chargeable_days?: number; pending_chargeable_days?: number; remaining_provisional: number | null }
type Holiday = { date: string; name: string; region: string; category: string; official_source_url: string | null; hr_verified: boolean }
type AttendanceResponse = { punches: Punch[]; explanations: Explanation[]; timezone: string; source: string }
type LeaveBalanceResponse = { year: number; balances: Balance[]; notice: string }
type HREmployee = { user_id: number; name: string; employee_id: string | null; department: string | null; role: string; status: string; check_in_utc: string | null; check_out_utc: string | null; absence_reason: string | null; explanation_status: string | null }
type HROverview = { date: string; employees: HREmployee[]; pending_leaves: Leave[]; pending_explanations: Explanation[]; pending_cancellations?: Leave[]; notice: string }
type HRNotice = { leave_id: number; user_id: number; employee_name: string; leave_type: string; from_date: string; to_date: string; created_at: string; is_read: boolean }
type HRNotices = { unread_count: number; pending_count: number; notifications: HRNotice[] }
type CompanyLeavePolicy = { year: number; intern_monthly_days: number; probation_first_six_month_days: number; months_seven_to_twelve_extra_days: number; full_time_annual_days: number; working_weekdays: number[]; no_carry_forward: boolean }
type EmploymentRow = { user_id: number; employee_name: string; department: string | null; role: string; joining_date: string | null; employment_category: string | null; assigned: boolean }
type HRHistory = { employee: { user_id: number; name: string; employee_id: string | null; department: string | null; role: string }; year: number | null; requests: Leave[]; summary: { total_requests: number; approved_requests: number; approved_calendar_days: number; pending_requests: number; pending_calendar_days: number; rejected_requests: number; cancelled_requests: number }; notice: string }

const LEAVE_OPTIONS = ['paid', 'casual', 'sick', 'earned', 'unpaid'] as const
// Leave category and duration are separate: 0.5 day is not a new payroll category.
type LeaveForm = { leave_type: string; from_date: string; to_date: string; duration: 'full_day' | 'half_day'; half_day_session: 'morning' | 'afternoon'; office_time: string; reason: string }
const newLeaveForm = (): LeaveForm => ({ leave_type: 'casual', from_date: todayIST(), to_date: todayIST(), duration: 'full_day', half_day_session: 'morning', office_time: '', reason: '' })
const leaveDays = (item: Leave) => item.duration === 'half_day' ? 0.5 : item.requested_calendar_days
const leaveSession = (item: Leave) => item.duration === 'half_day' ? `Half day · ${item.half_day_session === 'afternoon' ? 'Afternoon' : 'Morning'}` : 'Full day'
const officeTimeLabel = (item: Leave) => item.duration === 'half_day' && item.office_time ? ` · ${item.half_day_session === 'morning' ? 'Return' : 'Exit'} ${item.office_time}` : ''
// A monthly summary never combines half-day requests across different months.
function halfDayMonthlyTotals(leaves: Leave[]) {
  const totals = new Map<string, number>()
  for (const item of leaves) {
    if (item.duration !== 'half_day' || item.status !== 'approved' || item.cancellation_status === 'approved') continue
    const month = item.from_date.slice(0, 7)
    totals.set(month, (totals.get(month) ?? 0) + 1)
  }
  return [...totals.entries()].sort(([a], [b]) => b.localeCompare(a)).map(([month, count]) => ({ month, count, days: count * 0.5 }))
}
const fmt = (datetime: string | null) => datetime ? new Date(datetime).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' }) : '—'
const statusName = (s: string) => s.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase())
const todayIST = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
const errorText = (err: unknown) => err instanceof Error ? err.message : 'Request failed. Please try again.'

const nav = [
  { to: '/hrms/leave/balance', name: 'Leave Balance' },
  { to: '/hrms/leave/apply', name: 'Leave Application' },
  { to: '/hrms/leave/calendar', name: 'My Leave Calendar' },
  { to: '/hrms/leave/holidays', name: 'Holiday Calendar' },
  { to: '/hrms/attendance', name: 'My Attendance' },
]

function Header({
  title,
  description,
  hr = false,
}: {
  title: string
  description: string
  hr?: boolean
}) {
  const { user } = useAuth()

  const visibleNav = user?.role === 'employee' ? nav : []

  return (
    <>
      <header className="hrms-header">
        <span className="hrms-eyebrow">
          {hr ? 'HR MANAGEMENT' : 'EMPLOYEE SELF-SERVICE'} · NAKSHATECH
        </span>
        <h1>{title}</h1>
        <p>{description}</p>
      </header>

      {!hr && visibleNav.length > 0 && (
        <nav
          className="hrms-tabs"
          aria-label="Leave and attendance pages"
        >
          {visibleNav.map((link) => (
            <Link key={link.to} to={link.to}>
              {link.name}
            </Link>
          ))}
        </nav>
      )}
    </>
  )
}
export default Header;

function Failure({ message }: { message: string }) { return message ? <div role="alert" className="hrms-error">{message}</div> : null }
function Success({ message }: { message: string }) { return message ? <div role="status" className="hrms-success">{message}</div> : null }
function Badge({ status }: { status: string }) { return <span className={`hrms-status hrms-status--${status}`}>{statusName(status)}</span> }

// Touch-scrollable content with equivalent keyboard-accessible arrow buttons.
function SwipeRail({ children, title, className = '' }: { children: ReactNode; title: string; className?: string }) {
  const rail = useRef<HTMLDivElement>(null)
  const scroll = (direction: number) => rail.current?.scrollBy({ left: direction * Math.max(260, rail.current.clientWidth * .7), behavior: 'smooth' })
  return <div className={`hrms-swipe-wrap ${className}`}>
    <div className="hrms-swipe-heading"><span>{title}</span><div className="hrms-swipe-arrows">
      <button type="button" aria-label={`Previous ${title}`} onClick={() => scroll(-1)}><ChevronLeft size={17}/></button>
      <button type="button" aria-label={`Next ${title}`} onClick={() => scroll(1)}><ChevronRight size={17}/></button>
    </div></div>
    <div ref={rail} className="hrms-swipe-track" tabIndex={0} aria-label={`${title}, horizontally scrollable`}>{children}</div>
    <small className="hrms-swipe-hint">Swipe sideways or use the arrows to see more.</small>
  </div>
}

const shiftedMonth = (month: string, offset: number) => {
  const [year, number] = month.split('-').map(Number)
  const adjusted = new Date(Date.UTC(year, number - 1 + offset, 1))
  return `${adjusted.getUTCFullYear()}-${String(adjusted.getUTCMonth() + 1).padStart(2, '0')}`
}

function MonthNavigator({ month, onChange }: { month: string; onChange: (value: string) => void }) {
  const startX = useRef<number | null>(null)
  return <div className="hrms-month-nav" onTouchStart={e => { startX.current = e.touches[0]?.clientX ?? null }}
    onTouchEnd={e => { const dx = startX.current === null ? 0 : e.changedTouches[0].clientX - startX.current; if (Math.abs(dx) > 65) onChange(shiftedMonth(month, dx < 0 ? 1 : -1)); startX.current = null }}>
    <button type="button" aria-label="Previous month" onClick={() => onChange(shiftedMonth(month, -1))}><ChevronLeft size={18}/></button>
    <label className="hrms-calendar-month">Month<input type="month" value={month} onChange={e => onChange(e.target.value)} /></label>
    <button type="button" aria-label="Next month" onClick={() => onChange(shiftedMonth(month, 1))}><ChevronRight size={18}/></button>
    <span className="hrms-month-hint">Swipe to change month</span>
  </div>
}

function YearHolidayTiles({ year, holidays, onSelect }: { year: number; holidays: Holiday[]; onSelect: (month: string) => void }) {
  const shortMonths = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC']
  return <SwipeRail title={`Holiday months · ${year}`} className="hrms-year-months">
    {shortMonths.map((name, i) => {
      const month = `${year}-${String(i + 1).padStart(2, '0')}`
      const items = holidays.filter(h => h.date.startsWith(month))
      return <button className="hrms-month-tile" type="button" key={month} onClick={() => onSelect(month)} aria-label={`Open ${name} ${year}: ${items.length} listed holidays`}>
        <span className="hrms-month-tile-title">{name} {year} <ChevronRight size={14}/></span>
        {items.length ? items.slice(0, 3).map((h, index) => <span key={`${h.date}-${index}`} className="hrms-mini-holiday">
          <strong>{h.date.slice(-2)}</strong><span>{h.name}</span>
        </span>) : <span className="hrms-mini-empty">No listed holidays</span>}
        {items.length > 3 && <small>+{items.length - 3} more · Open month</small>}
      </button>
    })}
  </SwipeRail>
}

function MonthCalendar({ month, leaves, holidays, governmentReference = false }: { month: string; leaves: Leave[]; holidays: Holiday[]; governmentReference?: boolean }) {
  const [year, number] = month.split('-').map(Number)
  const count = new Date(Date.UTC(year, number, 0)).getUTCDate()
  const offset = (new Date(Date.UTC(year, number - 1, 1)).getUTCDay() + 6) % 7
  const cells = Array.from({ length: offset + count }, (_, index) => {
    const day = index - offset + 1
    return day <= 0 ? null : `${month}-${String(day).padStart(2, '0')}`
  })
  return <div className="hrms-calendar" role="grid" aria-label={`${month} leave and holiday calendar`}>
    {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(day => <div key={day} className="hrms-calendar-head">{day}</div>)}
    {cells.map((day, i) => <div key={day || `empty-${i}`} className={`hrms-calendar-day ${day ? '' : 'hrms-calendar-empty'}`}>
      {day && <><strong>{Number(day.slice(-2))}</strong>
        {leaves.filter(l => l.status !== 'cancelled' && l.status !== 'rejected' && l.from_date <= day && l.to_date >= day).map(l => <span key={l.id} className={`hrms-calendar-event ${l.status}`}>{statusName(l.leave_type)} · {leaveSession(l)} · {l.status}</span>)}
        {holidays.filter(h => h.date === day).map(h => <span key={`${h.date}-${h.region}`} className="hrms-calendar-event holiday" title={governmentReference ? 'Official Karnataka government reference (not HR-published)' : h.hr_verified ? 'HR verified' : 'Awaiting HR verification'}>{h.name}{governmentReference ? (h.category === 'restricted' ? ' (Restricted)' : '') : (h.hr_verified ? '' : ' (pending HR verification)')}</span>)}
      </>}
    </div>)}
  </div>
}

export function LeavePage({ mode }: { mode: 'balance' | 'apply' | 'calendar' | 'holidays' }) {
  const { user } = useAuth()
  const hrUsesEmail = mode === 'apply' && user?.role === 'hr'
  const year = new Date().getFullYear()
  const [requests, setRequests] = useState<Leave[]>([])
  const [balance, setBalance] = useState<LeaveBalanceResponse | null>(null)
  const [holidays, setHolidays] = useState<Holiday[]>([])
  const [calendarMonth, setCalendarMonth] = useState(todayIST().slice(0, 7))
  const [holidayYear, setHolidayYear] = useState(year)
  const [holidayView, setHolidayView] = useState<'government' | 'company'>('government')
  const [applicationTab, setApplicationTab] = useState<'apply' | 'pending' | 'history'>('apply')
  const applyTouchX = useRef<number | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState<LeaveForm>(newLeaveForm)
  const [editingId, setEditingId] = useState<number | null>(null)

  const load = useCallback(async () => {
    try {
      const [a, b, c] = await Promise.all([
        apiFetch<Leave[]>('/hrms/me/leave'),
        apiFetch<LeaveBalanceResponse>(`/hrms/me/balance?year=${year}`),
        apiFetch<Holiday[]>(`/hrms/holidays?year=${mode === 'holidays' ? holidayYear : year}`),
      ])
      setRequests(a); setBalance(b); setHolidays(c)
      setError('')
    } catch (err) { setError(errorText(err)) }
  }, [year, holidayYear, mode])
  useEffect(() => { void load() }, [load])

  async function apply(event: FormEvent) {
    event.preventDefault(); setNotice(''); setError('')
    if (form.duration === 'half_day' && (!form.office_time || form.from_date !== form.to_date)) {
      setError('Half-day leave requires one date and an expected office exit/return time.')
      return
    }
    setBusy(true)
    try {
      const payload = {
        leave_type: form.leave_type,
        from_date: form.from_date,
        to_date: form.duration === 'half_day' ? form.from_date : form.to_date,
        reason: form.reason,
        duration: form.duration,
        half_day_session: form.duration === 'half_day' ? form.half_day_session : null,
        office_time: form.duration === 'half_day' ? form.office_time : null,
      }
      if (editingId === null) {
        await apiFetch('/hrms/me/leave', { method: 'POST', body: JSON.stringify(payload) })
        setNotice('Leave application submitted to HR for review.')
      } else {
        await apiFetch(`/hrms/me/leave/${editingId}`, { method: 'PUT', body: JSON.stringify(payload) })
        setNotice('Pending leave application updated. HR will review the latest version.')
      }
      setEditingId(null)
      setForm(newLeaveForm())
      setApplicationTab('pending')
      await load()
    } catch (err) { setError(errorText(err)) } finally { setBusy(false) }
  }
  function editPending(item: Leave) {
    if (item.status !== 'pending') return
    setEditingId(item.id)
    setForm({
      leave_type: item.leave_type,
      from_date: item.from_date,
      to_date: item.duration === 'half_day' ? item.from_date : item.to_date,
      duration: item.duration === 'half_day' ? 'half_day' : 'full_day',
      half_day_session: item.half_day_session === 'afternoon' ? 'afternoon' : 'morning',
      office_time: item.office_time ?? '',
      reason: item.reason,
    })
    setApplicationTab('apply')
    setError(''); setNotice('')
  }
  function stopEditing() { setEditingId(null); setForm(newLeaveForm()); setError('') }
  async function withdraw(id: number) {
    if (!window.confirm('Withdraw this pending leave application?')) return
    setBusy(true); setError('')
    try {
      await apiFetch(`/hrms/me/leave/${id}/cancel`, { method: 'POST' })
      setNotice('Pending leave application withdrawn.')
      await load()
    } catch (err) { setError(errorText(err)) } finally { setBusy(false) }
  }
  async function requestApprovedCancellation(id: number) {
    const reason = window.prompt('Reason for requesting cancellation of an APPROVED leave (HR must approve):', '')
    if (reason === null) return
    if (reason.trim().length < 5) { setError('Please provide at least five characters as the cancellation reason.'); return }
    setBusy(true); setError(''); setNotice('')
    try {
      await apiFetch(`/hrms/me/leave/${id}/request-cancellation`, { method: 'POST', body: JSON.stringify({ reason: reason.trim() }) })
      setNotice('Cancellation request sent to HR. The original leave remains approved until HR accepts the cancellation.')
      await load()
    } catch (err) { setError(errorText(err)) } finally { setBusy(false) }
  }
  const titles = { balance: 'Leave Balance', apply: 'Leave Application', calendar: 'My Leave Calendar', holidays: 'Holiday Calendar' }
  const filtered = useMemo(() => [...requests].sort((a, b) => b.from_date.localeCompare(a.from_date)), [requests])
  const monthlyHalfDays = useMemo(() => halfDayMonthlyTotals(requests), [requests])

  return <main className="hrms-page">
    <Header title={titles[mode]} description="Review your leave records, applications and NakshaTech-approved holidays." />
    <Failure message={error}/><Success message={notice}/>
    {mode === 'balance' && user?.role === 'employee' && <section className="hrms-panel hrms-reference-panel">
      <div className="hrms-row"><div><p className="hrms-section-eyebrow">MY LEAVE ACCOUNT</p><h2>Leave balances · {year}</h2></div><Link className="hrms-primary hrms-inline-action" to="/hrms/leave/apply">Apply for leave <ArrowUpRight size={15}/></Link></div>
      <SwipeRail title="Your leave types">{balance?.balances.map(item => <article className="hrms-balance-card" key={item.leave_type}>
        <span>{statusName(item.leave_type)} Leave</span><small>Entitlement: {item.entitled ?? 'Awaiting HR setup'}</small>
        <strong>{item.entitled === null ? '—' : item.remaining_provisional}</strong><span className="hrms-balance-caption">Available (provisional)</span>
        <div className="hrms-balance-divider"/><small>Used working days: {item.approved_chargeable_days ?? item.approved_calendar_days} · Pending: {item.pending_chargeable_days ?? item.pending_calendar_days}</small>
      </article>)}</SwipeRail>
      <p className="hrms-muted">{balance?.notice || 'HR has not configured the company leave policy.'} These amounts are not posted to payroll.</p>
    </section>}
    {hrUsesEmail && <section className="hrms-panel"><h2>HR personal leave requests</h2><p className="hrms-muted">HR personnel request their own leave through the designated company email procedure. Employee applications and approvals are available in the HR dashboard.</p><Link to="/hrms/hr" className="hrms-primary hrms-inline-action">Open employee leave requests</Link></section>}
    {mode === 'apply' && user?.role === 'employee' && <section className="hrms-panel hrms-reference-panel" onTouchStart={e => {
      if ((e.target as HTMLElement).closest('input, textarea, select, button')) return
      applyTouchX.current = e.touches[0]?.clientX ?? null
    }} onTouchEnd={e => {
      if (applyTouchX.current === null) return
      const dx = e.changedTouches[0].clientX - applyTouchX.current
      applyTouchX.current = null
      if (Math.abs(dx) < 85) return
      const tabs = ['apply', 'pending', 'history'] as const
      const next = Math.min(2, Math.max(0, tabs.indexOf(applicationTab) + (dx < 0 ? 1 : -1)))
      setApplicationTab(tabs[next])
    }}>
      <div className="hrms-row"><div><p className="hrms-section-eyebrow">EMPLOYEE LEAVE DESK</p><h2>{editingId === null ? 'Apply for leave' : `Edit pending leave #${editingId}`}</h2></div><Link className="hrms-secondary hrms-inline-action" to="/hrms/leave/balance">View balance</Link></div>
      <div className="hrms-segmented" role="tablist" aria-label="Leave application views">
        {(['apply','pending','history'] as const).map(tab => <button key={tab} type="button" role="tab" aria-selected={applicationTab === tab} className={applicationTab === tab ? 'active' : ''} onClick={() => setApplicationTab(tab)}>{tab === 'apply' ? 'Apply' : tab === 'pending' ? `Pending (${requests.filter(r => r.status === 'pending').length})` : 'History'}</button>)}
      </div>
      {applicationTab === 'apply' && <><p className="hrms-muted">Leave is granted according to company policy. Select a leave type, date range and reason before submitting for HR review.</p>
      <form className="hrms-form hrms-apply-form" onSubmit={e => void apply(e)}>
        <label>Leave type<select required value={form.leave_type} onChange={e => setForm({ ...form, leave_type: e.target.value })}>{LEAVE_OPTIONS.map(t => <option key={t} value={t}>{statusName(t)}</option>)}</select></label>
        <label>Leave duration<select required value={form.duration} onChange={e => {
          const duration = e.target.value as LeaveForm['duration']
          setForm(current => ({ ...current, duration, to_date: duration === 'half_day' ? current.from_date : current.to_date }))
        }}><option value="full_day">Full day</option><option value="half_day">Half day (0.5)</option></select></label>
        <label>From date<input type="date" required value={form.from_date} onChange={e => setForm({ ...form, from_date: e.target.value, to_date: form.duration === 'half_day' ? e.target.value : form.to_date })}/></label>
        <label>To date<input type="date" required disabled={form.duration === 'half_day'} min={form.from_date} value={form.duration === 'half_day' ? form.from_date : form.to_date} onChange={e => setForm({ ...form, to_date: e.target.value })}/></label>
        {form.duration === 'half_day' && <>
          <label>Half-day session<select value={form.half_day_session} onChange={e => setForm({ ...form, half_day_session: e.target.value as LeaveForm['half_day_session'], office_time: '' })} required>
            <option value="morning">Morning to noon (first half)</option><option value="afternoon">Noon to end of day (second half)</option>
          </select></label>
          <label>{form.half_day_session === 'morning' ? 'Expected office return time' : 'Expected office leaving time'}<input type="time" required value={form.office_time} onChange={e => setForm({ ...form, office_time: e.target.value })}/></label>
          <p className="hrms-muted hrms-form-wide">This is a planned time supplied with the request. Actual check-in/out remains recorded separately by attendance.</p>
        </>}
        <label>Available paid leave<input readOnly value={balance?.balances.find(b => b.leave_type === 'paid')?.remaining_provisional ?? 'Awaiting HR policy'}/></label>
        <label className="hrms-form-wide">Reason<textarea rows={4} minLength={5} maxLength={1500} required value={form.reason} onChange={e => setForm({ ...form, reason: e.target.value })} placeholder="Tell HR why you need leave"/></label>
        <button disabled={busy} className="hrms-primary">{busy ? 'Saving...' : editingId === null ? 'Submit leave request' : 'Save pending changes'}</button>
        {editingId !== null && <button type="button" className="hrms-secondary" disabled={busy} onClick={stopEditing}>Cancel edit</button>}
      </form><p className="hrms-muted">Duration uses provisional calendar days; weekends, payroll and leave rules remain governed by HR.</p></>}
      {applicationTab !== 'apply' && <>
        {applicationTab === 'history' && <section aria-label="Monthly approved half-day summary" className="hrms-panel">
          <h3>Approved half-day totals by month</h3>
          <p className="hrms-muted">Two approved half-days in the same month = one day. Different months remain separate. Requests are not merged or deleted.</p>
          {monthlyHalfDays.length ? <div className="hrms-grid">{monthlyHalfDays.map(m => <article className="hrms-metric" key={m.month}><span>{m.month}</span><strong>{m.days} {m.days === 1 ? 'day' : 'days'}</strong><small>{m.count} approved half-day requests</small></article>)}</div> : <p className="hrms-muted">No approved half-day leave recorded.</p>}
        </section>}
        <div className="hrms-table-wrap"><table><thead><tr><th>Dates</th><th>Type</th><th>Duration / session</th><th>Status</th><th>HR note</th><th>Action</th></tr></thead>
          <tbody>{filtered.filter(x => applicationTab === 'pending' ? x.status === 'pending' : x.status !== 'pending').map(item => <tr key={item.id}>
            <td>{item.from_date} → {item.to_date}</td><td>{statusName(item.leave_type)}</td>
            <td>{leaveSession(item)} · {leaveDays(item)} day{leaveDays(item) === 1 ? '' : 's'}{officeTimeLabel(item)}</td>
            <td><Badge status={item.status}/>{item.cancellation_status === 'pending' && <small> · Cancellation awaiting HR</small>}{item.cancellation_status === 'rejected' && <small> · Cancellation declined</small>}</td>
            <td>{item.decision_note || '—'}</td>
            <td><div className="hrms-actions">
              {item.status === 'pending' && <><button type="button" disabled={busy} className="hrms-small" onClick={() => editPending(item)}>Edit</button><button type="button" disabled={busy} className="hrms-small" onClick={() => void withdraw(item.id)}>Withdraw</button></>}
              {item.status === 'approved' && !item.cancellation_status && <button type="button" disabled={busy} className="hrms-small" onClick={() => void requestApprovedCancellation(item.id)}>Request cancellation</button>}
            </div></td>
          </tr>)}</tbody></table>
          {!filtered.some(x => applicationTab === 'pending' ? x.status === 'pending' : x.status !== 'pending') && <div className="hrms-empty">No {applicationTab} applications.</div>}
        </div>
      </>}
    </section>}
    {mode === 'calendar' && user?.role === 'employee' && <section className="hrms-panel">
      <h2>My leave records</h2>
      <p className="hrms-muted">Approved and pending periods are shown below. Cancel pending requests if your plans change.</p>
      <div className="hrms-leave-calendar-layout"><div><MonthNavigator month={calendarMonth} onChange={setCalendarMonth}/>
      <MonthCalendar month={calendarMonth} leaves={requests} holidays={holidays} /></div>
      <aside className="hrms-transaction-side"><h3>Leave transactions ({filtered.filter(r => r.from_date.startsWith(calendarMonth) || r.to_date.startsWith(calendarMonth)).length})</h3>
        {filtered.filter(r => r.from_date.startsWith(calendarMonth) || r.to_date.startsWith(calendarMonth)).slice(0, 6).map(r => <div className="hrms-transaction-row" key={r.id}><div><strong>{statusName(r.leave_type)}</strong><small>{r.from_date} → {r.to_date}</small></div><Badge status={r.status}/></div>)}
        {!filtered.some(r => r.from_date.startsWith(calendarMonth) || r.to_date.startsWith(calendarMonth)) && <div className="hrms-muted">No leave transactions this month.</div>}
      </aside></div>
      <div className="hrms-table-wrap"><table><thead><tr><th>Dates</th><th>Type</th><th>Days*</th><th>Status</th><th>HR note</th><th>Action</th></tr></thead>
      <tbody>{filtered.map(item => <tr key={item.id}><td>{item.from_date} → {item.to_date}</td><td>{statusName(item.leave_type)}{item.duration === 'half_day' ? ` · ${leaveSession(item)}${officeTimeLabel(item)}` : ''}</td><td>{leaveDays(item)}</td><td><Badge status={item.status}/>{item.cancellation_status === 'pending' && <small> · Cancellation awaiting HR</small>}</td><td>{item.decision_note || '—'}</td><td>{item.status === 'pending' && <button className="hrms-small" onClick={() => void withdraw(item.id)}>Withdraw</button>}</td></tr>)}</tbody></table>
      {filtered.length === 0 && <p>No leave applications yet.</p>}</div><p className="hrms-muted">* Provisional calendar days, not payroll leave deductions.</p>
    </section>}
    {mode === 'holidays' && <section className="hrms-panel hrms-reference-panel">
      <div className="hrms-row"><div><p className="hrms-section-eyebrow">INDIA · KARNATAKA</p><h2>Holiday Calendar</h2></div>
        <label className="hrms-year-selector">Year<select value={holidayYear} onChange={e => { const next = Number(e.target.value); setHolidayYear(next); setCalendarMonth(`${next}-01`) }}>
          {[year - 1, year, year + 1].filter(y => y >= 2026).map(y => <option key={y} value={y}>{y}</option>)}
        </select></label></div>
      <div className="hrms-gov-source"><div className="hrms-gov-icon"><CalendarDays size={25}/></div>
        <div><strong>National Portal of India — Karnataka Holiday Calendar</strong><p>Government holiday reference. The 2026 list is based on Karnataka notification DPAR 16 HHL 2025; it is not automatically a NakshaTech paid-leave entitlement.</p></div>
        <a href={KARNATAKA_GOV_CALENDAR_URL} target="_blank" rel="noopener noreferrer" className="hrms-source-link">Open official calendar <ArrowUpRight size={16}/></a></div>
      <div className="hrms-segmented" role="tablist" aria-label="Holiday calendar type">
        <button role="tab" type="button" aria-selected={holidayView === 'government'} className={holidayView === 'government' ? 'active' : ''} onClick={() => setHolidayView('government')}>Karnataka government reference</button>
        <button role="tab" type="button" aria-selected={holidayView === 'company'} className={holidayView === 'company' ? 'active' : ''} onClick={() => setHolidayView('company')}>HR-published company holidays</button>
      </div>
      {(() => { const selected = holidayView === 'government' ? (holidayYear === 2026 ? governmentHolidays2026 : []) : holidays
        return <>
          <YearHolidayTiles year={holidayYear} holidays={selected} onSelect={setCalendarMonth}/>
          <div className="hrms-month-summary"><h3>{new Date(`${calendarMonth}-01T00:00:00Z`).toLocaleDateString('en-IN',{month:'long',year:'numeric',timeZone:'UTC'})}</h3>
            <span>{selected.filter(h => h.date.startsWith(calendarMonth)).length} listed holidays</span></div>
          <MonthNavigator month={calendarMonth} onChange={setCalendarMonth}/>
          <MonthCalendar month={calendarMonth} leaves={[]} holidays={selected} governmentReference={holidayView === 'government'} />
          {holidayView === 'government' ? <p className="hrms-muted"><strong>Source note:</strong> This is a read-only 2026 notification reference, not a live API sync. Religious dates can be amended. For other years, open the official government site. HR must separately approve the actual company calendar.</p> : <p className="hrms-muted">Company holidays come only from HR's verified and published records. No government-reference date is automatically applied to leave balances.</p>}
          {!selected.length && <div className="hrms-empty">{holidayView === 'government' ? 'No verified embedded government list for this year. Open the official government calendar above.' : 'HR has not published holidays for this year yet.'}</div>}
        </> })()}
    </section>}
  </main>
}

export function AttendancePage() {
  const { user } = useAuth()
  const [month, setMonth] = useState(todayIST().slice(0, 7))
  const [data, setData] = useState<AttendanceResponse | null>(null)
  const [reasonDate, setReasonDate] = useState(todayIST())
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const load = useCallback(async () => { try { setData(await apiFetch<AttendanceResponse>(`/hrms/me/attendance?month=${month}`)); setError('') } catch (err) { setError(errorText(err)) } }, [month])
  useEffect(() => { void load() }, [load])
  const today = data?.punches.find(p => p.work_date === todayIST())
  async function punch(action: 'check-in' | 'check-out') {
    setBusy(true); setError(''); setNotice('')
    try { await apiFetch(`/hrms/me/${action}`, { method: 'POST' }); setNotice(`Successfully recorded ${action.replace('-', ' ')} on the server.`); await load() }
    catch (err) { setError(errorText(err)) } finally { setBusy(false) }
  }
  async function submitExplanation(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(''); setNotice('')
    try { await apiFetch('/hrms/me/absence', { method: 'POST', body: JSON.stringify({ work_date: reasonDate, reason }) }); setNotice('Your explanation has been submitted to HR.'); setReason(''); await load() }
    catch (err) { setError(errorText(err)) } finally { setBusy(false) }
  }
  if (user?.role !== 'employee') {
  return (
    <main className="hrms-page">
      <section className="hrms-panel">
        <h2>Employee Self-Service</h2>
        <p>
          Personal attendance is available only through individual employee accounts.
        </p>
      </section>
    </main>
  )
}

return <main className="hrms-page">
    <Header title="My Attendance" description="Attendance is recorded only when you actively check in or check out through the ERP website."/>
    <Failure message={error}/><Success message={notice}/>
    <section className="hrms-panel"><h2>Today's attendance · {todayIST()}</h2>
      <div className="hrms-actions"><button className="hrms-primary" disabled={busy || Boolean(today)} onClick={() => void punch('check-in')}><LogIn size={17}/> Check in</button>
      <button className="hrms-secondary" disabled={busy || !today || Boolean(today.check_out_utc)} onClick={() => void punch('check-out')}><LogOut size={17}/> Check out</button></div>
      <p className="hrms-muted">{today ? `Checked in: ${fmt(today.check_in_utc)} · Checked out: ${fmt(today.check_out_utc)}` : 'No check-in recorded today.'} Timestamps are recorded by the server in UTC and displayed in IST. No location or biometric tracking is collected.</p>
    </section>
    <section className="hrms-panel"><div className="hrms-row"><h2>Attendance history</h2><label>Month <input type="month" value={month} onChange={e => setMonth(e.target.value)}/></label></div>
      <div className="hrms-table-wrap"><table><thead><tr><th>Date</th><th>Check in (IST)</th><th>Check out (IST)</th><th>Status</th></tr></thead>
        <tbody>{data?.punches.map(p => <tr key={p.id}><td>{p.work_date}</td><td>{fmt(p.check_in_utc)}</td><td>{fmt(p.check_out_utc)}</td><td><Badge status={p.check_out_utc ? 'checked_out' : 'checked_in'}/></td></tr>)}</tbody></table>
        {!data?.punches.length && <p>No web check-in records for this month.</p>}</div>
    </section>
    <section className="hrms-panel"><h2>Absence / missing attendance explanation</h2>
      <p className="hrms-muted">If you were absent or forgot to punch, submit a reason. HR reviews the explanation; it does not manufacture check-in/out timestamps.</p>
      <form onSubmit={e => void submitExplanation(e)} className="hrms-form"><label>Date<input type="date" required max={todayIST()} value={reasonDate} onChange={e => setReasonDate(e.target.value)}/></label>
      <label className="hrms-form-wide">Reason<textarea required minLength={5} maxLength={1500} rows={3} value={reason} onChange={e => setReason(e.target.value)} placeholder="Why were you absent, or why was attendance not recorded?"/></label>
      <button className="hrms-primary" disabled={busy}>Send to HR</button></form>
      {data?.explanations.map(x => <p key={x.id} className="hrms-explanation"><strong>{x.work_date}</strong> · <Badge status={x.status}/> · {x.reason}</p>)}
    </section>
  </main>
}

export function HRManagementPage() {
  const [day, setDay] = useState(todayIST())
  const [data, setData] = useState<HROverview | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [filter, setFilter] = useState('')
  const [busy, setBusy] = useState(false)
  const [alerts, setAlerts] = useState<HRNotices | null>(null)
  const [selectedEmployee, setSelectedEmployee] = useState<number | null>(null)
  const [history, setHistory] = useState<HRHistory | null>(null)
  const [selectedBalance, setSelectedBalance] = useState<LeaveBalanceResponse | null>(null)
  const [historyYear, setHistoryYear] = useState<string>('all')
  const [historyBusy, setHistoryBusy] = useState(false)
  // The company-wide policy is published once per year, not per employee.
  const [policyYear, setPolicyYear] = useState(new Date().getFullYear())
  const [policyReady, setPolicyReady] = useState(false)
  const [policy, setPolicy] = useState<CompanyLeavePolicy>({ year: new Date().getFullYear(), intern_monthly_days: 1, probation_first_six_month_days: 5, months_seven_to_twelve_extra_days: 0, full_time_annual_days: 15, working_weekdays: [0, 1, 2, 3, 4, 5], no_carry_forward: true })
  const [employmentRows, setEmploymentRows] = useState<EmploymentRow[]>([])
  const [selectedUsers, setSelectedUsers] = useState<number[]>([])
  const [employmentCategory, setEmploymentCategory] = useState<'intern' | 'staff'>('staff')
  const [verifiedJoiningDate, setVerifiedJoiningDate] = useState('')
  const [holiday, setHoliday] = useState({ holiday_date: '', name: '', region: 'Karnataka', category: 'state', official_source_url: KARNATAKA_GOV_CALENDAR_URL, hr_verified: false })
  const load = useCallback(async () => { try { setData(await apiFetch<HROverview>(`/hrms/hr/overview?day=${day}`)); setError('') } catch (err) { setError(errorText(err)) } }, [day])
  useEffect(() => { void load() }, [load])
  const loadAlerts = useCallback(async () => {
    try { setAlerts(await apiFetch<HRNotices>('/hrms/hr/leave-notifications')) }
    catch (err) { setError(errorText(err)) }
  }, [])
  useEffect(() => {
    void loadAlerts()
    const timer = window.setInterval(() => { void loadAlerts() }, 30000)
    return () => window.clearInterval(timer)
  }, [loadAlerts])
  const openHistory = useCallback(async (userId: number, yearFilter: string = 'all') => {
    setSelectedEmployee(userId); setHistoryBusy(true); setHistory(null); setSelectedBalance(null)
    try {
      const suffix = yearFilter === 'all' ? '' : `?year=${yearFilter}`
      const balanceYear = yearFilter === 'all' ? new Date().getFullYear() : Number(yearFilter)
      const [hist, bal] = await Promise.all([
        apiFetch<HRHistory>(`/hrms/hr/employees/${userId}/leave-history${suffix}`),
        apiFetch<LeaveBalanceResponse>(`/hrms/hr/employees/${userId}/balance?year=${balanceYear}`)
      ])
      setHistory(hist); setSelectedBalance(bal)
    } catch (err) { setError(errorText(err)) }
    finally { setHistoryBusy(false) }
  }, [])
  async function openLeaveNotice(item: HRNotice) {
    try {
      if (!item.is_read) await apiFetch(`/hrms/hr/leave-notifications/${item.leave_id}/read`, { method: 'POST' })
      await Promise.all([loadAlerts(), openHistory(item.user_id, historyYear)])
    } catch (err) { setError(errorText(err)) }
  }
  const filtered = useMemo(() => data?.employees.filter(e => `${e.name} ${e.department || ''} ${e.employee_id || ''}`.toLowerCase().includes(filter.toLowerCase())) ?? [], [data, filter])
  async function decide(kind: 'leave' | 'absence', id: number, status: 'approved' | 'rejected') {
    setBusy(true); setError(''); setNotice('')
    try { const note = window.prompt('Optional HR decision note:', '') ; if (note === null) return
      await apiFetch(`/hrms/hr/${kind}/${id}/decision`, { method: 'POST', body: JSON.stringify({ status, note }) })
      setNotice(`Request ${status}.`); await Promise.all([load(), loadAlerts()])
      if (selectedEmployee !== null) await openHistory(selectedEmployee, historyYear)
    } catch (err) { setError(errorText(err)) } finally { setBusy(false) }
  }
  async function decideCancellation(id: number, status: 'approved' | 'rejected') {
    const note = window.prompt(`Reason for ${status === 'approved' ? 'approving' : 'rejecting'} this cancellation:`, '')
    if (note === null) return
    setBusy(true); setError(''); setNotice('')
    try {
      await apiFetch(`/hrms/hr/leave/${id}/cancellation-decision`, { method: 'POST', body: JSON.stringify({ status, note }) })
      setNotice(status === 'approved' ? 'Leave cancellation approved. Leave balance will be recalculated.' : 'Cancellation rejected. Original leave remains approved.')
      await Promise.all([load(), loadAlerts()])
      if (selectedEmployee !== null) await openHistory(selectedEmployee, historyYear)
    } catch (err) { setError(errorText(err)) } finally { setBusy(false) }
  }
  const loadPolicy = useCallback(async (year: number) => {
    try {
      const response = await apiFetch<{ configured: boolean; policy: CompanyLeavePolicy | null }>(`/hrms/hr/policy?year=${year}`)
      setPolicyReady(response.configured)
      setPolicy(response.policy || { year, intern_monthly_days: 1, probation_first_six_month_days: 5, months_seven_to_twelve_extra_days: 0, full_time_annual_days: 15, working_weekdays: [0, 1, 2, 3, 4, 5], no_carry_forward: true })
    } catch (err) { setError(errorText(err)) }
  }, [])
  const loadEmployment = useCallback(async () => {
    try { setEmploymentRows(await apiFetch<EmploymentRow[]>('/hrms/hr/employees/classifications')) }
    catch (err) { setError(errorText(err)) }
  }, [])
  useEffect(() => { void loadPolicy(policyYear); void loadEmployment() }, [policyYear, loadPolicy, loadEmployment])
  async function saveCompanyPolicy(e: FormEvent) {
    e.preventDefault(); setBusy(true); setNotice(''); setError('')
    try {
      const result = await apiFetch<{ policy: CompanyLeavePolicy }>('/hrms/hr/policy', { method: 'PUT', body: JSON.stringify({ ...policy, year: policyYear }) })
      setPolicy(result.policy); setPolicyReady(true)
      setNotice(`Company policy saved for ${policyYear}. Employee leave balances calculate automatically once categories are assigned.`)
    } catch (err) { setError(errorText(err)) } finally { setBusy(false) }
  }
  async function assignEmployment(e: FormEvent) {
    e.preventDefault(); if (!selectedUsers.length) { setError('Select at least one employee first.'); return }
    setBusy(true); setNotice(''); setError('')
    try {
      const result = await apiFetch<{ saved: number }>('/hrms/hr/employees/classifications/bulk', {
        method: 'PUT', body: JSON.stringify({ user_ids: selectedUsers, employment_category: employmentCategory, joining_date: verifiedJoiningDate || null })
      })
      setNotice(`${result.saved} employee classifications saved. Leave balances will now use company policy.`)
      setSelectedUsers([]); await loadEmployment()
    } catch (err) { setError(errorText(err)) } finally { setBusy(false) }
  }
  async function addHoliday(e: FormEvent) {
    e.preventDefault(); setBusy(true); setNotice(''); setError('')
    try { await apiFetch('/hrms/hr/holidays', { method: 'POST', body: JSON.stringify({ ...holiday, official_source_url: holiday.official_source_url || null }) }); setNotice('Holiday saved; employees can view the source and verification status.') }
    catch (err) { setError(errorText(err)) } finally { setBusy(false) }
  }
  return <main className="hrms-page">
    <Header hr title="HR Leave & Attendance" description="Company-wide attendance monitoring, absence explanations, leave approvals and policy administration."/>
    <Failure message={error}/><Success message={notice}/>
    <section className="hrms-panel hrms-alert-panel" aria-label="HR leave notifications">
      <div className="hrms-row"><h2><Bell size={19}/> Employee leave notifications</h2>
        <span className="hrms-notice-count" aria-live="polite">{alerts?.unread_count ?? 0} new · {alerts?.pending_count ?? 0} pending</span></div>
      <p className="hrms-muted">New employee leave requests appear here when HR opens the dashboard; the list checks for updates every 30 seconds.</p>
      <div className="hrms-notice-list">
        {alerts?.notifications.map(item => <button type="button" key={item.leave_id} className={`hrms-notice-item ${item.is_read ? 'read' : 'unread'}`}
          onClick={() => void openLeaveNotice(item)}>
          <span><strong>{item.employee_name}</strong><small>{statusName(item.leave_type)} · {item.from_date} → {item.to_date}</small></span>
          <span className="hrms-notice-state">{item.is_read ? 'View employee' : 'New request · View'}</span>
        </button>)}
        {!alerts?.notifications.length && <div className="hrms-empty">No pending employee leave notifications.</div>}
      </div>
    </section>
    <section className="hrms-panel"><div className="hrms-row"><h2>Attendance register</h2><label>Reporting date<input type="date" value={day} onChange={e => setDay(e.target.value)}/></label></div>
      <p className="hrms-muted">{data?.notice} Only authenticated active ERP accounts are included; Employee Master staff without accounts need account linking.</p>
      <div className="hrms-grid">{[
        ['Active ERP accounts', data?.employees.length ?? 0],
        ['Checked in/out', data?.employees.filter(x => ['checked_in', 'checked_out'].includes(x.status)).length ?? 0],
        ['Approved leave', data?.employees.filter(x => x.status === 'on_approved_leave').length ?? 0],
        ['No punch recorded', data?.employees.filter(x => x.status === 'no_punch_recorded').length ?? 0],
      ].map(([name, value]) => <article className="hrms-metric" key={String(name)}><span>{name}</span><strong>{value}</strong></article>)}</div>
      <label>Search employees<input placeholder="Name, department, employee ID" value={filter} onChange={e => setFilter(e.target.value)}/></label>
      <div className="hrms-table-wrap"><table><thead><tr><th>Employee</th><th>Department</th><th>Status</th><th>Check in / out (IST)</th><th>Explanation</th></tr></thead>
      <tbody>{filtered.map(e => <tr key={e.user_id}><td><button type="button" className="hrms-employee-link" onClick={() => void openHistory(e.user_id, historyYear)}>
        <strong>{e.name}</strong><small>{e.employee_id || `User ${e.user_id}`}</small></button></td><td>{e.department || '—'}</td><td><Badge status={e.status}/></td><td>{fmt(e.check_in_utc)}<br/>{fmt(e.check_out_utc)}</td><td>{e.absence_reason || 'Not provided'} {e.explanation_status && <Badge status={e.explanation_status}/>}</td></tr>)}</tbody></table></div>
    </section>
    {selectedEmployee !== null && <section className="hrms-panel hrms-history-panel" id="hrms-employee-history" aria-label="Employee leave history">
      <div className="hrms-row"><h2><History size={19}/> {history?.employee.name ?? 'Loading employee'} — Leave history</h2>
        <div className="hrms-actions"><label>Period<select value={historyYear} onChange={e => { setHistoryYear(e.target.value); void openHistory(selectedEmployee, e.target.value) }}>
          <option value="all">All years</option>{[new Date().getFullYear()-2,new Date().getFullYear()-1,new Date().getFullYear()].map(y => <option key={y} value={String(y)}>{y}</option>)}</select></label>
          <button type="button" className="hrms-secondary" onClick={() => { setSelectedEmployee(null); setHistory(null) }}>Close</button></div></div>
      {historyBusy && <p className="hrms-muted">Loading leave history…</p>}
      {history && <><p className="hrms-muted">{history.employee.department ?? 'Department not assigned'} · {history.employee.employee_id ?? `User ${history.employee.user_id}`}</p>
        <div className="hrms-grid">{[
          ['Total leave requests', history.summary.total_requests],
          ['Approved requests', history.summary.approved_requests],
          ['Approved calendar days*', history.summary.approved_calendar_days],
          ['Pending requests', history.summary.pending_requests],
          ['Rejected requests', history.summary.rejected_requests],
        ].map(([title, value]) => <article className="hrms-metric" key={String(title)}><span>{title}</span><strong>{value}</strong></article>)}</div>
        {selectedBalance && <div className="hrms-grid">{selectedBalance.balances.filter(b => b.leave_type === 'paid').map(b => <article key={b.leave_type} className="hrms-metric"><span>Paid leave remaining · {selectedBalance.year}</span><strong>{b.remaining_provisional ?? 'Unconfigured'}</strong><small>Granted: {b.entitled ?? '—'} · Used working days: {b.approved_chargeable_days ?? b.approved_calendar_days} · Pending: {b.pending_chargeable_days ?? b.pending_calendar_days}</small></article>)}</div>}
        <p className="hrms-muted">* Full-day leave uses the existing HR policy; half-day leave counts as 0.5 day per approved request. Office times are planned, not verified attendance punches.</p>
        {halfDayMonthlyTotals(history.requests).length > 0 && <div className="hrms-grid">{halfDayMonthlyTotals(history.requests).map(m => <article className="hrms-metric" key={m.month}><span>{m.month} approved half-days</span><strong>{m.days} day{m.days === 1 ? '' : 's'}</strong><small>{m.count} half-day requests in this month</small></article>)}</div>}
        <div className="hrms-table-wrap"><table><thead><tr><th>Leave dates</th><th>Type</th><th>Days*</th><th>Reason</th><th>Status</th><th>HR note</th></tr></thead>
          <tbody>{history.requests.map(item => <tr key={item.id}><td>{item.from_date} → {item.to_date}</td><td>{statusName(item.leave_type)}{item.duration === 'half_day' ? ` · ${leaveSession(item)}${officeTimeLabel(item)}` : ''}</td><td>{leaveDays(item)}</td><td>{item.reason}</td><td><Badge status={item.status}/>{item.cancellation_status === 'pending' && <small> · Cancellation awaiting HR</small>}</td><td>{item.decision_note ?? '—'}</td></tr>)}</tbody></table></div>
        {history.requests.length === 0 && <div className="hrms-empty">No recorded leave applications for this employee.</div>}
      </>}
    </section>}
    <section className="hrms-panel"><h2>Pending leave applications</h2><div className="hrms-table-wrap"><table><thead><tr><th>Employee</th><th>Period</th><th>Leave type</th><th>Reason</th><th>Decision</th></tr></thead>
      <tbody>{data?.pending_leaves.map(x => <tr key={x.id}><td><button type="button" className="hrms-employee-link" onClick={() => void openHistory(x.user_id, historyYear)}>{x.employee_name}</button></td><td>{x.from_date} → {x.to_date}<small>{leaveDays(x)} provisional day(s){x.duration === 'half_day' ? ` · ${leaveSession(x)}${officeTimeLabel(x)}` : ''}</small></td><td>{statusName(x.leave_type)}</td><td>{x.reason}</td><td><div className="hrms-actions"><button disabled={busy} onClick={() => void decide('leave', x.id, 'approved')} className="hrms-small">Approve</button><button disabled={busy} onClick={() => void decide('leave', x.id, 'rejected')} className="hrms-small">Reject</button></div></td></tr>)}</tbody></table>
      {!data?.pending_leaves.length && <p>No pending leave applications.</p>}</div></section>
    {Boolean(data?.pending_cancellations?.length) && <section className="hrms-panel" aria-label="Approved leave cancellation requests">
      <h2>Approved leave cancellation requests</h2>
      <p className="hrms-muted">The original leave remains approved and charged until HR accepts cancellation. Approval restores its leave entitlement through backend recalculation.</p>
      <div className="hrms-table-wrap"><table><thead><tr><th>Employee</th><th>Leave dates</th><th>Duration</th><th>Decision</th></tr></thead><tbody>
        {data?.pending_cancellations?.map(item => <tr key={item.id}><td>{item.employee_name ?? `User ${item.user_id}`}</td><td>{item.from_date} → {item.to_date}</td><td>{leaveSession(item)} · {leaveDays(item)} day(s){officeTimeLabel(item)}</td>
          <td><div className="hrms-actions"><button type="button" disabled={busy} className="hrms-small" onClick={() => void decideCancellation(item.id, 'approved')}>Accept cancellation</button><button type="button" disabled={busy} className="hrms-small" onClick={() => void decideCancellation(item.id, 'rejected')}>Reject cancellation</button></div></td></tr>)}
      </tbody></table></div>
    </section>}
    <section className="hrms-panel"><h2>Pending attendance explanations</h2><div className="hrms-table-wrap"><table><thead><tr><th>Employee</th><th>Date</th><th>Reason</th><th>Decision</th></tr></thead><tbody>{data?.pending_explanations.map(x => <tr key={x.id}><td>{x.employee_name}</td><td>{x.work_date}</td><td>{x.reason}</td><td><div className="hrms-actions"><button disabled={busy} onClick={() => void decide('absence', x.id, 'approved')} className="hrms-small">Approve</button><button disabled={busy} onClick={() => void decide('absence', x.id, 'rejected')} className="hrms-small">Reject</button></div></td></tr>)}</tbody></table>
      {!data?.pending_explanations.length && <p>No pending explanations.</p>}</div></section>
    <div className="hrms-two-col">
      <section className="hrms-panel" aria-label="Company-wide automatic leave policy">
        <div className="hrms-row"><div><h2>Company-wide Leave Policy</h2><p className="hrms-muted">Configure once for every category; no per-employee entitlement entry required.</p></div>
          <span className="hrms-notice-count">{policyReady ? 'Saved policy' : 'Not published'}</span></div>
        <p className="hrms-muted">The latest saved policy continues into future years until HR publishes a newer one. Paid leave does not carry forward between full-time calendar years.</p>
        <p className="hrms-muted">HR policy values are for local HR review. Verify contractual and statutory leave rules before payroll or production use. Full-time calendar-year carry-forward is disabled.</p>
        <form className="hrms-form" onSubmit={e => void saveCompanyPolicy(e)}>
          <label>Policy year<input type="number" min="2020" max="2100" value={policyYear} onChange={e => setPolicyYear(Number(e.target.value))}/></label>
          <label>Intern days per completed month<input type="number" min="0" max="31" required value={policy.intern_monthly_days} onChange={e => setPolicy({ ...policy, intern_monthly_days: Number(e.target.value) })}/></label>
          <label>First 6 months paid leave<input type="number" min="0" max="31" required value={policy.probation_first_six_month_days} onChange={e => setPolicy({ ...policy, probation_first_six_month_days: Number(e.target.value) })}/></label>
          <label>Months 7–12 additional paid days<input type="number" min="0" max="31" required value={policy.months_seven_to_twelve_extra_days} onChange={e => setPolicy({ ...policy, months_seven_to_twelve_extra_days: Number(e.target.value) })}/></label>
          <label>After 1 year — annual paid leave<input type="number" min="0" max="366" required value={policy.full_time_annual_days} onChange={e => setPolicy({ ...policy, full_time_annual_days: Number(e.target.value) })}/></label>
          <fieldset className="hrms-weekday-field"><legend>Chargeable working weekdays</legend><div className="hrms-weekday-options">{['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map((day, index) => <label key={day}>
            <input type="checkbox" checked={policy.working_weekdays.includes(index)} onChange={e => setPolicy({ ...policy, working_weekdays: e.target.checked ? [...policy.working_weekdays, index].sort() : policy.working_weekdays.filter(d => d !== index) })}/>{day}
          </label>)}</div></fieldset>
          <div className="hrms-form-wide"><p className="hrms-muted">Approved HR company holidays are excluded when calculating chargeable days. Paid Leave, Casual, Sick and Earned leave share the same paid leave pool; Unpaid leave is tracked separately.</p>
            <button className="hrms-primary" type="submit" disabled={busy || !policy.working_weekdays.length}>Save company-wide policy</button></div>
        </form>
      </section>
      <section className="hrms-panel" aria-label="Bulk employment category assignment">
        <div className="hrms-row"><h2>Assign Employee Categories — Bulk</h2><span className="hrms-notice-count">{selectedUsers.length} selected</span></div>
        <p className="hrms-muted">Choose employees and assign Intern or Staff. Staff automatically transitions from probation to 7–12 months to full-time using a verified joining date. Leave policy is applied to everyone assigned to the category.</p>
        <div className="hrms-row"><button type="button" className="hrms-secondary" onClick={() => setSelectedUsers(employmentRows.filter(row => row.role !== 'hr').map(row => row.user_id))}>Select all non-HR employees</button>
          <button type="button" className="hrms-secondary" onClick={() => setSelectedUsers([])}>Clear selection</button></div>
        <div className="hrms-selection-list">{employmentRows.filter(row => row.role !== 'hr').map(row => <label key={row.user_id} className="hrms-selection-row">
          <input type="checkbox" checked={selectedUsers.includes(row.user_id)} onChange={e => setSelectedUsers(e.target.checked ? [...selectedUsers, row.user_id] : selectedUsers.filter(id => id !== row.user_id))}/>
          <span><strong>{row.employee_name}</strong><small>{row.department || row.role} · {row.employment_category || 'Not assigned'} · Joined: {row.joining_date || 'Missing date'}</small></span>
        </label>)}</div>
        <form className="hrms-form" onSubmit={e => void assignEmployment(e)}>
          <label>Category<select value={employmentCategory} onChange={e => setEmploymentCategory(e.target.value as 'intern' | 'staff')}>
            <option value="staff">Staff — automatic service-based stages</option><option value="intern">Intern — monthly accrual</option></select></label>
          <label>Verified joining date (optional override)<input type="date" max={todayIST()} value={verifiedJoiningDate} onChange={e => setVerifiedJoiningDate(e.target.value)}/></label>
          <div className="hrms-form-wide"><p className="hrms-muted">Leave date blank to use each employee's recorded joining date. If any selected employee lacks one, assignment will be rejected until verified. A supplied date applies to EVERY selected employee.</p>
            <button className="hrms-primary" disabled={busy || !selectedUsers.length}>Apply classification to {selectedUsers.length} employees</button></div>
        </form>
      </section>
      <section className="hrms-panel"><h2>Publish official holiday</h2><p className="hrms-muted">Use a verified government notification, not an autogenerated date list. Confirm that it applies to NakshaTech before marking HR verified.</p>
        <form className="hrms-form" onSubmit={e => void addHoliday(e)}><label>Date<input required type="date" value={holiday.holiday_date} onChange={e => setHoliday({ ...holiday, holiday_date: e.target.value })}/></label>
          <label>Holiday name<input required minLength={2} maxLength={180} value={holiday.name} onChange={e => setHoliday({ ...holiday, name: e.target.value })}/></label>
          <label>Applicable region<input required value={holiday.region} onChange={e => setHoliday({ ...holiday, region: e.target.value })}/></label>
          <label>Category<select value={holiday.category} onChange={e => setHoliday({ ...holiday, category: e.target.value })}><option value="national">National</option><option value="state">State</option><option value="restricted">Restricted</option><option value="company">Company</option></select></label>
          <label className="hrms-form-wide">Official notification URL<input placeholder="https://..." type="url" value={holiday.official_source_url} onChange={e => setHoliday({ ...holiday, official_source_url: e.target.value })}/></label>
          <label className="hrms-form-wide"><input type="checkbox" checked={holiday.hr_verified} onChange={e => setHoliday({ ...holiday, hr_verified: e.target.checked })}/> HR has checked the official notification and company applicability</label>
          <button disabled={busy} className="hrms-primary">Save holiday</button></form></section>
    </div>
  </main>
}
