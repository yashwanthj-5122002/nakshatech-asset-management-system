import { Check, Repeat2, Save, XCircle } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import { DashboardHeader } from '../components/DashboardHeader'
import { useAuth } from '../context/AuthContext'
import { apiFetch } from '../lib/api'
import type { Asset, ReplacementRecord } from '../types'

export function ReplacementsPage() {
  const { user } = useAuth()
  const [assets, setAssets] = useState<Asset[]>([])
  const [records, setRecords] = useState<ReplacementRecord[]>([])
  const [message, setMessage] = useState('')
  const [replacementSelections, setReplacementSelections] = useState<Record<number, string>>({})
  const [error, setError] = useState('')
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
      const created = await apiFetch<ReplacementRecord>('/replacements', { method: 'POST', body: JSON.stringify({ ...form, old_asset_id: Number(form.old_asset_id), new_asset_id: form.new_asset_id ? Number(form.new_asset_id) : null }) })
      setMessage(`${created.replacement_code} created and sent for approval.`); setForm({ ...form, old_asset_id: '', new_asset_id: '', reason: '', inspection_finding: '' }); await load()
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to create replacement request') }
  }

  async function decide(record: ReplacementRecord, approval_status: string) {
    try {
      const selectedAssetId = replacementSelections[record.id] || (record.new_asset_id ? String(record.new_asset_id) : '')
      if (approval_status === 'approved' && !selectedAssetId) {
        setError('Select an available replacement asset before approval.')
        return
      }
      await apiFetch(`/replacements/${record.id}`, { method: 'PATCH', body: JSON.stringify({ approval_status, new_asset_id: selectedAssetId ? Number(selectedAssetId) : null, final_action: approval_status === 'approved' ? 'replace_and_retire' : 'repair', remarks: `Decision by ${user?.full_name}` }) })
      setMessage(`${record.replacement_code} ${approval_status}.`); await load()
    } catch (err) { setError(err instanceof Error ? err.message : 'Approval failed') }
  }

  const availableAssets = assets.filter(asset => asset.status === 'available')
  return (
    <>
      <DashboardHeader eyebrow="ASSET LIFECYCLE" title="Complete CPU / Laptop Replacement" description="Identify systems by CPU / Physical Asset Tag and Workstation Number. Use this page only when the complete computer, laptop or major independent asset must be replaced." />
      {message && <div className="success-message">{message}</div>}{error && <div className="error-message">{error}</div>}
      <section className="dashboard-grid replacement-layout">
        {(user?.role === 'admin' || user?.role === 'it') && <article className="panel">
          <div className="panel-heading"><div><span className="section-kicker">NEW REQUEST</span><h2>Raise Replacement</h2></div><Repeat2 /></div>
          <form className="data-form" onSubmit={submit}>
            <label>Old / Failed CPU or Laptop<select required value={form.old_asset_id} onChange={e => setForm({ ...form, old_asset_id: e.target.value })}><option value="">Select by CPU tag and workstation</option>{assets.filter(asset => !['disposed', 'replaced'].includes(asset.status)).map(asset => <option key={asset.id} value={asset.id}>{asset.cpu_asset_tag || 'No physical tag'} · {asset.workstation_no || 'No workstation'} · {asset.used_by || 'Unassigned'} · Internal {asset.asset_code}</option>)}</select></label>
            <label>Available New CPU or Laptop (optional)<select value={form.new_asset_id} onChange={e => setForm({ ...form, new_asset_id: e.target.value })}><option value="">Assign after approval</option>{availableAssets.map(asset => <option key={asset.id} value={asset.id}>{asset.cpu_asset_tag || 'No physical tag'} · {asset.workstation_no || 'Unplaced'} · {asset.device_type} · {asset.processor || 'No processor'} · Internal {asset.asset_code}</option>)}</select></label>
            <label>Damage Category<select value={form.damage_category} onChange={e => setForm({ ...form, damage_category: e.target.value })}><option value="normal_wear_and_tear">Normal wear and tear</option><option value="technical_failure">Technical failure</option><option value="accidental_damage">Accidental damage</option><option value="user_negligence">User negligence / improper usage</option><option value="lost">Lost</option><option value="stolen">Stolen</option><option value="unknown">Unknown</option></select></label>
            <label>Recommended Final Action<select value={form.final_action} onChange={e => setForm({ ...form, final_action: e.target.value })}><option value="replacement_pending">Replacement pending</option><option value="repair">Repair instead</option><option value="for_parts">Recover components / for parts</option><option value="disposal_pending">Send for disposal</option></select></label>
            <label>Reason<textarea required rows={3} value={form.reason} onChange={e => setForm({ ...form, reason: e.target.value })} placeholder="Describe why the asset must be replaced" /></label>
            <label>IT Inspection Finding<textarea rows={3} value={form.inspection_finding} onChange={e => setForm({ ...form, inspection_finding: e.target.value })} placeholder="Example: motherboard failed; not economically repairable" /></label>
            <button className="primary-button"><Save size={17} /> Submit for Approval</button>
          </form>
        </article>}
        <article className={`panel ${user?.role === 'management' ? 'full-span-panel' : ''}`}>
          <div className="panel-heading"><div><span className="section-kicker">TRACEABLE HISTORY</span><h2>Replacement Records</h2></div><span className="count-chip">{records.length}</span></div>
          <div className="replacement-workflow-list">
            {records.map(record => { const oldAsset = assets.find(asset => asset.id === record.old_asset_id); const newAsset = assets.find(asset => asset.id === record.new_asset_id); return <article key={record.id}>
              <div className="record-top"><div><strong>{record.replacement_code}</strong><span>{new Date(record.created_at).toLocaleDateString()}</span></div><span className={`status ${record.approval_status}`}>{record.approval_status}</span></div>
              <div className="replacement-link"><span>{oldAsset?.cpu_asset_tag || record.old_asset_code}<small>{oldAsset?.workstation_no || 'No workstation'} · Internal {record.old_asset_code}</small></span><i>replaced by</i><span>{newAsset?.cpu_asset_tag || record.new_asset_code || 'Not assigned'}<small>{newAsset?.workstation_no || oldAsset?.workstation_no || 'Workstation pending'}{record.new_asset_code ? ` · Internal ${record.new_asset_code}` : ''}</small></span></div>
              <p>{record.reason}</p><small>{record.damage_category.replaceAll('_', ' ')} · {record.final_action.replaceAll('_', ' ')}</small>
              {record.inspection_finding && <blockquote>{record.inspection_finding}</blockquote>}
              {(user?.role === 'admin' || user?.role === 'management') && record.approval_status === 'pending' && <div className="approval-selection"><label>Replacement asset<select value={replacementSelections[record.id] || (record.new_asset_id ? String(record.new_asset_id) : '')} onChange={event => setReplacementSelections({ ...replacementSelections, [record.id]: event.target.value })}><option value="">Select available asset</option>{availableAssets.filter(asset => asset.id !== record.old_asset_id).map(asset => <option key={asset.id} value={asset.id}>{asset.cpu_asset_tag || 'No physical tag'} · {asset.workstation_no || 'Unplaced'} · {asset.device_type} · {asset.processor || 'Specification not recorded'} · Internal {asset.asset_code}</option>)}</select></label><div className="record-actions"><button className="primary-button" onClick={() => void decide(record, 'approved')}><Check size={15} /> Approve & Assign</button><button className="danger-button" onClick={() => void decide(record, 'rejected')}><XCircle size={15} /> Reject</button></div></div>}
            </article> })}
            {!records.length && <div className="empty-state">No replacement requests yet.</div>}
          </div>
        </article>
      </section>
    </>
  )
}
