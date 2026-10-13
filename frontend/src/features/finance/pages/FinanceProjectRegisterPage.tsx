import { FolderOpen, RefreshCcw, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import type { FinanceProject } from '../../../types'
import { ProjectDetailsPanel, ProjectRegisterFilters, ProjectRegisterTable, type RegisterProject } from '../../operations/components/ProjectRegister'
import { FINANCE_STATUS_OPTIONS, filterProjects } from '../../operations/components/register-utils'
import { Project360, formatMoney, lifecycleStatusLabel, lifecycleStatusTone } from '../../operations/lifecycle-types'
import '../../operations/operations.css'

type WorkflowDashboard = { projects: RegisterProject[] }

// Finance can also find Project Master records that never entered the BD workflow.
const FINANCE_FILTER_OPTIONS = [...FINANCE_STATUS_OPTIONS, { value: 'legacy', label: 'Legacy (No Workflow)' }]

/** Project Master record with no BD workflow row: no Finance/operational workflow status exists for it. */
function legacyProject(row: FinanceProject): RegisterProject {
  return {
    id: row.id, project_code: row.project_code, project_name: row.project_name, client_code: row.client_code, client_name: row.client_name,
    start_date: row.start_date, end_date: row.end_date, scope_text: row.task || row.description,
    workflow_status: null, lifecycle_status: row.lifecycle_status, project_manager_id: row.project_manager_id, project_manager_name: row.project_manager_name,
  }
}

/**
 * Finance Project Register: view-only. It renders the same shared Project
 * Register presentation as BD Project Management with `readOnly`, so only the
 * Details action exists -- no Create/Edit/Resubmit/Assign PM/Change Client/Delete.
 * Billing actions live in the separate Finance Billing workflow.
 */
export function FinanceProjectRegisterPage() {
  const [projects, setProjects] = useState<RegisterProject[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [lifecycle, setLifecycle] = useState<Project360 | null>(null)
  const [lifecycleError, setLifecycleError] = useState('')
  const [lifecycleLoading, setLifecycleLoading] = useState(false)
  const [query, setQuery] = useState('')
  const [financeFilter, setFinanceFilter] = useState('all')
  const [operationalFilter, setOperationalFilter] = useState('all')
  const [error, setError] = useState('')

  function load() {
    setError('')
    // Every Project Master record, enriched with the BD workflow status where one exists.
    void Promise.all([
      apiFetch<FinanceProject[]>('/finance/report-projects'),
      apiFetch<WorkflowDashboard>('/operations/workflow/finance/dashboard'),
    ])
      .then(([master, workflow]) => {
        const byId = new Map(workflow.projects.map(row => [row.id, row]))
        setProjects(master.map(row => byId.get(row.id) ?? legacyProject(row)))
      })
      .catch(err => setError(err instanceof Error ? err.message : 'Unable to load the Project Register'))
  }
  useEffect(load, [])

  const rows = useMemo(() => filterProjects(projects, query, financeFilter, operationalFilter), [projects, query, financeFilter, operationalFilter])
  const selected = projects.find(row => row.id === selectedId) ?? null

  useEffect(() => {
    if (!selectedId) { setLifecycle(null); setLifecycleError(''); return }
    let cancelled = false
    setLifecycleLoading(true)
    setLifecycleError('')
    void apiFetch<Project360>(`/operations/lifecycle/projects/${selectedId}`)
      .then(row => { if (!cancelled) setLifecycle(row) })
      .catch(err => { if (!cancelled) { setLifecycle(null); setLifecycleError(err instanceof Error ? err.message : 'Client feedback/billing lifecycle detail is not available for this project.') } })
      .finally(() => { if (!cancelled) setLifecycleLoading(false) })
    return () => { cancelled = true }
  }, [selectedId])

  return <div className="operations-page">
    <DashboardHeader
      eyebrow="FINANCE · PROJECT PORTFOLIO INTELLIGENCE"
      title="Project Register"
      description="Search the complete project portfolio and inspect finance status, operational status plus the client feedback, rework and billing lifecycle. View-only register — billing actions are handled in Finance Billing."
      meta={<><span className="nk-meta-chip"><FolderOpen size={14} /> {projects.length} projects</span><span className="nk-meta-chip"><Search size={14} /> {rows.length} matching filters</span></>}
      actions={<button className="operations-button secondary" onClick={load}><RefreshCcw size={16} /> Refresh</button>}
    />
    {error && <div className="operations-alert error">{error}</div>}
    <section className="operations-panel">
      <ProjectRegisterFilters query={query} onQueryChange={setQuery} financeFilter={financeFilter} onFinanceFilterChange={setFinanceFilter} operationalFilter={operationalFilter} onOperationalFilterChange={setOperationalFilter} financeOptions={FINANCE_FILTER_OPTIONS} />
      <ProjectRegisterTable readOnly rows={rows} onDetails={row => setSelectedId(row.id)} />
    </section>

    {selected && <ProjectDetailsPanel project={selected} />}

    {selected && <section className="operations-panel">
      <header><div><span className="operations-kicker">V8.1 LIFECYCLE</span><h2>Client Feedback, Rework &amp; Billing Status</h2></div></header>
      {lifecycleLoading && <div className="operations-empty">Loading lifecycle detail...</div>}
      {!lifecycleLoading && lifecycleError && <div className="operations-note">{lifecycleError}</div>}
      {!lifecycleLoading && lifecycle && <>
        <div className="operations-detail-grid">
          <div><span>Lifecycle Stage</span><strong><span className={`operations-status ${lifecycleStatusTone(lifecycle.workflow_status)}`}>{lifecycleStatusLabel(lifecycle.workflow_status)}</span></strong></div>
          <div><span>Progress</span><strong>{lifecycle.progress_percent}%</strong></div>
          <div><span>Rework Cycles</span><strong>{lifecycle.rework_count}</strong></div>
          <div><span>Invoices</span><strong>{lifecycle.invoice_count}</strong></div>
          <div><span>Outstanding Balance</span><strong>{formatMoney(lifecycle.invoice_balance)}</strong></div>
          <div><span>Overdue</span><strong>{lifecycle.has_overdue_invoice ? 'Yes' : 'No'}</strong></div>
        </div>
        {!!lifecycle.invoices.length && <div className="operations-table-wrap"><table className="operations-table">
          <thead><tr><th>Invoice</th><th>Status</th><th>Amount</th><th>Paid</th><th>Balance</th></tr></thead>
          <tbody>{lifecycle.invoices.map(row => <tr key={row.id}><td>{row.invoice_number}</td><td><span className={`operations-status ${lifecycleStatusTone(row.status)}`}>{lifecycleStatusLabel(row.status)}</span></td><td>{formatMoney(row.total_amount, row.currency)}</td><td>{formatMoney(row.paid_amount, row.currency)}</td><td>{formatMoney(row.balance, row.currency)}</td></tr>)}</tbody>
        </table></div>}
      </>}
    </section>}
  </div>
}
