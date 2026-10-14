import { FileSpreadsheet, Loader2, Upload } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { apiFetch, uploadExcel } from '../../../lib/api'

// V8.3 Team Lead Excel-driven work allocation — SHARED by Project Operations (/ortho, the
// authoritative entry point) and Production Tracking (which only links here). Both pages use
// the exact same backend endpoints, so there is one source of truth:
//   master-import/preview · master-import/commit · allocation-options · area-files · assign-files

export type MasterPreview = {
  filename: string
  project_id: number
  project_code: string
  rows: number
  valid: number
  errors: number
  lots: number
  codes: number
  areas: number
  files: number
  new_rows: number
  skipped_existing: number
  conflicts: { row: number; lot: string; code: string; area_name: string; item_number: string; reason: string }[]
  planned_by_unit: { measurement_type: string; unit: string; quantity: number; rows: number }[]
  lot_list: string[]
}

export type AllocationArea = {
  work_package_id: number
  lot?: string | null
  code?: string | null
  area_name?: string | null
  planned_quantity?: number | null
  planned_unit?: string | null
  supply_date?: string | null
  declared_total_files?: number | null
  file_count: number
  assigned_files?: number
  available_files?: number
  files_completed: number
  production_status: string
  qc_status: string
  qa_status: string
  ready_for_delivery: boolean
  delivered_files: number
}

export type AllocationOptions = {
  project_id: number
  project_code: string
  team_lead_user_id?: number | null
  lots: { lot: string; areas: { code?: string | null; area_name?: string | null; work_package_id: number }[] }[]
  areas: AllocationArea[]
  team: {
    production: { user_id: number; full_name?: string | null }[]
    qc: { user_id: number; full_name?: string | null }[]
    qa: { user_id: number; full_name?: string | null }[]
  }
}

export type AreaFilesResponse = {
  work_package_id: number
  package_code: string
  area_name: string
  lot?: string | null
  planned_quantity?: number | null
  planned_unit?: string | null
  supply_date?: string | null
  declared_total_files?: number | null
  total_files?: number
  assigned_files?: number
  available_files?: number
  remarks?: string | null
  files: {
    work_package_item_id: number
    item_number: string
    item_name?: string | null
    planned_quantity?: number | null
    planned_unit?: string | null
    production_status: string
    production_user_id?: number | null
    production_user?: string | null
    production_target_date?: string | null
    qc_user_id?: number | null
    qa_user_id?: number | null
    qc_user?: string | null
    qa_user?: string | null
    qc_attempts?: number
    qa_attempts?: number
  }[]
  planned_groups: { measurement_type: string; unit: string; quantity: number; rows: number }[]
}

/** One Production employee's assignment draft/saved card for the selected area. */
type ProdAssignment = {
  key: string
  userId: string
  itemIds: number[]
  targetDate: string
  instructions: string
  editing: boolean
}

function fmtQty(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return Number.isInteger(value) ? String(value) : String(Math.round(value * 1000) / 1000)
}

// ===========================================================================================
// STEP 1 — WORK FILE MASTER (upload -> preview -> transactional confirm)
// ===========================================================================================

