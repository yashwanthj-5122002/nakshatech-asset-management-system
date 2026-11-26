import {
  Activity,
  AlertTriangle,
  Bell,
  CheckCircle2,
  Database,
  Gauge,
  HardDrive,
  History,
  MailCheck,
  RefreshCcw,
  Server,
  ShieldCheck,
  XCircle,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { StatCard } from '../../../components/StatCard'
import { apiFetch } from '../../../lib/api'
import '../operations.css'
import '../hardening.css'

type Check = {key:string;label:string;status:'pass'|'warn'|'fail';critical:boolean;detail:string}
type AuditRow = {id?:string|number|null;event_type?:string|null;module?:string|null;target_type?:string|null;target_id?:string|null;actor_name?:string|null;created_at?:string|null}
type NotificationRow = {id?:string|number|null;event_type?:string|null;title?:string|null;recipient_name?:string|null;is_read?:boolean|null;created_at?:string|null}
type Overview = {
  viewer_role:string
  generated_at:string
  phase:string
  read_only:boolean
  production_review_ready:boolean
  readiness_score:number
  summary:{checks:number;passed:number;warnings:number;failed:number;critical_failures:number;audit_events:number;notifications:number;unread_notifications:number;optimization_indexes:number}
  checks:Check[]
  services:{database:{ok:boolean;detail:string;dialect?:string|null};redis:{configured:boolean;ok:boolean;detail:string};minio:{configured:boolean;ok:boolean;detail:string};smtp:{configured:boolean;host?:string|null;port?:number;username?:string|null;password_present:boolean}}
  security:{configured:boolean;source?:string|null;length:number;weak_default_or_short:boolean}
  routing:{routing_mode?:string;live_technical_routing_enabled?:boolean}
  audit:{available:boolean;table?:string|null;total:number;recent:AuditRow[];by_event:Record<string,number>}
  notifications:{available:boolean;table?:string|null;total:number;unread:number;recent:NotificationRow[];by_event:Record<string,number>}
  optimization:{count:number;indexes:Array<{table:string;name:string;columns:string[]}>}
  backup:{scripts_detected:number;script_names:string[];detail:string}
  go_live_note:string
}

type SmtpResult = {configured:boolean;ok:boolean;detail:string;host?:string|null;port?:number;username?:string|null}

function human(value?:string|null){
  if(!value)return '—'
  return value.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase())
}

function statusIcon(status:Check['status']){
  if(status==='pass')return <CheckCircle2 size={17}/>
  if(status==='warn')return <AlertTriangle size={17}/>
  return <XCircle size={17}/>
}

