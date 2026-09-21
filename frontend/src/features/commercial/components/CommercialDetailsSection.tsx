import { CircleDollarSign, Plus, RefreshCcw, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../../../lib/api'
import type { CommercialFormState } from '../commercial-form'
import type { CurrencyPayload } from '../types'
import { BILLING_TYPE_OPTIONS, DEFAULT_UNIT, UNIT_RATE_TYPES, money } from '../types'
import '../../operations/operations.css'
import '../commercial-workflow.css'

type FxPreview = { fx_rate_to_inr: number; fx_rate_date: string; fx_rate_source: string; fx_rate_mode: string; inr_equivalent: number }

/**
 * COMMERCIAL & BILLING DETAILS: the initial commercial terms (Revision 1) entered while BD creates or corrects
 * the project. BD enters the commercial COMMITMENT and PAYMENT TERMS only; actual payments received stay a
 * Finance action. Foreign-currency rates come from the backend FX service, never from the browser.
 */
export function CommercialDetailsSection({ form, onChange, currencies, disabled = false }: {
  form: CommercialFormState
  onChange: (next: CommercialFormState) => void
  currencies: CurrencyPayload | null
  disabled?: boolean
}) {
  const set = (patch: Partial<CommercialFormState>) => onChange({ ...form, ...patch })
  const foreign = form.currency_code !== 'INR'
  const unitBilling = UNIT_RATE_TYPES.has(form.billing_type) || form.billing_type === 'time_material'
  const [preview, setPreview] = useState<FxPreview | null>(null)
  const [fxError, setFxError] = useState('')
  const [fxBusy, setFxBusy] = useState(false)
  const [manualFx, setManualFx] = useState(false)

  const amount = Number(form.estimated_amount) || 0
  const base = form.taxable_base_amount.trim() ? Number(form.taxable_base_amount) : amount
  const tax = Math.round(base * (Number(form.tax_percent) || 0)) / 100
  const milestoneTotal = form.milestones.reduce((sum, m) => sum + (Number(m.percent) || 0), 0)
  const unitLabel = form.quantity_unit || DEFAULT_UNIT[form.billing_type] || 'unit'
  const currencyList = useMemo(() => currencies?.currencies ?? [{ code: 'INR', name: 'Indian Rupee' }], [currencies])

  useEffect(() => { setPreview(null); setFxError(''); if (!foreign) setManualFx(false) }, [form.currency_code, form.estimated_amount])

  async function checkRate() {
    if (!foreign || !(amount > 0)) return
    setFxBusy(true); setFxError(''); setPreview(null)
    try {
      setPreview(await apiFetch<FxPreview>('/commercial/fx/preview', {
        method: 'POST',
        body: JSON.stringify({ amount, currency_code: form.currency_code, event_date: new Date().toISOString().slice(0, 10) }),
      }))
    } catch (err) {
      setFxError(err instanceof Error ? err.message : 'Automatic exchange rate unavailable.')
      setManualFx(true)
    } finally { setFxBusy(false) }
  }

  function changeBillingType(value: string) {
    const patch: Partial<CommercialFormState> = { billing_type: value }
    if (DEFAULT_UNIT[value]) patch.quantity_unit = DEFAULT_UNIT[value]
    if (value === 'milestone' && !form.milestones.length) patch.milestones = [{ milestone_name: '', percent: '' }]
    set(patch)
  }

  return <fieldset className="cw-section" disabled={disabled}>
    <legend><CircleDollarSign size={15} /> COMMERCIAL &amp; BILLING DETAILS</legend>
    <p className="cw-hint">Enter the commercial commitment and the agreed <b>payment terms</b>. Actual payments received are recorded later by Finance. This becomes <b>Commercial Revision 1</b> and is submitted to Finance together with the project.</p>
    <div className="operations-form-grid">
      <label className="operations-field operations-span-2"><span>Scope / Commercial Basis *</span><textarea required value={form.scope_description} onChange={e => set({ scope_description: e.target.value })} placeholder="What is being sold: survey area, deliverables, assumptions" /></label>
      <label className="operations-field"><span>Billing Type *</span><select value={form.billing_type} onChange={e => changeBillingType(e.target.value)}>{BILLING_TYPE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select></label>
      <label className="operations-field"><span>Currency *</span><select value={form.currency_code} onChange={e => set({ currency_code: e.target.value, fx_rate_to_inr: e.target.value === 'INR' ? '' : form.fx_rate_to_inr })}>{currencyList.map(c => <option key={c.code} value={c.code}>{c.code} · {c.name}</option>)}</select></label>

      {unitBilling && <>
        <label className="operations-field"><span>Rate per {unitLabel} ({form.currency_code}){UNIT_RATE_TYPES.has(form.billing_type) ? ' *' : ''}</span><input type="number" min="0" step="0.0001" value={form.unit_rate} onChange={e => set({ unit_rate: e.target.value })} /></label>
        <label className="operations-field"><span>Estimated scope ({unitLabel})</span><input type="number" min="0" step="0.001" value={form.estimated_quantity} onChange={e => set({ estimated_quantity: e.target.value })} /></label>
        <label className="operations-field"><span>Unit</span><input value={form.quantity_unit} onChange={e => set({ quantity_unit: e.target.value })} placeholder={DEFAULT_UNIT[form.billing_type] || 'unit'} /></label>
        <div className="operations-field cw-inline-action"><span>&nbsp;</span><button type="button" className="operations-button secondary" disabled={!(Number(form.unit_rate) > 0 && Number(form.estimated_quantity) > 0)} onClick={() => {
          const total = Math.round(Number(form.unit_rate) * Number(form.estimated_quantity) * 100) / 100
          set({ estimated_amount: String(total), taxable_base_amount: String(total) })
        }}>Use rate × scope as contract amount</button></div>
      </>}

      <label className="operations-field"><span>Estimated Contract Amount ({form.currency_code}) *</span><input required type="number" min="0.01" step="0.01" value={form.estimated_amount} onChange={e => set({ estimated_amount: e.target.value })} /></label>
      <label className="operations-field"><span>Taxable / Base Amount</span><input type="number" min="0" step="0.01" value={form.taxable_base_amount} onChange={e => set({ taxable_base_amount: e.target.value })} placeholder="Defaults to the contract amount" /></label>
      <label className="operations-field"><span>Expected Tax %</span><input type="number" min="0" max="100" step="0.01" value={form.tax_percent} onChange={e => set({ tax_percent: e.target.value })} /></label>
      <div className="operations-field"><span>Expected tax / gross</span><div className="cw-readout">{money(tax, form.currency_code)} tax · {money(base + tax, form.currency_code)} gross</div></div>

      {form.billing_type === 'milestone' && <div className="operations-field operations-span-2 cw-milestones">
        <span>Billing milestones * <small>(percentage of the taxable base; total {milestoneTotal}%)</small></span>
        {form.milestones.map((m, index) => <div className="cw-milestone-row" key={index}>
          <input aria-label={`Milestone ${index + 1} name`} placeholder={`Milestone ${index + 1} (e.g. After survey completion)`} value={m.milestone_name} onChange={e => set({ milestones: form.milestones.map((row, i) => i === index ? { ...row, milestone_name: e.target.value } : row) })} />
          <input aria-label={`Milestone ${index + 1} percent`} type="number" min="0" max="100" step="0.01" placeholder="%" value={m.percent} onChange={e => set({ milestones: form.milestones.map((row, i) => i === index ? { ...row, percent: e.target.value } : row) })} />
          <button type="button" className="cw-icon-button" aria-label={`Remove milestone ${index + 1}`} onClick={() => set({ milestones: form.milestones.filter((_, i) => i !== index) })}><Trash2 size={14} /></button>
        </div>)}
        <button type="button" className="operations-button secondary" onClick={() => set({ milestones: [...form.milestones, { milestone_name: '', percent: '' }] })}><Plus size={14} /> Add milestone</button>
      </div>}

      <label className="operations-field operations-span-2"><span>Payment Terms *</span><input required value={form.payment_terms} onChange={e => set({ payment_terms: e.target.value })} placeholder="e.g. 30% advance · 40% after survey completion · 30% after final delivery" /></label>
      <label className="operations-field"><span>Expected Billing Milestone</span><input value={form.expected_billing_milestone} onChange={e => set({ expected_billing_milestone: e.target.value })} placeholder="e.g. On final delivery" /></label>
      <label className="operations-field"><span>Quotation Reference</span><input value={form.quotation_reference} onChange={e => set({ quotation_reference: e.target.value })} /></label>
      <label className="operations-field"><span>PO / WO Reference</span><input value={form.po_wo_reference} onChange={e => set({ po_wo_reference: e.target.value })} /></label>
      <label className="operations-field"><span>Estimated direct cost (INR, optional)</span><input type="number" min="0" step="0.01" value={form.estimated_direct_cost_inr} onChange={e => set({ estimated_direct_cost_inr: e.target.value })} /></label>
      <label className="operations-field operations-span-2"><span>Commercial Notes / Assumptions</span><textarea value={form.notes} onChange={e => set({ notes: e.target.value })} /></label>

      {foreign && <div className="cw-fx operations-span-2">
        <div className="cw-fx-head"><strong>Exchange rate to INR (accounting base currency)</strong>
          <button type="button" className="operations-button secondary" disabled={fxBusy || !(amount > 0)} onClick={() => void checkRate()}><RefreshCcw size={14} /> {fxBusy ? 'Checking…' : preview || fxError ? 'Retry' : 'Check rate'}</button></div>
        {!preview && !fxError && !manualFx && <small className="cw-muted">The rate is fetched automatically on the estimate date when the project is saved. Use “Check rate” to preview it.</small>}
        {preview && <div className="cw-fx-ok">1 {form.currency_code} = ₹{preview.fx_rate_to_inr.toLocaleString('en-IN', { maximumFractionDigits: 8 })} · {preview.fx_rate_date} · {preview.fx_rate_source} → <b>{money(preview.inr_equivalent)}</b> INR equivalent</div>}
        {fxError && <div className="cw-fx-warn"><b>Automatic exchange rate unavailable.</b> {fxError} <button type="button" className="cw-link" onClick={() => void checkRate()}>Retry</button> or <button type="button" className="cw-link" onClick={() => setManualFx(true)}>enter the rate manually</button>.</div>}
        {!manualFx && !fxError && <button type="button" className="cw-link" onClick={() => setManualFx(true)}>Enter a contract / agreed rate manually</button>}
        {manualFx && <div className="operations-form-grid">
          <label className="operations-field"><span>Rate: 1 {form.currency_code} = ₹</span><input type="number" min="0.00000001" step="0.00000001" value={form.fx_rate_to_inr} onChange={e => set({ fx_rate_to_inr: e.target.value })} /></label>
          <label className="operations-field"><span>Basis</span><select value={form.fx_rate_mode} onChange={e => set({ fx_rate_mode: e.target.value })}><option value="MANUAL_OVERRIDE">Manual override</option><option value="CONTRACT_RATE">Contract rate</option><option value="BANK_REALIZATION_RATE">Bank rate</option><option value="OTHER">Other</option></select></label>
          <label className="operations-field operations-span-2"><span>Reason for manual rate {form.fx_rate_to_inr ? '*' : ''}</span><input value={form.fx_override_reason} onChange={e => set({ fx_override_reason: e.target.value })} placeholder="e.g. rate fixed in the client contract" /></label>
          <div className="operations-actions"><button type="button" className="operations-button secondary" onClick={() => { set({ fx_rate_to_inr: '', fx_override_reason: '' }); setManualFx(false) }}>Use automatic rate</button></div>
        </div>}
      </div>}
    </div>
  </fieldset>
}
