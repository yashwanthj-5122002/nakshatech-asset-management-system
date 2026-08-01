import type { DistributionItem } from '../types'

export function DonutChart({ data, centerLabel }: { data: DistributionItem[]; centerLabel: string }) {
  const total = data.reduce((sum, item) => sum + item.value, 0) || 1
  let cursor = 0
  const colors = ['#12c9f5', '#1769e8', '#35a6dd', '#69b8e5', '#3d7fc2', '#8bcbe9']
  const stops = data.map((item, index) => {
    const start = cursor
    cursor += (item.value / total) * 100
    return `${colors[index % colors.length]} ${start}% ${cursor}%`
  }).join(', ')
  return (
    <div className="donut-wrap">
      <div className="donut" style={{ background: `conic-gradient(${stops || '#16334d 0 100%'})` }}>
        <div><strong>{total}</strong><span>{centerLabel}</span></div>
      </div>
      <div className="legend-list">
        {data.map((item, index) => (
          <div key={item.name}><i style={{ background: colors[index % colors.length] }} /><span>{item.name}</span><strong>{item.value}</strong></div>
        ))}
      </div>
    </div>
  )
}

export function HorizontalBars({ data, maxItems = 8 }: { data: DistributionItem[]; maxItems?: number }) {
  const shown = data.slice(0, maxItems)
  const max = Math.max(...shown.map(item => item.value), 1)
  return (
    <div className="bar-list">
      {shown.map(item => (
        <div className="bar-row" key={item.name}>
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
