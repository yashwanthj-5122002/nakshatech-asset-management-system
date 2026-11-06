import {
  Activity, ArrowRight, BadgeIndianRupee, CheckCircle2, ChevronRight,
  ClipboardCheck, Download, Eye, FileCheck2, FilePlus2, FileText, FolderKanban,
  IndianRupee, Layers3, Plus, RefreshCcw, Search, Send, ShieldCheck,
  SlidersHorizontal, UsersRound, Wallet, X,
} from 'lucide-react'
import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../../../lib/api'
import { commercialFormProblems, commercialFormToPayload, emptyCommercialForm, type CommercialFormState } from '../../commercial/commercial-form'
import { CommercialDetailsSection } from '../../commercial/components/CommercialDetailsSection'
import type { CurrencyPayload } from '../../commercial/types'
import type { LifecycleDashboard } from '../../operations/lifecycle-types'
import { FinanceBillingPage } from './FinanceBillingPage'
import '../../operations/operations.css'
import './finance-management-projects.css'
import './finance-management-prussian-theme.css'

type ManagementClient = {
  id: number; client_code: string; client_name: string; source_person_name: string
  contact_person_name: string; client_email: string | null; address: string | null
  gst_number: string | null; work_description: string | null; is_active: boolean
}
type ManagementProject = {
  id: number; management_client_id: number; project_code: string; project_name: string
  source_person_name: string; department_code: string; department_label: string
  workflow_status: string; project_manager_id: number | null; project_manager_name: string | null
  start_date: string; end_date: string; created_at: string
  project_value: number | null; currency: string; source_approved: boolean
}
type AdditionalProjectRequest = {
  id: number; management_client_id: number; client_code: string; client_name: string
  source_person_name: string; project_name: string; scope_text: string
  expected_start_date: string | null; remarks: string | null; status: 'PENDING' | 'CREATED'
  created_project_id: number | null; created_project_code: string | null; created_at: string
}
type Register = { clients: ManagementClient[]; projects: ManagementProject[] }
type PM = { id: number; full_name: string; employee_id?: string | null }
type Options = { departments: Array<{ code: string; label: string }>; project_managers_by_department: Record<string, PM[]> }
type ProjectFinancial = {
  invoice_count: number; invoiced_inr: number; received_inr: number
  outstanding_inr: number; missing_fx_rows: number
}
type Summary = {
  projects: Record<string, ProjectFinancial>
  totals: ProjectFinancial & { collection_rate: number }
}
type StageKey = 'production' | 'qc' | 'qa' | 'delivery'
type StageTracking = { completed: number; total: number; percent: number; in_progress: number }
type ProjectTracking = {
  overall_percent: number; operational_status: string; work_units: number
  active_files: number; legacy_areas: number; rework_count: number
  last_activity_at: string | null; stages: Record<StageKey, StageTracking>
}
type TrackingResponse = { as_of: string; projects: Record<string, ProjectTracking> }
type TrackingFile = {
  work_package_item_id: number | null; package_code: string; item_number: string
  item_name: string | null; is_active: boolean; tracking_basis: 'file_activity' | 'legacy_area'
  production: string; qc: string; qa: string; delivery: string
  production_completed_at: string | null; qc_completed_at: string | null
  qa_completed_at: string | null; delivered_at: string | null
  production_employee: string | null; qc_employee: string | null; qa_employee: string | null
}
type TrackingDetail = { project_id: number; as_of: string; summary: ProjectTracking; files: TrackingFile[] }
const STAGE_KEYS: StageKey[] = ['production', 'qc', 'qa', 'delivery']
const STAGE_LABELS: Record<StageKey, string> = { production: 'Production', qc: 'QC', qa: 'QA', delivery: 'Delivery' }
const statusTone = (value: string) => {
  const s = value.toLowerCase()
  if (['completed', 'passed', 'approved', 'delivered'].includes(s)) return 'complete'
  if (['rejected', 'rework', 'production_rework'].includes(s)) return 'rework'
  if (s === 'in_progress' || s === 'started') return 'active'
  return 'pending'
}

// NAKSHA MANAGEMENT PROGRESS V8 FUNCTION START
// Management UI presentation only. Never change incoming percentages.
function managementProgressTone(p: number): 'red'|'orange'|'yellow'|'green' {
  const n = Number.isFinite(p) ? Math.max(0, Math.min(100, p)) : 0
  if (n < 30) return 'red'
  if (n < 50) return 'orange'
  if (n < 70) return 'yellow'
  return 'green'
}
// NAKSHA MANAGEMENT PROGRESS V8 FUNCTION END

function StageTrackingBars({ tracking, compact = false }: { tracking: ProjectTracking; compact?: boolean }) {
  return <div className={compact ? 'mp-stage-tracking compact' : 'mp-stage-tracking'}>
    {STAGE_KEYS.map(stage => {
      const item = tracking.stages[stage]
      return <div className="mp-stage-track" key={stage}>
        <div className="mp-stage-track-label"><strong>{STAGE_LABELS[stage]}</strong><span>{item.completed}/{item.total} · {item.percent.toFixed(0)}%</span></div>
        <div className="mp-progress"><span className={`mp-v8-${managementProgressTone(item.percent)}`} style={{ width: `${Math.min(100, Math.max(0, item.percent))}%` }}/></div>
      </div>
    })}
  </div>
}
function FileTrackingTable({ detail }: { detail: TrackingDetail }) {
  return <div className="mp-file-tracking">
    <div className="mp-file-heading"><h3>File-wise Tracking</h3><span>{detail.summary.active_files} active files · {detail.summary.legacy_areas} legacy areas</span></div>
    {detail.files.length === 0 ? <p className="mp-tracking-note">No work packages or files have been allocated to this project yet.</p> :
      <div className="mp-table-scroll"><table className="mp-table mp-file-table"><thead><tr><th>Area / File</th><th>Production</th><th>QC</th><th>QA</th><th>Delivery</th></tr></thead><tbody>
        {detail.files.map((file, index) => <tr key={`${file.work_package_item_id ?? 'area'}-${file.package_code}-${index}`} className={!file.is_active ? 'mp-inactive-file' : ''}>
          <td><strong>{file.item_number}</strong><small>{file.package_code}{file.tracking_basis === 'legacy_area' ? ' · Area tracking' : ''}{!file.is_active ? ' · Inactive' : ''}</small></td>
          {STAGE_KEYS.map(stage => {
            const raw = file[stage] || 'not_started'
            const person = stage === 'delivery' ? null : file[`${stage}_employee` as 'production_employee' | 'qc_employee' | 'qa_employee']
            return <td key={stage}><span className={`mp-stage-badge ${statusTone(raw)}`} data-management-status={statusLabel(raw)}>{statusLabel(raw)}</span>{person && <small>{person}</small>}</td>
          })}
        </tr>)}
      </tbody></table></div>}
  </div>
}
type ProjectForm = {
  project_code: string; project_name: string; scope_text: string; start_date: string
  end_date: string; performing_department_code: string; priority: string
  quantity: string; quantity_unit: string; description: string; project_manager_id: string
}
type MainTab = 'projects' | 'clients' | 'invoices' | 'payments' | 'tracking' | 'requests'
type DetailTab = 'overview' | 'workflow' | 'billing'

