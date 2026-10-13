import {
  ArrowDownToLine, CalendarDays, CheckCircle2, ChevronLeft, ChevronRight, Cpu, FileClock, Laptop, PackageCheck,
  RefreshCw, RotateCcw, Search, ShoppingCart, UserRoundCheck,
} from 'lucide-react'
import { CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import { DashboardHeader } from '../components/DashboardHeader'
import { useITMonthUrl } from '../context/ITMonthContext'
import { apiFetch, downloadFile } from '../lib/api'
import type { ITActivityItem, ITActivitySummary } from '../types'

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

const sourceColors: Record<string, string> = {
  asset_edit: '#059669',
  component_change: '#2563eb',
  handover_return: '#7c3aed',
  purchase: '#d97706',
}

const ACTIVITY_ROWS_PER_PAGE = 10
type PaginationItem = number | 'start-ellipsis' | 'end-ellipsis'

function getPaginationItems(currentPage: number, totalPages: number): PaginationItem[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1)
  }

  if (currentPage <= 4) {
    return [1, 2, 3, 4, 5, 'end-ellipsis', totalPages]
  }

  if (currentPage >= totalPages - 3) {
    return [1, 'start-ellipsis', totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages]
  }

  return [1, 'start-ellipsis', currentPage - 1, currentPage, currentPage + 1, 'end-ellipsis', totalPages]
}

