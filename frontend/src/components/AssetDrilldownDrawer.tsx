import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  BarChart3,
  Download,
  HardDrive,
  Laptop,
  Monitor,
  PackageOpen,
  PieChart,
  RefreshCcw,
  Repeat2,
  RotateCcw,
  Search,
  Smartphone,
  UserCheck,
  Wrench,
  X,
} from 'lucide-react'
import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch, downloadFile } from '../lib/api'
import { DonutChart, HorizontalBars } from './Charts'
import type { Asset, ITAssetDrilldownData, ITAssetDrilldownSelection } from '../types'

type DrawerFilterField = 'department' | 'device_type' | 'status' | 'location' | 'work_mode'

interface DrawerFilters {
  search: string
  department: string
  device_type: string
  status: string
  location: string
  work_mode: string
  sort_by: string
  sort_dir: 'asc' | 'desc'
}

const EMPTY_FILTERS: DrawerFilters = {
  search: '',
  department: '',
  device_type: '',
  status: '',
  location: '',
  work_mode: '',
  sort_by: 'asset_code',
  sort_dir: 'asc',
}

const summaryCards = [
  { key: 'total', label: 'Total', icon: HardDrive, filter: null, tone: 'blue' },
  { key: 'computers', label: 'Computers', icon: Monitor, filter: ['device_type', 'Computer'], tone: 'navy' },
  { key: 'laptops', label: 'Laptops', icon: Laptop, filter: ['device_type', 'Laptop'], tone: 'cyan' },
  { key: 'smartphones', label: 'Smartphones', icon: Smartphone, filter: ['device_type', 'Smartphone'], tone: 'purple' },
  { key: 'assigned', label: 'Assigned / In Use', icon: UserCheck, filter: ['status', 'assigned'], tone: 'green' },
  { key: 'available', label: 'Available', icon: PackageOpen, filter: ['status', 'available'], tone: 'teal' },
  { key: 'repair', label: 'Under Repair', icon: Wrench, filter: ['status', 'repair'], tone: 'orange' },
  { key: 'replacement_pending', label: 'Replacement Pending', icon: Repeat2, filter: ['status', 'replacement_pending'], tone: 'red' },
] as const

function label(value?: string) {
  return (value || 'Not recorded').replaceAll('_', ' ').replace(/\b\w/g, character => character.toUpperCase())
}

function compactStorage(asset: Asset) {
  return [asset.ssd && `SSD ${asset.ssd}`, asset.hdd && `HDD ${asset.hdd}`].filter(Boolean).join(' · ') || 'Not recorded'
}

function buildParams(
  selectedMonth: string,
  selection: ITAssetDrilldownSelection,
  filters: DrawerFilters,
  page: number,
  pageSize: number,
) {
  const params = new URLSearchParams({
    month: selectedMonth,
    scope: selection.scope,
    page: String(page),
    page_size: String(pageSize),
    sort_by: filters.sort_by,
    sort_dir: filters.sort_dir,
  })
  if (selection.value) params.set('scope_value', selection.value)
  if (filters.search.trim()) params.set('search', filters.search.trim())
  if (filters.department) params.set('department', filters.department)
  if (filters.device_type) params.set('device_type', filters.device_type)
  if (filters.status) params.set('status', filters.status)
  if (filters.location) params.set('location', filters.location)
  if (filters.work_mode) params.set('work_mode', filters.work_mode)
  return params
}

