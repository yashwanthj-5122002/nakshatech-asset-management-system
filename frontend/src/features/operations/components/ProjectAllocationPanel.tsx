import { Loader2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch } from '../../../lib/api'

// ===========================================================================================
// V8.6 PROJECT-SCOPE Team Lead allocation.
//
// ONE allocation action may assign physical files belonging to DIFFERENT Lots / Codes / Areas
// to ONE Production employee. The backend operation is ATOMIC (validate-all-then-write), so a
// rejected selection never leaves a partial allocation behind.
//
// Single source of truth: the physical file identity is the persistent WorkPackageItem id —
// a FILE NUMBER is only unique INSIDE its area ("Area A File 1" != "Area B File 1").
// ===========================================================================================

export type AllocationFile = {
  work_package_id: number
  work_package_item_id: number
  lot_or_batch?: string | null
  code?: string | null
  area?: string | null
  file_number: string
  file_name?: string | null
  remarks?: string | null
  planned_quantity?: number | null
  unit?: string | null
  planned_unit?: string | null
  production_employee_id?: number | null
  production_employee_name?: string | null
  status: string
  production_status: string
  qc_status: string
  qa_status: string
  is_available: boolean
  safe_reassign: boolean
}

export type ProjectAllocationOptions = {
  project_id: number
  project_code: string
  team_lead_user_id?: number | null
  files?: AllocationFile[]
  total_files?: number
  assigned_files?: number
  available_files?: number
  areas: {
    work_package_id: number
    lot?: string | null
    code?: string | null
    area_name?: string | null
    planned_quantity?: number | null
    planned_unit?: string | null
    declared_total_files?: number | null
    file_count: number
    assigned_files?: number
    available_files?: number
  }[]
  team: {
    production: { user_id: number; full_name?: string | null }[]
    qc: { user_id: number; full_name?: string | null }[]
    qa: { user_id: number; full_name?: string | null }[]
  }
}

type Draft = {
  key: string
  userId: string
  itemIds: number[]
  prodTarget: string
  qcUser: string
  qcTarget: string
  qaUser: string
  qaTarget: string
  instructions: string
  editing: boolean
}

function fileLabel(f: AllocationFile): string {
  return [
    (f.lot_or_batch || '').trim() || '—',
    (f.code || '').trim() || '—',
    (f.area || '').trim() || '—',
    `File ${f.file_number}`,
    f.file_name ? f.file_name : '',
  ].filter(Boolean).join(' | ')
}

function newDraft(seedUser = ''): Draft {
  return {
    key: `d${Date.now()}${Math.random().toString(36).slice(2, 7)}`,
    userId: seedUser, itemIds: [], prodTarget: '', qcUser: '', qcTarget: '', qaUser: '', qaTarget: '',
    instructions: '', editing: false,
  }
}

