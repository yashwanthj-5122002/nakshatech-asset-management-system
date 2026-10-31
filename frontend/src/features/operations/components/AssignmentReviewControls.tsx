import { useEffect, useState } from 'react'
import { apiFetch } from '../../../lib/api'
import { parseTimestamp, type ActivityItem } from './ItemStageActivityControls'
import './assignment-review-controls.css'

type ReviewStage = 'qc' | 'qa'
type Props = {
  packageId: number
  items: ActivityItem[]
  myUserId: number
  onChanged: () => void
}

function isRework(value: string) {
  return value === 'rejected' || value === 'rework'
}

function ReviewStageControls({ stage, packageId, items, myUserId, onChanged }: Props & { stage: ReviewStage }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [openRework, setOpenRework] = useState(false)
  const [selectedId, setSelectedId] = useState('')
  const [reason, setReason] = useState('')

  const owned = items.filter(item => item.is_active !== false && (stage === 'qc' ? item.qc_user_id : item.qa_user_id) === myUserId)
  const reviewing = owned.filter(item => item.open_session?.employee_user_id === myUserId && item.open_session.stage === stage)
  const previouslySent = owned.filter(item => isRework(stage === 'qc' ? item.qc_status : item.qa_status))
  // Rework can be requested while reviewing OR immediately after a PASS.
  // A QC-passed file is locked once QA has begun; a QA-passed file is locked
  // after Ready for Delivery is confirmed or the file is delivered.
  const canRework = owned.filter(item => {
    if (item.production_status !== 'completed') return false
    if (item.delivery_status === 'delivered' || item.ready_for_delivery) return false
    if (item.open_session) {
      return item.open_session.employee_user_id === myUserId && item.open_session.stage === stage
    }
    const status = stage === 'qc' ? item.qc_status : item.qa_status
    if (status !== 'passed') return false
    if (stage === 'qc') return item.qa_status === 'not_started'
    return item.qc_status === 'passed'
  })
  const readyToStart = owned.some(item => {
    if (item.open_session) return false
    if (item.production_status !== 'completed') return false
    if (stage === 'qa' && item.qc_status !== 'passed') return false
    const status = stage === 'qc' ? item.qc_status : item.qa_status
    if (status === 'passed' || status === 'in_progress') return false
    if (isRework(status)) {
      // After rejection, Production must finish a newer correction attempt.
      // Backend checks this again using authoritative activity records.
      const prodEnd = item.production_end ? parseTimestamp(item.production_end) : null
      const reviewEndText = stage === 'qc' ? item.qc_end : item.qa_end
      const reviewEnd = reviewEndText ? parseTimestamp(reviewEndText) : null
      return prodEnd !== null && reviewEnd !== null && prodEnd > reviewEnd
    }
    return true
  })
  const alreadyPassed = owned.filter(item => (stage === 'qc' ? item.qc_status : item.qa_status) === 'passed').length

  useEffect(() => {
    // Keep the dropdown open after Complete; only clear a selection that
    // is no longer eligible according to the refreshed backend state.
    if (selectedId && !canRework.some(item => item.work_package_item_id === Number(selectedId))) {
      setSelectedId('')
    }
  }, [selectedId, items, myUserId, stage])

  async function execute(endpoint: string, body?: object): Promise<boolean> {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const result = await apiFetch<{count?: number; item_id?: number}>(
        `/operations/workflow/ortho/work-packages/${packageId}/review/${stage}/${endpoint}`,
        { method: 'POST', ...(body ? { body: JSON.stringify(body) } : {}) },
      )
      setNotice(endpoint === 'rework' ? 'Selected file sent back to Production.' :
        `${stage.toUpperCase()}: ${result.count ?? 0} file(s) ${endpoint === 'start' ? 'started' : 'passed'}.`)
      onChanged()
      return true
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to save review activity')
      return false
    } finally {
      setBusy(false)
    }
  }

  async function sendRework() {
    if (!selectedId || reason.trim().length < 3) {
      setError('Choose a file and enter a rework reason (at least 3 characters).')
      return
    }
    if (await execute('rework', { item_id: Number(selectedId), reason: reason.trim() })) {
      setOpenRework(false)
      setSelectedId('')
      setReason('')
    }
  }

  if (!owned.length) return null
  return (
    <section className="assignment-review" aria-label={`${stage.toUpperCase()} assignment controls`}>
      <div className="assignment-review-heading">
        <div>
          <strong>{stage.toUpperCase()} Review</strong>
          <span>{alreadyPassed} of {owned.length} passed · {reviewing.length} in progress · {previouslySent.length} rework</span>
        </div>
        <div className="assignment-review-buttons">
          <button type="button" className="operations-button" disabled={busy || !readyToStart}
            onClick={() => void execute('start')}>Start</button>
          <button type="button" className="operations-button success" disabled={busy || reviewing.length === 0}
            onClick={() => void execute('complete')}>Complete</button>
          <button type="button" className="operations-button secondary" disabled={busy}
            aria-expanded={openRework} onClick={() => setOpenRework(v => !v)}>Rework ▾</button>
        </div>
      </div>
      {openRework && (
        <div className="assignment-review-dropdown">
          <strong>Send a file back to Production</strong>
          {canRework.length ? (
            <>
              <label className="operations-field">
                <span>File to rework</span>
                <select value={selectedId} onChange={event => setSelectedId(event.target.value)}>
                  <option value="">Select a file</option>
                  {canRework.map(item => <option key={item.work_package_item_id} value={item.work_package_item_id}>
                    {item.item_number}{item.item_name ? ` - ${item.item_name}` : ''}
                  </option>)}
                </select>
              </label>
              <label className="operations-field">
                <span>Reason *</span>
                <textarea rows={2} value={reason} onChange={event => setReason(event.target.value)}
                  placeholder="Describe the issue for Production" />
              </label>
              <button type="button" className="operations-button danger" disabled={busy || !selectedId || reason.trim().length < 3}
                onClick={() => { if (window.confirm('Send the selected file back to Production for rework?')) void sendRework() }}>Send Selected File to Production</button>
            </>
          ) : <small>No files are eligible for rework. Only your active review files or passed files that have not moved to the next stage can be selected.</small>}
          <div className="assignment-review-sent">
            <strong>Files currently sent to Production for rework</strong>
            {previouslySent.length ? previouslySent.map(item => <span key={item.work_package_item_id}>
              {item.item_number}{item.item_name ? ` - ${item.item_name}` : ''}: {stage === 'qc' ? item.qc_remarks || 'Sent to Production' : item.qa_remarks || 'Sent to Production'}
            </span>) : <small>No files sent back at this stage.</small>}
          </div>
        </div>
      )}
      {error && <div className="operations-alert error" role="alert">{error}</div>}
      {notice && <div className="operations-alert success" role="status">{notice}</div>}
    </section>
  )
}

export function AssignmentReviewControls(props: Props) {
  const hasQc = props.items.some(item => item.is_active !== false && item.qc_user_id === props.myUserId)
  const hasQa = props.items.some(item => item.is_active !== false && item.qa_user_id === props.myUserId)
  if (!hasQc && !hasQa) return null
  return (
    <div className="assignment-review-list">
      {hasQc && <ReviewStageControls {...props} stage="qc" />}
      {hasQa && <ReviewStageControls {...props} stage="qa" />}
    </div>
  )
}
