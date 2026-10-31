import { BarChart3, Boxes, ChevronDown, ClipboardList, Eye, HardHat, Layers3, Map, MapPin, Plane, RadioTower, RefreshCcw, ScanLine, Search, Workflow, type LucideIcon } from 'lucide-react'
import { Fragment, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { StatCard } from '../../../components/StatCard'
import { apiFetch } from '../../../lib/api'
import type { PackageTrackingRow, ProjectTrackingRow, TrackingSummary } from '../components/ProductionTrackingPanel'
import '../operations.css'
import './bd-project-tracking.css'

// BD uses a dedicated GET-only endpoint and read-only UI. The department manager's
// ProductionTrackingPage, file activity endpoints, and permissions remain unchanged.
const DEPT_LABELS: Record<string, string> = {
  lidar: 'LiDAR', mobile_mapping: 'Mobile Mapping', ortho: 'Ortho',
  laser_scanning: 'Laser Scanning', civil: 'Civil', bim: 'BIM', gis: 'GIS', drone: 'Drone / UAV',
}
const STAGE_LABELS: Record<string, string> = {
  import: 'Import', production: 'Production', production_rework: 'Production Rework',
  qc: 'QC', qa: 'QA', dxf: 'DXF', inspection: 'Inspection',
  delivery: 'Delivery', delivery_ready: 'Delivery Ready', delivered: 'Delivered', upload: 'Upload',
}
const fmtStage = (v?: string | null) => v ? (STAGE_LABELS[v] || v.replace(/_/g, ' ').toUpperCase()) : 'Not started'
const fmtNumber = (v?: number | null) => v == null ? '—' : Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 })
const pct = (v?: number | null) => {
  const number = Number(v ?? 0)
  return Number.isFinite(number) ? Math.max(0, Math.min(100, number)) : 0
}

type ProgressTone = 'red' | 'orange' | 'yellow' | 'green'
const progressTone = (value: number): ProgressTone =>
  value < 30 ? 'red' : value < 50 ? 'orange' : value < 70 ? 'yellow' : 'green'
const PROGRESS_GUIDE: { tone: ProgressTone; range: string; meaning: string }[] = [
  { tone: 'red', range: '0–<30%', meaning: 'Low progress' },
  { tone: 'orange', range: '30–<50%', meaning: 'Below average' },
  { tone: 'yellow', range: '50–<70%', meaning: 'Moderate progress' },
  { tone: 'green', range: '70–100%', meaning: 'Good progress' },
]

// Department colors identify departments; progress colors always identify completion percentage.
const DEPT_VISUALS: Record<string, { Icon: LucideIcon; className: string }> = {
  lidar: { Icon: RadioTower, className: 'lidar' },
  mobile_mapping: { Icon: MapPin, className: 'mobile-mapping' },
  ortho: { Icon: Layers3, className: 'ortho' },
  laser_scanning: { Icon: ScanLine, className: 'laser-scanning' },
  civil: { Icon: HardHat, className: 'civil' },
  bim: { Icon: Boxes, className: 'bim' },
  gis: { Icon: Map, className: 'gis' },
  drone: { Icon: Plane, className: 'drone' },
}
function departmentVisual(code: string) {
  const normalized = (code || '').trim().toLowerCase().replace(/[\s-]+/g, '_')
  return DEPT_VISUALS[normalized] || { Icon: ClipboardList, className: 'default' }
}

function ProgressGuide() {
  return <section className="bdpt-guide" aria-label="Progress color guide">
    <div className="bdpt-guide-heading"><strong>Project Progress Guide</strong><span>Colors indicate completion percentage</span></div>
    <div className="bdpt-guide-items">{PROGRESS_GUIDE.map(({ tone, range, meaning }) =>
      <div className={`bdpt-guide-item bdpt-guide-item--${tone}`} key={tone}>
        <span className="bdpt-guide-swatch" aria-hidden="true" />
        <span><strong>{range}</strong><small>{meaning}</small></span>
      </div>
    )}</div>
  </section>
}

function Progress({ value, label }: { value?: number | null; label: string }) {
  const amount = pct(value)
  const tone = progressTone(amount)
  const description = PROGRESS_GUIDE.find((item) => item.tone === tone)?.meaning || 'Progress'
  return <div className={`bdpt-progress bdpt-progress--${tone}`} title={`${label}: ${fmtNumber(amount)}% · ${description}`}>
    <div className="bdpt-progress-track" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={amount} data-zero={amount === 0}>
      <span style={{ width: `${amount}%` }} />
    </div>
    <strong>{fmtNumber(amount)}%</strong>
  </div>
}

function FileCount({ row, kind }: { row: PackageTrackingRow; kind: 'qc' | 'qa' | 'production' | 'delivered' }) {
  const total = row.files_expected ?? 0
  const value = kind === 'qc' ? row.files_qc_passed : kind === 'qa' ? row.files_qa_passed
    : kind === 'production' ? row.files_production_done : row.files_delivered
  return <span>{total > 0 ? `${value ?? 0} / ${total}` : '—'}</span>
}

