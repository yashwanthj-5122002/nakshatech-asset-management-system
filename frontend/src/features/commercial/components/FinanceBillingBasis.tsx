import { Calculator, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { apiFetch } from '../../../lib/api'
import type { BillingRecommendation } from '../types'
import { money, statusLabel } from '../types'
import '../../operations/operations.css'
import '../commercial-workflow.css'

export type InvoiceLinks = { estimate_revision_id: number | null; billing_basis_id: number | null; billed_quantity: number | null; billed_milestone_id: number | null }
export type RecommendationApply = {
  currency: string
  amount: string
  tax_percent: string
  tax_amount: string
  payment_terms: string
  po_wo_reference: string
  links: InvoiceLinks
}

const fact = (label: string, value: React.ReactNode, sub?: React.ReactNode, wide = false) =>
  <div className={`cw-fact${wide ? ' wide' : ''}`}><span>{label}</span><strong>{value}</strong>{sub ? <small>{sub}</small> : null}</div>

/**
 * Finance Billing: APPROVED COMMERCIAL BASIS + PM BILLING BASIS + a recommended taxable amount.
 * The recommendation only pre-fills the invoice form. Finance reviews tax, dates, PO and evidence and explicitly
 * creates and raises the invoice; nothing here raises an invoice automatically.
 */
export function FinanceBillingBasis({ projectId, refreshKey = 0, onUse }: { projectId: number; refreshKey?: number; onUse: (apply: RecommendationApply) => void }) {
  const [data, setData] = useState<BillingRecommendation | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let cancelled = false
    setData(null); setError('')
    void apiFetch<BillingRecommendation>(`/commercial/projects/${projectId}/billing-recommendation`)
      .then(result => { if (!cancelled) setData(result) })
      .catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : 'Unable to load the billing basis') })
    return () => { cancelled = true }
  }, [projectId, refreshKey])

  if (error) return <div className="operations-alert error">{error}</div>
  if (!data) return <div className="cw-muted">Loading billing basis…</div>
  const basis = data.commercial_basis
  const pm = data.pm_basis
  const rec = data.recommendation
  const ref = data.operational_reference
  const foreign = basis != null && basis.currency_code !== 'INR'

  return <div style={{ display: 'grid', gap: 14 }}>
    <div>
      <span className="operations-kicker">APPROVED COMMERCIAL BASIS</span>
      {!basis ? <div className="operations-note" style={{ marginTop: 6 }}>No Finance-approved commercial revision (legacy project). Enter the invoice manually.</div> : <div className="cw-summary-grid" style={{ marginTop: 6 }}>
        {fact('Revision', `R${basis.revision_no} · ${statusLabel(basis.status)}`, basis.is_baseline ? 'Approved baseline (locked)' : 'Approved revision')}
        {fact('Billing type', basis.billing_type_label || statusLabel(basis.billing_type))}
        {fact('Approved value', money(basis.taxable_base_amount, basis.currency_code), `${basis.tax_percent}% tax → gross ${money(basis.expected_gross, basis.currency_code)}`)}
        {fact('Approved INR equivalent', money(basis.base_inr), foreign ? `1 ${basis.currency_code} = ₹${basis.fx_rate_to_inr.toLocaleString('en-IN', { maximumFractionDigits: 8 })} · ${basis.fx_rate_date} · ${basis.fx_rate_source}` : 'INR contract')}
        {basis.unit_rate != null && fact('Approved rate', `${money(basis.unit_rate, basis.currency_code)} / ${basis.quantity_unit || 'unit'}`, basis.estimated_quantity != null ? `Estimated scope ${basis.estimated_quantity} ${basis.quantity_unit || ''}` : undefined)}
        {!!basis.milestones?.length && fact('Milestones', basis.milestones.map(m => `${m.sequence}. ${m.milestone_name}${m.percent != null ? ` (${m.percent}%)` : ''}`).join(' · '), undefined, true)}
        {fact('PO / WO', basis.po_wo_reference || '—')}
        {fact('Payment terms', basis.payment_terms || '—', undefined, true)}
      </div>}
    </div>

    <div>
      <span className="operations-kicker">PM BILLING BASIS (operational facts)</span>
      {!pm ? <div className="operations-note" style={{ marginTop: 6 }}>The Project Manager has not confirmed a billing basis yet.</div> : <div className="cw-summary-grid" style={{ marginTop: 6 }}>
        {pm.cumulative_billable_quantity != null && fact('Accepted billable quantity', `${pm.cumulative_billable_quantity} ${pm.quantity_unit || ''}`, `Entry #${pm.entry_no}`)}
        {pm.milestone_name && fact('Milestone achieved', pm.milestone_name)}
        {pm.completion_percent != null && fact('Completion', `${pm.completion_percent}%`)}
        {fact('Delivery accepted', pm.delivery_accepted ? 'Yes' : 'No', pm.acceptance_reference || undefined)}
        {fact('Billing readiness date', pm.billing_readiness_date || '—')}
        {fact('Confirmed by', pm.confirmed_by_name || '—', new Date(pm.confirmed_at).toLocaleString('en-IN'))}
        {pm.pm_remarks && fact('PM remarks', pm.pm_remarks, undefined, true)}
      </div>}
      <small className="cw-muted">Work packages delivered: {ref.work_packages_delivered}/{ref.work_packages_total}{ref.delivered_area != null ? ` · delivered area ${ref.delivered_area} ${ref.area_unit || ''}` : ''}</small>
    </div>

    <div className="cw-recommend">
      <span className="operations-kicker"><Calculator size={12} /> RECOMMENDED INVOICE (advisory)</span>
      {rec ? <>
        <div className="cw-big">{money(rec.base_amount, rec.currency_code)} <small style={{ fontSize: 13, fontWeight: 600, color: '#55697d' }}>taxable · {rec.tax_percent}% tax = {money(rec.tax_amount, rec.currency_code)} · gross {money(rec.gross_amount, rec.currency_code)}</small></div>
        <div className="cw-muted">Basis: {rec.formula}</div>
        {rec.other_confirmed_milestones && rec.other_confirmed_milestones.length > 0 && <div className="cw-muted">Also confirmed and waiting: {rec.other_confirmed_milestones.map(m => m.name).join(', ')}</div>}
        <div className="operations-actions"><button type="button" className="operations-button" onClick={() => onUse({
          currency: rec.currency_code,
          amount: String(rec.base_amount),
          tax_percent: String(rec.tax_percent),
          tax_amount: String(rec.tax_amount),
          payment_terms: basis?.payment_terms || '',
          po_wo_reference: basis?.po_wo_reference || '',
          links: {
            estimate_revision_id: rec.estimate_revision_id,
            billing_basis_id: rec.billing_basis_id,
            billed_quantity: rec.method === 'UNIT_RATE' && rec.quantity != null ? rec.quantity : null,
            billed_milestone_id: rec.method === 'MILESTONE' && rec.milestone_id != null ? rec.milestone_id : null,
          },
        })}>Use these values in the invoice form</button></div>
        <small className="cw-muted"><ShieldCheck size={12} /> Nothing is raised automatically. Verify tax, invoice date, PO and billing evidence, then create and raise the invoice yourself.</small>
      </> : <div className="cw-muted">No amount can be recommended yet.</div>}
      {data.warnings.length > 0 && <ul className="cw-warning-list">{data.warnings.map(w => <li key={w}>{w}</li>)}</ul>}
      {data.invoiced_to_date.invoice_count > 0 && <small className="cw-muted">Already invoiced/drafted: {data.invoiced_to_date.invoice_count} invoice(s){data.invoiced_to_date.quantity > 0 ? ` · ${data.invoiced_to_date.quantity} ${basis?.quantity_unit || ''} billed` : ''}</small>}
    </div>
  </div>
}
