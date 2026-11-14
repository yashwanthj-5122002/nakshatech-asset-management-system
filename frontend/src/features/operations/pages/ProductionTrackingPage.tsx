import { BarChart3, CalendarDays, ChevronDown, ChevronLeft, ChevronRight, Download, FileSpreadsheet, RefreshCcw, Workflow } from 'lucide-react'
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

type EmployeeEntry = {
  id: string
  date: string | null
  stage: string
  work: string
  package: string | null
  quantity: number | null
  unit: string | null
  files: number
  status: string
  duration_seconds: number | null
  remarks: string | null
}
type EmployeeProject = {
  project_id: number
  project_code: string
  department_code: string | null
  work_days: number
  completed_files: number
  totals_by_unit: { unit: string; quantity: number }[]
  history: EmployeeEntry[]
}
type EmployeeTrackingSummary = Omit<TrackingSummary, 'viewer_mode'> & {
  viewer_mode: 'employee' | TrackingSummary['viewer_mode']
  employee_projects?: EmployeeProject[]
}

type PersonalActivity = EmployeeEntry & { project_code: string; department_code: string | null }

// Display recorded employee activity durations without recalculating or inventing time.
function formatRecordedDuration(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds) || seconds < 0) return 'â€”'
  const total = Math.floor(seconds)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const remaining = total % 60
  return [hours, minutes, remaining].map((part) => String(part).padStart(2, '0')).join(':')
}

