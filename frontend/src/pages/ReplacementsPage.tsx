import { CalendarDays, Mail, Repeat2, Save, Settings2, ShieldCheck, ShoppingCart } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import { DashboardHeader } from '../components/DashboardHeader'
import { useAuth } from '../context/AuthContext'
import { useITMonthUrl } from '../context/ITMonthContext'
import { apiFetch } from '../lib/api'
import { monthLabel } from '../lib/itMonth'
import type { Asset, ReplacementRecord } from '../types'

function workflowLabel(record: ReplacementRecord) {
  if (record.final_action === 'replace_with_spare') return 'Completed · Spare Used'
  if (record.final_action === 'procurement_required') return 'Awaiting Purchase Approval'
  if (record.final_action === 'procurement_completed_replacement') return 'Completed · Procured Asset'
  if (record.approval_status === 'pending' || record.approval_status === 'returned') return 'Legacy · IT Processing Required'
  if (record.approval_status === 'rejected') return 'Legacy · Rejected'
  return record.final_action.replaceAll('_', ' ')
}

export function ReplacementsPage() {
  const { user } = useAuth()
  const { selectedMonth } = useITMonthUrl()
  const canOperate = user?.role === 'it' || user?.role === 'admin'
  const [assets, setAssets] = useState<Asset[]>([])
  const [records, setRecords] = useState<ReplacementRecord[]>([])
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [form, setForm] = useState({
    old_asset_id: '',
    new_asset_id: '',
    reason: '',
    damage_category: 'technical_failure',
    inspection_finding: '',
    final_action: 'replacement_pending',
    approval_recipient_name: '',
    approval_recipient_email: '',
  })

  async function load() {
    try {
      const [assetData, replacementData] = await Promise.all([
        apiFetch<Asset[]>('/assets?limit=1000'),
        apiFetch<ReplacementRecord[]>('/replacements'),
      ])
      setAssets(assetData)
      setRecords(replacementData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load replacement workflow')
    }
  }

  useEffect(() => { void load() }, [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    setMessage('')
    setError('')
    setBusy('create')
    try {
      const created = await apiFetch<ReplacementRecord>('/replacements', {
        method: 'POST',
        body: JSON.stringify({
          reporting_month: selectedMonth,
          old_asset_id: Number(form.old_asset_id),
          new_asset_id: form.new_asset_id ? Number(form.new_asset_id) : null,
          reason: form.reason,
          damage_category: form.damage_category,
          inspection_finding: form.inspection_finding || null,
          final_action: 'replacement_pending',
          approval_recipient_name: form.approval_recipient_name,
          approval_recipient_email: form.approval_recipient_email,
        }),
      })
      setMessage(created.final_action === 'procurement_required'
        ? `${created.replacement_code} processed by IT. No suitable spare was available, so a Purchase Request and secure approval email were created.`
        : `${created.replacement_code} processed by IT. An available spare was used; no Management approval or approval email was required.`)
      setForm(current => ({ ...current, old_asset_id: '', new_asset_id: '', reason: '', inspection_finding: '' }))
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to process replacement')
    } finally {
      setBusy('')
    }
  }

  async function processLegacy(record: ReplacementRecord) {
    setBusy(`legacy-${record.id}`)
    setError('')
    setMessage('')
    try {
      const updated = await apiFetch<ReplacementRecord>(`/replacements/${record.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          new_asset_id: null,
          remarks: 'Migrated to final Batch 4 IT-controlled replacement workflow',
          approval_recipient_name: form.approval_recipient_name,
          approval_recipient_email: form.approval_recipient_email,
        }),
      })
      setMessage(updated.final_action === 'procurement_required'
        ? `${record.replacement_code} migrated. A Purchase Request and approval email are now waiting for the selected approver.`
        : `${record.replacement_code} migrated and completed using an available spare.`)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to process legacy replacement')
    } finally {
      setBusy('')
    }
  }

  const availableAssets = assets.filter(asset => asset.status === 'available' && !asset.used_by)
  const selectedOldAsset = assets.find(asset => asset.id === Number(form.old_asset_id))
  const compatibleAvailableAssets = availableAssets.filter(asset => !selectedOldAsset || asset.device_type === selectedOldAsset.device_type)

  return (
    <>
      <DashboardHeader
        eyebrow="ASSET LIFECYCLE"
        title="Complete Asset Replacement"
        description={`IT controls the technical replacement workflow for ${monthLabel(selectedMonth)}. Available spare stock is used first. Management permission is required only when a Purchase Request is created.`}
        meta={<>
          <span className="nk-meta-chip"><CalendarDays size={14} /> Reporting month {monthLabel(selectedMonth)}</span>
          <span className="nk-meta-chip"><Repeat2 size={14} /> Spare stock first → purchase only when required</span>
          <span className="nk-meta-chip"><ShieldCheck size={14} /> Management approves Purchase Requests only</span>
        </>}
      />
      {message && <div className="success-message">{message}</div>}
      {error && <div className="error-message">{error}</div>}

      {user?.role === 'management' && (
        <div className="approval-note">
          <ShieldCheck size={16} /> Management view is read-only here. Replacement decisions belong to IT; Management approves only Purchase Requests when procurement is required.
        </div>
      )}

      <section className="dashboard-grid replacement-layout">
        {canOperate && <article className="panel">
          <div className="panel-heading"><div><span className="section-kicker">IT TECHNICAL CONTROL · {monthLabel(selectedMonth).toUpperCase()}</span><h2>Process Replacement</h2></div><Repeat2 /></div>
          <form className="data-form" onSubmit={submit}>
            <label>Old / Failed Asset<select required value={form.old_asset_id} onChange={event => setForm({ ...form, old_asset_id: event.target.value, new_asset_id: '' })}><option value="">Select by CPU tag and workstation</option>{assets.filter(asset => !['disposed', 'replaced', 'retired'].includes(asset.status)).map(asset => <option key={asset.id} value={asset.id}>{asset.cpu_asset_tag || 'No physical tag'} · {asset.workstation_no || 'No workstation'} · {asset.used_by || 'Unassigned'} · Internal {asset.asset_code}</option>)}</select></label>
            <label>Preferred Available Spare (optional)<select value={form.new_asset_id} onChange={event => setForm({ ...form, new_asset_id: event.target.value })}><option value="">Automatic: use compatible Available spare first</option>{compatibleAvailableAssets.map(asset => <option key={asset.id} value={asset.id}>{asset.cpu_asset_tag || 'No physical tag'} · {asset.device_type} · {asset.model || asset.processor || 'Specification not recorded'} · Internal {asset.asset_code}</option>)}</select></label>
            <div className="approval-note">If no compatible Available spare exists, the system automatically creates one Purchase Request. That Purchase Request — not the technical replacement — goes to Management for permission.</div>
            <label>Approval Recipient Name<input required value={form.approval_recipient_name} onChange={event => setForm({ ...form, approval_recipient_name: event.target.value })} placeholder="Manager / UAT approver name" /></label>
            <label>Approval Email<input required type="email" value={form.approval_recipient_email} onChange={event => setForm({ ...form, approval_recipient_email: event.target.value })} placeholder="approver@nakshatech.com" /></label>
            <div className="approval-note"><Mail size={15} /> This recipient is used only if procurement is required. If IT uses an Available spare, no purchase approval email is sent.</div>
            <label>Damage Category<select value={form.damage_category} onChange={event => setForm({ ...form, damage_category: event.target.value })}><option value="normal_wear_and_tear">Normal wear and tear</option><option value="technical_failure">Technical failure</option><option value="accidental_damage">Accidental damage</option><option value="user_negligence">User negligence / improper usage</option><option value="lost">Lost</option><option value="stolen">Stolen</option><option value="unknown">Unknown</option></select></label>
            <label>Reason<textarea required rows={3} value={form.reason} onChange={event => setForm({ ...form, reason: event.target.value })} placeholder="Describe why the asset must be replaced" /></label>
            <label>IT Inspection Finding<textarea rows={3} value={form.inspection_finding} onChange={event => setForm({ ...form, inspection_finding: event.target.value })} placeholder="Example: motherboard failed; not economically repairable" /></label>
            <button className="primary-button" disabled={busy === 'create'}><Save size={17} /> {busy === 'create' ? 'Processing…' : 'Process Replacement'}</button>
          </form>
        </article>}

        <article className={`panel ${!canOperate ? 'full-span-panel' : ''}`}>
          <div className="panel-heading"><div><span className="section-kicker">READ-ONLY HISTORY</span><h2>Replacement Records</h2></div><span className="count-chip">{records.length}</span></div>
          <div className="replacement-workflow-list">
            {records.map(record => {
              const oldAsset = assets.find(asset => asset.id === record.old_asset_id)
              const newAsset = assets.find(asset => asset.id === record.new_asset_id)
              const legacyNeedsProcessing = canOperate && ['pending', 'returned'].includes(record.approval_status) && !['procurement_required', 'replace_with_spare', 'procurement_completed_replacement'].includes(record.final_action)
              return <article key={record.id}>
                <div className="record-top">
                  <div><strong>{record.replacement_code}</strong><span>Effective: {monthLabel(record.reporting_month || selectedMonth)} · Recorded: {new Date(record.created_at).toLocaleString()}</span></div>
                  <span className={`status ${record.final_action}`}>{workflowLabel(record)}</span>
                </div>
                <div className="replacement-link">
                  <span>{oldAsset?.cpu_asset_tag || record.old_asset_code}<small>{oldAsset?.workstation_no || 'No workstation'} · Internal {record.old_asset_code}</small></span>
                  <i>replacement</i>
                  <span>{newAsset?.cpu_asset_tag || record.new_asset_code || (record.final_action === 'procurement_required' ? 'Purchase pending' : 'Not assigned')}<small>{record.new_asset_code ? `Internal ${record.new_asset_code}` : 'Spare / procurement outcome'}</small></span>
                </div>
                <p>{record.reason}</p>
                <small>{record.damage_category.replaceAll('_', ' ')} · {record.final_action.replaceAll('_', ' ')}</small>
                {record.inspection_finding && <blockquote>{record.inspection_finding}</blockquote>}
                {record.decision_remarks && <div className="approval-note">{record.decision_remarks}</div>}
                {record.final_action === 'procurement_required' && <div className="approval-note"><ShoppingCart size={15} /> Purchase permission is waiting with Management and the selected approval email recipient. IT cannot procure until that Purchase Request is approved.</div>}
                {legacyNeedsProcessing && <button className="secondary-button" disabled={busy === `legacy-${record.id}`} onClick={() => void processLegacy(record)}><Settings2 size={15} /> {busy === `legacy-${record.id}` ? 'Processing…' : 'Process Legacy Record Under IT Control'}</button>}
              </article>
            })}
            {!records.length && <div className="empty-state">No replacement records yet.</div>}
          </div>
        </article>
      </section>
    </>
  )
}
