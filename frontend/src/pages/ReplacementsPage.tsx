import { Check, PencilLine, Repeat2, RotateCcw, Save, XCircle } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import { DashboardHeader } from '../components/DashboardHeader'
import { useAuth } from '../context/AuthContext'
import { useITMonthUrl } from '../context/ITMonthContext'
import { apiFetch } from '../lib/api'
import { monthLabel } from '../lib/itMonth'
import type { Asset, ReplacementRecord } from '../types'

export function ReplacementsPage() {
  const { user } = useAuth()
  const { selectedMonth } = useITMonthUrl()
  const [assets, setAssets] = useState<Asset[]>([])
  const [records, setRecords] = useState<ReplacementRecord[]>([])
  const [message, setMessage] = useState('')
  const [replacementSelections, setReplacementSelections] = useState<Record<number, string>>({})
  const [error, setError] = useState('')
  const [decisionRemarks, setDecisionRemarks] = useState<Record<number, string>>({})
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState({ old_asset_id: '', new_asset_id: '', reason: '', damage_category: 'technical_failure', inspection_finding: '', final_action: 'replacement_pending' })

  async function load() {
    try {
      const [assetData, replacementData] = await Promise.all([apiFetch<Asset[]>('/assets?limit=1000'), apiFetch<ReplacementRecord[]>('/replacements')])
      setAssets(assetData); setRecords(replacementData)
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to load replacement workflow') }
  }
  useEffect(() => { void load() }, [])

  async function submit(event: FormEvent) {
    event.preventDefault(); setMessage(''); setError('')
    try {
      const commonPayload = {
        reporting_month: selectedMonth,
        new_asset_id: form.new_asset_id ? Number(form.new_asset_id) : null,
        reason: form.reason,
        damage_category: form.damage_category,
        inspection_finding: form.inspection_finding || null,
        final_action: form.final_action,
      }
      const created = editingId
        ? await apiFetch<ReplacementRecord>(`/replacements/${editingId}/resubmit`, { method: 'PUT', body: JSON.stringify(commonPayload) })
        : await apiFetch<ReplacementRecord>('/replacements', { method: 'POST', body: JSON.stringify({ ...commonPayload, old_asset_id: Number(form.old_asset_id) }) })
      setMessage(editingId
        ? `${created.replacement_code} corrected and resubmitted for Management approval.`
        : `${created.replacement_code} created and sent for Management approval.`)
      setEditingId(null)
      setForm({ ...form, old_asset_id: '', new_asset_id: '', reason: '', inspection_finding: '' })
      await load()
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to save replacement request') }
  }

  function editReturned(record: ReplacementRecord) {
    setEditingId(record.id)
    setForm({
      old_asset_id: String(record.old_asset_id),
      new_asset_id: record.new_asset_id ? String(record.new_asset_id) : '',
      reason: record.reason,
      damage_category: record.damage_category,
      inspection_finding: record.inspection_finding || '',
      final_action: record.final_action,
    })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function decide(record: ReplacementRecord, approval_status: 'approved' | 'rejected' | 'returned') {
    try {
      const selectedAssetId = replacementSelections[record.id] || (record.new_asset_id ? String(record.new_asset_id) : '')
      const remarks = (decisionRemarks[record.id] || '').trim()
      if (approval_status === 'approved' && !selectedAssetId) {
        setError('Select an available replacement asset before approval.')
        return
      }
      if ((approval_status === 'rejected' || approval_status === 'returned') && !remarks) {
        setError('Management remarks are required when rejecting or returning a replacement request.')
        return
      }
      await apiFetch(`/replacements/${record.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          approval_status,
          new_asset_id: selectedAssetId ? Number(selectedAssetId) : null,
          final_action: approval_status === 'approved' ? 'replace_and_retire' : record.final_action,
          remarks: remarks || null,
        }),
      })
      setDecisionRemarks(current => ({ ...current, [record.id]: '' }))
      setMessage(approval_status === 'approved'
        ? `${record.replacement_code} approved and assigned by Management.`
        : approval_status === 'returned'
          ? `${record.replacement_code} returned to IT for correction.`
          : `${record.replacement_code} rejected by Management.`)
      await load()
    } catch (err) { setError(err instanceof Error ? err.message : 'Management decision failed') }
  }

  const availableAssets = assets.filter(asset => asset.status === 'available')
  const selectedOldAsset = assets.find(asset => asset.id === Number(form.old_asset_id))
  const compatibleAvailableAssets = availableAssets.filter(asset => !selectedOldAsset || asset.device_type === selectedOldAsset.device_type)
  return (
    <>
      <DashboardHeader eyebrow="ASSET LIFECYCLE" title="Complete Asset Replacement" description={`Computer, laptop, smartphone and printer replacement requests created here are reported in ${monthLabel(selectedMonth)}. Approval keeps the request's original reporting month, while actual server timestamps remain unchanged.`} />
      {message && <div className="success-message">{message}</div>}{error && <div className="error-message">{error}</div>}
      <section className="dashboard-grid replacement-layout">
        {(user?.role === 'it' || user?.role === 'admin') && <article className="panel">
          <div className="panel-heading"><div><span className="section-kicker">NEW REQUEST · {monthLabel(selectedMonth).toUpperCase()}</span><h2>Raise Replacement</h2></div><Repeat2 /></div>
          <form className="data-form" onSubmit={submit}>
            <label>Old / Failed Asset<select required disabled={editingId !== null} value={form.old_asset_id} onChange={e => setForm({ ...form, old_asset_id: e.target.value, new_asset_id: '' })}><option value="">Select by CPU tag and workstation</option>{assets.filter(asset => !['disposed', 'replaced'].includes(asset.status)).map(asset => <option key={asset.id} value={asset.id}>{asset.cpu_asset_tag || 'No physical tag'} · {asset.workstation_no || 'No workstation'} · {asset.used_by || 'Unassigned'} · Internal {asset.asset_code}</option>)}</select></label>
            <label>Available Replacement Asset (same type, optional)<select value={form.new_asset_id} onChange={e => setForm({ ...form, new_asset_id: e.target.value })}><option value="">Assign after approval</option>{compatibleAvailableAssets.map(asset => <option key={asset.id} value={asset.id}>{asset.cpu_asset_tag || 'No physical tag'} · {asset.workstation_no || 'Unplaced'} · {asset.device_type} · {asset.device_type === 'Printer' ? (asset.model || 'No model') : (asset.processor || 'No processor')} · Internal {asset.asset_code}</option>)}</select></label>
            <label>Damage Category<select value={form.damage_category} onChange={e => setForm({ ...form, damage_category: e.target.value })}><option value="normal_wear_and_tear">Normal wear and tear</option><option value="technical_failure">Technical failure</option><option value="accidental_damage">Accidental damage</option><option value="user_negligence">User negligence / improper usage</option><option value="lost">Lost</option><option value="stolen">Stolen</option><option value="unknown">Unknown</option></select></label>
            <label>Recommended Final Action<select value={form.final_action} onChange={e => setForm({ ...form, final_action: e.target.value })}><option value="replacement_pending">Replacement pending</option><option value="repair">Repair instead</option><option value="for_parts">Recover components / for parts</option><option value="disposal_pending">Send for disposal</option></select></label>
            <label>Reason<textarea required rows={3} value={form.reason} onChange={e => setForm({ ...form, reason: e.target.value })} placeholder="Describe why the asset must be replaced" /></label>
            <label>IT Inspection Finding<textarea rows={3} value={form.inspection_finding} onChange={e => setForm({ ...form, inspection_finding: e.target.value })} placeholder="Example: motherboard failed; not economically repairable" /></label>
            <button className="primary-button"><Save size={17} /> {editingId ? 'Resubmit to Management' : 'Submit for Approval'}</button>
            {editingId && <button type="button" className="secondary-button" onClick={() => { setEditingId(null); setForm({ old_asset_id: '', new_asset_id: '', reason: '', damage_category: 'technical_failure', inspection_finding: '', final_action: 'replacement_pending' }) }}><XCircle size={17} /> Cancel Correction</button>}
          </form>
        </article>}
        <article className={`panel ${user?.role === 'management' ? 'full-span-panel' : ''}`}>
          <div className="panel-heading"><div><span className="section-kicker">TRACEABLE HISTORY</span><h2>Replacement Records</h2></div><span className="count-chip">{records.length}</span></div>
          <div className="replacement-workflow-list">
            {records.map(record => { const oldAsset = assets.find(asset => asset.id === record.old_asset_id); const newAsset = assets.find(asset => asset.id === record.new_asset_id); return <article key={record.id}>
              <div className="record-top"><div><strong>{record.replacement_code}</strong><span>Effective: {monthLabel(record.reporting_month || selectedMonth)} · Recorded: {new Date(record.created_at).toLocaleString()}</span></div><span className={`status ${record.approval_status}`}>{record.approval_status === 'pending' ? 'Pending · Management Approval' : record.approval_status.replaceAll('_', ' ')}</span></div>
              <div className="replacement-link"><span>{oldAsset?.cpu_asset_tag || record.old_asset_code}<small>{oldAsset?.workstation_no || 'No workstation'} · Internal {record.old_asset_code}</small></span><i>replaced by</i><span>{newAsset?.cpu_asset_tag || record.new_asset_code || 'Not assigned'}<small>{newAsset?.workstation_no || oldAsset?.workstation_no || 'Workstation pending'}{record.new_asset_code ? ` · Internal ${record.new_asset_code}` : ''}</small></span></div>
              <p>{record.reason}</p><small>{record.damage_category.replaceAll('_', ' ')} · {record.final_action.replaceAll('_', ' ')}</small>
              {record.inspection_finding && <blockquote>{record.inspection_finding}</blockquote>}
              {record.approval_status === 'pending' && user?.role === 'management' && <div className="approval-selection">
                <label>Replacement asset<select value={replacementSelections[record.id] || (record.new_asset_id ? String(record.new_asset_id) : '')} onChange={event => setReplacementSelections({ ...replacementSelections, [record.id]: event.target.value })}><option value="">Select available asset</option>{availableAssets.filter(asset => asset.id !== record.old_asset_id && (!oldAsset || asset.device_type === oldAsset.device_type)).map(asset => <option key={asset.id} value={asset.id}>{asset.cpu_asset_tag || 'No physical tag'} · {asset.workstation_no || 'Unplaced'} · {asset.device_type} · {asset.device_type === 'Printer' ? (asset.model || 'Model not recorded') : (asset.processor || 'Specification not recorded')} · Internal {asset.asset_code}</option>)}</select></label>
                <label>Management Remarks<textarea rows={2} value={decisionRemarks[record.id] || ''} onChange={event => setDecisionRemarks(current => ({ ...current, [record.id]: event.target.value }))} placeholder="Required when returning or rejecting" /></label>
                <div className="record-actions"><button className="primary-button" onClick={() => void decide(record, 'approved')}><Check size={15} /> Approve & Assign</button><button className="secondary-button" onClick={() => void decide(record, 'returned')}><RotateCcw size={15} /> Return to IT</button><button className="danger-button" onClick={() => void decide(record, 'rejected')}><XCircle size={15} /> Reject</button></div>
              </div>}
              {record.approval_status === 'pending' && user?.role !== 'management' && <div className="approval-note">Pending · Management Approval</div>}
              {record.approval_status === 'returned' && <div className="approval-selection"><div className="approval-note">Returned by Management{record.decision_remarks ? ` · ${record.decision_remarks}` : ''}</div>{(user?.role === 'it' || user?.role === 'admin') && <button className="secondary-button" onClick={() => editReturned(record)}><PencilLine size={15} /> Edit & Resubmit</button>}</div>}
              {record.approval_status === 'rejected' && record.decision_remarks && <div className="approval-note">Rejected · {record.decision_remarks}</div>}
              {record.approval_status === 'approved' && <div className="approval-note">Approved by {record.approved_by || 'Management'}</div>}
            </article> })}
            {!records.length && <div className="empty-state">No replacement requests yet.</div>}
          </div>
        </article>
      </section>
    </>
  )
}
