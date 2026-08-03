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
import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import { Link } from 'react-router-dom'
import { ActivityTrendChart, DonutChart, HorizontalBars } from '../components/Charts'
import { DashboardHeader } from '../components/DashboardHeader'
import { AssetDrilldownDrawer } from '../components/AssetDrilldownDrawer'
import { StatCard } from '../components/StatCard'
import { useITMonthUrl } from '../context/ITMonthContext'
import { apiFetch, downloadFile } from '../lib/api'
import { withITMonth } from '../lib/itMonth'
import type { ActivityTrendPoint, DistributionItem, ITActivitySummaryData, ITAssetDrilldownSelection, ITDashboardData, ReportMonth } from '../types'


function reportingMonthWindow(endMonth: string, count = 6): Array<{ key: string; label: string }> {
  const match = /^(\d{4})-(\d{2})$/.exec(endMonth)
  if (!match) return []
  const year = Number(match[1])
  const monthIndex = Number(match[2]) - 1
  return Array.from({ length: count }, (_, index) => {
    const offset = count - index - 1
    const date = new Date(Date.UTC(year, monthIndex - offset, 1))
    const key = `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`
    const label = date.toLocaleDateString('en-IN', { month: 'long', year: 'numeric', timeZone: 'UTC' })
    return { key, label }
  })
}

function normalizedStatusKey(label: string): string {
  return label.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')
}

function statusChartItems(items: DistributionItem[]): DistributionItem[] {
  let assigned = 0
  const result: DistributionItem[] = []
  for (const item of items) {
    const key = normalizedStatusKey(item.name)
    if (key === 'assigned' || key === 'in_use') {
      assigned += item.value
      continue
    }
    result.push({ ...item, key })
  }
  if (assigned > 0) result.unshift({ name: 'Assigned / In Use', value: assigned, key: 'assigned' })
  return result
}