function ProjectDetails({ project }: { project: ProjectTrackingRow }) {
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [isOpen, setIsOpen] = useState(true)
  const dept = departmentVisual(project.department_code)
  const DeptIcon = dept.Icon
  const tableId = `bdpt-project-table-${project.project_id}`
  return <section className="operations-panel bdpt-project" aria-label={`Tracking for project ${project.project_code}`}>
    <header className="bdpt-project-head">
      <div className="bdpt-project-identity">
        <div className={`bdpt-dept-icon bdpt-dept-icon--${dept.className}`} aria-hidden="true"><DeptIcon size={23} strokeWidth={2} /></div>
        <div>
          <span className="operations-kicker">{DEPT_LABELS[project.department_code] || project.department_code}</span>
          <h2>{project.project_code}</h2>
          <p>Manager: {project.project_manager?.full_name || 'Not assigned'} · {project.packages} work packages · Workflow: {fmtStage(project.workflow_status)}</p>
        </div>
      </div>
      <div className="bdpt-project-head-actions">
        <div className="bdpt-project-progress">
          <span>Production</span><Progress label={`Project ${project.project_code} production`} value={project.production_progress_percent} />
          <span>Workflow</span><Progress label={`Project ${project.project_code} workflow`} value={project.workflow_progress_percent} />
        </div>
        <button type="button" className="bdpt-collapse" aria-label={`${isOpen ? 'Collapse' : 'Expand'} project ${project.project_code}`} aria-expanded={isOpen} aria-controls={tableId}
          title={`${isOpen ? 'Collapse' : 'Expand'} project details`} onClick={() => setIsOpen((v) => !v)}>
          <ChevronDown size={19} className={isOpen ? 'bdpt-chevron-open' : ''} />
        </button>
      </div>
    </header>
    <div id={tableId} hidden={!isOpen}>
    {!project.package_rows.length ? (
      <div className="operations-empty">No work packages have been allocated to this project yet.</div>
    ) : (
      <div className="bdpt-table-scroll"><table className="operations-table bdpt-table">
        <thead><tr>
          <th>Lot / Code</th><th>Area</th><th>Target</th><th>Actual</th><th>Current Stage</th>
          <th>Production</th><th>QC files</th><th>QA files</th><th>Delivered</th><th>Workflow</th><th>Rework</th><th>Details</th>
        </tr></thead>
        <tbody>{project.package_rows.map((pkg) => <Fragment key={pkg.work_package_id}>
          <tr key={`row-${pkg.work_package_id}`}>
            <td><small>{pkg.lot_batch || '—'}</small><strong className="bdpt-code">{pkg.package_code}</strong></td>
            <td>{pkg.area_name || '—'}</td>
            <td>{fmtNumber(pkg.target_quantity)} {pkg.unit || ''}</td>
            <td>{fmtNumber(pkg.actual_quantity)} {pkg.unit || ''}</td>
            <td><span className="operations-status">{fmtStage(pkg.current_stage)}</span></td>
            <td><Progress label="Production" value={pkg.production_progress_percent} /></td>
            <td><FileCount row={pkg} kind="qc" /></td>
            <td><FileCount row={pkg} kind="qa" /></td>
            <td><FileCount row={pkg} kind="delivered" /></td>
            <td><Progress label="Workflow" value={pkg.workflow_progress_percent} /></td>
            <td>{pkg.rework || ['rework', 'rejected'].includes(pkg.stage_statuses?.qc ?? '') || ['rework', 'rejected'].includes(pkg.stage_statuses?.qa ?? '') ? <span className="operations-status warning">Rework</span> : '—'}</td>
            <td><button type="button" className="operations-button secondary" aria-expanded={expandedId === pkg.work_package_id} onClick={() => setExpandedId((v) => v === pkg.work_package_id ? null : pkg.work_package_id)}>
              <Eye size={14} /> {expandedId === pkg.work_package_id ? 'Hide' : 'View'}
            </button></td>
          </tr>
          {expandedId === pkg.work_package_id && <tr key={`details-${pkg.work_package_id}`}><td colSpan={12}>
            <div className="bdpt-details">
              <strong>{pkg.package_code} · {pkg.area_name || 'Work package'} · Stage breakdown</strong>
              <div className="bdpt-stage-list">{pkg.applicable_stages.map((stage) => <div key={stage}>
                <span>{fmtStage(stage)}</span><strong>{fmtStage(pkg.stage_statuses?.[stage])}</strong>
              </div>)}</div>
              <div className="bdpt-file-counts">
                <span>Production files: <FileCount row={pkg} kind="production" /></span>
                <span>QC passed: <FileCount row={pkg} kind="qc" /></span>
                <span>QA passed: <FileCount row={pkg} kind="qa" /></span>
                <span>Delivered: <FileCount row={pkg} kind="delivered" /></span>
              </div>
              {pkg.remarks && <p>Remarks: {pkg.remarks}</p>}
              <p className="bdpt-muted">Read-only view. QC/QA activities, assignments, and file-level actions remain available only in authorized department workflows.</p>
            </div>
          </td></tr>}
        </Fragment>)}</tbody>
      </table></div>
    )}
    </div>
  </section>
}

