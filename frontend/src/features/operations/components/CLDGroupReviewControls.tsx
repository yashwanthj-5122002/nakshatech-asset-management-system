import { useEffect, useState } from 'react'
import { apiFetch } from '../../../lib/api'
import { parseTimestamp, type ActivityItem } from './ItemStageActivityControls'
import './assignment-review-controls.css'

// CLD master imports intentionally create ONE package per MARCENA file. This
// separate toolbar groups files from the SAME imported source, project and
// reviewer. It never modifies the existing individual file action component.
type Stage = 'qc' | 'qa'
type Props = {
  projectId: number
  sourceName: string | null
  items: ActivityItem[]
  myUserId: number
  onChanged: () => void
}

function isRework(status: string) { return status === 'rework' || status === 'rejected' }

function StageActions({ stage, projectId, items, myUserId, onChanged }: Props & { stage: Stage }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [open, setOpen] = useState(false)
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [search, setSearch] = useState('')
  const [reason, setReason] = useState('')

  const owned = items.filter(item => item.is_active !== false &&
    (stage === 'qc' ? item.qc_user_id : item.qa_user_id) === myUserId)
  const active = owned.filter(item => item.open_session?.employee_user_id === myUserId && item.open_session.stage === stage)
  const passed = owned.filter(item => (stage === 'qc' ? item.qc_status : item.qa_status) === 'passed')
  const rework = owned.filter(item => isRework(stage === 'qc' ? item.qc_status : item.qa_status))
  const eligibleRework = owned.filter(item => {
    if (item.production_status !== 'completed' || item.delivery_status === 'delivered' || item.ready_for_delivery) return false
    if (item.open_session) return item.open_session.employee_user_id === myUserId && item.open_session.stage === stage
    const status = stage === 'qc' ? item.qc_status : item.qa_status
    if (status !== 'passed') return false
    return stage === 'qc' ? item.qa_status === 'not_started' : item.qc_status === 'passed'
  })
  const canStart = owned.some(item => {
    if (item.open_session || item.production_status !== 'completed') return false
    if (stage === 'qa' && item.qc_status !== 'passed') return false
    const status = stage === 'qc' ? item.qc_status : item.qa_status
    if (status === 'passed' || status === 'in_progress') return false
    if (isRework(status)) {
      const productionEnd = item.production_end ? parseTimestamp(item.production_end) : null
      const lastReview = stage === 'qc' ? item.qc_end : item.qa_end
      const reviewEnd = lastReview ? parseTimestamp(lastReview) : null
      return productionEnd !== null && reviewEnd !== null && productionEnd > reviewEnd
    }
    return true
  })
  // Label only: show pending review files, never the entire CLD import size.
  // Keep act() targets, canStart, Complete/Rework gates and per-file UI unchanged.
  const pendingCount = owned.filter(item => {
    const status = stage === 'qc' ? item.qc_status : item.qa_status
    if (status === 'passed') return false
    if (item.open_session) {
      return item.open_session.employee_user_id === myUserId && item.open_session.stage === stage
    }
    if (item.production_status !== 'completed') return false
    if (stage === 'qa' && item.qc_status !== 'passed') return false
    if (status === 'in_progress') return false
    if (isRework(status)) {
      const productionEnd = item.production_end ? parseTimestamp(item.production_end) : null
      const lastReview = stage === 'qc' ? item.qc_end : item.qa_end
      const reviewEnd = lastReview ? parseTimestamp(lastReview) : null
      return productionEnd !== null && reviewEnd !== null && productionEnd > reviewEnd
    }
    return true
  }).length
  const filtered = eligibleRework.filter(item =>
    `${item.item_number} ${item.item_name ?? ''}`.toLowerCase().includes(search.toLowerCase()))

  useEffect(() => {
    const valid = new Set(eligibleRework.map(item => item.work_package_item_id))
    setSelectedIds(current => current.every(id => valid.has(id)) ? current : current.filter(id => valid.has(id)))
  }, [items, myUserId, stage])

  async function act(action: 'start' | 'complete' | 'rework') {
    const target = action === 'rework' ? selectedIds : owned.map(item => item.work_package_item_id)
    if (!target.length) { setError('No files selected for this action.'); return }
    if (action === 'rework' && reason.trim().length < 3) {
      setError('Select one or more files and enter a rework reason (at least 3 characters).')
      return
    }
    if (action === 'complete' && !window.confirm(`Complete ${stage.toUpperCase()} for all eligible active files in this ${owned.length}-file block?`)) return
    if (action === 'rework' && !window.confirm(`Send ${target.length} selected MARCENA file(s) to Production for correction?`)) return
    setBusy(true); setError(''); setNotice('')
    try {
      const response = await apiFetch<{ count: number }>(
        `/operations/workflow/ortho/projects/${projectId}/cld-review/${stage}/${action}`,
        { method: 'POST', body: JSON.stringify({ item_ids: target, ...(action === 'rework' ? { reason: reason.trim() } : {}) }) },
      )
      setNotice(`${stage.toUpperCase()}: ${response.count} file(s) ${action === 'start' ? 'started' : action === 'complete' ? 'passed' : 'sent to Production for rework'}.`)
      if (action === 'rework') { setOpen(false); setSelectedIds([]); setReason('') }
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to save block review action')
    } finally { setBusy(false) }
  }

  if (!owned.length) return null
  return <section className="assignment-review cld-stage" aria-label={`${stage.toUpperCase()} full CLD import review`}>
    <div className="assignment-review-heading">
      <div><strong>{stage.toUpperCase()} Review — Entire Block</strong>
        <span>{passed.length} of {owned.length} passed · {active.length} in progress · {rework.length} rework</span>
      </div>
      <div className="assignment-review-buttons">
        <button type="button" className="operations-button" disabled={busy || !canStart}
          onClick={() => void act('start')}>Start All {pendingCount}</button>
        <button type="button" className="operations-button success" disabled={busy || !active.length}
          onClick={() => void act('complete')}>Complete All {pendingCount}</button>
        <button type="button" className="operations-button secondary" disabled={busy}
          aria-expanded={open} onClick={() => setOpen(v => !v)}>Rework ▾</button>
      </div>
    </div>
    {open && <div className="assignment-review-dropdown cld-review-dropdown">
      <strong>Select MARCENA files to return to Production</strong>
      <small>Only checked files will be returned. Your existing single-file actions remain unchanged.</small>
      {eligibleRework.length ? <>
        <label className="operations-field"><span>Search file names</span>
          <input value={search} onChange={event => setSearch(event.target.value)} placeholder="MARCENA file name" />
        </label>
        <div className="cld-review-selection-actions">
          <span>{selectedIds.length} of {eligibleRework.length} eligible file(s) selected</span>
          <button type="button" className="operations-button secondary" disabled={busy}
            onClick={() => setSelectedIds(eligibleRework.map(item => item.work_package_item_id))}>Select All Eligible</button>
          <button type="button" className="operations-button secondary" disabled={busy}
            onClick={() => setSelectedIds([])}>Clear</button>
        </div>
        <div className="cld-review-file-list">
          {filtered.map(item => <label className="cld-review-file" key={item.work_package_item_id}>
            <input type="checkbox" checked={selectedIds.includes(item.work_package_item_id)} disabled={busy}
              onChange={event => setSelectedIds(current => event.target.checked
                ? [...current.filter(id => id !== item.work_package_item_id), item.work_package_item_id]
                : current.filter(id => id !== item.work_package_item_id))} />
            <span><strong>{item.item_number}</strong>{item.item_name && item.item_name !== item.item_number ? ` — ${item.item_name}` : ''}</span>
            <small>{stage === 'qc' ? item.qc_status : item.qa_status}</small>
          </label>)}
          {!filtered.length && <small>No eligible files match this search.</small>}
        </div>
        <label className="operations-field"><span>Production rework reason *</span>
          <textarea rows={3} maxLength={2000} value={reason} onChange={event => setReason(event.target.value)}
            placeholder="Describe what Production must correct" />
        </label>
        <button type="button" className="operations-button danger" disabled={busy || !selectedIds.length || reason.trim().length < 3}
          onClick={() => void act('rework')}>Send {selectedIds.length} Selected File(s) to Production</button>
      </> : <small>No files currently qualify for rework. Start a review, or wait until the files are eligible.</small>}
      <div className="assignment-review-sent"><strong>Files already returned to Production</strong>
        {rework.length ? rework.map(item => <span key={item.work_package_item_id}>
          {item.item_number}: {(stage === 'qc' ? item.qc_remarks : item.qa_remarks) || 'Sent for correction'}
        </span>) : <small>None in this block.</small>}
      </div>
    </div>}
    {error && <div className="operations-alert error" role="alert">{error}</div>}
    {notice && <div className="operations-alert success" role="status">{notice}</div>}
  </section>
}

export function CLDGroupReviewControls(props: Props) {
  const hasQc = props.items.some(item => item.is_active !== false && item.qc_user_id === props.myUserId)
  const hasQa = props.items.some(item => item.is_active !== false && item.qa_user_id === props.myUserId)
  if (!hasQc && !hasQa) return null
  return <div className="cld-block-review">
    <div className="cld-block-heading">
      <div><span className="operations-kicker">ASSIGNMENT BLOCK · CLD IMPORT</span>
        <h3>CENTRELINE_M — {props.items.length} MARCENA files</h3>
        <small>Source: {props.sourceName || 'CLD import'} · Actions apply only to your assigned files</small>
      </div>
    </div>
    {hasQc && <StageActions {...props} stage="qc" />}
    {hasQa && <StageActions {...props} stage="qa" />}
    <small className="cld-review-note">The individual Start QC, QC Pass, Complete QC and Open Production Tracking buttons remain below each file.</small>
  </div>
}
