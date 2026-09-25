import { ArrowRight, Banknote, Download, Filter, RefreshCcw, Route, ShieldCheck, Users } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { StatCard } from '../../../components/StatCard'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch, downloadFile } from '../../../lib/api'
import type { TravelKmClaim, TravelKmDashboard } from '../travel-km-types'
import { km, money, statusTone, travelStatusLabels } from '../travel-km-utils'
import '../travel-km.css'

export function TravelKmStaffDashboardPage() {
  const { user } = useAuth()
  const [dashboard, setDashboard] = useState<TravelKmDashboard | null>(null)
  const [claims, setClaims] = useState<TravelKmClaim[]>([])
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  function load() {
    setLoading(true); setError('')
    const suffix = status ? `?status=${encodeURIComponent(status)}` : ''
    Promise.all([
      apiFetch<TravelKmDashboard>('/travel-km/dashboard'),
      apiFetch<TravelKmClaim[]>(`/travel-km/claims${suffix}`),
    ]).then(([summary, rows]) => { setDashboard(summary); setClaims(rows) })
      .catch(err => setError(err instanceof Error ? err.message : 'Could not load Travel KM dashboard'))
      .finally(() => setLoading(false))
  }
  useEffect(load, [status])

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return claims
    return claims.filter(item => [item.claim_code, item.employee_name, item.employee_email, item.department, item.project_code, item.project_name, item.client_name, item.purpose_description].some(value => String(value || '').toLowerCase().includes(q)))
  }, [claims, search])

  const title = user?.role === 'management' ? 'Management Travel Oversight' : user?.role === 'admin' ? 'Admin Travel Verification' : user?.role === 'hr' ? 'HR Travel Verification' : 'Finance Travel Approvals'
  const eyebrow = user?.role === 'management' ? 'MANAGEMENT · READ-ONLY VISIBILITY' : `${String(user?.role || '').toUpperCase()} · EMPLOYEE TRAVEL & KM`
  const description = user?.role === 'management'
    ? 'Visual oversight of every Employee → Admin → HR → Finance movement, travel KM, geo-evidence verification, final approval and monthly-salary inclusion status.'
    : 'Review project travel claims at your assigned approval stage while preserving the full workflow and audit history.'

  return <div className="travel-km-page">
    <DashboardHeader variant="ops" icon={Route} eyebrow={eyebrow} title={title} description={description} actions={<button className="travel-km-secondary" onClick={() => void downloadFile('/travel-km/reports.xlsx', 'NakshaTech Employee Travel KM Report.xlsx')}><Download size={16}/> Download Excel Report</button>} summary={<>
      <StatCard icon={ShieldCheck} label="Pending Admin" value={dashboard?.pending_admin || 0} tone="orange" note="Submitted employee claims"/>
      <StatCard icon={ShieldCheck} label="Pending HR" value={dashboard?.pending_hr || 0} tone="orange" note="Admin-verified claims"/>
      <StatCard icon={ShieldCheck} label="Pending Finance" value={dashboard?.pending_finance || 0} tone="orange" note="HR-approved claims"/>
      <StatCard icon={Banknote} label="Finance Approved" value={dashboard?.finance_approved_count ?? dashboard?.paid_count ?? 0} tone="green" note="Ready for monthly salary addition"/>
    </>} meta={<><span className="nk-meta-chip"><Route size={14}/> Admin → HR → Finance workflow</span><span className="nk-meta-chip"><Filter size={14}/> {status ? travelStatusLabels[status] || status : 'All statuses'}</span><span className="nk-meta-chip"><Users size={14}/> {claims.length} claims in view</span></>} />
    {error && <div className="travel-km-error">{error}</div>}
    {user?.role === 'management' && <div className="travel-km-readonly-banner"><ShieldCheck size={18}/><span>Management has complete read-only access to status, evidence, Admin/HR verification, final Finance approval and monthly-salary inclusion status. Approval actions remain with Admin, HR and Finance.</span></div>}

    <section className="travel-km-stat-grid">
      <article className="travel-km-stat"><span>Total Claims</span><strong>{dashboard?.total_claims || 0}</strong><small>All travel claims</small></article>
      <article className="travel-km-stat"><span>Total Travel</span><strong>{km(dashboard?.total_km)}</strong><small>Employee odometer KM</small></article>
      <article className="travel-km-stat"><span>Approved Allowance</span><strong>{money(dashboard?.approved_allowance)}</strong><small>After HR verification</small></article>
      <article className="travel-km-stat"><span>Approved for Salary</span><strong>{money(dashboard?.salary_approved_amount ?? dashboard?.paid_amount)}</strong><small>Finance-approved monthly allowance</small></article>
    </section>

    <section className="travel-km-panel"><div className="travel-km-inline"><Route size={18}/><div><span className="travel-km-kicker">WORKFLOW MOVEMENT</span><h2>Approval Pipeline</h2></div></div><div className="travel-km-workflow"><div className="travel-km-step done"><i>1</i><span>Employee Submitted<br/><b>{dashboard?.total_claims || 0}</b></span></div><div className="travel-km-step done"><i>2</i><span>Admin Queue<br/><b>{dashboard?.pending_admin || 0}</b></span></div><div className="travel-km-step done"><i>3</i><span>HR Queue<br/><b>{dashboard?.pending_hr || 0}</b></span></div><div className="travel-km-step done"><i>4</i><span>Finance Queue<br/><b>{dashboard?.pending_finance || 0}</b></span></div><div className="travel-km-step done"><i>5</i><span>Finance Approved<br/><b>{dashboard?.finance_approved_count ?? dashboard?.paid_count ?? 0}</b></span></div></div></section>

    <section className="travel-km-panel"><div className="travel-km-inline"><Filter size={17}/><div><span className="travel-km-kicker">FILTER & REVIEW</span><h2>Travel Claims</h2></div></div><div className="travel-km-filter-row" style={{margin:'13px 0'}}><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search employee, project, claim, purpose..."/><select value={status} onChange={e => setStatus(e.target.value)}><option value="">All statuses</option><option value="submitted">Pending Admin</option><option value="admin_approved">Pending HR</option><option value="hr_approved">Pending Finance</option><option value="admin_sent_back">Admin Sent Back</option><option value="hr_sent_back">HR Sent Back</option><option value="finance_approved">Finance Approved</option><option value="paid">Legacy Completed</option><option value="admin_rejected">Admin Rejected</option><option value="hr_rejected">HR Rejected</option><option value="finance_rejected">Finance Rejected</option></select></div>{loading ? <div className="travel-km-empty">Loading workflow...</div> : visible.length === 0 ? (claims.length === 0 ? <div className="nk-empty"><span className="nk-empty-icon"><Route size={22}/></span><h3>No travel claims yet</h3><p>Employee project travel shows up here as soon as claims are submitted for Admin, HR and Finance verification.</p></div> : <div className="nk-empty"><span className="nk-empty-icon"><Filter size={22}/></span><h3>No claims match this view</h3><p>All {claims.length} claims are hidden by the current status filter or search. Clear them to see the full queue.</p><div className="nk-empty-action"><button className="travel-km-secondary" onClick={() => { setSearch(''); setStatus('') }}>Clear filters</button></div></div>) : <div className="travel-km-table-wrap"><table className="travel-km-table"><thead><tr><th>Claim / Employee</th><th>Project</th><th>Travel</th><th>KM</th><th>Allowance</th><th>Status</th><th></th></tr></thead><tbody>{visible.map(claim => <tr key={claim.id}><td><strong>{claim.claim_code}</strong><small style={{display:'block'}}>{claim.employee_name} · {claim.department || 'No department'}</small></td><td>{claim.project_code}<small style={{display:'block'}}>{claim.project_name}</small></td><td>{claim.travel_date}<small style={{display:'block'}}>{claim.purpose_description}</small></td><td>{km(claim.final_eligible_km ?? claim.odometer_km)}</td><td>{money(claim.final_allowance ?? claim.calculated_allowance)}</td><td><span className={`travel-km-status ${statusTone(claim.status)}`}>{travelStatusLabels[claim.status] || claim.status}</span></td><td><Link className="travel-km-secondary" to={`/travel-km/${claim.id}`}>Open <ArrowRight size={14}/></Link></td></tr>)}</tbody></table></div>}</section>

    <section className="travel-km-summary-grid">
      <article className="travel-km-panel"><div className="travel-km-inline"><Route size={17}/><h3>Project-wise Travel</h3></div><div className="travel-km-summary-list" style={{marginTop:12}}>{dashboard?.project_summary.slice(0,8).map(row => <div className="travel-km-summary-row" key={row.name}><strong>{row.name}</strong><span>{km(row.km)}</span><span>{money(row.allowance)}</span></div>) || null}</div></article>
      <article className="travel-km-panel"><div className="travel-km-inline"><Users size={17}/><h3>Employee-wise Travel</h3></div><div className="travel-km-summary-list" style={{marginTop:12}}>{dashboard?.employee_summary.slice(0,8).map(row => <div className="travel-km-summary-row" key={row.name}><strong>{row.name}</strong><span>{km(row.km)}</span><span>{money(row.allowance)}</span></div>) || null}</div></article>
      <article className="travel-km-panel"><div className="travel-km-inline"><Banknote size={17}/><h3>Monthly Salary Allowance</h3></div><div className="travel-km-summary-list" style={{marginTop:12}}>{dashboard?.monthly_summary.slice(0,8).map(row => <div className="travel-km-summary-row" key={row.name}><strong>{row.name}</strong><span>{km(row.km)}</span><span>{money(row.allowance)}</span></div>) || null}</div></article>
    </section>
  </div>
}