export function BDProjectTrackingPage() {
  const [data, setData] = useState<TrackingSummary | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [department, setDepartment] = useState('all')
  const [projectId, setProjectId] = useState('all')
  const [query, setQuery] = useState('')

  function load() {
    setError('')
    setLoading(true)
    void apiFetch<TrackingSummary>('/operations/workflow/bd/project-tracking')
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : 'Unable to load BD project tracking'))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const projects = useMemo(() => data?.projects ?? [], [data])
  const departments = useMemo(() => [...new Set(projects.map((p) => p.department_code))].sort(), [projects])
  const visible = useMemo(() => projects.filter((p) => {
    if (department !== 'all' && p.department_code !== department) return false
    if (projectId !== 'all' && String(p.project_id) !== projectId) return false
    const term = query.trim().toLowerCase()
    return !term || p.project_code.toLowerCase().includes(term) ||
      (DEPT_LABELS[p.department_code] || p.department_code).toLowerCase().includes(term) ||
      p.package_rows.some((r) => [r.package_code, r.area_name, r.lot_batch || ''].some((v) => v.toLowerCase().includes(term)))
  }), [projects, department, projectId, query])
  const totals = useMemo(() => ({
    packages: visible.reduce((n, p) => n + p.packages, 0),
    rework: visible.reduce((n, p) => n + p.rework_packages, 0),
    blocked: visible.reduce((n, p) => n + p.blocked_packages, 0),
    production: visible.length ? visible.reduce((n, p) => n + p.production_progress_percent, 0) / visible.length : 0,
    workflow: visible.length ? visible.reduce((n, p) => n + p.workflow_progress_percent, 0) / visible.length : 0,
  }), [visible])

  return <div className="operations-page bdpt-page">
    <DashboardHeader variant="ops" icon={ClipboardList} eyebrow="BUSINESS DEVELOPMENT · READ-ONLY PROJECT STATUS"
      title="Project Tracking"
      description="Live status from the same project records used by LiDAR, Mobile Mapping and Ortho. Review progress, QC, QA, rework and delivery without changing operational data."
      actions={<><Link className="operations-button secondary" to="/bd/projects">Project Management</Link>
        <button type="button" className="operations-button secondary" disabled={loading} onClick={load}><RefreshCcw size={16} /> Refresh</button></>}
      summary={<>
        <StatCard icon={ClipboardList} label="Projects" value={visible.length} note="Visible to BD" />
        <StatCard icon={Workflow} label="Work Packages" value={totals.packages} tone="blue" note={`${totals.rework} in rework · ${totals.blocked} blocked`} />
        <StatCard icon={BarChart3} label="Production %" value={Number(totals.production.toFixed(2))} tone="purple" note="Average across visible projects" />
        <StatCard icon={BarChart3} label="Workflow %" value={Number(totals.workflow.toFixed(2))} tone="green" note="Average across visible projects" />
      </>}
    />
    <ProgressGuide />
    <div className="bdpt-readonly"><Eye size={16} /><strong>BD VIEW ONLY</strong> — You can see live status but cannot Start, Complete, Rework, or edit project operations here.</div>
    {error && <div className="operations-alert error" role="alert">{error} <button className="operations-button secondary" onClick={load}>Retry</button></div>}
    <section className="operations-panel"><div className="bdpt-filters">
      <label className="operations-field"><span>Search project / area / code</span><div className="bdpt-search"><Search size={15} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Project ID, lot, area, code…" /></div></label>
      <label className="operations-field"><span>Department</span><select value={department} onChange={(e) => { setDepartment(e.target.value); setProjectId('all') }}>
        <option value="all">All departments</option>{departments.map((d) => <option key={d} value={d}>{DEPT_LABELS[d] || d}</option>)}
      </select></label>
      <label className="operations-field"><span>Project</span><select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
        <option value="all">All projects</option>{projects.filter((p) => department === 'all' || p.department_code === department).map((p) => <option key={p.project_id} value={p.project_id}>{p.project_code}</option>)}
      </select></label>
    </div></section>
    {loading && <section className="operations-panel"><div className="operations-empty">Loading live project tracking…</div></section>}
    {!loading && !error && visible.length === 0 && <section className="operations-panel"><div className="operations-empty">No matching projects with tracking records. Try clearing the filters; projects appear after their workflow record exists.</div></section>}
    {!loading && visible.map((p) => <ProjectDetails project={p} key={p.project_id} />)}
  </div>
}
