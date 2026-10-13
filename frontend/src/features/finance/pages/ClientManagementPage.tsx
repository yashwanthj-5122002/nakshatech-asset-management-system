import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import {
  Building2,
  CalendarDays,
  ContactRound,
  Download,
  Edit3,
  FolderKanban,
  Mail,
  MapPin,
  Phone,
  Plus,
  Save,
  Search,
  Upload,
  UserRound,
  X,
} from 'lucide-react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch, downloadFile, uploadExcel } from '../../../lib/api'
import type { FinanceClient, FinanceClientSourceTeam, FinanceClientType, FinanceProject, FinanceProjectMasterStatus, FinanceProjectMasterUser } from '../../../types'
import '../finance-expenses.css'

type ClientForm = {
  client_code: string
  vendor_code: string
  client_type: FinanceClientType
  client_name: string
  primary_phone: string
  client_email: string
  contact_person_name: string
  contact_person_phone: string
  contact_person_email: string
  task: string
  bd_name: string
  address: string
  description: string
  country: string
  gst_number: string
  source_team: FinanceClientSourceTeam
  source_person_name: string
  is_active: boolean
}

type ProjectForm = {
  project_code: string
  project_name: string
  task: string
  project_status: FinanceProjectMasterStatus
  project_manager_id: string
  reporting_manager_id: string
  assigned_employee_ids: number[]
  project_source_team: FinanceClientSourceTeam
  project_source_person_name: string
  client_awarded_by_name: string
  project_award_date: string
  description: string
  start_date: string
  end_date: string
  is_active: boolean
}

const sourceTeamLabels: Record<FinanceClientSourceTeam, string> = {
  bd_team: 'BD Team',
  software_team: 'Software Team',
  team_manager: 'Team Manager',
  manager: 'Manager',
  department_head: 'Department Head',
  management: 'Management',
  other: 'Other',
}

const emptyClientForm: ClientForm = {
  client_code: '',
  vendor_code: '',
  client_type: 'client',
  client_name: '',
  primary_phone: '',
  client_email: '',
  contact_person_name: '',
  contact_person_phone: '',
  contact_person_email: '',
  task: '',
  bd_name: '',
  address: '',
  description: '',
  country: 'India',
  gst_number: '',
  source_team: 'bd_team',
  source_person_name: '',
  is_active: true,
}

const emptyProjectForm: ProjectForm = {
  project_code: '',
  project_name: '',
  task: '',
  project_status: 'active',
  project_manager_id: '',
  reporting_manager_id: '',
  assigned_employee_ids: [],
  project_source_team: 'bd_team',
  project_source_person_name: '',
  client_awarded_by_name: '',
  project_award_date: '',
  description: '',
  start_date: '',
  end_date: '',
  is_active: true,
}

function clean(value: string): string | null {
  const text = value.trim()
  return text || null
}

function projectStatus(project: FinanceProject): string {
  return project.lifecycle_status.replaceAll('_', ' ')
}

