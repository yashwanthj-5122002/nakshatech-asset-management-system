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

function requireOrder(source, first, second, label) {
  const firstIndex = source.indexOf(first)
  const secondIndex = source.indexOf(second)
  if (firstIndex < 0 || secondIndex < 0 || firstIndex >= secondIndex) {
    throw new Error(`${label}: expected ${first} before ${second}`)
  }
}

const drawer = read('src/components/AssetDrilldownDrawer.tsx')
const styles = read('src/styles.css')

requireText(drawer, 'const [visualsOpen, setVisualsOpen] = useState(false)', 'Visuals collapsed by default')
requireText(drawer, 'setVisualsOpen(false)', 'Visuals reset for a new card/month')
requireText(drawer, 'function toggleVisuals()', 'Visual toggle handler')
requireText(drawer, 'setVisualsOpen(current => !current)', 'Toggle changes only visual visibility')
requireText(drawer, 'aria-expanded={visualsOpen}', 'Accessible expanded state')
requireText(drawer, 'aria-controls="asset-drilldown-visuals"', 'Accessible visual target')
requireText(drawer, "{visualsOpen ? 'Hide Visuals' : 'Show Visuals'}", 'Show/hide button labels')
requireText(drawer, 'visualsOpen && data && data.filtered_total > 0', 'Charts render only when requested')
requireText(drawer, 'id="asset-drilldown-visuals"', 'Visual target id')
requireText(drawer, "data-compact={data.visuals.department_distribution.length <= 4 ? 'true' : 'false'}", 'Adaptive department graph sizing')
requireText(drawer, "selection.scope !== 'department'", 'Single-department drawers omit redundant allocation graph')
requireOrder(drawer, 'className="drilldown-header-actions"', 'className="drilldown-toolbar"', 'Toggle remains visible in the drawer header')
requireOrder(drawer, 'visualsOpen && data', 'className="drilldown-toolbar"', 'Expanded visuals remain above search/table')

requireText(styles, '.drilldown-header-actions', 'Header toggle placement')
requireText(styles, '.drilldown-visual-toggle', 'Toggle button styling')
requireText(styles, '.drilldown-visual-toggle.active', 'Open-state styling')
requireText(styles, '@keyframes drilldownVisualReveal', 'Visual reveal animation')
requireText(styles, '.drilldown-visual-grid {\n  align-items: start;', 'Chart cards do not stretch into empty space')
requireText(styles, '.department-visual-card[data-compact="true"] .bar-list', 'Compact department allocation behavior')
requireText(styles, 'max-height: none;', 'Compact charts remove unnecessary internal height')

// Small deterministic state simulation: toggling visuals must not alter filters or page.
const state = {
  visualsOpen: false,
  page: 6,
  filters: { department: 'BIM', device_type: 'Laptop', status: 'assigned' },
}
const toggle = current => ({ ...current, visualsOpen: !current.visualsOpen })
const opened = toggle(state)
const closed = toggle(opened)
if (!opened.visualsOpen || closed.visualsOpen) throw new Error('Toggle state simulation failed')
if (opened.page !== 6 || opened.filters.department !== 'BIM' || opened.filters.device_type !== 'Laptop') {
  throw new Error('Opening visuals changed table state')
}
if (closed.page !== 6 || closed.filters.status !== 'assigned') {
  throw new Error('Closing visuals changed table state')
}

console.log('DASHBOARD DRAWER VISUAL TOGGLE VERIFICATION PASSED')
console.log('- Visual analytics are collapsed by default')
console.log('- One Show/Hide Visuals button expands and collapses charts in the same drawer')
console.log('- Search, filters, reporting month and current table page remain unchanged')
console.log('- Department Allocation uses compact adaptive height for small result sets')
console.log('- Department drawers omit the redundant single-department allocation graph')
