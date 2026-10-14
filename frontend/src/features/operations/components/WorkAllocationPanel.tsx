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
  file_count: number
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
  files: {
    work_package_item_id: number
    item_number: string
    item_name?: string | null
    planned_quantity?: number | null
    planned_unit?: string | null
    production_status: string
    production_user?: string | null
    qc_user?: string | null
    qa_user?: string | null
  }[]
  planned_groups: { measurement_type: string; unit: string; quantity: number; rows: number }[]
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
            REMARKS (optional) · FILE NAME (optional). You will see a preview first — nothing is saved
            until you confirm, and files that already have work history are never overwritten.
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
  const [selected, setSelected] = useState<number[]>([])
  const [supplyDate, setSupplyDate] = useState('')
  const [prodUser, setProdUser] = useState('')
  const [prodTarget, setProdTarget] = useState('')
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
    setSelected([])
    if (!workPackageId) return
    void apiFetch<AreaFilesResponse>(`/operations/workflow/ortho/work-packages/${workPackageId}/area-files`)
      .then((v) => { setFiles(v); setSelected(v.files.map((f) => f.work_package_item_id)) })
      .catch((e) => setError(e instanceof Error ? e.message : 'Unable to load files'))
  }
  useEffect(() => { loadFiles(activeAreaId) }, [activeAreaId])

  const plannedTotal = useMemo(() => {
    // Group by unit string so incompatible units are never added together.
    const picked = (files?.files ?? []).filter((f) => selected.includes(f.work_package_item_id))
    const byUnit: Record<string, { unit: string; quantity: number }> = {}
    for (const f of picked) {
      const unit = f.planned_unit || 'unit'
      byUnit[unit] = byUnit[unit] ?? { unit, quantity: 0 }
      byUnit[unit].quantity += f.planned_quantity ?? 0
    }
    return Object.values(byUnit)
  }, [files, selected])

  async function assign() {
    if (!activeAreaId) { setError('Select Lot, Code and Area first.'); return }
    if (!selected.length) { setError('Select at least one file.'); return }
    if (!prodUser || !qcUser || !qaUser) { setError('Production, QC and QA employees are all required.'); return }
    if (!prodTarget || !qcTarget || !qaTarget) { setError('Production, QC and QA target dates are all required.'); return }
    if (!(prodTarget <= qcTarget && qcTarget <= qaTarget)) {
      setError('Target dates must satisfy Production ≤ QC ≤ QA.'); return
    }
    setBusy(true); setError(''); setNotice('')
    try {
      const summary = await apiFetch<{ assigned_files: number }>(
        `/operations/workflow/ortho/work-packages/${activeAreaId}/assign-files`,
        {
          method: 'POST',
          body: JSON.stringify({
            item_ids: selected,
            production_user_id: Number(prodUser),
            production_target_date: prodTarget,
            qc_user_id: Number(qcUser),
            qc_target_date: qcTarget,
            qa_user_id: Number(qaUser),
            qa_target_date: qaTarget,
            supply_date: supplyDate || null,
            note: note.trim() || null,
          }),
        },
      )
      setNotice(`${summary.assigned_files} file(s) allocated. Production, QC and QA employees notified.`)
      setProdUser(''); setQcUser(''); setQaUser('')
      setProdTarget(''); setQcTarget(''); setQaTarget('')
      setNote('')
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
              <div><span>Files</span><strong>{area.file_count} ({area.files_completed} completed)</strong></div>
              <div><span>Production</span><strong>{area.production_status}</strong></div>
              <div><span>QC</span><strong>{area.qc_status}</strong></div>
              <div><span>QA</span><strong>{area.qa_status}</strong></div>
              <div><span>Delivery readiness</span><strong>{area.ready_for_delivery ? 'Ready for Delivery' : 'Not ready'}</strong></div>
            </div>
          )}

          {files && (
            <>
              <div className="pt-alloc-files">
                <strong>Files of this area</strong>
                <div className="pt-alloc-file-actions">
                  <button type="button" className="operations-button secondary"
                    onClick={() => setSelected(files.files.map((f) => f.work_package_item_id))}>Select All</button>
                  <button type="button" className="operations-button secondary"
                    onClick={() => setSelected([])}>Clear</button>
                </div>
                {files.files.map((file) => (
                  <label className="operations-check" key={file.work_package_item_id}>
                    <input type="checkbox"
                      checked={selected.includes(file.work_package_item_id)}
                      onChange={(e) => setSelected((ids) => e.target.checked
                        ? [...ids, file.work_package_item_id]
                        : ids.filter((id) => id !== file.work_package_item_id))} />
                    <span>
                      {file.item_number}{file.item_name ? ` — ${file.item_name}` : ''} · {fmtQty(file.planned_quantity)} {file.planned_unit || ''}
                      {file.production_user ? ` · Production: ${file.production_user}` : ''}
                    </span>
                  </label>
                ))}
              </div>
              <div className="pt-alloc-total">
                <strong>Planned Quantity</strong>
                {plannedTotal.length === 0
                  ? <span>—</span>
                  : plannedTotal.map((g) => <span key={g.unit}>{fmtQty(g.quantity)} {g.unit}</span>)}
                <span className="pt-auto-tag">{selected.length} file(s) · auto-calculated</span>
              </div>
            </>
          )}

          <div className="pt-form-row">
            <label className="operations-field"><span>Supply Date</span>
              <input type="date" value={supplyDate || (files?.supply_date ?? '')} onChange={(e) => setSupplyDate(e.target.value)} />
            </label>
            <label className="operations-field"><span>Production employee</span>
              <select value={prodUser} onChange={(e) => setProdUser(e.target.value)}>
                <option value="">Select</option>
                {options.team.production.map((u) => <option key={u.user_id} value={u.user_id}>{u.full_name || `User ${u.user_id}`}</option>)}
              </select>
            </label>
            <label className="operations-field"><span>Production Target Date</span>
              <input type="date" value={prodTarget} onChange={(e) => setProdTarget(e.target.value)} />
            </label>
            <label className="operations-field"><span>QC employee</span>
              <select value={qcUser} onChange={(e) => setQcUser(e.target.value)}>
                <option value="">Select</option>
                {options.team.qc.map((u) => <option key={u.user_id} value={u.user_id}>{u.full_name || `User ${u.user_id}`}</option>)}
              </select>
            </label>
            <label className="operations-field"><span>QC Target Date</span>
              <input type="date" value={qcTarget} onChange={(e) => setQcTarget(e.target.value)} />
            </label>
            <label className="operations-field"><span>QA employee</span>
              <select value={qaUser} onChange={(e) => setQaUser(e.target.value)}>
                <option value="">Select</option>
                {options.team.qa.map((u) => <option key={u.user_id} value={u.user_id}>{u.full_name || `User ${u.user_id}`}</option>)}
              </select>
            </label>
            <label className="operations-field"><span>QA Target Date</span>
              <input type="date" value={qaTarget} onChange={(e) => setQaTarget(e.target.value)} />
            </label>
            <label className="operations-field pt-span"><span>Instructions (optional)</span>
              <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Work instructions for the assigned employees" />
            </label>
          </div>
          <div className="operations-actions">
            <button type="button" className="operations-button" disabled={busy} onClick={assign}>
              Assign Work &amp; Notify
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
