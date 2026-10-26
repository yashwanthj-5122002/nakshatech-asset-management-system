import { AlertTriangle, CheckCircle2, Download, Eye, FileText, Inbox, Pencil, Plus, Printer, RefreshCcw, Trash2, Wallet, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { useAuth } from '../../../context/AuthContext'
import { StatCard } from '../../../components/StatCard'
import { apiBlob, apiFetch, downloadFile } from '../../../lib/api'
import type { CurrencyPayload } from '../../commercial/types'
import { FinanceBillingBasis, type InvoiceLinks, type RecommendationApply } from '../../commercial/components/FinanceBillingBasis'
import { InvoiceA4Document } from '../components/InvoiceA4Document'
import { InvoiceTemplateSelector, invoiceTemplateQuery, type InvoiceTemplate } from '../components/InvoiceTemplateSelector'
import {
  BadDebtRow,
  InvoiceRow,
  InvoiceDocumentPayload,
  LifecycleDashboard,
  Project360,
  formatDate,
  formatDateTime,
  formatMoney,
  lifecycleStatusLabel,
  lifecycleStatusTone,
} from '../../operations/lifecycle-types'
import '../finance-expenses.css'
import '../invoice-document.css'
import '../../operations/operations.css'

const DRAFTABLE = new Set(['READY_FOR_BILLING', 'INVOICE_DRAFT'])
const PAYABLE = new Set(['INVOICE_RAISED', 'PAYMENT_PENDING', 'PARTIALLY_PAID', 'PAYMENT_OVERDUE'])

type LineItemForm = { sequence: number; description: string; hsn_sac: string; unit: string; quantity: string; rate: string }
type GstMode = 'none' | 'cgst_sgst' | 'igst'
type BadDebtFormState = { proposed_amount: string; reason: string; collection_attempts: string; last_followup_date: string; finance_remarks: string }
type RecoveryFormState = { amount: string; payment_date: string; payment_reference: string; payment_mode: string; remarks: string }
type MiniInvoicePreview = { invoiceId: number; invoiceNumber: string; theme: string; url: string }

function blankBadDebtForm(): BadDebtFormState {
  return { proposed_amount: '', reason: '', collection_attempts: '', last_followup_date: '', finance_remarks: '' }
}

function blankRecoveryForm(): RecoveryFormState {
  return { amount: '', payment_date: '', payment_reference: '', payment_mode: 'bank_transfer', remarks: '' }
}

function badDebtStatusMeta(status: BadDebtRow['status']): { label: string; tone: 'success' | 'warning' | 'danger' } {
  switch (status) {
    case 'PROPOSED': return { label: 'Bad Debt Proposed', tone: 'warning' }
    case 'APPROVED': return { label: 'Bad Debt / Written Off', tone: 'danger' }
    case 'REJECTED': return { label: 'Bad Debt Rejected', tone: 'danger' }
    case 'RECOVERED': return { label: 'Bad Debt Recovered', tone: 'success' }
  }
}

/** Human-readable labels for the three persisted invoice theme keys (keys are never renamed). */
function invoiceThemeLabel(theme: string | null | undefined): string {
  switch (theme) {
    case 'blue_topographic': return 'Theme 2 — Blue Topographic'
    case 'green_gold_premium': return 'Theme 3 — Green Gold Premium'
    default: return 'Theme 1 — Blue Classic'
  }
}
type AutoFillResult = {
  client: { name: string; address: string | null; gstin: string | null; email: string | null; phone: string | null }
  project: { code: string; name: string; description: string | null }
  company: { name: string; address: string | null; gstin: string | null; pan: string | null; phone: string | null; email: string | null; website: string | null; hsn_sac: string | null }
  bank: { bank_name: string | null; account_name: string | null; account_number: string | null; ifsc: string | null; swift: string | null; branch: string | null }
  recommended: { currency: string; amount: number; tax_percent: number; tax_amount: number; payment_terms: string | null; po_wo_reference: string | null; links: InvoiceLinks } | null
}

function blankLineItem(sequence: number): LineItemForm {
  return { sequence, description: '', hsn_sac: '', unit: 'Nos', quantity: '1', rate: '0' }
}

function lineItemAmount(item: LineItemForm): number {
  return (Number(item.quantity) || 0) * (Number(item.rate) || 0)
}

export function FinanceBillingPage() {
  const { user } = useAuth()
  const canEditDraft = user?.role === 'finance' || user?.role === 'admin'
  const [searchParams] = useSearchParams()
  const requestedProjectId = Number(searchParams.get('project') || 0) || null
  const requestedInvoiceId = Number(searchParams.get('invoice') || 0) || null
  const [dashboard, setDashboard] = useState<LifecycleDashboard | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<Project360 | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [search, setSearch] = useState('')
  const [preview, setPreview] = useState<InvoiceDocumentPayload | null>(null)
  const [template, setTemplate] = useState<InvoiceTemplate>('modern_teal')
  const [badDebts, setBadDebts] = useState<BadDebtRow[]>([])
  const [badDebtForm, setBadDebtForm] = useState<Record<number, BadDebtFormState>>({})
  const [recoveryForm, setRecoveryForm] = useState<Record<number, RecoveryFormState>>({})

  // --- V8.7.x COMPACT THEME PREVIEW ------------------------------------------------------
  // ONE small A4 panel per page, fed by the SAME backend PDF used by
  // A4 Preview / Download / Print (GET .../invoices/{id}/document.pdf).
  // Fetched ONLY when the user clicks Theme Preview or changes a theme — never
  // automatically for every invoice card.
  const [miniPreview, setMiniPreview] = useState<MiniInvoicePreview | null>(null)
  const [miniPreviewLoadingId, setMiniPreviewLoadingId] = useState<number | null>(null)
  const [miniPreviewError, setMiniPreviewError] = useState('')
  const [miniPreviewErrorId, setMiniPreviewErrorId] = useState<number | null>(null)
  const miniPreviewUrlRef = useRef<string | null>(null) // current Blob URL (single source for cleanup)
  const miniPreviewSeqRef = useRef(0) // drops stale / out-of-order PDF fetches

  const [currencies, setCurrencies] = useState<CurrencyPayload | null>(null)
  const [invoiceForm, setInvoiceForm] = useState({ invoice_number: '', invoice_date: '', due_date: '', amount: '', tax_amount: '0', tax_percent: '0', payment_terms: '', po_wo_reference: '', currency: 'INR', notes: '', fx_rate_to_inr: '', fx_rate_mode: 'MANUAL_OVERRIDE', fx_override_reason: '', theme: 'blue_classic' })
  const noLinks: InvoiceLinks = { estimate_revision_id: null, billing_basis_id: null, billed_quantity: null, billed_milestone_id: null }
  const [links, setLinks] = useState<InvoiceLinks>(noLinks)
  const [basisTick, setBasisTick] = useState(0)

  // --- Invoice Generation V2: entry mode, line items, GST split, work order fields -------
  const [entryMode, setEntryMode] = useState<'auto_fill' | 'manual' | null>(null)
  const [autoFillData, setAutoFillData] = useState<AutoFillResult | null>(null)
  const [autoFillBusy, setAutoFillBusy] = useState(false)
  const [lineItems, setLineItems] = useState<LineItemForm[]>([])
  const [gstMode, setGstMode] = useState<GstMode>('none')
  const [gstPercents, setGstPercents] = useState({ cgst: '9', sgst: '9', igst: '18' })
  const [workOrderForm, setWorkOrderForm] = useState({ work_order_date: '', dispatch_details: '', dispatch_date: '', place_of_supply: '' })

  const lineItemTotal = useMemo(() => lineItems.reduce((sum, item) => sum + lineItemAmount(item), 0), [lineItems])
  const taxableAmount = lineItems.length ? lineItemTotal : (Number(invoiceForm.amount) || 0)
  const gstBreakdown = useMemo(() => {
    if (gstMode === 'cgst_sgst') {
      const cgst = Math.round(taxableAmount * (Number(gstPercents.cgst) || 0) / 100 * 100) / 100
      const sgst = Math.round(taxableAmount * (Number(gstPercents.sgst) || 0) / 100 * 100) / 100
      return { cgst, sgst, igst: 0, total: cgst + sgst }
    }
    if (gstMode === 'igst') {
      const igst = Math.round(taxableAmount * (Number(gstPercents.igst) || 0) / 100 * 100) / 100
      return { cgst: 0, sgst: 0, igst, total: igst }
    }
    return { cgst: 0, sgst: 0, igst: 0, total: Number(invoiceForm.tax_amount) || 0 }
  }, [gstMode, gstPercents, taxableAmount, invoiceForm.tax_amount])

  // GSTIN starts with the 2-digit state code: same state → CGST+SGST, different → IGST.
  const suggestedGstMode = useMemo<GstMode | null>(() => {
    const sellerState = autoFillData?.company.gstin?.trim().slice(0, 2)
    const buyerState = autoFillData?.client.gstin?.trim().slice(0, 2)
    if (!sellerState || !buyerState || !/^\d{2}$/.test(sellerState) || !/^\d{2}$/.test(buyerState)) return null
    return sellerState === buyerState ? 'cgst_sgst' : 'igst'
  }, [autoFillData])

  useEffect(() => {
    if (!lineItems.length) return
    setInvoiceForm(form => (form.amount === lineItemTotal.toFixed(2) ? form : { ...form, amount: lineItemTotal.toFixed(2) }))
  }, [lineItems, lineItemTotal])

  useEffect(() => {
    if (gstMode === 'none') return
    const taxAmount = gstBreakdown.total.toFixed(2)
    const taxPercent = String(gstMode === 'igst' ? Number(gstPercents.igst) || 0 : (Number(gstPercents.cgst) || 0) + (Number(gstPercents.sgst) || 0))
    setInvoiceForm(form => (form.tax_amount === taxAmount && form.tax_percent === taxPercent ? form : { ...form, tax_amount: taxAmount, tax_percent: taxPercent }))
  }, [gstMode, gstBreakdown.total, gstPercents])

  function addLineItem() {
    setLineItems(items => [...items, blankLineItem((items[items.length - 1]?.sequence || 0) + 1)])
  }
  function updateLineItem(sequence: number, patch: Partial<LineItemForm>) {
    setLineItems(items => items.map(item => (item.sequence === sequence ? { ...item, ...patch } : item)))
  }
  function removeLineItem(sequence: number) {
    setLineItems(items => items.filter(item => item.sequence !== sequence))
  }

  async function startAutoFill() {
    if (!selectedId) return
    setEntryMode('auto_fill')
    setAutoFillBusy(true)
    try {
      const data = await apiFetch<AutoFillResult>(`/operations/lifecycle/projects/${selectedId}/invoices/auto-fill`)
      setAutoFillData(data)
      if (!lineItems.length) {
        setLineItems([{ sequence: 1, description: data.project.name, hsn_sac: data.company.hsn_sac || '', unit: 'Project', quantity: '1', rate: invoiceForm.amount || '0' }])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Auto Fill could not reach ERP data for this project')
    } finally {
      setAutoFillBusy(false)
    }
  }

  function startManualMode() {
    setEntryMode('manual')
    setAutoFillData(null)
  }

  function resetInvoiceFormExtras() {
    setEntryMode(null)
    setAutoFillData(null)
    setLineItems([])
    setGstMode('none')
    setWorkOrderForm({ work_order_date: '', dispatch_details: '', dispatch_date: '', place_of_supply: '' })
  }
  const [paymentForm, setPaymentForm] = useState<Record<number, { payment_reference: string; payment_date: string; amount: string; payment_mode: string; comments: string; fx_rate_to_inr: string; fx_rate_mode: string; fx_override_reason: string }>>({})

  function loadBadDebts() {
    void apiFetch<BadDebtRow[]>('/operations/lifecycle/bad-debts').then(setBadDebts).catch(() => setBadDebts([]))
  }

  function loadDashboard() {
    setLoading(true)
    setError('')
    void apiFetch<LifecycleDashboard>('/operations/lifecycle/dashboard')
      .then(data => {
        setDashboard(data)
        if (!selectedId && data.projects.length) {
          const requested = requestedProjectId && data.projects.some(row => row.id === requestedProjectId) ? requestedProjectId : null
          setSelectedId(requested || data.projects[0].id)
        }
      })
      .catch(err => setError(err instanceof Error ? err.message : 'Unable to load the billing lifecycle dashboard'))
      .finally(() => setLoading(false))
  }

  function loadDetail(id: number) {
    void apiFetch<Project360>(`/operations/lifecycle/projects/${id}`).then(setDetail).catch(err => setError(err instanceof Error ? err.message : 'Unable to load project detail'))
  }

  useEffect(() => { loadDashboard(); loadBadDebts() }, [])
  useEffect(() => { void apiFetch<CurrencyPayload>('/commercial/currencies').then(setCurrencies).catch(() => undefined) }, [])
  useEffect(() => { if (selectedId) loadDetail(selectedId) }, [selectedId])

  // Deep link from Bad Debt / overdue notifications:
  // /finance/billing?project=<id>&invoice=<id> must land on the exact invoice.
  useEffect(() => {
    if (!detail || !requestedInvoiceId) return
    const target = document.getElementById(`invoice-${requestedInvoiceId}`)
    if (!target) return
    target.scrollIntoView({ behavior: 'smooth', block: 'center' })
    target.classList.add('nk-deeplink-focus')
    const timer = window.setTimeout(() => target.classList.remove('nk-deeplink-focus'), 5000)
    return () => window.clearTimeout(timer)
  }, [detail, requestedInvoiceId])

  // Blob URL cleanup on unmount: revoke ONCE when the Billing page unmounts.
  // The URL is NEVER revoked on re-render or on miniPreview change — that was what
  // made the inline preview vanish. Deps must stay [].
  useEffect(() => () => {
    miniPreviewSeqRef.current += 1
    if (miniPreviewUrlRef.current) {
      URL.revokeObjectURL(miniPreviewUrlRef.current)
      miniPreviewUrlRef.current = null
    }
  }, [])

  const projects = useMemo(() => {
    const rows = dashboard?.projects ?? []
    const term = search.trim().toLowerCase()
    if (!term) return rows
    return rows.filter(row => row.project_code.toLowerCase().includes(term) || (row.client_name || '').toLowerCase().includes(term) || (row.client_id || '').toLowerCase().includes(term))
  }, [dashboard, search])

  async function run(key: string, action: () => Promise<unknown>, successMessage: string): Promise<boolean> {
    setBusy(key)
    setError('')
    setNotice('')
    try {
      await action()
      setNotice(successMessage)
      if (selectedId) loadDetail(selectedId)
      loadDashboard()
      loadBadDebts()
      return true
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Action failed')
      return false
    } finally {
      setBusy('')
    }
  }

  // --- V8.7.x compact theme preview: Blob URL lifecycle + backend PDF fetch ----------------
  /**
   * Fetch the REAL backend PDF (the same document.pdf used by A4 Preview / Download / Print)
   * as a Blob and show it in the small inline panel. The backend renderer stays the single
   * visual source of truth — nothing is duplicated in React.
   *
   * The currently displayed preview stays visible until the NEW PDF is ready; only then is
   * the previous Blob URL revoked and swapped. A sequence guard drops out-of-order fetches
   * (e.g. rapid Theme Preview clicks on two invoices) so only the latest request wins.
   */
  async function openMiniPreview(invoiceId: number, invoiceNumber: string, theme: string) {
    const seq = ++miniPreviewSeqRef.current
    setMiniPreviewLoadingId(invoiceId)
    setMiniPreviewError('')
    setMiniPreviewErrorId(null)
    try {
      const blob = await apiBlob(`/operations/lifecycle/invoices/${invoiceId}/document.pdf`)
      const nextUrl = URL.createObjectURL(blob)
      if (seq !== miniPreviewSeqRef.current) { URL.revokeObjectURL(nextUrl); return } // superseded: drop it
      if (miniPreviewUrlRef.current) URL.revokeObjectURL(miniPreviewUrlRef.current) // revoke PREVIOUS URL only now
      miniPreviewUrlRef.current = nextUrl
      setMiniPreview({ invoiceId, invoiceNumber, theme, url: nextUrl })
    } catch (err) {
      if (seq !== miniPreviewSeqRef.current) return
      setMiniPreviewError(err instanceof Error ? err.message : 'Theme preview could not be generated')
      setMiniPreviewErrorId(invoiceId)
    } finally {
      if (seq === miniPreviewSeqRef.current) setMiniPreviewLoadingId(null)
    }
  }

  /** Explicit close: revoke the Blob URL and clear the panel. The only user action (besides
   *  opening another invoice's preview or unmounting) that removes the preview. */
  function closeMiniPreview() {
    miniPreviewSeqRef.current += 1 // cancels any in-flight mini-preview fetch
    if (miniPreviewUrlRef.current) {
      URL.revokeObjectURL(miniPreviewUrlRef.current)
      miniPreviewUrlRef.current = null
    }
    setMiniPreview(null)
    setMiniPreviewError('')
    setMiniPreviewErrorId(null)
  }

  /**
   * Theme selector flow: PATCH the persisted theme through the existing endpoint first,
   * refresh invoice state, and ONLY THEN fetch the new PDF — so the thumbnail can never
   * show the previous theme. On save failure the existing error behaviour is kept and the
   * preview is never refreshed with unpersisted data.
   */
  async function changeInvoiceTheme(invoiceId: number, invoiceNumber: string, theme: string) {
    setBusy(`theme-${invoiceId}`)
    setError('')
    setNotice('')
    try {
      await apiFetch(`/operations/lifecycle/invoices/${invoiceId}`, { method: 'PATCH', body: JSON.stringify({ theme }) })
      setNotice('Invoice theme updated')
      if (selectedId) loadDetail(selectedId)
      loadDashboard()
      await openMiniPreview(invoiceId, invoiceNumber, theme)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invoice theme update failed')
    } finally {
      setBusy('')
    }
  }

  function applyRecommendation(apply: RecommendationApply) {
    setInvoiceForm(form => ({ ...form, currency: apply.currency, amount: apply.amount, tax_amount: apply.tax_amount, tax_percent: apply.tax_percent, payment_terms: apply.payment_terms || form.payment_terms, po_wo_reference: apply.po_wo_reference || form.po_wo_reference, fx_rate_to_inr: apply.currency === 'INR' ? '' : form.fx_rate_to_inr }))
    setLinks(apply.links)
    setNotice('Recommended values copied into the invoice form. Review them, then create the invoice draft.')
  }

  async function createInvoice() {
    if (!selectedId) return
    const gstFields = gstMode === 'cgst_sgst'
      ? { cgst_percent: Number(gstPercents.cgst), cgst_amount: gstBreakdown.cgst, sgst_percent: Number(gstPercents.sgst), sgst_amount: gstBreakdown.sgst, igst_percent: null, igst_amount: null }
      : gstMode === 'igst'
      ? { cgst_percent: null, cgst_amount: null, sgst_percent: null, sgst_amount: null, igst_percent: Number(gstPercents.igst), igst_amount: gstBreakdown.igst }
      : { cgst_percent: null, cgst_amount: null, sgst_percent: null, sgst_amount: null, igst_percent: null, igst_amount: null }
    await apiFetch(`/operations/lifecycle/projects/${selectedId}/invoices`, {
      method: 'POST',
      body: JSON.stringify({
        invoice_number: invoiceForm.invoice_number.trim(),
        invoice_date: invoiceForm.invoice_date,
        due_date: invoiceForm.due_date,
        amount: Number(invoiceForm.amount),
        tax_amount: Number(invoiceForm.tax_amount || 0),
        tax_percent: invoiceForm.tax_percent.trim() ? Number(invoiceForm.tax_percent) : null,
        currency: invoiceForm.currency,
        payment_terms: invoiceForm.payment_terms.trim() || null,
        po_wo_reference: invoiceForm.po_wo_reference.trim() || null,
        notes: invoiceForm.notes.trim() || null,
        // V8.7: stored on the invoice so the selected A4 design is remembered on reload.
        theme: invoiceForm.theme,
        fx_rate_to_inr: invoiceForm.fx_rate_to_inr.trim() ? Number(invoiceForm.fx_rate_to_inr) : null,
        fx_rate_mode: invoiceForm.fx_rate_to_inr.trim() ? invoiceForm.fx_rate_mode : null,
        fx_override_reason: invoiceForm.fx_rate_to_inr.trim() ? invoiceForm.fx_override_reason.trim() || null : null,
        ...links,
        entry_mode: entryMode,
        line_items: lineItems.map(item => ({
          sequence: item.sequence, description: item.description.trim(), hsn_sac: item.hsn_sac.trim() || null,
          unit: item.unit.trim() || 'Nos', quantity: Number(item.quantity) || 0, rate: Number(item.rate) || 0,
          amount: Math.round(lineItemAmount(item) * 100) / 100,
        })),
        ...gstFields,
        work_order_date: workOrderForm.work_order_date || null,
        dispatch_details: workOrderForm.dispatch_details.trim() || null,
        dispatch_date: workOrderForm.dispatch_date || null,
        place_of_supply: workOrderForm.place_of_supply.trim() || null,
      }),
    })
    setLinks(noLinks)
    setBasisTick(v => v + 1)
    setInvoiceForm({ invoice_number: '', invoice_date: '', due_date: '', amount: '', tax_amount: '0', tax_percent: '0', payment_terms: '', po_wo_reference: '', currency: 'INR', notes: '', fx_rate_to_inr: '', fx_rate_mode: 'MANUAL_OVERRIDE', fx_override_reason: '', theme: 'blue_classic' })
    resetInvoiceFormExtras()
  }

  async function raiseInvoice(invoiceId: number) {
    await apiFetch(`/operations/lifecycle/invoices/${invoiceId}/raise`, { method: 'POST', body: JSON.stringify({}) })
  }

  async function proposeBadDebt(invoice: InvoiceRow) {
    const form = badDebtForm[invoice.id] || blankBadDebtForm()
    // The backend requires the persisted PAYMENT_OVERDUE state. Finance gets a
    // single action: persist overdue first when the invoice is only overdue by
    // rule, then file the proposal.
    if (invoice.stored_status !== 'PAYMENT_OVERDUE') {
      await apiFetch(`/operations/lifecycle/invoices/${invoice.id}/overdue`, { method: 'POST' })
    }
    await apiFetch(`/operations/lifecycle/invoices/${invoice.id}/bad-debt`, {
      method: 'POST',
      body: JSON.stringify({
        reason: form.reason.trim(),
        collection_attempts: form.collection_attempts.trim(),
        last_followup_date: form.last_followup_date || null,
        finance_remarks: form.finance_remarks.trim() || null,
        proposed_amount: form.proposed_amount.trim() ? Number(form.proposed_amount) : null,
      }),
    })
    setBadDebtForm(forms => ({ ...forms, [invoice.id]: blankBadDebtForm() }))
  }

  async function recordRecovery(invoice: InvoiceRow) {
    const form = recoveryForm[invoice.id] || blankRecoveryForm()
    await apiFetch(`/operations/lifecycle/invoices/${invoice.id}/bad-debt/recovery`, {
      method: 'POST',
      body: JSON.stringify({
        amount: Number(form.amount),
        payment_date: form.payment_date,
        payment_reference: form.payment_reference.trim(),
        payment_mode: form.payment_mode,
        remarks: form.remarks.trim() || null,
      }),
    })
    setRecoveryForm(forms => ({ ...forms, [invoice.id]: blankRecoveryForm() }))
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
        fx_rate_to_inr: form.fx_rate_to_inr.trim() ? Number(form.fx_rate_to_inr) : null,
        fx_rate_mode: form.fx_rate_to_inr.trim() ? form.fx_rate_mode : null,
        fx_override_reason: form.fx_rate_to_inr.trim() ? form.fx_override_reason.trim() || null : null,
      }),
    })
    setPaymentForm({ ...paymentForm, [invoice.id]: { payment_reference: '', payment_date: '', amount: '', payment_mode: 'bank_transfer', comments: '', fx_rate_to_inr: '', fx_rate_mode: 'BANK_REALIZATION_RATE', fx_override_reason: '' } })
  }

  async function markOverdue(invoiceId: number) {
    await apiFetch(`/operations/lifecycle/invoices/${invoiceId}/overdue`, { method: 'POST' })
  }

  async function closeInvoice(invoiceId: number) {
    await apiFetch(`/operations/lifecycle/invoices/${invoiceId}/close`, { method: 'POST', body: JSON.stringify({}) })
  }

  async function previewInvoice(invoiceId: number) {
    setBusy(`preview-${invoiceId}`)
    setError('')
    try {
      // V8.7: the preview IS the backend-rendered document, so VIEW / PREVIEW / DOWNLOAD / PRINT
      // can never disagree about the invoice design (theme + signed state included).
      const blob = await apiBlob(`/operations/lifecycle/invoices/${invoiceId}/document.pdf`)
      const url = URL.createObjectURL(blob)
      window.open(url, '_blank', 'noopener')
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invoice preview could not be generated')
    } finally {
      setBusy('')
    }
  }

  const [editInvoiceId, setEditInvoiceId] = useState<number | null>(null)
  const [editForm, setEditForm] = useState<Record<string, string>>({})
  const [editInitial, setEditInitial] = useState<Record<string, string>>({})

  const editGst = useMemo(() => {
    const taxable = Number(editForm.amount) || 0
    const share = (percent: string | undefined) => Math.round(taxable * (Number(percent) || 0) / 100 * 100) / 100
    if (editForm.gst_mode === 'cgst_sgst') {
      const cgst = share(editForm.cgst_percent), sgst = share(editForm.sgst_percent)
      return { cgst, sgst, igst: 0, total: Math.round((cgst + sgst) * 100) / 100 }
    }
    if (editForm.gst_mode === 'igst') {
      const igst = share(editForm.igst_percent)
      return { cgst: 0, sgst: 0, igst, total: igst }
    }
    return { cgst: 0, sgst: 0, igst: 0, total: Number(editForm.tax_amount) || 0 }
  }, [editForm])

  /** Open EDIT INVOICE pre-filled from the EXISTING backend invoice (never a blank form). */
  function openEditInvoice(invoice: Record<string, unknown>) {
    setError('')
    setEditInvoiceId(Number(invoice.id))
    const gstMode = invoice.igst_amount != null ? 'igst' : (invoice.cgst_amount != null || invoice.sgst_amount != null) ? 'cgst_sgst' : 'none'
    const form = {
      invoice_date: String(invoice.invoice_date ?? ''),
      due_date: String(invoice.due_date ?? ''),
      amount: String(invoice.amount ?? ''),
      tax_amount: String(invoice.tax_amount ?? ''),
      tax_percent: String(invoice.tax_percent ?? ''),
      gst_mode: gstMode,
      cgst_percent: String(invoice.cgst_percent ?? '9'),
      sgst_percent: String(invoice.sgst_percent ?? '9'),
      igst_percent: String(invoice.igst_percent ?? '18'),
      payment_terms: String(invoice.payment_terms ?? ''),
      po_wo_reference: String(invoice.po_wo_reference ?? ''),
      place_of_supply: String(invoice.place_of_supply ?? ''),
      dispatch_details: String(invoice.dispatch_details ?? ''),
      notes: String(invoice.notes ?? ''),
      theme: String(invoice.theme || 'blue_classic'),
    }
    setEditForm(form)
    setEditInitial(form)
  }

  /** Save edits through the existing backend PATCH (same invoice record, never a duplicate).
   *  Only changed fields are sent, so a theme/notes edit after a payment is not refused. */
  async function saveEditInvoice(invoiceId: number) {
    const changed = (key: string) => (editForm[key] ?? '') !== (editInitial[key] ?? '')
    const body: Record<string, unknown> = { theme: editForm.theme || 'blue_classic' }
    for (const key of ['invoice_date', 'due_date', 'payment_terms', 'po_wo_reference',
      'place_of_supply', 'dispatch_details', 'notes'] as const) {
      if (changed(key)) body[key] = editForm[key].trim() || null
    }
    const taxChanged = ['amount', 'tax_amount', 'tax_percent', 'gst_mode', 'cgst_percent', 'sgst_percent', 'igst_percent'].some(changed)
    if (taxChanged) {
      if (editForm.amount !== '') body.amount = Number(editForm.amount)
      body.gst_mode = editForm.gst_mode
      body.tax_amount = editGst.total
      if (editForm.gst_mode === 'cgst_sgst') {
        Object.assign(body, { cgst_percent: Number(editForm.cgst_percent) || 0, cgst_amount: editGst.cgst, sgst_percent: Number(editForm.sgst_percent) || 0, sgst_amount: editGst.sgst, tax_percent: (Number(editForm.cgst_percent) || 0) + (Number(editForm.sgst_percent) || 0) })
      } else if (editForm.gst_mode === 'igst') {
        Object.assign(body, { igst_percent: Number(editForm.igst_percent) || 0, igst_amount: editGst.igst, tax_percent: Number(editForm.igst_percent) || 0 })
      } else if (editForm.tax_percent !== '') {
        body.tax_percent = Number(editForm.tax_percent)
      }
    }
    const saved = await run(`edit-${invoiceId}`, () => apiFetch(
      `/operations/lifecycle/invoices/${invoiceId}`, { method: 'PATCH', body: JSON.stringify(body) },
    ), 'Invoice updated (same invoice number)')
    setEditInvoiceId(null)
    // If the compact theme preview is open for this invoice, refresh it from the persisted theme.
    if (saved && miniPreview?.invoiceId === invoiceId) void openMiniPreview(invoiceId, miniPreview.invoiceNumber, editForm.theme || 'blue_classic')
  }

  async function downloadInvoice(invoiceId: number, invoiceNumber: string) {
    setBusy(`download-${invoiceId}`)
    setError('')
    try {
      await downloadFile(`/operations/lifecycle/invoices/${invoiceId}/document.pdf?download=true&${invoiceTemplateQuery(template)}`, `${invoiceNumber}_${template}_A4_Invoice.pdf`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invoice PDF could not be downloaded')
    } finally {
      setBusy('')
    }
  }

  async function printInvoice(invoiceId: number) {
    const printWindow = window.open('', '_blank')
    if (!printWindow) {
      setError('Allow pop-ups for this site to print the invoice')
      return
    }
    printWindow.opener = null
    printWindow.document.title = 'Preparing A4 invoice'
    printWindow.document.body.textContent = 'Preparing A4 invoice for print...'
    setBusy(`print-${invoiceId}`)
    setError('')
    try {
      const blob = await apiBlob(`/operations/lifecycle/invoices/${invoiceId}/document.pdf?${invoiceTemplateQuery(template)}`)
      const url = URL.createObjectURL(blob)
      printWindow.onload = () => {
        printWindow.focus()
        printWindow.print()
        window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
      }
      printWindow.location.href = url
    } catch (err) {
      printWindow.close()
      setError(err instanceof Error ? err.message : 'Invoice PDF could not be prepared for printing')
    } finally {
      setBusy('')
    }
  }

  return <div className="finance-page">
    <DashboardHeader
      eyebrow="FINANCE · PROJECT BILLING"
      title="Billing, Invoices &amp; Payments"
      description="Draft and raise invoices once a project reaches Ready For Billing, record partial/full payments and close invoices toward Finance Closure."
      actions={<button className="operations-button secondary" onClick={loadDashboard}><RefreshCcw size={16}/> Refresh</button>}
      meta={<>
        <span className="nk-meta-chip"><FileText size={14}/> Ready For Billing → Invoice → Payment → Closure</span>
        <span className="nk-meta-chip"><CheckCircle2 size={14}/> Partial and full payments supported</span>
      </>}
    />
    {error && <div className="operations-alert error">{error}</div>}
    {notice && <div className="operations-alert success">{notice}</div>}
    <InvoiceTemplateSelector value={template} onChange={setTemplate} label="Project invoice format for preview, PDF and print" compact/>

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
          {projects.map(row => {
            const projectBadDebt = badDebts.find(item => item.project_id === row.id)
            const projectBadDebtMeta = projectBadDebt ? badDebtStatusMeta(projectBadDebt.status) : null
            return <button key={row.id} type="button" className={row.id === selectedId ? 'active' : ''} onClick={() => setSelectedId(row.id)}>
              <span className="operations-workflow-step-number">{row.project_code.slice(-2)}</span>
              <span>
                <strong>{row.project_code}</strong>
                <small>{row.client_name || row.client_id || 'Client not recorded'}</small>
                <small className={`operations-status ${lifecycleStatusTone(row.workflow_status)}`}>{lifecycleStatusLabel(row.workflow_status)}</small>
                {projectBadDebtMeta && <small className={`operations-status ${projectBadDebtMeta.tone}`}>{projectBadDebtMeta.label}</small>}
              </span>
            </button>
          })}
          {!loading && !projects.length && (!dashboard ? (
            <div className="nk-empty">
              <span className="nk-empty-icon"><AlertTriangle size={22}/></span>
              <h3>Billing pipeline unavailable</h3>
              <p>The project register could not be loaded. Use Refresh in the page header to try again.</p>
            </div>
          ) : dashboard.projects.length === 0 ? (
            <div className="nk-empty">
              <span className="nk-empty-icon"><Inbox size={22}/></span>
              <h3>No billable projects</h3>
              <p>Projects appear in the Billing Pipeline once operations moves them toward Ready For Billing. Refresh to check for new work.</p>
              <div className="nk-empty-action"><button className="operations-button" onClick={loadDashboard}><RefreshCcw size={16}/> Refresh</button></div>
            </div>
          ) : (
            <div className="nk-empty">
              <span className="nk-empty-icon"><Inbox size={22}/></span>
              <h3>No projects match this search</h3>
              <p>{dashboard.projects.length} project(s) are in the pipeline. Clear the search box to see the full list.</p>
              <div className="nk-empty-action"><button className="operations-button secondary" onClick={() => setSearch('')}><RefreshCcw size={16}/> Clear search</button></div>
            </div>
          ))}
        </div>
      </section>

      <section className="operations-panel">
        {!detail && <div className="nk-empty">
          <span className="nk-empty-icon"><FileText size={22}/></span>
          <h3>{projects.length ? 'No project selected' : 'No billable project selected'}</h3>
          <p>{projects.length ? 'Select a project from the Billing Pipeline to review its invoices, record payments and move it toward Finance Closure.' : 'Nothing to invoice yet. Once a project enters the Billing Pipeline, select it here to draft its first invoice.'}</p>
        </div>}
        {detail && <>
          <header><div><span className="operations-kicker">{detail.project_code} · {detail.client_name || detail.client_id || 'Client not recorded'}</span><h2>{detail.project_name}</h2></div><span className={`operations-status ${lifecycleStatusTone(detail.workflow_status)}`}>{lifecycleStatusLabel(detail.workflow_status)}</span></header>

          {!!detail.change_requests.filter(row => row.status !== 'pending').length && <div className="operations-note">Approved/rejected change requests may affect invoice amount: {detail.change_requests.filter(r => r.status !== 'pending').map(r => `${r.request_code} (${r.status}${r.commercial_impact != null ? `, ${formatMoney(r.commercial_impact, r.currency)}` : ''})`).join(', ')}</div>}

          {DRAFTABLE.has(detail.workflow_status) && <div className="operations-daily-card"><header><div><span className="operations-kicker">BILLING BASIS · BEFORE YOU INVOICE</span></div></header><FinanceBillingBasis projectId={detail.id} refreshKey={basisTick} onUse={applyRecommendation} /></div>}

          {DRAFTABLE.has(detail.workflow_status) && <div className="operations-daily-card operations-span-2">
            <header><div><span className="operations-kicker">ENTRY MODE</span><h3>How would you like to prepare this invoice?</h3></div></header>
            <div className="operations-actions">
              <button type="button" className={`operations-button${entryMode === 'auto_fill' ? '' : ' secondary'}`} disabled={autoFillBusy} onClick={() => void startAutoFill()}>{autoFillBusy ? 'Loading ERP data…' : 'Auto Fill from ERP Data'}</button>
              <button type="button" className={`operations-button${entryMode === 'manual' ? '' : ' secondary'}`} onClick={startManualMode}>Fill Manually</button>
              {entryMode === 'auto_fill' && <span className="nk-meta-chip">AUTO-FILLED FROM ERP</span>}
              {entryMode === 'manual' && <span className="nk-meta-chip">MANUAL INVOICE ENTRY</span>}
            </div>
            {entryMode === 'auto_fill' && autoFillData && <div className="operations-note operations-span-2">
              Client: <strong>{autoFillData.client.name}</strong>{autoFillData.client.gstin ? ` · GSTIN ${autoFillData.client.gstin}` : ''} · Project: <strong>{autoFillData.project.name}</strong> ({autoFillData.project.code}) · Company: <strong>{autoFillData.company.name}</strong>. Use the Billing Basis recommendation above to fill the amount and tax, review every field below, then create the invoice.
            </div>}
          </div>}

          {DRAFTABLE.has(detail.workflow_status) && entryMode != null && <div className="operations-daily-form operations-span-2">
            {(links.estimate_revision_id != null) && <div className="operations-note operations-span-2">Invoice prepared from approved commercial revision{links.billed_quantity != null ? ` · PM-confirmed quantity ${links.billed_quantity}` : ''}{links.billed_milestone_id != null ? ' · PM-confirmed milestone' : ''}. <button type="button" className="cw-link" onClick={() => setLinks(noLinks)}>Clear links</button></div>}
            <div className="operations-note operations-span-2"><strong>INVOICE DETAILS</strong></div>
            <label className="operations-field"><span>Invoice Number</span><input value={invoiceForm.invoice_number} onChange={e => setInvoiceForm({ ...invoiceForm, invoice_number: e.target.value })}/></label>
            <label className="operations-field"><span>Invoice Date</span><input type="date" value={invoiceForm.invoice_date} onChange={e => setInvoiceForm({ ...invoiceForm, invoice_date: e.target.value })}/></label>
            <label className="operations-field"><span>Due Date</span><input type="date" value={invoiceForm.due_date} onChange={e => setInvoiceForm({ ...invoiceForm, due_date: e.target.value })}/></label>
            <label className="operations-field"><span>Currency</span><select value={invoiceForm.currency} onChange={e => setInvoiceForm({ ...invoiceForm, currency: e.target.value, fx_rate_to_inr: e.target.value === 'INR' ? '' : invoiceForm.fx_rate_to_inr })}>{(currencies?.currencies ?? [{code:'INR',name:'Indian Rupee'}]).map(item => <option key={item.code} value={item.code}>{item.code} · {item.name}</option>)}</select></label>
            <label className="operations-field"><span>Payment Terms</span><input value={invoiceForm.payment_terms} onChange={e => setInvoiceForm({ ...invoiceForm, payment_terms: e.target.value })} placeholder="e.g. 30 days"/></label>
            <label className="operations-field"><span>Work Order / PO Reference</span><input value={invoiceForm.po_wo_reference} onChange={e => setInvoiceForm({ ...invoiceForm, po_wo_reference: e.target.value })}/></label>
            <label className="operations-field"><span>Work Order Date</span><input type="date" value={workOrderForm.work_order_date} onChange={e => setWorkOrderForm({ ...workOrderForm, work_order_date: e.target.value })}/></label>
            <label className="operations-field"><span>Dispatch Details</span><input value={workOrderForm.dispatch_details} onChange={e => setWorkOrderForm({ ...workOrderForm, dispatch_details: e.target.value })}/></label>
            <label className="operations-field"><span>Dispatch Date</span><input type="date" value={workOrderForm.dispatch_date} onChange={e => setWorkOrderForm({ ...workOrderForm, dispatch_date: e.target.value })}/></label>
            <label className="operations-field"><span>Destination / Place of Supply</span><input value={workOrderForm.place_of_supply} onChange={e => setWorkOrderForm({ ...workOrderForm, place_of_supply: e.target.value })}/></label>
            {/* V8.7 A4 presentation theme — bound to the existing invoiceForm.theme and sent
                through the existing create payload; stored on the invoice (remembered on reload). */}
            <label className="operations-field"><span>Invoice Theme</span>
              <select value={invoiceForm.theme} onChange={e => setInvoiceForm({ ...invoiceForm, theme: e.target.value })}>
                <option value="blue_classic">Theme 1 — Blue Classic</option>
                <option value="blue_topographic">Theme 2 — Blue Topographic</option>
                <option value="green_gold_premium">Theme 3 — Green Gold Premium</option>
              </select>
            </label>
            {invoiceForm.currency !== 'INR' && <><label className="operations-field"><span>Manual FX to INR (optional)</span><input type="number" min={0.00000001} step="0.00000001" value={invoiceForm.fx_rate_to_inr} onChange={e => setInvoiceForm({ ...invoiceForm, fx_rate_to_inr: e.target.value })}/><small>Leave blank for automatic invoice-date reference rate.</small></label>{invoiceForm.fx_rate_to_inr && <><label className="operations-field"><span>FX Mode</span><select value={invoiceForm.fx_rate_mode} onChange={e => setInvoiceForm({ ...invoiceForm, fx_rate_mode: e.target.value })}><option value="MANUAL_OVERRIDE">Manual Override</option><option value="CONTRACT_RATE">Contract Rate</option><option value="BANK_REALIZATION_RATE">Bank Realization Rate</option><option value="OTHER">Other</option></select></label><label className="operations-field"><span>FX Override Reason *</span><input required value={invoiceForm.fx_override_reason} onChange={e => setInvoiceForm({ ...invoiceForm, fx_override_reason: e.target.value })}/></label></>}</>}

            <div className="operations-note operations-span-2"><strong>LINE ITEMS</strong> · Taxable total: {taxableAmount.toFixed(2)} {invoiceForm.currency}</div>
            <div className="operations-table-wrap operations-span-2"><table className="operations-table">
              <thead><tr><th>#</th><th>Description</th><th>HSN/SAC</th><th>Unit</th><th>Qty</th><th>Rate</th><th>Amount</th><th/></tr></thead>
              <tbody>{lineItems.map(item => <tr key={item.sequence}>
                <td>{item.sequence}</td>
                <td><input value={item.description} onChange={e => updateLineItem(item.sequence, { description: e.target.value })} placeholder="Description"/></td>
                <td><input value={item.hsn_sac} onChange={e => updateLineItem(item.sequence, { hsn_sac: e.target.value })} style={{ width: 80 }}/></td>
                <td><input value={item.unit} onChange={e => updateLineItem(item.sequence, { unit: e.target.value })} style={{ width: 70 }}/></td>
                <td><input type="number" min={0} step="0.001" value={item.quantity} onChange={e => updateLineItem(item.sequence, { quantity: e.target.value })} style={{ width: 70 }}/></td>
                <td><input type="number" min={0} step="0.01" value={item.rate} onChange={e => updateLineItem(item.sequence, { rate: e.target.value })} style={{ width: 100 }}/></td>
                <td>{lineItemAmount(item).toFixed(2)}</td>
                <td><button type="button" className="operations-button secondary" onClick={() => removeLineItem(item.sequence)} aria-label="Remove line item"><Trash2 size={14}/></button></td>
              </tr>)}</tbody>
            </table></div>
            <div className="operations-actions operations-span-2"><button type="button" className="operations-button secondary" onClick={addLineItem}><Plus size={15}/> Add Line Item</button></div>
            {!lineItems.length && <label className="operations-field"><span>Amount (no line items entered)</span><input type="number" min={0} step="0.01" value={invoiceForm.amount} onChange={e => setInvoiceForm({ ...invoiceForm, amount: e.target.value })}/></label>}

            <div className="operations-note operations-span-2"><strong>TAX SUMMARY</strong></div>
            <label className="operations-field"><span>GST Type</span><select value={gstMode} onChange={e => setGstMode(e.target.value as GstMode)}><option value="cgst_sgst">CGST + SGST (same state)</option><option value="igst">IGST (other state)</option><option value="none">Single combined tax / No GST</option></select>{suggestedGstMode && suggestedGstMode !== gstMode && <small>Suggested from GSTIN state codes: {suggestedGstMode === 'igst' ? 'IGST (inter-state)' : 'CGST + SGST (intra-state)'}</small>}</label>
            {gstMode === 'cgst_sgst' && <>
              <label className="operations-field"><span>CGST %</span><input type="number" min={0} max={100} step="0.01" value={gstPercents.cgst} onChange={e => setGstPercents({ ...gstPercents, cgst: e.target.value })}/><small>{gstBreakdown.cgst.toFixed(2)} {invoiceForm.currency}</small></label>
              <label className="operations-field"><span>SGST %</span><input type="number" min={0} max={100} step="0.01" value={gstPercents.sgst} onChange={e => setGstPercents({ ...gstPercents, sgst: e.target.value })}/><small>{gstBreakdown.sgst.toFixed(2)} {invoiceForm.currency}</small></label>
            </>}
            {gstMode === 'igst' && <label className="operations-field"><span>IGST %</span><input type="number" min={0} max={100} step="0.01" value={gstPercents.igst} onChange={e => setGstPercents({ ...gstPercents, igst: e.target.value })}/><small>{gstBreakdown.igst.toFixed(2)} {invoiceForm.currency}</small></label>}
            {gstMode === 'none' && <>
              <label className="operations-field"><span>Tax Amount</span><input type="number" min={0} step="0.01" value={invoiceForm.tax_amount} onChange={e => setInvoiceForm({ ...invoiceForm, tax_amount: e.target.value })}/></label>
              <label className="operations-field"><span>Tax %</span><input type="number" min={0} max={100} step="0.01" value={invoiceForm.tax_percent} onChange={e => setInvoiceForm({ ...invoiceForm, tax_percent: e.target.value })}/></label>
            </>}
            <div className="operations-note operations-span-2">Invoice Value: <strong>{(taxableAmount + gstBreakdown.total).toFixed(2)} {invoiceForm.currency}</strong></div>

            <div className="operations-note operations-span-2"><strong>NOTES</strong></div>
            <label className="operations-field operations-span-2"><span>Notes</span><textarea value={invoiceForm.notes} onChange={e => setInvoiceForm({ ...invoiceForm, notes: e.target.value })} rows={2}/></label>
            <div className="operations-actions"><button className="operations-button" disabled={busy === 'invoice' || !invoiceForm.invoice_number || !invoiceForm.invoice_date || !invoiceForm.due_date || !invoiceForm.amount || lineItems.some(item => !item.description.trim())} onClick={() => void run('invoice', createInvoice, 'Invoice draft created')}>Create Invoice Draft</button></div>
          </div>}

          {detail.invoices.map(invoice => {
            const pay = paymentForm[invoice.id] || { payment_reference: '', payment_date: '', amount: '', payment_mode: 'bank_transfer', comments: '', fx_rate_to_inr: '', fx_rate_mode: 'BANK_REALIZATION_RATE', fx_override_reason: '' }
            const badDebt = invoice.bad_debt
            const badDebtMeta = badDebt ? badDebtStatusMeta(badDebt.status) : null
            const canProposeBadDebt = invoice.status === 'PAYMENT_OVERDUE' && invoice.balance > 0 && invoice.collectible_balance > 0
            const showBadDebtSection = Boolean(badDebt) || canProposeBadDebt
            return <div key={invoice.id} id={`invoice-${invoice.id}`} className="operations-daily-card">
              <div className="operations-daily-heading">
                <div><span className="operations-kicker">{invoice.invoice_number}</span><h3>{formatMoney(invoice.total_amount, invoice.currency)}</h3><p>Due {formatDate(invoice.due_date)} · Paid {formatMoney(invoice.paid_amount, invoice.currency)} · Balance {formatMoney(invoice.balance, invoice.currency)}</p>{invoice.fx_rate_to_inr != null && <p>Invoice FX: 1 {invoice.currency} = ₹{invoice.fx_rate_to_inr.toLocaleString('en-IN',{maximumFractionDigits:8})} · {invoice.fx_rate_date || invoice.invoice_date} · {invoice.fx_rate_source || 'snapshot'}{invoice.fx_locked ? ' · locked' : ''}</p>}{invoice.base_inr != null && <p>INR accounting: base {formatMoney(invoice.base_inr)} · tax {formatMoney(invoice.tax_inr || 0)} · total {formatMoney(invoice.total_inr || 0)}</p>}</div>
                <div className="operations-status-stack">
                  {badDebtMeta && <span className={`operations-status ${badDebtMeta.tone}`}>{badDebtMeta.label}</span>}
                  <span className={`operations-status ${lifecycleStatusTone(invoice.status)}`}>{lifecycleStatusLabel(invoice.status)}</span>
                </div>
              </div>
              <div className="operations-actions">
                <button className="operations-button secondary" disabled={busy === `preview-${invoice.id}`} onClick={() => void previewInvoice(invoice.id)}><Eye size={15}/> A4 Preview</button>
                <button className="operations-button secondary" disabled={busy === `download-${invoice.id}`} onClick={() => void downloadInvoice(invoice.id, invoice.invoice_number)}><Download size={15}/> Download PDF</button>
                <button className="operations-button secondary" disabled={busy === `print-${invoice.id}`} onClick={() => void printInvoice(invoice.id)}><Printer size={15}/> Print</button>
                {canEditDraft && invoice.stored_status === 'INVOICE_DRAFT' && <button className="operations-button secondary" disabled={busy === `edit-${invoice.id}`} onClick={() => openEditInvoice(invoice as unknown as Record<string, unknown>)}><Pencil size={15}/> Edit Draft Details</button>}
                {invoice.stored_status === 'INVOICE_DRAFT' && <button className="operations-button" disabled={busy === `raise-${invoice.id}`} onClick={() => void run(`raise-${invoice.id}`, () => raiseInvoice(invoice.id), 'Invoice raised')}>Raise Invoice</button>}
                {invoice.status === 'PAYMENT_OVERDUE' && invoice.stored_status !== 'PAYMENT_OVERDUE' && <button className="operations-button warning" disabled={busy === `overdue-${invoice.id}`} onClick={() => void run(`overdue-${invoice.id}`, () => markOverdue(invoice.id), 'Invoice marked overdue')}>Mark Overdue</button>}
                {/* V8.7 invoice theme + authorised signature */}
                <select value={invoice.theme || 'blue_classic'} disabled={busy === `theme-${invoice.id}`}
                  onChange={(e) => void changeInvoiceTheme(invoice.id, invoice.invoice_number, e.target.value)}>
                  <option value="blue_classic">Theme 1 — Blue Classic</option>
                  <option value="blue_topographic">Theme 2 — Blue Topographic</option>
                  <option value="green_gold_premium">Theme 3 — Green Gold Premium</option>
                </select>
                {/* Theme Preview is UNCONDITIONAL: every existing invoice (Draft, Raised,
                    Payment Pending, Partially Paid, Overdue, CLOSED) can preview its theme. */}
                <button type="button" className="operations-button secondary" disabled={miniPreviewLoadingId === invoice.id}
                  onClick={() => void openMiniPreview(invoice.id, invoice.invoice_number, invoice.theme || 'blue_classic')}>
                  <Eye size={15}/> {miniPreviewLoadingId === invoice.id ? 'Loading…' : 'Theme Preview'}
                </button>
                {invoice.signed
                  ? <span className="sr-status success">SIGNED{invoice.signed_by_name ? ` by ${invoice.signed_by_name}` : ''}{invoice.signed_at ? ` · ${String(invoice.signed_at).slice(0, 16).replace('T', ' ')}` : ''}</span>
                  : invoice.signature_invalidated_at
                    ? <span className="sr-status warning">UNSIGNED — previous signature invalidated</span>
                    : <span className="sr-status danger">UNSIGNED</span>}
                {!invoice.signed && <button className="operations-button success" disabled={busy === `sign-${invoice.id}`} onClick={() => void run(`sign-${invoice.id}`, () => apiFetch(`/operations/lifecycle/invoices/${invoice.id}/sign`, { method: 'POST' }), 'Invoice signed')}>Sign Invoice</button>}
                <button className="operations-button secondary" disabled={busy === `edit-${invoice.id}`}
                  onClick={() => openEditInvoice(invoice as unknown as Record<string, unknown>)}>Edit Invoice</button>
                {invoice.can_close_invoice && <button className="operations-button success" disabled={busy === `close-${invoice.id}`} onClick={() => void run(`close-${invoice.id}`, () => closeInvoice(invoice.id), 'Invoice closed')}>Close Invoice</button>}
              </div>
              {/* V8.7.x SELECTED THEME PREVIEW — a small A4 thumbnail of the SAME backend PDF
                  (GET .../invoices/{id}/document.pdf), rendered ONLY from persistent miniPreview
                  state. It stays visible until the user clicks Close, opens another invoice's
                  preview, or the Billing page unmounts — it never vanishes on re-render or
                  data refresh. Positioned after the action row and BEFORE the Edit Invoice /
                  Payment / Bad Debt sections. The full [A4 Preview] button above is untouched. */}
              {(miniPreview?.invoiceId === invoice.id || miniPreviewErrorId === invoice.id) && (
                <section className="invoice-theme-mini-preview" aria-label="Selected invoice theme preview">
                  <header className="invoice-theme-mini-header">
                    <div>
                      <span>SELECTED THEME</span>
                      <strong>{miniPreview?.invoiceId === invoice.id ? invoiceThemeLabel(miniPreview.theme) : 'Preview unavailable'}</strong>
                    </div>
                    <button type="button" className="invoice-theme-mini-close" onClick={closeMiniPreview} aria-label="Close theme preview"><X size={16}/></button>
                  </header>
                  {miniPreview?.invoiceId === invoice.id
                    ? <button type="button" className="invoice-theme-mini-paper" onClick={() => void previewInvoice(invoice.id)} title="Open full A4 preview">
                        {/* Real backend PDF; pointer-events:none keeps the embedded viewer from
                            stealing scroll/focus — the paper button handles the click and opens
                            the EXISTING full A4 preview. */}
                        <iframe src={`${miniPreview.url}#toolbar=0&navpanes=0&scrollbar=0&view=Fit`} title={`${miniPreview.invoiceNumber} selected invoice theme`} tabIndex={-1}/>
                      </button>
                    : <div className="invoice-theme-mini-failure">Preview unavailable{miniPreviewError ? ` — ${miniPreviewError}` : ''}</div>}
                  <div className="invoice-theme-mini-actions">
                    <button type="button" className="operations-button secondary" onClick={() => void previewInvoice(invoice.id)}><Eye size={15}/> Open A4 Preview</button>
                    <button type="button" className="operations-button secondary" onClick={closeMiniPreview}><X size={15}/> Close</button>
                  </div>
                </section>
              )}
              {/* V8.7 EDIT INVOICE — pre-filled from the existing record; saves via backend PATCH. */}
              {editInvoiceId === invoice.id && (
                <div className="operations-daily-form">
                  <label className="operations-field"><span>Invoice Date</span><input type="date" value={editForm.invoice_date ?? ''} onChange={e => setEditForm({ ...editForm, invoice_date: e.target.value })}/></label>
                  <label className="operations-field"><span>Due Date</span><input type="date" value={editForm.due_date ?? ''} onChange={e => setEditForm({ ...editForm, due_date: e.target.value })}/></label>
                  <label className="operations-field"><span>Amount</span><input type="number" step="0.01" value={editForm.amount ?? ''} onChange={e => setEditForm({ ...editForm, amount: e.target.value })}/></label>
                  <label className="operations-field"><span>GST Type</span>
                    <select value={editForm.gst_mode ?? 'none'} onChange={e => setEditForm({ ...editForm, gst_mode: e.target.value })}>
                      <option value="cgst_sgst">CGST + SGST (same state)</option>
                      <option value="igst">IGST (other state)</option>
                      <option value="none">Single combined tax / No GST</option>
                    </select>
                  </label>
                  {editForm.gst_mode === 'cgst_sgst' && <>
                    <label className="operations-field"><span>CGST %</span><input type="number" min={0} max={100} step="0.01" value={editForm.cgst_percent ?? ''} onChange={e => setEditForm({ ...editForm, cgst_percent: e.target.value })}/><small>{editGst.cgst.toFixed(2)} {invoice.currency}</small></label>
                    <label className="operations-field"><span>SGST %</span><input type="number" min={0} max={100} step="0.01" value={editForm.sgst_percent ?? ''} onChange={e => setEditForm({ ...editForm, sgst_percent: e.target.value })}/><small>{editGst.sgst.toFixed(2)} {invoice.currency}</small></label>
                  </>}
                  {editForm.gst_mode === 'igst' && <label className="operations-field"><span>IGST %</span><input type="number" min={0} max={100} step="0.01" value={editForm.igst_percent ?? ''} onChange={e => setEditForm({ ...editForm, igst_percent: e.target.value })}/><small>{editGst.igst.toFixed(2)} {invoice.currency}</small></label>}
                  {(editForm.gst_mode ?? 'none') === 'none'
                    ? <>
                      <label className="operations-field"><span>Tax Amount</span><input type="number" step="0.01" value={editForm.tax_amount ?? ''} onChange={e => setEditForm({ ...editForm, tax_amount: e.target.value })}/></label>
                      <label className="operations-field"><span>Tax %</span><input type="number" min={0} max={100} step="0.01" value={editForm.tax_percent ?? ''} onChange={e => setEditForm({ ...editForm, tax_percent: e.target.value })}/></label>
                    </>
                    : <div className="operations-note">Tax Amount: <strong>{editGst.total.toFixed(2)} {invoice.currency}</strong> (calculated from Amount)</div>}
                  <label className="operations-field"><span>Payment Terms</span><input value={editForm.payment_terms ?? ''} onChange={e => setEditForm({ ...editForm, payment_terms: e.target.value })}/></label>
                  <label className="operations-field"><span>PO / WO Reference</span><input value={editForm.po_wo_reference ?? ''} onChange={e => setEditForm({ ...editForm, po_wo_reference: e.target.value })}/></label>
                  <label className="operations-field"><span>Place of Supply</span><input value={editForm.place_of_supply ?? ''} onChange={e => setEditForm({ ...editForm, place_of_supply: e.target.value })}/></label>
                  <label className="operations-field"><span>Dispatch Details</span><input value={editForm.dispatch_details ?? ''} onChange={e => setEditForm({ ...editForm, dispatch_details: e.target.value })}/></label>
                  <label className="operations-field"><span>Notes</span><input value={editForm.notes ?? ''} onChange={e => setEditForm({ ...editForm, notes: e.target.value })}/></label>
                  <label className="operations-field"><span>Invoice Theme</span>
                    <select value={editForm.theme ?? 'blue_classic'} onChange={e => setEditForm({ ...editForm, theme: e.target.value })}>
                      <option value="blue_classic">Theme 1 — Blue Classic</option>
                      <option value="blue_topographic">Theme 2 — Blue Topographic</option>
                      <option value="green_gold_premium">Theme 3 — Green Gold Premium</option>
                    </select>
                  </label>
                  <div className="operations-actions">
                    <button className="operations-button" disabled={busy === `edit-${invoice.id}`} onClick={() => void saveEditInvoice(invoice.id)}>Save Changes</button>
                    <button className="operations-button secondary" onClick={() => setEditInvoiceId(null)}>Cancel</button>
                  </div>
                  <div className="operations-note">
                    Financial fields are refused by the backend once a payment or Bad Debt case exists;
                    the invoice number and record are never duplicated. A material change to a signed
                    invoice clears its signature (re-sign afterwards).
                  </div>
                </div>
              )}
              {PAYABLE.has(invoice.stored_status) && invoice.collectible_balance > 0 && <div className="operations-daily-form">
                <label className="operations-field"><span>Payment Reference</span><input value={pay.payment_reference} onChange={e => setPaymentForm({ ...paymentForm, [invoice.id]: { ...pay, payment_reference: e.target.value } })}/></label>
                <label className="operations-field"><span>Payment Date</span><input type="date" value={pay.payment_date} onChange={e => setPaymentForm({ ...paymentForm, [invoice.id]: { ...pay, payment_date: e.target.value } })}/></label>
                <label className="operations-field"><span>Amount</span><input type="number" min={0} step="0.01" max={invoice.collectible_balance} value={pay.amount} onChange={e => setPaymentForm({ ...paymentForm, [invoice.id]: { ...pay, amount: e.target.value } })}/></label>
                <label className="operations-field"><span>Mode</span><select value={pay.payment_mode} onChange={e => setPaymentForm({ ...paymentForm, [invoice.id]: { ...pay, payment_mode: e.target.value } })}><option value="bank_transfer">Bank Transfer</option><option value="upi">UPI</option><option value="cheque">Cheque</option><option value="cash">Cash</option><option value="card">Card</option></select></label>
                {invoice.currency !== 'INR' && <><label className="operations-field"><span>Manual Realization FX (optional)</span><input type="number" min={0.00000001} step="0.00000001" value={pay.fx_rate_to_inr} onChange={e => setPaymentForm({ ...paymentForm, [invoice.id]: { ...pay, fx_rate_to_inr: e.target.value } })}/><small>Blank = automatic payment-date rate.</small></label>{pay.fx_rate_to_inr && <><label className="operations-field"><span>FX Mode</span><select value={pay.fx_rate_mode} onChange={e => setPaymentForm({ ...paymentForm, [invoice.id]: { ...pay, fx_rate_mode: e.target.value } })}><option value="BANK_REALIZATION_RATE">Bank Realization Rate</option><option value="MANUAL_OVERRIDE">Manual Override</option><option value="CONTRACT_RATE">Contract Rate</option><option value="OTHER">Other</option></select></label><label className="operations-field"><span>FX Reason *</span><input required value={pay.fx_override_reason} onChange={e => setPaymentForm({ ...paymentForm, [invoice.id]: { ...pay, fx_override_reason: e.target.value } })}/></label></>}</>}
                <label className="operations-field operations-span-2"><span>Payment Comments</span><input value={pay.comments} onChange={e => setPaymentForm({ ...paymentForm, [invoice.id]: { ...pay, comments: e.target.value } })}/></label>
                {badDebt?.status === 'APPROVED' && <div className="operations-note operations-span-2">Normal Record Payment is limited to the collectible balance outside the approved write-off. Use Record Recovery below for money received against the written-off amount.</div>}
                <div className="operations-actions"><button className="operations-button" disabled={busy === `pay-${invoice.id}` || !pay.payment_reference || !pay.payment_date || !pay.amount} onClick={() => void run(`pay-${invoice.id}`, () => recordPayment(invoice), 'Payment recorded with payment-date FX realization')}>Record Payment</button></div>
              </div>}
              {showBadDebtSection && (() => {
                const form = badDebtForm[invoice.id] || blankBadDebtForm()
                const recovery = recoveryForm[invoice.id] || blankRecoveryForm()
                const unrecovered = badDebt && badDebt.approved_amount != null
                  ? Math.max(badDebt.approved_amount - (badDebt.recovered_amount || 0), 0)
                  : 0
                const eligible = invoice.collectible_balance
                return <div className="operations-daily-form" aria-label="Bad Debt / Collection Action">
                  <div className="operations-note operations-span-2"><strong>BAD DEBT / COLLECTION ACTION</strong> · Escalation and write-off path for an overdue invoice. Bad Debt is never a payment and never Revenue. Record Payment above stays available for normal collection.</div>
                  <div className="operations-note operations-span-2">
                    Invoice Value <strong>{formatMoney(invoice.total_amount, invoice.currency)}</strong> · Cash Received <strong>{formatMoney(invoice.paid_amount, invoice.currency)}</strong> · Current Balance <strong>{formatMoney(invoice.balance, invoice.currency)}</strong><br/>
                    Due Date <strong>{formatDate(invoice.due_date)}</strong> · Days Overdue <strong>{invoice.days_overdue ?? 0}</strong> · Eligible Bad Debt Amount <strong>{formatMoney(eligible, invoice.currency)}</strong>
                  </div>

                  {canProposeBadDebt && (!badDebt || badDebt.status === 'REJECTED') && <>
                    <label className="operations-field"><span>Bad Debt Amount (blank = eligible)</span><input type="number" min={0} step="0.01" max={eligible} placeholder={eligible.toFixed(2)} value={form.proposed_amount} onChange={e => setBadDebtForm({ ...badDebtForm, [invoice.id]: { ...form, proposed_amount: e.target.value } })}/><small>Defaults to {formatMoney(eligible, invoice.currency)} when left blank.</small></label>
                    <label className="operations-field"><span>Reason *</span><input value={form.reason} placeholder="Why collection has failed" onChange={e => setBadDebtForm({ ...badDebtForm, [invoice.id]: { ...form, reason: e.target.value } })}/></label>
                    <label className="operations-field"><span>Last Follow-up Date</span><input type="date" value={form.last_followup_date} onChange={e => setBadDebtForm({ ...badDebtForm, [invoice.id]: { ...form, last_followup_date: e.target.value } })}/></label>
                    <label className="operations-field operations-span-2"><span>Collection Attempts / Collection Notes *</span><textarea rows={2} value={form.collection_attempts} placeholder="Emails, calls and meetings already attempted" onChange={e => setBadDebtForm({ ...badDebtForm, [invoice.id]: { ...form, collection_attempts: e.target.value } })}/></label>
                    <label className="operations-field operations-span-2"><span>Remarks</span><textarea rows={2} value={form.finance_remarks} onChange={e => setBadDebtForm({ ...badDebtForm, [invoice.id]: { ...form, finance_remarks: e.target.value } })}/></label>
                    <div className="operations-actions operations-span-2">
                      <button className="operations-button warning" disabled={busy === `bad-debt-${invoice.id}` || form.reason.trim().length < 3 || form.collection_attempts.trim().length < 3} onClick={() => void run(`bad-debt-${invoice.id}`, () => proposeBadDebt(invoice), 'Bad Debt proposal sent to Management')}>Propose Bad Debt to Management</button>
                    </div>
                  </>}

                  {badDebt?.status === 'PROPOSED' && <div className="operations-alert">
                    <strong>Bad Debt Proposal</strong><br/>
                    Amount: {formatMoney(badDebt.proposed_amount, invoice.currency)}<br/>
                    Status: Awaiting Management Approval<br/>
                    Reason: {badDebt.reason}<br/>
                    Proposed By: {badDebt.proposed_by_name || 'Finance'} · {formatDateTime(badDebt.proposed_at)}<br/>
                    Collection Attempts: {badDebt.collection_attempts}
                    {badDebt.finance_remarks && <><br/>Remarks: {badDebt.finance_remarks}</>}
                    <br/><small>Awaiting Management decision. No duplicate proposal can be filed, and Record Payment remains available.</small>
                  </div>}

                  {badDebt?.status === 'REJECTED' && <div className="operations-alert error">
                    <strong>Bad Debt Proposal Rejected</strong> · Management chose to continue collection.<br/>
                    Reason: {badDebt.decision_reason || '—'} · Reviewed by {badDebt.reviewed_by_name || 'Management'}{badDebt.reviewed_at ? ` · ${formatDateTime(badDebt.reviewed_at)}` : ''}
                    <br/><small>The invoice stays overdue and collectible. Propose again, or keep collecting with Record Payment.</small>
                  </div>}

                  {(badDebt?.status === 'APPROVED' || badDebt?.status === 'RECOVERED') && <div className="operations-alert success">
                    <strong>Bad Debt {badDebt.status === 'RECOVERED' ? 'Recovered' : 'Approved / Written Off'}</strong><br/>
                    Written Off: {formatMoney(badDebt.approved_amount ?? 0, invoice.currency)} · Recovered: {formatMoney(badDebt.recovered_amount || 0, invoice.currency)} · Remaining unrecovered: {formatMoney(unrecovered, invoice.currency)}<br/>
                    Reason: {badDebt.reason}<br/>
                    Approved by {badDebt.reviewed_by_name || 'Management'}{badDebt.reviewed_at ? ` · ${formatDateTime(badDebt.reviewed_at)}` : ''}
                    {badDebt.decision_reason && <><br/>Decision: {badDebt.decision_reason}</>}
                  </div>}

                  {badDebt?.status === 'APPROVED' && unrecovered > 0 && <>
                    <div className="operations-note operations-span-2"><strong>RECORD RECOVERY</strong> · Real cash received back against the write-off. Booked through the normal payment path; the original Bad Debt record is preserved.</div>
                    <label className="operations-field"><span>Recovery Amount</span><input type="number" min={0} step="0.01" max={unrecovered} placeholder={unrecovered.toFixed(2)} value={recovery.amount} onChange={e => setRecoveryForm({ ...recoveryForm, [invoice.id]: { ...recovery, amount: e.target.value } })}/><small>Unrecovered balance {formatMoney(unrecovered, invoice.currency)}</small></label>
                    <label className="operations-field"><span>Payment Date</span><input type="date" value={recovery.payment_date} onChange={e => setRecoveryForm({ ...recoveryForm, [invoice.id]: { ...recovery, payment_date: e.target.value } })}/></label>
                    <label className="operations-field"><span>Payment Reference / UTR</span><input value={recovery.payment_reference} onChange={e => setRecoveryForm({ ...recoveryForm, [invoice.id]: { ...recovery, payment_reference: e.target.value } })}/></label>
                    <label className="operations-field"><span>Mode</span><select value={recovery.payment_mode} onChange={e => setRecoveryForm({ ...recoveryForm, [invoice.id]: { ...recovery, payment_mode: e.target.value } })}><option value="bank_transfer">Bank Transfer</option><option value="upi">UPI</option><option value="cheque">Cheque</option><option value="cash">Cash</option><option value="card">Card</option></select></label>
                    <label className="operations-field operations-span-2"><span>Remarks</span><textarea rows={2} value={recovery.remarks} onChange={e => setRecoveryForm({ ...recoveryForm, [invoice.id]: { ...recovery, remarks: e.target.value } })}/></label>
                    <div className="operations-actions operations-span-2">
                      <button className="operations-button success" disabled={busy === `recover-${invoice.id}` || !recovery.amount || !recovery.payment_date || !recovery.payment_reference} onClick={() => void run(`recover-${invoice.id}`, () => recordRecovery(invoice), 'Recovery recorded against the Bad Debt write-off')}>Record Recovery</button>
                    </div>
                  </>}
                </div>
              })()}
              {!!invoice.payments.length && <div className="operations-table-wrap"><table className="operations-table"><thead><tr><th>Reference</th><th>Date</th><th>Amount</th><th>Realization FX</th><th>INR Realized</th><th>FX Gain / Loss</th><th>Mode</th></tr></thead><tbody>{invoice.payments.map(p => <tr key={p.id}><td>{p.payment_reference}</td><td>{formatDate(p.payment_date)}</td><td>{formatMoney(p.amount, p.payment_currency || invoice.currency)}</td><td>{p.fx_rate_to_inr == null ? '—' : `₹${p.fx_rate_to_inr.toLocaleString('en-IN',{maximumFractionDigits:8})}`}<br/><small>{p.fx_rate_date || ''} {p.fx_rate_source ? `· ${p.fx_rate_source}` : ''}</small></td><td>{p.inr_equivalent == null ? '—' : formatMoney(p.inr_equivalent)}</td><td>{p.fx_gain_loss_inr == null ? '—' : formatMoney(p.fx_gain_loss_inr)}</td><td>{p.payment_mode}</td></tr>)}</tbody></table></div>}
            </div>
          })}
          {!detail.invoices.length && <div className="nk-empty">
            <span className="nk-empty-icon"><FileText size={22}/></span>
            <h3>No invoices yet for this project</h3>
            <p>{DRAFTABLE.has(detail.workflow_status) ? 'Create the first invoice draft from the billing form above — it will appear here for raising and payment tracking.' : 'Invoices appear here once this project reaches Ready For Billing and Finance drafts the first invoice.'}</p>
          </div>}
        </>}
      </section>
    </div>
    <section className="operations-panel">
      <header><div><span className="operations-kicker">SEPARATE FINANCE TRACKING</span><h2>Bad Debt Register</h2></div><span className="nk-meta-chip">Not Revenue</span></header>
      {!badDebts.length ? <div className="operations-empty">No Bad Debt proposals or write-offs recorded.</div> : <div className="operations-table-wrap"><table className="operations-table"><thead><tr><th>Project</th><th>Invoice</th><th>Status</th><th>Proposed</th><th>Approved / Net</th><th>Reason</th></tr></thead><tbody>{badDebts.map(row => <tr key={row.id}><td>{row.project_code || row.project_id}</td><td>{row.invoice_number || row.invoice_id}</td><td>{(() => { const meta = badDebtStatusMeta(row.status); return <span className={`operations-status ${meta.tone}`}>{meta.label}</span> })()}</td><td>{formatMoney(row.proposed_amount, row.currency || 'INR')}</td><td>{row.approved_amount == null ? '—' : `${formatMoney(row.approved_amount, row.currency || 'INR')} / ${formatMoney(row.net_bad_debt, row.currency || 'INR')}`}</td><td>{row.reason}</td></tr>)}</tbody></table></div>}
    </section>
    {preview && <div className="invoice-preview-backdrop" role="presentation" onMouseDown={() => setPreview(null)}>
      <section className="invoice-preview-dialog" role="dialog" aria-modal="true" aria-labelledby="invoice-preview-title" onMouseDown={event => event.stopPropagation()}>
        <header className="invoice-preview-toolbar">
          <div><span>A4 INVOICE PREVIEW</span><h2 id="invoice-preview-title">{preview.invoice.invoice_number}</h2><p>Read-only preview from the existing ProjectInvoice record{preview.entry_mode ? ` · ${preview.entry_mode === 'auto_fill' ? 'Auto-filled from ERP' : 'Manual entry'}` : ''}</p></div>
          <div className="invoice-preview-actions">
            <button type="button" onClick={() => void downloadInvoice(preview.invoice.id, preview.invoice.invoice_number)}><Download size={16}/> Download PDF</button>
            <button type="button" onClick={() => void printInvoice(preview.invoice.id)}><Printer size={16}/> Print</button>
            <button type="button" className="invoice-preview-close" onClick={() => setPreview(null)} aria-label="Close invoice preview"><X size={19}/></button>
          </div>
        </header>
        <div className="invoice-preview-scroll-area"><InvoiceA4Document invoice={preview} template={template}/></div>
        {/*
          ERP-ONLY settlement panel (STEP 12).
          This is a Finance screen aid and is deliberately NOT part of the printable
          A4 sheet: the generated PDF and the print output never include it, while the
          underlying advance/payment data stays untouched in the ERP ledgers.
        */}
        {preview.settlement && (preview.settlement.advance_applied > 0 || preview.settlement.cash_received > 0) && (
          <section className="invoice-erp-settlement" aria-label="ERP settlement summary">
            <header><span>Settlement Summary (ERP only)</span><strong>Not printed on the tax invoice</strong></header>
            <div>
              <div><span>Advance Applied</span><strong>{formatMoney(preview.settlement.advance_applied)}</strong></div>
              <div><span>Cash Received</span><strong>{formatMoney(preview.settlement.cash_received)}</strong></div>
              <div><span>Total Settled</span><strong>{formatMoney(preview.settlement.total_settled)}</strong></div>
              <div><span>Outstanding</span><strong>{formatMoney(preview.settlement.outstanding)}</strong></div>
              <div><span>Payment Status</span><strong><span className="advance-status" data-status={preview.settlement.status}>{preview.settlement.status}</span></strong></div>
            </div>
          </section>
        )}
      </section>
    </div>}
  </div>
}
