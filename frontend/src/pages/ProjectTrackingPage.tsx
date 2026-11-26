
import { useCallback, useEffect, useMemo, useState } from 'react'
import './projectTracking.css'
import './project-tracking-ui-patch.css'

// Separate READ-ONLY operational endpoint.
// Finance/Sales APIs remain untouched.
const API = '/api/management/project-tracking'

const STATE_COLORS: Record<string, string> = {
  completed: '#168764',
  working: '#428ad1',
  rework: '#d45b4c',
  pending: '#abb6c5',
  unknown: '#dfab49',
}

type Period = 'today' | 'month' | 'year' | 'custom' | 'all'

type HeatCell = {
  id: string
  label: string
  state: string
  score: number | null
  type: string
}

type Project = {
  id: number
  project_code: string
  project_name: string
  client_name: string | null
  client_code: string | null
  department: string
  department_label: string
  project_value_inr: number | null
  project_manager: string | null
  description: string | null
  status: string
  workflow_status: string | null
  start_date: string | null
  end_date: string | null
  created_at: string | null
  completed_at: string | null
  progress_percent: number | null
  progress_method: string
  file_or_section_count: number
  heatmap: HeatCell[]
  heatmap_truncated: boolean
}

type Dashboard = {
  projects: Project[]
  departments: { code: string; label: string }[]
  summary: {
    total: number
    ongoing: number
    completed: number
    delayed: number
    rework: number
    not_started: number
    average_progress: number | null
  }
  generated_at: string
  read_only: boolean
}

type Package = {
  id: number
  code: string
  name: string
  current_stage: string
  production_state: string
  qc_state: string
  qa_state: string
  target_hours: number | null
  target_date: string | null
  team_lead: string | null
  production_employee: string | null
  qc_employee: string | null
  qa_employee: string | null
  delivered_at: string | null
  rework_source: string | null
}

type Member = {
  name: string | null
  role: string
  active: boolean
}

type History = {
  action: string
  status: string
  comments: string | null
  at: string | null
  actor: string | null
}

type Detail = {
  project: Project
  members: Member[]
  packages: Package[]
  items_total: number
  workflow_history: History[]
}

type WorkItem = {
  id: number
  name: string
  code: string
  status: string
  state: string
  progress_percent: number | null
  work_package_id: number
  production_employee: string | null
  qc_employee: string | null
  qa_employee: string | null
  production_target_date: string | null
  qc_target_date: string | null
  qa_target_date: string | null
  planned_quantity: number | null
  planned_unit: string | null
  created_at: string | null
}

type ItemPage = {
  total: number
  offset: number
  limit: number
  items: WorkItem[]
}

type Activity = {
  item_id: number
  stage: string
  status: string
  started_at: string | null
  ended_at: string | null
  at: string | null
  employee: string | null
  remarks: string | null
  delay_reason: string | null
  duration_seconds: number | null
  attempt_type: string | null
  attempt_number: number | null
}

type ActivityPage = {
  total: number
  offset: number
  limit: number
  activities: Activity[]
}

// ---------------------------------------------------------
// API helpers
// ---------------------------------------------------------

function authHeaders(): HeadersInit {
  const token =
    localStorage.getItem('asset_token') ||
    sessionStorage.getItem('asset_token')

  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function getJSON<T>(
  path: string,
  signal?: AbortSignal
): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    credentials: 'include',
    headers: authHeaders(),
    cache: 'no-store',
    signal,
  })

  if (response.status === 403) {
    throw new Error(
      'Project Tracking is available only to Vinod and Chethan management accounts.'
    )
  }

  if (response.status === 401) {
    throw new Error(
      'Please sign in to the Management account again.'
    )
  }

  if (!response.ok) {
    throw new Error(
      `Could not load project data (HTTP ${response.status}).`
    )
  }

  return response.json() as Promise<T>
}

function ymd(d: Date): string {
  return (
    `${d.getFullYear()}-` +
    `${String(d.getMonth() + 1).padStart(2, '0')}-` +
    `${String(d.getDate()).padStart(2, '0')}`
  )
}

function displayDate(
  value: string | null | undefined
): string {
  return value ? value.slice(0, 10) : 'Not recorded'
}

function pretty(
  value: string | null | undefined
): string {
  return value
    ? value
        .replace(/_/g, ' ')
        .replace(/\b\w/g, c => c.toUpperCase())
    : 'Not recorded'
}

