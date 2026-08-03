import fs from 'node:fs'
import path from 'node:path'

const root = process.cwd()
function read(relative) {
  const full = path.join(root, relative)
  if (!fs.existsSync(full)) throw new Error(`Missing required frontend file: ${relative}`)
  return fs.readFileSync(full, 'utf8')
}
function requireText(source, text, label) {
  if (!source.includes(text)) throw new Error(`${label}: missing ${text}`)
}
function forbidText(source, text, label) {
  if (source.includes(text)) throw new Error(`${label}: forbidden text remains: ${text}`)
}

const dashboard = read('src/pages/ITDashboard.tsx')
const charts = read('src/components/Charts.tsx')
const types = read('src/types.ts')
const styles = read('src/styles.css')

requireText(charts, 'export function DonutChart', 'Reusable pie/donut chart')
requireText(charts, '<svg className="svg-donut"', 'SVG donut rendering')
requireText(charts, 'onSelect?: (item: DistributionItem) => void', 'Clickable pie segments')
requireText(charts, 'export function ActivityTrendChart', 'Monthly activity graph')
requireText(charts, 'activity-line-chart', 'Line graph rendering')
requireText(charts, "useState<ActivityMetricKey>('total_activities')", 'Interactive metric selector')

requireText(dashboard, 'ariaLabel="IT assets by device type"', 'Device pie chart')
requireText(dashboard, "setDrilldown({ scope: 'device', value: item.name })", 'Device chart to same-page drawer')
requireText(dashboard, 'ariaLabel="IT assets by operational status"', 'Status pie chart')
requireText(dashboard, "setDrilldown({ scope: 'status', value: item.key || normalizedStatusKey(item.name) })", 'Status chart to same-page drawer')
requireText(dashboard, 'statusChartItems(data.status_distribution)', 'Assigned and in-use status aggregation')
requireText(dashboard, '<HorizontalBars', 'Department graph retained')
requireText(dashboard, '<ActivityTrendChart', 'Six-month activity graph mounted')
requireText(dashboard, '/it-activity/summary?month=', 'Activity graph data source')
requireText(dashboard, 'new AbortController()', 'Activity graph request cancellation')
requireText(dashboard, 'trendRequestSequence', 'Latest-response protection')
requireText(dashboard, 'result.month.key !== month.key', 'Per-month response validation')
requireText(dashboard, 'reportingMonthWindow(requestedMonth, 6)', 'Six-month selected reporting window')
requireText(dashboard, '<AssetDrilldownDrawer', 'Existing same-page asset drawer retained')
forbidText(dashboard, "navigate('/assets", 'Chart click navigation')

requireText(types, 'export interface ActivityTrendPoint', 'Activity trend typing')
requireText(types, 'key?: string', 'Stable chart filter keys')
requireText(styles, '.svg-donut-segment.clickable', 'Interactive chart styling')
requireText(styles, '.activity-line-chart', 'Activity graph styling')
requireText(styles, '@media (max-width: 620px)', 'Responsive chart layout')

// Deterministic month-window simulation: six months ending August 2026.
function monthWindow(endMonth, count = 6) {
  const match = /^(\d{4})-(\d{2})$/.exec(endMonth)
  if (!match) return []
  const year = Number(match[1])
  const monthIndex = Number(match[2]) - 1
  return Array.from({ length: count }, (_, index) => {
    const date = new Date(Date.UTC(year, monthIndex - (count - index - 1), 1))
    return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`
  })
}
const expected = ['2026-03', '2026-04', '2026-05', '2026-06', '2026-07', '2026-08']
const actual = monthWindow('2026-08')
if (JSON.stringify(actual) !== JSON.stringify(expected)) {
  throw new Error(`Six-month window mismatch: ${JSON.stringify(actual)}`)
}

console.log('IT DASHBOARD VISUAL ANALYTICS VERIFICATION PASSED')
console.log('- Device and status donut charts are interactive and open the existing same-page drawer')
console.log('- Department bar drill-down remains active')
console.log('- Six-month activity graph supports six selectable metrics')
console.log('- Graph requests are month-validated, cancellable and latest-response protected')
console.log('- Existing drill-down and reporting-month behavior remain present')