export function RecentChangesPage() {
  const { selectedMonth, presentMonth, setSelectedMonth, returnToPresent } = useITMonthUrl()
  const [department, setDepartment] = useState('')
  const [deviceCategory, setDeviceCategory] = useState('')
  const [changedBy, setChangedBy] = useState('')
  const [actionType, setActionType] = useState('')
  const [search, setSearch] = useState('')
  const [data, setData] = useState<ITActivitySummary | null>(null)
  const [selected, setSelected] = useState<ITActivityItem | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [currentPage, setCurrentPage] = useState(1)
  const requestSequence = useRef(0)

  async function load(clearExisting = false) {
    const requestedMonth = selectedMonth
    const requestId = ++requestSequence.current
    setLoading(true); setError('')
    if (clearExisting) {
      setData(null)
      setSelected(null)
    }

    try {
      const params = new URLSearchParams({ month: requestedMonth, limit: '2000' })
      if (department) params.set('department', department)
      if (deviceCategory) params.set('device_category', deviceCategory)
      if (changedBy) params.set('changed_by', changedBy)
      if (actionType) params.set('action_type', actionType)
      if (search.trim()) params.set('search', search.trim())
      const result = await apiFetch<ITActivitySummary>(`/it-activity/summary?${params}`)

      // Ignore any response that belongs to an older selector/filter state.
      if (requestId !== requestSequence.current) return
      if (result.month.key !== requestedMonth) {
        throw new Error(`Recent Changes returned ${result.month.key} while ${requestedMonth} was selected`)
      }

      setData(result)
      setCurrentPage(1)
      setSelected(current => current && result.items.some(item => item.activity_id === current.activity_id) ? current : result.items[0] || null)
    } catch (err) {
      if (requestId !== requestSequence.current) return
      setError(err instanceof Error ? err.message : 'Unable to load monthly activity')
    } finally {
      if (requestId === requestSequence.current) setLoading(false)
    }
  }

  useEffect(() => {
    const currentRequest = requestSequence.current + 1
    void load(true)
    return () => {
      if (requestSequence.current === currentRequest) requestSequence.current += 1
    }
  }, [selectedMonth, department, deviceCategory, changedBy, actionType])

  const donutStyle = useMemo<CSSProperties>(() => {
    if (!data || data.visual_summary.length === 0) return { background: '#e5edf4' }
    const total = data.visual_summary.reduce((sum, item) => sum + item.value, 0) || 1
    let cursor = 0
    const stops = data.visual_summary.map(item => {
      const start = cursor
      cursor += (item.value / total) * 100
      const key = item.name.toLowerCase().replaceAll(' ', '_')
      const color = sourceColors[key] || '#64748b'
      return `${color} ${start}% ${cursor}%`
    })
    return { background: `conic-gradient(${stops.join(',')})` }
  }, [data])

  function resetFilters() {
    setDepartment(''); setDeviceCategory(''); setChangedBy(''); setActionType(''); setSearch('')
  }

  const totalPages = Math.max(1, Math.ceil((data?.items.length || 0) / ACTIVITY_ROWS_PER_PAGE))
  const pageStartIndex = (currentPage - 1) * ACTIVITY_ROWS_PER_PAGE
  const paginatedItems = useMemo(
    () => data?.items.slice(pageStartIndex, pageStartIndex + ACTIVITY_ROWS_PER_PAGE) || [],
    [data, pageStartIndex],
  )
  const paginationItems = useMemo(() => getPaginationItems(currentPage, totalPages), [currentPage, totalPages])
  const firstVisibleRecord = data && data.items.length > 0 ? pageStartIndex + 1 : 0
  const lastVisibleRecord = data ? Math.min(pageStartIndex + ACTIVITY_ROWS_PER_PAGE, data.items.length) : 0

  function selectActivity(item: ITActivityItem) {
    setSelected(item)
    const itemIndex = data?.items.findIndex(candidate => candidate.activity_id === item.activity_id) ?? -1
    if (itemIndex >= 0) {
      setCurrentPage(Math.floor(itemIndex / ACTIVITY_ROWS_PER_PAGE) + 1)
    }
  }

  const kpis = data ? [
    { label: 'Assets Edited', value: data.summary.assets_edited, icon: FileClock },
    { label: 'Component Changes', value: data.summary.component_changes, icon: Cpu },
    { label: 'Laptop Handovers', value: data.summary.laptop_handovers, icon: Laptop },
    { label: 'Returns', value: data.summary.return_operations, icon: RotateCcw },
    { label: 'Purchases Recorded', value: data.summary.purchases_recorded, icon: ShoppingCart },
    { label: 'Detailed Activities', value: data.summary.total_activities, icon: CheckCircle2 },
  ] : []

  return (
    <>
      <DashboardHeader
        eyebrow="COMPLETE MONTHLY TRACEABILITY"
        title="IT Recent Changes & Monthly Activity"
        description="The selected reporting month controls where each activity appears. The actual system-recorded date and time remain visible separately, and activity remarks stay attached only to that record."
        meta={<>
          <span className="nk-meta-chip"><CalendarDays size={14} /> Reporting month {selectedMonth}</span>
          <span className="nk-meta-chip"><FileClock size={14} /> Server-recorded date & time preserved</span>
          <span className="nk-meta-chip"><Search size={14} /> {data ? `${data.summary.total_activities} activities · ${data.filters.users.length} users in scope` : 'Loading activity scope'}</span>
        </>}
      />
      {error && <div className="error-message">{error}</div>}

      <section className="panel activity-filter-panel">
        <label><CalendarDays size={17} /><span>Month</span><input type="month" value={selectedMonth} onChange={event => setSelectedMonth(event.target.value)} /></label>
        <label><span>Department</span><select value={department} onChange={event => setDepartment(event.target.value)}><option value="">All departments</option>{data?.filters.departments.map(item => <option key={item}>{item}</option>)}</select></label>
        <label><span>Device Type</span><select value={deviceCategory} onChange={event => setDeviceCategory(event.target.value)}><option value="">All device types</option>{data?.filters.device_categories.map(item => <option key={item}>{item}</option>)}</select></label>
        <label><span>Changed By</span><select value={changedBy} onChange={event => setChangedBy(event.target.value)}><option value="">All users</option>{data?.filters.users.map(item => <option key={item}>{item}</option>)}</select></label>
        <label><span>Action Type</span><select value={actionType} onChange={event => setActionType(event.target.value)}><option value="">All actions</option>{data?.filters.action_types.map(item => <option key={item}>{item}</option>)}</select></label>
        <div className="activity-filter-actions">
          {selectedMonth !== presentMonth && <button className="secondary-button" onClick={returnToPresent}><RotateCcw size={16} /> Return to Present</button>}
          <button className="secondary-button" onClick={resetFilters}><RefreshCw size={16} /> Clear</button>
          <button className="primary-button" onClick={() => void downloadFile(`/it-activity/monthly.xlsx?month=${encodeURIComponent(selectedMonth)}`, `NakshaTech IT Monthly Activity - ${selectedMonth}.xlsx`)}><ArrowDownToLine size={17} /> Download Monthly Excel</button>
        </div>
        <label className="activity-search"><Search size={17} /><input value={search} onChange={event => setSearch(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') void load() }} placeholder="Search asset tag, workstation, user, field or reason" /><button onClick={() => void load()}>Search</button></label>
      </section>

      {loading && <div className="loading-state">Loading month-wise activity…</div>}
      {data && !loading && <>
        <section className="activity-kpi-grid">
          {kpis.map(item => { const Icon = item.icon; return <article className="activity-kpi-card" key={item.label}><span className="activity-kpi-icon"><Icon size={22} /></span><div><small>{item.label}</small><strong>{item.value}</strong><span>{data.month.label}</span></div></article> })}
        </section>

        <section className="activity-dashboard-grid">
          <article className="panel activity-timeline-panel">
            <div className="panel-title-row"><div><span className="section-kicker">RECENT ACTIVITY</span><h2>Activity Timeline</h2></div><span className="record-count">{data.total}</span></div>
            <div className="activity-timeline">
              {data.timeline.length === 0 && <div className="empty-state">No activity is recorded for this month.</div>}
              {data.timeline.map(item => <button className={`timeline-entry ${selected?.activity_id === item.activity_id ? 'selected' : ''}`} key={item.activity_id} onClick={() => selectActivity(item)}>
                <span className="timeline-dot" style={{ background: sourceColors[item.source_type] || '#64748b' }} />
                <span className="timeline-copy"><small>Effective: {item.reporting_month || selectedMonth} · Recorded: {item.activity_date} {item.activity_time || ''}</small><strong>{item.action_label}</strong><span>{item.cpu_asset_tag || item.asset_code || item.field_or_component || 'General IT activity'}</span><em>{item.performed_by || 'Historical source record'}</em></span>
              </button>)}
            </div>
          </article>

          <article className="panel activity-table-panel">
            <div className="panel-title-row"><div><span className="section-kicker">FIELD-BY-FIELD DETAILS</span><h2>Detailed Monthly Changes</h2></div><span className="record-count">{data.items.length} records</span></div>
            <div className="table-scroll activity-table-scroll"><table className="activity-table"><thead><tr><th>Reporting Month</th><th>System Recorded</th><th>User</th><th>Asset</th><th>Action</th><th>Field / Component</th><th>Old Value</th><th>New Value</th><th>Reason</th></tr></thead><tbody>
              {paginatedItems.length === 0 && <tr className="activity-empty-row"><td colSpan={9}>No detailed changes match the selected month and filters.</td></tr>}
              {paginatedItems.map(item => <tr key={item.activity_id} onClick={() => selectActivity(item)} className={selected?.activity_id === item.activity_id ? 'selected-row' : ''}><td>{item.reporting_month || selectedMonth}</td><td>{item.activity_date}<small>{item.activity_time}</small></td><td>{item.performed_by || 'Historical record'}<small>{item.performed_by_role}</small></td><td>{item.cpu_asset_tag || item.asset_code || '—'}<small>{item.workstation_no}</small></td><td><span className={`activity-badge ${item.source_type}`}>{item.action_label}</span></td><td>{item.field_or_component || '—'}</td><td>{displayValue(item.old_value)}</td><td>{displayValue(item.new_value)}</td><td>{item.reason || item.remarks || '—'}</td></tr>)}
            </tbody></table></div>
            <div className="activity-pagination" aria-label="Detailed monthly changes pagination">
              <span className="activity-pagination-summary">Showing {firstVisibleRecord}–{lastVisibleRecord} of {data.items.length} records</span>
              <div className="activity-pagination-controls">
                <button type="button" onClick={() => setCurrentPage(page => Math.max(1, page - 1))} disabled={currentPage === 1} aria-label="Previous page"><ChevronLeft size={16} /><span>Previous</span></button>
                <div className="activity-page-numbers">
                  {paginationItems.map(item => typeof item === 'number' ? (
                    <button type="button" key={item} className={currentPage === item ? 'active' : ''} onClick={() => setCurrentPage(item)} aria-current={currentPage === item ? 'page' : undefined}>{item}</button>
                  ) : <span key={item} className="activity-page-ellipsis" aria-hidden="true">…</span>)}
                </div>
                <button type="button" onClick={() => setCurrentPage(page => Math.min(totalPages, page + 1))} disabled={currentPage === totalPages} aria-label="Next page"><span>Next</span><ChevronRight size={16} /></button>
              </div>
            </div>
          </article>

          <article className="panel activity-visual-panel">
            <div><span className="section-kicker">MONTHLY VISUAL SUMMARY</span><h2>Activity Distribution</h2></div>
            <div className="activity-donut-wrap"><div className="activity-donut" style={donutStyle}><div><strong>{data.summary.total_activities}</strong><span>Rows tracked</span></div></div></div>
            <div className="activity-legend">{data.visual_summary.map(item => { const key = item.name.toLowerCase().replaceAll(' ', '_'); return <span key={item.name}><i style={{ background: sourceColors[key] || '#64748b' }} /><b>{item.name}</b><em>{item.value}</em></span> })}</div>
            <div className="activity-user-summary"><h3><UserRoundCheck size={17} /> User Activity</h3>{data.user_activity.slice(0, 8).map(item => <span key={item.name}><b>{item.name}</b><em>{item.value}</em></span>)}</div>
          </article>
        </section>

        <section className="panel activity-detail-panel">
          <div className="panel-title-row"><div><span className="section-kicker">SELECTED AUDIT RECORD</span><h2>View Change</h2></div>{selected && <span className="activity-id">{selected.batch_code}</span>}</div>
          {!selected ? <div className="empty-state">Select an activity to view its full details.</div> : <div className="activity-detail-grid">
            <span><small>Asset / Tag</small><strong>{selected.cpu_asset_tag || selected.asset_code || 'Not linked'}</strong></span>
            <span><small>Action</small><strong>{selected.action_label}</strong></span>
            <span><small>Changed By</small><strong>{selected.performed_by || 'Historical record'}</strong></span>
            <span><small>Effective Reporting Month</small><strong>{selected.reporting_month || selectedMonth}</strong></span><span><small>Actually Recorded On</small><strong>{selected.activity_date} {selected.activity_time}</strong></span>
            <span><small>Field / Component</small><strong>{selected.field_or_component || '—'}</strong></span>
            <span><small>Old Value</small><strong>{displayValue(selected.old_value)}</strong></span>
            <span><small>New Value</small><strong>{displayValue(selected.new_value)}</strong></span>
            <span><small>Reason / Remarks</small><strong>{selected.reason || selected.remarks || '—'}</strong></span>
          </div>}
        </section>
      </>}
    </>
  )
}
