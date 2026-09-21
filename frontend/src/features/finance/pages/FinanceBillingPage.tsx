import { AlertTriangle, CheckCircle2, FileText, RefreshCcw, Wallet } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { StatCard } from '../../../components/StatCard'
import { apiFetch } from '../../../lib/api'
import {
  InvoiceRow,
  LifecycleDashboard,
  Project360,
  formatDate,
  formatMoney,
  lifecycleStatusLabel,
  lifecycleStatusTone,
} from '../../operations/lifecycle-types'
import '../finance-expenses.css'
import '../../operations/operations.css'

const DRAFTABLE = new Set(['READY_FOR_BILLING', 'INVOICE_DRAFT'])
const PAYABLE = new Set(['INVOICE_RAISED', 'PAYMENT_PENDING', 'PARTIALLY_PAID', 'PAYMENT_OVERDUE'])

export function FinanceBillingPage() {
  const [dashboard, setDashboard] = useState<LifecycleDashboard | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<Project360 | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [search, setSearch] = useState('')

  const [invoiceForm, setInvoiceForm] = useState({ invoice_number: '', invoice_date: '', due_date: '', amount: '', tax_amount: '0', currency: 'INR', notes: '' })
  const [paymentForm, setPaymentForm] = useState<Record<number, { payment_reference: string; payment_date: string; amount: string; payment_mode: string; comments: string }>>({})

  function loadDashboard() {
    setLoading(true)
    setError('')
    void apiFetch<LifecycleDashboard>('/operations/lifecycle/dashboard')
      .then(data => {
        setDashboard(data)
        if (!selectedId && data.projects.length) setSelectedId(data.projects[0].id)
      })
      .catch(err => setError(err instanceof Error ? err.message : 'Unable to load the billing lifecycle dashboard'))
      .finally(() => setLoading(false))
  }

  function loadDetail(id: number) {
    void apiFetch<Project360>(`/operations/lifecycle/projects/${id}`).then(setDetail).catch(err => setError(err instanceof Error ? err.message : 'Unable to load project detail'))
  }

  useEffect(loadDashboard, [])
  useEffect(() => { if (selectedId) loadDetail(selectedId) }, [selectedId])

  const projects = useMemo(() => {
    const rows = dashboard?.projects ?? []
    const term = search.trim().toLowerCase()
    if (!term) return rows
    return rows.filter(row => row.project_code.toLowerCase().includes(term) || (row.client_name || '').toLowerCase().includes(term) || (row.client_id || '').toLowerCase().includes(term))
  }, [dashboard, search])

  async function run(key: string, action: () => Promise<unknown>, successMessage: string) {
    setBusy(key)
    setError('')
    setNotice('')
    try {
      await action()
      setNotice(successMessage)
      if (selectedId) loadDetail(selectedId)
      loadDashboard()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Action failed')
    } finally {
      setBusy('')
    }
  }

  async function createInvoice() {
    if (!selectedId) return
    await apiFetch(`/operations/lifecycle/projects/${selectedId}/invoices`, {
      method: 'POST',
      body: JSON.stringify({
        invoice_number: invoiceForm.invoice_number.trim(),
        invoice_date: invoiceForm.invoice_date,
        due_date: invoiceForm.due_date,
        amount: Number(invoiceForm.amount),
        tax_amount: Number(invoiceForm.tax_amount || 0),
        currency: invoiceForm.currency,
        notes: invoiceForm.notes.trim() || null,
      }),
    })
    setInvoiceForm({ invoice_number: '', invoice_date: '', due_date: '', amount: '', tax_amount: '0', currency: 'INR', notes: '' })
  }

  async function raiseInvoice(invoiceId: number) {
    await apiFetch(`/operations/lifecycle/invoices/${invoiceId}/raise`, { method: 'POST', body: JSON.stringify({}) })
  }

  async function recordPayment(invoice: InvoiceRow) {
    const form = paymentForm[invoice.id]
    if (!form) return
    await apiFetch(`/operations/lifecycle/invoices/${invoice.id}/payments`, {
      method: 'POST',
      body: JSON.stringify({
        payment_reference: form.payment_reference.trim(),
        payment_date: form.payment_date,
        amount: Number(form.amount),
        payment_mode: form.payment_mode,
        comments: form.comments.trim() || null,
      }),
    })
    setPaymentForm({ ...paymentForm, [invoice.id]: { payment_reference: '', payment_date: '', amount: '', payment_mode: 'bank_transfer', comments: '' } })
  }

  async function markOverdue(invoiceId: number) {
    await apiFetch(`/operations/lifecycle/invoices/${invoiceId}/overdue`, { method: 'POST' })
  }

  async function closeInvoice(invoiceId: number) {
    await apiFetch(`/operations/lifecycle/invoices/${invoiceId}/close`, { method: 'POST', body: JSON.stringify({}) })
  }

  return <div className="finance-page">
    <DashboardHeader
      eyebrow="FINANCE · PROJECT BILLING"
      title="Billing, Invoices &amp; Payments"
      description="Draft and raise invoices once a project reaches Ready For Billing, record partial/full payments and close invoices toward Finance Closure."
      actions={<button className="operations-button secondary" onClick={loadDashboard}><RefreshCcw size={16}/> Refresh</button>}
    />
    {error && <div className="operations-alert error">{error}</div>}
    {notice && <div className="operations-alert success">{notice}</div>}

    {dashboard && <section className="operations-stats-grid">
      <StatCard icon={CheckCircle2} label="Ready For Billing" value={dashboard.summary.ready_for_billing} tone="green"/>
      <StatCard icon={Wallet} label="Payment Pending" value={dashboard.summary.payment_pending} tone="orange"/>
      <StatCard icon={AlertTriangle} label="Overdue" value={dashboard.summary.overdue} tone="red"/>
      <StatCard icon={FileText} label="Closed" value={dashboard.summary.closed} tone="navy"/>
    </section>}

    <div className="operations-workflow-console-grid">
      <section className="operations-panel">
        <header><div><span className="operations-kicker">PROJECT REGISTER</span><h2>Billing Pipeline</h2></div></header>
        <div className="operations-field operations-span-2"><input placeholder="Search Project ID or Client" value={search} onChange={e => setSearch(e.target.value)} /></div>
        {loading && <div className="operations-empty">Loading...</div>}
        <div className="operations-workflow-tree">
          {projects.map(row => <button key={row.id} type="button" className={row.id === selectedId ? 'active' : ''} onClick={() => setSelectedId(row.id)}>
            <span className="operations-workflow-step-number">{row.project_code.slice(-2)}</span>
            <span><strong>{row.project_code}</strong><small>{row.client_name || row.client_id || 'Client not recorded'}</small><small className={`operations-status ${lifecycleStatusTone(row.workflow_status)}`}>{lifecycleStatusLabel(row.workflow_status)}</small></span>
          </button>)}
          {!loading && !projects.length && <div className="operations-empty">No matching projects.</div>}
        </div>
      </section>

      <section className="operations-panel">
        {!detail && <div className="operations-empty">Select a project to manage billing.</div>}
        {detail && <>
          <header><div><span className="operations-kicker">{detail.project_code} · {detail.client_name || detail.client_id || 'Client not recorded'}</span><h2>{detail.project_name}</h2></div><span className={`operations-status ${lifecycleStatusTone(detail.workflow_status)}`}>{lifecycleStatusLabel(detail.workflow_status)}</span></header>

          {!!detail.change_requests.filter(row => row.status !== 'pending').length && <div className="operations-note">Approved/rejected change requests may affect invoice amount: {detail.change_requests.filter(r => r.status !== 'pending').map(r => `${r.request_code} (${r.status}${r.commercial_impact != null ? `, ${formatMoney(r.commercial_impact, r.currency)}` : ''})`).join(', ')}</div>}

          {DRAFTABLE.has(detail.workflow_status) && <div className="operations-daily-form operations-span-2">
            <label className="operations-field"><span>Invoice Number</span><input value={invoiceForm.invoice_number} onChange={e => setInvoiceForm({ ...invoiceForm, invoice_number: e.target.value })}/></label>
            <label className="operations-field"><span>Invoice Date</span><input type="date" value={invoiceForm.invoice_date} onChange={e => setInvoiceForm({ ...invoiceForm, invoice_date: e.target.value })}/></label>
            <label className="operations-field"><span>Due Date</span><input type="date" value={invoiceForm.due_date} onChange={e => setInvoiceForm({ ...invoiceForm, due_date: e.target.value })}/></label>
            <label className="operations-field"><span>Amount</span><input type="number" min={0} step="0.01" value={invoiceForm.amount} onChange={e => setInvoiceForm({ ...invoiceForm, amount: e.target.value })}/></label>
            <label className="operations-field"><span>Tax Amount</span><input type="number" min={0} step="0.01" value={invoiceForm.tax_amount} onChange={e => setInvoiceForm({ ...invoiceForm, tax_amount: e.target.value })}/></label>
            <label className="operations-field"><span>Currency</span><input value={invoiceForm.currency} onChange={e => setInvoiceForm({ ...invoiceForm, currency: e.target.value.toUpperCase() })}/></label>
            <label className="operations-field operations-span-2"><span>Notes</span><textarea value={invoiceForm.notes} onChange={e => setInvoiceForm({ ...invoiceForm, notes: e.target.value })} rows={2}/></label>
            <div className="operations-actions"><button className="operations-button" disabled={busy === 'invoice' || !invoiceForm.invoice_number || !invoiceForm.invoice_date || !invoiceForm.due_date || !invoiceForm.amount} onClick={() => void run('invoice', createInvoice, 'Invoice draft created')}>Create Invoice Draft</button></div>
          </div>}

          {detail.invoices.map(invoice => {
            const pay = paymentForm[invoice.id] || { payment_reference: '', payment_date: '', amount: '', payment_mode: 'bank_transfer', comments: '' }
            return <div key={invoice.id} className="operations-daily-card">
              <div className="operations-daily-heading">
                <div><span className="operations-kicker">{invoice.invoice_number}</span><h3>{formatMoney(invoice.total_amount, invoice.currency)}</h3><p>Due {formatDate(invoice.due_date)} · Paid {formatMoney(invoice.paid_amount, invoice.currency)} · Balance {formatMoney(invoice.balance, invoice.currency)}</p></div>
                <span className={`operations-status ${lifecycleStatusTone(invoice.status)}`}>{lifecycleStatusLabel(invoice.status)}</span>
              </div>
              <div className="operations-actions">
                {invoice.stored_status === 'INVOICE_DRAFT' && <button className="operations-button" disabled={busy === `raise-${invoice.id}`} onClick={() => void run(`raise-${invoice.id}`, () => raiseInvoice(invoice.id), 'Invoice raised')}>Raise Invoice</button>}
                {invoice.status === 'PAYMENT_OVERDUE' && invoice.stored_status !== 'PAYMENT_OVERDUE' && <button className="operations-button warning" disabled={busy === `overdue-${invoice.id}`} onClick={() => void run(`overdue-${invoice.id}`, () => markOverdue(invoice.id), 'Invoice marked overdue')}>Mark Overdue</button>}
                {invoice.stored_status === 'PAYMENT_RECEIVED' && <button className="operations-button success" disabled={busy === `close-${invoice.id}`} onClick={() => void run(`close-${invoice.id}`, () => closeInvoice(invoice.id), 'Invoice closed')}>Close Invoice</button>}
              </div>
              {PAYABLE.has(invoice.stored_status) && <div className="operations-daily-form">
                <label className="operations-field"><span>Payment Reference</span><input value={pay.payment_reference} onChange={e => setPaymentForm({ ...paymentForm, [invoice.id]: { ...pay, payment_reference: e.target.value } })}/></label>
                <label className="operations-field"><span>Payment Date</span><input type="date" value={pay.payment_date} onChange={e => setPaymentForm({ ...paymentForm, [invoice.id]: { ...pay, payment_date: e.target.value } })}/></label>
                <label className="operations-field"><span>Amount</span><input type="number" min={0} step="0.01" max={invoice.balance} value={pay.amount} onChange={e => setPaymentForm({ ...paymentForm, [invoice.id]: { ...pay, amount: e.target.value } })}/></label>
                <label className="operations-field"><span>Mode</span><select value={pay.payment_mode} onChange={e => setPaymentForm({ ...paymentForm, [invoice.id]: { ...pay, payment_mode: e.target.value } })}><option value="bank_transfer">Bank Transfer</option><option value="upi">UPI</option><option value="cheque">Cheque</option><option value="cash">Cash</option><option value="card">Card</option></select></label>
                <div className="operations-actions"><button className="operations-button" disabled={busy === `pay-${invoice.id}` || !pay.payment_reference || !pay.payment_date || !pay.amount} onClick={() => void run(`pay-${invoice.id}`, () => recordPayment(invoice), 'Payment recorded')}>Record Payment</button></div>
              </div>}
              {!!invoice.payments.length && <div className="operations-table-wrap"><table className="operations-table"><thead><tr><th>Reference</th><th>Date</th><th>Amount</th><th>Mode</th></tr></thead><tbody>{invoice.payments.map(p => <tr key={p.id}><td>{p.payment_reference}</td><td>{formatDate(p.payment_date)}</td><td>{formatMoney(p.amount, invoice.currency)}</td><td>{p.payment_mode}</td></tr>)}</tbody></table></div>}
            </div>
          })}
          {!detail.invoices.length && <div className="operations-empty">No invoices yet for this project.</div>}
        </>}
      </section>
    </div>
  </div>
}
