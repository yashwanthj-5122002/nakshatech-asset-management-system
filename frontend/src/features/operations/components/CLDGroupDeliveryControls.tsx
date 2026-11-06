import { useState } from 'react'
import { apiFetch } from '../../../lib/api'
import type { ActivityItem } from './ItemStageActivityControls'
import './assignment-review-controls.css'

type Props = {
  projectId: number
  sourceName: string
  items: ActivityItem[]
  onChanged: () => void
}

// Dedicated TL / PM toolbar. Existing per-file Mark Ready for Delivery actions,
// QC/QA review controls, and actual delivery actions are NOT modified.
export function CLDGroupDeliveryControls({ projectId, sourceName, items, onChanged }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const eligible = items.filter(item => item.is_active !== false &&
    item.production_status === 'completed' && item.qc_status === 'passed' &&
    item.qa_status === 'passed' && item.ready_for_delivery !== true &&
    item.delivery_status !== 'delivered')
  const count = eligible.length
  // Final delivery is separate from readiness; count only files with QA passed,
  // explicit readiness confirmed, and no prior delivery.
  const deliverable = items.filter(item => item.is_active !== false &&
    item.production_status === 'completed' && item.qc_status === 'passed' &&
    item.qa_status === 'passed' && item.ready_for_delivery === true &&
    item.delivery_status !== 'delivered')
  const deliveryCount = deliverable.length

  async function markAllReady() {
    if (!count || busy) return
    if (!window.confirm(`Confirm Ready for Delivery for all ${count} QA-passed file(s) in this CLD source? This does not mark files Delivered.`)) return
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await apiFetch<{ count: number }>(
        `/operations/workflow/ortho/projects/${projectId}/cld-ready-for-delivery`,
        { method: 'POST', body: JSON.stringify({ item_ids: eligible.map(item => item.work_package_item_id) }) },
      )
      setNotice(`${result.count} MARCENA file(s) marked Ready for Delivery. The Project Manager was notified.`)
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to mark CLD files Ready for Delivery')
    } finally { setBusy(false) }
  }

  async function markAllDelivered() {
    if (!deliveryCount || busy) return
    if (!window.confirm(`Mark all ${deliveryCount} ready-confirmed file(s) Delivered for this CLD source? This records FINAL delivery.`)) return
    const remarks = window.prompt('Final delivery remarks / reference (optional):', '')
    if (remarks === null) return
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await apiFetch<{ count: number }>(
        `/operations/workflow/ortho/projects/${projectId}/cld-deliver`,
        { method: 'POST', body: JSON.stringify({
          item_ids: deliverable.map(item => item.work_package_item_id), remarks: remarks || null,
        }) },
      )
      setNotice(`${result.count} MARCENA file(s) marked Delivered.`)
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to mark CLD files Delivered')
    } finally { setBusy(false) }
  }

  return <section className="cld-block-review" aria-label="Team Lead CLD bulk Ready for Delivery">
    <div className="cld-block-heading">
      <span className="operations-kicker">TEAM LEAD / PM · CLD IMPORT</span>
      <h3>CENTRELINE_M — {items.length} MARCENA files</h3>
      <small>Source: {sourceName} · {count} QA-passed file(s) waiting for confirmation</small>
    </div>
    <div className="assignment-review-buttons">
      <button type="button" className="operations-button success" disabled={busy || count === 0}
        onClick={() => void markAllReady()}>
        {busy ? 'Confirming…' : `Mark All ${count} Ready for Delivery`}
      </button>
      <button type="button" className="operations-button success" disabled={busy || deliveryCount === 0}
        onClick={() => void markAllDelivered()}>
        {busy ? 'Delivering…' : `Mark All ${deliveryCount} Delivered`}
      </button>
      <small className="cld-review-note">Ready confirmation and final delivery are separate steps. Individual delivery buttons below remain unchanged.</small>
    </div>
    {error && <div className="operations-alert error" role="alert">{error}</div>}
    {notice && <div className="operations-alert success" role="status">{notice}</div>}
  </section>
}
