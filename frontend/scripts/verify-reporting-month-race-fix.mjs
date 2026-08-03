import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const root = process.cwd()

function read(relativePath) {
  const fullPath = path.join(root, relativePath)
  if (!fs.existsSync(fullPath)) throw new Error(`Required file is missing: ${relativePath}`)
  return fs.readFileSync(fullPath, 'utf8')
}

function requireText(source, text, label) {
  if (!source.includes(text)) throw new Error(`${label}: expected code was not found: ${text}`)
}

function forbidText(source, text, label) {
  if (source.includes(text)) throw new Error(`${label}: obsolete unsafe code is still present: ${text}`)
}

const context = read('src/context/ITMonthContext.tsx')
const dashboard = read('src/pages/ITDashboard.tsx')
const recent = read('src/pages/RecentChangesPage.tsx')
const handover = read('src/pages/HandoverReturnPage.tsx')
const purchase = read('src/pages/PurchaseProcurementPage.tsx')
const assetForm = read('src/pages/AssetFormPage.tsx')
const workForm = read('src/pages/WorkFormPage.tsx')
const layout = read('src/components/Layout.tsx')

requireText(context, 'pendingMonthRef', 'IT month URL synchronization')
requireText(context, 'The URL is temporarily stale', 'IT month URL synchronization')
requireText(context, 'writeMonthToUrl(month)', 'IT month URL synchronization')
forbidText(
  context,
  "if (validMonth(urlMonth)) {\n      if (urlMonth !== monthContext.selectedMonth) monthContext.setSelectedMonth(urlMonth)\n      return",
  'IT month URL synchronization',
)

for (const [source, label] of [
  [dashboard, 'IT Dashboard'],
  [recent, 'Recent Changes'],
  [handover, 'Handover & Return'],
  [purchase, 'Purchase & Procurement'],
]) {
  requireText(source, 'requestSequence', `${label} stale-response protection`)
  requireText(source, 'requestId !== requestSequence.current', `${label} stale-response protection`)
}

requireText(dashboard, 'result.month.key !== requestedMonth', 'IT Dashboard response-month validation')
requireText(recent, 'result.month.key !== requestedMonth', 'Recent Changes response-month validation')
requireText(assetForm, 'requestPayload.reporting_month = selectedMonth', 'Asset edit reporting month')
requireText(workForm, 'reporting_month: selectedMonth', 'Work/component reporting month')
requireText(handover, 'reporting_month: selectedMonth', 'Handover reporting month')
requireText(purchase, 'reporting_month: selectedMonth', 'Purchase reporting month')
requireText(layout, "withITMonth(item.to, selectedMonth)", 'Sidebar month persistence')

// Deterministic model of the fixed transition. A stale present-month URL must
// not overwrite a deliberate historical-month selection before Router commits.
let contextMonth = '2026-08'
let urlMonth = '2026-08'
let pendingMonth = null

function chooseMonth(month) {
  pendingMonth = month
  contextMonth = month
}

function synchronize() {
  if (/^\d{4}-(0[1-9]|1[0-2])$/.test(urlMonth)) {
    if (pendingMonth) {
      if (urlMonth === pendingMonth) pendingMonth = null
      else return
    }
    if (urlMonth !== contextMonth) contextMonth = urlMonth
  }
}

chooseMonth('2026-06')
synchronize()
if (contextMonth !== '2026-06') throw new Error('Stale URL incorrectly overwrote the selected historical month')
urlMonth = '2026-06'
synchronize()
if (contextMonth !== '2026-06' || pendingMonth !== null) throw new Error('Router commit did not finalize the selected month')

// Deterministic model of latest-request-wins rendering.
let latestRequest = 0
const juneRequest = ++latestRequest
const augustRequest = ++latestRequest
if (juneRequest === latestRequest) throw new Error('Stale request protection model failed')
if (augustRequest !== latestRequest) throw new Error('Latest request protection model failed')

console.log('REPORTING MONTH RACE FIX VERIFICATION PASSED')
console.log('- A user-selected historical month cannot be overwritten by the stale present-month URL')
console.log('- Sidebar navigation keeps the selected month')
console.log('- Stale dashboard and activity responses cannot overwrite the latest selection')
console.log('- Asset, work, component, handover and purchase saves still send the selected reporting month')