export function AssetDrilldownDrawer({
  selectedMonth,
  selection,
  onClose,
}: {
  selectedMonth: string
  selection: ITAssetDrilldownSelection
  onClose: () => void
}) {
  const [data, setData] = useState<ITAssetDrilldownData | null>(null)
  const [filters, setFilters] = useState<DrawerFilters>(EMPTY_FILTERS)
  const [searchDraft, setSearchDraft] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState('')
  const [visualsOpen, setVisualsOpen] = useState(false)
  const requestSequence = useRef(0)

  useEffect(() => {
    setFilters(EMPTY_FILTERS)
    setSearchDraft('')
    setPage(1)
    setExpandedId(null)
    setVisualsOpen(false)
    setData(null)
  }, [selectedMonth, selection.scope, selection.value])

  useEffect(() => {
    const originalOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => {
      document.body.style.overflow = originalOverflow
      window.removeEventListener('keydown', closeOnEscape)
    }
  }, [onClose])

  useEffect(() => {
    const controller = new AbortController()
    const requestId = ++requestSequence.current
    const params = buildParams(selectedMonth, selection, filters, page, pageSize)
    setLoading(true)
    setError('')
    setData(null)

    void apiFetch<ITAssetDrilldownData>(`/dashboard/it/assets?${params.toString()}`, { signal: controller.signal })
      .then(result => {
        if (requestId !== requestSequence.current) return
        if (result.month.key !== selectedMonth) throw new Error(`The server returned ${result.month.label} instead of the selected month.`)
        setData(result)
        if (result.page !== page) setPage(result.page)
      })
      .catch(err => {
        if (controller.signal.aborted || requestId !== requestSequence.current) return
        setError(err instanceof Error ? err.message : 'Unable to load asset details')
      })
      .finally(() => {
        if (!controller.signal.aborted && requestId === requestSequence.current) setLoading(false)
      })

    return () => controller.abort()
  }, [selectedMonth, selection, filters, page, pageSize])

  const activeFilterCount = useMemo(() => [
    filters.search,
    filters.department,
    filters.device_type,
    filters.status,
    filters.location,
    filters.work_mode,
  ].filter(Boolean).length, [filters])

  function submitSearch(event: FormEvent) {
    event.preventDefault()
    setPage(1)
    setFilters(current => ({ ...current, search: searchDraft.trim() }))
  }

  function updateFilter(field: DrawerFilterField, value: string) {
    setPage(1)
    setExpandedId(null)
    setFilters(current => ({ ...current, [field]: value }))
  }

  function useVisualFilter(field: DrawerFilterField, value: string) {
    updateFilter(field, filters[field] === value ? '' : value)
  }

  function useSummaryFilter(filter: readonly [string, string] | null) {
    if (!filter) {
      setPage(1)
      setFilters(current => ({ ...current, device_type: '', status: '' }))
      return
    }
    const [field, value] = filter as ['device_type' | 'status', string]
    updateFilter(field, filters[field] === value ? '' : value)
  }

  function toggleVisuals() {
    setVisualsOpen(current => !current)
  }

  function clearFilters() {
    setFilters(EMPTY_FILTERS)
    setSearchDraft('')
    setPage(1)
    setExpandedId(null)
  }

  async function downloadResults() {
    setDownloading(true)
    setError('')
    try {
      const params = buildParams(selectedMonth, selection, filters, 1, 100)
      params.delete('page')
      params.delete('page_size')
      await downloadFile(
        `/reports/it-dashboard-assets.xlsx?${params.toString()}`,
        `NakshaTech ${data?.scope.label || 'IT Assets'} - ${data?.month.label || selectedMonth}.xlsx`,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to download the filtered Excel')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="asset-drilldown-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
      <aside className="asset-drilldown-drawer" role="dialog" aria-modal="true" aria-label="IT asset dashboard details">
        <header className="drilldown-header">
          <div>
            <span className="section-kicker">DASHBOARD DRILL-DOWN</span>
            <h2>{data?.scope.label || 'Asset Details'}</h2>
            <p>{data?.month.label || selectedMonth} inventory snapshot · read-only dashboard view</p>
          </div>
          <div className="drilldown-header-actions">
            <button
              type="button"
              className={`drilldown-visual-toggle ${visualsOpen ? 'active' : ''}`}
              onClick={toggleVisuals}
              aria-expanded={visualsOpen}
              aria-controls="asset-drilldown-visuals"
              disabled={!data || data.filtered_total === 0}
            >
              <BarChart3 size={17} />
              <span>{visualsOpen ? 'Hide Visuals' : 'Show Visuals'}</span>
              <ChevronUp size={16} className={visualsOpen ? '' : 'collapsed'} />
            </button>
            <button className="icon-button" onClick={onClose} aria-label="Close asset details"><X /></button>
          </div>
        </header>

        {error && <div className="error-message drilldown-error"><span>{error}</span><button className="secondary-button" onClick={() => setFilters(current => ({ ...current }))}><RefreshCcw size={15} /> Retry</button></div>}

        <section className="drilldown-summary-grid">
          {summaryCards.map(card => {
            const Icon = card.icon
            const value = data?.summary[card.key] ?? 0
            const filter = card.filter
            const active = !filter
              ? !filters.device_type && !filters.status
              : filters[filter[0] as 'device_type' | 'status'] === filter[1]
            return (
              <button
                key={card.key}
                type="button"
                className={`drilldown-summary-card tone-${card.tone} ${active ? 'active' : ''}`}
                onClick={() => useSummaryFilter(filter)}
                disabled={!data || (value === 0 && !active)}
              >
                <Icon size={18} />
                <span>{card.label}</span>
                <strong>{value}</strong>
              </button>
            )
          })}
        </section>


        {visualsOpen && data && data.filtered_total > 0 && (
          <section id="asset-drilldown-visuals" className="drilldown-visual-section" aria-label={`${data.scope.label} visual analytics`}>
            <div className="drilldown-visual-heading">
              <div>
                <span className="section-kicker">VISUAL ANALYSIS</span>
                <h3>{data.scope.label}</h3>
                <p>Charts use all {data.filtered_total} matching records, not only the current table page. Click a slice or bar to filter the details below.</p>
              </div>
              <span className="drilldown-visual-total"><BarChart3 size={16} /><strong>{data.filtered_total}</strong> records visualized</span>
            </div>

            <div className={`drilldown-visual-grid ${selection.scope === 'all' ? 'three-visuals' : 'two-visuals'}`}>
              {selection.scope !== 'device' && (
                <article className="drilldown-visual-card">
                  <div className="drilldown-chart-title"><PieChart size={16} /><div><strong>Device Mix</strong><span>Computers, laptops and smartphones</span></div></div>
                  <DonutChart
                    data={data.visuals.device_distribution}
                    centerLabel="Assets"
                    ariaLabel={`${data.scope.label} by device type`}
                    activeKey={filters.device_type}
                    onSelect={item => useVisualFilter('device_type', item.key || item.name)}
                  />
                </article>
              )}

              {selection.scope !== 'status' && (
                <article className="drilldown-visual-card">
                  <div className="drilldown-chart-title"><PieChart size={16} /><div><strong>Status Distribution</strong><span>Assigned, available, repair and replacement</span></div></div>
                  <DonutChart
                    data={data.visuals.status_distribution}
                    centerLabel="Assets"
                    ariaLabel={`${data.scope.label} by asset status`}
                    activeKey={filters.status}
                    onSelect={item => useVisualFilter('status', item.key || item.name)}
                  />
                </article>
              )}

              {selection.scope !== 'department' && (
                <article
                  className="drilldown-visual-card department-visual-card"
                  data-compact={data.visuals.department_distribution.length <= 4 ? 'true' : 'false'}
                >
                  <div className="drilldown-chart-title"><BarChart3 size={16} /><div><strong>Department Allocation</strong><span>Distribution across NakshaTech teams</span></div></div>
                  <HorizontalBars
                    data={data.visuals.department_distribution}
                    maxItems={8}
                    activeName={filters.department}
                    onSelect={item => useVisualFilter('department', item.key || item.name)}
                  />
                </article>
              )}
            </div>
          </section>
        )}

        <section className="drilldown-toolbar">
          <form className="drilldown-search" onSubmit={submitSearch}>
            <Search size={17} />
            <input value={searchDraft} onChange={event => setSearchDraft(event.target.value)} placeholder="Search tag, workstation, employee, system, IP..." />
            <button type="submit">Search</button>
          </form>
          <button className="secondary-button" onClick={() => void downloadResults()} disabled={downloading || !data}>
            <Download size={16} /> {downloading ? 'Preparing...' : 'Download Current Results'}
          </button>
        </section>

        <section className="drilldown-filter-grid">
          <label>Department<select value={filters.department} onChange={event => updateFilter('department', event.target.value)}><option value="">All departments</option>{data?.filter_options.departments.map(item => <option key={item}>{item}</option>)}</select></label>
          <label>Device<select value={filters.device_type} onChange={event => updateFilter('device_type', event.target.value)}><option value="">All devices</option>{data?.filter_options.devices.map(item => <option key={item}>{item}</option>)}</select></label>
          <label>Status<select value={filters.status} onChange={event => updateFilter('status', event.target.value)}><option value="">All statuses</option><option value="assigned">Assigned / In Use</option>{data?.filter_options.statuses.filter(item => !['assigned', 'in_use'].includes(item)).map(item => <option key={item} value={item}>{label(item)}</option>)}</select></label>
          <label>Location<select value={filters.location} onChange={event => updateFilter('location', event.target.value)}><option value="">All locations</option>{data?.filter_options.locations.map(item => <option key={item}>{item}</option>)}</select></label>
          <label>Work Mode<select value={filters.work_mode} onChange={event => updateFilter('work_mode', event.target.value)}><option value="">All work modes</option>{data?.filter_options.work_modes.map(item => <option key={item} value={item}>{label(item)}</option>)}</select></label>
          <label>Sort<select value={`${filters.sort_by}:${filters.sort_dir}`} onChange={event => { const [sort_by, sort_dir] = event.target.value.split(':'); setPage(1); setFilters(current => ({ ...current, sort_by, sort_dir: sort_dir as 'asc' | 'desc' })) }}><option value="asset_code:asc">Asset ID A–Z</option><option value="cpu_asset_tag:asc">CPU / Asset Tag A–Z</option><option value="department:asc">Department A–Z</option><option value="used_by:asc">Employee A–Z</option><option value="status:asc">Status A–Z</option><option value="updated_at:desc">Recently updated</option></select></label>
          <button className="text-button drilldown-clear" onClick={clearFilters} disabled={activeFilterCount === 0}><RotateCcw size={15} /> Clear {activeFilterCount ? `${activeFilterCount} filter${activeFilterCount === 1 ? '' : 's'}` : 'filters'}</button>
        </section>

        <div className="drilldown-result-strip">
          <span><strong>{data?.filtered_total ?? 0}</strong> matching record{data?.filtered_total === 1 ? '' : 's'}</span>
          <span>Scope total: <strong>{data?.scope_total ?? 0}</strong></span>
          {activeFilterCount > 0 && <span className="filtered-badge">Filtered view</span>}
        </div>

        <section className="drilldown-table-shell">
          {loading && <div className="drilldown-loading"><RefreshCcw className="spin" /><span>Loading accurate asset details…</span></div>}
          {!loading && data && data.assets.length === 0 && <div className="empty-state drilldown-empty">No assets match the selected dashboard card and filters.</div>}
          {!loading && data && data.assets.length > 0 && <div className="table-wrap"><table className="drilldown-table">
            <thead><tr><th>CPU / Asset Tag</th><th>System / Workstation</th><th>Device</th><th>Department</th><th>Employee</th><th>Status</th><th>Location</th><th /></tr></thead>
            <tbody>{data.assets.map(asset => {
              const expanded = expandedId === asset.id
              return [
                <tr key={`row-${asset.id}`} className={expanded ? 'expanded' : ''}>
                  <td><strong>{asset.cpu_asset_tag || asset.asset_code}</strong><small>{asset.asset_code}</small></td>
                  <td>{asset.system_name || '—'}<small>{asset.workstation_no || 'No workstation'}</small></td>
                  <td>{asset.device_type}</td>
                  <td>{asset.department || 'Unassigned'}</td>
                  <td>{asset.used_by || 'Unassigned'}</td>
                  <td><span className={`status ${asset.status}`}>{label(asset.status)}</span></td>
                  <td>{asset.location || 'Unknown'}</td>
                  <td><button className="icon-button compact" onClick={() => setExpandedId(expanded ? null : asset.id)} aria-label={expanded ? 'Collapse details' : 'Expand details'}><ChevronDown className={expanded ? 'rotated' : ''} /></button></td>
                </tr>,
                expanded && <tr key={`details-${asset.id}`} className="drilldown-expanded-row"><td colSpan={8}><div className="drilldown-asset-details">
                  <div><span>Processor</span><strong>{asset.processor || 'Not recorded'}</strong></div>
                  <div><span>Memory</span><strong>{asset.memory_gb || 'Not recorded'}</strong></div>
                  <div><span>Storage</span><strong>{compactStorage(asset)}</strong></div>
                  <div><span>Graphics</span><strong>{asset.graphics_card || 'Not recorded'}</strong></div>
                  <div><span>Operating System</span><strong>{asset.operating_system || 'Not recorded'}</strong></div>
                  <div><span>IP Address</span><strong>{asset.ip_address || 'Not recorded'}</strong></div>
                  <div><span>MAC Address</span><strong>{asset.mac_address || 'Not recorded'}</strong></div>
                  <div><span>Network</span><strong>{asset.network_type || 'Not recorded'}</strong></div>
                  <div><span>Monitor Tag(s)</span><strong>{asset.monitor_asset_tags || 'Not recorded'}</strong></div>
                  <div><span>Mouse / Keyboard</span><strong>{[asset.mouse_asset_tag, asset.keyboard_asset_tag].filter(Boolean).join(' / ') || 'Not recorded'}</strong></div>
                  <div><span>Approved By</span><strong>{asset.approved_by || 'Not recorded'}</strong></div>
                  <div><span>Work Mode</span><strong>{label(asset.work_mode)}</strong></div>
                  <div className="wide"><span>Asset Master Remarks</span><strong>{asset.remarks || 'No permanent asset remark'}</strong></div>
                </div></td></tr>,
              ]
            })}</tbody>
          </table></div>}
        </section>

        <footer className="drilldown-footer">
          <label>Rows<select value={pageSize} onChange={event => { setPageSize(Number(event.target.value)); setPage(1) }}><option value={10}>10</option><option value={20}>20</option><option value={50}>50</option><option value={100}>100</option></select></label>
          <span>{data ? `Page ${data.page} of ${data.pages}` : 'Page 1 of 1'}</span>
          <div className="pagination-buttons">
            <button className="icon-button" disabled={!data || data.page <= 1 || loading} onClick={() => setPage(current => Math.max(1, current - 1))}><ChevronLeft /></button>
            <button className="icon-button" disabled={!data || data.page >= data.pages || loading} onClick={() => setPage(current => current + 1)}><ChevronRight /></button>
          </div>
          <button className="secondary-button" onClick={onClose}>Close</button>
        </footer>
      </aside>
    </div>
  )
}
