import { CheckCircle2, ClipboardList, PlusCircle } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import type { DroneAssetListResponse, DroneKit, DroneProject, DroneWorkRecord } from '../../../types'

const today = new Date().toISOString().slice(0, 10)

export function DroneWorkRecordsPage() {
  const [records, setRecords] = useState<DroneWorkRecord[]>([])
  const [projects, setProjects] = useState<DroneProject[]>([])
  const [assets, setAssets] = useState<DroneAssetListResponse['items']>([])
  const [kits, setKits] = useState<DroneKit[]>([])
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [form, setForm] = useState({ title: '', work_type: 'inspection', project_id: '', asset_id: '', kit_id: '', assigned_to: '', technician: 'Drone Department', priority: 'medium', description: '', initial_condition: '', start_date: today, expected_completion_date: '' })

  const load = async () => {
    setError('')
    try {
      const [work, projectRows, assetRows, kitRows] = await Promise.all([
        apiFetch<DroneWorkRecord[]>('/drone/work-records'),
        apiFetch<DroneProject[]>('/drone/projects'),
        apiFetch<DroneAssetListResponse>('/drone/assets?limit=500'),
        apiFetch<DroneKit[]>('/drone/kits'),
      ])
      setRecords(work); setProjects(projectRows); setAssets(assetRows.items); setKits(kitRows)
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to load Drone work records') }
  }

  useEffect(() => { void load() }, [])

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError(''); setSuccess('')
    try {
      const created = await apiFetch<DroneWorkRecord>('/drone/work-records', {
        method: 'POST',
        body: JSON.stringify({
          ...form,
          project_id: form.project_id ? Number(form.project_id) : null,
          asset_id: form.asset_id ? Number(form.asset_id) : null,
          kit_id: form.kit_id ? Number(form.kit_id) : null,
          expected_completion_date: form.expected_completion_date || null,
        }),
      })
      setSuccess(`${created.work_code} created successfully.`)
      setForm({ title: '', work_type: 'inspection', project_id: '', asset_id: '', kit_id: '', assigned_to: '', technician: 'Drone Department', priority: 'medium', description: '', initial_condition: '', start_date: today, expected_completion_date: '' })
      await load()
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to create work record') }
  }

  const complete = async (record: DroneWorkRecord) => {
    setError(''); setSuccess('')
    try {
      await apiFetch(`/drone/work-records/${record.id}`, { method: 'PATCH', body: JSON.stringify({ status: 'completed', resolution: 'Work completed and verified by Drone Department' }) })
      setSuccess(`${record.work_code} marked completed.`); await load()
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to complete work record') }
  }

  return <>
    <DashboardHeader eyebrow="DRONE DEPARTMENT WORKFLOW" title="Drone Work Records" description="Record inspections, flight planning, equipment checks, field preparation and operational tasks. Dispatch and return transactions automatically create linked work records here." />
    {error && <div className="error-message">{error}</div>}
    {success && <div className="success-message">{success}</div>}
    <section className="work-record-layout">
      <form className="panel drone-work-form" onSubmit={submit}>
        <div className="panel-heading"><div><span className="section-kicker">NEW WORK RECORD</span><h2>Record Drone Department Work</h2></div><PlusCircle /></div>
        <div className="form-grid operation-form-grid">
          <label><span>Work Type *</span><select value={form.work_type} onChange={e => setForm({ ...form, work_type: e.target.value })}><option value="inspection">Inspection</option><option value="flight_planning">Flight Planning</option><option value="pre_flight_check">Pre-flight Check</option><option value="post_flight_check">Post-flight Check</option><option value="equipment_preparation">Equipment Preparation</option><option value="data_processing">Data Processing</option><option value="documentation">Documentation</option><option value="other">Other</option></select></label>
          <label><span>Priority *</span><select value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value })}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select></label>
          <label className="wide"><span>Work Title *</span><input required value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="Example: Pre-flight inspection of Trinity Unit 1173" /></label>
          <label><span>Project</span><select value={form.project_id} onChange={e => setForm({ ...form, project_id: e.target.value })}><option value="">No project</option>{projects.map(project => <option key={project.id} value={project.id}>{project.project_code} · {project.project_name}</option>)}</select></label>
          <label><span>Asset</span><select value={form.asset_id} onChange={e => setForm({ ...form, asset_id: e.target.value, kit_id: e.target.value ? '' : form.kit_id })}><option value="">No individual asset</option>{assets.map(asset => <option key={asset.id} value={asset.id}>{asset.asset_tag} · {asset.asset_name}</option>)}</select></label>
          <label><span>Kit</span><select value={form.kit_id} onChange={e => setForm({ ...form, kit_id: e.target.value, asset_id: e.target.value ? '' : form.asset_id })}><option value="">No kit</option>{kits.map(kit => <option key={kit.id} value={kit.id}>{kit.kit_tag} · {kit.kit_name}</option>)}</select></label>
          <label><span>Assigned Employee / Team</span><input value={form.assigned_to} onChange={e => setForm({ ...form, assigned_to: e.target.value })} /></label>
          <label><span>Technician / Function</span><input value={form.technician} onChange={e => setForm({ ...form, technician: e.target.value })} /></label>
          <label><span>Start Date</span><input type="date" value={form.start_date} onChange={e => setForm({ ...form, start_date: e.target.value })} /></label>
          <label><span>Expected Completion</span><input type="date" value={form.expected_completion_date} onChange={e => setForm({ ...form, expected_completion_date: e.target.value })} /></label>
          <label className="wide"><span>Description</span><textarea value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} /></label>
          <label className="wide"><span>Initial Condition / Required Components</span><textarea value={form.initial_condition} onChange={e => setForm({ ...form, initial_condition: e.target.value })} /></label>
        </div>
        <button className="primary-button full-action"><ClipboardList size={17} /> Create Work Record</button>
      </form>

      <section className="panel drone-work-history">
        <div className="panel-heading"><div><span className="section-kicker">OPERATION HISTORY</span><h2>Current Drone Work Records</h2></div><span className="count-chip">{records.length}</span></div>
        <div className="work-record-list">
          {records.map(record => <article key={record.id}>
            <div className="work-record-copy"><span className="section-kicker">{record.work_code}</span><h3>{record.title}</h3><p>{record.description || 'No description recorded.'}</p><div className="record-chips"><span>{record.work_type.replaceAll('_',' ')}</span><span>{record.priority}</span>{record.project && <span>{record.project}</span>}{record.asset_tag && <span>{record.asset_tag}</span>}{record.kit_tag && <span>{record.kit_tag}</span>}</div></div>
            <div className="work-record-actions"><span className={`status ${record.status}`}>{record.status.replaceAll('_',' ')}</span>{!['completed','closed','cancelled'].includes(record.status) && <button className="primary-button small" onClick={() => void complete(record)}><CheckCircle2 size={15} /> Complete</button>}</div>
          </article>)}
          {records.length === 0 && <div className="empty-state">No Drone work records have been created.</div>}
        </div>
      </section>
    </section>
  </>
}