// Employee-only compact tracking: work dates are derived from employee-scoped
// tracking history already returned by the backend. Daily Activity is untouched.
function CompactEmployeeTracking({ projects, projectId, onProjectChange, refresh, error }: {
  projects: EmployeeProject[]
  projectId: number | null
  onProjectChange: (id: string) => void
  refresh: () => void
  error: string
}) {
  const allActivities = useMemo(() => projects.flatMap((project) => project.history.map((entry) => ({
    ...entry, project_code: project.project_code, department_code: project.department_code,
  }))).sort((a, b) => (b.date || '').localeCompare(a.date || '') || a.id.localeCompare(b.id)), [projects])
  const activityDates = useMemo(() => new Set(allActivities.map((entry) => entry.date?.slice(0, 10)).filter((date): date is string => !!date && /^\d{4}-\d{2}-\d{2}$/.test(date))), [allActivities])
  const latestDate = [...activityDates].sort().at(-1) ?? new Date().toLocaleDateString('en-CA')
  const [selectedDate, setSelectedDate] = useState(() => latestDate)
  const [month, setMonth] = useState(() => latestDate.slice(0, 7))
  const [calendarOpen, setCalendarOpen] = useState(false)
  const [showAllDay, setShowAllDay] = useState(false)
  const [showProjectHistory, setShowProjectHistory] = useState(false)
  const [historyPage, setHistoryPage] = useState(0)
  const chosenProject = projects.find((p) => p.project_id === projectId) ?? projects[0]
  const selectedActivities = allActivities.filter((entry) => entry.date?.slice(0, 10) === selectedDate)
  const projectHistory = chosenProject?.history ?? []
  useEffect(() => {
    if (!showProjectHistory) return
    const onEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setShowProjectHistory(false)
    }
    document.addEventListener('keydown', onEscape)
    return () => document.removeEventListener('keydown', onEscape)
  }, [showProjectHistory])
  const pageSize = 5
  const pageCount = Math.max(1, Math.ceil(projectHistory.length / pageSize))
  const currentPage = Math.min(historyPage, pageCount - 1)
  const [yearText, monthText] = month.split('-')
  const year = Number(yearText)
  const monthIndex = Number(monthText) - 1
  const firstWeekday = new Date(year, monthIndex, 1).getDay()
  const daysInMonth = new Date(year, monthIndex + 1, 0).getDate()
  const cells = Array.from({ length: Math.ceil((firstWeekday + daysInMonth) / 7) * 7 }, (_, i) => i - firstWeekday + 1)
  const displayDate = (date: string) => new Date(`${date}T12:00:00`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
  const dayRecords = showAllDay ? selectedActivities : selectedActivities.slice(0, 5)
  function moveMonth(offset: number) {
    const next = new Date(year, monthIndex + offset, 1)
    setMonth(`${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}`)
  }
  function chooseDate(date: string) {
    setSelectedDate(date)
    setMonth(date.slice(0, 7))
    setCalendarOpen(false)
    setShowAllDay(false)
  }
  const statStyle = { border: '1px solid #d7e4f5', borderRadius: 12, padding: '11px 14px', background: '#f7faff', minWidth: 0 } as const
  const buttonStyle = { border: '1px solid #c7d9f2', background: 'white', borderRadius: 8, padding: '7px 12px', cursor: 'pointer', color: '#174579', fontWeight: 650 } as const
  const tableWrap = { overflowX: 'auto' } as const
  const tdStyle = { padding: '9px 10px', borderBottom: '1px solid #e9eef6', verticalAlign: 'top' } as const
  const thStyle = { ...tdStyle, fontSize: 11, textTransform: 'uppercase' as const, color: '#315077', background: '#f2f6fc' }
  return (
    <div className="operations-page" style={{ paddingBottom: 16 }}>
      <section className="operations-panel" style={{ padding: '16px 18px', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 24, lineHeight: 1.25, color: '#102b53' }}>Production Tracking</h1>
            <p style={{ margin: '3px 0 0', color: '#5c7291', fontSize: 13 }}>My projects, daily work and history</p>
          </div>
          <button type="button" className="operations-button secondary" onClick={refresh}><RefreshCcw size={15} /> Refresh</button>
        </div>
        {error && <div className="operations-alert error" style={{ marginTop: 10 }}>{error}</div>}
        {projects.length ? <>
          <label style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 13, flexWrap: 'wrap', fontWeight: 700, color: '#173760' }}>
            My worked project
            <select aria-label="My worked project" value={chosenProject?.project_id ?? ''} onChange={(e) => { onProjectChange(e.target.value); setHistoryPage(0); setShowProjectHistory(true); setCalendarOpen(false) }} style={{ flex: '1 1 250px', maxWidth: 620, border: '1px solid #b6d0f0', borderRadius: 8, padding: '9px 12px', font: 'inherit', background: 'white', color: '#173760' }}>
              {projects.map((project) => <option key={project.project_id} value={project.project_id}>{project.project_code} — {project.department_code || 'Department'}</option>)}
            </select>
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(165px, 1fr))', gap: 10, marginTop: 12 }}>
            <div style={statStyle}><div style={{ color: '#617994', fontSize: 12 }}>Worked projects</div><strong style={{ fontSize: 22 }}>{projects.length}</strong></div>
            <div style={statStyle}><div style={{ color: '#617994', fontSize: 12 }}>Work days · selected project</div><strong style={{ fontSize: 22 }}>{chosenProject?.work_days ?? 0}</strong></div>
            <div style={statStyle}><div style={{ color: '#617994', fontSize: 12 }}>Completed files · selected project</div><strong style={{ fontSize: 22 }}>{chosenProject?.completed_files ?? 0}</strong></div>
            <div style={statStyle}><div style={{ color: '#617994', fontSize: 12 }}>My recorded quantities</div><strong style={{ fontSize: 16 }}>{chosenProject?.totals_by_unit.length ? chosenProject.totals_by_unit.map((total) => `${total.quantity.toLocaleString('en-IN')} ${total.unit}`).join(' · ') : '—'}</strong></div>
          </div>
        </> : <p style={{ marginBottom: 0 }}>No recorded work yet. Your projects will appear after activity is recorded.</p>}
      </section>
      {projects.length > 0 && <section className="operations-panel" style={{ padding: '15px 18px', marginBottom: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10, marginBottom: 12 }}>
          <div><h2 style={{ margin: 0, fontSize: 18 }}>My Work History</h2><p style={{ margin: '3px 0 0', fontSize: 12, color: '#64748b' }}>Choose a date to view your recorded work across all projects.</p></div>
          <div style={{ position: 'relative', width: 'min(100%, 235px)' }}>
            <button type="button" aria-label="Choose work date" aria-expanded={calendarOpen} onClick={() => setCalendarOpen((current) => !current)} style={{ ...buttonStyle, width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}><span><CalendarDays size={16} style={{ verticalAlign: 'middle', marginRight: 8 }} />{displayDate(selectedDate)}</span><ChevronDown size={16} /></button>
            {calendarOpen && <div role="dialog" aria-label="Work calendar" style={{ position: 'absolute', right: 0, top: 'calc(100% + 5px)', zIndex: 40, background: 'white', border: '1px solid #c8d9ee', borderRadius: 12, padding: 12, boxShadow: '0 12px 34px #0d30532b', width: 290, maxWidth: 'calc(100vw - 45px)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 9 }}><button type="button" aria-label="Previous month" onClick={() => moveMonth(-1)} style={buttonStyle}><ChevronLeft size={15} /></button><strong>{new Date(year, monthIndex, 1).toLocaleDateString('en-IN', { month: 'long', year: 'numeric' })}</strong><button type="button" aria-label="Next month" onClick={() => moveMonth(1)} style={buttonStyle}><ChevronRight size={15} /></button></div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, minmax(0, 1fr))', gap: 3, textAlign: 'center' }}>
                {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((label, i) => <span key={i} style={{ fontSize: 11, color: '#64748b' }}>{label}</span>)}
                {cells.map((day, i) => day < 1 || day > daysInMonth ? <span key={`blank-${i}`} /> : (() => {
                  const date = `${month}-${String(day).padStart(2, '0')}`
                  const hasWork = activityDates.has(date)
                  const selected = selectedDate === date
                  return <button key={date} type="button" aria-label={`${date}${hasWork ? ' - work recorded' : ''}`} aria-pressed={selected} onClick={() => chooseDate(date)} style={{ border: selected ? '2px solid #2563eb' : '1px solid #deebf6', borderRadius: 7, height: 31, cursor: 'pointer', background: selected ? '#dbeafe' : hasWork ? '#dcfce7' : '#f8fafc', color: selected ? '#1d4ed8' : hasWork ? '#166534' : '#475569', fontWeight: hasWork ? 700 : 400, padding: 0 }}>{day}</button>
                })())}
              </div>
              <p style={{ margin: '10px 0 0', fontSize: 11, color: '#64748b' }}>Green = recorded work · Blue = selected date</p>
              <button type="button" style={{ ...buttonStyle, marginTop: 8, width: '100%' }} onClick={() => setCalendarOpen(false)}>Close calendar</button>
            </div>}
          </div>
        </div>
        <div style={{ background: '#edf5ff', border: '1px solid #d7e7fc', borderRadius: 10, padding: '9px 12px', marginBottom: 10, display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
          <strong style={{ color: '#163967' }}>{displayDate(selectedDate)}</strong>
          <span style={{ fontSize: 13, color: '#31567f' }}>{selectedActivities.length} {selectedActivities.length === 1 ? 'activity' : 'activities'} · {new Set(selectedActivities.map((row) => row.project_code)).size} projects</span>
        </div>
        {selectedActivities.length ? <>
          <div style={tableWrap}><table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 640, fontSize: 12 }}><thead><tr><th style={thStyle}>Project / Dept</th><th style={thStyle}>Work file / Area</th><th style={thStyle}>Stage</th><th style={thStyle}>Quantity</th><th style={thStyle}>Files</th><th style={thStyle}>Time Taken</th><th style={thStyle}>Status</th></tr></thead><tbody>
            {dayRecords.map((entry) => <tr key={`${entry.project_code}-${entry.id}`}><td style={tdStyle}><strong>{entry.project_code}</strong><div>{entry.department_code || '—'}</div></td><td style={tdStyle}>{entry.work}{entry.remarks ? <div style={{ color: '#64748b', fontSize: 11 }}>{entry.remarks}</div> : null}</td><td style={tdStyle}>{entry.stage}</td><td style={tdStyle}>{entry.quantity === null ? '—' : `${entry.quantity.toLocaleString('en-IN')} ${entry.unit || ''}`}</td><td style={tdStyle}>{entry.files}</td><td style={tdStyle}>{formatRecordedDuration(entry.duration_seconds)}</td><td style={tdStyle}>{entry.status.replace(/_/g, ' ')}</td></tr>)}
          </tbody></table></div>
          {selectedActivities.length > 5 && <button type="button" style={{ ...buttonStyle, marginTop: 10 }} onClick={() => setShowAllDay((current) => !current)}>{showAllDay ? 'Show fewer activities' : `View all ${selectedActivities.length} activities for this date`}</button>}
        </> : <p style={{ fontSize: 13, color: '#64748b' }}>No work recorded on this date.</p>}
        <p style={{ margin: '10px 0 0', fontSize: 12, color: '#617994' }}>To review the full history of a project, select it from My worked project above.</p>

      </section>}
      {showProjectHistory && chosenProject && (
        <div
          role="presentation"
          onMouseDown={(event) => { if (event.target === event.currentTarget) setShowProjectHistory(false) }}
          style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(8, 24, 47, 0.57)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-label={`Project ${chosenProject.project_code} personal work history`}
            className="operations-panel"
            style={{ width: 'min(940px, 100%)', maxHeight: 'min(82vh, 780px)', display: 'flex', flexDirection: 'column', padding: 0, overflow: 'hidden', boxShadow: '0 20px 70px rgba(6, 28, 60, 0.3)' }}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 14, padding: '17px 20px', borderBottom: '1px solid #e2eaf5' }}>
              <div>
                <h2 style={{ margin: 0, fontSize: 19, color: '#102b53' }}>Project {chosenProject.project_code} · My Work History</h2>
                <p style={{ margin: '5px 0 0', fontSize: 12, color: '#617994' }}>{chosenProject.department_code || 'Department'} · {chosenProject.work_days} work days · {chosenProject.completed_files} completed files</p>
              </div>
              <button type="button" aria-label="Close project history" onClick={() => setShowProjectHistory(false)} style={{ ...buttonStyle, padding: '5px 11px', fontSize: 19, lineHeight: 1.2 }}>×</button>
            </div>
            <div style={{ overflowY: 'auto', minHeight: 0, padding: '16px 20px 20px' }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 14 }}>
                <div style={statStyle}><div style={{ fontSize: 12, color: '#617994' }}>Recorded work</div><strong>{chosenProject.totals_by_unit.length ? chosenProject.totals_by_unit.map((total) => `${total.quantity.toLocaleString('en-IN')} ${total.unit}`).join(' · ') : '—'}</strong></div>
                <div style={statStyle}><div style={{ fontSize: 12, color: '#617994' }}>History records</div><strong>{projectHistory.length}</strong></div>
              </div>
              {projectHistory.length ? <>
                <div style={tableWrap}>
                  <table style={{ width: '100%', minWidth: 620, borderCollapse: 'collapse', fontSize: 12 }}>
                    <thead><tr><th style={thStyle}>Date</th><th style={thStyle}>Work file / Area</th><th style={thStyle}>Stage</th><th style={thStyle}>Quantity</th><th style={thStyle}>Files</th><th style={thStyle}>Time Taken</th><th style={thStyle}>Status</th></tr></thead>
                    <tbody>{projectHistory.slice(currentPage * pageSize, (currentPage + 1) * pageSize).map((entry) => <tr key={entry.id}><td style={tdStyle}>{entry.date || '—'}</td><td style={tdStyle}>{entry.work}{entry.remarks && <div style={{ color: '#64748b', fontSize: 11 }}>{entry.remarks}</div>}</td><td style={tdStyle}>{entry.stage}</td><td style={tdStyle}>{entry.quantity === null ? '—' : `${entry.quantity.toLocaleString('en-IN')} ${entry.unit || ''}`}</td><td style={tdStyle}>{entry.files}</td><td style={tdStyle}>{formatRecordedDuration(entry.duration_seconds)}</td><td style={tdStyle}>{entry.status.replace(/_/g, ' ')}</td></tr>)}</tbody>
                  </table>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', flexWrap: 'wrap', gap: 9, marginTop: 12 }}>
                  <span style={{ fontSize: 12, color: '#617994', marginRight: 'auto' }}>{projectHistory.length} records · {pageSize} per page</span>
                  <button type="button" style={buttonStyle} disabled={currentPage === 0} onClick={() => setHistoryPage((p) => Math.max(0, p - 1))}>Previous</button>
                  <span style={{ fontSize: 12 }}>{currentPage + 1} / {pageCount}</span>
                  <button type="button" style={buttonStyle} disabled={currentPage >= pageCount - 1} onClick={() => setHistoryPage((p) => Math.min(pageCount - 1, p + 1))}>Next</button>
                </div>
              </> : <p style={{ fontSize: 13, color: '#64748b' }}>No recorded history for this project.</p>}
            </div>
          </section>
        </div>
      )}
    </div>
  )
}

