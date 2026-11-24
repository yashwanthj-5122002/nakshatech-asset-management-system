
import { useEffect, useRef, useState } from 'react'
import { apiFetch } from '../../lib/api'

export type BDAIContext = {
  client_name: string
  project_reference: string
  department: string
  requirements: string
}

export type BDAIAnalysis = {
  project_objective: string
  scope_of_work: string
  expected_deliverables: string[]
  technical_specifications: string[]
  constraints_deadline: string
  missing_information: string[]
  clarification_questions: string[]
  confirmed_requirements: string[]
  acceptance_criteria: string[]
  department_handover_notes: string[]
}

export type BDAIAnswer = {
  question: string
  answer: string
}

export type SubmissionSnapshot = {
  context: BDAIContext
  analysis: BDAIAnalysis
  answers: BDAIAnswer[]
  human_verified: boolean
  pending_acknowledged: boolean
  revision_note: string
}

type SubmissionStatus =
  | 'pending_review'
  | 'approved'
  | 'returned'
  | 'rejected'

export type SubmissionRow = {
  id: number
  reference: string
  employee_name: string
  employee_code: string | null
  client_name: string
  project_reference: string
  department: string
  status: SubmissionStatus
  revision_number: number
  submitted_at: string
  already_submitted?: boolean
}

export type SubmissionDetail = SubmissionRow & {
  manager_name: string | null
  snapshot: SubmissionSnapshot
  viewed_revision: number
  revisions: {
    revision_number: number
    submitted_at: string
  }[]
  events: {
    action: string
    actor_name: string
    revision_number: number
    note: string | null
    created_at: string
  }[]
}

type SubmissionList = {
  items: SubmissionRow[]
  has_more: boolean
  offset: number
}

const labels: Record<string, string> = {
  all: 'All Submissions',
  pending_review: 'Pending Review',
  approved: 'Approved',
  returned: 'Returned for Revision',
  rejected: 'Rejected',
}

function formatDate(value: string) {
  const normalized = /Z$|[+-]\d{2}:\d{2}$/.test(value)
    ? value
    : `${value}Z`

  return new Date(normalized).toLocaleString('en-IN', {
    timeZone: 'Asia/Kolkata',
  })
}