export function MasterImportPanel({ projectId, onImported }: { projectId: number; onImported: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<MasterPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function previewMaster(selected: File) {
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await uploadExcel(
        `/operations/workflow/ortho/projects/${projectId}/master-import/preview`, selected,
      ) as unknown as MasterPreview
      setFile(selected)
      setPreview(result)
    } catch (e) {
      setPreview(null); setFile(null)
      setError(e instanceof Error ? e.message : 'Preview failed')
    } finally {
      setBusy(false)
    }
  }

  async function confirmMaster() {
    if (!file) return
    setBusy(true); setError(''); setNotice('')
    try {
      const summary = await uploadExcel(
        `/operations/workflow/ortho/projects/${projectId}/master-import/commit`, file,
      ) as unknown as {
        created_packages: number; created_items: number; skipped_existing: number
        conflicts: { reason: string }[]
      }
      setNotice(
        `Imported ${summary.created_items} file(s) into ${summary.created_packages} new area(s)`
        + (summary.skipped_existing ? ` · ${summary.skipped_existing} already present (skipped)` : '')
        + (summary.conflicts.length
          ? ` · ${summary.conflicts.length} with existing work history (skipped, never overwritten)`
          : '')
        + '.',
      )
      setPreview(null)
      setFile(null)
      onImported()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="operations-panel pt-master-panel">
      <header>
        <div>
          <span className="operations-kicker">TEAM LEAD · STEP 1 · WORK FILE MASTER</span>
          <h2>Upload the work file master (Excel)</h2>
          <p>
            Columns: MARCHE LOTTO 3 · CODE · AREA NAME · FILE NUMBER · PLANNED LENGTH · UOM ·
            REMARKS (optional) · FILE NAME (optional). For count-based areas use TOTAL FILES instead
            of FILE NUMBER — the ERP then creates File 1..N for that Lot/Code/Area (no per-file
            length is invented). You will see a preview first — nothing is saved until you confirm,
            and files that already have work history are never overwritten.
          </p>
        </div>
        <label className="operations-button">
          <Upload size={15} /> {busy ? 'Working…' : 'Upload Excel'}
          <input
            type="file"
            accept=".csv,.xlsx,.xls"
            hidden
            disabled={busy}
            onChange={(e) => {
              const chosen = e.target.files?.[0]
              e.target.value = ''
              if (chosen) void previewMaster(chosen)
            }}
          />
        </label>
      </header>
      {error && <div className="operations-alert error">{error}</div>}
      {notice && <div className="operations-alert success">{notice}</div>}
      {preview && (
        <div className="pt-preview">
          <div className="pt-preview-head">
            <strong><FileSpreadsheet size={14} /> {preview.filename}</strong>
            <span>Project {preview.project_code}</span>
          </div>
          <div className="pt-preview-grid">
            <div><span>Rows</span><strong>{preview.rows}</strong></div>
            <div><span>Valid</span><strong>{preview.valid}</strong></div>
            <div><span>Errors</span><strong>{preview.errors}</strong></div>
            <div><span>Lots</span><strong>{preview.lots}</strong></div>
            <div><span>Codes</span><strong>{preview.codes}</strong></div>
            <div><span>Areas</span><strong>{preview.areas}</strong></div>
            <div><span>Files</span><strong>{preview.files}</strong></div>
            <div><span>New rows</span><strong>{preview.new_rows}</strong></div>
            <div><span>Already present</span><strong>{preview.skipped_existing}</strong></div>
            <div><span>With history (skipped)</span><strong>{preview.conflicts.length}</strong></div>
          </div>
          <div className="pt-preview-planned">
            <strong>Planned Quantity</strong>
            <span>
              {preview.planned_by_unit.length
                ? preview.planned_by_unit.map((g) => `${g.quantity} ${g.unit}`).join(' + ')
                : '—'}
            </span>
          </div>
          {preview.conflicts.length > 0 && (
            <ul className="pt-preview-conflicts">
              {preview.conflicts.slice(0, 10).map((c) => (
                <li key={`${c.row}-${c.item_number}`}>
                  Row {c.row} · {c.lot} / {c.code} / {c.area_name} · file {c.item_number} — {c.reason}
                </li>
              ))}
            </ul>
          )}
          <div className="operations-actions">
            <button type="button" className="operations-button secondary" disabled={busy}
              onClick={() => { setPreview(null); setFile(null) }}>
              Cancel
            </button>
            <button type="button" className="operations-button" disabled={busy} onClick={confirmMaster}>
              {busy ? 'Importing…' : 'Confirm Import'}
            </button>
          </div>
        </div>
      )}
    </section>
  )
}

// ===========================================================================================
// STEP 2 — ALLOCATE IMPORTED WORK (Lot -> Code -> Area -> Files + stage targets)
// ===========================================================================================

export function ImportedAllocationPanel({ projectId, onAssigned }: { projectId: number; onAssigned: () => void }) {
  const [options, setOptions] = useState<AllocationOptions | null>(null)
  const [loadError, setLoadError] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [lot, setLot] = useState('')
  const [code, setCode] = useState('')
  const [areaId, setAreaId] = useState('')
  const [files, setFiles] = useState<AreaFilesResponse | null>(null)
  // Production is built per employee: an employee's own card owns its exact physical files.
  const [prodBlocks, setProdBlocks] = useState<ProdAssignment[]>([])
  const [supplyDate, setSupplyDate] = useState('')
  const [qcUser, setQcUser] = useState('')
  const [qcTarget, setQcTarget] = useState('')
  const [qaUser, setQaUser] = useState('')
  const [qaTarget, setQaTarget] = useState('')
  const [note, setNote] = useState('')

  function loadOptions() {
    setLoadError('')
    void apiFetch<AllocationOptions>(`/operations/workflow/ortho/projects/${projectId}/allocation-options`)
      .then(setOptions)
      .catch((e) => setLoadError(e instanceof Error ? e.message : 'Unable to load allocation data'))
  }
  useEffect(loadOptions, [projectId])

  const lots = options?.lots ?? []
  const activeLot = lot || (lots.length === 1 ? lots[0].lot : '')
  const codes = useMemo(() => {
    const chosen = lots.find((l) => l.lot === activeLot)
    const seen = new Map<string, string>()
    for (const area of chosen?.areas ?? []) {
      if (area.code && !seen.has(area.code)) seen.set(area.code, area.code)
    }
    return [...seen.keys()]
  }, [lots, activeLot])
  const activeCode = code || (codes.length === 1 ? codes[0] : '')
  const areas = useMemo(
    () => lots.find((l) => l.lot === activeLot)?.areas.filter((a) => a.code === activeCode) ?? [],
    [lots, activeLot, activeCode],
  )
  const activeAreaId = areaId || (areas.length === 1 ? String(areas[0].work_package_id) : '')

  function loadFiles(workPackageId: string) {
    setFiles(null)
    setProdBlocks([])
    if (!workPackageId) return
    void apiFetch<AreaFilesResponse>(`/operations/workflow/ortho/work-packages/${workPackageId}/area-files`)
      .then(setFiles)
      .catch((e) => setError(e instanceof Error ? e.message : 'Unable to load files'))
  }
  useEffect(() => { loadFiles(activeAreaId) }, [activeAreaId])

  const areaFiles = files?.files ?? []

  /** A file is LOCKED once real work exists — it can never be silently reassigned. */
  function isLocked(f: AreaFilesResponse['files'][number]): boolean {
    return (!!f.production_status && f.production_status !== 'not_started')
      || (f.qc_attempts ?? 0) > 0 || (f.qa_attempts ?? 0) > 0
  }

  /** Saved assignments grouped by owner — server state is the single source of truth. */
  const savedGroups = useMemo(() => {
    const map = new Map<number, { userId: number; name: string; files: typeof areaFiles; target: string | null }>()
    for (const f of areaFiles) {
      if (!f.production_user_id) continue
      const g = map.get(f.production_user_id) ?? {
        userId: f.production_user_id, name: f.production_user || `User ${f.production_user_id}`,
        files: [] as typeof areaFiles, target: f.production_target_date ?? null,
      }
      g.files.push(f)
      map.set(f.production_user_id, g)
    }
    return [...map.values()].sort((a, b) => a.name.localeCompare(b.name))
  }, [areaFiles])

  const usedProdIds = useMemo(() => new Set(savedGroups.map((g) => g.userId)), [savedGroups])
  // ONLY PM-selected Production team members of THIS project; already-assigned employees
  // are excluded from NEW assignment cards (one card per employee).
  const prodMembers = options?.team.production ?? []
  const unusedProdMembers = prodMembers.filter((m) => !usedProdIds.has(m.user_id))
  const totalFiles = files?.total_files ?? areaFiles.length
  const assignedCount = areaFiles.filter((f) => f.production_user_id).length
  const availableCount = Math.max(0, totalFiles - assignedCount)

  /** Files a block may select: unassigned, or already owned by that same employee (edit). */
  function selectableFor(block: ProdAssignment) {
    return areaFiles.filter((f) => !isLocked(f)
      && (!f.production_user_id || String(f.production_user_id) === block.userId))
  }

  function newBlock(seedUser = ''): ProdAssignment {
    return {
      key: `b${Date.now()}${Math.random().toString(36).slice(2, 7)}`,
      userId: seedUser, itemIds: [], targetDate: '', instructions: '', editing: false,
    }
  }

  function addEmployee() {
    // Exactly ONE unused eligible employee remains -> preselect them automatically.
    const seed = unusedProdMembers.length === 1 ? String(unusedProdMembers[0].user_id) : ''
    setProdBlocks((b) => [...b, newBlock(seed)])
  }

  function editAssignment(group: { userId: number; files: typeof areaFiles }) {
    setProdBlocks((b) => [...b, {
      ...newBlock(String(group.userId)),
      itemIds: group.files.filter((f) => !isLocked(f)).map((f) => f.work_package_item_id),
      targetDate: group.files.find((f) => f.production_target_date)?.production_target_date ?? '',
      editing: true,
    }])
  }

  function patchBlock(key: string, patch: Partial<ProdAssignment>) {
    setProdBlocks((b) => b.map((x) => (x.key === key ? { ...x, ...patch } : x)))
  }

  async function assignBlock(block: ProdAssignment) {
    if (!activeAreaId) { setError('Select Lot, Code and Area first.'); return }
    if (!block.userId) { setError('Select a Production employee for this assignment.'); return }
    if (!block.itemIds.length) { setError('Select at least one file for this assignment.'); return }
    if (!qcUser || !qaUser) { setError('QC and QA employees are required.'); return }
    if (!block.targetDate || !qcTarget || !qaTarget) {
      setError('Production, QC and QA target dates are all required.'); return
    }
    if (!(block.targetDate <= qcTarget && qcTarget <= qaTarget)) {
      setError('Target dates must satisfy Production ≤ QC ≤ QA.'); return
    }
    setBusy(true); setError(''); setNotice('')
    try {
      const summary = await apiFetch<{ assigned_files: number }>(
        `/operations/workflow/ortho/work-packages/${activeAreaId}/assign-files`,
        {
          method: 'POST',
          body: JSON.stringify({
            item_ids: block.itemIds,
            production_user_id: Number(block.userId),
            production_target_date: block.targetDate,
            qc_user_id: Number(qcUser),
            qc_target_date: qcTarget,
            qa_user_id: Number(qaUser),
            qa_target_date: qaTarget,
            supply_date: supplyDate || null,
            note: block.instructions.trim() || note.trim() || null,
            // Explicit edit/reassign; the backend still refuses started/history files.
            reassign: block.editing,
          }),
        },
      )
      setNotice(`${summary.assigned_files} file(s) allocated. Production, QC and QA employees notified.`)
      setProdBlocks((b) => b.filter((x) => x.key !== block.key))
      // Authoritative refresh — files, ownership, availability and cards come from the server.
      loadFiles(activeAreaId)
      loadOptions()
      onAssigned()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Allocation failed')
    } finally {
      setBusy(false)
    }
  }

  const area = options?.areas.find((a) => String(a.work_package_id) === activeAreaId)

  return (
    <section className="operations-panel pt-alloc-panel">
      <header>
        <div>
          <span className="operations-kicker">TEAM LEAD · STEP 2 · ALLOCATE IMPORTED WORK</span>
          <h2>Lot → Code → Area → Files</h2>
          <p>
            Lot, Code, Area, File Number, Planned Length and UOM come from the imported work file
            master — no manual entry. Only the allocation decisions (Supply Date, employees and the
            three stage target dates) are filled here.
          </p>
        </div>
      </header>
      {loadError && <div className="operations-alert error">{loadError}</div>}
      {notice && <div className="operations-alert success">{notice}</div>}
      {error && <div className="operations-alert error">{error}</div>}
      {!options ? (
        <div className="pt-drawer-loading"><Loader2 size={16} className="spin" /> Loading allocation data…</div>
      ) : !options.areas.length ? (
        <div className="nk-empty">
          <h3>No imported work yet</h3>
          <p>Upload the work file master above (STEP 1) — the imported areas and files appear here for allocation.</p>
        </div>
      ) : (
        <div className="pt-alloc">
          <div className="pt-form-row">
            <label className="operations-field"><span>Lot / Batch</span>
              <select value={activeLot} onChange={(e) => { setLot(e.target.value); setCode(''); setAreaId('') }}>
                <option value="">Select lot</option>
                {lots.map((l) => <option key={l.lot} value={l.lot}>{l.lot}</option>)}
              </select>
            </label>
            <label className="operations-field"><span>Code</span>
              <select value={activeCode} onChange={(e) => { setCode(e.target.value); setAreaId('') }}>
                <option value="">Select code</option>
                {codes.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
            <label className="operations-field"><span>Area</span>
              <select value={activeAreaId} onChange={(e) => setAreaId(e.target.value)}>
                <option value="">Select area</option>
                {areas.map((a) => (
                  <option key={a.work_package_id} value={a.work_package_id}>{a.area_name}</option>
                ))}
              </select>
            </label>
          </div>

          {area && (
            <div className="pt-alloc-summary">
              <div><span>Planned quantity</span><strong>{fmtQty(area.planned_quantity)} {area.planned_unit || ''}</strong></div>
              <div><span>Total files</span><strong>{area.declared_total_files ?? area.file_count}</strong></div>
              <div><span>Assigned</span><strong>{area.assigned_files ?? 0}</strong></div>
              <div><span>Available</span><strong>{area.available_files ?? area.file_count}</strong></div>
              <div><span>Production</span><strong>{area.production_status}</strong></div>
              <div><span>QC</span><strong>{area.qc_status}</strong></div>
              <div><span>QA</span><strong>{area.qa_status}</strong></div>
              <div><span>Delivery readiness</span><strong>{area.ready_for_delivery ? 'Ready for Delivery' : 'Not ready'}</strong></div>
            </div>
          )}

          {files && (
            <>
              {/* Imported master remarks are READ-ONLY here — allocation must never edit them. */}
              {files.remarks && (
                <div className="operations-note">
                  <strong>Imported master remarks (read-only):</strong> {files.remarks}
                </div>
              )}
              <div className="pt-alloc-summary">
                <div><span>Total files</span><strong>{totalFiles}</strong></div>
                <div><span>Assigned</span><strong>{assignedCount}</strong></div>
                <div><span>Available</span><strong>{availableCount}</strong></div>
              </div>

              <div className="pt-alloc-files">
                <strong>Production Assignments</strong>
                {!savedGroups.length && !prodBlocks.length && (
                  <div className="operations-note">
                    No Production assignment yet — click “+ Add Employee” to assign exact files to a
                    PM-selected Production team member.
                  </div>
                )}

                {savedGroups.map((g) => (
                  <div className="pt-alloc-assignment" key={g.userId}>
                    <div className="pt-alloc-assignment-head">
                      <strong>{g.name}</strong>
                      <span>{g.files.length} assigned</span>
                      {g.target && <span>Target: {g.target}</span>}
                    </div>
                    <div className="operations-project-meta">
                      <span>Assigned Files: {g.files.map((f) => f.item_number).join(', ')}</span>
                      <span>Status: {g.files.filter(isLocked).length} started · {g.files.filter((f) => !isLocked(f)).length} not started</span>
                    </div>
                    <div className="operations-actions">
                      <button type="button" className="operations-button secondary" disabled={busy}
                        onClick={() => editAssignment(g)}>Edit Assignment</button>
                    </div>
                  </div>
                ))}

                {prodBlocks.map((block, index) => {
                  const selectable = selectableFor(block)
                  const lockedFiles = areaFiles.filter(isLocked)
                  const memberOptions = block.editing
                    ? prodMembers.filter((m) => String(m.user_id) === block.userId)
                    : prodMembers.filter((m) => !usedProdIds.has(m.user_id))
                  return (
                    <div className="pt-alloc-assignment" key={block.key}>
                      <div className="pt-alloc-assignment-head">
                        <strong>PRODUCTION ASSIGNMENT {savedGroups.length + index + 1}{block.editing ? ' · EDIT' : ''}</strong>
                      </div>
                      <div className="pt-form-row">
                        <label className="operations-field"><span>Production Employee</span>
                          <select value={block.userId} disabled={block.editing}
                            onChange={(e) => patchBlock(block.key, { userId: e.target.value, itemIds: [] })}>
                            <option value="">Select</option>
                            {/* PM-selected Production members of THIS project only. */}
                            {memberOptions.map((u) => (
                              <option key={u.user_id} value={u.user_id}>{u.full_name || `User ${u.user_id}`}</option>
                            ))}
                          </select>
                        </label>
                        <label className="operations-field"><span>Production Target Date</span>
                          <input type="date" value={block.targetDate}
                            onChange={(e) => patchBlock(block.key, { targetDate: e.target.value })} />
                        </label>
                        <label className="operations-field pt-span"><span>Team Lead Instructions (optional)</span>
                          <input value={block.instructions}
                            onChange={(e) => patchBlock(block.key, { instructions: e.target.value })}
                            placeholder="Instructions for this employee" />
                        </label>
                      </div>
                      <div className="pt-alloc-file-list">
                        <div className="pt-alloc-file-actions">
                          <button type="button" className="operations-button secondary" disabled={busy}
                            onClick={() => patchBlock(block.key, {
                              itemIds: selectable.map((f) => f.work_package_item_id),
                            })}>Select All Available</button>
                          <button type="button" className="operations-button secondary" disabled={busy}
                            onClick={() => patchBlock(block.key, { itemIds: [] })}>Clear</button>
                          <span className="pt-auto-tag">{block.itemIds.length} file(s) selected</span>
                        </div>
                        {!selectable.length && (
                          <div className="operations-note">
                            No available files remain for this employee (unassigned and not started).
                          </div>
                        )}
                        {selectable.map((f) => (
                          <label className="operations-check" key={f.work_package_item_id}>
                            <input type="checkbox"
                              checked={block.itemIds.includes(f.work_package_item_id)}
                              onChange={(e) => patchBlock(block.key, {
                                itemIds: e.target.checked
                                  ? [...block.itemIds, f.work_package_item_id]
                                  : block.itemIds.filter((id) => id !== f.work_package_item_id),
                              })} />
                            <span>
                              File {f.item_number}{f.item_name ? ` — ${f.item_name}` : ''} · {fmtQty(f.planned_quantity)} {f.planned_unit || ''} · Remarks: —
                            </span>
                          </label>
                        ))}
                        {lockedFiles.length > 0 && (
                          <div className="operations-note">
                            Locked — cannot be reassigned after work has started:{' '}
                            {lockedFiles.map((f) => `File ${f.item_number}${f.production_user ? ` (${f.production_user})` : ''}`).join(' · ')}
                          </div>
                        )}
                      </div>
                      <div className="operations-actions">
                        <button type="button" className="operations-button" disabled={busy} onClick={() => assignBlock(block)}>
                          {block.editing ? 'Save Assignment' : 'Assign'}
                        </button>
                        <button type="button" className="operations-button secondary" disabled={busy}
                          onClick={() => setProdBlocks((b) => b.filter((x) => x.key !== block.key))}>Cancel</button>
                      </div>
                    </div>
                  )
                })}

                <div className="operations-actions">
                  {unusedProdMembers.length > 0
                    ? (
                      <button type="button" className="operations-button secondary" disabled={busy} onClick={addEmployee}>
                        + Add Employee
                      </button>
                    )
                    : (
                      <span className="operations-note">
                        No additional Production team members are available for this project.
                      </span>
                    )}
                </div>
              </div>
            </>
          )}

          <div className="pt-form-row">
            <label className="operations-field"><span>Supply Date</span>
              <input type="date" value={supplyDate || (files?.supply_date ?? '')} onChange={(e) => setSupplyDate(e.target.value)} />
            </label>
            <label className="operations-field"><span>QC employee</span>
              <select value={qcUser} onChange={(e) => setQcUser(e.target.value)}>
                <option value="">Select</option>
                {/* PM-selected QC members of THIS project only. */}
                {options.team.qc.map((u) => <option key={u.user_id} value={u.user_id}>{u.full_name || `User ${u.user_id}`}</option>)}
              </select>
            </label>
            <label className="operations-field"><span>QC Target Date</span>
              <input type="date" value={qcTarget} onChange={(e) => setQcTarget(e.target.value)} />
            </label>
            <label className="operations-field"><span>QA employee</span>
              <select value={qaUser} onChange={(e) => setQaUser(e.target.value)}>
                <option value="">Select</option>
                {/* PM-selected QA members of THIS project only. */}
                {options.team.qa.map((u) => <option key={u.user_id} value={u.user_id}>{u.full_name || `User ${u.user_id}`}</option>)}
              </select>
            </label>
            <label className="operations-field"><span>QA Target Date</span>
              <input type="date" value={qaTarget} onChange={(e) => setQaTarget(e.target.value)} />
            </label>
            <label className="operations-field pt-span"><span>General Instructions (optional)</span>
              <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Applies to the whole area when no per-employee instructions are set" />
            </label>
          </div>
          <div className="operations-actions">
            <span className="pt-auto-tag">
              Each “Assign” sends that employee’s exact files to Production/QC/QA and notifies them.
            </span>
          </div>
        </div>
      )}
    </section>
  )
}
