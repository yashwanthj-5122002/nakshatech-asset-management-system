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
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [fileQuery, setFileQuery] = useState('')
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
    // Drop only files that have become ineligible after a backend refresh.
    const eligible = new Set(canRework.map(item => item.work_package_item_id))
    setSelectedIds(current => {
      const remaining = current.filter(id => eligible.has(id))
      return remaining.length === current.length ? current : remaining
    })
  }, [items, myUserId, stage])

  const visibleRework = canRework.filter(item =>
    `${item.item_number} ${item.item_name || ''}`.toLowerCase().includes(fileQuery.trim().toLowerCase()),
  )

  async function execute(endpoint: string, body?: object): Promise<boolean> {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const result = await apiFetch<{count?: number; item_ids?: number[]}>(
        `/operations/workflow/ortho/work-packages/${packageId}/review/${stage}/${endpoint}`,
        { method: 'POST', ...(body ? { body: JSON.stringify(body) } : {}) },
      )
      setNotice(endpoint === 'rework/bulk'
        ? `${result.count ?? 0} selected file(s) sent to Production for rework.`
        : `${stage.toUpperCase()}: ${result.count ?? 0} file(s) ${endpoint === 'start' ? 'started' : 'passed'}.`)
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
    if (!selectedIds.length || reason.trim().length < 3) {
      setError('Choose one or more files and enter a rework reason (at least 3 characters).')
      return
    }
    if (await execute('rework/bulk', { item_ids: selectedIds, reason: reason.trim() })) {
      setOpenRework(false)
      setSelectedIds([])
      setFileQuery('')
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
            onClick={() => void execute('start')}>Start All {owned.length}</button>
          <button type="button" className="operations-button success" disabled={busy || reviewing.length === 0}
            onClick={() => void execute('complete')}>Complete All {owned.length}</button>
          <button type="button" className="operations-button secondary" disabled={busy}
            aria-expanded={openRework} onClick={() => setOpenRework(v => !v)}>Rework ▾</button>
        </div>
      </div>
      {openRework && (
        <div className="assignment-review-dropdown">
          <strong>Select files to send back to Production</strong>
          {canRework.length ? (
            <>
              <label className="operations-field">
                <span>Search eligible MARCENA files</span>
                <input value={fileQuery} onChange={event => setFileQuery(event.target.value)}
                  placeholder="Search file number or name" />
              </label>
              <div className="assignment-review-selection-bar">
                <span>{selectedIds.length} of {canRework.length} eligible files selected</span>
                <button type="button" className="operations-button secondary" disabled={busy}
                  onClick={() => setSelectedIds(canRework.map(item => item.work_package_item_id))}>Select All Eligible</button>
                <button type="button" className="operations-button secondary" disabled={busy || !selectedIds.length}
                  onClick={() => setSelectedIds([])}>Clear</button>
              </div>
              <div className="assignment-review-file-picker" role="group" aria-label="Files for Production rework">
                {visibleRework.map(item => <label key={item.work_package_item_id} className="assignment-review-file-choice">
                  <input type="checkbox" checked={selectedIds.includes(item.work_package_item_id)} disabled={busy}
                    onChange={event => setSelectedIds(current => event.target.checked
                      ? current.includes(item.work_package_item_id) ? current : [...current, item.work_package_item_id]
                      : current.filter(id => id !== item.work_package_item_id))}/>
                  <span><strong>{item.item_number}</strong>{item.item_name ? ` — ${item.item_name}` : ''}</span>
                </label>)}
                {!visibleRework.length && <small>No eligible files match this search.</small>}
              </div>
              <label className="operations-field">
                <span>Reason for Production rework *</span>
                <textarea rows={3} value={reason} onChange={event => setReason(event.target.value)}
                  maxLength={2000} placeholder="Describe the corrections required for the selected files" />
              </label>
              <button type="button" className="operations-button danger" disabled={busy || !selectedIds.length || reason.trim().length < 3}
                onClick={() => { if (window.confirm(`Send ${selectedIds.length} selected file(s) back to Production for rework?`)) void sendRework() }}>
                Send {selectedIds.length} Selected File{selectedIds.length === 1 ? '' : 's'} to Production
              </button>
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
