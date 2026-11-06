
import { Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { apiFetch } from '../../../lib/api'

// Shared physical-file workflow controls.
// Used by Project Operations and Production Tracking.
// Production actual quantity is displayed read-only.
// The backend must independently enforce the locked value.

export const DELAY_CATEGORIES = [
  'Normal Work',
  'Large / Complex Building Data',
  'Heavy File / High Data Volume',
  'Poor Input Data Quality',
  'Rework / Correction',
  'System Malfunction',
  'Software Performance Issue',
  'Network / Server Issue',
  'Waiting for Required Data',
  'Other',
]

export const DEADLINE_LABELS: Record<string, string> = {
  on_track: 'On Track',
  due_today: 'Due Today',
  buffer_day: 'Buffer Day',
  overdue: 'Overdue',
  not_due: 'Not Due',
  completed_on_time: 'Completed On Time',
  completed_in_buffer: 'Completed In Buffer',
  completed_late: 'Completed Late',
  delivered: 'Delivered',
  no_target: 'No Target',
}

export type StageDeadline = {
  status?: string | null
  target_date?: string | null
  buffer_until?: string | null
  days_overdue?: number
  days_late?: number
}

export type ActivityItem = {
  work_package_item_id: number
  item_number: string
  item_name?: string | null
  planned_quantity?: number | null
  planned_unit?: string | null
  is_active?: boolean
  status?: string

  production_user_id?: number | null
  qc_user_id?: number | null
  qa_user_id?: number | null

  production_user?: string | null
  qc_user?: string | null
  qa_user?: string | null

  production_status: string
  production_rework_pending?: boolean
  production_rework_source?: string | null
  production_rework_reason?: string | null

  qc_status: string
  qa_status: string
  delivery_status?: string

  production_start?: string | null
  production_end?: string | null
  production_completed_at?: string | null
  production_sessions?: number
  production_duration_seconds?: number | null

  qc_start?: string | null
  qc_end?: string | null
  qc_duration_seconds?: number | null
  qc_attempts?: number

  qa_start?: string | null
  qa_end?: string | null
  qa_duration_seconds?: number | null
  qa_attempts?: number

  production_quantity?: number | null
  production_unit?: string | null
  production_files?: number

  production_attempt_type?: string | null
  production_attempt_number?: number | null
  qc_attempt_type?: string | null
  qa_attempt_type?: string | null

  production_remarks?: string | null
  qc_remarks?: string | null
  qa_remarks?: string | null

  delay_category?: string | null
  delay_reason?: string | null
  delay_remarks?: string | null
  system_malfunction?: boolean
  affected_item_number?: string | null

  production_target_date?: string | null
  qc_target_date?: string | null
  qa_target_date?: string | null
  supply_date?: string | null

  production_deadline?: StageDeadline | null
  qc_deadline?: StageDeadline | null
  qa_deadline?: StageDeadline | null

  ready_for_delivery?: boolean

  open_session?: {
    activity_id: number
    stage: string
    employee_user_id: number
    started_at?: string | null
  } | null

  // Server-calculated values.
  // Return quantity as a decimal string to avoid UI rounding.
  locked_actual_quantity?: string | null
  locked_actual_unit?: string | null
}

export function fmtQty(
  value: number | null | undefined,
): string {
  if (value === null || value === undefined) return '—'
  return String(value)
}

export function fmtDate(
  value?: string | null,
): string {
  if (!value) return '—'
  if (value.length <= 10) return value

  const ms = parseTimestamp(value)
  if (ms === null) return value.slice(0, 10)

  const d = new Date(ms)
  const pad = (n: number) => String(n).padStart(2, '0')

  return (
    `${d.getFullYear()}-` +
    `${pad(d.getMonth() + 1)}-` +
    `${pad(d.getDate())}`
  )
}

export function parseTimestamp(
  value: string,
): number | null {
  const ms = Date.parse(
    /[zZ]|[+-]\d{2}:\d{2}$/.test(value)
      ? value
      : `${value}Z`,
  )

  return Number.isNaN(ms) ? null : ms
}

export function fmtTime(
  value?: string | null,
): string {
  if (!value) return '—'

  const ms = parseTimestamp(value)

  if (ms === null) {
    return value.length >= 11
      ? value.slice(11, 19)
      : value
  }

  const d = new Date(ms)
  const pad = (n: number) => String(n).padStart(2, '0')

  return (
    `${pad(d.getHours())}:` +
    `${pad(d.getMinutes())}:` +
    `${pad(d.getSeconds())}`
  )
}

export function fmtDuration(
  seconds?: number | null,
): string {
  if (seconds === null || seconds === undefined) {
    return '—'
  }

  const total = Math.max(0, Math.floor(seconds))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60

  return (
    `${String(hours).padStart(2, '0')}:` +
    `${String(minutes).padStart(2, '0')}:` +
    `${String(secs).padStart(2, '0')}`
  )
}

export function label(value: string): string {
  return value
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

export function stageLabel(stage: string): string {
  return (
    {
      production: 'Production',
      qc: 'QC',
      qa: 'QA',
    }[stage] ?? label(stage)
  )
}

export function stageStatusTone(
  stageOrStatus: string | null | undefined,
  status?: string | null,
): string {
  const value =
    status === undefined ? stageOrStatus : status

  if (!value) return ''
  if (value === 'in_progress') return 'warning'

  if (
    ['completed', 'passed', 'approved', 'delivered']
      .includes(value)
  ) {
    return 'success'
  }

  if (/reject|rework|blocked/.test(value)) {
    return 'danger'
  }

  if (/pending|not_started/.test(value)) {
    return 'warning'
  }

  return ''
}

function stageDeadlineLabel(
  deadline?: StageDeadline | null,
): string | null {
  if (
    !deadline ||
    !deadline.status ||
    deadline.status === 'no_target'
  ) {
    return null
  }

  return (
    DEADLINE_LABELS[deadline.status] ??
    label(deadline.status)
  )
}

// This helper is only for displaying existing progress.
// The authoritative quantity calculation stays on the server.
function convertToPlannedUnit(
  quantity: number | null,
  fromUnit: string,
  toUnit: string,
): number | null {
  if (quantity === null) return null

  const from = fromUnit.trim().toLowerCase()
  const to = toUnit.trim().toLowerCase()

  if (from === to) return quantity

  const lengthScale: Record<string, number> = {
    m: 1,
    meter: 1,
    meters: 1,
    metre: 1,
    metres: 1,
    km: 1000,
    kilometer: 1000,
    kilometers: 1000,
    kilometre: 1000,
    kilometres: 1000,
    cm: 0.01,
    mm: 0.001,
  }

  const fromScale = lengthScale[from]
  const toScale = lengthScale[to]

  if (
    fromScale === undefined ||
    toScale === undefined
  ) {
    return null
  }

  return (quantity * fromScale) / toScale
}

const EMPTY_PRODUCTION_DRAFT = {
  delayCategory: '',
  delayReason: '',
  systemMalfunction: false,
}

const EMPTY_REVIEW_DRAFT = {
  status: 'passed',
  remarks: '',
}

export function ItemStageActivityControls({
  item,
  myUserId,
  canDeliver = false,
  onChanged,
  compact = false,
  showReviewActions = true,
}: {
  item: ActivityItem
  myUserId: number
  canDeliver?: boolean
  siblings?: {
    work_package_item_id: number
    item_number: string
  }[]
  onChanged: () => void
  compact?: boolean
  showReviewActions?: boolean
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const [active, setActive] = useState<
    'production' | 'qc' | 'qa' | null
  >(null)

  const [prodDraft, setProdDraft] = useState(
    EMPTY_PRODUCTION_DRAFT,
  )

  const [reviewDraft, setReviewDraft] = useState(
    EMPTY_REVIEW_DRAFT,
  )

  const [now, setNow] = useState(() => Date.now())

  const isActive = item.is_active !== false

  const myOpen =
    item.open_session &&
    item.open_session.employee_user_id === myUserId
      ? item.open_session
      : null

  const openStage = (
    myOpen?.stage ?? null
  ) as 'production' | 'qc' | 'qa' | null

  const openStartedAt = myOpen?.started_at ?? null

  const lockedQuantity =
    item.locked_actual_quantity ?? null

  const lockedUnit =
    item.locked_actual_unit ?? null

  const lockedActualAvailable =
    lockedQuantity !== null &&
    lockedQuantity.trim() !== '' &&
    lockedUnit !== null &&
    lockedUnit.trim() !== ''

  useEffect(() => {
    if (!openStage) return

    const timer = window.setInterval(
      () => setNow(Date.now()),
      5000,
    )

    return () => window.clearInterval(timer)
  }, [openStage])

  async function run(
    action: () => Promise<unknown>,
    success: string,
  ): Promise<boolean> {
    setBusy(true)
    setError('')
    setNotice('')

    try {
      await action()
      setNotice(success)
      onChanged()
      return true
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : 'Action failed',
      )
      return false
    } finally {
      setBusy(false)
    }
  }

  async function start(
    stage: 'production' | 'qc' | 'qa',
  ) {
    const saved = await run(
      () =>
        apiFetch(
          `/operations/workflow/ortho/items/${item.work_package_item_id}/activity/start`,
          {
            method: 'POST',
            body: JSON.stringify({ stage }),
          },
        ),
      `${stageLabel(stage)} started for ${item.item_number} — the server recorded the start time.`,
    )

    if (saved) {
      setActive(null)
    }
  }

  async function submitProduction(
    finalize: boolean,
  ) {
    if (!lockedActualAvailable) {
      setError(
        'Locked actual quantity is unavailable. ' +
        'The server must provide the planned-source ' +
        'quantity before this file can be completed.',
      )
      return
    }

    if (
      prodDraft.delayCategory &&
      prodDraft.delayCategory !== 'Normal Work' &&
      !prodDraft.delayReason.trim()
    ) {
      setError(
        'Describe the delay / difficulty reason.',
      )
      return
    }

    if (!myOpen) return

    const saved = await run(
      () =>
        apiFetch(
          `/operations/workflow/ortho/activities/${myOpen.activity_id}/stop`,
          {
            method: 'POST',
            body: JSON.stringify({
              status: 'completed',
              finalize,

              // Preserve the decimal text. No JS rounding.
              // Backend MUST rederive and validate this value.
              quantity_completed: lockedQuantity,
              unit: lockedUnit,

              // Removed completion-form fields.
              remarks: null,
              affected_item_id: null,
              delay_remarks: null,

              // Existing optional delay fields retained.
              delay_category:
                prodDraft.delayCategory || null,
              delay_reason:
                prodDraft.delayReason.trim() || null,
              system_malfunction:
                prodDraft.systemMalfunction ||
                prodDraft.delayCategory ===
                  'System Malfunction',
            }),
          },
        ),
      item.production_rework_pending
        ? `${item.item_number}: Production rework completed. The corrected file is ready for QC/QA review.`
        : `${item.item_number}: production COMPLETED — QC now ready.`,
    )

    if (saved) {
      setProdDraft(EMPTY_PRODUCTION_DRAFT)
      setActive(null)
    }
  }

  async function completeReview(
    stage: 'qc' | 'qa',
  ) {
    if (
      reviewDraft.status !== 'passed' &&
      !reviewDraft.remarks.trim()
    ) {
      setError(
        `${stage.toUpperCase()} reject/rework requires comments.`,
      )
      return
    }

    if (!myOpen) return

    const saved = await run(
      () =>
        apiFetch(
          `/operations/workflow/ortho/activities/${myOpen.activity_id}/stop`,
          {
            method: 'POST',
            body: JSON.stringify({
              status: reviewDraft.status,
              remarks:
                reviewDraft.remarks.trim() || null,
            }),
          },
        ),
      `${item.item_number}: ${stage.toUpperCase()} recorded (${reviewDraft.status}).`,
    )

    if (saved) {
      setReviewDraft(EMPTY_REVIEW_DRAFT)
      setActive(null)
    }
  }

  async function deliver() {
    const remarks = window.prompt(
      'Delivery remarks / reference (optional):',
      '',
    )

    if (remarks === null) return

    await run(
      () =>
        apiFetch(
          `/operations/workflow/ortho/items/${item.work_package_item_id}/delivery`,
          {
            method: 'POST',
            body: JSON.stringify({
              remarks: remarks || null,
              reference: null,
            }),
          },
        ),
      `${item.item_number}: delivered.`,
    )
  }

  const isProductionRework =
    item.production_rework_pending === true

  const canStartProduction =
    isActive &&
    !item.open_session &&
    item.production_user_id === myUserId &&
    (
      item.production_status !== 'completed' ||
      isProductionRework
    )

  const canStartQc =
    isActive &&
    !item.open_session &&
    item.qc_user_id === myUserId &&
    item.production_status === 'completed' &&
    item.qc_status !== 'passed'

  const canStartQa =
    isActive &&
    !item.open_session &&
    item.qa_user_id === myUserId &&
    item.qc_status === 'passed' &&
    item.qa_status !== 'passed'

  const plannedQty = item.planned_quantity ?? null
  const cumulativeQty =
    item.production_quantity ?? null

  const plannedUnit = item.planned_unit || ''
  const cumulativeUnit =
    item.production_unit || plannedUnit

  const cumulativeInPlannedUnit =
    convertToPlannedUnit(
      cumulativeQty,
      cumulativeUnit,
      plannedUnit,
    )

  const remainingQty =
    plannedQty !== null &&
    cumulativeInPlannedUnit !== null
      ? plannedQty - cumulativeInPlannedUnit
      : null

  const progressPct =
    plannedQty !== null &&
    plannedQty > 0 &&
    cumulativeInPlannedUnit !== null
      ? Math.round(
          (cumulativeInPlannedUnit / plannedQty) *
            10000,
        ) / 100
      : null

  const sessionCount =
    item.production_sessions ?? 0

  const stageRow = (
    stage: 'production' | 'qc' | 'qa',
    status: string,
    startedAt?: string | null,
    endedAt?: string | null,
    duration?: number | null,
    deadline?: StageDeadline | null,
    target?: string | null,
    attemptType?: string | null,
    attemptNumber?: number | null,
  ) => (
    <div className="isa-stage" key={stage}>
      <span className="isa-stage-name">
        {stageLabel(stage)}
      </span>

      <span
        className={
          `operations-status ${stageStatusTone(status)}`
        }
      >
        {label(status)}
      </span>

      {attemptType === 'REWORK' && (
        <span className="operations-status warning">
          REWORK
          {attemptNumber
            ? ` attempt ${attemptNumber}`
            : ''}
        </span>
      )}

      {target && (
        <span className="isa-meta">
          Target: {target}
        </span>
      )}

      {stageDeadlineLabel(deadline) && (
        <span className="isa-meta">
          {stageDeadlineLabel(deadline)}
        </span>
      )}

      {startedAt && (
        <span className="isa-meta">
          Started: {fmtTime(startedAt)}
        </span>
      )}

      {endedAt && (
        <span className="isa-meta">
          Completed: {fmtTime(endedAt)}
        </span>
      )}

      {duration !== null &&
        duration !== undefined && (
          <span className="isa-meta">
            Duration: {fmtDuration(duration)}
          </span>
        )}
    </div>
  )

  return (
    <div
      className={
        `isa-controls ${compact ? 'isa-compact' : ''}`
      }
    >
      {notice && (
        <div className="operations-alert success">
          {notice}
        </div>
      )}

      {error && (
        <div className="operations-alert error">
          {error}
        </div>
      )}

      {stageRow(
        'production',
        item.production_status,
        item.production_start,
        item.production_end,
        item.production_duration_seconds,
        item.production_deadline,
        item.production_target_date,
        item.production_attempt_type,
        item.production_attempt_number,
      )}

      {stageRow(
        'qc',
        item.qc_status,
        item.qc_start,
        item.qc_end,
        item.qc_duration_seconds,
        item.qc_deadline,
        item.qc_target_date,
        item.qc_attempt_type,
      )}

      {stageRow(
        'qa',
        item.qa_status,
        item.qa_start,
        item.qa_end,
        item.qa_duration_seconds,
        item.qa_deadline,
        item.qa_target_date,
        item.qa_attempt_type,
      )}

      {(sessionCount > 0 ||
        cumulativeQty !== null) && (
        <div className="isa-meta isa-strong">
          Planned: {fmtQty(plannedQty)} {plannedUnit}
          {' · '}
          Cumulative actual: {fmtQty(cumulativeQty)}{' '}
          {cumulativeUnit}

          {remainingQty !== null && (
            <>
              {' · '}
              Remaining: {fmtQty(remainingQty)}{' '}
              {plannedUnit}
            </>
          )}

          {progressPct !== null && (
            <>
              {' · '}
              Progress: {progressPct}%
            </>
          )}
        </div>
      )}

      {(sessionCount > 0 ||
        item.production_duration_seconds) && (
        <div className="isa-meta">
          Production sessions: {sessionCount}

          {item.production_duration_seconds != null &&
            ` · Total production time: ${
              fmtDuration(
                item.production_duration_seconds,
              )
            }`}

          {item.production_completed_at &&
            ` · Final completion: ${
              fmtTime(
                item.production_completed_at,
              )
            }`}

          {(item.production_files ?? 0) > 0 &&
            ` · Files completed: ${
              item.production_files
            }`}
        </div>
      )}

      {item.delay_category && (
        <div className="isa-meta">
          Delay: {item.delay_category}

          {item.affected_item_number
            ? ` · ${item.affected_item_number}`
            : ''}

          {item.system_malfunction
            ? ' · SYSTEM MALFUNCTION'
            : ''}

          {item.delay_reason
            ? ` · ${item.delay_reason}`
            : ''}
        </div>
      )}

      {item.production_remarks && (
        <div className="isa-meta">
          Remarks: {item.production_remarks}
        </div>
      )}

      {item.qc_remarks && (
        <div className="isa-meta">
          QC remarks: {item.qc_remarks}
        </div>
      )}

      {item.qa_remarks && (
        <div className="isa-meta">
          QA remarks: {item.qa_remarks}
        </div>
      )}

      {openStage && (
        <div className="isa-meta isa-open">
          {stageLabel(openStage)} IN PROGRESS
          {' · '}
          started {fmtTime(openStartedAt)}

          {openStartedAt &&
            ` · elapsed ${
              fmtDuration(
                Math.floor(
                  (
                    now -
                    (
                      parseTimestamp(
                        openStartedAt,
                      ) ?? now
                    )
                  ) / 1000,
                ),
              )
            }`}
        </div>
      )}

      {/* Production and rework actions */}
      {item.production_user_id === myUserId &&
        isProductionRework && (
          <div className="isa-meta isa-wait">
            Rework requested by{' '}
            {item.production_rework_source
              ?.toUpperCase() ?? 'QC/QA'}

            {item.production_rework_reason
              ? `: ${item.production_rework_reason}`
              : ''}
          </div>
        )}

      {item.production_user_id === myUserId && (
        <div className="isa-actions">
          {openStage === 'production' &&
            active !== 'production' && (
              <button
                type="button"
                className="operations-button danger"
                disabled={busy}
                onClick={() =>
                  setActive('production')
                }
              >
                {isProductionRework
                  ? 'Complete Rework'
                  : 'Complete File'}
              </button>
            )}

          {!item.open_session &&
            canStartProduction && (
              <button
                type="button"
                className="operations-button"
                disabled={busy}
                onClick={() =>
                  start('production')
                }
              >
                {isProductionRework
                  ? 'Start Rework'
                  : 'Start Work'}
              </button>
            )}
        </div>
      )}

      {/* QC actions */}
      {item.qc_user_id === myUserId && (
        <>
          {item.production_status !==
            'completed' && (
            <div className="isa-meta isa-wait">
              QC status: WAITING FOR PRODUCTION
            </div>
          )}

          {item.production_status ===
            'completed' &&
            item.qc_status !== 'passed' && (
              <div className="isa-meta isa-strong">
                QC status:{' '}
                {item.qc_status === 'not_started'
                  ? 'READY FOR QC'
                  : label(item.qc_status)}
              </div>
            )}

          {showReviewActions && (
            <div className="isa-actions">
              {openStage === 'qc' &&
                active !== 'qc' && (
                  <button
                    type="button"
                    className="operations-button danger"
                    disabled={busy}
                    onClick={() =>
                      setActive('qc')
                    }
                  >
                    Complete QC
                  </button>
                )}

              {!item.open_session &&
                canStartQc && (
                  <button
                    type="button"
                    className="operations-button"
                    disabled={busy}
                    onClick={() =>
                      start('qc')
                    }
                  >
                    Start QC
                  </button>
                )}
            </div>
          )}
        </>
      )}

      {/* QA actions */}
      {item.qa_user_id === myUserId && (
        <>
          {item.qc_status !== 'passed' && (
            <div className="isa-meta isa-wait">
              QA status: WAITING FOR QC
            </div>
          )}

          {item.qc_status === 'passed' &&
            item.qa_status !== 'passed' && (
              <div className="isa-meta isa-strong">
                QA status:{' '}
                {item.qa_status === 'not_started'
                  ? 'READY FOR QA'
                  : label(item.qa_status)}
              </div>
            )}

          {showReviewActions && (
            <div className="isa-actions">
              {openStage === 'qa' &&
                active !== 'qa' && (
                  <button
                    type="button"
                    className="operations-button danger"
                    disabled={busy}
                    onClick={() =>
                      setActive('qa')
                    }
                  >
                    Complete QA
                  </button>
                )}

              {!item.open_session &&
                canStartQa && (
                  <button
                    type="button"
                    className="operations-button"
                    disabled={busy}
                    onClick={() =>
                      start('qa')
                    }
                  >
                    Start QA
                  </button>
                )}
            </div>
          )}
        </>
      )}

      {/* Delivery remains unchanged */}
      {canDeliver &&
        isActive &&
        item.delivery_status !== 'delivered' &&
        item.qa_status === 'passed' &&
        !item.open_session && (
          <div className="isa-actions">
            <button
              type="button"
              className="operations-button success"
              disabled={busy}
              onClick={deliver}
            >
              Mark Delivered
            </button>
          </div>
        )}

      {/* Production Complete File form */}
      {openStage === 'production' &&
        active === 'production' && (
          <div className="isa-form">
            <strong>
              {isProductionRework
                ? 'Complete rework'
                : 'Complete file'}
              {' — '}
              {item.item_number}
            </strong>

            {/* Locked actual quantity */}
            <div className="pt-form-row">
              <div className="operations-field">
                <span>
                  Actual Quantity (
                  {lockedUnit ||
                    item.planned_unit ||
                    'unit'}
                  )
                </span>

                <output
                  className="isa-locked-value"
                  aria-label="Locked actual quantity"
                  style={{
                    display: 'block',
                    width: '100%',
                    padding: '12px 14px',
                    marginTop: 6,
                    border: '1px solid #cbd5e1',
                    borderRadius: 9,
                    backgroundColor: '#f1f5f9',
                    color: '#17324d',
                    fontSize: 16,
                    fontWeight: 700,
                    fontVariantNumeric:
                      'tabular-nums',
                    boxSizing: 'border-box',
                  }}
                >
                  {lockedActualAvailable
                    ? lockedQuantity
                    : 'Not available'}
                </output>

                <small>
                  Automatically calculated from
                  the imported planned quantity.
                  This value cannot be edited.
                </small>
              </div>
            </div>

            {!lockedActualAvailable && (
              <div className="operations-alert error">
                Locked quantity has not been
                supplied by the backend.
                Completion is disabled until
                the server provides it.
              </div>
            )}

            <div className="isa-meta">
              Completing the file records
              the server end time and duration
              and unlocks QC for this file.
              Files completed is counted
              automatically, once per physical
              file and not per attempt.
            </div>

            {/* Optional delay information */}
            <div className="pt-delay-box">
              <strong>
                Difficulty / Delay (optional)
              </strong>

              <div className="pt-form-row">
                <label className="operations-field">
                  <span>Delay category</span>

                  <select
                    value={
                      prodDraft.delayCategory
                    }
                    onChange={(e) =>
                      setProdDraft({
                        ...prodDraft,
                        delayCategory:
                          e.target.value,
                        systemMalfunction:
                          e.target.value ===
                          'System Malfunction'
                            ? true
                            : prodDraft.systemMalfunction,
                      })
                    }
                  >
                    <option value="">
                      None
                    </option>

                    {DELAY_CATEGORIES.map(
                      (category) => (
                        <option
                          key={category}
                          value={category}
                        >
                          {category}
                        </option>
                      ),
                    )}
                  </select>
                </label>

                <label className="operations-field">
                  <span>Reason</span>

                  <input
                    value={
                      prodDraft.delayReason
                    }
                    onChange={(e) =>
                      setProdDraft({
                        ...prodDraft,
                        delayReason:
                          e.target.value,
                      })
                    }
                  />
                </label>
              </div>

              <div className="pt-form-row">
                <label className="operations-check">
                  <input
                    type="checkbox"
                    checked={
                      prodDraft.systemMalfunction
                    }
                    onChange={(e) =>
                      setProdDraft({
                        ...prodDraft,
                        systemMalfunction:
                          e.target.checked,
                      })
                    }
                  />

                  <span>
                    System Malfunction — the
                    system affected production
                    speed (not employee-caused)
                  </span>
                </label>
              </div>
            </div>

            <div className="operations-actions">
              <button
                type="button"
                className="operations-button success"
                disabled={
                  busy || !lockedActualAvailable
                }
                onClick={() =>
                  submitProduction(true)
                }
              >
                {isProductionRework
                  ? 'Complete Rework'
                  : 'Complete File'}
              </button>

              <button
                type="button"
                className="operations-button secondary"
                onClick={() =>
                  setActive(null)
                }
              >
                Cancel
              </button>
            </div>
          </div>
        )}

      {/* Existing QC / QA form */}
      {showReviewActions &&
        (
          openStage === 'qc' ||
          openStage === 'qa'
        ) &&
        active === openStage && (
          <div className="isa-form">
            <strong>
              {openStage === 'qc'
                ? 'Complete QC'
                : 'Complete QA'}
              {' — '}
              {item.item_number}
            </strong>

            <div className="pt-form-row">
              <label className="operations-field">
                <span>Result *</span>

                <select
                  value={reviewDraft.status}
                  onChange={(e) =>
                    setReviewDraft({
                      ...reviewDraft,
                      status: e.target.value,
                    })
                  }
                >
                  <option value="passed">
                    Pass
                  </option>

                  <option value="rejected">
                    Reject
                  </option>

                  <option value="rework">
                    Rework
                  </option>
                </select>
              </label>

              <label className="operations-field">
                <span>
                  Comments
                  {reviewDraft.status !== 'passed'
                    ? ' *'
                    : ''}
                </span>

                <input
                  value={reviewDraft.remarks}
                  onChange={(e) =>
                    setReviewDraft({
                      ...reviewDraft,
                      remarks: e.target.value,
                    })
                  }
                />
              </label>
            </div>

            <div className="operations-actions">
              <button
                type="button"
                className="operations-button success"
                disabled={busy}
                onClick={() =>
                  completeReview(openStage)
                }
              >
                Save {openStage.toUpperCase()} Result
              </button>

              <button
                type="button"
                className="operations-button secondary"
                onClick={() =>
                  setActive(null)
                }
              >
                Cancel
              </button>
            </div>
          </div>
        )}

      {busy && (
        <div className="pt-drawer-loading">
          <Loader2
            size={14}
            className="spin"
          />
          {' '}
          Saving…
        </div>
      )}
    </div>
  )
}
