import { FolderPlus, Repeat2 } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import type { DroneProject } from '../../../types'

export function DroneProjectsPage() {
  const [projects, setProjects] = useState<DroneProject[]>([])
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState('')
  const [form, setForm] = useState({ project_name: '', client: '', project_manager: '', start_date: '', expected_end_date: '', status: 'planned', financial_year: '', location: '', project_area: '', description: '', remarks: '' })
  const load = () => apiFetch<DroneProject[]>('/drone/projects').then(setProjects).catch(err => setError(err.message))
  useEffect(() => { void load() }, [])
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError('')
    try {
      await apiFetch('/drone/projects', { method: 'POST', body: JSON.stringify({ ...form, start_date: form.start_date || null, expected_end_date: form.expected_end_date || null }) })
      setShowForm(false); setForm({ project_name: '', client: '', project_manager: '', start_date: '', expected_end_date: '', status: 'planned', financial_year: '', location: '', project_area: '', description: '', remarks: '' }); await load()
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to create project') }
  }
  return <>
    <DashboardHeader eyebrow="PROJECT MASTER" title="Drone Projects" description="Create every project once. Multiple projects can run in the same month, and one project can continue across several months or financial years." actions={<button className="primary-button" onClick={() => setShowForm(value => !value)}><FolderPlus size={17} /> New Project</button>} meta={<><span className="nk-meta-chip"><FolderPlus size={14} /> Create every project once</span><span className="nk-meta-chip"><Repeat2 size={14} /> Spans multiple months and financial years</span></>} />
    {error && <div className="error-message">{error}</div>}
    {showForm && <form className="panel compact-form-panel drone-project-form" onSubmit={submit}>
      <div className="compact-form-heading">
        <div><span className="section-kicker">NEW PROJECT</span><h2>Create New Project</h2><p>Enter the project master details once. The same project can continue across multiple months or financial years.</p></div>
      </div>
      <div className="form-grid project-form-grid">
        <label className="project-field project-name"><span>Project Name *</span><input required value={form.project_name} placeholder="Enter project name" onChange={event => setForm({ ...form, project_name: event.target.value })} /></label>
        <label className="project-field project-client"><span>Client</span><input value={form.client} placeholder="Enter client name" onChange={event => setForm({ ...form, client: event.target.value })} /></label>
        <label className="project-field project-manager"><span>Project Manager</span><input value={form.project_manager} placeholder="Enter manager name" onChange={event => setForm({ ...form, project_manager: event.target.value })} /></label>
        <label className="project-field project-status"><span>Status</span><select value={form.status} onChange={event => setForm({ ...form, status: event.target.value })}><option value="planned">Planned</option><option value="active">Active</option><option value="on_hold">On Hold</option><option value="delayed">Delayed</option><option value="completed">Completed</option><option value="closure_pending">Closure Pending</option><option value="closed">Closed</option><option value="cancelled">Cancelled</option></select></label>
        <label className="project-field project-start"><span>Start Date</span><input type="date" value={form.start_date} onChange={event => setForm({ ...form, start_date: event.target.value })} /></label>
        <label className="project-field project-end"><span>Expected End</span><input type="date" value={form.expected_end_date} onChange={event => setForm({ ...form, expected_end_date: event.target.value })} /></label>
        <label className="project-field project-fy"><span>Financial Year</span><input value={form.financial_year} placeholder="2026-27" onChange={event => setForm({ ...form, financial_year: event.target.value })} /></label>
        <label className="project-field project-location"><span>Location</span><input value={form.location} placeholder="Enter project location" onChange={event => setForm({ ...form, location: event.target.value })} /></label>
        <label className="project-field project-area"><span>Project Area</span><input value={form.project_area} placeholder="Sq.Km / district / corridor" onChange={event => setForm({ ...form, project_area: event.target.value })} /></label>
        <label className="project-field project-description"><span>Description</span><textarea value={form.description} placeholder="Enter project description" onChange={event => setForm({ ...form, description: event.target.value })} /></label>
        <label className="project-field project-remarks"><span>Remarks</span><textarea value={form.remarks} placeholder="Enter optional remarks" onChange={event => setForm({ ...form, remarks: event.target.value })} /></label>
      </div>
      <div className="form-actions"><button type="button" className="secondary-button" onClick={() => setShowForm(false)}>Cancel</button><button className="primary-button">Create Project</button></div>
    </form>}
    <section className="project-card-grid">
      {projects.map(project => <Link className="panel project-card project-card-link" to={`/drone/projects/${project.id}`} key={project.id}><div className="project-card-head"><div><span className="section-kicker">{project.project_code}</span><h2>{project.project_name}</h2></div><span className={`status ${project.status}`}>{project.status.replaceAll('_', ' ')}</span></div><p>{project.description || 'No project description recorded.'}</p><div className="project-meta"><div><span>Client</span><strong>{project.client || 'Not recorded'}</strong></div><div><span>Manager</span><strong>{project.project_manager || 'Not assigned'}</strong></div><div><span>Period</span><strong>{project.start_date || 'Not set'} → {project.expected_end_date || 'Open'}</strong></div><div><span>Location</span><strong>{project.location || 'Not recorded'}</strong></div></div><span className="project-open-link">Open project operations →</span></Link>)}
      {projects.length === 0 && <div className="empty-state">No Drone projects created yet.</div>}
    </section>
  </>
}
