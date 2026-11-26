import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'

// Static structural guard only. It does not replace browser visual testing.
const root = process.cwd()
const read = file => fs.readFileSync(path.join(root, file), 'utf8')
const financePage = read('src/features/finance/pages/FinanceDashboardPage.tsx')
const financeCss = read('src/features/finance/finance-dashboard-v2.css')
const globalCss = read('src/styles.css')

// Finance approval queue: the Action column exists and is pinned, and the table card scrolls
// horizontally instead of clipping its right-hand columns.
assert.ok(financePage.includes('<th className="fin-action-col">Action</th>'), 'Finance queue must render an Action header column')
assert.ok(financePage.includes('className="fin-action-col"'), 'Finance Action cells must carry the pinned action class')
assert.ok(/\.fin-table-card\s*\{[^}]*overflow-x:\s*auto/.test(financeCss), 'fin-table-card must scroll horizontally, not clip')
assert.ok(!/\.fin-table-card\s*\{[^}]*overflow:\s*hidden/.test(financeCss), 'fin-table-card must not use overflow:hidden')
assert.ok(/\.fin-action-col\s*\{[^}]*position:\s*sticky[^}]*right:\s*0/.test(financeCss), 'Action column must be sticky on the right')
assert.ok(/\.fin-action-col\s*\{[^}]*background:\s*#ffffff/.test(financeCss), 'sticky Action cells need a solid background')
assert.ok(/\.fin-table\s*\{[^}]*min-width:\s*\d+px/.test(financeCss), 'fin-table needs a usable minimum width')

// Shared IT/ticket/asset panels must not clip tables or action rows.
for (const selector of ['ticket-list-panel', 'asset-table-panel', 'software-security-panel']) {
  const rule = new RegExp(`\\.${selector}\\s*\\{[^}]*\\}`).exec(globalCss)
  assert.ok(rule, `${selector} rule must exist`)
  assert.ok(!/overflow:\s*hidden/.test(rule[0]), `${selector} must not clip with overflow:hidden`)
  assert.ok(/overflow-x:\s*auto/.test(rule[0]), `${selector} must scroll horizontally when needed`)
}

// Ticket list keeps its Raise Ticket action and wraps its toolbar at narrow widths.
const ticketPage = read('src/features/employee_portal/pages/TicketListPage.tsx')
assert.ok(ticketPage.includes('Raise Ticket'), 'Raise Ticket action must exist on the ticket list')
assert.ok(/\.ticket-list-toolbar\s*\{[^}]*flex-wrap:\s*wrap/.test(globalCss), 'ticket toolbar must wrap so actions stay reachable')
assert.ok(/\.table-wrap\s*\{[^}]*overflow-x:\s*auto/.test(globalCss), 'table wrappers must scroll horizontally')

// Layout shell: the content column must be allowed to shrink (no 100vw inside the sidebar grid).
assert.ok(/\.app-shell\s*\{[^}]*grid-template-columns:\s*278px\s+minmax\(0,\s*1fr\)/.test(globalCss), 'app shell content column must be minmax(0,1fr)')

console.log('CRITICAL ACTION VISIBILITY STRUCTURAL VERIFICATION PASSED')
console.log('- Finance queue: Action column exists, is sticky-right, and the table card scrolls horizontally')
console.log('- Shared IT/ticket/asset panels scroll horizontally instead of clipping')
console.log('- Ticket toolbar wraps and keeps Raise Ticket reachable')
console.log('- App shell content column uses minmax(0,1fr) so it never overflows the sidebar layout')
console.log('- Static source check only: browser visual UAT is still required')
