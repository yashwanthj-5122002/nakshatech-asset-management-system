import { useEffect, useState } from 'react'
import { apiFetch } from '../../../lib/api'
import type { CommercialEstimate } from '../types'
import { money, statusLabel } from '../types'
import { StoredDocumentsList } from './SupportingDocuments'
import '../commercial-workflow.css'

type Fallback = { currency?: string | null; commercial_value?: number | null; po_wo_number?: string | null }

const fact = (label: string, value: React.ReactNode, sub?: React.ReactNode, wide = false) =>
  <div className={`cw-fact${wide ? ' wide' : ''}`}><span>{label}</span><strong>{value}</strong>{sub ? <small>{sub}</small> : null}</div>

/**
 * COMMERCIAL SUMMARY shown inside the Finance project review. Finance approves the project and Commercial
 * Revision 1 together, so everything BD committed to must be readable here, not on another page.
 */
export function FinanceCommercialSummary({ projectId, fallback }: { projectId: number; fallback?: Fallback }) {
  const [rows, setRows] = useState<CommercialEstimate[] | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let cancelled = false
    setRows(null); setError('')
    void apiFetch<CommercialEstimate[]>(`/commercial/projects/${projectId}/estimates`)
      .then(data => { if (!cancelled) setRows(data) })
      .catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : 'Unable to load the commercial summary') })
    return () => { cancelled = true }
  }, [projectId])

  if (error) return <div className="operations-alert error">{error}</div>
  if (rows === null) return <div className="cw-muted">Loading commercial summary…</div>
  const rev = rows.find(row => row.revision_no === 1) ?? rows[rows.length - 1]
  if (!rev) {
    return <div className="cw-summary-grid">
      {fact('Commercial Estimate', 'Not available — legacy project', 'No Revision 1 was entered for this project.', true)}
      {fact('Original value', fallback?.commercial_value == null ? '—' : money(fallback.commercial_value, fallback.currency || 'INR'))}
      {fact('PO / WO', fallback?.po_wo_number || '—')}
    </div>
  }
  const foreign = rev.currency_code !== 'INR'
  const unitBased = rev.unit_rate != null
  const later = rows.filter(row => row.revision_no > 1)
  return <div style={{ display: 'grid', gap: 12 }}>
    <div className="cw-fact wide" style={{ display: 'flex', gap: 10, alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}>
      <span style={{ margin: 0 }}>Revision {rev.revision_no} · {rev.billing_type_label || statusLabel(rev.billing_type)}</span>
      {rev.is_locked ? <span className="cw-locked">Baseline locked · approved {rev.approved_at ? new Date(rev.approved_at).toLocaleDateString('en-IN') : ''}</span> : <span className="cw-pending">{statusLabel(rev.status)} — approved together with this project</span>}
    </div>
    <div className="cw-summary-grid">
      {fact('Scope / Commercial Basis', rev.scope_description, undefined, true)}
      {fact('Billing Type', rev.billing_type_label || statusLabel(rev.billing_type), unitBased ? `${money(rev.unit_rate, rev.currency_code)} per ${rev.quantity_unit || 'unit'}${rev.estimated_quantity != null ? ` × ${rev.estimated_quantity} ${rev.quantity_unit || ''}` : ''}` : undefined)}
      {fact('Original Currency', rev.currency_code)}
      {fact('Original Contract Amount', money(rev.estimated_amount, rev.currency_code))}
      {fact('Taxable / Base Amount', money(rev.taxable_base_amount, rev.currency_code), foreign ? `₹ ${rev.base_inr.toLocaleString('en-IN')}` : undefined)}
      {fact('Expected Tax', `${rev.tax_percent}% · ${money(rev.expected_tax, rev.currency_code)}`)}
      {fact('Expected Gross', money(rev.expected_gross, rev.currency_code), foreign ? `₹ ${rev.gross_inr.toLocaleString('en-IN')}` : undefined)}
      {fact('INR Equivalent (contract)', money(rev.estimated_inr), foreign ? 'Accounting value at the estimate-date rate' : 'Indian Rupee: rate 1')}
      {fact('FX Rate', foreign ? `1 ${rev.currency_code} = ₹${rev.fx_rate_to_inr.toLocaleString('en-IN', { maximumFractionDigits: 8 })}` : 'Not applicable (INR)', foreign ? `${rev.fx_rate_date} · ${rev.fx_rate_source} · ${statusLabel(rev.fx_rate_mode)}` : undefined)}
      {fact('Payment Terms', rev.payment_terms || '—', undefined, true)}
      {fact('Billing Milestone', rev.expected_billing_milestone || '—')}
      {fact('Quotation Reference', rev.quotation_reference || '—')}
      {fact('PO / WO Reference', rev.po_wo_reference || '—')}
      {rev.notes && fact('Commercial Notes / Assumptions', rev.notes, undefined, true)}
    </div>
    {!!rev.milestones?.length && <div className="cw-table-wrap"><table className="cw-table"><thead><tr><th>#</th><th>Billing milestone</th><th>% of base</th><th>Amount</th></tr></thead><tbody>{rev.milestones.map(m => <tr key={m.id}><td>{m.sequence}</td><td>{m.milestone_name}</td><td>{m.percent == null ? '—' : `${m.percent}%`}</td><td>{m.amount == null ? '—' : money(m.amount, rev.currency_code)}</td></tr>)}</tbody></table></div>}
    <div><span className="cw-muted">Supporting documents</span><StoredDocumentsList projectId={projectId} revisionId={rev.id} /></div>
    {rev.decision_comments && <div className="cw-muted"><b>Last Finance decision note:</b> {rev.decision_comments}</div>}
    {!!later.length && <div className="cw-muted">Later commercial revisions: {later.map(row => `R${row.revision_no} ${statusLabel(row.status)}`).join(' · ')}</div>}
  </div>
}
