import { useMemo, useState, type KeyboardEvent } from 'react'
import type { ActivityMetricKey, ActivityTrendPoint, DistributionItem } from '../types'

const CHART_COLORS = [
  '#0b4f8a',
  '#12aabd',
  '#4c78db',
  '#7557b7',
  '#2f9a6e',
  '#dc922f',
  '#cf5b68',
  '#687d91',
  '#1b879d',
  '#9361c7',
]

function itemKey(item: DistributionItem): string {
  return item.key || item.name
}

export function DonutChart({
  data,
  centerLabel,
  onSelect,
  activeKey,
  ariaLabel = 'Distribution chart',
}: {
  data: DistributionItem[]
  centerLabel: string
  onSelect?: (item: DistributionItem) => void
  activeKey?: string
  ariaLabel?: string
}) {
  const total = data.reduce((sum, item) => sum + Math.max(item.value, 0), 0)
  const radius = 43
  const circumference = 2 * Math.PI * radius
  const segments = useMemo(() => {
    let cursor = 0
    return data.map((item, index) => {
      const safeValue = Math.max(item.value, 0)
      const length = total > 0 ? (safeValue / total) * circumference : 0
      const segment = {
        item,
        color: CHART_COLORS[index % CHART_COLORS.length],
        length,
        offset: cursor,
      }
      cursor += length
      return segment
    })
  }, [circumference, data, total])

  function activate(item: DistributionItem) {
    onSelect?.(item)
  }

  return (
    <div className={`donut-wrap svg-donut-wrap ${onSelect ? 'interactive-chart' : ''}`}>
      <div className="svg-donut-shell">
        <svg className="svg-donut" viewBox="0 0 120 120" role="img" aria-label={ariaLabel}>
          <circle className="svg-donut-track" cx="60" cy="60" r={radius} />
          {segments.map(({ item, color, length, offset }) => {
            if (length <= 0) return null
            const key = itemKey(item)
            const active = activeKey === key
            return (
              <circle
                key={key}
                className={`svg-donut-segment ${onSelect ? 'clickable' : ''} ${active ? 'active' : ''}`}
                cx="60"
                cy="60"
                r={radius}
                pathLength={circumference}
                stroke={color}
                strokeDasharray={`${length} ${Math.max(circumference - length, 0)}`}
                strokeDashoffset={-offset}
                tabIndex={onSelect ? 0 : undefined}
                role={onSelect ? 'button' : undefined}
                aria-label={onSelect ? `${item.name}: ${item.value}. Open matching asset details.` : `${item.name}: ${item.value}`}
                onClick={() => activate(item)}
                onKeyDown={(event: KeyboardEvent<SVGCircleElement>) => {
                  if (!onSelect) return
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    activate(item)
                  }
                }}
              >
                <title>{item.name}: {item.value}</title>
              </circle>
            )
          })}
        </svg>
        <div className="svg-donut-center" aria-hidden="true">
          <strong>{total}</strong>
          <span>{centerLabel}</span>
        </div>
      </div>

      <div className="legend-list chart-legend-list">
        {data.map((item, index) => {
          const key = itemKey(item)
          const active = activeKey === key
          const content = <><i style={{ background: CHART_COLORS[index % CHART_COLORS.length] }} /><span>{item.name}</span><strong>{item.value}</strong></>
          return onSelect ? (
            <button
              type="button"
              className={active ? 'active' : ''}
              key={key}
              onClick={() => activate(item)}
              aria-label={`Open ${item.name} asset details`}
            >
              {content}
            </button>
          ) : (
            <div key={key}>{content}</div>
          )
        })}
      </div>
    </div>
  )
}

export function HorizontalBars({
  data,
  maxItems = 8,
  onSelect,
  activeName,
}: {
  data: DistributionItem[]
  maxItems?: number
  onSelect?: (item: DistributionItem) => void
  activeName?: string
}) {
  const shown = data.slice(0, maxItems)
  const max = Math.max(...shown.map(item => item.value), 1)
  return (
    <div className="bar-list">
      {shown.map(item => (
        <div
          className={`bar-row ${onSelect ? 'interactive-bar-row' : ''} ${activeName === item.name ? 'active' : ''}`}
          key={item.name}
          role={onSelect ? 'button' : undefined}
          tabIndex={onSelect ? 0 : undefined}
          onClick={() => onSelect?.(item)}
          onKeyDown={(event: KeyboardEvent<HTMLDivElement>) => {
            if (!onSelect) return
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault()
              onSelect(item)
            }
          }}
          aria-label={onSelect ? `Open ${item.name} department asset details` : undefined}
        >
          <div className="bar-label"><span>{item.name}</span><strong>{item.value}</strong></div>
          <div className="bar-track"><div style={{ width: `${Math.max((item.value / max) * 100, 4)}%` }} /></div>
        </div>
      ))}
    </div>
  )
}

export function StatusGrid({ data }: { data: DistributionItem[] }) {
  return (
    <div className="status-grid">
      {data.slice(0, 10).map(item => (
        <article key={item.name}>
          <span>{item.name}</span>
          <strong>{item.value}</strong>
        </article>
      ))}
    </div>
  )
}

