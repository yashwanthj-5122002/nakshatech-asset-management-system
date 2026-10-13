import { BarChart3, RefreshCcw, TrendingUp } from 'lucide-react'
import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import type { FinanceProject } from '../../../types'
import type { CommercialAnalytics, CurrencyPayload } from '../types'
import { money } from '../types'
import '../commercial.css'

const fyStart = () => {
  const now = new Date()
  const year = now.getMonth() < 3 ? now.getFullYear() - 1 : now.getFullYear()
  return `${year}-04-01`
}
const today = () => new Date().toISOString().slice(0, 10)

export function ManagementCommercialPage() {
  const [projects, setProjects] = useState<FinanceProject[]>([])
  const [currencies, setCurrencies] = useState<CurrencyPayload | null>(null)
  const [data, setData] = useState<CommercialAnalytics | null>(null)
  const [dateFrom, setDateFrom] = useState(fyStart)
  const [dateTo, setDateTo] = useState(today)
  const [projectId, setProjectId] = useState('')
  const [displayCurrency, setDisplayCurrency] = useState('INR')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function loadReferences() {
    try {
      const [projectRows, refs] = await Promise.all([apiFetch<FinanceProject[]>('/finance/report-projects'), apiFetch<CurrencyPayload>('/commercial/currencies')])
      setProjects(projectRows); setCurrencies(refs)
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to load analytics references') }
  }

  async function loadAnalytics(event?: FormEvent) {
    event?.preventDefault()
    setLoading(true); setError('')
    try {
      const params = new URLSearchParams()
      if (dateFrom) params.set('date_from', dateFrom)
      if (dateTo) params.set('date_to', dateTo)
      if (projectId) params.set('project_id', projectId)
      params.set('display_currency', displayCurrency)
      setData(await apiFetch<CommercialAnalytics>(`/commercial/management/analytics?${params.toString()}`))
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to load commercial analytics') }
    finally { setLoading(false) }
  }

  useEffect(() => { void loadReferences(); void loadAnalytics() }, [])

  const summary = data?.summary_inr ?? {}
  const maxMonthly = useMemo(() => Math.max(1, ...(data?.monthly ?? []).map(row => Math.max(row.billing_inr, row.total_cost_inr))), [data])

  return <div className="commercial-page">
    <DashboardHeader eyebrow="MANAGEMENT · COMMERCIAL INTELLIGENCE" title="Project Commercial Analytics" description="INR is the accounting truth. Display-currency conversion is optional and presentation-only; historic transaction FX snapshots remain unchanged." actions={<button className="commercial-button secondary" onClick={() => { void loadReferences(); void loadAnalytics() }}><RefreshCcw size={15}/> Refresh</button>} meta={<><span className="nk-meta-chip"><TrendingUp size={14}/> Project-level commercial analytics</span><span className="nk-meta-chip"><BarChart3 size={14}/> INR accounting · display currency is optional</span><span className="nk-meta-chip"><RefreshCcw size={14}/> Historic FX snapshots preserved</span></>}/>
    {error && <div className="commercial-alert error">{error}</div>}
    <section className="commercial-panel">
      <form className="commercial-toolbar" onSubmit={loadAnalytics}>
        <label className="commercial-field"><span>From</span><input type="date" value={dateFrom} onChange={e=>setDateFrom(e.target.value)}/></label>
        <label className="commercial-field"><span>To</span><input type="date" value={dateTo} onChange={e=>setDateTo(e.target.value)}/></label>
        <label className="commercial-field"><span>Project</span><select value={projectId} onChange={e=>setProjectId(e.target.value)}><option value="">All Projects</option>{projects.map(row=><option key={row.id} value={row.id}>{row.project_code}</option>)}</select></label>
        <label className="commercial-field"><span>Display Currency</span><select value={displayCurrency} onChange={e=>setDisplayCurrency(e.target.value)}>{(currencies?.management_display_currencies ?? ['INR','USD','EUR','GBP']).map(code=><option key={code}>{code}</option>)}</select></label>
        <button className="commercial-button" disabled={loading}><BarChart3 size={15}/>{loading ? 'Loading…' : 'Apply'}</button>
      </form>
    </section>

    {data && <>
      <section className="commercial-kpis">
        <div className="commercial-kpi"><span>Revision 1 Baseline · Base</span><strong>{money(summary.baseline_revision_base_inr)}</strong></div>
        <div className="commercial-kpi"><span>Latest Approved Commercial Value</span><strong>{money(summary.approved_estimate_base_inr)}</strong></div>
        <div className="commercial-kpi"><span>Billed Net Revenue</span><strong>{money(summary.billed_net_inr)}</strong></div>
        <div className="commercial-kpi"><span>Payments Realized</span><strong>{money(summary.payments_realized_inr)}</strong></div>
        <div className="commercial-kpi"><span>Total Direct Cost</span><strong>{money(summary.total_direct_cost_inr)}</strong></div>
        <div className="commercial-kpi"><span>Actual Margin</span><strong>{money(summary.margin_inr)}</strong></div>
        <div className="commercial-kpi"><span>Employee Cost</span><strong>{money(summary.employee_cost_inr)}</strong></div>
        <div className="commercial-kpi"><span>Vendor Cost</span><strong>{money(summary.vendor_cost_inr)}</strong></div>
        <div className="commercial-kpi"><span>Commercial (Scope) Variance</span><strong>{money(summary.commercial_variance_inr)}</strong></div>
        <div className="commercial-kpi"><span>FX Variance (invoice vs baseline)</span><strong>{money(summary.fx_variance_inr)}</strong></div>
        <div className="commercial-kpi"><span>Realized FX Gain / Loss</span><strong>{money(summary.fx_gain_loss_inr)}</strong></div>
      </section>
      {data.display_conversion && <div className="commercial-note">Display only: ₹1 = {data.display_conversion.rate_from_inr.toLocaleString('en-IN',{maximumFractionDigits:8})} {data.display_conversion.currency} using {data.display_conversion.source} on {data.display_conversion.rate_date}. This does not rewrite historical accounting rates.</div>}

      <section className="commercial-panel"><header><div><span className="commercial-kicker">PROJECT PROFITABILITY</span><h2>Project-wise Commercial View</h2></div><TrendingUp size={22}/></header><div className="commercial-table-wrap"><table className="commercial-table"><thead><tr><th>Project</th><th>Rev 1 Baseline</th><th>Latest Approved</th><th>Billed</th><th>Realized</th><th>Employee Cost</th><th>Vendor Cost</th><th>Total Cost</th><th>Margin</th><th>FX G/L</th></tr></thead><tbody>{data.projects.map(row=><tr key={row.project_id}><td><strong>{row.project_code}</strong><br/><small>{row.client_code || '—'}</small></td><td>{money(row.baseline_revision_base_inr)}</td><td>{money(row.latest_approved_base_inr ?? row.estimate_base_inr)}{row.latest_approved_revision_no ? <><br/><small>R{row.latest_approved_revision_no}</small></> : null}</td><td>{money(row.billed_net_inr)}{row.commercial_variance_inr != null ? <><br/><small>scope {money(row.commercial_variance_inr)} · FX {money(row.fx_variance_inr)}</small></> : null}</td><td>{money(row.payments_realized_inr)}</td><td>{money(row.employee_cost_inr)}</td><td>{money(row.vendor_cost_inr)}</td><td>{money(row.total_direct_cost_inr)}</td><td><strong>{money(row.margin_inr)}</strong></td><td>{money(row.fx_gain_loss_inr)}</td></tr>)}</tbody></table></div></section>

      <div className="commercial-grid">
        <section className="commercial-panel"><header><div><span className="commercial-kicker">MONTHLY MOVEMENT</span><h2>Billing vs Direct Cost</h2></div></header><div className="commercial-bar-list">{data.monthly.map(row=><div className="commercial-bar-row" key={row.month}><div><strong>{row.month}</strong><span>{money(row.billing_inr)} billed · {money(row.total_cost_inr)} cost</span></div><div className="commercial-bar-track"><i style={{width:`${Math.min(100,(row.billing_inr/maxMonthly)*100)}%`}}/></div><div className="commercial-bar-track"><i style={{width:`${Math.min(100,(row.total_cost_inr/maxMonthly)*100)}%`, opacity:.45}}/></div></div>)}{!data.monthly.length && <div className="commercial-empty">No dated commercial activity in this period.</div>}</div></section>
        <section className="commercial-panel"><header><div><span className="commercial-kicker">EMPLOYEE COST CONTRIBUTION</span><h2>Approved Project Costs</h2></div></header><div className="commercial-table-wrap"><table className="commercial-table"><thead><tr><th>Employee</th><th>Cost</th></tr></thead><tbody>{data.employee_costs.map(row=><tr key={row.employee_id}><td>{row.employee_name}</td><td><strong>{money(row.cost_inr)}</strong></td></tr>)}</tbody></table>{!data.employee_costs.length && <div className="commercial-empty">No employee project costs in this period.</div>}</div></section>
      </div>
    </>}
  </div>
}
