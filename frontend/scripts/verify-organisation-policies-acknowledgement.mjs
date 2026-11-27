import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'

// Static structural guard for Organisation Policies acknowledgement persistence
// and status synchronisation. It does not replace browser or API testing.
const root = process.cwd()
const read = file =>
  fs.readFileSync(path.join(root, file), 'utf8').replace(/\r\n/g, '\n')

const page = read('src/features/organisation_policies/OrganisationPoliciesPage.tsx')
const css = read('src/features/organisation_policies/organisation-policies.css')
const backend = read('../backend/app/modules/organisation_policies/router.py')

// ---------------------------------------------------------------
// 1. The database stays the single source of truth.
// ---------------------------------------------------------------
assert.ok(
  /acknowledged_at:\s*string\s*\|\s*null/.test(page),
  'Policy payload must carry acknowledged_at from the backend',
)
assert.ok(
  !page.includes('localStorage'),
  'Acknowledgement state must never be cached in localStorage',
)
assert.ok(
  !page.includes('sessionStorage'),
  'Acknowledgement state must never be cached in sessionStorage',
)
assert.ok(
  !/acknowledgedIds|acknowledgedSet|isAcknowledgedLocal/.test(page),
  'No client-side acknowledgement set may shadow the database status',
)

// ---------------------------------------------------------------
// 2. Pending / Acknowledged status, filter counts and progress are all
//    derived from the server-supplied acknowledged_at value.
// ---------------------------------------------------------------
assert.ok(
  page.includes("filter === 'pending' && policy.acknowledged_at"),
  'Pending filter must hide policies the database already records as acknowledged',
)
assert.ok(
  page.includes("filter === 'acknowledged' && !policy.acknowledged_at"),
  'Acknowledged filter must show only database-acknowledged policies',
)
assert.ok(
  page.includes('published.filter(p => p.acknowledged_at)'),
  'Acknowledged count must be derived from acknowledged_at',
)
assert.ok(
  /policy\.acknowledged_at\s*\?\s*'Acknowledged'/.test(page),
  'Policy list status must be driven by acknowledged_at',
)

// ---------------------------------------------------------------
// 3. A successful submission reloads the library and refreshes the
//    remaining acknowledgement views (filter counts, history, compliance).
// ---------------------------------------------------------------
const performBlock = /async function perform\([\s\S]*?\n  \}/.exec(page)
assert.ok(performBlock, 'perform() helper must exist')
assert.ok(
  performBlock[0].includes('await reload()'),
  'Every completed action must reload the policy library from the backend',
)

const acknowledgeBlock = /async function acknowledge\(\) \{[\s\S]*?\n  \}/.exec(page)
assert.ok(acknowledgeBlock, 'acknowledge() must exist')
assert.ok(
  acknowledgeBlock[0].includes('await perform('),
  'acknowledge() must go through perform() so the library reloads',
)
assert.ok(
  acknowledgeBlock[0].includes('refreshAcknowledgementData()'),
  'acknowledge() must refresh history/compliance views after recording',
)
assert.ok(
  acknowledgeBlock[0].includes('selected.acknowledged_at'),
  'acknowledge() must refuse to resubmit an acknowledgement already stored',
)

const refreshBlock = /const refreshAcknowledgementData = useCallback[\s\S]*?\}, \[isHR\]\)/.exec(page)
assert.ok(refreshBlock, 'refreshAcknowledgementData must exist')
assert.ok(
  refreshBlock[0].includes('/compliance'),
  'HR compliance rows must be refreshed after an acknowledgement write',
)
assert.ok(
  refreshBlock[0].includes('/my-acknowledgements'),
  'Employee acknowledgement history must be refreshed after a write',
)