export function ImportedAllocationPanel({ projectId, onAssigned }: { projectId: number; onAssigned: () => void }) {
  const [options, setOptions] = useState<ProjectAllocationOptions | null>(null)
  const [loadError, setLoadError] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [expanded, setExpanded] = useState<number | null>(null)
  const [filter, setFilter] = useState('')
  // Compact "Files" combobox: the picker only appears when the field is opened.
  const [filesOpen, setFilesOpen] = useState(false)
  const filesBoxRef = useRef<HTMLDivElement | null>(null)
  const rangeAnchor = useRef<number | null>(null)

  useEffect(() => {
    if (!filesOpen) return
    function onDown(event: MouseEvent) {
      if (!filesBoxRef.current?.contains(event.target as Node)) setFilesOpen(false)
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setFilesOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [filesOpen])

  function loadOptions() {
    setLoadError('')
    void apiFetch<ProjectAllocationOptions>(
      `/operations/workflow/ortho/projects/${projectId}/allocation-options`,
    )
      .then(setOptions)
      .catch((e) => setLoadError(e instanceof Error ? e.message : 'Unable to load allocation data'))
  }
  useEffect(loadOptions, [projectId])

  const files = useMemo(() => options?.files ?? [], [options])
  const totalFiles = options?.total_files ?? files.length
  const assignedFiles = options?.assigned_files ?? files.filter((f) => f.production_employee_id).length
  const availableFiles = options?.available_files ?? Math.max(0, totalFiles - assignedFiles)

  // Allocations grouped by Production employee — the card is derived from authoritative state.
  const allocations = useMemo(() => {
    const map = new Map<number, { userId: number; name: string; files: AllocationFile[] }>()
    for (const f of files) {
      if (!f.production_employee_id) continue
      const g = map.get(f.production_employee_id) ?? {
        userId: f.production_employee_id,
        name: f.production_employee_name || `User ${f.production_employee_id}`,
        files: [] as AllocationFile[],
      }
      g.files.push(f)
      map.set(f.production_employee_id, g)
    }
    return [...map.values()].sort((a, b) => a.name.localeCompare(b.name))
  }, [files])
  const usedProdIds = useMemo(() => new Set(allocations.map((a) => a.userId)), [allocations])

  // PM-selected Production members of THIS project only.
  const prodMembers = options?.team.production ?? []
  const unusedProdMembers = prodMembers.filter((m) => !usedProdIds.has(m.user_id))

  // Selectable for the draft: unassigned files, or files already owned by the draft employee
  // (explicit edit/reassign of an unstarted file). Assigned-with-history files stay locked.
  function selectableFor(d: Draft): AllocationFile[] {
    return files.filter((f) => {
      if (!d.userId) return false
      const owned = Boolean(f.production_employee_id)
      if (!owned) return true
      if (String(f.production_employee_id) !== d.userId) return false
      return d.editing && f.safe_reassign
    })
  }

  /** Checkbox click, plus SHIFT+click range selection over the currently listed files. */
  function toggleFile(id: number, shiftKey: boolean, orderedIds: number[]) {
    setDraft((d) => {
      if (!d) return d
      if (shiftKey && rangeAnchor.current !== null && orderedIds.includes(rangeAnchor.current)) {
        const from = orderedIds.indexOf(rangeAnchor.current)
        const to = orderedIds.indexOf(id)
        const [lo, hi] = from <= to ? [from, to] : [to, from]
        return { ...d, itemIds: Array.from(new Set([...d.itemIds, ...orderedIds.slice(lo, hi + 1)])) }
      }
      rangeAnchor.current = id
      return {
        ...d,
        itemIds: d.itemIds.includes(id) ? d.itemIds.filter((x) => x !== id) : [...d.itemIds, id],
      }
    })
  }

  function addEmployee() {
    const seed = unusedProdMembers.length === 1 ? String(unusedProdMembers[0].user_id) : ''
    setDraft(newDraft(seed))
  }

  function editAllocation(userId: number) {
    const group = allocations.find((a) => a.userId === userId)
    if (!group) return
    setDraft({
      ...newDraft(String(userId)),
      itemIds: group.files.filter((f) => f.safe_reassign).map((f) => f.work_package_item_id),
      prodTarget: '', qcUser: '', qcTarget: '', qaUser: '', qaTarget: '',
      editing: true,
    })
  }

  async function assign(d: Draft) {
    if (!d.userId) { setError('Select a Production employee.'); return }
    if (!d.itemIds.length) { setError('Select at least one file.'); return }
    if (!d.qcUser || !d.qaUser) { setError('QC and QA employees are required.'); return }
    if (!d.prodTarget || !d.qcTarget || !d.qaTarget) {
      setError('Production, QC and QA target dates are all required.'); return
    }
    if (!(d.prodTarget <= d.qcTarget && d.qcTarget <= d.qaTarget)) {
      setError('Target dates must satisfy Production ≤ QC ≤ QA.'); return
    }
    setBusy(true); setError(''); setNotice('')
    try {
      const summary = await apiFetch<{ assigned_files: number; areas: string[]; work_packages: number }>(
        `/operations/workflow/ortho/projects/${projectId}/assign-files`,
        {
          method: 'POST',
          body: JSON.stringify({
            item_ids: d.itemIds,
            production_user_id: Number(d.userId),
            production_target_date: d.prodTarget,
            qc_user_id: Number(d.qcUser),
            qc_target_date: d.qcTarget,
            qa_user_id: Number(d.qaUser),
            qa_target_date: d.qaTarget,
            supply_date: null,
            note: d.instructions.trim() || null,
            reassign: d.editing,
          }),
        },
      )
      setNotice(
        `${summary.assigned_files} file(s) allocated across ${summary.work_packages} area(s). `
        + 'Production, QC and QA employees were notified.',
      )
      setDraft(null)
      // AUTHORITATIVE refetch — never trust local state after an allocation.
      loadOptions()
      onAssigned()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Allocation failed')
    } finally {
      setBusy(false)
    }
  }

  const visible = draft
    ? selectableFor(draft).filter((f) => {
      const q = filter.trim().toLowerCase()
      if (!q) return true
      return fileLabel(f).toLowerCase().includes(q)
    })
    : []
  const byArea = useMemo(() => {
    const map = new Map<string, AllocationFile[]>()
    for (const f of visible) {
      const key = [(f.lot_or_batch || '').trim(), (f.code || '').trim(), (f.area || '').trim()]
        .filter(Boolean).join(' | ') || 'Unnamed area'
      const list = map.get(key) ?? []
      list.push(f)
      map.set(key, list)
    }
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]))
  }, [visible])

  if (!options) {
    return (
      <section className="operations-panel pt-alloc-panel">
        <header>
          <div>
            <span className="operations-kicker">TEAM LEAD · STEP 2 · ALLOCATE IMPORTED WORK</span>
            <h2>Project-wide file allocation</h2>
          </div>
        </header>
        {loadError
          ? <div className="operations-alert error">{loadError}</div>
          : <div className="pt-drawer-loading"><Loader2 size={16} className="spin" /> Loading allocation data…</div>}
      </section>
    )
  }

  return (
    <section className="operations-panel pt-alloc-panel">
      <header>
        <div>
          <span className="operations-kicker">TEAM LEAD · STEP 2 · ALLOCATE IMPORTED WORK</span>
          <h2>Project-wide file allocation</h2>
          <p>
            Select exact physical files from any Lot / Code / Area of this project and assign them to one
            Production employee in a single action. File numbers are only unique inside their area — the
            identity used here is the persistent physical file.
          </p>
        </div>
      </header>
      {loadError && <div className="operations-alert error">{loadError}</div>}
      {notice && <div className="operations-alert success">{notice}</div>}
      {error && <div className="operations-alert error">{error}</div>}

      <div className="pt-alloc">
        <div className="pt-alloc-summary">
          <div><span>Total files</span><strong>{totalFiles}</strong></div>
          <div><span>Assigned</span><strong>{assignedFiles}</strong></div>
          <div><span>Available</span><strong>{availableFiles}</strong></div>
          <div><span>Areas</span><strong>{options.areas.length}</strong></div>
        </div>

        {!totalFiles && (
          <div className="operations-note">
            No imported physical files yet — upload the work file master in STEP 1 first.
          </div>
        )}

        {/* ---- saved allocations (derived from authoritative server state) ---- */}
        {allocations.map((group) => {
          const completed = group.files.filter((f) => f.production_status === 'completed').length
          const done = completed === group.files.length
          return (
            <div className="pt-alloc-assignment" key={group.userId}>
              <div className="pt-alloc-assignment-head">
                <strong>{group.name}</strong>
                <span>{group.files.length} file(s) allocated</span>
                <span className={`operations-status ${done ? 'success' : 'warning'}`}>
                  {done ? 'COMPLETED' : `IN PROGRESS · ${completed}/${group.files.length} production complete`}
                </span>
              </div>
              <div className="operations-actions">
                <button type="button" className="operations-button secondary" disabled={busy}
                  onClick={() => setExpanded((v) => (v === group.userId ? null : group.userId))}>
                  {expanded === group.userId ? 'Hide Files' : 'View Files'}
                </button>
                <button type="button" className="operations-button secondary" disabled={busy}
                  onClick={() => editAllocation(group.userId)}>Edit Assignment</button>
              </div>
              {expanded === group.userId && (
                <div className="operations-project-meta">
                  {group.files.map((f) => (
                    <span key={f.work_package_item_id}>
                      {fileLabel(f)} · Production: {f.production_status}
                      {f.safe_reassign ? '' : ' · locked (work started)'}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )
        })}

        {/* ---- one explicit allocation block at a time ---- */}
        {draft && (
          <div className="pt-alloc-assignment">
            <div className="pt-alloc-assignment-head">
              <strong>{draft.editing ? 'EDIT ASSIGNMENT' : 'NEW ASSIGNMENT'}</strong>
              <span>{draft.itemIds.length} file(s) selected</span>
            </div>
            <div className="pt-form-row">
              <label className="operations-field"><span>Employee</span>
                <select value={draft.userId} disabled={draft.editing}
                  onChange={(e) => setDraft({ ...draft, userId: e.target.value, itemIds: [] })}>
                  <option value="">Select Production employee</option>
                  {(draft.editing
                    ? prodMembers.filter((m) => String(m.user_id) === draft.userId)
                    : unusedProdMembers
                  ).map((u) => (
                    <option key={u.user_id} value={u.user_id}>{u.full_name || `User ${u.user_id}`}</option>
                  ))}
                </select>
              </label>
              <label className="operations-field"><span>Production Target Date</span>
                <input type="date" value={draft.prodTarget}
                  onChange={(e) => setDraft({ ...draft, prodTarget: e.target.value })} />
              </label>
              <label className="operations-field"><span>Instructions (optional)</span>
                <input value={draft.instructions}
                  onChange={(e) => setDraft({ ...draft, instructions: e.target.value })} />
              </label>
              {/* Compact Files combobox — same visual weight as the Employee dropdown. */}
              <div className="operations-field pt-files-field" ref={filesBoxRef}>
                <span>Files</span>
                <button type="button" className="pt-files-trigger"
                  disabled={busy || !draft.userId}
                  aria-haspopup="listbox" aria-expanded={filesOpen}
                  onClick={() => setFilesOpen((v) => !v)}>
                  <span>
                    {!draft.userId
                      ? 'Select an employee first'
                      : draft.itemIds.length
                        ? `${draft.itemIds.length} file(s) selected`
                        : 'Select Files'}
                  </span>
                  <i aria-hidden>▾</i>
                </button>
                {filesOpen && draft.userId && (
                  <div className="pt-files-pop" role="listbox">
                    <input className="pt-files-search" autoFocus placeholder="Search files..."
                      value={filter} onChange={(e) => setFilter(e.target.value)} />
                    {!visible.length && (
                      <div className="operations-note">No available files for this employee.</div>
                    )}
                    {byArea.map(([areaKey, list]) => (
                      <div key={areaKey}>
                        <div className="pt-files-group">{list[0]?.area || areaKey}</div>
                        {list.map((f) => (
                          <label className="pt-files-row" key={f.work_package_item_id}>
                            <input type="checkbox"
                              checked={draft.itemIds.includes(f.work_package_item_id)}
                              onChange={() => undefined}
                              onClick={(e) => toggleFile(
                                f.work_package_item_id, e.shiftKey,
                                visible.map((x) => x.work_package_item_id))} />
                            <span className="pt-files-text">
                              <span className="pt-files-primary">
                                {(f.lot_or_batch || '').trim() || '—'} | File {f.file_number}
                                {f.file_name ? ` | ${f.file_name}` : ''}
                              </span>
                              <span className="pt-files-secondary">
                                {[(f.code || '').trim(), (f.area || '').trim()].filter(Boolean).join(' · ') || '—'}
                              </span>
                              {f.remarks ? <span className="pt-files-note">{f.remarks}</span> : null}
                            </span>
                          </label>
                        ))}
                      </div>
                    ))}
                    <div className="pt-files-foot">
                      <span>{draft.itemIds.length} FILE(S) SELECTED</span>
                      <span className="pt-files-foot-actions">
                        <button type="button" className="operations-button secondary"
                          onClick={() => setDraft({
                            ...draft, itemIds: visible.map((f) => f.work_package_item_id),
                          })}>Select All</button>
                        <button type="button" className="operations-button secondary"
                          onClick={() => setDraft({ ...draft, itemIds: [] })}>Clear</button>
                        <button type="button" className="operations-button"
                          onClick={() => setFilesOpen(false)}>Done</button>
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="pt-form-row">
              <label className="operations-field"><span>QC Employee</span>
                <select value={draft.qcUser} onChange={(e) => setDraft({ ...draft, qcUser: e.target.value })}>
                  <option value="">Select</option>
                  {options.team.qc.map((u) => (
                    <option key={u.user_id} value={u.user_id}>{u.full_name || `User ${u.user_id}`}</option>
                  ))}
                </select>
              </label>
              <label className="operations-field"><span>QC Target Date</span>
                <input type="date" value={draft.qcTarget}
                  onChange={(e) => setDraft({ ...draft, qcTarget: e.target.value })} />
              </label>
              <label className="operations-field"><span>QA Employee</span>
                <select value={draft.qaUser} onChange={(e) => setDraft({ ...draft, qaUser: e.target.value })}>
                  <option value="">Select</option>
                  {options.team.qa.map((u) => (
                    <option key={u.user_id} value={u.user_id}>{u.full_name || `User ${u.user_id}`}</option>
                  ))}
                </select>
              </label>
              <label className="operations-field"><span>QA Target Date</span>
                <input type="date" value={draft.qaTarget}
                  onChange={(e) => setDraft({ ...draft, qaTarget: e.target.value })} />
              </label>
            </div>

            <div className="operations-actions">
              <button type="button" className="operations-button" disabled={busy} onClick={() => assign(draft)}>
                Assign {draft.itemIds.length ? `(${draft.itemIds.length})` : ''}
              </button>
              <button type="button" className="operations-button secondary" disabled={busy}
                onClick={() => setDraft(null)}>Cancel</button>
            </div>
          </div>
        )}

        <div className="operations-actions">
          {!draft && unusedProdMembers.length > 0 && (
            <button type="button" className="operations-button secondary" disabled={busy} onClick={addEmployee}>
              + Add Employee
            </button>
          )}
          {!draft && !unusedProdMembers.length && totalFiles > 0 && (
            <span className="operations-note">
              No additional Production team members are available for this project.
            </span>
          )}
        </div>
      </div>
    </section>
  )
}