export function ITDashboard() {
  const { selectedMonth, presentMonth, setSelectedMonth, returnToPresent } = useITMonthUrl()
  const [data, setData] = useState<ITDashboardData | null>(null)
  const [months, setMonths] = useState<ReportMonth[]>([])
  const [error, setError] = useState('')
  const [downloading, setDownloading] = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const [lastUpdated, setLastUpdated] = useState('')
  const requestSequence = useRef(0)
  const trendRequestSequence = useRef(0)
  const trendAbortController = useRef<AbortController | null>(null)
  const [drilldown, setDrilldown] = useState<ITAssetDrilldownSelection | null>(null)
  const [activityTrend, setActivityTrend] = useState<ActivityTrendPoint[]>([])
  const [trendLoading, setTrendLoading] = useState(false)
  const [trendError, setTrendError] = useState('')

  async function loadMonths() {
    try {
      setMonths(await apiFetch<ReportMonth[]>('/reports/months'))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load available months')
    }
  }

  async function loadActivityTrend() {
    const requestedMonth = selectedMonth
    const requestId = ++trendRequestSequence.current
    trendAbortController.current?.abort()
    const controller = new AbortController()
    trendAbortController.current = controller
    setTrendLoading(true)
    setTrendError('')

    try {
      const window = reportingMonthWindow(requestedMonth, 6)
      const summaries = await Promise.all(window.map(async month => {
        const result = await apiFetch<ITActivitySummaryData>(
          `/it-activity/summary?month=${encodeURIComponent(month.key)}&limit=1`,
          { signal: controller.signal },
        )
        if (result.month.key !== month.key) {
          throw new Error(`Activity graph returned ${result.month.key} while ${month.key} was requested`)
        }
        return {
          month: month.key,
          label: result.month.label || month.label,
          total_activities: result.summary.total_activities,
          asset_edit_operations: result.summary.asset_edit_operations,
          component_changes: result.summary.component_changes,
          handover_operations: result.summary.handover_operations,
          return_operations: result.summary.return_operations,
          purchases_recorded: result.summary.purchases_recorded,
        } satisfies ActivityTrendPoint
      }))

      if (requestId !== trendRequestSequence.current || controller.signal.aborted) return
      setActivityTrend(summaries)
    } catch (err) {
      if (requestId !== trendRequestSequence.current || controller.signal.aborted) return
      setActivityTrend([])
      setTrendError(err instanceof Error ? err.message : 'Unable to load monthly activity graph')
    } finally {
      if (requestId === trendRequestSequence.current && !controller.signal.aborted) setTrendLoading(false)
    }
  }

  async function load(showIndicator = false, clearExisting = false) {
    const requestedMonth = selectedMonth
    const requestId = ++requestSequence.current
    setError('')
    if (clearExisting) {
      setData(null)
      if (!showIndicator) setRefreshing(false)
    }
    if (showIndicator) setRefreshing(true)

    try {
      const result = await apiFetch<ITDashboardData>(
        `/dashboard/it?month=${encodeURIComponent(requestedMonth)}&refresh=${Date.now()}`
      )

      // A slower response for an older month must never overwrite the newest
      // selection. The API month is also checked before rendering.
      if (requestId !== requestSequence.current) return
      if (result.month.key !== requestedMonth) {
        throw new Error(`Dashboard returned ${result.month.key} while ${requestedMonth} was selected`)
      }

      setData(result)
      setLastUpdated(new Date().toLocaleTimeString())
    } catch (err) {
      if (requestId !== requestSequence.current) return
      setError(err instanceof Error ? err.message : 'Unable to load dashboard')
    } finally {
      if (requestId === requestSequence.current && showIndicator) setRefreshing(false)
    }
  }

  useEffect(() => { void loadMonths() }, [])
  useEffect(() => {
    const currentRequest = requestSequence.current + 1
    void load(false, true)
    return () => {
      if (requestSequence.current === currentRequest) requestSequence.current += 1
    }
  }, [selectedMonth])
  useEffect(() => {
    void loadActivityTrend()
    return () => {
      trendAbortController.current?.abort()
      trendRequestSequence.current += 1
    }
  }, [selectedMonth])

  function chooseMonth(month: string) {
    setSelectedMonth(month)
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
  const statusVisualData = statusChartItems(data.status_distribution)
  const registerUrl = withITMonth('/assets', selectedMonth)

  return (
    <>
      <DashboardHeader
        eyebrow="IT DEPARTMENT"
        title="IT Asset Dashboard"
        description={`${data.month.label} reporting context — inventory snapshot plus all activities assigned to this month. Actual server entry time remains separately recorded.`}
        actions={<>
          <label className="dashboard-month-select">
            <CalendarDays size={17} />
            <span>Month</span>
            <select value={selectedMonth} onChange={(event: ChangeEvent<HTMLSelectElement>) => chooseMonth(event.target.value)}>
              {months.map(item => (
                <option key={item.key} value={item.key}>
                  {item.label}{item.is_current ? ' — Present' : item.status === 'finalized' ? ' — Finalized' : ' — Historical'}
                </option>
              ))}
            </select>
          </label>
          {selectedMonth !== presentMonth && <button className="secondary-button" onClick={returnToPresent}><RotateCcw size={17} /> Return to Present</button>}
          <button className="secondary-button" onClick={() => void load(true)} disabled={refreshing}><RefreshCcw size={17} className={refreshing ? 'spin' : ''} /> {refreshing ? 'Refreshing...' : 'Refresh'}{lastUpdated && !refreshing ? ` · ${lastUpdated}` : ''}</button>
          <button className="secondary-button" onClick={() => void download('dashboard')} disabled={!!downloading}><FileDown size={17} /> Dashboard Excel</button>
          <button className="primary-button" onClick={() => void download('assets')} disabled={!!downloading}><FileDown size={17} /> {downloading === 'assets' ? 'Preparing...' : 'Download Asset Excel'}</button>
        </>}
      />
      {error && <div className="error-message">{error}</div>}

      <section className={`month-context-banner ${data.month.is_live ? 'live' : 'historical'}`}>
        <div><CalendarDays size={20} /><span>Viewing</span><strong>{data.month.label}</strong><b>{data.month.is_live ? 'LIVE / PRESENT' : 'EFFECTIVE REPORTING MONTH'}</b></div>
        <div className="month-activity-strip">
          <span><strong>{data.monthly_activity.new_assets}</strong> New assets</span>
          <span><strong>{data.monthly_activity.work_records}</strong> Work records</span>
          <span><strong>{data.monthly_activity.assets_edited}</strong> Assets edited</span>
          <span><strong>{data.monthly_activity.asset_edit_operations}</strong> Full edit saves</span>
          <span><strong>{data.monthly_activity.component_changes}</strong> Component change items</span>
          <span><strong>{data.monthly_activity.complete_replacements}</strong> Complete replacements</span>
        </div>
      </section>

      <section className="stats-grid stats-eight dashboard-drilldown-cards" aria-label="Clickable IT asset summaries">
        <StatCard icon={HardDrive} label="Total IT Assets" value={k.total} note={data.month.is_live ? 'Current active register · click for details' : `${data.month.label} closing register · click for details`} onClick={() => setDrilldown({ scope: 'all' })} active={drilldown?.scope === 'all'} />
        <StatCard icon={Monitor} label="Computers" value={k.computers} tone="navy" note="Click for computer details" onClick={() => setDrilldown({ scope: 'device', value: 'Computer' })} active={drilldown?.scope === 'device' && drilldown.value === 'Computer'} />
        <StatCard icon={Laptop} label="Laptops" value={k.laptops} tone="cyan" note="Click for laptop details" onClick={() => setDrilldown({ scope: 'device', value: 'Laptop' })} active={drilldown?.scope === 'device' && drilldown.value === 'Laptop'} />
        <StatCard icon={Smartphone} label="Smartphones" value={k.smartphones} tone="purple" note="Click for smartphone details" onClick={() => setDrilldown({ scope: 'device', value: 'Smartphone' })} active={drilldown?.scope === 'device' && drilldown.value === 'Smartphone'} />
        <StatCard icon={CheckCircle2} label="Assigned / In Use" value={k.assigned} tone="green" note="Click for assigned assets" onClick={() => setDrilldown({ scope: 'status', value: 'assigned' })} active={drilldown?.scope === 'status' && drilldown.value === 'assigned'} />
        <StatCard icon={PackageOpen} label="Available" value={k.available} tone="teal" note="Click for available assets" onClick={() => setDrilldown({ scope: 'status', value: 'available' })} active={drilldown?.scope === 'status' && drilldown.value === 'available'} />
        <StatCard icon={Wrench} label="Under Repair" value={k.repair} tone="orange" note="Click for repair details" onClick={() => setDrilldown({ scope: 'status', value: 'repair' })} active={drilldown?.scope === 'status' && drilldown.value === 'repair'} />
        <StatCard icon={Repeat2} label="Replacement Pending" value={k.replacement_pending} tone="red" note="Click for pending replacements" onClick={() => setDrilldown({ scope: 'status', value: 'replacement_pending' })} active={drilldown?.scope === 'status' && drilldown.value === 'replacement_pending'} />
      </section>

      <section className="dashboard-grid three-column">
        <article className="panel chart-panel">
          <div className="panel-heading"><div><span className="section-kicker">INVENTORY MIX</span><h2>Device Distribution</h2><small className="panel-helper">Click a pie segment or legend to inspect that device type here.</small></div></div>
          <DonutChart
            data={data.device_distribution}
            centerLabel="Assets"
            ariaLabel="IT assets by device type"
            onSelect={item => setDrilldown({ scope: 'device', value: item.name })}
            activeKey={drilldown?.scope === 'device' ? drilldown.value : undefined}
          />
        </article>
        <article className="panel chart-panel span-two">
          <div className="panel-heading"><div><span className="section-kicker">TEAM ALLOCATION</span><h2>Assets by Department</h2><small className="panel-helper">Click a department bar to inspect all matching assets here.</small></div></div>
          <HorizontalBars
            data={data.department_distribution}
            maxItems={10}
            onSelect={item => setDrilldown({ scope: 'department', value: item.name })}
            activeName={drilldown?.scope === 'department' ? drilldown.value : undefined}
          />
        </article>
      </section>

      <section className="dashboard-grid two-column">
        <article className="panel chart-panel">
          <div className="panel-heading"><div><span className="section-kicker">{data.month.is_live ? 'LIVE CONDITION' : 'MONTH-END CONDITION'}</span><h2>Asset Status Distribution</h2><small className="panel-helper">Click a pie segment to open matching status records without leaving the dashboard.</small></div></div>
          <DonutChart
            data={statusVisualData}
            centerLabel="Assets"
            ariaLabel="IT assets by operational status"
            onSelect={item => setDrilldown({ scope: 'status', value: item.key || normalizedStatusKey(item.name) })}
            activeKey={drilldown?.scope === 'status' ? drilldown.value : undefined}
          />
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

      <section className="dashboard-grid">
        <article className="panel activity-trend-panel">
          <div className="panel-heading">
            <div>
              <span className="section-kicker">MONTHLY VISUAL ANALYTICS</span>
              <h2>IT Activity Trend — Six-Month View</h2>
              <small className="panel-helper">The graph ends at {data.month.label}. Switch metrics to compare edits, component work, handovers, returns and purchases.</small>
            </div>
          </div>
          <ActivityTrendChart
            data={activityTrend}
            selectedMonth={selectedMonth}
            loading={trendLoading}
            error={trendError}
            onRetry={() => void loadActivityTrend()}
          />
        </article>
      </section>

      <section className="dashboard-grid two-column">
        <article className="panel">
          <div className="panel-heading"><div><span className="section-kicker">IT OPERATIONS</span><h2>Work Records in {data.month.label}</h2></div><Link to={withITMonth('/work', selectedMonth)}>Manage work <ArrowRight size={15} /></Link></div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Work ID</th><th>Asset</th><th>Work</th><th>Technician</th><th>Priority</th><th>Status</th></tr></thead>
              <tbody>{data.recent_work.map(work => <tr key={work.id}><td><strong>{work.work_code}</strong></td><td>{work.asset_code || '—'}</td><td>{work.title}</td><td>{work.technician || 'Unassigned'}</td><td><span className={`priority ${work.priority}`}>{work.priority}</span></td><td><span className={`status ${work.status}`}>{work.status.replace('_', ' ')}</span></td></tr>)}</tbody>
            </table>
            {!data.recent_work.length && <div className="empty-state">No system work record is available for this month.</div>}
          </div>
        </article>
        <article className="panel">
          <div className="panel-heading"><div><span className="section-kicker">LIFECYCLE CONTROL</span><h2>Replacement Requests in {data.month.label}</h2></div><Link to={withITMonth('/replacements', selectedMonth)}>Open workflow <ArrowRight size={15} /></Link></div>
          <div className="replacement-list">
            {data.recent_replacements.length === 0 && <div className="empty-state">No complete-asset replacement request for this month.</div>}
            {data.recent_replacements.map(item => <article key={item.id}><div><strong>{item.replacement_code}</strong><span className={`status ${item.approval_status}`}>{item.approval_status}</span></div><p><b>{item.old_asset_code}</b> · {item.reason}</p><small>{item.damage_category.replaceAll('_', ' ')} · {item.final_action.replaceAll('_', ' ')}</small></article>)}
          </div>
        </article>
      </section>

      {drilldown && <AssetDrilldownDrawer selectedMonth={selectedMonth} selection={drilldown} onClose={() => setDrilldown(null)} />}
    </>
  )
}