export function ProductionReadinessPage(){
  const [data,setData]=useState<Overview|null>(null)
  const [error,setError]=useState('')
  const [smtp,setSmtp]=useState<SmtpResult|null>(null)
  const [smtpBusy,setSmtpBusy]=useState(false)

  function load(){
    setError('')
    void apiFetch<Overview>('/operations/hardening/overview')
      .then(setData)
      .catch(err=>setError(err instanceof Error?err.message:'Could not load Phase 9 production readiness'))
  }
  useEffect(load,[])

  async function testSmtp(){
    setSmtpBusy(true);setSmtp(null);setError('')
    try{
      const result=await apiFetch<SmtpResult>('/operations/hardening/smtp-check',{method:'POST'})
      setSmtp(result)
      load()
    }catch(err){setError(err instanceof Error?err.message:'SMTP diagnostic failed')}
    finally{setSmtpBusy(false)}
  }

  const critical=useMemo(()=>data?.checks.filter(item=>item.critical)??[],[data])
  const canTestSmtp=data?.viewer_role==='admin'||data?.viewer_role==='software_team'

  return <div className="operations-page phase9-hardening-page">
    <DashboardHeader
      eyebrow="PHASE 9 · PRODUCTION HARDENING"
      title="Production Readiness & System Assurance"
      description="Read-only operational assurance for auditability, notifications, service health, security configuration, performance indexes and go-live readiness."
      actions={<button className="operations-button secondary" type="button" onClick={load}><RefreshCcw size={16}/> Refresh</button>}
      meta={<>
        <span className="nk-meta-chip"><Activity size={14}/> Read-only operational assurance</span>
        <span className="nk-meta-chip"><ShieldCheck size={14}/> {data?.production_review_ready ? 'Ready for production review' : 'Checking go-live readiness…'}</span>
        <span className="nk-meta-chip"><Gauge size={14}/> Health · security · performance indexes</span>
      </>}
    />

    {data&&<div className={`hardening-readiness-banner ${data.production_review_ready?'ready':'blocked'}`}>
      <ShieldCheck size={20}/>
      <div><strong>{data.production_review_ready?'Ready for production review':'Production review has critical blockers'}</strong><span>{data.go_live_note}</span></div>
      <b>{data.readiness_score}%</b>
    </div>}
    {error&&<div className="error-message">{error}</div>}

    <section className="stats-grid hardening-stats">
      <StatCard icon={Gauge} label="Readiness Score" value={data?`${data.readiness_score}%`:'—'} tone="green" />
      <StatCard icon={CheckCircle2} label="Checks Passed" value={data?data.summary.passed:'—'} tone="green" />
      <StatCard icon={AlertTriangle} label="Warnings" value={data?data.summary.warnings:'—'} tone="orange" />
      <StatCard icon={History} label="Audit Events" value={data?data.summary.audit_events:'—'} />
      <StatCard icon={Bell} label="Notifications" value={data?data.summary.notifications:'—'} tone="purple" />
      <StatCard icon={Database} label="Phase 9 Indexes" value={data?data.summary.optimization_indexes:'—'} />
    </section>

    {!data?<section className="operations-panel"><div className="operations-empty">Loading production readiness…</div></section>:<>
      <section className="operations-panel hardening-checks">
        <header><div><span className="operations-kicker">GO-LIVE GATE</span><h2>Readiness Checklist</h2><p>Critical checks must pass before production review. Warnings are operational follow-ups and do not change ERP workflow state.</p></div></header>
        <div className="hardening-check-grid">{data.checks.map(item=><article key={item.key} className={`hardening-check ${item.status}`}>
          <span className="hardening-check-icon">{statusIcon(item.status)}</span>
          <div><strong>{item.label}{item.critical?<em>Critical</em>:null}</strong><p>{item.detail}</p></div>
          <span className={`operations-status ${item.status==='pass'?'success':item.status==='warn'?'warning':'danger'}`}>{item.status.toUpperCase()}</span>
        </article>)}</div>
        <div className="hardening-critical-note"><ShieldCheck size={17}/><span>{critical.filter(item=>item.status==='pass').length}/{critical.length} critical production checks currently pass.</span></div>
      </section>

      <section className="hardening-service-grid">
        <article className="operations-panel hardening-service-card"><Database size={22}/><div><span>Database</span><strong>{data.services.database.ok?'Healthy':'Issue'}</strong><small>{data.services.database.detail}</small></div></article>
        <article className="operations-panel hardening-service-card"><Activity size={22}/><div><span>Redis</span><strong>{data.services.redis.ok?'Healthy':data.services.redis.configured?'Unavailable':'Not configured'}</strong><small>{data.services.redis.detail}</small></div></article>
        <article className="operations-panel hardening-service-card"><HardDrive size={22}/><div><span>MinIO</span><strong>{data.services.minio.ok?'Reachable':data.services.minio.configured?'Unavailable':'Not configured'}</strong><small>{data.services.minio.detail}</small></div></article>
        <article className="operations-panel hardening-service-card"><MailCheck size={22}/><div><span>SMTP</span><strong>{data.services.smtp.configured?'Configured':'Incomplete'}</strong><small>{data.services.smtp.username||'No sender configured'} · {data.services.smtp.host||'No host'}</small>{canTestSmtp&&<button className="operations-button secondary compact" type="button" disabled={smtpBusy} onClick={()=>void testSmtp()}>{smtpBusy?'Testing…':'Test SMTP Auth'}</button>}{smtp&&<small className={smtp.ok?'hardening-ok':'hardening-bad'}>{smtp.detail}</small>}</div></article>
      </section>

      <section className="operations-panel hardening-routing">
        <header><div><span className="operations-kicker">ROUTING SAFETY</span><h2>Phase 7 State Preserved</h2></div><Server size={22}/></header>
        <div className="hardening-routing-row"><span>Current mode</span><strong>{human(data.routing.routing_mode)}</strong></div>
        <div className="hardening-routing-row"><span>Live technical routing</span><strong>{data.routing.live_technical_routing_enabled?'ACTIVE':'LOCKED / OFF'}</strong></div>
        <p>Phase 9 never activates production routing. The irreversible Phase 7 Admin cutover remains separate.</p>
      </section>

      <section className="operations-panel hardening-audit">
        <header><div><span className="operations-kicker">AUDITABILITY</span><h2>Recent Audit Trail</h2><p>High-level event metadata only. Details/before/after payloads are intentionally not exposed on this dashboard.</p></div></header>
        {data.audit.recent.length===0?<div className="operations-empty">No audit events are available.</div>:<div className="hardening-table-wrap"><table className="hardening-table"><thead><tr><th>Event</th><th>Actor</th><th>Module</th><th>Target</th><th>Time</th></tr></thead><tbody>{data.audit.recent.map((row,index)=><tr key={`${row.id??'audit'}-${index}`}><td><strong>{human(row.event_type)}</strong></td><td>{row.actor_name||'System / Unknown'}</td><td>{human(row.module)}</td><td>{row.target_type?`${human(row.target_type)}${row.target_id?` #${row.target_id}`:''}`:'—'}</td><td>{row.created_at?new Date(row.created_at).toLocaleString():'—'}</td></tr>)}</tbody></table></div>}
      </section>

      <section className="operations-panel hardening-notifications">
        <header><div><span className="operations-kicker">NOTIFICATION ASSURANCE</span><h2>Notification Store Health</h2><p>{data.notifications.total} total · {data.notifications.unread} unread. Message bodies are not exposed here.</p></div></header>
        {data.notifications.recent.length===0?<div className="operations-empty">No notification events are available.</div>:<div className="hardening-notification-grid">{data.notifications.recent.slice(0,8).map((row,index)=><article key={`${row.id??'notification'}-${index}`}><Bell size={16}/><div><strong>{row.title||human(row.event_type)}</strong><small>{row.recipient_name||'Recipient'} · {row.created_at?new Date(row.created_at).toLocaleString():'—'}</small></div><span className={`operations-status ${row.is_read?'':'warning'}`}>{row.is_read?'Read':'Unread'}</span></article>)}</div>}
      </section>

      <section className="operations-panel hardening-optimization">
        <header><div><span className="operations-kicker">OPTIMIZATION</span><h2>Phase 9 Database Indexes</h2><p>Additive indexes accelerate audit, notification and operational reporting queries without changing business records.</p></div></header>
        <div className="hardening-index-grid">{data.optimization.indexes.map(row=><div key={row.name}><strong>{row.name}</strong><span>{row.table}</span><code>{row.columns.join(', ')}</code></div>)}</div>
      </section>
    </>}
  </div>
}
