import {
  ArrowUpRight,
  BarChart3,
  Building2,
  DollarSign,
  HelpCircle,
  IndianRupee,
  Layers,
  PieChart,
  RefreshCcw,
  TrendingDown,
  TrendingUp,
  Wallet,
} from 'lucide-react'
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
      const [projectRows, refs] = await Promise.all([
        apiFetch<FinanceProject[]>('/finance/report-projects'),
        apiFetch<CurrencyPayload>('/commercial/currencies'),
      ])
      setProjects(projectRows)
      setCurrencies(refs)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load analytics references')
    }
  }

  async function loadAnalytics(event?: FormEvent) {
    event?.preventDefault()
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams()
      if (dateFrom) params.set('date_from', dateFrom)
      if (dateTo) params.set('date_to', dateTo)
      if (projectId) params.set('project_id', projectId)
      params.set('display_currency', displayCurrency)
      setData(await apiFetch<CommercialAnalytics>(`/commercial/management/analytics?${params.toString()}`))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load commercial analytics')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadReferences()
    void loadAnalytics()
  }, [])

  const summary = data?.summary_inr ?? {}
  const maxMonthly = useMemo(
    () => Math.max(1, ...(data?.monthly ?? []).map(row => Math.max(row.billing_inr, row.total_cost_inr))),
    [data]
  )

  const marginPercent =
    summary.billed_net_inr && summary.margin_inr
      ? ((summary.margin_inr / summary.billed_net_inr) * 100).toFixed(1)
      : null

  const realizationPercent =
    summary.billed_net_inr && summary.payments_realized_inr
      ? ((summary.payments_realized_inr / summary.billed_net_inr) * 100).toFixed(1)
      : null

  return (
    <div className="commercial-page">
      <DashboardHeader
        eyebrow="MANAGEMENT · COMMERCIAL & PROFITABILITY INTELLIGENCE"
        title="Project Commercial Analytics"
        description="Statutory INR commercial telemetry. Multi-currency conversions are presentation snapshots and preserve historical ledger FX rates."
        actions={
          <button className="commercial-button secondary" onClick={() => { void loadReferences(); void loadAnalytics() }}>
            <RefreshCcw size={15} /> Refresh Analytics
          </button>
        }
      />

      {error && <div className="commercial-alert error">{error}</div>}

      {/* Filter Toolbar */}
      <section className="commercial-panel" style={{ padding: '16px 20px' }}>
        <form className="commercial-toolbar" onSubmit={loadAnalytics}>
          <label className="commercial-field">
            <span>From Date</span>
            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
          </label>
          <label className="commercial-field">
            <span>To Date</span>
            <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} />
          </label>
          <label className="commercial-field">
            <span>Project Scope</span>
            <select value={projectId} onChange={e => setProjectId(e.target.value)}>
              <option value="">All Lifecycle Projects</option>
              {projects.map(row => (
                <option key={row.id} value={row.id}>
                  {row.project_code}
                </option>
              ))}
            </select>
          </label>
          <label className="commercial-field">
            <span>Display Currency</span>
            <select value={displayCurrency} onChange={e => setDisplayCurrency(e.target.value)}>
              {(currencies?.management_display_currencies ?? ['INR', 'USD', 'EUR', 'GBP']).map(code => (
                <option key={code}>{code}</option>
              ))}
            </select>
          </label>
          <button className="commercial-button" disabled={loading} style={{ alignSelf: 'flex-end', height: '42px' }}>
            <BarChart3 size={15} /> {loading ? 'Computing…' : 'Apply Filters'}
          </button>
        </form>
      </section>

      {data && (
        <>
          {/* Executive Top-Line Financial Quad */}
          <section className="commercial-executive-quad">
            <div className="commercial-hero-kpi">
              <span>Approved Commercial Value</span>
              <strong>{money(summary.approved_estimate_base_inr)}</strong>
              <small>Rev 1 Baseline: {money(summary.baseline_revision_base_inr)}</small>
            </div>

            <div className="commercial-hero-kpi">
              <span>Billed Net Revenue</span>
              <strong>{money(summary.billed_net_inr)}</strong>
              <small>Invoiced across all active lifecycle cycles</small>
            </div>

            <div className="commercial-hero-kpi">
              <span>Payments Realized</span>
              <strong>{money(summary.payments_realized_inr)}</strong>
              <small>
                {realizationPercent ? `${realizationPercent}% of billed revenue collected` : 'Realization tracking'}
              </small>
            </div>

            <div className="commercial-hero-kpi profit">
              <span>Operating Margin</span>
              <strong>{money(summary.margin_inr)}</strong>
              <small>
                {marginPercent ? `${marginPercent}% net margin on billed revenue` : 'Calculated post direct costs'}
              </small>
            </div>
          </section>

          {/* Cost & Variance Secondary Strip */}
          <section className="commercial-variance-strip">
            <div className="commercial-variance-box">
              <span>Total Direct Project Costs</span>
              <strong>{money(summary.total_direct_cost_inr)}</strong>
              <small>
                Staff: {money(summary.employee_cost_inr)} · Vendors: {money(summary.vendor_cost_inr)}
              </small>
            </div>

            <div className="commercial-variance-box">
              <span>Commercial Scope Variance</span>
              <strong>{money(summary.commercial_variance_inr)}</strong>
              <small>Approved contract revisions vs initial budget</small>
            </div>

            <div className="commercial-variance-box">
              <span>Realized FX Gain / Loss</span>
              <strong style={{ color: (summary.fx_gain_loss_inr ?? 0) >= 0 ? '#166534' : '#dc2626' }}>
                {money(summary.fx_gain_loss_inr)}
              </strong>
              <small>FX variance: {money(summary.fx_variance_inr)}</small>
            </div>
          </section>

          {data.display_conversion && (
            <div className="commercial-note" style={{ borderRadius: '12px', marginBottom: '16px' }}>
              <strong>Multi-Currency Presentation:</strong> ₹1 = {data.display_conversion.rate_from_inr.toLocaleString('en-IN', { maximumFractionDigits: 6 })} {data.display_conversion.currency} using {data.display_conversion.source} snapshot on {data.display_conversion.rate_date}. INR remains statutory accounting truth.
            </div>
          )}

          {/* Project-Wise Profitability Ledger */}
          <section className="commercial-panel">
            <header>
              <div>
                <span className="commercial-kicker">PROJECT PROFITABILITY LEDGER</span>
                <h2>Commercial Ledger By Project</h2>
              </div>
              <TrendingUp size={22} color="#0f766e" />
            </header>
            <div className="commercial-table-wrap">
              <table className="commercial-table">
                <thead>
                  <tr>
                    <th>Project & Client</th>
                    <th>Rev 1 Baseline</th>
                    <th>Latest Approved</th>
                    <th>Billed Revenue</th>
                    <th>Realized</th>
                    <th>Direct Cost</th>
                    <th>Operating Margin</th>
                    <th>FX Impact</th>
                  </tr>
                </thead>
                <tbody>
                  {data.projects.map(row => (
                    <tr key={row.project_id}>
                      <td>
                        <strong>{row.project_code}</strong>
                        <br />
                        <small style={{ color: '#64748b' }}>{row.client_code || 'Direct Client'}</small>
                      </td>
                      <td>{money(row.baseline_revision_base_inr)}</td>
                      <td>
                        {money(row.latest_approved_base_inr ?? row.estimate_base_inr)}
                        {row.latest_approved_revision_no ? (
                          <>
                            <br />
                            <small style={{ color: '#0284c7' }}>Rev {row.latest_approved_revision_no}</small>
                          </>
                        ) : null}
                      </td>
                      <td>
                        {money(row.billed_net_inr)}
                        {row.commercial_variance_inr != null && (
                          <>
                            <br />
                            <small style={{ color: '#64748b' }}>Scope: {money(row.commercial_variance_inr)}</small>
                          </>
                        )}
                      </td>
                      <td style={{ color: '#166534', fontWeight: 650 }}>{money(row.payments_realized_inr)}</td>
                      <td>{money(row.total_direct_cost_inr)}</td>
                      <td>
                        <strong style={{ color: (row.margin_inr ?? 0) >= 0 ? '#0f766e' : '#dc2626' }}>
                          {money(row.margin_inr)}
                        </strong>
                      </td>
                      <td>{money(row.fx_gain_loss_inr)}</td>
                    </tr>
                  ))}
                  {!data.projects.length && (
                    <tr>
                      <td colSpan={8} style={{ textAlign: 'center', padding: '24px', color: '#64748b' }}>
                        No commercial project data for the selected period.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          {/* Monthly Movement & Cost Distribution */}
          <div className="commercial-grid">
            <section className="commercial-panel">
              <header>
                <div>
                  <span className="commercial-kicker">MONTHLY VELOCITY</span>
                  <h2>Billing vs Direct Costs</h2>
                </div>
              </header>
              <div className="commercial-bar-list">
                {data.monthly.map(row => (
                  <div className="commercial-bar-row" key={row.month}>
                    <div>
                      <strong>{row.month}</strong>
                      <span style={{ fontSize: '0.74rem', color: '#64748b' }}>
                        {money(row.billing_inr)} billed · {money(row.total_cost_inr)} cost
                      </span>
                    </div>
                    <div className="commercial-bar-track" title={`Billed: ${money(row.billing_inr)}`}>
                      <i style={{ width: `${Math.min(100, (row.billing_inr / maxMonthly) * 100)}%` }} />
                    </div>
                    <div className="commercial-bar-track" title={`Cost: ${money(row.total_cost_inr)}`}>
                      <i
                        style={{
                          width: `${Math.min(100, (row.total_cost_inr / maxMonthly) * 100)}%`,
                          background: '#f59e0b',
                        }}
                      />
                    </div>
                  </div>
                ))}
                {!data.monthly.length && (
                  <div className="commercial-empty">No dated commercial activity in this period.</div>
                )}
              </div>
            </section>

            <section className="commercial-panel">
              <header>
                <div>
                  <span className="commercial-kicker">WORKFORCE CONTRIBUTION</span>
                  <h2>Approved Project Cost Allocations</h2>
                </div>
              </header>
              <div className="commercial-table-wrap">
                <table className="commercial-table">
                  <thead>
                    <tr>
                      <th>Team Member</th>
                      <th>Direct Cost Allocation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.employee_costs.map(row => (
                      <tr key={row.employee_id}>
                        <td>{row.employee_name}</td>
                        <td>
                          <strong>{money(row.cost_inr)}</strong>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!data.employee_costs.length && (
                  <div className="commercial-empty">No employee project costs recorded in this period.</div>
                )}
              </div>
            </section>
          </div>
        </>
      )}
    </div>
  )
}
