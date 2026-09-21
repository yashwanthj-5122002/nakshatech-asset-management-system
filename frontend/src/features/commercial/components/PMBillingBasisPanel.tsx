import { ClipboardCheck, Send } from 'lucide-react'
import { useEffect, useState } from 'react'
import { apiFetch } from '../../../lib/api'
import type { PMBillingBasisView } from '../types'
import { UNIT_RATE_TYPES } from '../types'
import '../../operations/operations.css'
import '../commercial-workflow.css'

type Draft = { quantity: string; unit: string; milestone_id: string; completion_percent: string; accepted: boolean; reference: string; remarks: string; readiness: string }
const blank = (): Draft => ({ quantity: '', unit: '', milestone_id: '', completion_percent: '', accepted: false, reference: '', remarks: '', readiness: '' })

/**
 * PROJECT MANAGER · BILLING BASIS. The PM confirms what was actually delivered / achieved (quantity, milestone,
 * completion, acceptance). No rate, contract value, FX or margin is ever shown here: Finance combines these
 * operational facts with the approved commercial basis and raises the invoice.
 */
export function PMBillingBasisPanel({ projectId, projectCode }: { projectId: number; projectCode: string }) {
  const [view, setView] = useState<PMBillingBasisView | null>(null)
  const [hidden, setHidden] = useState(false)
  const [draft, setDraft] = useState<Draft>(blank)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  function load() {
    setHidden(false)
    void apiFetch<PMBillingBasisView>(`/commercial/projects/${projectId}/pm-billing-basis`)
      .then(data => { setView(data); setDraft(current => ({ ...current, unit: current.unit || data.quantity_unit || '' })) })
      .catch(() => setHidden(true))   // not this project's PM (or not permitted): the panel simply does not exist for them
  }
  useEffect(() => { setView(null); setDraft(blank()); setError(''); setNotice(''); load() }, [projectId])

  if (hidden || !view) return null
  const type = view.billing_type
  const quantityBased = type != null && (UNIT_RATE_TYPES.has(type) || type === 'time_material')
  const ref = view.operational_reference
  const unit = view.quantity_unit || draft.unit
  const areaMatchesUnit = ref.area_unit != null && unit !== '' && ref.area_unit.toLowerCase() === unit.toLowerCase() && ref.delivered_area != null

  async function submit() {
    setBusy(true); setError(''); setNotice('')
    try {
      await apiFetch(`/commercial/projects/${projectId}/pm-billing-basis`, {
        method: 'POST',
        body: JSON.stringify({
          cumulative_billable_quantity: draft.quantity.trim() === '' ? null : Number(draft.quantity),
          quantity_unit: unit || null,
          milestone_id: draft.milestone_id ? Number(draft.milestone_id) : null,
          completion_percent: draft.completion_percent.trim() === '' ? null : Number(draft.completion_percent),
          delivery_accepted: draft.accepted,
          acceptance_reference: draft.reference.trim() || null,
          pm_remarks: draft.remarks.trim() || null,
          billing_readiness_date: draft.readiness || null,
        }),
      })
      setNotice('Billing basis confirmed. Finance has been notified and will prepare the invoice.')
      setDraft({ ...blank(), unit: view?.quantity_unit || '' })
      load()
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to record the billing basis') }
    finally { setBusy(false) }
  }

  return <section className="operations-panel">
    <header><div><span className="operations-kicker">PROJECT MANAGER · BILLING BASIS · {projectCode}</span><h2><ClipboardCheck size={16} /> What is billable?</h2>
      <p>Confirm the operational facts Finance needs to invoice: {view.billing_type_label ? <b>{view.billing_type_label}</b> : 'billable work'}. You do not see or set rates, contract value or FX — Finance and BD own those.</p></div></header>
    {error && <div className="operations-alert error">{error}</div>}
    {notice && <div className="operations-alert success">{notice}</div>}

    <div className="cw-summary-grid">
      <div className="cw-fact"><span>Work packages delivered</span><strong>{ref.work_packages_delivered} / {ref.work_packages_total}</strong><small>{ref.completion_percent_by_packages == null ? 'No packages yet' : `${ref.completion_percent_by_packages}% by package count`}</small></div>
      {ref.delivered_area != null && <div className="cw-fact"><span>Delivered area (work packages)</span><strong>{ref.delivered_area} {ref.area_unit || ''}</strong><small>of {ref.total_area} {ref.area_unit || ''} allocated</small></div>}
      {ref.planned_quantity != null && <div className="cw-fact"><span>Planned quantity</span><strong>{ref.planned_quantity} {ref.planned_quantity_unit || ''}</strong></div>}
      {ref.completion_date && <div className="cw-fact"><span>Operational completion</span><strong>{ref.completion_date}</strong></div>}
    </div>

    {!view.can_submit && <div className="operations-note">{view.cannot_submit_reason || 'Billing basis cannot be recorded right now.'}</div>}
    {view.can_submit && <div className="operations-form-grid" style={{ marginTop: 12 }}>
      {quantityBased && <>
        <label className="operations-field"><span>Accepted billable quantity, cumulative to date ({unit || 'unit'}) *</span><input type="number" min="0" step="0.001" value={draft.quantity} onChange={e => setDraft({ ...draft, quantity: e.target.value })} /></label>
        <div className="operations-field cw-inline-action"><span>&nbsp;</span>{areaMatchesUnit ? <button type="button" className="operations-button secondary" onClick={() => setDraft({ ...draft, quantity: String(ref.delivered_area) })}>Use delivered area ({ref.delivered_area} {ref.area_unit})</button> : <small className="cw-muted">Enter the quantity the client has accepted.</small>}</div>
      </>}
      {type === 'milestone' && <label className="operations-field operations-span-2"><span>Milestone achieved *</span><select value={draft.milestone_id} onChange={e => setDraft({ ...draft, milestone_id: e.target.value, accepted: e.target.value ? true : draft.accepted })}><option value="">Select milestone</option>{view.milestones.map(m => <option key={m.id} value={m.id}>{m.sequence}. {m.name}</option>)}</select></label>}
      {type === 'fixed_price' && <label className="operations-field"><span>Completion % (or tick delivery accepted)</span><input type="number" min="0" max="100" step="0.01" value={draft.completion_percent} onChange={e => setDraft({ ...draft, completion_percent: e.target.value })} /></label>}
      {!quantityBased && type !== 'milestone' && type !== 'fixed_price' && <>
        <label className="operations-field"><span>Billable quantity (optional)</span><input type="number" min="0" step="0.001" value={draft.quantity} onChange={e => setDraft({ ...draft, quantity: e.target.value })} /></label>
        <label className="operations-field"><span>Unit</span><input value={draft.unit} onChange={e => setDraft({ ...draft, unit: e.target.value })} placeholder="e.g. sites" /></label>
      </>}
      <label className="operations-check operations-span-2"><input type="checkbox" checked={draft.accepted} onChange={e => setDraft({ ...draft, accepted: e.target.checked })} /><span>Delivery / milestone accepted by the client</span></label>
      <label className="operations-field"><span>Acceptance / reference</span><input value={draft.reference} onChange={e => setDraft({ ...draft, reference: e.target.value })} placeholder="e.g. client e-mail date, sign-off ID" /></label>
      <label className="operations-field"><span>Billing readiness date</span><input type="date" value={draft.readiness} onChange={e => setDraft({ ...draft, readiness: e.target.value })} /></label>
      <label className="operations-field operations-span-2"><span>Remarks for Finance</span><textarea value={draft.remarks} onChange={e => setDraft({ ...draft, remarks: e.target.value })} rows={2} /></label>
      <div className="operations-actions operations-span-2"><button className="operations-button" disabled={busy} onClick={() => void submit()}><Send size={15} /> Confirm Billing Basis</button></div>
    </div>}

    {!!view.entries.length && <div className="operations-table-wrap" style={{ marginTop: 12 }}><table className="operations-table"><thead><tr><th>#</th><th>Confirmed</th><th>Basis</th><th>Accepted</th><th>Reference / remarks</th></tr></thead>
      <tbody>{view.entries.map(row => <tr key={row.id}><td>{row.entry_no}</td><td>{new Date(row.confirmed_at).toLocaleString('en-IN')}<small>{row.confirmed_by_name}</small></td>
        <td>{row.milestone_name ? `Milestone: ${row.milestone_name}` : row.cumulative_billable_quantity != null ? `${row.cumulative_billable_quantity} ${row.quantity_unit || ''}` : row.completion_percent != null ? `${row.completion_percent}% complete` : '—'}</td>
        <td>{row.delivery_accepted ? 'Yes' : 'No'}</td><td>{row.acceptance_reference || '—'}{row.pm_remarks && <small>{row.pm_remarks}</small>}</td></tr>)}</tbody></table></div>}
  </section>
}
