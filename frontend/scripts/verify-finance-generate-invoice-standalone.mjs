import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'

const root = process.cwd()
const read = (...parts) => fs.readFileSync(path.join(root, ...parts), 'utf8')

const appSource = read('src/App.tsx')
const layoutSource = read('src/components/Layout.tsx')
const pageSource = read('src/features/finance/pages/GenerateInvoicePage.tsx')
const billingSource = read('src/features/finance/pages/FinanceBillingPage.tsx')
const documentSource = read('src/features/finance/components/InvoiceA4Document.tsx')
const cssSource = read('src/features/finance/invoice-document.css')

// ---------------------------------------------------------------------------
// Sidebar: Billing & Invoices -> Generate Invoice -> Commercial Control
// ---------------------------------------------------------------------------
const billingIndex = layoutSource.indexOf("to: '/finance/billing'")
const generateIndex = layoutSource.indexOf("to: '/finance/generate-invoice'")
const commercialIndex = layoutSource.indexOf("to: '/finance/commercial'")
assert.ok(billingIndex !== -1 && generateIndex !== -1 && commercialIndex !== -1, 'all three Finance items must exist')
assert.ok(billingIndex < generateIndex && generateIndex < commercialIndex, 'sidebar order must be Billing -> Generate -> Commercial')
assert.ok(layoutSource.includes("label: 'Generate Invoice'"), 'the item must be labelled Generate Invoice')
assert.ok(/to: '\/finance\/generate-invoice', label: 'Generate Invoice'.*roles: \['finance'\]/.test(layoutSource), 'Generate Invoice must be Finance-only in the sidebar')
assert.ok(layoutSource.includes('FilePlus2'), 'a Lucide icon must be used for the new item')

