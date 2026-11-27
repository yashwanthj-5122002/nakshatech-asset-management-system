import { useEffect, useMemo, useState } from 'react'
import { Clock3, ContactRound, IndianRupee, RefreshCw, Search, UsersRound, LockKeyhole } from 'lucide-react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { StatCard } from '../../../components/StatCard'
import { apiFetch } from '../../../lib/api'
import '../operations.css'
import './bd-my-team.css'

type CountName = 'prospects'|'clients'|'closed'|'contacted'|'responded'|'activities'|'enquiries'|'pending_followups'|'overdue_followups'
type Metrics = Record<CountName,number> & {confirmed_projects:number;confirmed_sales_value:number|null}
type EmployeeRow = Metrics & {user_id:number;employee_id:string;name:string;email:string;active:boolean}
type TeamResponse = {
  start_date:string;end_date:string;employee_count:number;employees:EmployeeRow[];
  summary:Metrics;official_attribution:'verified_project_value'|'partial'|'not_linked'
}
type Lead = {id:number;company_name:string;source:string;contact_person:string|null;contact_email:string|null;service_interest:string|null;status:string;next_followup_date:string|null;created_at:string}
type ContactEvent = {id:number;prospect_id:number;company_name:string;channel:string;outcome:string;remarks:string|null;contacted_at:string}
type Page<T> = {total:number;offset:number;items:T[]}
type Details = {employee:{id:string;name:string;email:string};period:{start_date:string;end_date:string};prospects:Page<Lead>;activities:Page<ContactEvent>}
type Period = 'today'|'week'|'month'|'30days'|'year'|'custom'
const PAGE_LIMIT = 25
const employeeIds = Array.from({length:5},(_,i)=>`BD${String(i+1).padStart(2,'0')}`)