export function ClientManagementPage() {
  const { user } = useAuth()
  const readOnly = user?.role === 'management' || user?.role === 'finance'
  const [clients, setClients] = useState<FinanceClient[]>([])
  const [projects, setProjects] = useState<FinanceProject[]>([])
  const [allProjects, setAllProjects] = useState<FinanceProject[]>([])
  const [projectSearch, setProjectSearch] = useState('')
  const [masterUsers, setMasterUsers] = useState<FinanceProjectMasterUser[]>([])
  const [selectedClientId, setSelectedClientId] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [clientEditorOpen, setClientEditorOpen] = useState(false)
  const [editingClientId, setEditingClientId] = useState<number | null>(null)
  const [clientForm, setClientForm] = useState<ClientForm>(emptyClientForm)
  const [projectEditorOpen, setProjectEditorOpen] = useState(false)
  const [editingProjectId, setEditingProjectId] = useState<number | null>(null)
  const [projectForm, setProjectForm] = useState<ProjectForm>(emptyProjectForm)
  const clientEditorRef = useRef<HTMLElement | null>(null)
  const projectEditorRef = useRef<HTMLElement | null>(null)

  // Naksha ERP V7.0.12 - editor navigation / focus alignment at Chrome 100%.
  useEffect(() => {
    if (!clientEditorOpen) return
    let focusTimer = 0
    const frame = window.requestAnimationFrame(() => {
      const editor = clientEditorRef.current
      if (!editor) return
      editor.scrollIntoView({ behavior: 'smooth', block: 'start' })
      focusTimer = window.setTimeout(() => {
        editor.querySelector<HTMLElement>('input:not([readonly]):not([disabled]), select:not([disabled]), textarea:not([disabled])')?.focus({ preventScroll: true })
      }, 350)
    })
    return () => {
      window.cancelAnimationFrame(frame)
      if (focusTimer) window.clearTimeout(focusTimer)
    }
  }, [clientEditorOpen, editingClientId])

  useEffect(() => {
    if (!projectEditorOpen) return
    let focusTimer = 0
    const frame = window.requestAnimationFrame(() => {
      const editor = projectEditorRef.current
      if (!editor) return
      editor.scrollIntoView({ behavior: 'smooth', block: 'start' })
      focusTimer = window.setTimeout(() => {
        editor.querySelector<HTMLElement>('input:not([readonly]):not([disabled]), select:not([disabled]), textarea:not([disabled])')?.focus({ preventScroll: true })
      }, 350)
    })
    return () => {
      window.cancelAnimationFrame(frame)
      if (focusTimer) window.clearTimeout(focusTimer)
    }
  }, [projectEditorOpen, editingProjectId])

  const selectedClient = clients.find(item => item.id === selectedClientId) || null
  const employeeUsers = masterUsers.filter(item => item.role === 'employee')

  const filteredClients = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return clients
    return clients.filter(client => [
      client.client_code,
      client.client_name,
      client.client_email || '',
      client.contact_person_name,
      client.contact_person_phone || '',
      client.contact_person_email || '',
      client.bd_name || '',
      client.task || '',
      client.gst_number || '',
      client.source_person_name || '',
      sourceTeamLabels[client.source_team],
    ].some(value => value.toLowerCase().includes(q)))
  }, [clients, search])

  const filteredAllProjects = useMemo(() => {
    const q = projectSearch.trim().toLowerCase()
    if (!q) return allProjects
    return allProjects.filter(project => [
      project.project_code,
      project.project_name,
      project.client_code || '',
      project.client_name || '',
      project.task || '',
      project.project_manager_name || '',
      project.reporting_manager_name || '',
      project.project_status || '',
      project.lifecycle_status || '',
    ].some(value => value.toLowerCase().includes(q)))
  }, [allProjects, projectSearch])

  const activeProjects = allProjects.filter(project => project.project_status === 'active').length

  async function loadAllProjects() {
    const result = await apiFetch<FinanceProject[]>('/finance/report-projects')
    setAllProjects(result)
    return result
  }

  async function loadClients(preferredId?: number | null) {
    setError('')
    const result = await apiFetch<FinanceClient[]>('/finance/clients')
    setClients(result)
    const requestedId = preferredId ?? selectedClientId
    const nextId = requestedId && result.some(item => item.id === requestedId)
      ? requestedId
      : result[0]?.id ?? null
    setSelectedClientId(nextId)
    return nextId
  }

  async function loadProjects(clientId: number | null) {
    if (!clientId) {
      setProjects([])
      return
    }
    const result = await apiFetch<FinanceProject[]>(`/finance/clients/${clientId}/projects`)
    setProjects(result)
  }

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [result, projectResult] = await Promise.all([
          apiFetch<FinanceClient[]>('/finance/clients'),
          apiFetch<FinanceProject[]>('/finance/report-projects'),
        ])
        if (cancelled) return
        setClients(result)
        setAllProjects(projectResult)
        setSelectedClientId(result[0]?.id ?? null)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load Finance client master')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    let cancelled = false
    apiFetch<FinanceProjectMasterUser[]>('/finance/project-master/users')
      .then(result => { if (!cancelled) setMasterUsers(result) })
      .catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load employee/project manager directory') })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    let cancelled = false
    if (!selectedClientId) {
      setProjects([])
      return
    }
    apiFetch<FinanceProject[]>(`/finance/clients/${selectedClientId}/projects`)
      .then(result => { if (!cancelled) setProjects(result) })
      .catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load client projects') })
    return () => { cancelled = true }
  }, [selectedClientId])

  function startAddClient() {
    setEditingClientId(null)
    setClientForm(emptyClientForm)
    setClientEditorOpen(true)
    setProjectEditorOpen(false)
    setMessage('')
    setError('')
  }

  function startEditClient(client: FinanceClient) {
    setEditingClientId(client.id)
    setClientForm({
      client_code: client.client_code,
      vendor_code: client.vendor_code || '',
      client_type: client.client_type || 'client',
      client_name: client.client_name,
      primary_phone: client.primary_phone || '',
      client_email: client.client_email || '',
      contact_person_name: client.contact_person_name,
      contact_person_phone: client.contact_person_phone || '',
      contact_person_email: client.contact_person_email || '',
      task: client.task || '',
      bd_name: client.bd_name || '',
      address: client.address || '',
      description: client.description || '',
      country: client.country || 'India',
      gst_number: client.gst_number || '',
      source_team: client.source_team,
      source_person_name: client.source_person_name || '',
      is_active: client.is_active,
    })
    setClientEditorOpen(true)
    setProjectEditorOpen(false)
    setMessage('')
    setError('')
  }

  async function saveClient(event: FormEvent) {
    event.preventDefault()
    setBusy('client')
    setError('')
    setMessage('')
    try {
      const { client_code, ...editableClientFields } = clientForm
      const payload = {
        ...editableClientFields,
        primary_phone: clean(clientForm.primary_phone),
        client_email: clean(clientForm.client_email),
        contact_person_phone: clean(clientForm.contact_person_phone),
        contact_person_email: clean(clientForm.contact_person_email),
        task: clean(clientForm.task),
        bd_name: clean(clientForm.bd_name),
        source_person_name: clean(clientForm.source_person_name) || clean(clientForm.bd_name),
        address: clean(clientForm.address),
        description: clean(clientForm.description),
        gst_number: clean(clientForm.gst_number),
      }
      const saved = editingClientId
        ? await apiFetch<FinanceClient>(`/finance/clients/${editingClientId}`, { method: 'PUT', body: JSON.stringify(payload) })
        : await apiFetch<FinanceClient>('/finance/clients', { method: 'POST', body: JSON.stringify({ ...payload, client_code: client_code.trim().toUpperCase() }) })
      const selected = await loadClients(saved.id)
      await loadProjects(selected)
      setClientEditorOpen(false)
      setEditingClientId(null)
      setMessage(editingClientId ? `${saved.client_code} updated.` : `${saved.client_code} created. You can now add projects under this client.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save client')
    } finally {
      setBusy('')
    }
  }

  function startAddProject() {
    if (!selectedClient) return
    setEditingProjectId(null)
    setProjectForm({
      ...emptyProjectForm,
      task: selectedClient.task || '',
      project_source_person_name: selectedClient.bd_name || selectedClient.source_person_name || '',
      client_awarded_by_name: selectedClient.contact_person_name,
    })
    setProjectEditorOpen(true)
    setClientEditorOpen(false)
    setMessage('')
    setError('')
  }

  function startEditProject(project: FinanceProject) {
    setEditingProjectId(project.id)
    setProjectForm({
      project_code: project.project_code,
      project_name: project.project_name,
      task: project.task || '',
      project_status: project.project_status || (project.is_active ? 'active' : 'inactive'),
      project_manager_id: project.project_manager_id ? String(project.project_manager_id) : '',
      reporting_manager_id: project.reporting_manager_id ? String(project.reporting_manager_id) : '',
      assigned_employee_ids: project.assigned_employee_ids || [],
      project_source_team: project.project_source_team || 'bd_team',
      project_source_person_name: project.project_source_person_name || '',
      client_awarded_by_name: project.client_awarded_by_name || '',
      project_award_date: project.project_award_date || '',
      description: project.description || '',
      start_date: project.start_date || '',
      end_date: project.end_date || '',
      is_active: project.is_active,
    })
    setProjectEditorOpen(true)
    setClientEditorOpen(false)
    setMessage('')
    setError('')
  }

  async function saveProject(event: FormEvent) {
    event.preventDefault()
    if (!selectedClient) return
    setBusy('project')
    setError('')
    setMessage('')
    try {
      const { project_code, ...editableProjectFields } = projectForm
      const payload = {
        ...editableProjectFields,
        task: clean(projectForm.task),
        project_manager_id: undefined, // BD-owned; JSON.stringify omits this field.
        reporting_manager_id: projectForm.reporting_manager_id ? Number(projectForm.reporting_manager_id) : null,
        assigned_employee_ids: projectForm.assigned_employee_ids,
        is_active: projectForm.project_status === 'active',
        client_awarded_by_name: clean(projectForm.client_awarded_by_name),
        project_award_date: clean(projectForm.project_award_date),
        description: clean(projectForm.description),
      }
      const saved = editingProjectId
        ? await apiFetch<FinanceProject>(`/finance/clients/${selectedClient.id}/projects/${editingProjectId}`, { method: 'PUT', body: JSON.stringify(payload) })
        : await apiFetch<FinanceProject>(`/finance/clients/${selectedClient.id}/projects`, { method: 'POST', body: JSON.stringify({ ...payload, project_code: project_code.trim().toUpperCase() }) })
      await loadProjects(selectedClient.id)
      await loadClients(selectedClient.id)
      await loadAllProjects()
      setProjectEditorOpen(false)
      setEditingProjectId(null)
      setMessage(editingProjectId ? `${saved.project_code} updated.` : `${saved.project_code} created and connected to Employee Project Expense selection.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save project')
    } finally {
      setBusy('')
    }
  }

  async function importClientWorkbook(file: File) {
    setBusy('import'); setError(''); setMessage('')
    try {
      const result = await uploadExcel('/finance/client-master/import.xlsx', file) as { created?: number; updated?: number; skipped_existing?: number; skipped_incomplete?: number; issue_count?: number }
      await loadClients(selectedClientId)
      await loadAllProjects()
      setMessage(`Client Excel imported: ${result.created || 0} new, ${result.updated || 0} updated, ${result.skipped_existing || 0} existing skipped, ${result.skipped_incomplete || 0} incomplete skipped.`)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not import Client Master Excel') }
    finally { setBusy('') }
  }

  async function changeProjectStatus(project: FinanceProject, nextStatus: FinanceProjectMasterStatus) {
    const label = nextStatus.replaceAll('_', ' ')
    if (!window.confirm(`Change ${project.project_code} status to ${label.toUpperCase()}?`)) return
    setBusy(`status-${project.id}`)
    setError('')
    setMessage('')
    try {
      const saved = await apiFetch<FinanceProject>(`/finance/projects/${project.id}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ project_status: nextStatus }),
      })
      await loadAllProjects()
      if (project.client_id && project.client_id === selectedClientId) await loadProjects(project.client_id)
      await loadClients(selectedClientId)
      setMessage(`${saved.project_code} is now ${saved.project_status.replaceAll('_', ' ').toUpperCase()}. ${saved.expense_allowed ? 'Employee claims are open.' : saved.expense_block_reason || 'Employee claims remain blocked.'}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not change project status')
    } finally {
      setBusy('')
    }
  }

  function openProjectFromMaster(project: FinanceProject) {
    if (!project.client_id || !clients.some(client => client.id === project.client_id)) {
      setError(`${project.project_code} is a legacy/unlinked project. You can change its status here, but link it to a Client Master record before editing full project details.`)
      return
    }
    setSelectedClientId(project.client_id)
    setProjects([])
    setClientEditorOpen(false)
    startEditProject(project)
  }

  async function downloadMaster() {
    setBusy('download'); setError('')
    try { await downloadFile('/finance/client-master/export.xlsx', 'Naksha_Client_Project_CRM_Master.xlsx') }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not download Client/Project CRM Excel') }
    finally { setBusy('') }
  }

  async function downloadClientReport(client: FinanceClient) {
    setBusy(`client-report-${client.id}`); setError('')
    try { await downloadFile(`/finance/clients/${client.id}/report.xlsx`, `Client_${client.client_code}_Detailed_Tracking.xlsx`) }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not download client report') }
    finally { setBusy('') }
  }

  async function downloadProjectReport(project: FinanceProject) {
    setBusy(`project-report-${project.id}`); setError('')
    try { await downloadFile(`/finance/projects/${project.id}/report.xlsx`, `Project_${project.project_code}_Detailed_Tracking.xlsx`) }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not download project report') }
    finally { setBusy('') }
  }

  if (loading) return <div className="finance-page"><div className="finance-panel finance-empty-state">Loading Client Management...</div></div>

  return <div className="finance-page">
    <DashboardHeader
      eyebrow="FINANCE · CLIENT MASTER"
      title="Client Management"
      description="Central CRM master for imported and newly added clients, Finance-controlled Client/Project IDs and project lifecycle, BD-controlled Project Manager, workforce tracking, Travel/KM linkage, and detailed Excel tracking."
      actions={<div className="finance-toolbar">
        <button className="finance-secondary-button" type="button" onClick={() => void downloadMaster()} disabled={busy === 'download'}><Download size={16}/> Download CRM Excel</button>
        {!readOnly && <label className="finance-secondary-button" style={{cursor: 'pointer'}}><Upload size={16}/> {busy === 'import' ? 'Importing...' : 'Import Client Excel'}<input type="file" accept=".xlsx" hidden disabled={busy === 'import'} onChange={event => { const file = event.target.files?.[0]; if (file) void importClientWorkbook(file); event.currentTarget.value = '' }} /></label>}
        {!readOnly && <button className="finance-primary-button" onClick={startAddClient}><Plus size={16} /> Add Client</button>}
      </div>}
      meta={<>
        <span className="nk-meta-chip"><Building2 size={14} /> Central CRM client & project master</span>
        <span className="nk-meta-chip"><FolderKanban size={14} /> Finance-controlled Client / Project IDs</span>
        <span className="nk-meta-chip"><Download size={14} /> Excel import & export supported</span>
      </>}
    />

    {error && <div className="finance-error">{error}</div>}
    {message && <div className="finance-success-message">{message}</div>}

    <section className="finance-kpi-grid finance-kpi-grid-4">
      <article className="finance-kpi-card"><span><Building2 size={15}/> Clients</span><strong>{clients.length}</strong><small>{clients.filter(item => item.is_active).length} active clients</small></article>
      <article className="finance-kpi-card"><span><FolderKanban size={15}/> Projects</span><strong>{allProjects.length}</strong><small>{activeProjects} marked active</small></article>
      <article className="finance-kpi-card"><span><ContactRound size={15}/> Acquisition Record</span><strong>{clients.filter(item => item.source_person_name).length}</strong><small>clients with source person captured</small></article>
      <article className="finance-kpi-card"><span><CalendarDays size={15}/> Project Master</span><strong>{allProjects.filter(item => item.project_status === 'completed').length}</strong><small>completed projects</small></article>
    </section>

    <section className="finance-panel">
      <div className="finance-panel-header">
        <div>
          <span className="finance-panel-kicker">GLOBAL PROJECT MASTER</span>
          <h2>Find & Activate Any Project ID</h2>
          <p>Search every project directly. Finance/Admin can activate, hold, complete or deactivate a Project ID without first finding its client. This also works for legacy projects that are not yet linked to Client Master.</p>
        </div>
      </div>
      <label className="finance-search finance-client-search"><Search size={16}/><input value={projectSearch} onChange={event => setProjectSearch(event.target.value)} placeholder="Search Project ID, project name, client, manager or status" /></label>
      <div className="finance-table-wrap"><table className="finance-table finance-client-project-table"><thead><tr><th>Project ID</th><th>Project</th><th>Client</th><th>Status</th><th>Claims</th><th>Manager</th>{!readOnly && <th>Change Status</th>}<th>Action</th></tr></thead><tbody>
        {filteredAllProjects.map(project => <tr key={project.id}>
          <td><strong>{project.project_code}</strong></td>
          <td><strong>{project.project_name}</strong><small>{project.task ? <><br/>{project.task}</> : null}</small></td>
          <td>{project.client_code ? <strong>{project.client_code}</strong> : <strong>Legacy / Unlinked</strong>}<small><br/>{project.client_name || 'Client not linked'}</small></td>
          <td><span className={`finance-status ${project.project_status === 'active' ? 'tone-success' : project.project_status === 'completed' ? 'tone-draft' : 'tone-warning'}`}>{project.project_status.replaceAll('_', ' ')}</span></td>
          <td>{project.expense_allowed ? <span className="finance-status tone-success">Claims Open</span> : <span className="finance-status tone-warning">Blocked</span>}<small>{project.expense_block_reason ? <><br/>{project.expense_block_reason}</> : null}</small></td>
          <td>{project.project_manager_name || 'Not assigned'}</td>
          {!readOnly && <td><div className="finance-toolbar">
            {project.project_status !== 'active' && <button type="button" className="finance-primary-button" disabled={busy === `status-${project.id}`} onClick={() => void changeProjectStatus(project, 'active')}>Activate</button>}
            {project.project_status === 'active' && <button type="button" className="finance-secondary-button" disabled={busy === `status-${project.id}`} onClick={() => void changeProjectStatus(project, 'on_hold')}>On Hold</button>}
            {project.project_status !== 'completed' && <button type="button" className="finance-secondary-button" disabled={busy === `status-${project.id}`} onClick={() => void changeProjectStatus(project, 'completed')}>Complete</button>}
            {project.project_status !== 'inactive' && <button type="button" className="finance-secondary-button" disabled={busy === `status-${project.id}`} onClick={() => void changeProjectStatus(project, 'inactive')}>Inactive</button>}
          </div></td>}
          <td><div className="finance-toolbar"><button type="button" className="finance-secondary-button" onClick={() => void downloadProjectReport(project)}><Download size={14}/> Excel</button>{!readOnly && project.client_id && <button type="button" className="finance-secondary-button" onClick={() => openProjectFromMaster(project)}><Edit3 size={14}/> Edit</button>}</div></td>
        </tr>)}
        {!filteredAllProjects.length && <tr><td colSpan={readOnly ? 7 : 8}><div className="finance-empty-state">No project matches this search.</div></td></tr>}
      </tbody></table></div>
    </section>

    <section className="finance-client-layout">
      <article className="finance-panel finance-client-register">
        <div className="finance-panel-header"><div><span className="finance-panel-kicker">CLIENT REGISTER</span><h2>Clients</h2><p>Client IDs/Codes come from the imported Client Codes workbook or are entered manually by Finance/Admin. No automatic Client ID is generated.</p></div></div>
        <label className="finance-search finance-client-search"><Search size={16}/><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search Client Code, company, contact, GST or source person" /></label>
        <div className="finance-client-list">
          {filteredClients.map(client => <button key={client.id} type="button" className={`finance-client-list-item ${selectedClientId === client.id ? 'selected' : ''}`} onClick={() => { setSelectedClientId(client.id); setClientEditorOpen(false); setProjectEditorOpen(false) }}>
            <span className="finance-client-code">{client.client_code}</span>
            <strong>{client.client_name}</strong>
            <small>{client.contact_person_name} · {client.contact_person_email || client.country}</small>
            <em>{client.project_count} project{client.project_count === 1 ? '' : 's'} · {client.is_active ? 'Active' : 'Inactive'}</em>
          </button>)}
          {!filteredClients.length && <div className="finance-empty-state">{clients.length ? 'No clients match this search.' : 'No client has been created yet.'}</div>}
        </div>
      </article>

      <div className="finance-client-workspace">
        {clientEditorOpen && <article ref={clientEditorRef} style={{ scrollMarginTop: '88px' }} className="finance-form-card finance-client-editor">
          <div className="finance-panel-header"><div><span className="finance-panel-kicker">{editingClientId ? 'EDIT CLIENT' : 'NEW CLIENT'}</span><h2>{editingClientId ? `Update ${clients.find(item => item.id === editingClientId)?.client_code || 'Client'}` : 'Add Client Details'}</h2><p>Finance/Admin enters the official Client ID / Code manually. The system never auto-generates it; duplicate IDs are blocked.</p></div><button type="button" className="finance-icon-button" onClick={() => setClientEditorOpen(false)}><X size={17}/></button></div>
          <form onSubmit={saveClient} className="finance-form-grid">
            <label className="finance-field"><span>Client ID / Code *</span><input required readOnly={!!editingClientId} value={clientForm.client_code} onChange={event => setClientForm({...clientForm, client_code: event.target.value.toUpperCase()})} placeholder="Example: NT1055" /></label>
            <label className="finance-field"><span>Vendor Code</span><input value={clientForm.vendor_code} onChange={event => setClientForm({...clientForm, vendor_code: event.target.value.toUpperCase()})} placeholder="Example: NV500" /></label>
            <label className="finance-field"><span>Client Type</span><select value={clientForm.client_type} onChange={event => setClientForm({...clientForm, client_type: event.target.value as FinanceClientType})}><option value="client">Client</option><option value="uav">UAV</option></select></label>
            <label className="finance-field"><span>Client Name *</span><input required value={clientForm.client_name} onChange={event => setClientForm({...clientForm, client_name: event.target.value})} /></label>
            <label className="finance-field full"><span>Task / Scope</span><textarea value={clientForm.task} onChange={event => setClientForm({...clientForm, task: event.target.value})} placeholder="Task from the Client Code master sheet" /></label>
            <label className="finance-field"><span>BD Name</span><input value={clientForm.bd_name} onChange={event => setClientForm({...clientForm, bd_name: event.target.value, source_person_name: event.target.value || clientForm.source_person_name})} placeholder="Business Development owner" /></label>
            <label className="finance-field"><span>Client Phone Number</span><input value={clientForm.primary_phone} onChange={event => setClientForm({...clientForm, primary_phone: event.target.value})} /></label>
            <label className="finance-field"><span>Client Email</span><input type="email" value={clientForm.client_email} onChange={event => setClientForm({...clientForm, client_email: event.target.value})} placeholder="client@company.com" /></label>
            <label className="finance-field"><span>Contact Person *</span><input required value={clientForm.contact_person_name} onChange={event => setClientForm({...clientForm, contact_person_name: event.target.value})} /></label>
            <label className="finance-field"><span>Contact Person Mail ID</span><input type="email" value={clientForm.contact_person_email} onChange={event => setClientForm({...clientForm, contact_person_email: event.target.value})} placeholder="contact@client.com" /></label>
            <label className="finance-field"><span>Contact Person Number</span><input value={clientForm.contact_person_phone} onChange={event => setClientForm({...clientForm, contact_person_phone: event.target.value})} placeholder="Optional" /></label>
            <label className="finance-field"><span>Country *</span><input required value={clientForm.country} onChange={event => setClientForm({...clientForm, country: event.target.value})} /></label>
            <label className="finance-field"><span>GST Number</span><input value={clientForm.gst_number} onChange={event => setClientForm({...clientForm, gst_number: event.target.value.toUpperCase()})} placeholder="Optional for non-GST / overseas clients" /></label>
            <label className="finance-field"><span>Client Source Team *</span><select value={clientForm.source_team} onChange={event => setClientForm({...clientForm, source_team: event.target.value as FinanceClientSourceTeam})}>{Object.entries(sourceTeamLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label className="finance-field"><span>Legacy Source Person</span><input value={clientForm.source_person_name} onChange={event => setClientForm({...clientForm, source_person_name: event.target.value})} placeholder="NakshaTech employee / manager / head name" /></label>
            <label className="finance-field full"><span>Address</span><textarea value={clientForm.address} onChange={event => setClientForm({...clientForm, address: event.target.value})} /></label>
            <label className="finance-field full"><span>Description / Notes</span><textarea value={clientForm.description} onChange={event => setClientForm({...clientForm, description: event.target.value})} /></label>
            <label className="finance-client-toggle full"><input type="checkbox" checked={clientForm.is_active} onChange={event => setClientForm({...clientForm, is_active: event.target.checked})}/><span>Client is active and can receive new projects</span></label>
            <div className="finance-toolbar full"><span className="finance-help-text">Existing Client Code remains unchanged when details are edited.</span><button className="finance-primary-button" disabled={busy === 'client'}><Save size={16}/> {busy === 'client' ? 'Saving...' : editingClientId ? 'Save Client Changes' : 'Create Client'}</button></div>
          </form>
        </article>}

        {projectEditorOpen && selectedClient && <article ref={projectEditorRef} style={{ scrollMarginTop: '88px' }} className="finance-form-card finance-client-editor">
          <div className="finance-panel-header"><div><span className="finance-panel-kicker">{editingProjectId ? 'EDIT PROJECT' : 'NEW CLIENT PROJECT'}</span><h2>{editingProjectId ? 'Update Project' : `Add Project Under ${selectedClient.client_code}`}</h2><p>{editingProjectId ? 'The manually entered Project Number remains immutable.' : 'Enter the official Project Number manually and record who secured this project for NakshaTech.'}</p></div><button type="button" className="finance-icon-button" onClick={() => setProjectEditorOpen(false)}><X size={17}/></button></div>
          <form onSubmit={saveProject} className="finance-form-grid">
            <label className="finance-field"><span>Project ID / Number *</span><input required readOnly={!!editingProjectId} value={projectForm.project_code} onChange={event => setProjectForm({...projectForm, project_code: event.target.value.toUpperCase()})} placeholder="Example: NT1055-P1" /></label>
            <label className="finance-field"><span>Project Name *</span><input required value={projectForm.project_name} onChange={event => setProjectForm({...projectForm, project_name: event.target.value})} /></label>
            <label className="finance-field full"><span>Task / Scope</span><textarea value={projectForm.task} onChange={event => setProjectForm({...projectForm, task: event.target.value})} placeholder="Project work scope / task" /></label>
            <label className="finance-field"><span>Project Status *</span><select value={projectForm.project_status} onChange={event => setProjectForm({...projectForm, project_status: event.target.value as FinanceProjectMasterStatus, is_active: event.target.value === 'active'})}><option value="active">Active</option><option value="on_hold">On Hold</option><option value="completed">Completed</option><option value="inactive">Inactive</option></select></label>
            <label className="finance-field"><span>Project Manager (BD Assigned)</span><input readOnly value={projectForm.project_manager_id ? (masterUsers.find(item => String(item.id) === projectForm.project_manager_id)?.full_name || `User #${projectForm.project_manager_id}`) : 'Not assigned by BD yet'} /><small>Read only for Finance/Admin. Only the BD team can assign or change the Project Manager after the official Project ID is created.</small></label>
            <label className="finance-field"><span>Reporting Manager</span><select value={projectForm.reporting_manager_id} onChange={event => setProjectForm({...projectForm, reporting_manager_id: event.target.value})}><option value="">Not assigned</option>{masterUsers.map(item => <option key={item.id} value={item.id}>{item.full_name} · {item.role}</option>)}</select></label>
            <label className="finance-field full"><span>Assigned Employees</span><select multiple size={Math.min(8, Math.max(4, employeeUsers.length || 4))} value={projectForm.assigned_employee_ids.map(String)} onChange={event => setProjectForm({...projectForm, assigned_employee_ids: Array.from(event.target.selectedOptions, option => Number(option.value))})}>{employeeUsers.map(item => <option key={item.id} value={item.id}>{item.full_name}{item.employee_id ? ` · ${item.employee_id}` : ''}{item.department ? ` · ${item.department}` : ''}</option>)}</select><small>Ctrl/Cmd-click to select multiple employees for staffing/allocation tracking. Assignment does not hide an active project from other employees; active project status controls whether a claim can be raised.</small></label>
            <label className="finance-field"><span>Project Secured Through *</span><select value={projectForm.project_source_team} onChange={event => setProjectForm({...projectForm, project_source_team: event.target.value as FinanceClientSourceTeam})}>{Object.entries(sourceTeamLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label className="finance-field"><span>Project Secured By *</span><input required value={projectForm.project_source_person_name} onChange={event => setProjectForm({...projectForm, project_source_person_name: event.target.value})} placeholder="NakshaTech employee / manager / head name" /></label>
            <label className="finance-field"><span>Client Person Who Awarded Project</span><input value={projectForm.client_awarded_by_name} onChange={event => setProjectForm({...projectForm, client_awarded_by_name: event.target.value})} /></label>
            <label className="finance-field"><span>Project Award Date</span><input type="date" value={projectForm.project_award_date} onChange={event => setProjectForm({...projectForm, project_award_date: event.target.value})} /></label>
            <label className="finance-field"><span>Project Start Date *</span><input required type="date" value={projectForm.start_date} onChange={event => setProjectForm({...projectForm, start_date: event.target.value})} /></label>
            <label className="finance-field"><span>Project End Date *</span><input required type="date" min={projectForm.start_date || undefined} value={projectForm.end_date} onChange={event => setProjectForm({...projectForm, end_date: event.target.value})} /></label>
            <label className="finance-field full"><span>Project Description</span><textarea value={projectForm.description} onChange={event => setProjectForm({...projectForm, description: event.target.value})} /></label>
            <div className="finance-toolbar full"><span className="finance-help-text">Employees see Client Name, Project ID/Number, Project Name and Task for project selection. Only active/ongoing projects can accept new claims; completed/on-hold/inactive projects are shown as blocked. Client contact, email, BD and commercial details remain Finance/Admin/Management-only.</span><button className="finance-primary-button" disabled={busy === 'project'}><Save size={16}/> {busy === 'project' ? 'Saving...' : editingProjectId ? 'Save Project Changes' : 'Create Project'}</button></div>
          </form>
        </article>}

        {!clientEditorOpen && !projectEditorOpen && !selectedClient && <article className="finance-panel finance-empty-state"><Building2 size={30}/><h2>Create your first client</h2><p>Enter the official Client Code, then add projects using their official Project Numbers. Active/ongoing projects become available to employees for Expense and Travel/KM claims; completed/on-hold/inactive projects remain visible as closed, while client contact/BD/commercial details remain protected.</p>{!readOnly && <button className="finance-primary-button" onClick={startAddClient}><Plus size={16}/> Add Client</button>}</article>}

        {!clientEditorOpen && !projectEditorOpen && selectedClient && <>
          <article className="finance-panel">
            <div className="finance-panel-header"><div><span className="finance-panel-kicker">CLIENT PROFILE</span><h2>{selectedClient.client_code} · {selectedClient.client_name}</h2><p>{selectedClient.description || 'No additional client description recorded.'}</p></div><div className="finance-toolbar"><button className="finance-secondary-button" type="button" disabled={busy === `client-report-${selectedClient.id}`} onClick={() => void downloadClientReport(selectedClient)}><Download size={15}/> Detailed Excel</button>{!readOnly && <button className="finance-secondary-button" onClick={() => startEditClient(selectedClient)}><Edit3 size={15}/> Edit Client</button>}</div></div>
            <div className="finance-client-profile-grid">
              <div><Building2/><span>Master Identity</span><strong>{selectedClient.client_code}</strong><small>{selectedClient.vendor_code ? `Vendor ${selectedClient.vendor_code} · ` : ''}{selectedClient.client_type?.toUpperCase() || 'CLIENT'}{selectedClient.import_source ? ` · Imported` : ' · Manual'}</small></div>
              <div><ContactRound/><span>Contact Person</span><strong>{selectedClient.contact_person_name}</strong><small>{selectedClient.contact_person_email || 'Mail ID not recorded'}{selectedClient.contact_person_phone ? ` · ${selectedClient.contact_person_phone}` : ''}</small></div>
              <div><UserRound/><span>BD Name</span><strong>{selectedClient.bd_name || selectedClient.source_person_name || 'Not recorded'}</strong><small>Internal business owner</small></div>
              <div><FolderKanban/><span>Task / Scope</span><strong>{selectedClient.task || 'Not recorded'}</strong><small>Client master task</small></div>
              <div><Phone/><span>Client Phone</span><strong>{selectedClient.primary_phone || 'Not recorded'}</strong><small>{selectedClient.is_active ? 'Active client' : 'Inactive client'}</small></div>
              <div><Mail/><span>Client Email</span><strong>{selectedClient.client_email || 'Not recorded'}</strong><small>Legacy / general client email</small></div>
              <div><MapPin/><span>Country / GST</span><strong>{selectedClient.country}</strong><small>{selectedClient.gst_number || 'GST not recorded'}</small></div>
            </div>
            {selectedClient.address && <div className="finance-client-address"><MapPin size={15}/><span>{selectedClient.address}</span></div>}
          </article>

          <article className="finance-panel">
            <div className="finance-panel-header"><div><span className="finance-panel-kicker">PROJECT MASTER</span><h2>Projects Under {selectedClient.client_code}</h2><p>Project IDs/Numbers are entered manually by Finance/Admin and reused by Expense, Travel/KM and V5 geofence verification. Employee assignment is retained for staffing reports, while project lifecycle/status determines whether any employee can raise a new claim. Employees receive Client Name + Project Name/ID + Task, but never contact/BD/commercial fields.</p></div>{!readOnly && <button className="finance-primary-button" disabled={!selectedClient.is_active} onClick={startAddProject}><Plus size={15}/> Add Project</button>}</div>
            <div className="finance-table-wrap"><table className="finance-table finance-client-project-table"><thead><tr><th>Project Number</th><th>Internal Project</th><th>BD Project Manager / Reporting</th><th>Assigned Employees</th><th>Period</th><th>Status</th><th>Travel Availability</th><th>Report</th>{!readOnly && <th>Action</th>}</tr></thead><tbody>
              {projects.map(project => <tr key={project.id}><td><strong>{project.project_code}</strong><small><br/>Employee-visible ID</small></td><td>{project.project_name}<small>{project.task ? <><br/>{project.task}</> : project.description ? <><br/>{project.description}</> : null}</small></td><td><strong>{project.project_manager_name || 'No Project Manager'}</strong><small><br/>Reporting: {project.reporting_manager_name || 'Not assigned'}</small></td><td><strong>{project.assigned_employees.length}</strong><small><br/>{project.assigned_employees.length ? project.assigned_employees.map(item => item.full_name).join(', ') : 'No employees assigned'}</small></td><td>{project.start_date || 'Not set'}<small><br/>to {project.end_date || 'Not set'}</small></td><td><span className={`finance-status ${project.lifecycle_status === 'active' ? 'tone-success' : project.lifecycle_status === 'upcoming' ? 'tone-pending' : 'tone-draft'}`}>{projectStatus(project)}</span></td><td>{project.expense_allowed ? <span className="finance-status tone-success">Claims Open</span> : <span className="finance-status tone-warning">Claims Blocked</span>}<small>{project.expense_block_reason ? <><br/>{project.expense_block_reason}</> : null}</small></td><td><button className="finance-secondary-button" type="button" disabled={busy === `project-report-${project.id}`} onClick={() => void downloadProjectReport(project)}><Download size={14}/> Excel</button></td>{!readOnly && <td><button className="finance-secondary-button" onClick={() => startEditProject(project)}><Edit3 size={14}/> Edit</button></td>}</tr>)}
              {!projects.length && <tr><td colSpan={readOnly ? 8 : 9}><div className="finance-empty-state">No projects exist under this client yet.</div></td></tr>}
            </tbody></table></div>
          </article>
        </>}
      </div>
    </section>
  </div>
}