// ---------------------------------------------------------------
// 4. The acknowledgement checkbox and submit button are replaced by an
//    "Acknowledged Successfully" status with the acknowledgement date
//    and time as soon as the database reports the record.
// ---------------------------------------------------------------
assert.ok(
  page.includes('Acknowledged Successfully'),
  'The acknowledged panel must show an Acknowledged Successfully status',
)
assert.ok(
  page.includes('<strong>Acknowledged on:</strong>'),
  'The acknowledged panel must show the acknowledgement date and time',
)
assert.ok(
  page.includes('formatDate(selected.acknowledged_at)'),
  'The acknowledgement timestamp must be rendered from acknowledged_at',
)
assert.ok(
  /selected\.acknowledged_at \? \(/.test(page),
  'The panel must switch on acknowledged_at returned by the backend',
)
assert.ok(
  /className="op-ack-status"/.test(page),
  'The Acknowledged Successfully status must be visibly styled',
)

// The checkbox + submit button only exist inside the not-yet-acknowledged
// branch of that ternary.
const panelStart = page.indexOf('className="op-ack-panel"')
assert.ok(panelStart > -1, 'The acknowledgement panel must exist')
const acknowledgedBranch = page.slice(
  panelStart,
  page.indexOf(') : (', panelStart),
)
assert.ok(
  !acknowledgedBranch.includes('type="checkbox"'),
  'An acknowledged policy must not render the acknowledgement checkbox',
)
assert.ok(
  !acknowledgedBranch.includes('Submit Acknowledgement'),
  'An acknowledged policy must not render the submit button',
)
const pendingBranch = page.slice(
  page.indexOf(') : (', panelStart),
  page.indexOf('</section>', panelStart),
)
assert.ok(
  pendingBranch.includes('type="checkbox"'),
  'A pending policy must still offer the acknowledgement checkbox',
)
assert.ok(
  pendingBranch.includes('Submit Acknowledgement'),
  'A pending policy must still offer the submit button',
)

// ---------------------------------------------------------------
// 5. The backend stores one acknowledgement per (employee, version) and
//    reports it for every employee role the module serves.
// ---------------------------------------------------------------
assert.ok(
  backend.includes(
    'user_id: Mapped[int] = mapped_column(\n        ForeignKey("users.id"), primary_key=True\n    )',
  ),
  'Acknowledgement user_id must stay part of the composite primary key',
)
assert.ok(
  backend.includes('version_id: Mapped[int] = mapped_column(\n        ForeignKey("organisation_policy_versions.id"),\n        primary_key=True,\n    )',
  ),
  'Acknowledgement version_id must stay part of the composite primary key',
)
assert.ok(
  backend.includes('if user.role in EMPLOYEE_ROLES:\n        if policy.archived_at is not None or current is None:'),
  'Acknowledgement status must be reported for every employee role',
)
assert.ok(
  backend.includes('if user.role in EMPLOYEE_ROLES:\n        query = query.where('),
  'Employee policy listing must apply to every employee role',
)
assert.ok(
  backend.includes('db.get(Ack, (user.id, current.id))'),
  'The acknowledgement must be looked up by authenticated user and version',
)
assert.ok(
  backend.includes('except IntegrityError:'),
  'Repeated submissions must stay idempotent under concurrent writes',
)
assert.ok(
  backend.includes('current.id != payload.version_id'),
  'A stale or foreign policy version id must be rejected',
)
assert.ok(
  backend.includes('recipient_roles=list(EMPLOYEE_ROLES)'),
  'Publication notices must reach every employee role',
)
assert.ok(
  backend.includes('def run_policy_reminders():'),
  'Reminder generation must keep checking stored acknowledgements',
)

// ---------------------------------------------------------------
// 6. The status pill is styled.
// ---------------------------------------------------------------
assert.ok(
  /\.op-ack-status\s*\{[^}]*\}/.test(css),
  'op-ack-status style must exist',
)

console.log('ORGANISATION POLICIES ACKNOWLEDGEMENT VERIFICATION PASSED')
console.log('- Acknowledgement status is read from the database for every employee role')
console.log('- Pending / Acknowledged filters, counts and progress derive from acknowledged_at')
console.log('- Submission reloads the library and refreshes history/compliance views')
console.log('- Acknowledged policies render "Acknowledged Successfully" with date and time')
console.log('- One composite-key row per (employee, version); repeats stay idempotent')
console.log('- Stale version ids rejected; publication notices reach every employee role')
console.log('- Static source check only: browser and API testing are still required')