const emptyProject = (): ProjectForm => ({
  project_code: '', project_name: '', scope_text: '', start_date: '', end_date: '',
  performing_department_code: '', priority: 'medium', quantity: '', quantity_unit: 'unit',
  description: '', project_manager_id: '',
})
const EMPTY_FINANCIAL: ProjectFinancial = {
  invoice_count: 0, invoiced_inr: 0, received_inr: 0, outstanding_inr: 0, missing_fx_rows: 0,
}
const INVOICE_STATES = new Set([
  'READY_FOR_BILLING', 'INVOICE_DRAFT', 'INVOICE_RAISED', 'PAYMENT_PENDING',
  'PARTIALLY_PAID', 'PAYMENT_OVERDUE', 'CLOSED',
])
const WORKFLOW_STEPS = [
  { label: 'Create Project', sub: 'Finance', icon: FilePlus2 },
  { label: 'Assign Department', sub: 'Project Manager', icon: UsersRound },
  { label: 'Production', sub: 'Execution', icon: Layers3 },
  { label: 'QC / QA', sub: 'Quality Checks', icon: ClipboardCheck },
  { label: 'Delivery', sub: 'Final Output', icon: Send },
  { label: 'Generate Invoice', sub: 'Existing Engine', icon: FileText },
  { label: 'Receive Payment', sub: 'Full / Partial', icon: IndianRupee },
  { label: 'Project Closure', sub: 'Completed', icon: CheckCircle2 },
]
const money = (amount: number) => `₹${new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2, minimumFractionDigits: 0 }).format(amount)}`
const projectMoney = (amount: number | null, currency: string) => amount == null ? '—' :
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: currency || 'INR', maximumFractionDigits: 2 }).format(amount)
const statusLabel = (status: string) => status.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase())
const managementStatusLabel = (status: string, approved: boolean) =>
  status.toUpperCase() === 'READY_FOR_BILLING' && approved
    ? 'Approved / Ready for Billing' : statusLabel(status)
