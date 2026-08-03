import fs from 'node:fs'
import path from 'node:path'

const root = process.cwd()
const read = relative => fs.readFileSync(path.join(root, relative), 'utf8')
const styles = read('src/styles.css')
const drawer = read('src/components/AssetDrilldownDrawer.tsx')

function requireText(source, text, label) {
  if (!source.includes(text)) throw new Error(`${label} is missing: ${text}`)
}

function forbidText(source, text, label) {
  if (source.includes(text)) throw new Error(`${label} is still present: ${text}`)
}

requireText(drawer, 'className="drilldown-header"', 'Drawer header')
requireText(drawer, "className={`drilldown-visual-toggle", 'Show/Hide Visuals button')
requireText(drawer, "aria-controls=\"asset-drilldown-visuals\"", 'Visual toggle accessibility target')
requireText(drawer, 'className="drilldown-search"', 'Drawer search shell')

requireText(styles, '--naksha-topbar-height: 64px;', 'Desktop topbar height variable')
requireText(styles, 'margin-top: var(--naksha-topbar-height);', 'Drawer topbar offset')
requireText(styles, 'height: calc(100dvh - var(--naksha-topbar-height));', 'Drawer viewport height calculation')
requireText(styles, '.drilldown-header > div:first-child', 'Header text width protection')
requireText(styles, '.drilldown-header-actions', 'Header action alignment')
requireText(styles, 'grid-template-columns: minmax(0, 1fr) auto;', 'Toolbar alignment')
requireText(styles, '.drilldown-table-shell {\n  min-height: 0;', 'Flexible table height')

requireText(styles, '.app-shell input:focus-visible,', 'Native focus reset')
requireText(styles, 'outline-offset: 0;', 'Duplicate native outline removal')
requireText(styles, '.search-shell:focus-within,', 'Composite search focus shell')
requireText(styles, '.drilldown-search:focus-within', 'Drawer search outer focus ring')
requireText(styles, '.drilldown-search > input:focus-visible', 'Drawer search inner-ring removal')
requireText(styles, 'box-shadow: none !important;', 'Inner focus shadow removal')
requireText(styles, '@media (max-width: 900px)', 'Tablet alignment handling')
requireText(styles, '--naksha-topbar-height: 60px;', 'Tablet topbar offset')
requireText(styles, '--naksha-topbar-height: 58px;', 'Mobile topbar offset')

forbidText(styles, '.asset-drilldown-drawer {\n  top: 0;', 'Unsafe drawer top positioning')

console.log('DASHBOARD DRAWER LAYOUT AND FOCUS VERIFICATION PASSED')
console.log('- Drawer title and Show/Hide Visuals button remain below the global header')
console.log('- Drawer sections and controls keep consistent alignment')
console.log('- Search fields use one outer focus ring instead of nested blue boxes')
console.log('- Desktop, tablet and mobile header offsets are covered')