// ---------------------------------------------------------------------------
// Route: Finance-only, and Billing & Invoices is untouched
// ---------------------------------------------------------------------------
assert.ok(appSource.includes('path="/finance/generate-invoice"'), 'the Generate Invoice route must exist')
assert.ok(/path="\/finance\/generate-invoice" element=\{<ProtectedRoute roles=\{\['finance'\]\}/.test(appSource), 'the route must be Finance-only')
assert.ok(/path="\/finance\/billing" element=\{<ProtectedRoute roles=\{\['finance', 'admin', 'management'\]\}/.test(appSource), 'existing Billing & Invoices route must not change')
assert.ok(appSource.includes('GenerateInvoicePage'), 'the page must be routed')

// ---------------------------------------------------------------------------
// Manual form sections
// ---------------------------------------------------------------------------
for (const section of ['INVOICE DETAILS', 'SELLER', 'BILL TO', 'SHIP TO', 'LINE ITEMS', 'TAX & TOTALS', 'BANK DETAILS', 'FINAL DETAILS']) {
  assert.ok(pageSource.includes(section), `form section must exist: ${section}`)
}
for (const field of ['invoice_number', 'invoice_date', 'terms', 'due_date', 'reference_work_order', 'place_of_supply']) {
  assert.ok(pageSource.includes(`invoice.${field}`), `invoice detail field must exist: ${field}`)
}
for (const field of ['msme_registration', 'website', 'gstin', 'pan']) {
  assert.ok(pageSource.includes(field), `seller/bill-to field must exist: ${field}`)
}
for (const field of ['bank_name', 'account_name', 'account_number', 'ifsc_code', 'swift_code', 'bank_address']) {
  assert.ok(pageSource.includes(field), `bank field must exist: ${field}`)
}
assert.ok(/bank\[key as keyof BankForm\]/.test(pageSource), 'bank inputs must bind to the bank form state')
assert.ok(/bank: Object\.fromEntries/.test(pageSource), 'bank details must be part of the payload built by the page')
// ---------------------------------------------------------------------------
// Line items: add / remove, 1..N
// ---------------------------------------------------------------------------
assert.ok(/setItems\(current => \[\.\.\.current/.test(pageSource), 'line items must be addable')
assert.ok(/standalone-remove-line/.test(pageSource), 'line items must be removable')
assert.ok(pageSource.includes('Trash2'), 'a delete affordance must exist per line item')
assert.ok(pageSource.includes('blankItem()'), 'new rows start from a blank item')
assert.ok(/Add Line Item/.test(pageSource), 'an add control must be labelled')
assert.ok(pageSource.includes('key={item.id}'), 'line items must be keyed so add/remove stays stable')
assert.ok(pageSource.includes('items.length === 1'), 'the last remaining line item must not be removable')

// ---------------------------------------------------------------------------
// Tax: CGST+SGST OR IGST, never hardcoded 9+9/18
// ---------------------------------------------------------------------------
assert.ok(pageSource.includes("taxMode === 'cgst_sgst'") && pageSource.includes("taxMode === 'igst'"), 'both GST modes must be supported')
assert.ok(pageSource.includes('taxes.cgst') && pageSource.includes('taxes.sgst') && pageSource.includes('taxes.igst'), 'CGST, SGST and IGST inputs must be editable')
assert.ok(/<option value="none">No GST<\/option>/.test(pageSource), 'an explicit no-tax mode must exist')
assert.ok(pageSource.includes('tax_mode: taxMode'), 'the chosen mode must reach the backend payload')

// ---------------------------------------------------------------------------
// Preview / PDF / Print all come from the same backend payload
// ---------------------------------------------------------------------------
assert.ok(pageSource.includes('/finance/generated-invoices'), 'the standalone API base path must be used')
assert.ok(pageSource.includes('/document.pdf'), 'the shared PDF endpoint must be reused')
assert.ok(pageSource.includes('<InvoiceA4Document'), 'preview must render the shared A4 document')
assert.ok(pageSource.includes('setPreview'), 'preview must be shown')
assert.ok(pageSource.includes('apiBlob'), 'PDF download must stream the backend document')
assert.ok(pageSource.includes('Download PDF') && pageSource.includes('Print'), 'preview must offer download and print')

// ---------------------------------------------------------------------------
// History: document fields only, no accounting columns
// ---------------------------------------------------------------------------
assert.ok(pageSource.includes('STANDALONE HISTORY'), 'a standalone history section must exist')
for (const column of ['Invoice', 'Date', 'Party', 'Total', 'Created By', 'Created At']) {
  assert.ok(pageSource.includes(`<th>${column}</th>`), `history column must exist: ${column}`)
}
for (const forbidden of ['Payment Pending', 'Partial Payment', 'Outstanding', 'Revenue']) {
  assert.ok(!pageSource.includes(`<th>${forbidden}</th>`), `history must NOT show ${forbidden}`)
}

// ---------------------------------------------------------------------------
// Absolute isolation: the standalone page must not touch project accounting
// ---------------------------------------------------------------------------
for (const forbidden of ['advance-payments', 'command-center', 'sales-revenue', 'client-register']) {
  assert.ok(!pageSource.includes(forbidden), `standalone page must not call ${forbidden}`)
}
assert.ok(!pageSource.includes('applyAdvanceToInvoice'), 'standalone page must never apply a client advance')
assert.ok(!pageSource.includes('recordAdvanceTransaction'), 'standalone page must never record an advance receipt')

// ---------------------------------------------------------------------------
// Existing Billing page + shared visual surface
// ---------------------------------------------------------------------------
// STEP 12: settlement data may stay on the ERP Finance preview, but it must never reach
// the printable A4 document (which is what the PDF and the print output render).
assert.ok(billingSource.includes('invoice-erp-settlement'), 'the ERP settlement panel must live on the Billing page')
assert.ok(!documentSource.includes('invoice-erp-settlement'), 'the printable A4 document must not render the ERP settlement panel')
assert.ok(!/Settlement Summary/i.test(documentSource), 'the printable A4 document must not render a settlement summary')
assert.ok(documentSource.includes('invoice-a4-watermark'), 'a watermark must exist on the shared document')
assert.ok(documentSource.includes('nakshatech-logo'), 'the official NakshaTech logo must be used')
assert.ok(cssSource.includes('invoice-a4-watermark'), 'watermark styling must exist')
assert.ok(cssSource.includes('invoice-preview-scroll-area'), 'only the scroll area may scroll')

console.log('FINANCE GENERATE INVOICE (STANDALONE) VERIFICATION PASSED')
console.log('- Sidebar: Billing & Invoices -> Generate Invoice -> Commercial Control, Finance-only')
console.log('- Route /finance/generate-invoice is Finance-only; /finance/billing unchanged')
console.log('- Manual form: seller, invoice details, bill/ship-to, line items, tax, notes, bank')
console.log('- Line items support add/remove; Ship To mirrors Bill To')
console.log('- Tax supports CGST+SGST and IGST with editable rates plus a no-tax mode')
console.log('- Preview, PDF download and print reuse one backend document payload')
console.log('- History lists document columns only - no payment/outstanding/revenue')
console.log('- Standalone page never calls project, advance or command-center APIs')
console.log('- Printable project invoice carries no settlement summary')
console.log('- Shared A4 document: official logo + watermark; only the scroll area scrolls')
assert.ok(pageSource.includes('sameAsBill'), 'Ship To must offer "Same as Bill To"')