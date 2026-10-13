import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'

const root = process.cwd()
const pageSource = fs.readFileSync(path.join(root, 'src/features/finance/pages/FinanceBillingPage.tsx'), 'utf8')
const cssSource = fs.readFileSync(path.join(root, 'src/features/finance/invoice-document.css'), 'utf8')

// ---------------------------------------------------------------------------
// ProjectInvoice stays the only source of truth: no new invoice entity/page,
// the existing Raise Invoice / Record Payment workflow is extended in place.
// ---------------------------------------------------------------------------
assert.ok(pageSource.includes('/operations/lifecycle/invoices/${invoiceId}/document'), 'preview must read the canonical document endpoint')
assert.ok(pageSource.includes('/operations/lifecycle/invoices/${invoiceId}/document.pdf?download=true'), 'download must use the PDF download endpoint')
assert.ok(pageSource.includes('/operations/lifecycle/invoices/${invoiceId}/document.pdf'), 'print must fetch the inline PDF endpoint')
assert.ok(pageSource.includes('A4 Preview') && pageSource.includes('Download PDF') && pageSource.includes('Print'), 'three invoice actions must be exposed per invoice row')
assert.ok(!/invoice-generation|InvoiceGeneration/i.test(pageSource), 'no separate Invoice Generation concept must be introduced')

// ---------------------------------------------------------------------------
// Print must render the authoritative PDF itself (native browser print of the
// generated document), not an HTML approximation riddled with ERP chrome.
// ---------------------------------------------------------------------------
assert.ok(pageSource.includes("window.open('', '_blank')"), 'print must open a dedicated blank window, never print the ERP shell in place')
assert.ok(pageSource.includes('printWindow.print()'), 'print must invoke the native print dialog on the loaded PDF')
assert.ok(pageSource.includes('printWindow.opener = null'), 'print window must not hold a back-reference (reverse tabnabbing guard)')

// ---------------------------------------------------------------------------
// A4 preview sheet dimensions and read-only framing.
// ---------------------------------------------------------------------------
assert.ok(cssSource.includes('794px') && cssSource.includes('1123px'), 'preview sheet must use A4 @96dpi dimensions (794x1123)')
assert.ok(pageSource.includes('Read-only preview from the existing ProjectInvoice record'), 'preview must be labelled read-only')
// The printable A4 sheet lives in the shared document component (STEP 10): both
// the project invoice and the standalone invoice render the SAME visual document.
const documentSource = fs.readFileSync(path.join(root, 'src/features/finance/components/InvoiceA4Document.tsx'), 'utf8')
assert.ok(pageSource.includes('<InvoiceA4Document'), 'the billing preview must use the shared A4 document component')
for (const section of ['invoice-a4-brand', 'invoice-a4-header-strip', 'invoice-a4-meta', 'invoice-a4-parties', 'invoice-a4-table', 'invoice-a4-totals', 'invoice-a4-signature']) {
  assert.ok(documentSource.includes(section), `shared A4 document must render the ${section} section`)
}
assert.ok(documentSource.includes('Amount Chargeable (in words)'), 'A4 document must show amount in words')
assert.ok(!documentSource.includes('SETTLEMENT SUMMARY'), 'the printable A4 document must NOT contain a settlement summary (STEP 12)')
// STEP 12: settlement data stays on the ERP Finance screen only.
assert.ok(pageSource.includes('Settlement Summary') && pageSource.includes('preview.settlement.advance_applied') && pageSource.includes('preview.settlement.outstanding'), 'the ERP preview must show the advance/cash settlement summary')
assert.ok(pageSource.includes("preview.settlement.advance_applied > 0 || preview.settlement.cash_received > 0"), 'settlement summary must be conditional on actual payment activity, not shown as all-zero noise')
assert.ok(pageSource.includes('invoice-erp-settlement'), 'the ERP settlement panel must be clearly separate from the printable sheet')

