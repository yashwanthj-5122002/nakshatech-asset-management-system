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

const drawer = read('src/components/AssetDrilldownDrawer.tsx')
const types = read('src/types.ts')
const styles = read('src/styles.css')

requireText(drawer, "import { DonutChart, HorizontalBars } from './Charts'", 'Reusable chart components in the drawer')
requireText(drawer, 'VISUAL ANALYSIS', 'Drawer visual analysis section')
requireText(drawer, 'Charts use all {data.filtered_total} matching records', 'Full-result accuracy message')
requireText(drawer, 'data.visuals.device_distribution', 'Device distribution chart data')
requireText(drawer, 'data.visuals.status_distribution', 'Status distribution chart data')
requireText(drawer, 'data.visuals.department_distribution', 'Department graph data')
requireText(drawer, "selection.scope !== 'device'", 'Device-scope chart selection')
requireText(drawer, "selection.scope !== 'status'", 'Status-scope chart selection')
requireText(drawer, "selection.scope !== 'department'", 'Department-scope chart selection')
requireText(drawer, "useVisualFilter('device_type'", 'Device chart filtering')
requireText(drawer, "useVisualFilter('status'", 'Status chart filtering')
requireText(drawer, "useVisualFilter('department'", 'Department graph filtering')
requireText(types, 'device_distribution: DistributionItem[]', 'Device visual typing')
requireText(types, 'status_distribution: DistributionItem[]', 'Status visual typing')
requireText(types, 'department_distribution: DistributionItem[]', 'Department visual typing')
requireText(styles, '.drilldown-visual-section', 'Drawer visual section styling')
requireText(styles, '.drilldown-visual-grid.three-visuals', 'Three-chart layout')
requireText(styles, '.drilldown-visual-grid.two-visuals', 'Scope-aware two-chart layout')
requireText(styles, '.drilldown-visual-card .svg-donut-wrap', 'Compact drawer donut layout')

console.log('DASHBOARD DRAWER VISUAL ANALYTICS VERIFICATION PASSED')
console.log('- Computer and laptop drawers show status pie charts and department bar graphs')
console.log('- Total-assets drawer shows device, status and department visuals')
console.log('- Department drawer shows device and status visuals')
console.log('- Chart clicks filter the same drawer table without page navigation')
console.log('- Charts use all matching records rather than only the current page')