// NEW: Format existing project value without inventing amounts.
function formatProjectValue(
  value: number | null | undefined
): string {
  if (value === null || value === undefined) {
    return 'Not available'
  }

  if (!Number.isFinite(value)) {
    return 'Not available'
  }

  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(value)
}

// ---------------------------------------------------------
// Progress
// ---------------------------------------------------------

function Progress({ project }: { project: Project }) {
  const val = project.progress_percent

  return (
    <div
      className="ptm-progress"
      aria-label={
        val === null
          ? 'Progress not yet tracked'
          : `Project ${val}% complete`
      }
    >
      <div className="ptm-progress-head">
        <strong>
          {val === null ? 'Not tracked' : `${val}%`}
        </strong>
        <small>{project.status}</small>
      </div>

      <div
        className="ptm-progress-track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={val ?? undefined}
      >
        {val !== null && (
          <div
            className="ptm-progress-fill"
            style={{
              width: `${Math.max(0, Math.min(100, val))}%`,
              background:
                val === 100
                  ? STATE_COLORS.completed
                  : '#428ad1',
            }}
          />
        )}
      </div>

      <small className="ptm-progress-note">
        {project.progress_method ===
        'software_milestones_not_connected'
          ? 'Software milestone data not yet connected'
          : project.progress_method ===
              'stage_weighted_from_work_records'
            ? 'Estimated from recorded workflow stages'
            : 'No completed work records available'}
      </small>
    </div>
  )
}

// ---------------------------------------------------------
// File / section heatmap
// ---------------------------------------------------------

function Heatmap({
  project,
  onSelect,
}: {
  project: Project
  onSelect: (id?: string) => void
}) {
  if (
    project.department === 'software' ||
    project.department === 'software_team' ||
    project.department === 'software_development'
  ) {
    return null
  }

  if (project.heatmap.length === 0) {
    return (
      <small className="ptm-muted">
        No files or survey sections recorded.
      </small>
    )
  }

  return (
    <div
      className="ptm-heatmap"
      aria-label="File and survey section statuses"
    >
      {project.heatmap.map(cell => (
        <button
          type="button"
          key={cell.id}
          title={
            `${cell.label}: ${pretty(cell.state)}` +
            (cell.score === null
              ? ''
              : ` (${cell.score}% stage estimate)`)
          }
          aria-label={`View ${cell.label}: ${pretty(cell.state)}`}
          style={{
            backgroundColor:
              STATE_COLORS[cell.state] ||
              STATE_COLORS.unknown,
          }}
          onClick={() => onSelect(cell.id)}
        />
      ))}

      {project.heatmap_truncated && (
        <small>
          First 80 shown. Open Details for all files.
        </small>
      )}
    </div>
  )
}

function Field({
  label,
  value,
}: {
  label: string
  value: string | number | null | undefined
}) {
  return (
    <div className="ptm-field">
      <small>{label}</small>
      <strong>
        {value === null ||
        value === undefined ||
        value === ''
          ? 'Not recorded'
          : value}
      </strong>
    </div>
  )
}

// ---------------------------------------------------------
// Main Project Tracking component
// ---------------------------------------------------------