function isoDate(date:Date):string {
  const year=date.getFullYear()
  return `${year}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`
}
function dateRange(period:Period, customStart:string, customEnd:string) {
  const today=new Date()
  const end=isoDate(today)
  const first=new Date(today.getFullYear(),today.getMonth(),today.getDate())
  if(period==='today') return {start:end,end}
  if(period==='week') { first.setDate(first.getDate()-((first.getDay()+6)%7));return {start:isoDate(first),end} }
  if(period==='month') return {start:isoDate(new Date(first.getFullYear(),first.getMonth(),1)),end}
  if(period==='30days') {first.setDate(first.getDate()-29);return {start:isoDate(first),end}}
  if(period==='year') return {start:isoDate(new Date(first.getFullYear(),0,1)),end}
  return {start:customStart,end:customEnd}
}
function salesValue(value:number|null|undefined):string {
  if(value===null||value===undefined)return 'Not fully linked'
  return new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:2}).format(value)
}
function displayStatus(value:string):string {return value.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase())}
function displayDate(value:string|null):string {if(!value)return '—';return value.slice(0,10)}
function displayDateTime(value:string):string {return new Date(value.endsWith('Z')?value:`${value}Z`).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',dateStyle:'medium',timeStyle:'short'})}

export function BDMyTeamPage(){
  const [employeeId,setEmployeeId]=useState('all')
  const [period,setPeriod]=useState<Period>('month')
  const [customStart,setCustomStart]=useState(()=>isoDate(new Date(new Date().getFullYear(),new Date().getMonth(),1)))
  const [customEnd,setCustomEnd]=useState(()=>isoDate(new Date()))
  const [search,setSearch]=useState('')
  const [refresh,setRefresh]=useState(0)
  const [team,setTeam]=useState<TeamResponse|null>(null)
  const [busy,setBusy]=useState(true)
  const [error,setError]=useState('')
  const [openEmployee,setOpenEmployee]=useState<string|null>(null)
  const [details,setDetails]=useState<Details|null>(null)
  const [detailsError,setDetailsError]=useState('')
  const [prospectsOffset,setProspectsOffset]=useState(0)
  const [activitiesOffset,setActivitiesOffset]=useState(0)
  const [detailsLoading,setDetailsLoading]=useState(false)
  const range=useMemo(()=>dateRange(period,customStart,customEnd),[period,customStart,customEnd])
  const invalidRange=!range.start||!range.end||range.start>range.end
  const qs=useMemo(()=>{
    const q=new URLSearchParams({start_date:range.start,end_date:range.end})
    if(employeeId!=='all')q.set('employee_id',employeeId)
    return q.toString()
  },[range.start,range.end,employeeId])

  useEffect(()=>{
    if(invalidRange){setError('Choose a valid start and end date.');setTeam(null);setBusy(false);return}
    const ctrl=new AbortController()
    setBusy(true);setError('')
    void apiFetch<TeamResponse>(`/bd-employee/manager/team?${qs}`,{signal:ctrl.signal})
      .then(x=>{if(!ctrl.signal.aborted)setTeam(x)})
      .catch(err=>{if(!ctrl.signal.aborted){setError(err instanceof Error?err.message:'Unable to load team');setTeam(null)}})
      .finally(()=>{if(!ctrl.signal.aborted)setBusy(false)})
    return ()=>ctrl.abort()
  },[qs,refresh,invalidRange])

  useEffect(()=>{setOpenEmployee(null);setDetails(null);setProspectsOffset(0);setActivitiesOffset(0)},[qs])

  useEffect(()=>{
    if(!openEmployee||invalidRange)return
    const ctrl=new AbortController()
    setDetailsLoading(true);setDetailsError('')
    const params=new URLSearchParams({start_date:range.start,end_date:range.end,prospects_offset:String(prospectsOffset),activities_offset:String(activitiesOffset),limit:String(PAGE_LIMIT)})
    void apiFetch<Details>(`/bd-employee/manager/team/${encodeURIComponent(openEmployee)}/details?${params}`,{signal:ctrl.signal})
      .then(x=>{if(!ctrl.signal.aborted)setDetails(x)})
      .catch(err=>{if(!ctrl.signal.aborted){setDetailsError(err instanceof Error?err.message:'Unable to load details');setDetails(null)}})
      .finally(()=>{if(!ctrl.signal.aborted)setDetailsLoading(false)})
    return ()=>ctrl.abort()
  },[openEmployee,range.start,range.end,prospectsOffset,activitiesOffset,refresh,invalidRange])

  const listed=(team?.employees??[]).filter(row=>`${row.employee_id} ${row.name}`.toLowerCase().includes(search.trim().toLowerCase()))
  const summary=team?.summary
  function showEmployee(id:string){setOpenEmployee(openEmployee===id?null:id);setDetails(null);setProspectsOffset(0);setActivitiesOffset(0)}

  return <div className="operations-page bdmt-page">
    <DashboardHeader variant="ops" icon={UsersRound} eyebrow="BUSINESS DEVELOPMENT · MY TEAM" title="My Team" description="Employee-wise outreach, client responses and follow-ups from the five BD test accounts." actions={<button type="button" className="operations-button secondary" onClick={()=>setRefresh(v=>v+1)}><RefreshCw size={16}/> Refresh</button>} meta={<><span className="nk-meta-chip"><UsersRound size={14}/> BD01–BD05</span><span className="nk-meta-chip"><Clock3 size={14}/> Reporting dates: India (IST)</span></>}/>

    <section className="operations-panel bdmt-filters" aria-label="Team filters">
      <div className="bdmt-filter-grid">
        <label>Employee<select value={employeeId} onChange={e=>setEmployeeId(e.target.value)}><option value="all">All Employees</option>{employeeIds.map(id=><option key={id} value={id}>{id}</option>)}</select></label>
        <label>Time Period<select value={period} onChange={e=>setPeriod(e.target.value as Period)}><option value="today">Today</option><option value="week">This Week</option><option value="month">This Month</option><option value="30days">Last 30 Days</option><option value="year">This Year</option><option value="custom">Custom Date Range</option></select></label>
        {period==='custom'&&<><label>From<input type="date" value={customStart} onChange={e=>setCustomStart(e.target.value)}/></label><label>To<input type="date" value={customEnd} onChange={e=>setCustomEnd(e.target.value)}/></label></>}
      </div>
      <p className="bdmt-hint">Prospects includes all leads added in the period, even if converted. Total Clients counts actual registered BD clients created in the period. Closed is a prospect status, not a confirmed project sale.</p>
    </section>

    {error&&<div className="operations-alert error" role="alert">{error}</div>}
    {busy&&<section className="operations-panel"><div className="operations-empty">Loading team performance…</div></section>}
    {!busy&&team&&<>
      <section className="operations-stats-grid" aria-label="Team performance summary">
        <StatCard icon={UsersRound} label="Prospects Added" value={summary?.prospects??0} note="New prospects in selected period"/>
        <StatCard icon={ContactRound} label="Clients Contacted" value={summary?.contacted??0} note="Unique prospects contacted" tone="teal"/>
        <StatCard icon={UsersRound} label="Total Clients" value={summary?.clients??0} note="Registered BD clients in period" tone="green"/>
        <StatCard icon={LockKeyhole} label="Closed" value={summary?.closed??0} note="Current status: Won or Not Interested" tone="orange"/>
        <StatCard icon={IndianRupee} label="Total Sales" value={salesValue(summary?.confirmed_sales_value)} note="Confirmed BD project value, not payments" tone="purple"/>
      </section>
      <section className="operations-panel bdmt-register">
        <header><div><span className="operations-kicker">TEAM PERFORMANCE</span><h2>Employee Overview</h2><p>{team.employee_count} employee{team.employee_count===1?'':'s'} · {range.start} to {range.end}</p></div></header>
        <label className="bdmt-search"><Search size={16}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search employee name or ID" aria-label="Search employee name or ID"/></label>
        <div className="bdmt-table-scroll"><table className="bdmt-table"><thead><tr><th>Employee</th><th>Prospects</th><th>Contacted</th><th>Total Clients</th><th>Closed</th><th>Total Sales</th><th>Details</th></tr></thead><tbody>
          {listed.map(row=><tr key={row.user_id}><td><strong>{row.employee_id}</strong><small>{row.name}</small>{!row.active&&<small className="bdmt-inactive">Inactive</small>}</td><td>{row.prospects}</td><td>{row.contacted}</td><td>{row.clients}</td><td>{row.closed}</td><td className={row.confirmed_sales_value===null?'bdmt-unlinked':undefined}>{salesValue(row.confirmed_sales_value)}</td><td><button type="button" className="operations-button secondary" onClick={()=>showEmployee(row.employee_id)} aria-expanded={openEmployee===row.employee_id}>{openEmployee===row.employee_id?'Hide':'View'}</button></td></tr>)}
          {!listed.length&&<tr><td colSpan={7} className="bdmt-no-data">No matching employees found.</td></tr>}
        </tbody></table></div>
      </section>
      {openEmployee&&<section className="operations-panel bdmt-detail" aria-label={`${openEmployee} detailed activity`}>
        <header><div><span className="operations-kicker">EMPLOYEE DETAILS</span><h2>{openEmployee} · Full Activity</h2><p>Prospects and communication history recorded in the selected period.</p></div><button type="button" className="operations-button secondary" onClick={()=>setOpenEmployee(null)}>Close</button></header>
        {detailsError&&<div className="operations-alert error" role="alert">{detailsError}</div>}
        {detailsLoading&&<p className="bdmt-hint">Loading employee history…</p>}
        {details&&!detailsLoading&&<div className="bdmt-detail-columns">
          <div className="bdmt-sub-panel"><h3>Prospects ({details.prospects.total})</h3>{details.prospects.items.length?<div className="bdmt-list">{details.prospects.items.map(p=><article key={p.id}><div><strong>{p.company_name}</strong><span className="bdmt-status">{displayStatus(p.status)}</span></div><small>Source: {displayStatus(p.source)} · {displayDate(p.created_at)}</small><small>Contact: {p.contact_person||'Not provided'} · Service: {p.service_interest||'Not specified'}</small>{p.next_followup_date&&<small>Next follow-up: {displayDate(p.next_followup_date)}</small>}</article>)}</div>:<p className="bdmt-hint">No new prospects in this period.</p>}
            <div className="bdmt-pager"><button type="button" className="operations-button secondary" disabled={prospectsOffset===0} onClick={()=>setProspectsOffset(v=>Math.max(0,v-PAGE_LIMIT))}>Previous</button><small>{details.prospects.total?`${details.prospects.offset+1}–${Math.min(details.prospects.offset+PAGE_LIMIT,details.prospects.total)} of ${details.prospects.total}`:'0 of 0'}</small><button type="button" className="operations-button secondary" disabled={prospectsOffset+PAGE_LIMIT>=details.prospects.total} onClick={()=>setProspectsOffset(v=>v+PAGE_LIMIT)}>Next</button></div>
          </div>
          <div className="bdmt-sub-panel"><h3>Contact Activity ({details.activities.total})</h3>{details.activities.items.length?<div className="bdmt-list">{details.activities.items.map(a=><article key={a.id}><div><strong>{a.company_name}</strong><span className="bdmt-status">{displayStatus(a.outcome)}</span></div><small>{displayStatus(a.channel)} · {displayDateTime(a.contacted_at)}</small>{a.remarks&&<p>{a.remarks}</p>}</article>)}</div>:<p className="bdmt-hint">No contacts recorded in this period.</p>}
            <div className="bdmt-pager"><button type="button" className="operations-button secondary" disabled={activitiesOffset===0} onClick={()=>setActivitiesOffset(v=>Math.max(0,v-PAGE_LIMIT))}>Previous</button><small>{details.activities.total?`${details.activities.offset+1}–${Math.min(details.activities.offset+PAGE_LIMIT,details.activities.total)} of ${details.activities.total}`:'0 of 0'}</small><button type="button" className="operations-button secondary" disabled={activitiesOffset+PAGE_LIMIT>=details.activities.total} onClick={()=>setActivitiesOffset(v=>v+PAGE_LIMIT)}>Next</button></div>
          </div>
        </div>}
      </section>}
      <p className="bdmt-footnote">Prospects includes converted leads. Total Clients counts actual registered BD clients credited to the employee. Closed is a current lead status. Total Sales is submitted, finalized BD project commercial value (INR), not invoice collections or realized revenue; unavailable values are never guessed.</p>
    </>}
  </div>
}
