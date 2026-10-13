import fs from 'node:fs'
import path from 'node:path'

const root = process.cwd()
const read = (relative) => fs.readFileSync(path.join(root, relative), 'utf8')
const exists = (relative) => fs.existsSync(path.join(root, relative))

function assert(condition, message) {
  if (!condition) throw new Error(`Assertion failed: ${message}`)
}

// ---------------------------------------------------------------------------
// 1. Route + role protection for the BD feedback page
// ---------------------------------------------------------------------------
const app = read('src/App.tsx')
assert(app.includes('path="/bd/feedback"'), 'the /bd/feedback route must exist')
const routeLine = app.split('\n').find((line) => line.includes('path="/bd/feedback"'))
assert(routeLine.includes("'bd'"), 'the feedback route must be reachable by BD')
assert(!routeLine.includes("'production'") && !routeLine.includes("'qc'"),
  'operational roles must not be routed to the BD feedback page')
assert(app.includes("path=\"/finance/billing\" element={<ProtectedRoute roles={['finance', 'admin', 'management']}"),
  'billing must stay Finance/Management/Admin only - BD must not raise invoices from feedback')

const feedbackPath = 'src/features/operations/pages/BDClientFeedbackPage.tsx'
const feedback = read(feedbackPath)

// ---------------------------------------------------------------------------
// 2. Deep link: exact project query param auto-selects that project
// ---------------------------------------------------------------------------
assert(feedback.includes("searchParams.get('project')"), 'the page must read the ?project= deep link')
assert(
  feedback.includes('requestedProjectId && data.projects.some(row => row.id === requestedProjectId)'),
  'the deep-linked project must be matched exactly against the BD project list',
)
assert(
  feedback.includes('setSelectedId(requested || data.projects[0].id)'),
  'the exact deep-linked project must auto-select (falling back only when absent)',
)
assert(
  feedback.includes("useSearchParams"),
  'the page must use react-router search params for the deep link',
)

const bell = read('src/components/GlobalNotificationBell.tsx')
assert(bell.includes('isSafeInternalPath(notification.target_url)'), 'the bell must follow the notification target_url')
assert(
  bell.includes("value.startsWith('/') && !value.startsWith('//')"),
  'deep links must be restricted to safe internal paths while still allowing ?query= params',
)
const lifecycleService = read('../backend/app/modules/operations/lifecycle_service.py')
assert(
  lifecycleService.includes('target_url=f"/bd/feedback?project={project.id}"'),
  'backend notifications must deep link to /bd/feedback?project=<exact id>',
)

// ---------------------------------------------------------------------------
// 3. Action Center visibility is driven by the legitimate feedback stage
// ---------------------------------------------------------------------------
assert(feedback.includes('Client Feedback Action Center'), 'the Action Center heading must render')
assert(feedback.includes('FEEDBACK_ACTION_STATUSES'), 'visibility must be driven by the feedback action statuses')
assert(feedback.includes('const inFeedbackStage = detail ? FEEDBACK_ACTION_STATUSES.includes(detail.workflow_status) : false'),
  'the Action Center must be gated on the workflow status')
assert(feedback.includes('{inFeedbackStage && <div className="operations-daily-card">'),
  'the Action Center must render only while the project is at the feedback stage')

// Required actions
assert(feedback.includes('Send Feedback Request'), 'the Send Feedback Request action must exist')
assert(feedback.includes('Client Accepted / Positive'), 'the offline Positive action must exist')
assert(feedback.includes('Negative Feedback'), 'the Negative Feedback action must exist')
assert(feedback.includes('No Feedback Received'), 'the No Feedback action must exist')

// ---------------------------------------------------------------------------
// 4. Buttons disappear once the project is Ready For Billing
// ---------------------------------------------------------------------------
assert(
  feedback.includes("'READY_FOR_BILLING'") && feedback.includes('FEEDBACK_END_STATUSES'),
  'READY_FOR_BILLING must be a terminal feedback status',
)
const actionStatusLine = feedback.split('\n').find((line) => line.includes('const FEEDBACK_ACTION_STATUSES'))
assert(actionStatusLine && !actionStatusLine.includes("'READY_FOR_BILLING'"),
  'decision buttons must be hidden once the project is Ready For Billing')
const endStatusLine = feedback.split('\n').find((line) => line.includes('const FEEDBACK_END_STATUSES'))
assert(endStatusLine.includes("'READY_FOR_BILLING'") && endStatusLine.includes("'CLIENT_ACCEPTED'"),
  'finished projects must show the completion note instead of the decision buttons')
assert(
  feedback.includes('The client feedback decision is complete for this project'),
  'a completion note must replace the Action Center after the decision',
)

// ---------------------------------------------------------------------------
// 5. Offline (manual) Positive and Negative recording with audit reference
// ---------------------------------------------------------------------------
assert(
  feedback.includes('/feedback-responses/manual'),
  'BD must be able to record an offline client outcome against the existing lifecycle API',
)
assert(feedback.includes('client_name') && feedback.includes('reference'),
  'offline acceptance/negative must capture the client contact and audit reference')
assert(feedback.includes('Confirm & Record'), 'the manual recording dialog must require confirmation')
assert(
  feedback.includes("recordManualFeedback(manualForm.open === 'accepted' ? 'accepted' : 'correction')"),
  'the offline Positive/Negative must reuse the existing accepted/correction response types',
)
assert(
  feedback.includes('Record Client Acceptance (offline)') && feedback.includes('Record Negative Client Feedback (offline)'),
  'both offline dialogs must be labelled',
)