// ---------------------------------------------------------------------------
// ISSUE 1: every item row must close with a clean, continuous separator that
// spans the complete table width (no open Description cell), drawn with thin
// per-cell borders rather than a collapsed grid inside the overflow wrapper.
// ---------------------------------------------------------------------------
const tableCss = (cssSource.match(/\.invoice-a4-table[^{]*\{[^}]*\}/g) || []).join('\n')
assert.ok(/\.invoice-a4-table\{[^}]*border-collapse:separate/.test(tableCss), 'the item table must use separated borders so the row separator is not clipped by the scroll wrapper')
assert.ok(/\.invoice-a4-table th,\.invoice-a4-table td\{[^}]*border-bottom:1px solid/.test(tableCss), 'every item cell must carry a bottom rule so each row closes across the full table width')
assert.ok(/\.invoice-a4-table th,\.invoice-a4-table td\{[^}]*border-right:1px solid/.test(tableCss), 'the item table must keep subtle vertical column separators')
assert.ok(!/\.invoice-a4-table td\{[^}]*border:1px solid #cbd5e1/.test(tableCss), 'the old collapsed-grid border shorthand must not reappear on item cells')
assert.ok(/\.invoice-a4-table th\{[^}]*border-bottom:1px solid #08a8c4/.test(tableCss), 'the item table header must keep its clear NakshaTech cyan underline')

// ---------------------------------------------------------------------------
// Preview alignment (section 16): toolbar fixed, a dedicated scroll area below
// it, the A4 sheet itself never scrolls directly, and scrollbar-gutter keeps
// the page from shifting sideways when the scrollbar appears.
// ---------------------------------------------------------------------------
assert.ok(pageSource.includes('invoice-preview-scroll-area'), 'preview must wrap the A4 sheet in a dedicated scroll area')
assert.ok(cssSource.includes('grid-template-rows:auto 1fr'), 'dialog must keep the toolbar fixed and let the scroll area fill the rest')
assert.ok(cssSource.includes('scrollbar-gutter:stable'), 'scroll area must reserve scrollbar space so the sheet never shifts')

// ---------------------------------------------------------------------------
// Invoice Generation V2: entry mode selector, line items editor, GST split.
// ---------------------------------------------------------------------------
assert.ok(pageSource.includes('Auto Fill from ERP Data') && pageSource.includes('Fill Manually'), 'entry mode selector must offer Auto Fill and Manual options')
assert.ok(pageSource.includes("/invoices/auto-fill"), 'Auto Fill must call the read-only auto-fill endpoint')
assert.ok(pageSource.includes('AUTO-FILLED FROM ERP') && pageSource.includes('MANUAL INVOICE ENTRY'), 'entry mode badge must be shown once a mode is chosen')
assert.ok(pageSource.includes('Add Line Item') && pageSource.includes('removeLineItem'), 'line item editor must support add and delete before raise')
for (const field of ['hsn_sac', 'quantity', 'rate']) {
  assert.ok(pageSource.includes(field), `line item editor must capture ${field}`)
}
assert.ok(pageSource.includes("'cgst_sgst'") && pageSource.includes("'igst'"), 'tax summary must support both CGST+SGST and IGST modes')
assert.ok(pageSource.includes('line_items:') && pageSource.includes('cgst_percent') && pageSource.includes('work_order_date'), 'invoice create payload must send line items, GST split and work order fields')

// ---------------------------------------------------------------------------
// Existing Billing page behaviour must not be removed: Raise Invoice / Record
// Payment handlers stay present alongside the new document actions.
// ---------------------------------------------------------------------------
for (const existing of ['raiseInvoice', 'recordPayment', 'closeInvoice']) {
  assert.ok(new RegExp(existing, 'i').test(pageSource), `existing ${existing} workflow must remain present`)
}

console.log('FINANCE COMMAND CENTER / BILLING A4 INVOICE DOCUMENT (V2) VERIFICATION PASSED')
console.log('- Preview/Download/Print wired to the existing ProjectInvoice document endpoints only')
console.log('- No second invoice entity or Invoice Generation navigation introduced')
console.log('- Print opens a dedicated window and prints the authoritative PDF (no ERP chrome to leak)')
console.log('- A4 preview sheet uses 794x1123px (A4 @96dpi), scroll-isolated, and explicitly labelled read-only')
console.log('- Settlement summary renders only once there is real payment activity')
console.log('- Entry Mode selector (Auto Fill / Manual) gates a common line-item + GST-split editor')
console.log('- Create payload carries line items, CGST/SGST/IGST and work-order/dispatch/destination fields')
console.log('- Existing Raise Invoice / Record Payment / Close Invoice handlers remain in place')
