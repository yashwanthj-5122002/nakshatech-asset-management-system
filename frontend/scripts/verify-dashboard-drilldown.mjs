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
  if (source.includes(text)) throw new Error(`${label}: forbidden navigation remains: ${text}`)
}

// This verifier intentionally checks frontend files only. The frontend Docker
// service mounts /app to the frontend folder and cannot access ../backend.
// Backend API/service checks run separately in the backend verification script.
const dashboard = read('src/pages/ITDashboard.tsx')
const drawer = read('src/components/AssetDrilldownDrawer.tsx')
const charts = read('src/components/Charts.tsx')
const statCard = read('src/components/StatCard.tsx')

requireText(dashboard, "setDrilldown({ scope: 'device', value: 'Computer' })", 'Computer card mapping')
requireText(dashboard, "setDrilldown({ scope: 'device', value: 'Laptop' })", 'Laptop card mapping')
requireText(dashboard, "setDrilldown({ scope: 'device', value: 'Smartphone' })", 'Smartphone card mapping')
requireText(dashboard, "setDrilldown({ scope: 'department', value: item.name })", 'Department bar mapping')
requireText(dashboard, '<AssetDrilldownDrawer', 'Same-page drawer rendering')
forbidText(dashboard, "navigate('/assets", 'Dashboard card drill-down')
forbidText(dashboard, "to={withITMonth('/assets", 'Dashboard card drill-down')

requireText(drawer, '/dashboard/it/assets?', 'Read-only drill-down API')
requireText(drawer, '/reports/it-dashboard-assets.xlsx?', 'Filtered Excel API')
requireText(drawer, 'requestSequence', 'Stale response protection')
requireText(drawer, 'new AbortController()', 'Request cancellation')
requireText(drawer, 'result.month.key !== selectedMonth', 'Reporting month validation')
requireText(drawer, 'read-only dashboard view', 'Read-only UI')
requireText(drawer, 'Asset Master Remarks', 'Permanent remarks labeling')
requireText(charts, 'onSelect?: (item: DistributionItem) => void', 'Clickable department bars')
requireText(statCard, 'onClick?: () => void', 'Clickable KPI cards')

console.log('DASHBOARD DRILL-DOWN FRONTEND VERIFICATION PASSED')
console.log('- Computer, laptop and smartphone cards map to their own device type')
console.log('- Department bars open the same-page read-only drawer')
console.log('- Month validation, request cancellation and latest-response protection are present')
console.log('- Filtered Excel request uses the selected drawer filters')
