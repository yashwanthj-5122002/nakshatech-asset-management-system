export interface CommandCenterOpenSalesCategories {
  invoice_not_raised_inr: number
  payment_pending_inr: number
  partial_payment_inr: number
  payment_received_closure_pending_inr: number
  other_open_inr: number
}

export interface CommandCenterInvoiceKpiSource {
  status: string
  total_amount: number
  total_inr: number
  paid_amount: number
  balance_inr: number
  open_sales_category: string | null
}

export interface CommandCenterProjectKpiSource {
  open_sales_inr: number
  open_sales_categories: CommandCenterOpenSalesCategories
  unbilled_open_sales_inr: number
  partial_payment_balance_inr: number
  received_against_open_sales_inr: number
  outstanding_inr: number
  sales_visible: boolean
  sales_status: string
  open_payment_pending_invoice_count: number
  open_partial_invoice_count: number
  invoice_not_raised: boolean
  sales_value_inr: number
  invoice_count: number
  invoices: CommandCenterInvoiceKpiSource[]
}

export interface CommandCenterRevenueKpiSource {
  revenue_amount_inr: number
}

function isRevenueQualifyingInvoice(invoice: CommandCenterInvoiceKpiSource) {
  return invoice.status === 'INVOICE_CLOSED' && invoice.paid_amount >= invoice.total_amount
}

function isOutstandingReceivable(invoice: CommandCenterInvoiceKpiSource) {
  return !isRevenueQualifyingInvoice(invoice)
    && (invoice.open_sales_category === 'payment_pending_inr'
      || invoice.open_sales_category === 'partial_payment_inr')
}

export function openSalesCategoriesForProject(row: CommandCenterProjectKpiSource): CommandCenterOpenSalesCategories {
  const categories: CommandCenterOpenSalesCategories = {
    invoice_not_raised_inr: Math.max(row.unbilled_open_sales_inr || 0, 0),
    payment_pending_inr: 0,
    partial_payment_inr: 0,
    payment_received_closure_pending_inr: 0,
    other_open_inr: 0,
  }
  for (const invoice of row.invoices) {
    if (isRevenueQualifyingInvoice(invoice)) continue
    const balance = Math.max(invoice.balance_inr || 0, 0)
    if (invoice.open_sales_category === 'payment_pending_inr') categories.payment_pending_inr += balance
    else if (invoice.open_sales_category === 'partial_payment_inr') categories.partial_payment_inr += balance
    else if (invoice.open_sales_category === 'other_open_inr') categories.other_open_inr += balance
  }
  return categories
}

export function aggregateFinanceCommandCenterKpis(
  projects: CommandCenterProjectKpiSource[],
  revenueEvents: CommandCenterRevenueKpiSource[],
) {
  const sumCategories = (key: keyof CommandCenterOpenSalesCategories) =>
    projects.reduce((sum, row) => sum + openSalesCategoriesForProject(row)[key], 0)
  const categories: CommandCenterOpenSalesCategories = {
    invoice_not_raised_inr: sumCategories('invoice_not_raised_inr'),
    payment_pending_inr: sumCategories('payment_pending_inr'),
    partial_payment_inr: sumCategories('partial_payment_inr'),
    payment_received_closure_pending_inr: sumCategories('payment_received_closure_pending_inr'),
    other_open_inr: sumCategories('other_open_inr'),
  }
  const categoriesSum = Object.values(categories).reduce((sum, value) => sum + value, 0)
  const openSales = categoriesSum
  const received = projects.reduce((sum, row) => sum + row.received_against_open_sales_inr, 0)
  // Overdue invoices retain their payment-pending or partial-payment category,
  // so this sums every unpaid receivable once without including unbilled sales.
  const outstanding = projects.reduce((sum, row) =>
    sum + row.invoices
      .filter(isOutstandingReceivable)
      .reduce((invoiceSum, invoice) => invoiceSum + Math.max(invoice.balance_inr, 0), 0), 0)
  const closedRevenue = revenueEvents.reduce((sum, row) => sum + row.revenue_amount_inr, 0)
  const openInvoiced = projects.reduce((sum, row) =>
    sum + row.invoices
      .filter(invoice => !isRevenueQualifyingInvoice(invoice) && invoice.open_sales_category != null)
      .reduce((invoiceSum, invoice) => invoiceSum + invoice.total_inr, 0), 0)

  return {
    openSales,
    received,
    outstanding,
    closedRevenue,
    openInvoiced,
    categories,
    categoriesSum,
    reconciled: Math.abs(openSales - categoriesSum) <= 0.01,
    salesCount: projects.filter(row => row.sales_visible).length,
    revenueCount: revenueEvents.length,
    partial: projects.filter(row => row.sales_status === 'Partially Paid').length,
    overdue: projects.filter(row => row.sales_status === 'Overdue').length,
    paymentPendingCount: projects.reduce((sum, row) => sum + (row.open_payment_pending_invoice_count || 0), 0),
    paymentPendingAmount: categories.payment_pending_inr,
    partialCount: projects.reduce((sum, row) => sum + (row.open_partial_invoice_count || 0), 0),
    // The backend deliberately keeps the full invoice value in the open-sales
    // category. The Command Center KPI is the unpaid remainder only.
    partialAmount: projects.reduce((sum, row) => sum + (row.partial_payment_balance_inr || 0), 0),
    notRaisedCount: projects.filter(row => row.invoice_not_raised ?? (row.sales_value_inr > 0 && row.invoice_count === 0)).length,
    notRaisedAmount: categories.invoice_not_raised_inr,
  }
}
