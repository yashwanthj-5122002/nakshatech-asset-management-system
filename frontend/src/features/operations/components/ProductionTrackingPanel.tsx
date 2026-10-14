import { History, Loader2, Upload, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { PaginationBar } from '../../../components/PaginationBar'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch, uploadExcel } from '../../../lib/api'
import {
  DEADLINE_LABELS,
  ItemStageActivityControls,
  fmtDate,
  fmtDuration,
  fmtQty,
  fmtTime,
  label,
  stageLabel,
  stageStatusTone,
} from './ItemStageActivityControls'

// Shared read model for the V8.1 Daily Activity / Production Tracking table plus
// the V8.2 optional FILE / TILE / ITEM tracking (area detail drawer).
// Shapes mirror backend production_service.tracking_summary (package_rows),
// production_items.item_list and the Excel exports, so UI and export never disagree.

export type BufferInfo = {
  target_date?: string | null
  production_target_date?: string | null
  buffer_days: number
  buffer_until?: string | null
  status: string
  days_overdue: number
  days_late?: number
}

export type PackageTrackingRow = {
  work_package_id: number
  lot_batch?: string | null
  package_code: string
  area_name: string
  target_quantity?: number | null
  unit?: string | null
  actual_quantity: number
  files: number
  production_progress_percent: number
  over_target_quantity: number
  workflow_progress_percent: number
  applicable_stages: string[]
  stage_statuses: Record<string, string | null>
  pending_stages: string[]
  current_stage: string
  production_state: string
  qc_state: string
  qa_state: string
  stage_dates: Record<string, string | null>
  qc_decision?: string | null
  qa_decision?: string | null
  team_leader?: string | null
  production_user?: string | null
  qc_user?: string | null
  qa_user?: string | null
  dxf_user?: string | null
  rework: boolean
  rework_cycle_id?: number | null
  target_date?: string | null
  production_target_date?: string | null
  buffer?: BufferInfo
  files_expected?: number
  files_production_done?: number
  files_qc_passed?: number
  files_qa_passed?: number
  files_delivered?: number
  file_production_percent?: number
  file_qc_percent?: number
  file_qa_percent?: number
  file_delivery_percent?: number
  remarks?: string | null
  instructions?: string | null
}

export type ProjectTrackingRow = {
  project_id: number
  project_code: string
  department_code: string
  workflow_status: string
  project_manager?: { id: number; full_name: string } | null
  team_leaders: string[]
  packages: number
  package_rows: PackageTrackingRow[]
  planned_by_unit: { unit: string | null; planned: number; completed: number; packages: number }[]
  production_progress_percent: number
  workflow_progress_percent: number
  mixed_measurement_types: boolean
  pending_stages: Record<string, number>
  rework_packages: number
  blocked_packages: number
  employees?: { user_id: number; full_name?: string | null }[]
}

export type TrackingSummary = {
  projects: ProjectTrackingRow[]
  viewer_mode: 'read_only' | 'project_manager' | 'participant'
}

export type FlatTrackingRow = PackageTrackingRow & {
  project_id: number
  project_code: string
  employees: { user_id: number; full_name?: string | null }[]
}

export type ItemRow = {
  work_package_item_id: number
  work_package_id: number
  item_number: string
  item_name?: string | null
  planned_quantity?: number | null
  planned_unit?: string | null
  status: string
  is_active: boolean
  production_user_id?: number | null
  production_user?: string | null
  qc_user_id?: number | null
  qc_user?: string | null
  qa_user_id?: number | null
  qa_user?: string | null
  production_status: string
  qc_status: string
  qa_status: string
  delivery_status: string
  production_start?: string | null
  production_end?: string | null
  production_duration_seconds?: number | null
  production_quantity?: number | null
  production_unit?: string | null
  production_files: number
  production_remarks?: string | null
  production_employee?: string | null
  qc_start?: string | null
  qc_end?: string | null
  qc_duration_seconds?: number | null
  qc_remarks?: string | null
  qc_employee?: string | null
  qa_start?: string | null
  qa_end?: string | null
  qa_duration_seconds?: number | null
  qa_remarks?: string | null
  qa_employee?: string | null
  delivery_at?: string | null
  delivery_by?: string | null
  delivery_remarks?: string | null
  delay_category?: string | null
  delay_reason?: string | null
  delay_remarks?: string | null
  affected_item_number?: string | null
  system_malfunction: boolean
  open_session: { activity_id: number; stage: string; employee_user_id: number; started_at?: string | null } | null
  // V8.3 allocation
  production_target_date?: string | null
  qc_target_date?: string | null
  qa_target_date?: string | null
  supply_date?: string | null
  import_source?: string | null
  ready_for_delivery?: boolean
  production_deadline?: DeadlineInfo
  qc_deadline?: DeadlineInfo
  qa_deadline?: DeadlineInfo
}

export type DeadlineInfo = {
  target_date?: string | null
  buffer_until?: string | null
  status: string
  days_overdue?: number
  days_late?: number
}

export type ReadinessInfo = {
  applicable: boolean
  ready: boolean
  total_files: number
  production_completed: number
  production_pending: number
  qc_passed: number
  qc_pending: number
  qc_rework: number
  qa_passed: number
  qa_pending: number
  qa_rework: number
  ready_by_id?: number | null
  ready_at?: string | null
  confirmed: boolean
}

