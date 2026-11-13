import './naksha-management-tracking-light-v4.css';
import { Activity, ArrowLeft, Building2, CheckCircle2, ChevronDown, ChevronRight, Eye, Pencil, Plus, RefreshCw, Search, X } from 'lucide-react'
import { Fragment, type FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { DashboardHeader } from '../../components/DashboardHeader'
import { apiFetch } from '../../lib/api'
import '../operations/operations.css'
import './management-project-tracking.css'
import { CountrySelect } from './CountrySelect'
type Client = {
  id: number
  client_code: string
  client_name: string
  client_email: string | null
  organization_email: string | null
  address: string | null
  country: string
  gst_number: string | null
  contact_person_name: string
  contact_person_email: string | null
  contact_person_phone: string | null
  work_description: string | null
  source_person_name: string
  is_active: boolean
  created_at: string
  updated_at: string
  can_request_project: boolean
}

type ClientForm = {
  client_code: string
  client_name: string
  client_email: string
  organization_email: string
  address: string
  country: string
  gst_number: string
  contact_person_name: string
  contact_person_email: string
  contact_person_phone: string
  work_description: string
}

function getTaxField(country: string) {
  const labels: Record<string, { label: string; placeholder: string }> = {
    India: { label: 'GSTIN', placeholder: 'Enter GSTIN' },
    'United Arab Emirates': { label: 'TRN / VAT Number', placeholder: 'Enter TRN' },
    'United Kingdom': { label: 'VAT Registration Number', placeholder: 'Enter VAT number' },
    'United States': { label: 'EIN / Tax ID', placeholder: 'Enter applicable tax ID' },
    Australia: { label: 'ABN', placeholder: 'Enter ABN' },
    Canada: { label: 'GST/HST Registration Number', placeholder: 'Enter registration number' },
    Germany: { label: 'VAT ID', placeholder: 'Enter VAT ID' },
    France: { label: 'VAT Number', placeholder: 'Enter VAT number' },
    Singapore: { label: 'GST Registration Number', placeholder: 'Enter registration number' },
    'Saudi Arabia': { label: 'VAT Number', placeholder: 'Enter VAT number' },
    Qatar: { label: 'Tax Registration Number', placeholder: 'Enter tax number' },
    Japan: { label: 'Corporate / Tax Number', placeholder: 'Enter applicable tax number' },
  }

  return labels[country] ?? {
    label: 'Tax Registration Number',
    placeholder: 'Enter applicable tax registration number',
  }
}


const emptyForm: ClientForm = {
  client_code: '', client_name: '', client_email: '', organization_email: '',
  address: '', country: 'India', gst_number: '', contact_person_name: '',
  contact_person_email: '', contact_person_phone: '', work_description: '',
}

type AdditionalProjectRequest = {
  id: number; management_client_id: number; client_code: string; client_name: string
  source_person_name: string; project_name: string; scope_text: string
  expected_start_date: string | null; remarks: string | null
  project_type: 'regular' | 'pilot'; pilot_payment_type: 'free' | 'paid' | null
  status: 'PENDING' | 'CREATED'; created_project_code: string | null; created_at: string
}
const endpoint = '/management/client-register'
const requestEndpoint = `${endpoint}/additional-project-requests`
type StageKey = 'production' | 'qc' | 'qa' | 'delivery'
type Stage = { completed: number; total: number; percent: number; in_progress: number }
type TrackingSummary = {
  overall_percent: number; operational_status: string; work_units: number
  active_files: number; legacy_areas: number; rework_count: number
  last_activity_at: string | null; stages: Record<StageKey, Stage>
}
type ManagementProject = {
  id: number; management_client_id: number; project_code: string; project_name: string
  source_person_name: string; department_label: string; workflow_status: string
  project_manager_name: string | null; start_date: string; end_date: string
  project_value: number | null; currency: string; tracking: TrackingSummary
  can_approve: boolean; source_approved: boolean
  project_type: 'regular' | 'pilot'; pilot_payment_type: 'free' | 'paid' | null
}
type ClientTracking = {
  project_count: number; active_projects: number; completed_projects: number
  overall_percent: number; work_units: number
}
type TrackingRegister = {
  as_of: string; projects: ManagementProject[]; clients: Record<string, ClientTracking>
}
type TrackingFile = {
  work_package_item_id: number | null; package_code: string; item_number: string
  item_name: string | null; is_active: boolean; tracking_basis: 'file_activity' | 'legacy_area'
  production: string; qc: string; qa: string; delivery: string
  production_completed_at: string | null; qc_completed_at: string | null
  qa_completed_at: string | null; delivered_at: string | null
  production_employee: string | null; qc_employee: string | null; qa_employee: string | null
}
type TrackingDetail = {
  project_id: number; as_of: string; project: Omit<ManagementProject, 'tracking'>
  summary: TrackingSummary; files: TrackingFile[]
}
const stages: StageKey[] = ['production', 'qc', 'qa', 'delivery']
const stageLabels: Record<StageKey, string> = { production: 'Production', qc: 'QC', qa: 'QA', delivery: 'Delivery' }
const trackingEndpoint = `${endpoint}/project-tracking`
const readable = (value: string) => (value || 'Not started').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
const stageTone = (value: string) => {
  const normalized = (value || '').toLowerCase()
  if (['completed', 'passed', 'approved', 'delivered'].includes(normalized)) return 'complete'
  if (normalized.includes('rework') || ['rejected', 'failed'].includes(normalized)) return 'rework'
  if (['in_progress', 'started'].includes(normalized)) return 'active'
  return 'pending'
}
const percentText = (value: number) => `${Number.isFinite(value) ? Math.round(value) : 0}%`

function ProgressMeter({ value, label }: { value: number; label: string }) {
  return <div className="mct-progress" role="progressbar" aria-label={label} aria-valuenow={Math.min(100, Math.max(0, value))} aria-valuemin={0} aria-valuemax={100}>
    <span style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
  </div>
}

function ManagementTrackingDialog({ project, client, onClose }: {
  project: ManagementProject; client: Client | undefined; onClose: () => void
}) {
  const [detail, setDetail] = useState<TrackingDetail | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    let busy = false
    async function refresh() {
      if (!active || busy || document.hidden) return
      busy = true
      try {
        const result = await apiFetch<TrackingDetail>(`${trackingEndpoint}/${project.id}`)
        if (active) { setDetail(result); setError('') }
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : 'Tracking is temporarily unavailable')
      } finally { busy = false }
    }
    function onFocus() { void refresh() }
    function onKey(event: KeyboardEvent) { if (event.key === 'Escape') onClose() }
    void refresh()
    const timer = window.setInterval(() => void refresh(), 5000)
    window.addEventListener('focus', onFocus)
    window.addEventListener('keydown', onKey)
    return () => {
      active = false
      window.clearInterval(timer)
      window.removeEventListener('focus', onFocus)
      window.removeEventListener('keydown', onKey)
    }
  }, [project.id, onClose])
  // Keep the background ERP page from scrolling while the tracking dialog is open.
  useEffect(() => {
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = previousOverflow }
  }, [])
  const summary = detail?.summary ?? project.tracking
  const projectInfo = detail?.project ?? project
  const files = detail?.files ?? []
  const asOf = detail?.as_of
  return createPortal(<div className="mct-modal-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
    <section className="mct-modal" role="dialog" aria-modal="true" aria-label={`Tracking for project ${project.project_code}`} data-naksha-management-live-v4="true">
      <header className="mct-modal-header">
        <div><span className="mct-eyebrow">MANAGEMENT PROJECT · {project.source_person_name}</span>
          <h2>{project.project_code} — {project.project_name}</h2>
          <p>{client?.client_name ?? 'Management client'} · {project.department_label} · Read-only live tracking</p>
        </div>
        <button className="mct-close" type="button" onClick={onClose}><X size={16} /> Close</button>
      </header>
      {error && <div className="mct-warning" role="alert">Unable to refresh tracking: {error}. {detail ? 'Showing last successful data.' : 'Showing the latest project summary.'}</div>}
      <div className="mct-modal-metrics">
        <div className="mct-dark-card">
          <h3>Overall Stage Completion</h3>
          <strong className="mct-big-percent">{percentText(summary.overall_percent)}</strong>
          <div className={'mct-management-progress-tone mct-v8-' + managementProgressTone(summary.overall_percent)}><ProgressMeter value={summary.overall_percent} label="Overall project stage completion" /></div>
          <small>{summary.operational_status}</small>
        </div>
        <div className="mct-dark-card mct-stages-card"><h3>Stage Progress</h3>
          <div className="mct-stages-grid">{stages.map(stage => {
            const value = summary.stages[stage]
            return <div className="mct-stage" key={stage}>
              <strong>{stageLabels[stage]}</strong>
              <span>{percentText(value.percent)} ({value.completed}/{value.total})</span>
              <div className={'mct-management-progress-tone mct-v8-' + managementProgressTone(value.percent)}><ProgressMeter value={value.percent} label={`${stageLabels[stage]} completion`} /></div>
            </div>
          })}</div>
        </div>
        <div className="mct-dark-card mct-project-details"><h3>Project Details</h3>
          <dl><dt>Client Source</dt><dd>{project.source_person_name}</dd>
            <dt>Project Manager</dt><dd>{projectInfo.project_manager_name || 'Not assigned'}</dd>
            <dt>Administrative Status</dt><dd>{readable(projectInfo.workflow_status)}</dd>
            <dt>Active Files</dt><dd>{summary.active_files}</dd>
            <dt>Rework Items</dt><dd>{summary.rework_count}</dd>
          </dl>
        </div>
      </div>
      <div className="mct-dark-card mct-files">
        <div className="mct-files-heading"><h3>File / Segment Tracking</h3>
          <span>{detail ? `${summary.active_files} active files · ${summary.legacy_areas} legacy areas` : 'Loading file details…'}</span></div>
        {!detail && !error ? <p>Loading current employee activity…</p> : detail && files.length === 0 ?
          <p>No work packages or files have been allocated to this project yet.</p> :
          <div className="mct-file-scroll"><table><thead><tr>
            <th>File / Segment</th><th>Production</th><th>QC</th><th>QA</th><th>Delivery</th><th>Last Stage Update</th>
          </tr></thead><tbody>{files.map((file, index) => <tr key={`${file.work_package_item_id ?? 'legacy'}-${file.package_code}-${index}`} className={!file.is_active ? 'mct-inactive' : ''}>
            <td><strong>{file.item_name || file.item_number}</strong><small>{file.package_code}{file.tracking_basis === 'legacy_area' ? ' · Area tracking' : ''}{!file.is_active ? ' · Inactive' : ''}</small></td>
            {stages.map(stage => <td key={stage}>
              <span className={`mct-status ${stageTone(file[stage])}`} data-management-status={readable(file[stage])}>{readable(file[stage])}</span>
              {stage !== 'delivery' && file[`${stage}_employee` as 'production_employee' | 'qc_employee' | 'qa_employee'] &&
                <small>{file[`${stage}_employee` as 'production_employee' | 'qc_employee' | 'qa_employee']}</small>}
            </td>)}
            <td><small>{[file.delivered_at, file.qa_completed_at, file.qc_completed_at, file.production_completed_at]
              .filter(Boolean).slice(0, 1).map(value => formatDateTime(value!)).join('') || '—'}</small></td>
          </tr>)}</tbody></table></div>}
      </div>
      <div className="mct-dark-card"><h3>Workflow Timeline</h3>
        <div className="mct-timeline">{stages.map(stage => <div key={stage}>
          <span className={`mct-timeline-dot ${summary.stages[stage].percent === 100 ? 'done' : summary.stages[stage].percent > 0 ? 'partial' : ''}`} />
          <strong>{stageLabels[stage]}</strong>
          <small>{summary.stages[stage].percent === 100 ? 'Completed' : summary.stages[stage].percent > 0 ? `In progress (${percentText(summary.stages[stage].percent)})` : 'Pending'}</small>
        </div>)}</div>
      </div>
      <footer className="mct-modal-footer"><span>Read-only · Refreshes every 5 seconds while open{asOf ? ` · Updated ${formatDateTime(asOf)}` : ''}</span>
        <button className="mct-close" type="button" onClick={onClose}>Close</button></footer>
    </section>
  </div>, document.body)
}