function showValue(value: string | string[]) {
  if (Array.isArray(value)) {
    return value.length ? (
      <ul>
        {value.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    ) : <p>None recorded</p>
  }

  return <p style={{ whiteSpace: 'pre-wrap' }}>{value || 'Not specified'}</p>
}

type Props = {
  managerMode: boolean
  refreshKey: number
  editingBusy?: boolean
  onRevise?: (detail: SubmissionDetail) => boolean
}

export function BDSubmissionPanel({
  managerMode,
  refreshKey,
  editingBusy = false,
  onRevise,
}: Props) {
  const [rows, setRows] = useState<SubmissionRow[]>([])
  const [filter, setFilter] = useState('all')
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const [loading, setLoading] = useState(false)
  const [detail, setDetail] = useState<SubmissionDetail | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [detailError, setDetailError] = useState('')
  const [note, setNote] = useState('')

  const dialogRef = useRef<HTMLDialogElement>(null)
  const actionLock = useRef(false)

  useEffect(() => {
    let active = true

    const endpoint = managerMode
      ? '/bd-ai/manager/submissions'
      : '/bd-ai/submissions/mine'

    setLoading(true)
    setError('')

    apiFetch<SubmissionList>(
      `${endpoint}?request_status=${filter}&limit=50&offset=${offset}`
    )
      .then(result => {
        if (!active) return
        setRows(result.items)
        setHasMore(result.has_more)
      })
      .catch(err => {
        if (!active) return
        setRows([])
        setHasMore(false)
        setError(err instanceof Error ? err.message : 'Unable to load submissions')
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => { active = false }
  }, [managerMode, filter, offset, refreshKey, refresh])

  useEffect(() => {
    const dialog = dialogRef.current

    if (detail && dialog && !dialog.open) {
      dialog.showModal()
    }
  }, [detail])

  async function openDetail(id: number, revision?: number) {
    if (actionLock.current) return

    actionLock.current = true
    setBusy(true)
    setDetailError('')
    setError('')

    try {
      const suffix = revision ? `?revision=${revision}` : ''

      const result = await apiFetch<SubmissionDetail>(
        `/bd-ai/submissions/${id}${suffix}`
      )

      setDetail(result)
      setNote('')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unable to load brief'
      if (detail) setDetailError(message)
      else setError(message)
    } finally {
      actionLock.current = false
      setBusy(false)
    }
  }

  function closeDetail() {
    if (actionLock.current) return
    dialogRef.current?.close()
    setDetail(null)
    setDetailError('')
    setNote('')
  }

  async function review(decision: 'approve' | 'return' | 'reject') {
    if (
      actionLock.current ||
      !managerMode ||
      !detail ||
      detail.status !== 'pending_review' ||
      detail.viewed_revision !== detail.revision_number
    ) return

    if (decision !== 'approve' && !note.trim()) {
      setDetailError('Manager remarks are required.')
      return
    }

    if (!window.confirm(`Confirm ${decision} for ${detail.reference}?`)) return

    actionLock.current = true
    setBusy(true)
    setDetailError('')

    try {
      await apiFetch<SubmissionRow>(
        `/bd-ai/manager/submissions/${detail.id}/${decision}`,
        {
          method: 'POST',
          body: JSON.stringify({
            expected_revision: detail.revision_number,
            note: note.trim(),
          }),
        }
      )

      dialogRef.current?.close()
      setDetail(null)
      setRefresh(value => value + 1)
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : 'Review failed')
    } finally {
      actionLock.current = false
      setBusy(false)
    }
  }

  return (
    <section className="bd-ai-card" style={{ marginBottom: 20 }}>
      <div className="bd-ai-card-title">
        <div>
          <h2>
            {managerMode
              ? 'Technical Requirement Requests'
              : 'My Submissions'}
          </h2>
          <p>Review and track submitted technical requirement briefs.</p>
        </div>
      </div>

      <div className="bd-ai-actions">
        <select
          aria-label="Filter submissions"
          value={filter}
          disabled={busy}
          onChange={e => {
            setFilter(e.target.value)
            setOffset(0)
          }}
        >
          {Object.entries(labels).map(([key, label]) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </select>

        <button
          type="button"
          className="bd-ai-button-secondary"
          disabled={loading || busy}
          onClick={() => setRefresh(value => value + 1)}
        >
          Refresh
        </button>
      </div>

      {error && <p role="alert">{error}</p>}
      {loading && <p>Loading submissions...</p>}
      {!loading && !error && rows.length === 0 && (
        <p>No submissions found.</p>
      )}

      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', textAlign: 'left', borderSpacing: 8 }}>
          <thead>
            <tr>
              <th>Reference</th>
              <th>Client / Project</th>
              {managerMode && <th>Employee</th>}
              <th>Department</th>
              <th>Status</th>
              <th>Submitted</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={row.id}>
                <td>{row.reference}</td>
                <td>
                  <strong>{row.client_name}</strong>
                  <div>{row.project_reference}</div>
                </td>
                {managerMode && (
                  <td>{row.employee_name} ({row.employee_code || '-'})</td>
                )}
                <td>{row.department}</td>
                <td>{labels[row.status] || row.status}</td>
                <td>{formatDate(row.submitted_at)}</td>
                <td>
                  <button
                    type="button"
                    className="bd-ai-button-secondary"
                    disabled={busy}
                    onClick={() => void openDetail(row.id)}
                  >
                    View Details
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="bd-ai-actions">
        <button
          type="button"
          className="bd-ai-button-secondary"
          disabled={offset === 0 || loading || busy}
          onClick={() => setOffset(value => Math.max(0, value - 50))}
        >
          Previous
        </button>

        <button
          type="button"
          className="bd-ai-button-secondary"
          disabled={!hasMore || loading || busy}
          onClick={() => setOffset(value => value + 50)}
        >
          Next
        </button>
      </div>

      {detail && (
        <dialog
          ref={dialogRef}
          onCancel={e => {
            e.preventDefault()
            closeDetail()
          }}
          style={{
            width: 'min(900px, 92vw)',
            maxHeight: '85vh',
            overflowY: 'auto',
            borderRadius: 14,
            padding: 20,
          }}
        >
          <section className="bd-ai-card">
            <div className="bd-ai-actions">
              <h2>{detail.reference}</h2>

              <button
                type="button"
                className="bd-ai-button-secondary"
                disabled={busy}
                onClick={closeDetail}
              >
                Close
              </button>
            </div>

            <p><strong>Status:</strong> {labels[detail.status]}</p>
            <p><strong>Employee:</strong> {detail.employee_name}</p>
            <p><strong>Manager:</strong> {detail.manager_name || 'Not available'}</p>

            <label className="bd-ai-field">
              <span>Submitted Revision</span>
              <select
                value={detail.viewed_revision}
                disabled={busy}
                onChange={e => void openDetail(detail.id, Number(e.target.value))}
              >
                {detail.revisions.map(rev => (
                  <option key={rev.revision_number} value={rev.revision_number}>
                    Revision {rev.revision_number}
                  </option>
                ))}
              </select>
            </label>

            <div className="bd-ai-brief">
              <h3>Client Requirements</h3>

              <p><strong>Client:</strong> {detail.snapshot.context.client_name}</p>
              <p><strong>Project:</strong> {detail.snapshot.context.project_reference}</p>
              <p><strong>Department:</strong> {detail.snapshot.context.department}</p>

              {showValue(detail.snapshot.context.requirements)}

              <h3>Technical Requirement Brief</h3>

              {Object.entries(detail.snapshot.analysis).map(([key, value]) => (
                <div key={key}>
                  <strong style={{ textTransform: 'capitalize' }}>
                    {key.replace(/_/g, ' ')}
                  </strong>
                  {showValue(value)}
                </div>
              ))}

              <h3>Clarification History</h3>

              {detail.snapshot.answers.length === 0 && <p>No answers recorded.</p>}

              {detail.snapshot.answers.map((item, i) => (
                <div key={i}>
                  <strong>{i + 1}. {item.question}</strong>
                  <p style={{ whiteSpace: 'pre-wrap' }}>{item.answer}</p>
                </div>
              ))}

              <p>
                <strong>Human verification:</strong>{' '}
                {detail.snapshot.human_verified ? 'Confirmed' : 'Not confirmed'}
              </p>

              {detail.snapshot.revision_note && (
                <p><strong>Revision note:</strong> {detail.snapshot.revision_note}</p>
              )}

              <h3>Review History</h3>

              {detail.events.map((event, i) => (
                <div key={i}>
                  <strong>
                    {event.action.toUpperCase()} — Revision {event.revision_number}
                  </strong>
                  <p>{event.actor_name} · {formatDate(event.created_at)}</p>
                  {event.note && <p>{event.note}</p>}
                </div>
              ))}
            </div>

            {detailError && <p role="alert">{detailError}</p>}

            {managerMode &&
              detail.status === 'pending_review' &&
              detail.viewed_revision === detail.revision_number && (
                <>
                  <label className="bd-ai-field">
                    <span>Manager Remarks</span>
                    <textarea
                      rows={4}
                      maxLength={2000}
                      value={note}
                      disabled={busy}
                      onChange={e => setNote(e.target.value)}
                    />
                  </label>

                  <div className="bd-ai-actions">
                    <button
                      type="button"
                      className="bd-ai-button-primary"
                      disabled={busy}
                      onClick={() => void review('approve')}
                    >
                      Approve Brief
                    </button>

                    <button
                      type="button"
                      className="bd-ai-button-secondary"
                      disabled={busy || !note.trim()}
                      onClick={() => void review('return')}
                    >
                      Return for Revision
                    </button>

                    <button
                      type="button"
                      className="bd-ai-button-secondary"
                      disabled={busy || !note.trim()}
                      onClick={() => void review('reject')}
                    >
                      Reject
                    </button>
                  </div>
                </>
              )}

            {!managerMode &&
              detail.status === 'returned' &&
              detail.viewed_revision === detail.revision_number && (
                <button
                  type="button"
                  className="bd-ai-button-primary"
                  disabled={busy || editingBusy}
                  onClick={() => {
                    if (onRevise?.(detail)) closeDetail()
                  }}
                >
                  Revise and Resubmit
                </button>
              )}
          </section>
        </dialog>
      )}
    </section>
  )
}