export type EmployeeTotal = {
  employee_user_id: number
  employee?: string | null
  files_completed: number
  quantity_completed: number
  unit?: string | null
  duration_seconds: number
  production_assigned?: number
  production_completed?: number
  production_pending?: number
  qc_assigned?: number
  qc_passed?: number
  qc_pending?: number
  qa_assigned?: number
  qa_passed?: number
  qa_pending?: number
}

export type ItemListResponse = {
  work_package_id: number
  project_id: number
  package_code: string
  package_name: string
  lot_batch?: string | null
  supply_date?: string | null
  can_manage: boolean
  can_deliver: boolean
  can_confirm_ready: boolean
  my_user_id: number
  deadline: BufferInfo
  stage_targets: { production?: string | null; qc?: string | null; qa?: string | null }
  stage_deadlines: { production: DeadlineInfo; qc: DeadlineInfo; qa: DeadlineInfo }
  readiness: ReadinessInfo
  project_manager?: { id: number; full_name: string } | null
  employee_totals: EmployeeTotal[]
  items: ItemRow[]
}

export type HistoryEvent = {
  kind: string
  stage?: string | null
  at?: string | null
  date?: string | null
  actor_name?: string | null
  actor_role?: string | null
  from_status?: string | null
  to_status?: string | null
  quantity?: number | null
  unit?: string | null
  files?: number | null
  hours?: number | null
  remarks?: string | null
  blockers?: string | null
  attempt_no?: number
}

export const STAGE_ORDER = ['import', 'production', 'qc', 'qa', 'dxf', 'inspection', 'delivery', 'upload'] as const

export const STAGE_LABELS: Record<string, string> = {
  import: 'Import',
  production: 'Production',
  qc: 'QC',
  qa: 'QA',
  dxf: 'DXF',
  inspection: 'Inspection',
  delivery: 'Delivery',
  upload: 'Upload',
}

export const TRACKABLE_STAGES = ['import', 'dxf', 'inspection', 'upload'] as const

export const TRACKABLE_STAGE_STATUSES: Record<string, string[]> = {
  import: ['not_started', 'in_progress', 'completed', 'on_hold'],
  dxf: ['not_started', 'pending', 'in_progress', 'approved', 'rejected'],
  inspection: ['pending', 'inspected', 'not_inspected'],
  upload: ['pending', 'in_progress', 'uploaded', 'on_hold'],
}

// Controlled difficulty/delay categories (mirrors backend DELAY_CATEGORIES).

const STAGE_COMPLETE: Record<string, string[]> = {
  production: ['completed'],
  qc: ['approved', 'passed'],
  qa: ['approved', 'passed'],
  delivery: ['delivered'],
  import: ['completed'],
  dxf: ['approved'],
  inspection: ['inspected'],
  upload: ['uploaded'],
}

export function deadlineTone(status?: string | null): string {
  if (status === 'overdue' || status === 'completed_late') return 'danger'
  if (status === 'buffer_day' || status === 'completed_in_buffer' || status === 'due_today') return 'warning'
  if (status === 'completed_on_time' || status === 'on_track') return 'success'
  return ''
}

// Backend timestamps are naive UTC ISO strings — parse them as UTC so elapsed
// time and clock displays are correct in the viewer's local timezone.

function ReadinessPanel({
  readiness, canConfirm, busy, onConfirm,
}: { readiness: ReadinessInfo; canConfirm: boolean; busy: boolean; onConfirm: () => void }) {
  if (!readiness.applicable) return null
  return (
    <section className="pt-readiness">
      <h4>
        Delivery readiness{' '}
        {readiness.confirmed
          ? <span className="operations-status success">Ready for Delivery confirmed</span>
          : <span className={`operations-status ${readiness.ready ? 'success' : 'warning'}`}>
              {readiness.ready ? 'READY FOR DELIVERY' : 'NOT READY FOR DELIVERY'}
            </span>}
      </h4>
      <div className="pt-readiness-grid">
        <div><span>Total files</span><strong>{readiness.total_files}</strong></div>
        <div><span>Production completed</span><strong>{readiness.production_completed}</strong></div>
        <div><span>QC passed</span><strong>{readiness.qc_passed}</strong></div>
        <div><span>QA passed</span><strong>{readiness.qa_passed}</strong></div>
        <div><span>Production pending</span><strong>{readiness.production_pending}</strong></div>
        <div><span>QC pending</span><strong>{readiness.qc_pending}</strong></div>
        <div><span>QC rework</span><strong>{readiness.qc_rework}</strong></div>
        <div><span>QA pending</span><strong>{readiness.qa_pending}</strong></div>
        <div><span>QA rework</span><strong>{readiness.qa_rework}</strong></div>
      </div>
      {!readiness.ready && (
        <p className="pt-drawer-text">
          Every active file must pass QA before this area can be marked Ready for Delivery.
        </p>
      )}
      {readiness.confirmed ? (
        <p className="pt-drawer-text">
          Confirmed ready {fmtDate(readiness.ready_at)}. Delivery continues through the existing
          authorized delivery workflow — Finance is not affected.
        </p>
      ) : canConfirm && readiness.ready ? (
        <div className="operations-actions">
          <button type="button" className="operations-button success" disabled={busy} onClick={onConfirm}>
            Mark Ready for Delivery
          </button>
        </div>
      ) : null}
    </section>
  )
}

function flatten(projects: ProjectTrackingRow[]): FlatTrackingRow[] {
  return projects.flatMap((p) =>
    (p.package_rows ?? []).map((row) => ({
      ...row,
      project_id: p.project_id,
      project_code: p.project_code,
      employees: p.employees ?? [],
    })),
  )
}