function formatDateTime(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('en-IN')
}

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleDateString()
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

export function ManagementClientRegisterPage() {
  const [clients, setClients] = useState<Client[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [query, setQuery] = useState('')
  const [ownerFilter, setOwnerFilter] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [form, setForm] = useState<ClientForm>(emptyForm)
  const [tracking, setTracking] = useState<TrackingRegister | null>(null)
  const [trackingError, setTrackingError] = useState('')
  const [additionalRequests, setAdditionalRequests] = useState<AdditionalProjectRequest[]>([])
  const [requestingClientId, setRequestingClientId] = useState<number | null>(null)
  const [requestProjectName, setRequestProjectName] = useState('')
  const [requestProjectType, setRequestProjectType] = useState<'regular' | 'pilot'>('regular')
  const [requestPilotPaymentType, setRequestPilotPaymentType] = useState<'free' | 'paid'>('free')
  const [requestScope, setRequestScope] = useState('')
  const [requestStart, setRequestStart] = useState('')
  const [requestRemarks, setRequestRemarks] = useState('')
  const [requestBusy, setRequestBusy] = useState(false)
  const [requestError, setRequestError] = useState('')
  const [trackingView, setTrackingView] = useState<'clients' | 'projects'>('clients')
  const [projectTypeFilter, setProjectTypeFilter] = useState('')
  const [expandedClientId, setExpandedClientId] = useState<number | null>(null)
  const [trackingProjectId, setTrackingProjectId] = useState<number | null>(null)
  // NAKSHA_MGMT_CLIENTS_PAGINATION_5_V2: only the Management users' Registered Clients table.
  const [managementClientPage, setManagementClientPage] = useState(1)
  // Reset after search/source filter changes; keep search across ALL clients.
  useEffect(() => { setManagementClientPage(1) }, [query, ownerFilter])

  async function load() {
    setLoading(true)
    setError('')
    try {
      setClients(await apiFetch<Client[]>(endpoint))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load management clients')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])
  // New-project requests are separate from client and operational tracking state.
  useEffect(() => {
    let alive = true
    const refresh = () => {
      if (document.visibilityState === 'hidden') return
      void apiFetch<AdditionalProjectRequest[]>(requestEndpoint)
        .then(rows => { if (alive) setAdditionalRequests(rows) })
        .catch(() => undefined)
    }
    refresh()
    const interval = window.setInterval(refresh, 5000)
    return () => { alive = false; window.clearInterval(interval) }
  }, [])

  function openAdditionalRequest(client: Client) {
    if (!client.can_request_project) return
    setRequestingClientId(client.id)
    setRequestProjectName('')
    setRequestProjectType('regular')
    setRequestPilotPaymentType('free')
    setRequestScope('')
    setRequestStart('')
    setRequestRemarks('')
    setRequestError('')
  }

  async function submitAdditionalRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (requestingClientId === null || requestBusy) return
    setRequestBusy(true); setRequestError('')
    try {
      await apiFetch(requestEndpoint, { method: 'POST', body: JSON.stringify({
        management_client_id: requestingClientId,
        project_name: requestProjectName.trim(), scope_text: requestScope.trim(),
        project_type: requestProjectType,
        pilot_payment_type: requestProjectType === 'pilot' ? requestPilotPaymentType : null,
        expected_start_date: requestStart || null, remarks: requestRemarks.trim() || null,
      }) })
      setAdditionalRequests(await apiFetch<AdditionalProjectRequest[]>(requestEndpoint))
      setRequestingClientId(null)
      setNotice('Project request sent to Finance. The status will change to Project Created when Finance creates and links the new project.')
    } catch (err) {
      setRequestError(err instanceof Error ? err.message : 'Unable to request a project')
    } finally { setRequestBusy(false) }
  }
  useEffect(() => {
    let active = true
    let busy = false
    async function refreshTracking() {
      if (!active || busy || document.hidden) return
      busy = true
      try {
        const result = await apiFetch<TrackingRegister>(trackingEndpoint)
        if (active) { setTracking(result); setTrackingError('') }
      } catch (err) {
        if (active) setTrackingError(err instanceof Error ? err.message : 'Unable to load project tracking')
      } finally { busy = false }
    }
    function onFocus() { void refreshTracking() }
    void refreshTracking()
    const timer = window.setInterval(() => void refreshTracking(), 5000)
    window.addEventListener('focus', onFocus)
    return () => { active = false; window.clearInterval(timer); window.removeEventListener('focus', onFocus) }
  }, [])

  const owners = useMemo(() => [...new Set(clients.map(row => row.source_person_name))].sort(), [clients])
  const filtered = useMemo(() => clients.filter(row => {
    const term = query.trim().toLowerCase()
    const matchesText = !term || [row.client_code, row.client_name, row.contact_person_name, row.client_email,
      row.organization_email, row.work_description, row.source_person_name].some(value => (value || '').toLowerCase().includes(term))
    return matchesText && (!ownerFilter || row.source_person_name === ownerFilter)
  }), [clients, ownerFilter, query])
  const selected = clients.find(row => row.id === selectedId) ?? null
  const projects = tracking?.projects ?? []
  const selectedTrackingProject = projects.find(row => row.id === trackingProjectId) ?? null
  const closeTracking = useCallback(() => setTrackingProjectId(null), [])
  const filteredProjects = projects.filter(project => {
    const client = clients.find(item => item.id === project.management_client_id)
    const term = query.trim().toLowerCase()
    return (!projectTypeFilter || project.project_type === projectTypeFilter) &&
      (!ownerFilter || project.source_person_name === ownerFilter) && (!term ||
      [project.project_code, project.project_name, project.department_label, project.source_person_name,
        client?.client_name, client?.client_code].some(value => (value || '').toLowerCase().includes(term)))
  })
  const activeProjects = Object.values(tracking?.clients ?? {}).reduce((sum, client) => sum + client.active_projects, 0)
  const completedProjects = Object.values(tracking?.clients ?? {}).reduce((sum, client) => sum + client.completed_projects, 0)

  async function approveProject(project: ManagementProject) {
    if (busy || !project.can_approve) return
    if (!window.confirm(`Approve ${project.project_code} — ${project.project_name} for Finance billing?`)) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await apiFetch(`${endpoint}/projects/${project.id}/approve`, { method: 'POST' })
      setNotice(`${project.project_code} approved by its original Management source. Finance may now create an invoice.`)
      try {
        setTracking(await apiFetch<TrackingRegister>(trackingEndpoint))
      } catch {
        setTrackingError('Approval saved, but tracking could not refresh. Reopen this page to see the latest status.')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to approve Management project')
    } finally {
      setBusy(false)
    }
  }

  function updateField<K extends keyof ClientForm>(field: K, value: ClientForm[K]) {
    setForm(previous => ({ ...previous, [field]: value }))
  }

  function openCreate() {
    setForm({ ...emptyForm })
    setEditingId(null)
    setShowForm(true)
    setSelectedId(null)
    setError('')
    setNotice('')
  }

  function openEdit(client: Client) {
    setForm({
      client_code: client.client_code, client_name: client.client_name,
      client_email: client.client_email || '', organization_email: client.organization_email || '',
      address: client.address || '', country: client.country || 'India', gst_number: client.gst_number || '',
      contact_person_name: client.contact_person_name, contact_person_email: client.contact_person_email || '',
      contact_person_phone: client.contact_person_phone || '', work_description: client.work_description || '',
    })
    setEditingId(client.id)
    setSelectedId(client.id)
    setShowForm(true)
    setError('')
    setNotice('')
  }

  async function saveClient(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const payload = {
        ...form,
        client_code: form.client_code.trim().toUpperCase(),
        gst_number: form.gst_number.trim().toUpperCase(),
      }
      const saved = await apiFetch<Client>(editingId === null ? endpoint : `${endpoint}/${editingId}`, {
        method: editingId === null ? 'POST' : 'PUT', body: JSON.stringify(payload),
      })
      setShowForm(false)
      setEditingId(null)
      setSelectedId(saved.id)
      setNotice(`Client ${saved.client_code} ${editingId === null ? 'registered' : 'updated'} successfully.`)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to save client')
    } finally {
      setBusy(false)
    }
  }

  const managementClientPageSize = 5
  const managementClientTotal = (filtered).length
  const managementClientPageCount = Math.max(1, Math.ceil(managementClientTotal / managementClientPageSize))
  const managementClientSafePage = Math.min(managementClientPage, managementClientPageCount)
  const managementClientFirst = managementClientTotal === 0 ? 0 : (managementClientSafePage - 1) * managementClientPageSize + 1
  const managementClientLast = Math.min(managementClientSafePage * managementClientPageSize, managementClientTotal)
  return <div className="operations-page">
    <DashboardHeader
      eyebrow="MANAGEMENT · CLIENT INTAKE"
      title="Client Register"
      description="Register Management-direct clients and record their initial requirements. This page does not create projects or assign departments."
      details={<>
        <div><span>Management Clients</span><strong>{clients.length}</strong></div>
        <div><span>Client Sources</span><strong>{owners.length}</strong></div>
        <div><span>Work Notes Recorded</span><strong>{clients.filter(row => Boolean(row.work_description)).length}</strong></div>
        <div><span>Active Projects</span><strong>{tracking ? activeProjects : '—'}</strong></div>
        <div><span>Completed Projects</span><strong>{tracking ? completedProjects : '—'}</strong></div>
      </>}
      actions={<>
        <button type="button" className="operations-button" onClick={openCreate}><Plus size={16} /> Register Client</button>
        <button type="button" className="operations-button secondary" disabled={loading} onClick={() => void load()}><RefreshCw size={16} /> Refresh</button>
      </>}
    />

    {notice && <div className="operations-alert success" role="status">{notice}</div>}
    {error && <div className="operations-alert error" role="alert">{error}</div>}

    {showForm && <section className="operations-panel">
      <header><div><span className="operations-kicker">{editingId === null ? 'NEW CLIENT' : 'EDIT CLIENT'}</span>
        <h2>{editingId === null ? 'Client Registration' : 'Update Client Details'}</h2>
        <p>Use the same core client details as BD. This registration does not create a project or assign a department.</p>
      </div></header>
      <form className="operations-form-grid" onSubmit={event => void saveClient(event)}>
        <label className="operations-field"><span>Client ID / Code *</span><input required maxLength={32} value={form.client_code} onChange={event => updateField('client_code', event.target.value.toUpperCase())} placeholder="CLIENT-001" /></label>
        <label className="operations-field"><span>Client Organization Name *</span><input required maxLength={255} value={form.client_name} onChange={event => updateField('client_name', event.target.value)} /></label>
        <label className="operations-field"><span>Client Email ID</span><input type="email" value={form.client_email} onChange={event => updateField('client_email', event.target.value)} /></label>
        <label className="operations-field"><span>Organization Email ID</span><input type="email" value={form.organization_email} onChange={event => updateField('organization_email',event.target.value)} /></label>       
<CountrySelect
  value={form.country || 'India'}
  onChange={(country) =>
    setForm((prev) => ({
      ...prev,
      country,
    }))
  }
/>
       
<label className="operations-field">
  <span>{getTaxField(form.country).label}</span>
  <input
    maxLength={32}
    placeholder={getTaxField(form.country).placeholder}
    value={form.gst_number}
    onChange={event =>
      updateField('gst_number', event.target.value.toUpperCase())
    }
  />
</label>

        <label className="operations-field operations-span-2"><span>Client Address</span><textarea rows={2} value={form.address} onChange={event => updateField('address', event.target.value)} /></label>
        <label className="operations-field"><span>Contact Person Name *</span><input required value={form.contact_person_name} onChange={event => updateField('contact_person_name', event.target.value)} /></label>
        <label className="operations-field"><span>Contact Person Email ID</span><input type="email" value={form.contact_person_email} onChange={event => updateField('contact_person_email', event.target.value)} /></label>
        <label className="operations-field"><span>Contact Person Phone</span><input type="tel" maxLength={40} value={form.contact_person_phone} onChange={event => updateField('contact_person_phone', event.target.value)} /></label>
        <label className="operations-field operations-span-2"><span>Client Work / Initial Requirement</span><textarea rows={4} maxLength={5000} value={form.work_description} onChange={event => updateField('work_description', event.target.value)} placeholder="Describe the work requested by the client. Project creation is handled separately." /></label>
        <div className="operations-note operations-span-2">The client source is automatically recorded as the logged-in Management user. BD, project creation, and Finance approval workflows are not triggered.</div>
        <div className="operations-actions operations-span-2">
          <button className="operations-button" type="submit" disabled={busy}>{busy ? 'Saving…' : editingId === null ? 'Create Client' : 'Save Changes'}</button>
          <button className="operations-button secondary" type="button" disabled={busy} onClick={() => setShowForm(false)}>Cancel</button>
        </div>
      </form>
    </section>}

    {requestingClientId !== null && <section className="operations-panel" aria-label="New project request for existing client">
      <header><div><span className="operations-kicker">EXISTING MANAGEMENT CLIENT</span>
        <h2>Request Another Project</h2>
        <p>Finance will create the project under the same existing client. This request does not create a project.</p>
      </div></header>
      {requestError && <div className="operations-alert error" role="alert">{requestError}</div>}
      <form className="operations-form-grid" onSubmit={event => void submitAdditionalRequest(event)}>
        <div className="operations-field"><span>Client</span><strong>{clients.find(c => c.id === requestingClientId)?.client_name || 'Existing client'} ({clients.find(c => c.id === requestingClientId)?.client_code})</strong></div>
        <label className="operations-field"><span>Project Type *</span><select value={requestProjectType} onChange={e => setRequestProjectType(e.target.value as 'regular' | 'pilot')}><option value="regular">Regular Project</option><option value="pilot">Pilot Project</option></select></label>
        {requestProjectType === 'pilot' && <label className="operations-field"><span>Pilot Financial Type *</span><select value={requestPilotPaymentType} onChange={e => setRequestPilotPaymentType(e.target.value as 'free' | 'paid')}><option value="free">Free Pilot</option><option value="paid">Paid Pilot</option></select></label>}
        <label className="operations-field"><span>Requested Project Name *</span><input required minLength={2} maxLength={255} value={requestProjectName} onChange={event => setRequestProjectName(event.target.value)} /></label>
        <label className="operations-field operations-span-2"><span>New Project Scope / Requirements *</span><textarea required minLength={2} maxLength={5000} rows={3} value={requestScope} onChange={event => setRequestScope(event.target.value)} /></label>
        <label className="operations-field"><span>Expected Start (optional)</span><input type="date" value={requestStart} onChange={event => setRequestStart(event.target.value)} /></label>
        <label className="operations-field operations-span-2"><span>Remarks (optional)</span><textarea maxLength={2000} rows={2} value={requestRemarks} onChange={event => setRequestRemarks(event.target.value)} /></label>
        <div className="operations-actions operations-span-2"><button type="submit" className="operations-button" disabled={requestBusy}>{requestBusy ? 'Sending…' : 'Send Request to Finance'}</button>
          <button type="button" className="operations-button secondary" disabled={requestBusy} onClick={() => setRequestingClientId(null)}>Cancel</button></div>
      </form>
    </section>}

    {!showForm && selected && <section className="operations-panel">
      <header><div><span className="operations-kicker">CLIENT DETAILS · {selected.client_code}</span><h2>{selected.client_name}</h2><p>Registered by {selected.source_person_name} · {formatDate(selected.created_at)}</p></div></header>
      <div className="operations-form-grid">
        <div className="operations-field"><span>Contact Person</span><strong>{selected.contact_person_name}</strong></div>
        <div className="operations-field"><span>Contact Phone</span><strong>{selected.contact_person_phone || '—'}</strong></div>
        <div className="operations-field"><span>Client Email</span><strong>{selected.client_email || '—'}</strong></div>
        <div className="operations-field"><span>Contact Email</span><strong>{selected.contact_person_email || '—'}</strong></div>
        <div className="operations-field"><span>Organization Email</span><strong>{selected.organization_email || '—'}</strong></div>
        <div className="operations-field"><span>Country</span><strong>{selected.country}</strong></div>
        <div className="operations-field"><span>GST / VAT / SUT</span><strong>{selected.gst_number || '—'}</strong></div>
        <div className="operations-field"><span>Address</span><strong>{selected.address || '—'}</strong></div>
        <div className="operations-field operations-span-2"><span>Client Work / Initial Requirement</span><p>{selected.work_description || 'No work notes recorded yet.'}</p></div>
      </div>
      {additionalRequests.filter(row => row.management_client_id === selected.id).length > 0 && <div className="operations-note" style={{ marginBottom: 12 }}>
        <strong>Additional Project Request History</strong>
        {additionalRequests.filter(row => row.management_client_id === selected.id).map(row =>
          <p key={row.id}>{row.project_name} · <span style={{ color: row.status === 'CREATED' ? '#166534' : '#9f3636' }}>{row.status === 'CREATED' ? `Project Created (${row.created_project_code || 'Linked'})` : 'Awaiting Finance'}</span></p>
        )}
      </div>}
      <div className="operations-actions">
        <button type="button" className="operations-button secondary" onClick={() => setSelectedId(null)}><ArrowLeft size={16} /> Back to Register</button>
        <button type="button" className="operations-button" onClick={() => openEdit(selected)}><Pencil size={16} /> Edit Client</button>
      </div>
    </section>}

    <section className="operations-panel">
      <header><div><span className="operations-kicker">MANAGEMENT CLIENT REGISTER</span><h2><Building2 size={19} /> Registered Clients</h2><p>Only clients registered by the two Management accounts appear here.</p></div>
        <div className="mct-view-switch" role="group" aria-label="Management client and project views">
          <button type="button" className={trackingView === 'clients' ? 'active' : ''} onClick={() => setTrackingView('clients')}><Building2 size={15} /> Client View</button>
          <button type="button" className={trackingView === 'projects' ? 'active' : ''} onClick={() => setTrackingView('projects')}><Activity size={15} /> Project Tracking</button>
        </div></header>
      <div className="operations-form-grid">
        <label className="operations-field"><span>Search Clients</span><div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Search size={16} /><input aria-label="Search management clients" value={query} onChange={event => setQuery(event.target.value)} placeholder="Client ID, company, contact, work…" /></div></label>
        <label className="operations-field"><span>Registered By</span><select value={ownerFilter} onChange={event => setOwnerFilter(event.target.value)}><option value="">Both Management Users</option>{owners.map(owner => <option key={owner} value={owner}>{owner}</option>)}</select></label>
        {trackingView === 'projects' && <label className="operations-field"><span>Project Type</span><select value={projectTypeFilter} onChange={e => setProjectTypeFilter(e.target.value)}><option value="">All Projects</option><option value="regular">Regular Projects</option><option value="pilot">Pilot Projects</option></select></label>}
      </div>
      {trackingError && <div className="mct-inline-warning" role="alert">Project tracking could not refresh: {trackingError}. Client registration remains available.</div>}
      {trackingView === 'clients' ? (loading ? <div className="operations-empty">Loading clients…</div> : filtered.length === 0 ?
        <div className="operations-empty">No management clients found.</div> :
        <div className="operations-table-wrap"><table className="operations-table mct-register-table"><thead><tr>
          <th>Client ID</th><th>Client Organization</th><th>Contact Person</th><th>Registered By</th><th>Created</th><th>Projects</th><th>Tracking (Overall)</th><th>Actions</th>
        </tr></thead><tbody>{(filtered).slice((managementClientSafePage - 1) * managementClientPageSize, managementClientSafePage * managementClientPageSize).map(client => {
          const clientTracking = tracking?.clients[String(client.id)]
          const clientProjects = projects.filter(project => project.management_client_id === client.id)
          const hasApprovableProject = clientProjects.some(project => project.can_approve)
          const expanded = expandedClientId === client.id
          const latestRequest = additionalRequests.find(row => row.management_client_id === client.id)
          const pendingRequest = additionalRequests.some(row => row.management_client_id === client.id && row.status === 'PENDING')
          return <Fragment key={client.id}>
            <tr><td><button className="mct-expand" type="button" onClick={() => setExpandedClientId(expanded ? null : client.id)} aria-expanded={expanded} aria-label={`${expanded ? 'Collapse' : 'Expand'} projects for ${client.client_name}`}>
              {expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
              <strong>{client.client_code}</strong></button></td>
              <td>{client.client_name}</td><td>{client.contact_person_name}</td><td>{client.source_person_name}</td><td>{formatDate(client.created_at)}</td>
              <td><button type="button" className="mct-count" onClick={() => setExpandedClientId(expanded ? null : client.id)}>{clientTracking ? `${clientTracking.project_count} ${clientTracking.project_count === 1 ? 'Project' : 'Projects'}` : '—'}</button></td>
              <td>{clientTracking && clientTracking.project_count ? <div className="mct-progress-cell"><div className={'mct-management-progress-tone mct-v8-' + managementProgressTone(clientTracking.overall_percent)}><ProgressMeter value={clientTracking.overall_percent} label={`${client.client_name} stage completion`} /></div><span>{percentText(clientTracking.overall_percent)}</span></div> : '—'}</td>
              <td><div className="operations-actions"><button type="button" className="operations-button secondary" onClick={() => { setSelectedId(client.id); setShowForm(false) }}>View</button><button type="button" className="operations-button secondary" onClick={() => openEdit(client)}><Pencil size={14} /> Edit</button>
                {client.can_request_project && <button type="button" className="operations-button secondary" disabled={pendingRequest || requestBusy} onClick={() => openAdditionalRequest(client)}><Plus size={14} /> Request Project</button>}
                {latestRequest && <span title={latestRequest.project_name} style={{ fontSize: 12, fontWeight: 500, whiteSpace: 'nowrap', padding: '6px 9px', borderRadius: 8, background: latestRequest.status === 'CREATED' ? '#e8f6eb' : '#fcebea', color: latestRequest.status === 'CREATED' ? '#166534' : '#a23e3e', border: `1px solid ${latestRequest.status === 'CREATED' ? '#b9dec1' : '#efc9c6'}` }}>{latestRequest.status === 'CREATED' ? `Project Created: ${latestRequest.created_project_code || ''}` : 'Awaiting Finance'}</span>}
                {hasApprovableProject && <button type="button" className="operations-button secondary" onClick={() => setExpandedClientId(client.id)}><CheckCircle2 size={14} /> Approve</button>}</div></td>
            </tr>
            {expanded && <tr className="mct-expanded-row"><td colSpan={8}>
              <div className="mct-client-projects"><h3>Client Projects — {client.client_name} ({clientProjects.length})</h3>
                {clientProjects.length === 0 ? <p>No Finance-created management projects for this client yet.</p> :
                  <div className="mct-projects-scroll"><table className="mct-projects-table"><thead><tr><th>Project Code</th><th>Project Name</th><th>Department</th><th>Production</th><th>QC</th><th>QA</th><th>Delivery</th><th>Status</th><th>Action</th></tr></thead>
                    <tbody>{clientProjects.map(project => <tr key={project.id}>
                      <td><strong>{project.project_code}</strong></td><td>{project.project_name}{project.project_type === 'pilot' && <span style={{ marginLeft: 8, fontWeight: 700, color: '#176d79' }}>PILOT</span>}</td><td>{project.department_label}</td>
                      {stages.map(stage => <td key={stage}>{percentText(project.tracking.stages[stage].percent)}</td>)}
                      <td>{project.tracking.operational_status}<small> · {project.source_approved && project.workflow_status === 'READY_FOR_BILLING' ? 'Approved / Ready for Billing' : readable(project.workflow_status)}</small></td>
                      <td><div className="operations-actions"><button type="button" className="mct-track-button" onClick={() => setTrackingProjectId(project.id)}><Eye size={14} /> View Tracking</button>{project.can_approve && <button type="button" className="operations-button secondary" disabled={busy} onClick={() => void approveProject(project)}><CheckCircle2 size={14} /> Approve</button>}</div></td>
                    </tr>)}</tbody></table></div>}
              </div>
            </td></tr>}
          </Fragment>
        })}</tbody></table>
          {/* Management Client Register: pagination, appearance only. */}
          <nav aria-label="Registered clients pagination" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, padding: "12px 8px 6px", color: "#234969", fontSize: 13 }}>
            <span aria-live="polite">Showing {managementClientFirst}–{managementClientLast} of {managementClientTotal} clients</span>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <button type="button" disabled={managementClientSafePage <= 1} onClick={() => setManagementClientPage(page => Math.max(1, Math.min(page, managementClientPageCount) - 1))} style={{ padding: "7px 13px", borderRadius: 8, border: "1px solid #bdd4e8", background: "#ffffff", color: "#153e60", fontSize: 13, cursor: managementClientSafePage <= 1 ? "not-allowed" : "pointer", opacity: managementClientSafePage <= 1 ? 0.5 : 1 }}>Previous</button>
              <span style={{ whiteSpace: "nowrap" }}>Page {managementClientSafePage} of {managementClientPageCount}</span>
              <button type="button" disabled={managementClientSafePage >= managementClientPageCount} onClick={() => setManagementClientPage(page => Math.min(managementClientPageCount, Math.min(page, managementClientPageCount) + 1))} style={{ padding: "7px 13px", borderRadius: 8, border: "1px solid #bdd4e8", background: "#ffffff", color: "#153e60", fontSize: 13, cursor: managementClientSafePage >= managementClientPageCount ? "not-allowed" : "pointer", opacity: managementClientSafePage >= managementClientPageCount ? 0.5 : 1 }}>Next</button>
            </div>
          </nav></div>) :
        <div className="operations-table-wrap"><table className="operations-table mct-register-table"><thead><tr>
          <th>Project Code</th><th>Client / Source</th><th>Project Name</th><th>Department</th><th>Progress</th><th>Operational Status</th><th>Action</th>
        </tr></thead><tbody>{filteredProjects.map(project => {
          const client = clients.find(item => item.id === project.management_client_id)
          return <tr key={project.id}><td><strong>{project.project_code}</strong></td>
            <td><strong>{client?.client_name || 'Management client'}</strong><small>{project.source_person_name}</small></td>
            <td><strong>{project.project_name}</strong>{project.project_type === 'pilot' && <small style={{ color: '#176d79', fontWeight: 700 }}>PILOT · {project.pilot_payment_type?.toUpperCase()}</small>}<small>PM: {project.project_manager_name || 'Not assigned'}</small></td>
            <td>{project.department_label}</td><td><div className="mct-progress-cell"><div className={'mct-management-progress-tone mct-v8-' + managementProgressTone(project.tracking.overall_percent)}><ProgressMeter value={project.tracking.overall_percent} label={`${project.project_code} stage completion`} /></div><span>{percentText(project.tracking.overall_percent)}</span></div></td>
            <td>{project.tracking.operational_status}<small> · {project.source_approved && project.workflow_status === 'READY_FOR_BILLING' ? 'Approved / Ready for Billing' : readable(project.workflow_status)}</small></td>
            <td><div className="operations-actions"><button type="button" className="mct-track-button" onClick={() => setTrackingProjectId(project.id)}><Eye size={14} /> View Tracking</button>{project.can_approve && <button type="button" className="operations-button secondary" disabled={busy} onClick={() => void approveProject(project)}><CheckCircle2 size={14} /> Approve</button>}</div></td>
          </tr>
        })}</tbody></table>{filteredProjects.length === 0 && <div className="operations-empty">{tracking ? 'No matching management projects.' : 'Loading management project tracking…'}</div>}</div>}
      <div className="mct-tracking-footer">Live project tracking · Only the original Management source can approve fully delivered projects · Automatically refreshes every 5 seconds while this page is open{tracking?.as_of ? ` · Last updated ${formatDateTime(tracking.as_of)}` : ''}</div>
    </section>
    {selectedTrackingProject && <ManagementTrackingDialog key={selectedTrackingProject.id} project={selectedTrackingProject}
      client={clients.find(item => item.id === selectedTrackingProject.management_client_id)}
      onClose={closeTracking} />}
  </div>
}