// ---------------------------------------------------------------------------
// 6. Portal Positive still waits for BD confirmation before Finance handoff
// ---------------------------------------------------------------------------
assert(
  feedback.includes("classification_status === 'pending_bd'"),
  'a portal positive must land in a pending-BD-confirmation state',
)
assert(
  feedback.includes('BD confirmation is required before Finance receives the billing hand-off.'),
  'the portal positive card must state that BD confirmation gates Finance',
)
assert(
  feedback.includes('/confirm-acceptance'),
  'BD must confirm the portal acceptance through the existing confirm-acceptance endpoint',
)
assert(
  feedback.includes('Client Accepted – Send for Billing'),
  'the BD confirmation action must send the project to Finance as Ready For Billing',
)
assert(
  feedback.includes('response.source === \'bd_manual\''),
  'offline-recorded responses must be visually distinguished from portal responses',
)

// ---------------------------------------------------------------------------
// 7. Negative reuses the existing classification / rework / change request engine
// ---------------------------------------------------------------------------
assert(feedback.includes('Correction / rework'), 'the existing correction/rework classification must remain')
assert(feedback.includes('Additional scope / change request'), 'the existing change-request classification must remain')
assert(feedback.includes('/classification'), 'negative feedback must post to the existing classification endpoint')
assert(feedback.includes('/rework-cycles/') || feedback.includes('syncRework'),
  'rework cycles must reuse the existing rework engine - no second engine')
assert(feedback.includes('/change-requests/') || feedback.includes('decide('),
  'additional scope must reuse the existing change request workflow')
assert(feedback.includes('REWORK_DELIVERED'), 'a corrected delivery must surface a resubmit action for BD')

// ---------------------------------------------------------------------------
// 8. No Feedback requires Management authorization (never a silent BD bypass)
// ---------------------------------------------------------------------------
assert(
  feedback.includes('/no-feedback-recommendation'),
  'No Feedback must raise a recommendation to Management, not a direct closure',
)
assert(feedback.includes('noFeedbackReason'), 'the No Feedback action must be gated by eligibility')
assert(
  feedback.includes('reminder_count < 1'),
  'a reminder must be sent before a no-feedback recommendation is eligible',
)
assert(feedback.includes('canRemind'), 'the client must get the chance to respond before no-feedback closure')
const lifecycle = lifecycleService
assert(
  lifecycle.includes('Only Management or Admin can authorize deemed acceptance'),
  'deemed acceptance must remain Management/Admin authorized',
)
assert(lifecycle.includes('status=READY_FOR_BILLING') || lifecycle.includes('status=DEEMED_ACCEPTED'),
  'authorized deemed acceptance must continue to Ready For Billing')

const managementPage = read('src/features/operations/pages/ManagementProject360Page.tsx')
assert(managementPage.includes('/deemed-acceptance'), 'Management Project 360 must expose the deemed-acceptance authorisation')
assert(managementPage.includes('Management Authorization Required: Deemed Acceptance'),
  'Management must see the explicit authorisation panel')

// ---------------------------------------------------------------------------
// 9. BD must never raise an invoice directly from this page
// ---------------------------------------------------------------------------
assert(!feedback.includes('/raise-invoice') && !feedback.includes('/invoices'),
  'the BD feedback page must not call any invoice endpoint')
assert(!feedback.includes('READY_FOR_BILLING\' ,') && !feedback.includes("setWorkflowStatus('READY_FOR_BILLING')"),
  'BD must not force the Ready For Billing status directly')

// ---------------------------------------------------------------------------
// 10. No browser alert()/confirm() introduced by this feature
// ---------------------------------------------------------------------------
assert(!/\balert\(/.test(feedback), 'the BD feedback page must not use window.alert()')
assert(!/\bconfirm\(/.test(feedback), 'the BD feedback page must not use window.confirm()')

// ---------------------------------------------------------------------------
// 11. Supporting type/status contracts
// ---------------------------------------------------------------------------
const types = read('src/features/operations/lifecycle-types.ts')
for (const status of ['CLIENT_ACCEPTED', 'DEEMED_ACCEPTED', 'READY_FOR_BILLING', 'FEEDBACK_NEGATIVE', 'NO_FEEDBACK_CLOSURE_RECOMMENDED']) {
  assert(types.includes(`${status}:`), `lifecycle-types must label ${status}`)
}
const router = read('../backend/app/modules/operations/lifecycle_router.py')
for (const endpoint of ['feedback-responses/manual', 'confirm-acceptance', 'no-feedback-recommendation', 'deemed-acceptance']) {
  assert(router.includes(endpoint), `the lifecycle router must expose ${endpoint}`)
}
assert(
  lifecycle.includes('bd_owner_user_id != actor.id'),
  'manual feedback and recommendations must be restricted to the BD owner (or admin)',
)

console.log('BD CLIENT FEEDBACK ACTION CENTER / DEEP LINK / BAD DEBT SUPPORT VERIFICATION PASSED')
console.log('- /bd/feedback route is role protected and reads the exact ?project= deep link')
console.log('- Action Center renders only at the legitimate feedback stage with all four actions')
console.log('- Decision buttons are hidden once the project reaches Ready For Billing')
console.log('- Offline Positive and Negative reuse the existing response + classification engine')
console.log('- Portal Positive still requires BD confirmation before the Finance hand-off')
console.log('- No Feedback still requires Management deemed-acceptance authorisation')
console.log('- BD never raises an invoice and no browser alert()/confirm() is used')
