import { BarChart3, Download, FileSpreadsheet, RefreshCcw, Workflow } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { StatCard } from '../../../components/StatCard'
import { apiFetch, downloadFile } from '../../../lib/api'
import { ProductionTrackingPanel, type TrackingSummary } from '../components/ProductionTrackingPanel'
import '../operations.css'

// V8.1 Daily Activity / Production Tracking: one compact ERP table over the
// shared work-package records, served by /operations/workflow/production-tracking.
// Aggregation and permission filtering happen server-side (see production_service).
const REPORT_TYPES = [
  { value: 'project_workbook', label: 'Project Workbook — AREA MASTER · FILE ACTIVITY · EMPLOYEE PRODUCTIVITY' },
  { value: 'production_detail', label: 'Production Detail (Daily Activity columns)' },
  { value: 'management_consolidated', label: 'Management Consolidated' },
  { value: 'project_progress', label: 'Project Progress' },
  { value: 'employee_production', label: 'Employee Production' },
  { value: 'pending_stages', label: 'Pending Stages' },
  { value: 'rework_quality', label: 'Rework & Quality' },
]

export function ProductionTrackingPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedProjectId = Number(searchParams.get('project') || 0) || null
  const [data, setData] = useState<TrackingSummary | null>(null)
  const [error, setError] = useState('')
  const [reportType, setReportType] = useState('project_workbook')
  const [exporting, setExporting] = useState(false)

  function load() {
    setError('')
    void apiFetch<TrackingSummary>('/operations/workflow/production-tracking')
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : 'Unable to load production tracking'))
  }
  useEffect(load, [])

  const projects = useMemo(() => data?.projects ?? [], [data])
  const selectedProjectId = requestedProjectId && projects.some((p) => p.project_id === requestedProjectId)
    ? requestedProjectId
    : null
  const visibleProjects = selectedProjectId ? projects.filter((p) => p.project_id === selectedProjectId) : projects

  const totals = useMemo(() => {
    const rows = visibleProjects
    const packages = rows.reduce((sum, p) => sum + p.packages, 0)
    const rework = rows.reduce((sum, p) => sum + p.rework_packages, 0)
    const blocked = rows.reduce((sum, p) => sum + p.blocked_packages, 0)
    const avg = (pick: (p: (typeof rows)[number]) => number) =>
      rows.length ? Math.round(rows.reduce((sum, p) => sum + pick(p), 0) / rows.length * 100) / 100 : 0
    return {
      projects: rows.length,
      packages,
      rework,
      blocked,
      production: avg((p) => p.production_progress_percent),
      workflow: avg((p) => p.workflow_progress_percent),
    }
  }, [visibleProjects])

  function exportReport() {
    if (reportType === 'project_workbook' && !selectedProjectId) {
      setError('Select ONE project first — the Project Workbook contains only that project’s records.')
      return
    }
    setExporting(true)
    setError('')
    const params = new URLSearchParams({ report: reportType })
    if (selectedProjectId) params.set('project_id', String(selectedProjectId))
    downloadFile(
      `/operations/workflow/production-tracking/export.xlsx?${params.toString()}`,
      `production-tracking-${reportType}.xlsx`,
    )
      .catch((e) => setError(e instanceof Error ? e.message : 'Export failed'))
      .finally(() => setExporting(false))
  }

  const readOnly = data?.viewer_mode === 'read_only'

  return (
    <div className="operations-page">
      <DashboardHeader
        variant="ops"
        icon={Workflow}
        eyebrow="V8.1 · DAILY ACTIVITY · SHARED WORK-PACKAGE RECORD"
        title="Production Tracking"
        description={
          readOnly
            ? 'Read-only consolidated production, QC, QA and delivery status across projects. One row per area/code work package with Production % and Workflow % kept separate.'
            : 'One row per area/code work package: target and actual quantity with unit, stage statuses, Production % and Workflow %. Filter, open a row for full history, or export the Daily Activity workbook.'
        }
        actions={
          <>
            <button className="operations-button secondary" onClick={load}><RefreshCcw size={16} /> Refresh</button>
            <button className="operations-button" disabled={exporting} onClick={exportReport}>
              <Download size={15} /> {exporting ? 'Exporting…' : 'Export Excel'}
            </button>
          </>
        }
        summary={
          <>
            <StatCard icon={BarChart3} label="Projects" value={totals.projects} note="Visible to your role" />
            <StatCard icon={Workflow} label="Work Packages" value={totals.packages} tone="blue" note={`${totals.rework} in rework · ${totals.blocked} blocked`} />
            <StatCard icon={FileSpreadsheet} label="Production %" value={totals.production} tone="purple" note="Quantity-weighted, per UOM group" />
            <StatCard icon={BarChart3} label="Workflow %" value={totals.workflow} tone="green" note="Completed stages / applicable stages" />
          </>
        }
      />

      {error && <div className="operations-alert error">{error}</div>}

      {selectedProjectId && !readOnly && (
        <section className="operations-panel">
          <header>
            <div>
              <span className="operations-kicker">TEAM LEAD ? WORK FILE MASTER</span>
              <h2>Work allocation moved to Project Operations</h2>
              <p>
                The Team Lead uploads the work file master and allocates imported Lot / Code / Area /
                Files in Project Operations, where the rest of the allocation workflow already lives.
                This page stays focused on tracking, progress and reports.
              </p>
            </div>
            <Link className="operations-button" to={`/ortho?project=${selectedProjectId}`}>
              Manage Work Allocation in Project Operations
            </Link>
          </header>
        </section>
      )}

      <section className="operations-panel">
        <header>
          <div>
            <span className="operations-kicker">PRODUCTION TRACKING REGISTER</span>
            <h2>Daily Production / QC / QA / Delivery Status</h2>
            <p>
              Production % measures completed quantity against target within compatible units.
              Workflow % measures completed applicable stages against the department's stage profile.
              The two measure different things and are never combined.
            </p>
          </div>
          <div className="pt-report-box">
            <label className="operations-field">
              <span>Report</span>
              <select value={reportType} onChange={(e) => setReportType(e.target.value)}>
                {REPORT_TYPES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            </label>
            <label className="operations-field">
              <span>Project</span>
              <select
                value={selectedProjectId ?? ''}
                onChange={(e) => {
                  const next = new URLSearchParams(searchParams)
                  if (e.target.value) next.set('project', e.target.value)
                  else next.delete('project')
                  setSearchParams(next, { replace: true })
                }}
              >
                <option value="">All projects</option>
                {projects.map((p) => <option key={p.project_id} value={p.project_id}>{p.project_code}</option>)}
              </select>
            </label>
            <button className="operations-button secondary" disabled={exporting} onClick={exportReport}>
              <Download size={15} /> Export
            </button>
          </div>
        </header>

        {!data ? (
          <div className="nk-empty"><h3>Loading production tracking…</h3></div>
        ) : !projects.length ? (
          <div className="nk-empty">
            <h3>No projects visible</h3>
            <p>Production tracking rows appear once a project team and work packages exist for your role.</p>
          </div>
        ) : (
          <ProductionTrackingPanel projects={visibleProjects} viewerMode={data.viewer_mode} />
        )}
      </section>
    </div>
  )
}
