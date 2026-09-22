import { Database, RefreshCcw, ShieldAlert, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { DashboardHeader } from '../components/DashboardHeader'
import { apiFetch } from '../lib/api'
import '../features/finance/finance-expenses.css'

type Validation = {
  clients: number
  projects: number
  departments?: Record<string, number>
  invoices?: number
  payments?: number
  closed_invoices?: number
  realized_revenue_inr?: number
  work_packages?: number
  expense_claims?: number
  project_expenses?: number
  vendor_invoices?: number
  travel_km_claims?: number
  uat_assets?: number
  uat_work_records?: number
  uat_drones?: number
}

type UatStatus = {
  enabled: boolean
  tag: string
  loaded: boolean
  counts: { clients: number; projects: number }
  validation: Validation | null
}

const TAG = 'UAT_YEAR_SIMULATION_2026'

function inr(value?: number) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(value || 0)
}

export function UAT2026ControlPage() {
  const [status, setStatus] = useState<UatStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<'load' | 'remove' | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function refresh() {
    setLoading(true)
    setError('')
    try {
      setStatus(await apiFetch<UatStatus>('/uat/2026/status'))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to load UAT control status')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void refresh() }, [])

  async function loadDataset() {
    if (!window.confirm('Load the full deterministic 2026 ERP testing dataset now? This creates synthetic UAT records only.')) return
    setBusy('load')
    setError('')
    setNotice('')
    try {
      await apiFetch('/uat/2026/load', { method: 'POST' })
      setNotice('2026 testing data loaded successfully.')
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to load 2026 testing data')
    } finally {
      setBusy(null)
    }
  }

  async function removeDataset() {
    const entered = window.prompt(
      'This removes only the tagged 2026 UAT dataset. Type the exact confirmation token to continue:',
      ''
    )
    if (entered === null) return
    if (entered.trim() !== TAG) {
      setError(`Confirmation did not match. Type exactly: ${TAG}`)
      return
    }
    if (!window.confirm('Final confirmation: remove all UAT_YEAR_SIMULATION_2026 test records? Genuine ERP data will not be targeted.')) return
    setBusy('remove')
    setError('')
    setNotice('')
    try {
      await apiFetch(`/uat/2026/remove?confirmation=${encodeURIComponent(TAG)}`, { method: 'POST' })
      setNotice('2026 testing data removed successfully.')
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to remove 2026 testing data')
    } finally {
      setBusy(null)
    }
  }

  const v = status?.validation

  return <div className="finance-page">
    <DashboardHeader
      eyebrow="FINANCE · LOCAL / UAT ONLY"
      title="2026 ERP Testing Data"
      description="Load or remove the deterministic full-year UAT dataset used to validate dashboards, workflows, Finance, operations, expenses, assets and reporting before deployment."
      actions={<button className="finance-secondary-button" type="button" onClick={() => void refresh()} disabled={loading || busy !== null}><RefreshCcw size={16}/> Refresh</button>}
    />

    <div className="finance-warning-message">
      <ShieldAlert size={18}/>
      <div><strong>Finance testing control only.</strong> This panel is disabled in production. The remove action targets only UAT26-prefixed / UAT_YEAR_SIMULATION_2026 records and never truncates the database.</div>
    </div>

    {notice && <div className="finance-success-message">{notice}</div>}
    {error && <div className="finance-error">{error}</div>}
    {loading && <div className="finance-panel finance-empty-state">Checking 2026 UAT dataset status...</div>}

    {!loading && status && <section className="finance-panel">
      <div className="finance-panel-header">
        <div>
          <span className="finance-panel-kicker">CURRENT TEST DATA STATUS</span>
          <h2>{status.loaded ? '2026 UAT Dataset Loaded' : '2026 UAT Dataset Not Loaded'}</h2>
          <p>{status.loaded ? 'Synthetic data is currently available for complete ERP visualization and end-to-end testing.' : 'The ERP is currently using only the data already present in the database.'}</p>
        </div>
      </div>

      <section className="finance-kpi-grid finance-kpi-grid-4">
        <article className="finance-kpi-card"><span>UAT Clients</span><strong>{status.counts.clients}</strong><small>Expected when loaded: 50</small></article>
        <article className="finance-kpi-card"><span>UAT Projects</span><strong>{status.counts.projects}</strong><small>Expected when loaded: 200</small></article>
        <article className="finance-kpi-card"><span>Closed Invoices</span><strong>{v?.closed_invoices ?? 0}</strong><small>Fully realized Finance invoices</small></article>
        <article className="finance-kpi-card"><span>Realized Revenue</span><strong>{inr(v?.realized_revenue_inr)}</strong><small>Expected full-year target: ₹4 crore</small></article>
      </section>

      {v && <div className="finance-table-wrap" style={{marginTop:16}}>
        <table className="finance-table">
          <thead><tr><th>Coverage</th><th>Count</th><th>Coverage</th><th>Count</th></tr></thead>
          <tbody>
            <tr><td>Invoices</td><td>{v.invoices ?? 0}</td><td>Payments</td><td>{v.payments ?? 0}</td></tr>
            <tr><td>Work Packages</td><td>{v.work_packages ?? 0}</td><td>Expense Claims</td><td>{v.expense_claims ?? 0}</td></tr>
            <tr><td>Project Expenses</td><td>{v.project_expenses ?? 0}</td><td>Vendor Invoices</td><td>{v.vendor_invoices ?? 0}</td></tr>
            <tr><td>Travel/KM Claims</td><td>{v.travel_km_claims ?? 0}</td><td>Assets / IT Work / Drones</td><td>{(v.uat_assets ?? 0)} / {(v.uat_work_records ?? 0)} / {(v.uat_drones ?? 0)}</td></tr>
          </tbody>
        </table>
      </div>}

      <div className="finance-header-actions" style={{marginTop:18, flexWrap:'wrap'}}>
        {!status.loaded && <button className="finance-primary-button" type="button" onClick={loadDataset} disabled={!status.enabled || busy !== null}>
          <Database size={16}/>{busy === 'load' ? ' Loading 2026 Test Data...' : ' Load 2026 Testing Data'}
        </button>}
        {status.loaded && <button className="finance-secondary-button" type="button" onClick={removeDataset} disabled={!status.enabled || busy !== null}>
          <Trash2 size={16}/>{busy === 'remove' ? ' Removing Test Data...' : ' Remove 2026 Testing Data'}
        </button>}
      </div>

      {!status.enabled && <div className="finance-error" style={{marginTop:14}}>UAT controls are disabled by environment configuration.</div>}
    </section>}
  </div>
}