const ACTIVITY_METRICS: Array<{ key: ActivityMetricKey; label: string; compact: string }> = [
  { key: 'total_activities', label: 'Total activities', compact: 'Total' },
  { key: 'asset_edit_operations', label: 'Asset edit saves', compact: 'Edits' },
  { key: 'component_changes', label: 'Component changes', compact: 'Components' },
  { key: 'handover_operations', label: 'Handovers', compact: 'Handovers' },
  { key: 'return_operations', label: 'Returns', compact: 'Returns' },
  { key: 'purchases_recorded', label: 'Purchases', compact: 'Purchases' },
]

function roundedMaximum(value: number): number {
  if (value <= 4) return 4
  if (value <= 10) return Math.ceil(value / 2) * 2
  if (value <= 30) return Math.ceil(value / 5) * 5
  if (value <= 100) return Math.ceil(value / 10) * 10
  return Math.ceil(value / 25) * 25
}

function shortMonthLabel(label: string): string {
  const [month, year] = label.split(' ')
  return `${month?.slice(0, 3) || label}${year ? ` ${year.slice(-2)}` : ''}`
}

export function ActivityTrendChart({
  data,
  selectedMonth,
  loading,
  error,
  onRetry,
}: {
  data: ActivityTrendPoint[]
  selectedMonth: string
  loading: boolean
  error: string
  onRetry: () => void
}) {
  const [metric, setMetric] = useState<ActivityMetricKey>('total_activities')
  const width = 840
  const height = 300
  const margin = { top: 26, right: 24, bottom: 58, left: 54 }
  const plotWidth = width - margin.left - margin.right
  const plotHeight = height - margin.top - margin.bottom
  const values = data.map(point => point[metric])
  const maximum = roundedMaximum(Math.max(...values, 0))
  const x = (index: number) => margin.left + (data.length <= 1 ? plotWidth / 2 : (index / (data.length - 1)) * plotWidth)
  const y = (value: number) => margin.top + plotHeight - (value / maximum) * plotHeight
  const linePath = data.map((point, index) => `${index === 0 ? 'M' : 'L'} ${x(index)} ${y(point[metric])}`).join(' ')
  const areaPath = data.length
    ? `${linePath} L ${x(data.length - 1)} ${margin.top + plotHeight} L ${x(0)} ${margin.top + plotHeight} Z`
    : ''
  const selectedMetric = ACTIVITY_METRICS.find(item => item.key === metric) || ACTIVITY_METRICS[0]
  const latestValue = data.at(-1)?.[metric] || 0

  return (
    <div className="activity-trend-chart">
      <div className="activity-metric-toolbar" aria-label="Choose activity metric">
        {ACTIVITY_METRICS.map(item => (
          <button
            type="button"
            key={item.key}
            className={metric === item.key ? 'active' : ''}
            onClick={() => setMetric(item.key)}
          >
            {item.compact}
          </button>
        ))}
      </div>

      {loading && <div className="chart-loading-state"><span className="chart-loading-line" /><span>Loading monthly activity graph…</span></div>}
      {!loading && error && <div className="chart-error-state"><span>{error}</span><button type="button" onClick={onRetry}>Retry</button></div>}
      {!loading && !error && !data.length && <div className="empty-state">No monthly activity data is available.</div>}

      {!loading && !error && data.length > 0 && (
        <>
          <div className="activity-trend-summary">
            <div><span>Selected metric</span><strong>{selectedMetric.label}</strong></div>
            <div><span>Latest plotted value</span><strong>{latestValue}</strong></div>
            <div><span>Period</span><strong>{data.length} months</strong></div>
          </div>
          <div className="activity-chart-scroll">
            <svg className="activity-line-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${selectedMetric.label} trend across ${data.length} months`}>
              <defs>
                <linearGradient id="activityTrendArea" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#0a8fb2" stopOpacity="0.26" />
                  <stop offset="100%" stopColor="#0a8fb2" stopOpacity="0.02" />
                </linearGradient>
              </defs>
              {[0, 1, 2, 3, 4].map(index => {
                const tickValue = (maximum / 4) * index
                const tickY = y(tickValue)
                return (
                  <g key={index}>
                    <line className="activity-grid-line" x1={margin.left} x2={width - margin.right} y1={tickY} y2={tickY} />
                    <text className="activity-axis-label" x={margin.left - 12} y={tickY + 4} textAnchor="end">{Math.round(tickValue)}</text>
                  </g>
                )
              })}
              {areaPath && <path className="activity-area" d={areaPath} />}
              {linePath && <path className="activity-line" d={linePath} />}
              {data.map((point, index) => {
                const active = point.month === selectedMonth
                const value = point[metric]
                return (
                  <g key={point.month} className={active ? 'selected-month-point' : ''}>
                    {active && <line className="activity-selected-guide" x1={x(index)} x2={x(index)} y1={margin.top} y2={margin.top + plotHeight} />}
                    <circle className="activity-point-halo" cx={x(index)} cy={y(value)} r={active ? 10 : 8} />
                    <circle className="activity-point" cx={x(index)} cy={y(value)} r={active ? 5.5 : 4.5}>
                      <title>{point.label} — {selectedMetric.label}: {value}</title>
                    </circle>
                    <text className="activity-value-label" x={x(index)} y={Math.max(y(value) - 13, 17)} textAnchor="middle">{value}</text>
                    <text className="activity-month-label" x={x(index)} y={height - 23} textAnchor="middle">{shortMonthLabel(point.label)}</text>
                  </g>
                )
              })}
            </svg>
          </div>
        </>
      )}
    </div>
  )
}