export default function ProjectTrackingPage() {
  const [period, setPeriod] = useState<Period>('month')
  const [customFrom, setCustomFrom] = useState('')
  const [customTo, setCustomTo] = useState('')
  const [department, setDepartment] = useState('all')
  const [status, setStatus] = useState('All')
  const [search, setSearch] = useState('')

  const [dashboard, setDashboard] =
    useState<Dashboard | null>(null)

  const [error, setError] = useState('')
  const [syncAt, setSyncAt] = useState('')
  const [selectedId, setSelectedId] =
    useState<number | null>(null)

  const [selectedCellId, setSelectedCellId] =
    useState<string | undefined>(undefined)

  const [detail, setDetail] = useState<Detail | null>(null)
  const [items, setItems] = useState<ItemPage | null>(null)
  const [activity, setActivity] =
    useState<ActivityPage | null>(null)

  const [detailError, setDetailError] = useState('')
  const [exporting, setExporting] = useState(false)

  // -------------------------------------------------------
  // Date filters
  // -------------------------------------------------------

  const range = useMemo(() => {
    const now = new Date()
    let start: Date

    if (period === 'month') {
      start = new Date(
        now.getFullYear(),
        now.getMonth(),
        1
      )
    } else if (period === 'year') {
      start = new Date(now.getFullYear(), 0, 1)
    } else {
      start = now
    }

    return {
      start:
        period === 'all'
          ? '1900-01-01'
          : period === 'custom'
            ? customFrom
            : ymd(start),

      end:
        period === 'all'
          ? '2100-12-31'
          : period === 'custom'
            ? customTo
            : ymd(now),
    }
  }, [period, customFrom, customTo])

  const rangeValid = Boolean(
    range.start && range.end && range.start <= range.end
  )

  // -------------------------------------------------------
  // Dashboard refresh
  // -------------------------------------------------------

  const refresh = useCallback(
    async (signal?: AbortSignal) => {
      if (!rangeValid) return

      try {
        const params = new URLSearchParams(range)
        const result = await getJSON<Dashboard>(
          `/dashboard?${params}`,
          signal
        )

        if (!signal?.aborted) {
          setDashboard(result)
          setError('')
          setSyncAt(new Date().toLocaleTimeString())
        }
      } catch (e) {
        if (!signal?.aborted) {
          setError(
            e instanceof Error
              ? e.message
              : 'Unable to load data'
          )
        }
      }
    },
    [range, rangeValid]
  )

  useEffect(() => {
    const controller = new AbortController()

    void refresh(controller.signal)

    const timer = window.setInterval(() => {
      if (!document.hidden) {
        void refresh(controller.signal)
      }
    }, 15000)

    return () => {
      controller.abort()
      window.clearInterval(timer)
    }
  }, [refresh])

  // -------------------------------------------------------
  // Project detail loading
  // -------------------------------------------------------

  useEffect(() => {
    if (selectedId === null) {
      setDetail(null)
      setItems(null)
      setActivity(null)
      return
    }

    const controller = new AbortController()

    setDetailError('')
    setDetail(null)
    setItems(null)
    setActivity(null)

    void Promise.all([
      getJSON<Detail>(
        `/projects/${selectedId}`,
        controller.signal
      ),
      getJSON<ItemPage>(
        `/projects/${selectedId}/items?offset=0&limit=100`,
        controller.signal
      ),
      getJSON<ActivityPage>(
        `/projects/${selectedId}/activity?offset=0&limit=100`,
        controller.signal
      ),
    ])
      .then(([d, it, a]) => {
        if (!controller.signal.aborted) {
          setDetail(d)
          setItems(it)
          setActivity(a)
        }
      })
      .catch(e => {
        if (!controller.signal.aborted) {
          setDetailError(
            e instanceof Error
              ? e.message
              : 'Details unavailable'
          )
        }
      })

    return () => controller.abort()
  }, [selectedId])

  // -------------------------------------------------------
  // Project filtering
  // -------------------------------------------------------

  const shown = useMemo(
    () =>
      (dashboard?.projects || []).filter(p => {
        if (
          department !== 'all' &&
          p.department !== department
        ) {
          return false
        }

        if (
          status !== 'All' &&
          p.status !== status
        ) {
          return false
        }

        return [
          p.project_name,
          p.project_code,
          p.client_name,
          p.client_code,
          p.project_manager,
          p.description,
        ]
          .join(' ')
          .toLowerCase()
          .includes(search.trim().toLowerCase())
      }),
    [dashboard, department, status, search]
  )

  const stats = useMemo(() => {
    const counts: Record<string, number> = {}

    for (const p of shown) {
      counts[p.status] = (counts[p.status] || 0) + 1
    }

    const known = shown
      .map(p => p.progress_percent)
      .filter((v): v is number => v !== null)

    return {
      total: shown.length,
      ongoing: counts['In Progress'] || 0,
      completed: counts.Completed || 0,
      delayed: counts.Delayed || 0,
      rework: counts.Rework || 0,
      not_started: counts['Not Started'] || 0,
      avg: known.length
        ? `${Math.round(
            known.reduce((a, b) => a + b, 0) /
              known.length
          )}%`
        : 'Not tracked',
    }
  }, [shown])

  const selectedProject = dashboard?.projects.find(
    p => p.id === selectedId
  )

  // -------------------------------------------------------
  // PDF / Excel export
  // -------------------------------------------------------

  async function exportFile(format: 'pdf' | 'xlsx') {
    if (!rangeValid || exporting) return

    setExporting(true)

    try {
      const params = new URLSearchParams(range)

      if (department !== 'all') {
        params.set('department', department)
      }

      if (status !== 'All') {
        params.set('status', status)
      }

      const res = await fetch(
        `${API}/export/${format}?${params}`,
        {
          headers: authHeaders(),
          credentials: 'include',
        }
      )

      if (!res.ok) {
        throw new Error(
          `Export failed (HTTP ${res.status})`
        )
      }

      const url = URL.createObjectURL(await res.blob())
      const link = document.createElement('a')

      link.href = url
      link.download =
        `naksha-project-tracking-` +
        `${range.start}-${range.end}.${format}`

      document.body.appendChild(link)
      link.click()
      link.remove()

      window.setTimeout(
        () => URL.revokeObjectURL(url),
        1000
      )
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : 'Export failed'
      )
    } finally {
      setExporting(false)
    }
  }

  // -------------------------------------------------------
  // Load more file records / activities
  // -------------------------------------------------------

  async function loadMore(which: 'items' | 'activity') {
    if (selectedId === null) return

    try {
      if (which === 'items' && items) {
        const next = await getJSON<ItemPage>(
          `/projects/${selectedId}/items?offset=${items.items.length}&limit=100`
        )

        setItems(prev =>
          prev
            ? {
                ...next,
                offset: 0,
                items: [
                  ...prev.items,
                  ...next.items,
                ],
              }
            : next
        )
      }

      if (which === 'activity' && activity) {
        const next = await getJSON<ActivityPage>(
          `/projects/${selectedId}/activity?offset=${activity.activities.length}&limit=100`
        )

        setActivity(prev =>
          prev
            ? {
                ...next,
                offset: 0,
                activities: [
                  ...prev.activities,
                  ...next.activities,
                ],
              }
            : next
        )
      }
    } catch (e) {
      setDetailError(
        e instanceof Error
          ? e.message
          : 'More records unavailable'
      )
    }
  }

  function openDetails(
    p: Project,
    cellId?: string
  ) {
    setSelectedId(p.id)
    setSelectedCellId(cellId)
  }

  // -------------------------------------------------------
  // Page rendering
  // -------------------------------------------------------

  return (
    <main className="ptm-page">
      <header className="ptm-banner">
        <div>
          <small>MANAGEMENT / OPERATIONS</small>
          <h1>Project Tracking</h1>
          <p>
            Department-wise project delivery, team
            assignments, work progress, QC, QA and rework.
          </p>
        </div>

        <div className="ptm-sync">
          <strong>
            {error
              ? 'Connection issue'
              : dashboard
                ? 'LIVE'
                : 'Loading'}
          </strong>

          <small>
            {syncAt
              ? `Last updated ${syncAt}`
              : 'Awaiting response'}
          </small>
        </div>
      </header>

      {/* Date filter toolbar */}
      <div className="ptm-toolbar">
        <div className="ptm-periods">
          {(
            [
              ['today', 'Today'],
              ['month', 'This Month'],
              ['year', 'This Year'],
              ['custom', 'Custom Dates'],
              ['all', 'All Time'],
            ] as [Period, string][]
          ).map(([key, label]) => (
            <button
              type="button"
              key={key}
              className={
                period === key ? 'selected' : ''
              }
              onClick={() => setPeriod(key)}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="ptm-actions">
          <button
            type="button"
            onClick={() => void refresh()}
          >
            Refresh
          </button>

          <button
            type="button"
            onClick={() => void exportFile('pdf')}
            disabled={exporting || !rangeValid}
          >
            Export PDF
          </button>

          <button
            type="button"
            onClick={() => void exportFile('xlsx')}
            disabled={exporting || !rangeValid}
          >
            Export Excel
          </button>
        </div>
      </div>

      {period === 'custom' && (
        <div className="ptm-custom">
          <label>
            From
            <input
              type="date"
              value={customFrom}
              onChange={e =>
                setCustomFrom(e.target.value)
              }
            />
          </label>

          <label>
            To
            <input
              type="date"
              value={customTo}
              onChange={e =>
                setCustomTo(e.target.value)
              }
            />
          </label>
        </div>
      )}

      {!rangeValid && (
        <p className="ptm-error">
          Select a valid date range.
        </p>
      )}

      {error && (
        <p role="alert" className="ptm-error">
          {error}
        </p>
      )}

      {/* Summary KPI cards */}
      <section
        className="ptm-kpis"
        aria-label="Project performance indicators"
      >
        {(
          [
            ['Total Projects', stats.total],
            ['Ongoing', stats.ongoing],
            ['Completed', stats.completed],
            ['Delayed', stats.delayed],
            ['Under Rework', stats.rework],
            ['Not Started', stats.not_started],
            ['Average Progress', stats.avg],
          ] as [string, number | string][]
        ).map(([key, value]) => (
          <div className="ptm-kpi" key={key}>
            <small>{key}</small>
            <strong>{value}</strong>
          </div>
        ))}
      </section>

      {/* Departments panel */}
      <section className="ptm-panel">
        <div className="ptm-section-head">
          <div>
            <h2>Departments</h2>
            <p>
              Choose a department to view all of its
              recorded projects.
            </p>
          </div>

          <button
            type="button"
            className={
              department === 'all' ? 'selected' : ''
            }
            onClick={() => setDepartment('all')}
          >
            All Departments
          </button>
        </div>

        {/* NEW: Compact one-row desktop grid */}
        <div className="ptm-departments pt-departments-grid">
          {(dashboard?.departments || []).map(dep => {
            const rows =
              dashboard?.projects.filter(
                p => p.department === dep.code
              ) || []

            const isSelected =
              department === dep.code

            return (
              <button
                type="button"
                key={dep.code}
                className={
                  isSelected
                    ? 'ptm-dep selected pt-department-card is-selected'
                    : 'ptm-dep pt-department-card'
                }
                onClick={() => {
                  setDepartment(dep.code)
                  setStatus('All')
                }}
              >
                <b className="pt-department-name">
                  {dep.label}
                </b>

                <span className="pt-department-count">
                  {rows.length}{' '}
                  project{rows.length !== 1 ? 's' : ''}
                </span>

                <small>
                  {
                    rows.filter(
                      p => p.status === 'In Progress'
                    ).length
                  }{' '}
                  ongoing /{' '}
                  {
                    rows.filter(
                      p => p.status === 'Completed'
                    ).length
                  }{' '}
                  completed
                </small>
              </button>
            )
          })}

          {dashboard &&
            dashboard.departments.length === 0 && (
              <p className="ptm-muted">
                No departments have recorded projects
                in this period.
              </p>
            )}
        </div>
      </section>

      {/* Department Project Register */}
      <section className="ptm-panel">
        <div className="ptm-section-head">
          <div>
            <h2>Department Project Register</h2>

            <p>
              {department === 'all'
                ? 'All departments'
                : dashboard?.departments.find(
                    x => x.code === department
                  )?.label}{' '}
              - {shown.length} matching projects
            </p>
          </div>
        </div>

        <div className="ptm-filters">
          <input
            aria-label="Search projects"
            placeholder="Search project, client code, PM..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />

          <select
            aria-label="Project status"
            value={status}
            onChange={e => setStatus(e.target.value)}
          >
            {[
              'All',
              'Not Started',
              'In Progress',
              'Completed',
              'Delayed',
              'Rework',
              'Inactive',
            ].map(s => (
              <option value={s} key={s}>
                {s === 'All' ? 'All Statuses' : s}
              </option>
            ))}
          </select>
        </div>

        <div className="ptm-table-scroll">
          <table className="ptm-table">
            <thead>
              <tr>
                <th>Project / Code</th>
                <th>Client Code</th>
                <th>Total Project Value (₹)</th>
                <th>Project Manager</th>
                <th>Project Details</th>
                <th>Progress / Heatmap</th>
                <th>Project Description</th>
              </tr>
            </thead>

            {/* FIXED: Proper tbody, map and table cells */}
            <tbody>
              {shown.map(p => (
                <tr key={p.id}>
                  <td>
                    <strong>{p.project_name}</strong>
                    <small>{p.project_code}</small>
                    <small>{p.department_label}</small>
                  </td>

                  <td>
                    {p.client_code || 'Not recorded'}
                  </td>

                  {/* NEW: Project value column */}
                  <td className="pt-project-value">
                    {formatProjectValue(
                      p.project_value_inr
                    )}
                  </td>

                  <td>
                    {p.project_manager || 'Not assigned'}
                  </td>

                  <td>
                    <button
                      className="ptm-outline"
                      type="button"
                      onClick={() => openDetails(p)}
                    >
                      View Details
                    </button>
                  </td>

                  <td className="ptm-progress-cell">
                    <Progress project={p} />

                    <Heatmap
                      project={p}
                      onSelect={cell =>
                        openDetails(p, cell)
                      }
                    />
                  </td>

                  <td className="ptm-description">
                    {p.description ||
                      'No description recorded'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {dashboard && shown.length === 0 && (
            <p className="ptm-empty">
              No projects match the selected department,
              dates and filters.
            </p>
          )}
        </div>

        <div className="ptm-legend">
          <b>File/section heatmap:</b>

          {Object.entries(STATE_COLORS).map(
            ([state, color]) => (
              <span key={state}>
                <i
                  style={{
                    background: color,
                  }}
                />
                {pretty(state)}
              </span>
            )
          )}
        </div>
      </section>

      {/* Project Details modal */}
      {selectedId !== null && (
        <div
          className="ptm-overlay"
          role="presentation"
          onClick={e => {
            if (e.target === e.currentTarget) {
              setSelectedId(null)
            }
          }}
        >
          <section
            className="ptm-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Complete project information"
          >
            <header>
              <div>
                <small>READ-ONLY PROJECT DETAILS</small>

                <h2>
                  {detail?.project.project_name ||
                    selectedProject?.project_name ||
                    'Project'}
                </h2>

                <p>
                  Complete operational history from
                  existing ERP records
                </p>
              </div>

              <button
                type="button"
                className="ptm-close"
                onClick={() => setSelectedId(null)}
                aria-label="Close details"
              >
                Close
              </button>
            </header>

            {detailError && (
              <p role="alert" className="ptm-error">
                {detailError}
              </p>
            )}

            {!detail && !detailError && (
              <p className="ptm-muted">
                Loading project information...
              </p>
            )}

            {detail && (
              <>
                <div className="ptm-detail-grid">
                  <Field
                    label="Project Code"
                    value={detail.project.project_code}
                  />

                  <Field
                    label="Client Code"
                    value={detail.project.client_code}
                  />

                  <Field
                    label="Client"
                    value={detail.project.client_name}
                  />

                  <Field
                    label="Department"
                    value={
                      detail.project.department_label
                    }
                  />

                  <Field
                    label="Project Manager"
                    value={
                      detail.project.project_manager
                    }
                  />

                  <Field
                    label="Status"
                    value={detail.project.status}
                  />

                  <Field
                    label="Created"
                    value={displayDate(
                      detail.project.created_at
                    )}
                  />

                  <Field
                    label="Planned Start"
                    value={displayDate(
                      detail.project.start_date
                    )}
                  />

                  <Field
                    label="Planned End"
                    value={displayDate(
                      detail.project.end_date
                    )}
                  />

                  <Field
                    label="Operational Completion"
                    value={displayDate(
                      detail.project.completed_at
                    )}
                  />
                </div>

                <h3>Project Description and Scope</h3>
                <p>
                  {detail.project.description ||
                    'Not recorded'}
                </p>

                <h3>Overall Progress</h3>
                <Progress project={detail.project} />

                <h3>Team Members</h3>

                {detail.members.length ? (
                  <div className="ptm-tags">
                    {detail.members.map((m, i) => (
                      <span key={i}>
                        {m.name || 'Unknown'} -{' '}
                        {pretty(m.role)}
                        {m.active
                          ? ''
                          : ' (inactive)'}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="ptm-muted">
                    No team membership records.
                  </p>
                )}

                <h3>Survey Areas / Work Packages</h3>

                {detail.packages.length ? (
                  <div className="ptm-table-scroll">
                    <table className="ptm-table">
                      <thead>
                        <tr>
                          <th>Section</th>
                          <th>Production</th>
                          <th>QC</th>
                          <th>QA</th>
                          <th>Team Lead</th>
                          <th>Target Date</th>
                        </tr>
                      </thead>

                      <tbody>
                        {detail.packages.map(x => (
                          <tr key={x.id}>
                            <td>
                              <b>{x.name}</b>
                              <small>{x.code}</small>
                            </td>

                            <td>
                              {pretty(x.production_state)}
                            </td>

                            <td>
                              {pretty(x.qc_state)}
                            </td>

                            <td>
                              {pretty(x.qa_state)}
                            </td>

                            <td>
                              {x.team_lead ||
                                'Not assigned'}
                            </td>

                            <td>
                              {displayDate(
                                x.target_date
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="ptm-muted">
                    No work packages recorded.
                    Software projects can be tracked
                    by milestones once connected.
                  </p>
                )}

                <h3>
                  Files and Individual Assignments (
                  {items?.total ??
                    detail.items_total})
                </h3>

                {selectedCellId && (
                  <p className="ptm-muted">
                    Selected heatmap unit:{' '}
                    {selectedCellId}.
                    Locate the corresponding file or
                    section below.
                  </p>
                )}

                {items?.items.length ? (
                  <div className="ptm-table-scroll">
                    <table className="ptm-table">
                      <thead>
                        <tr>
                          <th>File</th>
                          <th>Status</th>
                          <th>Production</th>
                          <th>QC</th>
                          <th>QA</th>
                          <th>Target</th>
                        </tr>
                      </thead>

                      <tbody>
                        {items.items.map(x => (
                          <tr
                            key={x.id}
                            className={
                              selectedCellId ===
                              `file-${x.id}`
                                ? 'ptm-highlight'
                                : ''
                            }
                          >
                            <td>
                              {x.name}
                              <small>{x.code}</small>
                            </td>

                            <td>
                              {pretty(x.status)}
                            </td>

                            <td>
                              {x.production_employee ||
                                '-'}
                            </td>

                            <td>
                              {x.qc_employee || '-'}
                            </td>

                            <td>
                              {x.qa_employee || '-'}
                            </td>

                            <td>
                              {displayDate(
                                x.production_target_date
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="ptm-muted">
                    No individual files recorded for
                    this project.
                  </p>
                )}

                {items &&
                  items.items.length < items.total && (
                    <button
                      className="ptm-outline"
                      onClick={() =>
                        void loadMore('items')
                      }
                    >
                      Load more files (
                      {items.items.length}/
                      {items.total})
                    </button>
                  )}

                <h3>
                  Production / QC / QA Activity
                  History ({activity?.total ?? 0})
                </h3>

                {activity?.activities.length ? (
                  <div className="ptm-table-scroll">
                    <table className="ptm-table">
                      <thead>
                        <tr>
                          <th>When</th>
                          <th>File ID</th>
                          <th>Stage</th>
                          <th>Employee</th>
                          <th>Status</th>
                          <th>Rework / Remarks</th>
                        </tr>
                      </thead>

                      <tbody>
                        {activity.activities.map(
                          (x, i) => (
                            <tr key={i}>
                              <td>
                                {x.at ||
                                  'Not recorded'}
                              </td>

                              <td>{x.item_id}</td>

                              <td>
                                {pretty(x.stage)}
                              </td>

                              <td>
                                {x.employee || '-'}
                              </td>

                              <td>
                                {pretty(x.status)}
                              </td>

                              <td>
                                {x.delay_reason ||
                                  x.remarks ||
                                  x.attempt_type ||
                                  '-'}
                              </td>
                            </tr>
                          )
                        )}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="ptm-muted">
                    No recorded file activity history.
                  </p>
                )}

                {activity &&
                  activity.activities.length <
                    activity.total && (
                    <button
                      className="ptm-outline"
                      onClick={() =>
                        void loadMore('activity')
                      }
                    >
                      Load more activity (
                      {activity.activities.length}/
                      {activity.total})
                    </button>
                  )}

                <h3>Project Workflow History</h3>

                {detail.workflow_history.length ? (
                  <ul className="ptm-history">
                    {detail.workflow_history.map(
                      (e, i) => (
                        <li key={i}>
                          <b>
                            {pretty(e.action)} -{' '}
                            {pretty(e.status)}
                          </b>

                          <small>
                            {e.at ||
                              'No timestamp'}{' '}
                            -{' '}
                            {e.actor ||
                              'Unknown user'}
                          </small>

                          <span>
                            {e.comments || ''}
                          </span>
                        </li>
                      )
                    )}
                  </ul>
                ) : (
                  <p className="ptm-muted">
                    No workflow events recorded.
                  </p>
                )}
              </>
            )}
          </section>
        </div>
      )}
    </main>
  )
}
