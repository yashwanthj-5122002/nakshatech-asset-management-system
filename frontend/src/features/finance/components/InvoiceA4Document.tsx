import type { InvoiceDocumentPayload } from '../../operations/lifecycle-types'
import { formatDate, formatMoney } from '../../operations/lifecycle-types'

function Details({ values }: { values: Array<[string, string | null | undefined]> }) {
  return <>{values.filter(([, value]) => value).map(([label, value]) => <p key={label}><strong>{label}:</strong> {value}</p>)}</>
}

export function InvoiceA4Document({ invoice }: { invoice: InvoiceDocumentPayload }) {
  const standalone = invoice.document_source === 'standalone_invoice'
  const taxColumns = standalone

  return <div className={`invoice-a4-sheet ${standalone ? 'invoice-a4-standalone' : 'invoice-a4-project'}`}>
    <div className="invoice-a4-watermark" aria-hidden="true"><img src="/nakshatech-logo.png" alt=""/></div>
    <div className="invoice-a4-brand">
      <img src="/nakshatech-logo.png" alt="NakshaTech" className="invoice-a4-logo" onError={event => { (event.currentTarget as HTMLImageElement).style.display = 'none' }}/>
      <div><h1>{invoice.document_type}</h1></div>
    </div>
    <div className="invoice-a4-header-strip">
      <div>
        <strong>{invoice.company.name}</strong>
        {invoice.company.address && <p>{invoice.company.address}</p>}
        <p>{[invoice.company.phone, invoice.company.email, invoice.company.website].filter(Boolean).join(' · ')}</p>
        <p>{[
          invoice.company.gstin && `GSTIN: ${invoice.company.gstin}`,
          invoice.company.pan && `PAN: ${invoice.company.pan}`,
          invoice.company.msme_registration && `MSME: ${invoice.company.msme_registration}`,
        ].filter(Boolean).join(' · ')}</p>
      </div>
      <div className="invoice-a4-meta">
        <div><span>Invoice No.</span><strong>{invoice.invoice.invoice_number}</strong></div>
        <div><span>Invoice Date</span><strong>{formatDate(invoice.invoice.invoice_date)}</strong></div>
        {invoice.invoice.payment_terms && <div><span>Terms</span><strong>{invoice.invoice.payment_terms}</strong></div>}
        {invoice.invoice.due_date && <div><span>Due Date</span><strong>{formatDate(invoice.invoice.due_date)}</strong></div>}
        {invoice.invoice.po_wo_reference && <div><span>Work Order / Reference</span><strong>{invoice.invoice.po_wo_reference}</strong></div>}
        {invoice.invoice.work_order_date && <div><span>Work Order Date</span><strong>{formatDate(invoice.invoice.work_order_date)}</strong></div>}
        {invoice.invoice.dispatch_details && <div><span>Dispatch Details</span><strong>{invoice.invoice.dispatch_details}</strong></div>}
        {invoice.invoice.dispatch_date && <div><span>Dispatch Date</span><strong>{formatDate(invoice.invoice.dispatch_date)}</strong></div>}
        {invoice.invoice.place_of_supply && <div><span>Place of Supply</span><strong>{invoice.invoice.place_of_supply}</strong></div>}
      </div>
    </div>
    <div className="invoice-a4-parties">
      <section>
        <span>Bill To</span><h3>{invoice.client.name}</h3>
        {invoice.client.address && <p>{invoice.client.address}</p>}
        {invoice.client.country && <p>{invoice.client.country}</p>}
        <Details values={[
          ['GSTIN', invoice.client.gstin], ['PAN', invoice.client.pan], ['Attn', invoice.client.contact_person],
          ['Email', invoice.client.email], ['Phone', invoice.client.phone],
        ]}/>
      </section>
      <section>
        {standalone && invoice.ship_to ? <>
          <span>Ship To</span><h3>{invoice.ship_to.name}</h3>
          {invoice.ship_to.address && <p>{invoice.ship_to.address}</p>}
          <Details values={[
            ['GSTIN', invoice.ship_to.gstin], ['PAN', invoice.ship_to.pan], ['Email', invoice.ship_to.email], ['Phone', invoice.ship_to.phone],
          ]}/>
        </> : <>
          <span>Bank Details</span>
          <Details values={[
            ['Bank Name', invoice.company.bank_name], ['Account Name', invoice.company.bank_account_name],
            ['Account Number', invoice.company.bank_account_number], ['SWIFT Code', invoice.company.bank_swift],
            ['IFSC', invoice.company.bank_ifsc], ['Bank Address', invoice.company.bank_branch],
          ]}/>
          {!invoice.company.bank_name && !invoice.company.bank_account_number && <p>Not configured</p>}
        </>}
      </section>
    </div>
    <div className="invoice-a4-table-wrap"><table className="invoice-a4-table"><thead><tr>
      <th>#</th><th>Description</th><th>HSN/SAC</th><th>Qty</th><th>Unit</th><th>Rate</th>
      {taxColumns && <><th>Tax %</th><th>Tax</th></>}<th>Amount</th>
    </tr></thead><tbody>{invoice.line_items.map(item => <tr key={item.sequence}>
      <td>{item.sequence}</td><td><strong>{item.description}</strong>{item.detail && <small>{item.detail}</small>}</td>
      <td>{item.hsn_sac || '—'}</td><td>{Number(item.quantity).toFixed(2)}</td><td>{item.unit}</td>
      <td>{formatMoney(item.rate, invoice.totals.currency)}</td>
      {taxColumns && <><td>{Number(item.tax_percent || 0).toFixed(2)}%</td><td>{formatMoney(item.tax_amount || 0, invoice.totals.currency)}</td></>}
      <td>{formatMoney(item.taxable_amount, invoice.totals.currency)}</td>
    </tr>)}</tbody></table></div>
    <div className="invoice-a4-totals">
      <div><span>Amount Chargeable (in words)</span><strong>{invoice.totals.amount_in_words}</strong>
        {(invoice.company.gstin || invoice.company.hsn_sac || invoice.company.pan) && <p className="invoice-a4-legal">{[
          invoice.company.gstin && `Company GST No.: ${invoice.company.gstin}`,
          invoice.company.hsn_sac && `HSN/SAC: ${invoice.company.hsn_sac}`,
          invoice.company.pan && `Company PAN: ${invoice.company.pan}`,
        ].filter(Boolean).join(' | ')}</p>}
      </div>
      <table><tbody>
        <tr><th>{standalone ? 'Subtotal' : 'Taxable Value'}</th><td>{formatMoney(invoice.totals.subtotal ?? invoice.totals.taxable_amount, invoice.totals.currency)}</td></tr>
        {invoice.tax_lines.map(line => <tr key={line.label}><th>{line.label}</th><td>{formatMoney(line.amount, invoice.totals.currency)}</td></tr>)}
        <tr><th>Total</th><td>{formatMoney(invoice.totals.invoice_total, invoice.totals.currency)}</td></tr>
        {standalone && <tr><th>Balance Due</th><td>{formatMoney(invoice.totals.balance_due ?? invoice.totals.invoice_total, invoice.totals.currency)}</td></tr>}
      </tbody></table>
    </div>
    {standalone && (invoice.company.bank_name || invoice.company.bank_account_number) && <section className="invoice-a4-remittance"><span>Bank Details</span><div className="invoice-a4-bank-grid"><Details values={[
      ['Bank Name', invoice.company.bank_name], ['Account Name', invoice.company.bank_account_name],
      ['Account Number', invoice.company.bank_account_number], ['IFSC', invoice.company.bank_ifsc],
      ['SWIFT', invoice.company.bank_swift], ['Bank Address', invoice.company.bank_branch],
    ]}/></div></section>}
    {(invoice.notes || invoice.invoice.notes) && <section className="invoice-a4-notes"><span>Notes</span><p>{invoice.notes || invoice.invoice.notes}</p></section>}
    {invoice.terms_conditions && <section className="invoice-a4-notes"><span>Terms & Conditions</span><p>{invoice.terms_conditions}</p></section>}
    <div className="invoice-a4-signature-row">
      {invoice.qr_image_data_uri ? <img className="invoice-a4-qr" src={invoice.qr_image_data_uri} alt="Invoice QR code"/> : <span/>}
      <div className="invoice-a4-signature"><p>For {invoice.company.name}</p><div className="invoice-a4-signature-space"/>{invoice.authorized_signatory_name && <strong>{invoice.authorized_signatory_name}</strong>}<p>Authorised Signatory</p></div>
    </div>
    <footer><span>{[invoice.company.phone, invoice.company.email, invoice.company.website, invoice.company.address].filter(Boolean).join(' · ') || 'Computer-generated from NakshaTech ERP'}</span><img src="/nakshatech-logo.png" alt="" className="invoice-a4-footer-logo" onError={event => { (event.currentTarget as HTMLImageElement).style.display = 'none' }}/></footer>
  </div>
}
