/** Presentation only: invoice financial values always come from the existing payload. */
export type InvoiceTemplate = 'green_gold' | 'modern_teal' | 'geospatial_blue'

export const INVOICE_TEMPLATES: ReadonlyArray<{ id: InvoiceTemplate; name: string; subtitle: string }> = [
  { id: 'green_gold', name: 'Premium Green & Gold', subtitle: 'Emerald and antique-gold corporate invoice' },
  { id: 'modern_teal', name: 'Modern Teal', subtitle: 'Contemporary teal with topographic detail' },
  { id: 'geospatial_blue', name: 'Geospatial Blue', subtitle: 'Crisp NakshaTech blue technical layout' },
]

/** Safe for request query strings, defaults to an explicit chosen template. */
export function invoiceTemplateQuery(template: InvoiceTemplate): string {
  return `template=${encodeURIComponent(template)}`
}

export function InvoiceTemplateSelector({ value, onChange, compact = false, label = 'Choose tax invoice format' }: {
  value: InvoiceTemplate
  onChange: (template: InvoiceTemplate) => void
  compact?: boolean
  label?: string
}) {
  return <section className={`invoice-template-picker ${compact ? 'invoice-template-picker--compact' : ''}`} aria-label={label}>
    <div className="invoice-template-picker__intro"><strong>{label}</strong><span>Same invoice data and GST values in every style</span></div>
    <div className="invoice-template-picker__options" role="group" aria-label={label}>
      {INVOICE_TEMPLATES.map(({ id, name, subtitle }, index) => <button
        type="button" key={id} className={`invoice-template-choice invoice-template-choice--${id}`}
        aria-pressed={value === id} onClick={() => onChange(id)} title={subtitle}>
        <span className="invoice-template-choice__thumb" aria-hidden="true"><i/><b>TAX INVOICE</b><em/><em/><i/></span>
        <span className="invoice-template-choice__name">{index + 1}. {name}</span>
      </button>)}
    </div>
  </section>
}
