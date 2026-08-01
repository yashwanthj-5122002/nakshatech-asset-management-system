import {
  AlertTriangle,
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  FileDown,
  HardDrive,
  Laptop,
  Monitor,
  PackageOpen,
  RefreshCcw,
  Repeat2,
  RotateCcw,
  Smartphone,
  Wrench,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { DonutChart, HorizontalBars, StatusGrid } from '../components/Charts'
import { DashboardHeader } from '../components/DashboardHeader'
import { StatCard } from '../components/StatCard'
import { apiFetch, downloadFile } from '../lib/api'
import type { ITDashboardData, ReportMonth } from '../types'

function currentMonthKey() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

export function ITDashboard() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [data, setData] = useState<ITDashboardData | null>(null)
  const [months, setMonths] = useState<ReportMonth[]>([])
  const [error, setError] = useState('')
  const [downloading, setDownloading] = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const [lastUpdated, setLastUpdated] = useState('')

  const presentMonth = useMemo(
    () => months.find(item => item.is_current)?.key || currentMonthKey(),
    [months],
  )
  const selectedMonth = searchParams.get('month') || presentMonth

  async function loadMonths() {
    try {
      setMonths(await apiFetch<ReportMonth[]>('/reports/months'))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load available months')
    }
  }

  async function load(showIndicator = false) {
    setError('')
    if (showIndicator) setRefreshing(true)
    try {
      setData(await apiFetch<ITDashboardData>(`/dashboard/it?month=${selectedMonth}&refresh=${Date.now()}`))
      setLastUpdated(new Date().toLocaleTimeString())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load dashboard')
    } finally {
      if (showIndicator) setRefreshing(false)
    }
  }

  useEffect(() => { void loadMonths() }, [])
  useEffect(() => { void load() }, [selectedMonth])

  function chooseMonth(month: string) {
    const next = new URLSearchParams(searchParams)
    if (month === presentMonth) next.delete('month')
    else next.set('month', month)
    setSearchParams(next)
  }

  function returnToPresent() {
    const next = new URLSearchParams(searchParams)
    next.delete('month')
    setSearchParams(next)
  }

  async function download(type: 'assets' | 'dashboard') {
    if (!data) return
    setDownloading(type)
    try {
      const encodedMonth = encodeURIComponent(data.month.key)
      if (type === 'assets') {
        await downloadFile(
          `/reports/monthly-assets.xlsx?month=${encodedMonth}`,
          `NakshaTech Asset Register - ${data.month.label}.xlsx`,
        )
      } else {
        await downloadFile(
          `/reports/monthly-summary.xlsx?month=${encodedMonth}`,
          `NakshaTech Dashboard Summary - ${data.month.label}.xlsx`,
        )
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Download failed')
    } finally {
      setDownloading('')
    }
  }

  if (!data) return <div className="loading-state">{error || 'Loading IT dashboard...'}</div>
  const k = data.kpis
  const registerUrl = data.month.is_live ? '/assets' : `/assets?month=${data.month.key}`

  return (
    <>
      <DashboardHeader
        eyebrow="IT DEPARTMENT"
        title="IT Asset Dashboard"
        description={`${data.month.label} ${data.month.is_live ? 'live inventory' : 'historical inventory snapshot'} — assets, work records, replacements and data-quality alerts.`}
        actions={<>
          <label className="dashboard-month-select">
            <CalendarDays size={17} />
            <span>Month</span>
            <select value={selectedMonth} onChange={event => chooseMonth(event.target.value)}>
              {months.map(item => (
                <option key={item.key} value={item.key}>
                  {item.label}{item.is_current ? ' — Present' : item.status === 'finalized' ? ' — Finalized' : ' — Historical'}
                </option>
              ))}
            </select>
          </label>
          {!data.month.is_live && <button className="secondary-button" onClick={returnToPresent}><RotateCcw size={17} /> Return to Present</button>}
          <button className="secondary-button" onClick={() => void load(true)} disabled={refreshing}><RefreshCcw size={17} className={refreshing ? 'spin' : ''} /> {refreshing ? 'Refreshing...' : 'Refresh'}{lastUpdated && !refreshing ? ` · ${lastUpdated}` : ''}</button>
          <button className="secondary-button" onClick={() => void download('dashboard')} disabled={!!downloading}><FileDown size={17} /> Dashboard Excel</button>
          <button className="primary-button" onClick={() => void download('assets')} disabled={!!downloading}><FileDown size={17} /> {downloading === 'assets' ? 'Preparing...' : 'Download Asset Excel'}</button>
        </>}
      />
      {error && <div className="error-message">{error}</div>}

      <section className={`month-context-banner ${data.month.is_live ? 'live' : 'historical'}`}>
        <div><CalendarDays size={20} /><span>Viewing</span><strong>{data.month.label}</strong><b>{data.month.is_live ? 'LIVE / PRESENT' : 'READ-ONLY HISTORY'}</b></div>
        <div className="month-activity-strip">
          <span><strong>{data.monthly_activity.new_assets}</strong> New assets</span>
          <span><strong>{data.monthly_activity.work_records}</strong> Work records</span>
          <span><strong>{data.monthly_activity.component_changes}</strong> Upgrade/replacement items</span>
          <span><strong>{data.monthly_activity.complete_replacements}</strong> Complete replacements</span>
        </div>
      </section>

      <section className="stats-grid stats-eight">
        <StatCard icon={HardDrive} label="Total IT Assets" value={k.total} note={data.month.is_live ? 'Current active register' : `${data.month.label} closing register`} />
        <StatCard icon={Monitor} label="Computers" value={k.computers} tone="navy" />
        <StatCard icon={Laptop} label="Laptops" value={k.laptops} tone="cyan" />
        <StatCard icon={Smartphone} label="Smartphones" value={k.smartphones} tone="purple" />
        <StatCard icon={CheckCircle2} label="Assigned / In Use" value={k.assigned} tone="green" />
        <StatCard icon={PackageOpen} label="Available" value={k.available} tone="teal" />
        <StatCard icon={Wrench} label="Under Repair" value={k.repair} tone="orange" />
        <StatCard icon={Repeat2} label="Replacement Pending" value={k.replacement_pending} tone="red" />
      </section>

      <section className="dashboard-grid three-column">
        <article className="panel chart-panel">
          <div className="panel-heading"><div><span className="section-kicker">INVENTORY MIX</span><h2>Device Distribution</h2></div><Link to={registerUrl}>View register <ArrowRight size={15} /></Link></div>
          <DonutChart data={data.device_distribution} centerLabel="Assets" />
        </article>
        <article className="panel chart-panel span-two">
          <div className="panel-heading"><div><span className="section-kicker">TEAM ALLOCATION</span><h2>Assets by Department</h2></div></div>
          <HorizontalBars data={data.department_distribution} maxItems={10} />
        </article>
      </section>

      <section className="dashboard-grid two-column">
        <article className="panel">
          <div className="panel-heading"><div><span className="section-kicker">{data.month.is_live ? 'LIVE CONDITION' : 'MONTH-END CONDITION'}</span><h2>Asset Status</h2></div><Link to={registerUrl}>Open assets <ArrowRight size={15} /></Link></div>
          <StatusGrid data={data.status_distribution} />
          <div className="mini-metrics">
            <span><strong>{k.wfh}</strong> Work from home</span>
            <span><strong>{k.field}</strong> Field deployment</span>
            <span><strong>{k.returned}</strong> Returned</span>
            <span><strong>{k.damaged}</strong> Damaged / beyond repair</span>
          </div>
        </article>
        <article className="panel alerts-panel">
          <div className="panel-heading"><div><span className="section-kicker">ACTION REQUIRED</span><h2>Alerts & Data Quality</h2></div></div>
          <div className="alert-list">
            {data.alerts.length === 0 && <div className="empty-state">No active alerts for this month.</div>}
            {data.alerts.map(alert => (
              <Link to={registerUrl} key={alert.title} className={`alert-row severity-${alert.severity}`}>
                <AlertTriangle size={19} /><div><strong>{alert.title}</strong>{alert.details?.length ? <small>{alert.details.join(', ')}</small> : <small>Open the selected month register</small>}</div><b>{alert.count}</b>
              </Link>
            ))}
          </div>
        </article>
      </section>

      <section className="dashboard-grid two-column">
        <article className="panel">
          <div className="panel-heading"><div><span className="section-kicker">IT OPERATIONS</span><h2>Work Records in {data.month.label}</h2></div>{data.month.is_live && <Link to="/work">Manage work <ArrowRight size={15} /></Link>}</div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Work ID</th><th>Asset</th><th>Work</th><th>Technician</th><th>Priority</th><th>Status</th></tr></thead>
              <tbody>{data.recent_work.map(work => <tr key={work.id}><td><strong>{work.work_code}</strong></td><td>{work.asset_code || '—'}</td><td>{work.title}</td><td>{work.technician || 'Unassigned'}</td><td><span className={`priority ${work.priority}`}>{work.priority}</span></td><td><span className={`status ${work.status}`}>{work.status.replace('_', ' ')}</span></td></tr>)}</tbody>
            </table>
            {!data.recent_work.length && <div className="empty-state">No system work record is available for this month.</div>}
          </div>
        </article>
        <article className="panel">
          <div className="panel-heading"><div><span className="section-kicker">LIFECYCLE CONTROL</span><h2>Replacement Requests in {data.month.label}</h2></div>{data.month.is_live && <Link to="/replacements">Open workflow <ArrowRight size={15} /></Link>}</div>
          <div className="replacement-list">
            {data.recent_replacements.length === 0 && <div className="empty-state">No complete-asset replacement request for this month.</div>}
            {data.recent_replacements.map(item => <article key={item.id}><div><strong>{item.replacement_code}</strong><span className={`status ${item.approval_status}`}>{item.approval_status}</span></div><p><b>{item.old_asset_code}</b> · {item.reason}</p><small>{item.damage_category.replaceAll('_', ' ')} · {item.final_action.replaceAll('_', ' ')}</small></article>)}
          </div>
        </article>
      </section>
    </>
  )
}