const shortDate = (value: string) => value ? new Date(`${value.slice(0, 10)}T12:00:00`).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'
const currentWorkflowStep = (status: string) => {
  const s = status.toUpperCase()
  if (s === 'CLOSED') return 7
  if (/PAYMENT|INVOICE_RAISED|OVERDUE/.test(s)) return 6
  if (/INVOICE_DRAFT|READY_FOR_BILLING/.test(s)) return 5
  if (/DELIVER|APPROVAL_PENDING|CLIENT_FEEDBACK|CLIENT_ACCEPT/.test(s)) return 4
  if (/\bQA\b|\bQC\b|QUALITY/.test(s)) return 3
  if (/PRODUCTION|IN_PROGRESS|WORK/.test(s)) return 2
  if (/PM_ASSIGNED|ASSIGNED/.test(s)) return 1
  return 0
}
function exportCsv(rows: ManagementProject[], clients: ManagementClient[], lifecycle: LifecycleDashboard | null, summary: Summary | null, tracking: TrackingResponse | null) {
  const escapeCell = (value: string | number | null | undefined) => {
    const raw = String(value ?? '')
    // Avoid formula execution when the CSV is opened in Excel.
    const safe = /^[\s]*[=+@\-\t\r]/.test(raw) && typeof value === 'string' ? `'${raw}` : raw
    return `"${safe.replace(/"/g, '""')}"`
  }
  const columns = ['Project Code', 'Project Name', 'Client', 'Source', 'Department', 'Project Manager', 'Status', 'Operational Status', 'Overall Stage Progress %', 'Production %', 'QC %', 'QA %', 'Delivery %', 'Project Value', 'Currency', 'Invoiced INR', 'Received INR', 'Outstanding INR']
  const csv = [columns.map(escapeCell).join(','), ...rows.map(row => {
    const client = clients.find(item => item.id === row.management_client_id)
    const life = lifecycle?.projects.find(item => item.id === row.id)
    const financial = summary?.projects[String(row.id)] ?? EMPTY_FINANCIAL
    const stages = tracking?.projects[String(row.id)]
    return [row.project_code, row.project_name, client?.client_name, row.source_person_name, row.department_label,
      row.project_manager_name, life?.workflow_status ?? row.workflow_status,
      stages?.operational_status ?? 'Tracking unavailable', stages?.overall_percent ?? '',
      ...STAGE_KEYS.map(stage => stages?.stages[stage].percent ?? ''),
      row.project_value, row.currency, financial.invoiced_inr, financial.received_inr, financial.outstanding_inr].map(escapeCell).join(',')
  })].join('\r\n')
  const url = URL.createObjectURL(new Blob(['\uFEFF', csv], { type: 'text/csv;charset=utf-8;' }))
  const link = document.createElement('a')
  link.href = url
  link.download = 'nakshatech-management-projects.csv'
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function FinanceManagementProjectsPage() {
  const [data, setData] = useState<Register>({ clients: [], projects: [] })
  const [options, setOptions] = useState<Options>({ departments: [], project_managers_by_department: {} })
  const [currencies, setCurrencies] = useState<CurrencyPayload | null>(null)
  const [lifecycle, setLifecycle] = useState<LifecycleDashboard | null>(null)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [tracking, setTracking] = useState<TrackingResponse | null>(null)
  const [trackingDetail, setTrackingDetail] = useState<TrackingDetail | null>(null)
  const [trackingError, setTrackingError] = useState('')
  const [detailError, setDetailError] = useState('')
  const [trackingRefreshedAt, setTrackingRefreshedAt] = useState('')
  const [selectedClientId, setSelectedClientId] = useState<number | null>(null)
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [additionalRequests, setAdditionalRequests] = useState<AdditionalProjectRequest[]>([])
  const [selectedRequestId, setSelectedRequestId] = useState<number | null>(null)
  const [requestSearch, setRequestSearch] = useState('')
  const [requestFetchError, setRequestFetchError] = useState('')
  const [project, setProject] = useState<ProjectForm>(emptyProject)
  const [commercial, setCommercial] = useState<CommercialFormState>(emptyCommercialForm)
  const [pmChoice, setPmChoice] = useState<Record<number, string>>({})
  const [activeTab, setActiveTab] = useState<MainTab>('projects')
  const [detailTab, setDetailTab] = useState<DetailTab>('overview')
  const [search, setSearch] = useState('')
  const [departmentFilter, setDepartmentFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [clientPage, setClientPage] = useState(1)
  const [projectPage, setProjectPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function load() {
    setLoading(true)
    setError('')
    try {
      const [register, assignment, billing, financial] = await Promise.all([
        apiFetch<Register>('/finance/management-projects'),
        apiFetch<Options>('/finance/management-projects/assignment-options'),
        apiFetch<LifecycleDashboard>('/operations/lifecycle/dashboard'),
        apiFetch<Summary>('/finance/management-projects/summary'),
      ])
      setData(register); setOptions(assignment); setLifecycle(billing); setSummary(financial)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load Management Projects')
    } finally { setLoading(false) }
  }
  useEffect(() => { void load(); void apiFetch<CurrencyPayload>('/commercial/currencies').then(setCurrencies).catch(() => undefined) }, [])
  // Refresh only management records and their existing financial ledger every 15 seconds.
  useEffect(() => {
    const timer = window.setInterval(() => {
      void Promise.all([
        apiFetch<Register>('/finance/management-projects'),
        apiFetch<LifecycleDashboard>('/operations/lifecycle/dashboard'),
        apiFetch<Summary>('/finance/management-projects/summary'),
      ]).then(([register, billing, financial]) => {
        setData(register); setLifecycle(billing); setSummary(financial)
      }).catch(() => undefined)
    }, 15000)
    return () => window.clearInterval(timer)
  }, [])

  // The independent Finance request queue refreshes even when the normal project tab is open.
  useEffect(() => {
    let alive = true
    const refresh = () => {
      if (document.visibilityState === 'hidden') return
      void apiFetch<AdditionalProjectRequest[]>('/finance/management-projects/additional-project-requests')
        .then(rows => { if (alive) { setAdditionalRequests(rows); setRequestFetchError('') } })
        .catch(err => { if (alive) setRequestFetchError(err instanceof Error ? err.message : 'Request list unavailable') })
    }
    refresh()
    const interval = window.setInterval(refresh, 5000)
    return () => { alive = false; window.clearInterval(interval) }
  }, [])

  // File-level tracking is a separate read-only Finance endpoint. Do not let a
  // tracking outage blank the client register, invoices or other Finance data.
  useEffect(() => {
    let alive = true
    let pending = false
    const refresh = async () => {
      if (pending || document.visibilityState === 'hidden') return
      pending = true
      try {
        const result = await apiFetch<TrackingResponse>('/finance/management-projects/tracking')
        if (alive) {
          setTracking(result)
          setTrackingError('')
          setTrackingRefreshedAt(new Date().toLocaleTimeString('en-IN'))
        }
      } catch (err) {
        if (alive) setTrackingError(err instanceof Error ? err.message : 'Tracking refresh failed')
      } finally { pending = false }
    }
    void refresh()
    const timer = window.setInterval(() => void refresh(), 5000)
    const onFocus = () => void refresh()
    window.addEventListener('focus', onFocus)
    document.addEventListener('visibilitychange', onFocus)
    return () => { alive = false; window.clearInterval(timer); window.removeEventListener('focus', onFocus); document.removeEventListener('visibilitychange', onFocus) }
  }, [])
  useEffect(() => {
    if (selectedProjectId === null) { setTrackingDetail(null); setDetailError(''); return }
    let alive = true
    let pending = false
    setTrackingDetail(null)
    const refresh = async () => {
      if (pending || document.visibilityState === 'hidden') return
      pending = true
      try {
        const detail = await apiFetch<TrackingDetail>(`/finance/management-projects/${selectedProjectId}/tracking`)
        if (alive) { setTrackingDetail(detail); setDetailError('') }
      } catch (err) {
        if (alive) setDetailError(err instanceof Error ? err.message : 'File tracking unavailable')
      } finally { pending = false }
    }
    void refresh()
    const timer = window.setInterval(() => void refresh(), 5000)
    const onFocus = () => void refresh()
    window.addEventListener('focus', onFocus)
    return () => { alive = false; window.clearInterval(timer); window.removeEventListener('focus', onFocus) }
  }, [selectedProjectId])

  const selectedClient = data.clients.find(row => row.id === selectedClientId) ?? null
  const selectedProject = data.projects.find(row => row.id === selectedProjectId) ?? null
  const selectedLifecycle = lifecycle?.projects.find(row => row.id === selectedProjectId) ?? null
  const selectedTracking = selectedProjectId === null ? null : tracking?.projects[String(selectedProjectId)] ?? null
  const selectedFinancial = selectedProject ? (summary?.projects[String(selectedProject.id)] ?? EMPTY_FINANCIAL) : EMPTY_FINANCIAL
  const billingStatus = selectedLifecycle?.workflow_status ?? selectedProject?.workflow_status ?? ''
  const canOpenInvoices = INVOICE_STATES.has(billingStatus.toUpperCase()) &&
    (Boolean(selectedProject?.source_approved) || selectedFinancial.invoice_count > 0)
  const pmOptions = options.project_managers_by_department[project.performing_department_code] ?? []
  const clientById = useMemo(() => new Map(data.clients.map(row => [row.id, row])), [data.clients])
  const lifecycleById = useMemo(() => new Map((lifecycle?.projects ?? []).map(row => [row.id, row])), [lifecycle])
  const sources = useMemo(() => [...new Set(data.clients.map(row => row.source_person_name).filter(Boolean))].sort(), [data.clients])
  const statuses = useMemo(() => [...new Set(data.projects.map(row => lifecycleById.get(row.id)?.workflow_status ?? row.workflow_status))].sort(), [data.projects, lifecycleById])
  const filteredProjects = useMemo(() => data.projects.filter(row => {
    const client = clientById.get(row.management_client_id)
    const status = lifecycleById.get(row.id)?.workflow_status ?? row.workflow_status
    const term = search.trim().toLowerCase()
    return (!term || [row.project_code, row.project_name, client?.client_name, row.source_person_name, row.department_label]
      .some(value => (value ?? '').toLowerCase().includes(term))) &&
      (!departmentFilter || row.department_code === departmentFilter) &&
      (!statusFilter || status === statusFilter) &&
      (!sourceFilter || row.source_person_name === sourceFilter)
  }), [data.projects, clientById, lifecycleById, search, departmentFilter, statusFilter, sourceFilter])
  const filteredClients = useMemo(() => data.clients.filter(row => {
    const term = search.trim().toLowerCase()
    return (!term || [row.client_code, row.client_name, row.source_person_name].some(value => value.toLowerCase().includes(term))) &&
      (!sourceFilter || row.source_person_name === sourceFilter)
  }), [data.clients, search, sourceFilter])
  // NAKSHA_FINANCE_PAGINATION_5_PER_PAGE_V1: restrict ONLY Projects/Clients table rows, not the source datasets.
  const financePageSize = 5
  const clientPageCount = Math.max(1, Math.ceil(filteredClients.length / financePageSize))
  const projectPageCount = Math.max(1, Math.ceil(filteredProjects.length / financePageSize))
  const currentClientPage = Math.min(clientPage, clientPageCount)
  const currentProjectPage = Math.min(projectPage, projectPageCount)
  const paginatedClients = filteredClients.slice((currentClientPage - 1) * financePageSize, currentClientPage * financePageSize)
  const paginatedProjects = filteredProjects.slice((currentProjectPage - 1) * financePageSize, currentProjectPage * financePageSize)
  // Search and filters still operate on ALL clients/projects; restart from page 1 on filter changes.
  useEffect(() => { setClientPage(1); setProjectPage(1) }, [search, departmentFilter, statusFilter, sourceFilter])
  // Clamp each page if live refresh removes records.
  useEffect(() => { if (clientPage > clientPageCount) setClientPage(clientPageCount) }, [clientPage, clientPageCount])
  useEffect(() => { if (projectPage > projectPageCount) setProjectPage(projectPageCount) }, [projectPage, projectPageCount])
  const paginationIsClients = activeTab === 'clients'
  const paginationCount = paginationIsClients ? filteredClients.length : filteredProjects.length
  const paginationPage = paginationIsClients ? currentClientPage : currentProjectPage
  const paginationPages = paginationIsClients ? clientPageCount : projectPageCount
  const paginationFirst = paginationCount === 0 ? 0 : (paginationPage - 1) * financePageSize + 1
  const paginationLast = Math.min(paginationPage * financePageSize, paginationCount)
  const activeProjects = data.projects.filter(row => !['CLOSED', 'COMPLETED'].includes((lifecycleById.get(row.id)?.workflow_status ?? row.workflow_status).toUpperCase())).length
  const total = summary?.totals ?? { ...EMPTY_FINANCIAL, collection_rate: 0 }

  function openCreate(client?: ManagementClient, requestRow?: AdditionalProjectRequest) {
    const chosen = client ?? data.clients.find(item => item.is_active)
    if (!chosen) {
      setActiveTab('clients')
      setNotice('No active management clients yet. Vinod Sir or Chethan Sir must register a client first.')
      return
    }
    setSelectedClientId(chosen.id)
    setSelectedRequestId(requestRow?.id ?? null)
    setProject({ ...emptyProject(),
      project_name: requestRow?.project_name ?? '',
      scope_text: requestRow?.scope_text ?? chosen.work_description ?? '',
      start_date: requestRow?.expected_start_date ?? '',
      description: requestRow?.remarks ?? '',
    })
    setCommercial(emptyCommercialForm())
    setShowCreate(true)
    setError(''); setNotice('')
  }

  function openDetails(row: ManagementProject, tab: DetailTab = 'overview') {
    setSelectedProjectId(row.id)
    setDetailTab(tab)
    setShowCreate(false)
  }

  async function createProject(event: FormEvent) {
    event.preventDefault()
    if (!selectedClient) return
    if (!project.performing_department_code) { setError('Select the Performing Department.'); return }
    const problems = commercialFormProblems(commercial)
    if (problems.length) { setError(problems[0]); return }
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await apiFetch<{ project_id: number; project_code: string }>('/finance/management-projects', {
        method: 'POST', body: JSON.stringify({
          management_client_id: selectedClient.id,
          additional_request_id: selectedRequestId,
          project_code: project.project_code, project_name: project.project_name,
          scope_text: project.scope_text, start_date: project.start_date, end_date: project.end_date,
          performing_department_code: project.performing_department_code, priority: project.priority,
          quantity: project.quantity ? Number(project.quantity) : null,
          quantity_unit: project.quantity_unit || 'unit', description: project.description || null,
          project_manager_id: project.project_manager_id ? Number(project.project_manager_id) : null,
          commercial: commercialFormToPayload(commercial),
        }),
      })
      setShowCreate(false)
      setSelectedRequestId(null)
      void apiFetch<AdditionalProjectRequest[]>('/finance/management-projects/additional-project-requests').then(setAdditionalRequests).catch(() => undefined)
      setSelectedProjectId(result.project_id)
      setDetailTab('overview')
      setActiveTab('projects')
      setNotice(`${result.project_code} created and Finance-approved. ${project.project_manager_id ? 'Department Project Manager assigned.' : 'Assign a department Project Manager to begin operations.'} Invoicing is available after Ready For Billing.`)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to create Management Project')
    } finally { setBusy(false) }
  }

  async function assignPm(row: ManagementProject) {
    const id = Number(pmChoice[row.id] || 0)
    if (!id) { setError('Select a Project Manager for the assigned department.'); return }
    setBusy(true); setError(''); setNotice('')
    try {
      await apiFetch(`/finance/management-projects/${row.id}/assign-pm`, {
        method: 'POST', body: JSON.stringify({ project_manager_id: id }),
      })
      setNotice(`${row.project_code}: Department Project Manager assigned.`)
      await load()
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to assign Project Manager') }
    finally { setBusy(false) }
  }

  const tabs: Array<{ id: MainTab; label: string; icon: typeof FolderKanban }> = [
    { id: 'projects', label: 'Projects', icon: FolderKanban },
    { id: 'clients', label: 'Clients', icon: UsersRound },
    { id: 'invoices', label: 'Invoices', icon: FileText },
    { id: 'payments', label: 'Payments', icon: Wallet },
    { id: 'tracking', label: 'Tracking', icon: Activity },
    { id: 'requests', label: 'Project Requests', icon: FilePlus2 },
  ]

  return <div className="operations-page mp-page">
    <header className="mp-heading">
      <div className="mp-heading-title">
        <div className="mp-heading-icon"><Layers3 size={25}/></div>
        <div>
          <span className="mp-eyebrow">FINANCE / MANAGEMENT PROJECTS</span>
          <h1>Management Projects</h1>
          <p>Projects created by Finance for Management Clients (Vinod Sir / Chethan Sir)</p>
        </div>
      </div>
      <div className="mp-heading-actions">
        <button className="mp-button mp-button-muted" type="button" disabled={loading} onClick={() => void load()}><RefreshCcw size={16}/> Refresh</button>
        <button className="mp-button mp-button-primary" type="button" onClick={() => openCreate()}><Plus size={18}/> Create Management Project</button>
      </div>
    </header>

    {error && <div className="operations-alert error" role="alert">{error}</div>}
    {notice && <div className="operations-alert success" role="status">{notice}</div>}
    {loading && <div className="mp-loading" role="status">Refreshing management clients, projects and financial totals…</div>}

    <div className="mp-stats">
      <div className="mp-stat mp-stat-blue"><div className="mp-stat-label"><UsersRound size={19}/> Management Clients</div><strong>{data.clients.length}</strong><small>{sources.map(source => `${source}: ${data.clients.filter(c => c.source_person_name === source).length}`).join('  ·  ') || 'No clients registered'}</small></div>
      <div className="mp-stat mp-stat-green"><div className="mp-stat-label"><FolderKanban size={19}/> Total Projects</div><strong>{data.projects.length}</strong><small>Active: {activeProjects} · Closed: {data.projects.length - activeProjects}</small></div>
      <div className="mp-stat mp-stat-gold"><div className="mp-stat-label"><FileText size={19}/> Total Invoiced (INR)</div><strong>{money(total.invoiced_inr)}</strong><small>{total.invoice_count} invoice record(s), including drafts</small></div>
      <div className="mp-stat mp-stat-cyan"><div className="mp-stat-label"><Wallet size={19}/> Amount Received (INR)</div><strong>{money(total.received_inr)}</strong><small>Outstanding: {money(total.outstanding_inr)}</small></div>
      <div className="mp-stat mp-stat-purple"><div className="mp-stat-label"><BadgeIndianRupee size={19}/> Collection Rate</div><strong>{total.collection_rate.toFixed(1)}%</strong><div className="mp-progress mp-stat-progress"><span style={{ width: `${Math.max(0, Math.min(100, total.collection_rate))}%` }}/></div><small>Invoice-value settlement basis</small></div>
    </div>
    {total.missing_fx_rows > 0 && <p className="mp-fx-note">Some foreign-currency invoice/payment rows have no recorded INR FX value ({total.missing_fx_rows}). INR totals exclude those amounts; see the existing Finance ledger for reconciliation.</p>}

    <nav className="mp-tabs" aria-label="Management Projects sections">
      {tabs.map(({ id, label, icon: Icon }) => <button key={id} type="button" className={activeTab === id ? 'mp-tab active' : 'mp-tab'} aria-current={activeTab === id ? 'page' : undefined} onClick={() => { setActiveTab(id); setSelectedProjectId(null) }}><Icon size={16}/>{label}{id === 'requests' && additionalRequests.filter(r => r.status === 'PENDING').length > 0 && <span style={{ marginLeft: 4, background: '#fcebea', color: '#a23e3e', borderRadius: 9, padding: '2px 6px', fontSize: 11 }}>{additionalRequests.filter(r => r.status === 'PENDING').length}</span>}</button>)}
    </nav>

    {activeTab === 'requests' && <section className="mp-panel" aria-label="Existing client project requests">
      <div className="mp-panel-heading"><h2>Existing Client – Project Requests</h2><span>{additionalRequests.filter(r => r.status === 'PENDING').length} awaiting Finance</span></div>
      <p style={{ margin: '8px 0 12px', color: '#46647c', fontSize: 13 }}>When Vinod Sir or Chethan Sir requests another project for an existing client, it appears here. Use the normal Create Project form to complete it.</p>
      {requestFetchError && <p role="alert" style={{ color: '#a23e3e' }}>{requestFetchError}</p>}
      <label className="mp-search" style={{ display: 'block', marginBottom: 12 }}><Search size={17}/><input aria-label="Search project requests" placeholder="Search client, project or Management source…" value={requestSearch} onChange={e => setRequestSearch(e.target.value)}/></label>
      <div className="mp-table-scroll"><table className="mp-table"><thead><tr><th>Client</th><th>Requested Project</th><th>Management Source</th><th>Requested</th><th>Status</th><th>Action</th></tr></thead><tbody>
        {additionalRequests.filter(row => !requestSearch.trim() || [row.client_code, row.client_name, row.project_name, row.source_person_name].some(value => (value || '').toLowerCase().includes(requestSearch.trim().toLowerCase()))).sort((a,b) => (a.status === 'PENDING' ? 0 : 1) - (b.status === 'PENDING' ? 0 : 1)).map(row =>
          <tr key={row.id}><td><strong>{row.client_code}</strong><small>{row.client_name}</small></td>
            <td><strong>{row.project_name}</strong><small>{row.scope_text}</small>{row.remarks && <small>Notes: {row.remarks}</small>}</td>
            <td>{row.source_person_name}</td><td>{row.created_at ? new Date(row.created_at).toLocaleDateString('en-IN') : '—'}</td>
            <td><span style={{ display: 'inline-block', fontSize: 12, fontWeight: 500, borderRadius: 8, padding: '6px 9px', background: row.status === 'CREATED' ? '#e8f6eb' : '#fcebea', border: `1px solid ${row.status === 'CREATED' ? '#b9dec1' : '#efc9c6'}`, color: row.status === 'CREATED' ? '#166534' : '#a23e3e' }}>{row.status === 'CREATED' ? `Project Created: ${row.created_project_code || ''}` : 'Awaiting Finance'}</span></td>
            <td>{row.status === 'PENDING' ? <button className="mp-button mp-button-primary mp-button-small" type="button" disabled={!clientById.get(row.management_client_id)?.is_active} onClick={() => openCreate(clientById.get(row.management_client_id), row)}><Plus size={14}/> Create Project</button> : row.created_project_code}</td></tr>
        )}</tbody></table></div>
      {additionalRequests.length === 0 && !requestFetchError && <div className="mp-empty">No additional project requests yet.</div>}
    </section>}

    {activeTab !== 'requests' && <>
    <div className="mp-toolbar">
      <label className="mp-search"><Search size={17}/><input aria-label="Search management projects or clients" placeholder="Search by project, client or code…" value={search} onChange={e => setSearch(e.target.value)}/></label>
      {activeTab !== 'clients' && <select aria-label="Department filter" value={departmentFilter} onChange={e => setDepartmentFilter(e.target.value)}><option value="">All Departments</option>{options.departments.map(d => <option key={d.code} value={d.code}>{d.label}</option>)}</select>}
      {activeTab !== 'clients' && <select aria-label="Status filter" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}><option value="">All Statuses</option>{statuses.map(s => <option key={s} value={s}>{statusLabel(s)}</option>)}</select>}
      <select aria-label="Management source filter" value={sourceFilter} onChange={e => setSourceFilter(e.target.value)}><option value="">All Sources</option>{sources.map(s => <option key={s} value={s}>{s}</option>)}</select>
      <button type="button" className="mp-button mp-button-muted" onClick={() => { setSearch(''); setDepartmentFilter(''); setStatusFilter(''); setSourceFilter('') }}><SlidersHorizontal size={15}/> Reset</button>
      <button type="button" className="mp-button mp-button-muted" onClick={() => exportCsv(filteredProjects, data.clients, lifecycle, summary, tracking)} disabled={!filteredProjects.length} title="Export filtered management projects as CSV"><Download size={15}/> Export CSV</button>
    </div>

    <section className="mp-panel" aria-label={`${activeTab} register`}>
      <div className="mp-panel-heading"><h2>{({ projects: 'Management Project Register', clients: 'Registered Management Clients', invoices: 'Management Project Invoices', payments: 'Payments & Collections', tracking: 'Project Tracking', requests: 'Project Requests' })[activeTab]}</h2><span>{activeTab === 'clients' ? filteredClients.length : filteredProjects.length} records</span></div>
      <div className="mp-table-scroll">
        {activeTab === 'clients' ? <table className="mp-table"><thead><tr><th>Client Code</th><th>Client</th><th>Source</th><th>Projects</th><th>Action</th></tr></thead><tbody>
          {paginatedClients.map(client => <tr key={client.id}><td className="mp-code">{client.client_code}</td><td><strong>{client.client_name}</strong><small>{client.contact_person_name}</small></td><td><span className="mp-source">{client.source_person_name}</span></td><td>{data.projects.filter(p => p.management_client_id === client.id).length}</td><td><button type="button" className="mp-button mp-button-primary mp-button-small" disabled={!client.is_active} onClick={() => openCreate(client)}><Plus size={14}/> Create Project</button></td></tr>)}
        </tbody></table> : <table className="mp-table"><thead><tr><th>Project Code</th><th>Client / Source</th><th>Project Name</th><th>Department</th>{activeTab === 'payments' || activeTab === 'invoices' ? <><th>Invoiced (INR)</th><th>Received (INR)</th><th>Outstanding (INR)</th></> : <><th>Project Value</th><th>Status</th><th>Progress</th></>}<th>Action</th></tr></thead><tbody>
          {(activeTab === 'projects' ? paginatedProjects : filteredProjects).filter(row => activeTab !== 'invoices' || (summary?.projects[String(row.id)]?.invoice_count ?? 0) > 0 || INVOICE_STATES.has((lifecycleById.get(row.id)?.workflow_status ?? row.workflow_status).toUpperCase())).map(row => {
            const client = clientById.get(row.management_client_id)
            const life = lifecycleById.get(row.id)
            const status = life?.workflow_status ?? row.workflow_status
            const stageTracking = tracking?.projects[String(row.id)]
            const progress = Math.min(100, Math.max(0, stageTracking?.overall_percent ?? 0))
            const financial = summary?.projects[String(row.id)] ?? EMPTY_FINANCIAL
            return <tr key={row.id} className={selectedProjectId === row.id ? 'mp-row-selected' : ''}>
              <td className="mp-code">{row.project_code}</td>
              <td><strong>{client?.client_name ?? 'Management Client'}</strong><small>{row.source_person_name}</small></td>
              <td><strong>{row.project_name}</strong><small>PM: {row.project_manager_name || 'Awaiting assignment'}</small></td>
              <td><span className="mp-department">{row.department_label}</span></td>
              {activeTab === 'payments' || activeTab === 'invoices' ? <><td>{money(financial.invoiced_inr)}</td><td>{money(financial.received_inr)}</td><td>{money(financial.outstanding_inr)}</td></> : <><td className="mp-project-value-visible">  {projectMoney(row.project_value, row.currency)}</td><td><span className="mp-status">{stageTracking?.operational_status ?? managementStatusLabel(status, row.source_approved)}</span>{stageTracking && <small>ERP: {managementStatusLabel(status, row.source_approved)}</small>}</td><td><div className="mp-progress-label"><div className="mp-progress"><span className={`mp-v8-${managementProgressTone(progress)}`} style={{ width: `${progress}%` }}/></div>{stageTracking ? `${progress.toFixed(0)}%` : '—'}</div></td></>}
              <td><button type="button" className="mp-icon-button" title="View project details" aria-label={`View ${row.project_code}`} onClick={() => openDetails(row, activeTab === 'payments' || activeTab === 'invoices' ? 'billing' : activeTab === 'tracking' ? 'workflow' : 'overview')}><Eye size={17}/></button><button type="button" className="mp-icon-button" title="Open invoice and payments" aria-label={`Open invoices for ${row.project_code}`} onClick={() => openDetails(row, 'billing')}><FileText size={17}/></button></td>
            </tr>
          })}
        </tbody></table>}
      </div>
      {(activeTab === 'projects' || activeTab === 'clients') && <nav aria-label={`${paginationIsClients ? 'Clients' : 'Projects'} pagination`} className="mp-finance-pagination" style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 12, paddingTop: 12 }}>
        <span aria-live="polite">Showing {paginationFirst}–{paginationLast} of {paginationCount} {paginationIsClients ? 'clients' : 'projects'}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button type="button" className="mp-button mp-button-muted" disabled={paginationPage <= 1} onClick={() => paginationIsClients ? setClientPage(page => Math.max(1, page - 1)) : setProjectPage(page => Math.max(1, page - 1))}>Previous</button>
          <span style={{ whiteSpace: 'nowrap' }}>Page {paginationPage} of {paginationPages}</span>
          <button type="button" className="mp-button mp-button-muted" disabled={paginationPage >= paginationPages} onClick={() => paginationIsClients ? setClientPage(page => Math.min(clientPageCount, page + 1)) : setProjectPage(page => Math.min(projectPageCount, page + 1))}>Next</button>
        </div>
      </nav>}
      {activeTab === 'clients' && filteredClients.length === 0 && <div className="mp-empty">No management clients match these filters. Vinod Sir and Chethan Sir register clients from their existing Client Register.</div>}
      {activeTab !== 'clients' && filteredProjects.length === 0 && <div className="mp-empty">No management projects match these filters. Select an active management client to create one.</div>}
      {activeTab === 'invoices' && filteredProjects.length > 0 && !filteredProjects.some(row => (summary?.projects[String(row.id)]?.invoice_count ?? 0) > 0 || INVOICE_STATES.has((lifecycleById.get(row.id)?.workflow_status ?? row.workflow_status).toUpperCase())) && <div className="mp-empty">No management project invoices yet. Invoicing becomes available once a project reaches Ready For Billing.</div>}
    </section>

    </>}

    {selectedProject && <section className="mp-panel mp-project-detail" aria-label="Selected management project">
      <div className="mp-detail-heading"><div><span className="mp-eyebrow">MANAGEMENT PROJECT · {selectedProject.source_person_name}</span><h2>{selectedProject.project_code} — {selectedProject.project_name}</h2><p>{clientById.get(selectedProject.management_client_id)?.client_name} · {selectedProject.department_label} · {managementStatusLabel(billingStatus, Boolean(selectedProject?.source_approved))}</p></div><button type="button" className="mp-button mp-button-muted" onClick={() => setSelectedProjectId(null)}><X size={15}/> Close</button></div>
      <div className="mp-detail-tabs"><button className={detailTab === 'overview' ? 'active' : ''} type="button" onClick={() => setDetailTab('overview')}>Overview</button><button className={detailTab === 'workflow' ? 'active' : ''} type="button" onClick={() => setDetailTab('workflow')}>Workflow & Tracking</button><button className={detailTab === 'billing' ? 'active' : ''} type="button" onClick={() => setDetailTab('billing')}>Invoices & Payments</button></div>
      {detailTab === 'overview' && <div className="mp-detail-grid">
        <div className="mp-detail-card"><h3>Project Information</h3><dl><dt>Project Code</dt><dd>{selectedProject.project_code}</dd><dt>Client</dt><dd>{clientById.get(selectedProject.management_client_id)?.client_name ?? '—'}</dd><dt>Source</dt><dd>{selectedProject.source_person_name}</dd><dt>Department</dt><dd>{selectedProject.department_label}</dd><dt>Project Manager</dt><dd>{selectedProject.project_manager_name || 'Not assigned'}</dd><dt>Project Value</dt><dd>{projectMoney(selectedProject.project_value, selectedProject.currency)}</dd><dt>Start Date</dt><dd>{shortDate(selectedProject.start_date)}</dd><dt>Expected Delivery</dt><dd>{shortDate(selectedProject.end_date)}</dd></dl></div>
        <div className="mp-detail-card"><h3>Production & Quality Progress</h3>
          {selectedTracking ? <><div className="mp-large-progress"><strong>{selectedTracking.work_units ? `${selectedTracking.overall_percent.toFixed(0)}%` : '—'}</strong><div className="mp-progress"><span className={`mp-v8-${managementProgressTone(selectedTracking.overall_percent)}`} style={{ width: `${Math.min(100, Math.max(0, selectedTracking.overall_percent))}%` }}/></div></div><p><strong>{selectedTracking.operational_status}</strong></p><StageTrackingBars tracking={selectedTracking} compact/><p>{selectedTracking.work_units} tracked work units · {selectedTracking.active_files} active files{selectedTracking.rework_count > 0 ? ` · ${selectedTracking.rework_count} rework flags` : ''}</p></> : <p>{trackingError ? 'Tracking temporarily unavailable' : 'Loading file-level tracking…'}</p>}
          <p>Administrative ERP status: <strong>{managementStatusLabel(billingStatus, Boolean(selectedProject?.source_approved))}</strong></p>
          {trackingError && <p className="mp-tracking-error" role="alert">Tracking refresh failed. Showing last successful data, if available.</p>}
          {trackingRefreshedAt && <p className="mp-tracking-refreshed">Last checked: {trackingRefreshedAt}</p>}
          <button type="button" className="mp-button mp-button-muted" onClick={() => setDetailTab('workflow')}>View Tracking <ChevronRight size={15}/></button></div>
        <div className="mp-detail-card"><h3>Billing Summary</h3><dl><dt>Invoice Records</dt><dd>{selectedFinancial.invoice_count}</dd><dt>Total Invoiced (INR)</dt><dd>{money(selectedFinancial.invoiced_inr)}</dd><dt>Received (INR)</dt><dd>{money(selectedFinancial.received_inr)}</dd><dt>Outstanding (INR)</dt><dd>{money(selectedFinancial.outstanding_inr)}</dd></dl><button type="button" className="mp-button mp-button-primary" onClick={() => setDetailTab('billing')}><FileText size={15}/> {canOpenInvoices ? 'Open Invoice Generator' : 'View Billing Status'}</button></div>
      </div>}
      {detailTab === 'workflow' && <div className="mp-tracking-detail"><div className="mp-tracking-header"><h3>Project Workflow & Live Tracking</h3><span>Administrative status: {managementStatusLabel(billingStatus, Boolean(selectedProject?.source_approved))}</span></div>
        {selectedTracking ? <><p className="mp-tracking-current">Operational status: <strong>{selectedTracking.operational_status}</strong> · Overall stage completion: <strong>{selectedTracking.work_units ? `${selectedTracking.overall_percent.toFixed(1)}%` : 'Not allocated'}</strong></p><StageTrackingBars tracking={selectedTracking}/></> : <p className="mp-tracking-note">{trackingError ? 'Tracking temporarily unavailable.' : 'Loading tracking…'}</p>}
        {detailError && <p className="mp-tracking-error" role="alert">File tracking refresh failed. Showing last successful details, if available.</p>}
        {trackingDetail ? <FileTrackingTable detail={trackingDetail}/> : <p className="mp-tracking-note">Loading file-wise status…</p>}
        <h3 className="mp-tracking-milestones">Administrative workflow</h3><div className="mp-workflow-steps">{WORKFLOW_STEPS.map(({ label, sub, icon: Icon }, index) => <div className={index === currentWorkflowStep(billingStatus) ? 'mp-workflow-step current' : 'mp-workflow-step'} key={label}><div className="mp-workflow-icon"><Icon size={19}/></div><strong>{label}</strong><small>{sub}</small></div>)}</div><p className="mp-tracking-note">Operational stage percentages are calculated from active file completion records, with legacy area-level fallback. Rework remains visible. Administrative status and billing readiness remain separate; department, QC/QA and delivery actions stay in their original ERP modules.</p></div>}
      {detailTab === 'billing' && <div className="mp-billing-container">{canOpenInvoices ? <FinanceBillingPage key={selectedProject.id} embeddedProjectId={selectedProject.id}/> : <div className="mp-billing-locked"><ShieldCheck size={27}/><h3>Invoice generation is not available yet</h3><p>Management projects require approval from their original Management source after Delivery, followed by <strong>Ready For Billing</strong>. Finance can then use the existing invoice, PDF, signing and payment controls.</p><p>Current status: <strong>{managementStatusLabel(billingStatus, Boolean(selectedProject?.source_approved))}</strong></p></div>}</div>}
      {!selectedProject.project_manager_id && ['finance_approved', 'pm_assigned'].includes(selectedProject.workflow_status.toLowerCase()) && <div className="mp-assign-box"><div><strong>Department Project Manager not assigned</strong><small>Select a manager from the existing BD department mapping.</small></div><select aria-label={`Project Manager for ${selectedProject.project_code}`} value={pmChoice[selectedProject.id] || ''} onChange={e => setPmChoice(prev => ({ ...prev, [selectedProject.id]: e.target.value }))}><option value="">Select Project Manager</option>{(options.project_managers_by_department[selectedProject.department_code] ?? []).map(pm => <option key={pm.id} value={pm.id}>{pm.full_name}</option>)}</select><button className="mp-button mp-button-primary" type="button" disabled={busy || !pmChoice[selectedProject.id]} onClick={() => void assignPm(selectedProject)}>Assign Manager <ArrowRight size={15}/></button></div>}
    </section>}

    <section className="mp-panel mp-workflow-panel">
      <div className="mp-panel-heading"><div><h2>Management Project Workflow</h2><p>End-to-end flow from Finance project creation to invoice settlement and closure</p></div><span><FileCheck2 size={17}/> Existing ERP lifecycle</span></div>
      <div className="mp-workflow-steps">{WORKFLOW_STEPS.map(({ label, sub, icon: Icon }, index) => <div className="mp-workflow-step" key={label}><div className="mp-workflow-icon"><Icon size={20}/></div><strong>{label}</strong><small>{sub}</small>{index < WORKFLOW_STEPS.length - 1 && <ArrowRight className="mp-workflow-arrow" size={15}/>}</div>)}</div>
      <p className="mp-workflow-disclaimer">Management projects require original-source approval after Delivery before the existing Finance Billing engine can draft an invoice. Finance owns management-project creation; BD cannot view these management-sourced records.</p>
    </section>

    {showCreate && selectedClient && <div className="mp-overlay" role="presentation"><aside className="mp-create-dialog" role="dialog" aria-modal="true" aria-label="Create Management Project">
      <div className="mp-dialog-heading"><div><span className="mp-eyebrow">FINANCE DEPARTMENT</span><h2>Create Management Project</h2><p>Choose a management client, assign department, then save.</p></div><button type="button" className="mp-icon-button" aria-label="Close project form" disabled={busy} onClick={() => setShowCreate(false)}><X size={19}/></button></div>
      <form className="mp-dialog-body" onSubmit={event => void createProject(event)}>
        <div className="mp-form-section"><h3>1. Client Information</h3><label className="mp-field"><span>Management Client *</span><select value={selectedClientId ?? ''} disabled={selectedRequestId !== null} onChange={e => { const id = Number(e.target.value); const chosen = data.clients.find(c => c.id === id); setSelectedClientId(id); if (chosen) setProject(prev => ({ ...prev, scope_text: chosen.work_description || prev.scope_text })) }}>{data.clients.filter(c => c.is_active).map(c => <option key={c.id} value={c.id}>{c.client_name}</option>)}</select></label><div className="mp-readonly-pair"><div><span>Client Source</span><strong>{selectedClient.source_person_name}</strong></div><div><span>Client Code</span><strong>{selectedClient.client_code}</strong></div></div></div>
        <div className="mp-form-section"><h3>2. Project Details</h3><div className="mp-form-grid"><label className="mp-field"><span>Project Code *</span><input required minLength={2} value={project.project_code} onChange={e => setProject({ ...project, project_code: e.target.value.toUpperCase() })} placeholder="MGT-PRJ-001"/></label><label className="mp-field"><span>Project Name *</span><input required minLength={2} value={project.project_name} onChange={e => setProject({ ...project, project_name: e.target.value })} placeholder="Enter project name"/></label><label className="mp-field mp-full"><span>Project Description / Scope of Work *</span><textarea required minLength={2} value={project.scope_text} onChange={e => setProject({ ...project, scope_text: e.target.value })} placeholder="Describe deliverables"/></label><label className="mp-field"><span>Start Date *</span><input required type="date" value={project.start_date} onChange={e => setProject({ ...project, start_date: e.target.value })}/></label><label className="mp-field"><span>Expected Delivery *</span><input required type="date" min={project.start_date || undefined} value={project.end_date} onChange={e => setProject({ ...project, end_date: e.target.value })}/></label><label className="mp-field mp-full"><span>Finance Notes</span><textarea value={project.description} onChange={e => setProject({ ...project, description: e.target.value })}/></label></div></div>
        <div className="mp-form-section"><h3>3. Department Assignment · Same as BD</h3><div className="mp-form-grid"><label className="mp-field"><span>Assign Department *</span><select required value={project.performing_department_code} onChange={e => setProject({ ...project, performing_department_code: e.target.value, project_manager_id: '' })}><option value="">Select Department</option>{options.departments.map(dept => <option key={dept.code} value={dept.code}>{dept.label}</option>)}</select></label><label className="mp-field"><span>Department Project Manager</span><select value={project.project_manager_id} onChange={e => setProject({ ...project, project_manager_id: e.target.value })} disabled={!project.performing_department_code}><option value="">Assign after creation</option>{pmOptions.map(pm => <option key={pm.id} value={pm.id}>{pm.employee_id ? `${pm.employee_id} · ` : ''}{pm.full_name}</option>)}</select></label><label className="mp-field"><span>Priority</span><select value={project.priority} onChange={e => setProject({ ...project, priority: e.target.value })}><option value="low">Low</option><option value="medium">Normal</option><option value="high">High</option><option value="urgent">Urgent</option></select></label><label className="mp-field"><span>Planned Quantity</span><input type="number" min="0" step="0.001" value={project.quantity} onChange={e => setProject({ ...project, quantity: e.target.value })}/></label><label className="mp-field"><span>Quantity Unit</span><input value={project.quantity_unit} onChange={e => setProject({ ...project, quantity_unit: e.target.value })}/></label></div><p className="mp-form-help">The existing BD department/PM assignment and notification mechanism is reused. Finance approves the project on creation.</p></div>
        <div className="mp-form-section"><h3>4. Commercial Information</h3><div className="mp-commercial"><CommercialDetailsSection form={commercial} onChange={setCommercial} currencies={currencies} disabled={busy}/></div></div>
        <div className="mp-form-section"><h3>5. Invoice Generation</h3><p className="mp-form-help"><ShieldCheck size={15}/> The existing Finance invoice generator, A4 PDF, themes, signature and payment ledger will open inside this page after the project reaches Ready For Billing. No invoice is issued during project creation.</p></div>
        <div className="mp-dialog-actions"><button type="button" className="mp-button mp-button-muted" disabled={busy} onClick={() => setShowCreate(false)}>Cancel</button><button type="submit" className="mp-button mp-button-primary" disabled={busy}>{busy ? 'Creating Project…' : 'Create & Assign Project'} <ChevronRight size={17}/></button></div>
      </form>
    </aside></div>}
  </div>
}