type PanelProps = {
  projects: ProjectTrackingRow[]
  showProjectColumn?: boolean
  viewerMode?: string
  emptyMessage?: string
}

const PAGE_SIZE = 25

export function ProductionTrackingPanel({ projects, showProjectColumn = true, viewerMode, emptyMessage }: PanelProps) {
  const [search, setSearch] = useState('')
  const [currentStage, setCurrentStage] = useState('')
  const [pendingStage, setPendingStage] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<FlatTrackingRow | null>(null)

  const rows = useMemo(() => flatten(projects), [projects])
  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase()
    return rows.filter((row) => {
      if (currentStage && row.current_stage !== currentStage) return false
      if (pendingStage && !row.pending_stages.includes(pendingStage)) return false
      if (!term) return true
      return [row.package_code, row.area_name, row.lot_batch ?? '', row.remarks ?? '', row.project_code]
        .some((value) => value.toLowerCase().includes(term))
    })
  }, [rows, search, currentStage, pendingStage])

  useEffect(() => setPage(1), [search, currentStage, pendingStage])

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const safePage = Math.min(page, pageCount)
  const pageRows = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)
  const stageOptions = useMemo(
    () => [...new Set(rows.flatMap((r) => r.applicable_stages))].sort(
      (a, b) => STAGE_ORDER.indexOf(a as never) - STAGE_ORDER.indexOf(b as never),
    ),
    [rows],
  )

  return (
    <>
      <div className="pt-toolbar">
        <label className="operations-field">
          <span>Search code / area / lot</span>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="DX20-24730, Murlo, lot…" />
        </label>
        <label className="operations-field">
          <span>Current stage</span>
          <select value={currentStage} onChange={(e) => setCurrentStage(e.target.value)}>
            <option value="">All stages</option>
            {['not_started', 'production', 'qc', 'qa', 'delivery_ready', 'delivered'].map((s) => (
              <option key={s} value={s}>{label(s)}</option>
            ))}
          </select>
        </label>
        <label className="operations-field">
          <span>Pending stage</span>
          <select value={pendingStage} onChange={(e) => setPendingStage(e.target.value)}>
            <option value="">Any</option>
            {stageOptions.map((s) => (
              <option key={s} value={s}>{stageLabel(s)} pending</option>
            ))}
          </select>
        </label>
        {(search || currentStage || pendingStage) && (
          <button type="button" className="operations-button secondary pt-clear" onClick={() => { setSearch(''); setCurrentStage(''); setPendingStage('') }}>
            Clear filters
          </button>
        )}
      </div>

      {!pageRows.length ? (
        <div className="nk-empty">
          <h3>No work packages match</h3>
          <p>{emptyMessage ?? 'No production-tracking rows are available for your role and the current filters.'}</p>
        </div>
      ) : (
        <div className="operations-table-wrap pt-table-wrap">
          <table className="operations-table pt-table">
            <thead>
              <tr>
                <th className="pt-sticky-1">Lot / Batch</th>
                <th className="pt-sticky-2">Code</th>
                {showProjectColumn && <th>Project</th>}
                <th>Area</th>
                <th>Target</th>
                <th>Actual</th>
                <th>Stages</th>
                <th>Files</th>
                <th>Current Stage</th>
                <th>Production %</th>
                <th>QC %</th>
                <th>QA %</th>
                <th>Delivery %</th>
                <th>Workflow %</th>
                <th>Target Date / Buffer</th>
                <th>Remarks</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((row) => {
                const buffer = row.buffer
                return (
                  <tr key={`${row.project_id}-${row.work_package_id}`} onClick={() => setSelected(row)} className="pt-row">
                    <td className="pt-sticky-1">{row.lot_batch || '—'}</td>
                    <td className="pt-sticky-2">
                      <strong>{row.package_code}</strong>
                      {row.rework && <span className="operations-status warning pt-rework">Rework</span>}
                    </td>
                    {showProjectColumn && <td>{row.project_code}</td>}
                    <td>{row.area_name || '—'}</td>
                    <td>{fmtQty(row.target_quantity)} {row.unit || ''}</td>
                    <td>
                      {fmtQty(row.actual_quantity)} {row.unit || ''}
                      {row.over_target_quantity > 0 && <span className="pt-over" title="Over target"> +{fmtQty(row.over_target_quantity)}</span>}
                    </td>
                    <td>
                      <span className="pt-stage-group">
                        {row.applicable_stages.map((stage) => {
                          const status = row.stage_statuses[stage]
                          return (
                            <span key={stage} className={`operations-status ${stageStatusTone(stage, status)}`} title={`${stageLabel(stage)}: ${status ? label(status) : 'not started'}`}>
                              {stageLabel(stage)}
                            </span>
                          )
                        })}
                      </span>
                    </td>
                    <td title={`${row.files_production_done ?? 0} production completed · ${row.files_qc_passed ?? 0} QC passed · ${row.files_qa_passed ?? 0} QA passed · ${row.files_delivered ?? 0} delivered`}>
                      {(row.files_expected ?? 0) > 0
                        ? `${row.files_production_done ?? 0} / ${row.files_expected}`
                        : row.files}
                    </td>
                    <td><span className="operations-status">{label(row.current_stage)}</span></td>
                    <td>
                      <div className="operations-progress pt-progress"><span style={{ width: `${Math.min(100, row.production_progress_percent)}%` }} /></div>
                      <small>{row.production_progress_percent}%</small>
                    </td>
                    <td>{(row.files_expected ?? 0) > 0 ? `${row.file_qc_percent ?? 0}%` : '—'}</td>
                    <td>{(row.files_expected ?? 0) > 0 ? `${row.file_qa_percent ?? 0}%` : '—'}</td>
                    <td>{(row.files_expected ?? 0) > 0 ? `${row.file_delivery_percent ?? 0}%` : '—'}</td>
                    <td>{row.workflow_progress_percent}%</td>
                    <td>
                      <div>{fmtDate(row.target_date)}</div>
                      {buffer && buffer.status !== 'no_target' && (
                        <span className={`operations-status ${deadlineTone(buffer.status)}`}>
                          {DEADLINE_LABELS[buffer.status] ?? buffer.status}
                          {buffer.status === 'overdue' && buffer.days_overdue > 0 ? ` · ${buffer.days_overdue}d` : ''}
                        </span>
                      )}
                    </td>
                    <td className="pt-remarks" title={row.remarks ?? ''}>{row.remarks || '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <PaginationBar
        page={safePage}
        pageCount={pageCount}
        total={filtered.length}
        rangeStart={filtered.length ? (safePage - 1) * PAGE_SIZE + 1 : 0}
        rangeEnd={Math.min(safePage * PAGE_SIZE, filtered.length)}
        onPageChange={setPage}
        label="Work packages"
      />

      {selected && createPortal(
        <PackageDetailDrawer
          row={selected}
          readOnly={viewerMode === 'read_only'}
          onClose={() => setSelected(null)}
        />,
        // Portal to body: the panel's backdrop-filter creates a stacking context
        // that would otherwise trap this fixed drawer UNDER the sidebar.
        document.body,
      )}
    </>
  )
}

// ===========================================================================================
// Area detail drawer: area details + V8.2 file/tile table + role actions
// ===========================================================================================

function PackageDetailDrawer({ row, readOnly, onClose }: { row: FlatTrackingRow; readOnly: boolean; onClose: () => void }) {
  const { user } = useAuth()
  const [history, setHistory] = useState<HistoryEvent[] | null>(null)
  const [historyError, setHistoryError] = useState('')
  const [items, setItems] = useState<ItemListResponse | null>(null)
  const [itemsError, setItemsError] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [now, setNow] = useState(() => Date.now())

  // TL file controls
  const [addOpen, setAddOpen] = useState(false)
  const [addNumber, setAddNumber] = useState('')
  const [addName, setAddName] = useState('')
  const [bulkText, setBulkText] = useState('')
  const [genPrefix, setGenPrefix] = useState('FILE')
  const [genStart, setGenStart] = useState('1')
  const [genCount, setGenCount] = useState('10')
  const [genPadding, setGenPadding] = useState('3')
  const [genExt, setGenExt] = useState('')
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [assignProduction, setAssignProduction] = useState('')
  const [assignQc, setAssignQc] = useState('')
  const [assignQa, setAssignQa] = useState('')
  const [timelineOpen, setTimelineOpen] = useState(false)
  const [prodTarget, setProdTarget] = useState(row.production_target_date || '')
  const [bufferDays, setBufferDays] = useState(String(row.buffer?.buffer_days ?? 1))

  // employee session + stop form

  function loadItems() {
    setItemsError('')
    void apiFetch<ItemListResponse>(`/operations/workflow/ortho/work-packages/${row.work_package_id}/items`)
      .then(setItems)
      .catch((e) => setItemsError(e instanceof Error ? e.message : 'Unable to load files'))
  }

  useEffect(() => {
    setHistory(null)
    setHistoryError('')
    void apiFetch<{ events: HistoryEvent[] }>(`/operations/workflow/ortho/work-packages/${row.work_package_id}/history`)
      .then((v) => setHistory(v.events))
      .catch((e) => setHistoryError(e instanceof Error ? e.message : 'Unable to load history'))
    loadItems()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [row.work_package_id])

  // Elapsed ticker while any session is open (duration itself is backend-computed).
  const hasOpen = (items?.items ?? []).some((it) => it.open_session !== null)
  useEffect(() => {
    if (!hasOpen) return
    const timer = window.setInterval(() => setNow(Date.now()), 5000)
    return () => window.clearInterval(timer)
  }, [hasOpen])

  async function run(action: () => Promise<unknown>, success: string): Promise<boolean> {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await action()
      setNotice(success)
      loadItems()
      return true
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed')
      return false
    } finally {
      setBusy(false)
    }
  }

  async function addSingle() {
    const number = addNumber.trim()
    if (!number) { setError('File number is required.'); return }
    if (await run(
      () => apiFetch(`/operations/workflow/ortho/work-packages/${row.work_package_id}/items`, {
        method: 'POST',
        body: JSON.stringify({ items: [{ item_number: number, item_name: addName.trim() || null }] }),
      }),
      `File ${number} added.`,
    )) {
      setAddNumber(''); setAddName(''); setAddOpen(false)
    }
  }

  async function addBulk() {
    const entries = bulkText
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [number, ...rest] = line.split(',')
        return { item_number: number.trim(), item_name: rest.join(',').trim() || null }
      })
      .filter((e) => e.item_number)
    if (!entries.length) { setError('Enter one file per line as NUMBER or NUMBER,Name.'); return }
    if (await run(
      () => apiFetch(`/operations/workflow/ortho/work-packages/${row.work_package_id}/items`, {
        method: 'POST',
        body: JSON.stringify({ items: entries }),
      }),
      `${entries.length} file(s) added.`,
    )) {
      setBulkText(''); setAddOpen(false)
    }
  }

  async function generateSequence() {
    if (await run(
      () => apiFetch(`/operations/workflow/ortho/work-packages/${row.work_package_id}/items/generate`, {
        method: 'POST',
        body: JSON.stringify({
          prefix: genPrefix || 'FILE',
          start: Number(genStart) || 1,
          count: Number(genCount) || 1,
          padding: Number(genPadding) || 3,
          extension: genExt.trim() || null,
        }),
      }),
      `Generated ${genCount} sequential file(s).`,
    )) {
      setAddOpen(false)
    }
  }

  async function importFile(file: File) {
    if (await run(
      () => uploadExcel(`/operations/workflow/ortho/work-packages/${row.work_package_id}/items/import`, file),
      `Imported ${file.name}.`,
    )) {
      setAddOpen(false)
    }
  }

  async function assignSelected() {
    if (!selectedIds.length) { setError('Select at least one file to assign.'); return }
    if (!assignProduction && !assignQc && !assignQa) { setError('Choose at least one role to assign.'); return }
    const body: Record<string, unknown> = { item_ids: selectedIds }
    if (assignProduction) body.production_user_id = Number(assignProduction)
    if (assignQc) body.qc_user_id = Number(assignQc)
    if (assignQa) body.qa_user_id = Number(assignQa)
    if (await run(
      () => apiFetch(`/operations/workflow/ortho/work-packages/${row.work_package_id}/items/assign`, {
        method: 'POST', body: JSON.stringify(body),
      }),
      `${selectedIds.length} file(s) assigned.`,
    )) {
      setSelectedIds([]); setAssignProduction(''); setAssignQc(''); setAssignQa('')
    }
  }

  async function toggleActive(item: ItemRow, active: boolean) {
    await run(
      () => apiFetch(`/operations/workflow/ortho/items/${item.work_package_item_id}`, {
        method: 'PATCH', body: JSON.stringify({ is_active: active }),
      }),
      `${item.item_number} ${active ? 'reactivated' : 'deactivated'}. History preserved.`,
    )
  }

  async function markReady() {
    await run(
      () => apiFetch(`/operations/workflow/ortho/work-packages/${row.work_package_id}/ready-for-delivery`, {
        method: 'POST',
      }),
      'Ready for Delivery confirmed. The Project Manager was notified.',
    )
    loadItems()
  }

  async function saveTimeline() {
    if (await run(
      () => apiFetch(`/operations/workflow/ortho/work-packages/${row.work_package_id}/timeline`, {
        method: 'PATCH',
        body: JSON.stringify({
          production_target_date: prodTarget || null,
          buffer_days: bufferDays === '' ? null : Number(bufferDays),
        }),
      }),
      'Production target / buffer saved. Original target date unchanged.',
    )) {
      setTimelineOpen(false)
    }
  }

  const me = user?.id ?? 0
  const deadline = items?.deadline ?? row.buffer
  const stageRows = row.applicable_stages
  const employees = row.employees.filter((e) => e.user_id)
  const allItems = items?.items ?? []
  const activeCount = allItems.filter((it) => it.is_active).length
  const productionDone = allItems.filter((it) => it.is_active && it.production_status === 'completed').length

  return (
    <aside className="pt-drawer pt-drawer-wide" role="dialog" aria-label={`Details for ${row.package_code}`}>
      <header className="pt-drawer-head">
        <div>
          <span className="operations-kicker">{row.project_code} · {row.lot_batch ? `Lot ${row.lot_batch} · ` : ''}#{row.work_package_id}</span>
          <h3>{row.package_code} — {row.area_name}</h3>
        </div>
        <button type="button" className="pt-drawer-close" onClick={onClose} aria-label="Close"><X size={18} /></button>
      </header>

      <div className="pt-drawer-body">
        {notice && <div className="operations-alert success">{notice}</div>}
        {error && <div className="operations-alert error">{error}</div>}

        {/* ---------------- AREA DETAILS ---------------- */}
        <div className="pt-drawer-kpis">
          <div><span>Planned</span><strong>{fmtQty(row.target_quantity)} {row.unit || ''}</strong></div>
          <div><span>Actual</span><strong>{fmtQty(row.actual_quantity)} {row.unit || ''}</strong></div>
          <div><span>Production %</span><strong>{row.production_progress_percent}%</strong></div>
          <div><span>Workflow %</span><strong>{row.workflow_progress_percent}%</strong></div>
          <div><span>Files (done / total)</span><strong>{productionDone} / {activeCount || row.files}</strong></div>
          <div><span>Current Stage</span><strong>{label(row.current_stage)}</strong></div>
        </div>

        <div className="pt-deadline-bar">
          <div><span>Supply Date</span><strong>{fmtDate(row.stage_dates?.supply)}</strong></div>
          <div><span>Target Date</span><strong>{fmtDate(deadline?.target_date ?? row.target_date)}</strong></div>
          <div><span>Buffer Until</span><strong>{fmtDate(deadline?.buffer_until)}</strong></div>
          <div>
            <span>Deadline Status</span>
            <strong>
              {deadline && (
                <span className={`operations-status ${deadlineTone(deadline.status)}`}>
                  {DEADLINE_LABELS[deadline.status] ?? deadline.status}
                </span>
              )}
            </strong>
          </div>
          <div><span>Days Overdue</span><strong>{deadline?.days_overdue ?? 0}</strong></div>
        </div>

        {items?.can_manage && (
          <div className="pt-inline-actions">
            {!timelineOpen ? (
              <button type="button" className="operations-button secondary" onClick={() => setTimelineOpen(true)}>Set Production Target / Buffer</button>
            ) : (
              <div className="pt-inline-form">
                <label className="operations-field"><span>Production Target Date (original target unchanged)</span>
                  <input type="date" value={prodTarget} onChange={(e) => setProdTarget(e.target.value)} />
                </label>
                <label className="operations-field"><span>Buffer Days (default 1)</span>
                  <input type="number" min={0} max={365} value={bufferDays} onChange={(e) => setBufferDays(e.target.value)} />
                </label>
                <button type="button" className="operations-button" disabled={busy} onClick={saveTimeline}>Save</button>
                <button type="button" className="operations-button secondary" onClick={() => setTimelineOpen(false)}>Cancel</button>
              </div>
            )}
          </div>
        )}

        <h4>Stages (area level)</h4>
        <table className="operations-table pt-stage-table">
          <thead><tr><th>Stage</th><th>Status</th><th>Date</th></tr></thead>
          <tbody>
            {stageRows.map((stage) => {
              const status = row.stage_statuses[stage]
              return (
                <tr key={stage}>
                  <td>{stageLabel(stage)}</td>
                  <td><span className={`operations-status ${stageStatusTone(stage, status)}`}>{status ? label(status) : 'Not started'}</span></td>
                  <td>{fmtDate(row.stage_dates[stage])}</td>
                </tr>
              )
            })}
          </tbody>
        </table>

        <div className="pt-drawer-grid">
          <div><span>Team Lead</span><strong>{row.team_leader || '—'}</strong></div>
          <div><span>Area Production</span><strong>{row.production_user || '—'}</strong></div>
          <div><span>Area QC</span><strong>{row.qc_user || '—'}{row.qc_decision ? ` · ${label(row.qc_decision)}` : ''}</strong></div>
          <div><span>Area QA</span><strong>{row.qa_user || '—'}{row.qa_decision ? ` · ${label(row.qa_decision)}` : ''}</strong></div>
          <div><span>DXF</span><strong>{row.dxf_user || '—'}</strong></div>
          <div><span>Remarks</span><strong>{row.remarks || '—'}</strong></div>
        </div>

        {/* ---------------- FILE / TILE TABLE ---------------- */}
        <h4>
          Files / Tiles {items ? `(${activeCount} active)` : ''}
          {items && (
            <small className="pt-file-rollups">
              Production {items.items.filter((i) => i.is_active && i.production_status === 'completed').length}
              {' · '}QC Passed {items.items.filter((i) => i.is_active && i.qc_status === 'passed').length}
              {' · '}QA Passed {items.items.filter((i) => i.is_active && i.qa_status === 'passed').length}
              {' · '}Delivered {items.items.filter((i) => i.is_active && i.delivery_status === 'delivered').length}
            </small>
          )}
        </h4>
        {itemsError && <div className="operations-alert error">{itemsError}</div>}
        {!items && !itemsError && <div className="pt-drawer-loading"><Loader2 size={16} className="spin" /> Loading files…</div>}

        {(items?.stage_targets?.production || items?.stage_targets?.qc || items?.stage_targets?.qa) && (
          <div className="pt-stage-targets">
            <span>Production target <strong>{fmtDate(items?.stage_targets?.production)}</strong></span>
            <span>QC target <strong>{fmtDate(items?.stage_targets?.qc)}</strong></span>
            <span>QA target <strong>{fmtDate(items?.stage_targets?.qa)}</strong></span>
            <span>QC deadline <strong>{items ? (DEADLINE_LABELS[items.stage_deadlines.qc.status] ?? items.stage_deadlines.qc.status) : '—'}</strong></span>
            <span>QA deadline <strong>{items ? (DEADLINE_LABELS[items.stage_deadlines.qa.status] ?? items.stage_deadlines.qa.status) : '—'}</strong></span>
          </div>
        )}

        {items?.can_manage && (
          <div className="pt-file-controls">
            <button type="button" className="operations-button secondary" disabled={busy} onClick={() => setAddOpen((v) => !v)}>+ Add File</button>
            <label className="operations-button secondary pt-upload-label">
              <Upload size={14} /> Import Excel/CSV
              <input
                type="file"
                accept=".csv,.xlsx,.xls"
                hidden
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  e.target.value = ''
                  if (file) void importFile(file)
                }}
              />
            </label>
          </div>
        )}

        {items?.can_manage && addOpen && (
          <div className="pt-inline-form pt-stack-form">
            <div className="pt-form-row">
              <label className="operations-field"><span>Add one file — number *</span>
                <input value={addNumber} onChange={(e) => setAddNumber(e.target.value)} placeholder="BLDG_001" />
              </label>
              <label className="operations-field"><span>File name (optional)</span>
                <input value={addName} onChange={(e) => setAddName(e.target.value)} placeholder="BLDG_001.dxf" />
              </label>
              <button type="button" className="operations-button" disabled={busy} onClick={addSingle}>Add File</button>
            </div>
            <div className="pt-form-row">
              <label className="operations-field"><span>Add multiple — one per line: NUMBER,Name</span>
                <textarea rows={3} value={bulkText} onChange={(e) => setBulkText(e.target.value)} placeholder={'TILE_001,Tile 1\nTILE_002,Tile 2'} />
              </label>
              <button type="button" className="operations-button" disabled={busy} onClick={addBulk}>Add Multiple</button>
            </div>
            <div className="pt-form-row">
              <label className="operations-field"><span>Generate — prefix</span>
                <input value={genPrefix} onChange={(e) => setGenPrefix(e.target.value)} />
              </label>
              <label className="operations-field"><span>Start</span>
                <input type="number" min={1} value={genStart} onChange={(e) => setGenStart(e.target.value)} />
              </label>
              <label className="operations-field"><span>Count (1–50)</span>
                <input type="number" min={1} max={5000} value={genCount} onChange={(e) => setGenCount(e.target.value)} />
              </label>
              <label className="operations-field"><span>Padding</span>
                <input type="number" min={1} max={10} value={genPadding} onChange={(e) => setGenPadding(e.target.value)} />
              </label>
              <label className="operations-field"><span>Extension</span>
                <input value={genExt} onChange={(e) => setGenExt(e.target.value)} placeholder=".dxf" />
              </label>
              <button type="button" className="operations-button" disabled={busy} onClick={generateSequence}>Generate Sequence</button>
            </div>
          </div>
        )}

        {items?.can_manage && allItems.some((i) => i.is_active) && (
          <div className="pt-inline-form pt-assign-bar">
            <span className="pt-assign-label">Assign {selectedIds.length ? `${selectedIds.length} selected` : 'selected files'}:</span>
            <select value={assignProduction} onChange={(e) => setAssignProduction(e.target.value)}>
              <option value="">Production — keep</option>
              {employees.map((e) => <option key={e.user_id} value={e.user_id}>{e.full_name || `User ${e.user_id}`}</option>)}
            </select>
            <select value={assignQc} onChange={(e) => setAssignQc(e.target.value)}>
              <option value="">QC — keep</option>
              {employees.map((e) => <option key={e.user_id} value={e.user_id}>{e.full_name || `User ${e.user_id}`}</option>)}
            </select>
            <select value={assignQa} onChange={(e) => setAssignQa(e.target.value)}>
              <option value="">QA — keep</option>
              {employees.map((e) => <option key={e.user_id} value={e.user_id}>{e.full_name || `User ${e.user_id}`}</option>)}
            </select>
            <button type="button" className="operations-button" disabled={busy} onClick={assignSelected}>Bulk Assign</button>
          </div>
        )}

        {items && (
          <div className="operations-table-wrap pt-file-table-wrap">
            <table className="operations-table pt-file-table">
              <thead>
                <tr>
                  {items.can_manage && <th><input type="checkbox"
                    checked={selectedIds.length > 0 && selectedIds.length === allItems.filter((i) => i.is_active).length}
                    onChange={(e) => setSelectedIds(e.target.checked ? allItems.filter((i) => i.is_active).map((i) => i.work_package_item_id) : [])} /></th>}
                  <th>File</th>
                  <th>Production</th>
                  <th>QC</th>
                  <th>QA</th>
                  <th>Delivery</th>
                  <th>Delay</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {!allItems.length && (
                  <tr><td colSpan={items.can_manage ? 8 : 7}>
                    <div className="nk-empty">
                      <h3>No files tracked for this area</h3>
                      <p>File/tile tracking is optional — this area continues to work with area-level tracking exactly as before. Team Leads can add files above.</p>
                    </div>
                  </td></tr>
                )}
                {allItems.map((item) => {
                  const myOpen = item.open_session && item.open_session.employee_user_id === me ? item.open_session : null
                  const canStartProd = item.is_active && !item.open_session && (item.production_user_id === me || items.can_manage)
                  const canStartQc = item.is_active && !item.open_session && item.qc_user_id === me
                    && item.production_status === 'completed'
                  const canStartQa = item.is_active && !item.open_session && item.qa_user_id === me
                    && item.qc_status === 'passed'
                  const qaReady = item.qa_status === 'passed' || (!item.qa_user_id && item.qa_status === 'not_started')
                  return (
                    <tr key={item.work_package_item_id} className={item.is_active ? '' : 'pt-row-inactive'}>
                      {items.can_manage && (
                        <td>
                          <input type="checkbox" disabled={!item.is_active}
                            checked={selectedIds.includes(item.work_package_item_id)}
                            onChange={(e) => setSelectedIds((ids) => e.target.checked
                              ? [...ids, item.work_package_item_id]
                              : ids.filter((id) => id !== item.work_package_item_id))} />
                        </td>
                      )}
                      <td>
                        <strong>{item.item_number}</strong>
                        <small>{item.item_name || '—'}{!item.is_active && ' · INACTIVE'}{item.planned_quantity != null ? ` · ${fmtQty(item.planned_quantity)} ${item.planned_unit || ''}` : ''}</small>
                      </td>
                      <td>
                        <small>
                          {item.production_user || '—'}
                          <br />
                          <span className={`operations-status ${stageStatusTone('production', item.production_status)}`}>{label(item.production_status)}</span>
                          {item.production_start && (
                            <><br />{fmtDate(item.production_start)} {fmtTime(item.production_start)} → {item.production_end ? `${fmtDate(item.production_end)} ${fmtTime(item.production_end)}` : '…'}</>
                          )}
                          {item.production_duration_seconds != null && <><br />Duration {fmtDuration(item.production_duration_seconds)}</>}
                          {item.production_files > 0 && <><br />{item.production_files} file(s) · {fmtQty(item.production_quantity)} {item.production_unit || ''}</>}
                        </small>
                      </td>
                      <td>
                        <small>
                          {item.qc_user || '—'}
                          <br />
                          <span className={`operations-status ${stageStatusTone('qc', item.qc_status)}`}>{label(item.qc_status)}</span>
                          {item.qc_start && <><br />{fmtTime(item.qc_start)} → {item.qc_end ? fmtTime(item.qc_end) : '…'}</>}
                          {item.qc_duration_seconds != null && <><br />Duration {fmtDuration(item.qc_duration_seconds)}</>}
                        </small>
                      </td>
                      <td>
                        <small>
                          {item.qa_user || '—'}
                          <br />
                          <span className={`operations-status ${stageStatusTone('qa', item.qa_status)}`}>{label(item.qa_status)}</span>
                          {item.qa_start && <><br />{fmtTime(item.qa_start)} → {item.qa_end ? fmtTime(item.qa_end) : '…'}</>}
                          {item.qa_duration_seconds != null && <><br />Duration {fmtDuration(item.qa_duration_seconds)}</>}
                        </small>
                      </td>
                      <td>
                        <small>
                          <span className={`operations-status ${stageStatusTone('delivery', item.delivery_status)}`}>{label(item.delivery_status)}</span>
                          {item.delivery_at && <><br />{fmtDate(item.delivery_at)} {fmtTime(item.delivery_at)}</>}
                          {item.delivery_by && <><br />by {item.delivery_by}</>}
                        </small>
                      </td>
                      <td title={item.delay_remarks || item.delay_reason || ''}>
                        {item.delay_category ? (
                          <span className={`operations-status ${item.system_malfunction ? 'danger' : 'warning'}`}>
                            {item.system_malfunction ? 'System' : 'Delayed'}
                          </span>
                        ) : '—'}
                        {item.delay_category && <small>{item.delay_category}{item.affected_item_number ? ` · ${item.affected_item_number}` : ''}{item.delay_reason ? ` · ${item.delay_reason}` : ''}</small>}
                      </td>
                      <td className="pt-item-actions">
                        <ItemStageActivityControls
                          item={item}
                          myUserId={me}
                          canDeliver={items.can_deliver}
                          siblings={allItems.map((s) => ({ work_package_item_id: s.work_package_item_id, item_number: s.item_number }))}
                          onChanged={loadItems}
                        />
                        {items.can_manage && item.is_active && !item.open_session && (
                          <button type="button" className="operations-button secondary" disabled={busy} onClick={() => toggleActive(item, false)}>Deactivate</button>
                        )}
                        {items.can_manage && !item.is_active && (
                          <button type="button" className="operations-button secondary" disabled={busy} onClick={() => toggleActive(item, true)}>Reactivate</button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {items && items.employee_totals.length > 0 && (
          <>
            <h4>Employee-wise output</h4>
            <table className="operations-table pt-stage-table">
              <thead><tr><th>Employee</th><th>Files Completed</th><th>Quantity</th><th>Time Worked</th></tr></thead>
              <tbody>
                {items.employee_totals.map((t) => (
                  <tr key={`${t.employee_user_id}-${t.unit ?? ''}`}>
                    <td>{t.employee || `User #${t.employee_user_id}`}</td>
                    <td>{t.files_completed}</td>
                    <td>{fmtQty(t.quantity_completed)} {t.unit || ''}</td>
                    <td>{fmtDuration(t.duration_seconds)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}

        {items && (
          <ReadinessPanel
            readiness={items.readiness}
            canConfirm={items.can_confirm_ready}
            busy={busy}
            onConfirm={markReady}
          />
        )}

        <h4><History size={14} /> Area History</h4>
        {historyError && <div className="operations-alert error">{historyError}</div>}
        {history === null && !historyError && <div className="pt-drawer-loading"><Loader2 size={16} className="spin" /> Loading history…</div>}
        {history !== null && !history.length && <p className="pt-drawer-text">No history recorded yet.</p>}
        {history !== null && history.length > 0 && (
          <ul className="pt-history">
            {history.slice().reverse().map((event, index) => (
              <li key={`${event.kind}-${event.at}-${index}`}>
                <span>
                  {fmtDate(event.date ?? event.at)} · {stageLabel(event.stage ?? event.kind.replace('_review', '').replace('_', ' '))}
                  {event.actor_name ? ` · ${event.actor_name}` : ''}
                  {event.to_status ? ` · ${label(event.to_status)}` : ''}
                  {event.quantity !== null && event.quantity !== undefined ? ` · ${fmtQty(event.quantity)} ${event.unit ?? ''}` : ''}
                  {event.hours !== null && event.hours !== undefined ? ` · ${event.hours} h` : ''}
                  {event.files !== null && event.files !== undefined ? ` · ${event.files} files` : ''}
                </span>
                {(event.remarks || event.blockers) && (
                  <small>{event.blockers ? `Blocker: ${event.blockers} · ` : ''}{event.remarks || ''}</small>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <footer className="pt-drawer-foot">
        {readOnly ? (
          <Link className="operations-button secondary" to={`/ortho/project-360/${row.project_id}`}>Open Project 360</Link>
        ) : (
          <Link className="operations-button secondary" to={`/ortho?project=${row.project_id}`}>Open in Project Operations</Link>
        )}
      </footer>
    </aside>
  )
}