export function ProductionTrackingPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedProjectId = Number(searchParams.get('project') || 0) || null
  const [data, setData] = useState<EmployeeTrackingSummary | null>(null)
  const [error, setError] = useState('')
  const [reportType, setReportType] = useState('project_workbook')
  const [exporting, setExporting] = useState(false)

  function load() {
    setError('')
    void apiFetch<EmployeeTrackingSummary>('/operations/workflow/production-tracking')
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : 'Unable to load production tracking'))
  }
  useEffect(load, [])

  const isEmployee = data?.viewer_mode === 'employee'
  const employeeProjects = useMemo(() => data?.employee_projects ?? [], [data])
  const projects = useMemo(() => data?.projects ?? [], [data])
  const selectableProjects = isEmployee ? employeeProjects : projects
  const selectedProjectId = requestedProjectId && selectableProjects.some((p) => p.project_id === requestedProjectId)
    ? requestedProjectId
    : null
  const chosenEmployeeProject = isEmployee
    ? employeeProjects.find((p) => p.project_id === (selectedProjectId ?? employeeProjects[0]?.project_id))
    : undefined
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
    if (isEmployee) {
      setError('Employee tracking is read-only. Use your daily activity records to review your work.')
      return
    }
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

  if (isEmployee && data) {
    return <CompactEmployeeTracking
      projects={employeeProjects}
      projectId={selectedProjectId}
      onProjectChange={(value) => {
        const next = new URLSearchParams(searchParams)
        if (value) next.set('project', value)
        else next.delete('project')
        setSearchParams(next, { replace: true })
      }}
      refresh={load}
      error={error}
    />
  }

  return (
    <div className="operations-page">
      <DashboardHeader
        variant="ops"
        icon={Workflow}
        eyebrow="V8.1 · DAILY ACTIVITY · SHARED WORK-PACKAGE RECORD"
        title="Production Tracking"
        description={
          isEmployee
            ? 'Your own project work, original quantities and dated history from existing Daily Activity records.'
            : readOnly
            ? 'Read-only consolidated production, QC, QA and delivery status across projects. One row per area/code work package with Production % and Workflow % kept separate.'
            : 'One row per area/code work package: target and actual quantity with unit, stage statuses, Production % and Workflow %. Filter, open a row for full history, or export the Daily Activity workbook.'
        }
        actions={
          <>
            <button className="operations-button secondary" onClick={load}><RefreshCcw size={16} /> Refresh</button>
            {!isEmployee && <button className="operations-button" disabled={exporting} onClick={exportReport}>
              <Download size={15} /> {exporting ? 'Exporting…' : 'Export Excel'}
            </button>}
          </>
        }
        summary={
          isEmployee ? <>
            <StatCard icon={BarChart3} label="Worked Projects" value={employeeProjects.length} note="My recorded project history" />
            <StatCard icon={Workflow} label="Work Days" value={chosenEmployeeProject?.work_days ?? 0} tone="blue" note="Selected project" />
            <StatCard icon={FileSpreadsheet} label="Completed Files" value={chosenEmployeeProject?.completed_files ?? 0} tone="green" note="Recorded production completions" />
          </> : <>
            <StatCard icon={BarChart3} label="Projects" value={totals.projects} note="Visible to your role" />
            <StatCard icon={Workflow} label="Work Packages" value={totals.packages} tone="blue" note={`${totals.rework} in rework · ${totals.blocked} blocked`} />
            <StatCard icon={FileSpreadsheet} label="Production %" value={totals.production} tone="purple" note="Quantity-weighted, per UOM group" />
            <StatCard icon={BarChart3} label="Workflow %" value={totals.workflow} tone="green" note="Completed stages / applicable stages" />
          </>
        }
      />

      {error && <div className="operations-alert error">{error}</div>}

      {selectedProjectId && !readOnly && !isEmployee && (
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
            {!isEmployee && <label className="operations-field">
              <span>Report</span>
              <select value={reportType} onChange={(e) => setReportType(e.target.value)}>
                {REPORT_TYPES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            </label>}
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
                <option value="">{isEmployee ? 'Select my project' : 'All projects'}</option>
                {selectableProjects.map((p) => <option key={p.project_id} value={p.project_id}>{p.project_code}</option>)}
              </select>
            </label>
            {!isEmployee && <button className="operations-button secondary" disabled={exporting} onClick={exportReport}>
              <Download size={15} /> Export
            </button>}
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
