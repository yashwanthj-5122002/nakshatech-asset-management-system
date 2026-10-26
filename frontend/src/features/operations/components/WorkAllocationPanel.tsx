import { FileSpreadsheet, Loader2, Upload } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { apiFetch, uploadExcel } from '../../../lib/api'

// V8.3 Team Lead Excel-driven work allocation â€” SHARED by Project Operations (/ortho, the
// authoritative entry point) and Production Tracking (which only links here). Both pages use
// the exact same backend endpoints, so there is one source of truth:
//   master-import/preview Â· master-import/commit Â· allocation-options Â· area-files Â· assign-files

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
  if (value === null || value === undefined) return 'â€”'
  return Number.isInteger(value) ? String(value) : String(Math.round(value * 1000) / 1000)
}

// ===========================================================================================
// STEP 1 â€” WORK FILE MASTER (upload -> preview -> transactional confirm)
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
        + (summary.skipped_existing ? ` Â· ${summary.skipped_existing} already present (skipped)` : '')
        + (summary.conflicts.length
          ? ` Â· ${summary.conflicts.length} with existing work history (skipped, never overwritten)`
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
          <span className="operations-kicker">TEAM LEAD Â· STEP 1 Â· WORK FILE MASTER</span>
          <h2>Upload the work file master (Excel)</h2>
          <p>
            Columns: MARCHE LOTTO 3 Â· CODE Â· AREA NAME Â· FILE NUMBER Â· PLANNED LENGTH Â· UOM Â·
            REMARKS (optional) Â· FILE NAME (optional). For count-based areas use TOTAL FILES instead
            of FILE NUMBER â€” the ERP then creates File 1..N for that Lot/Code/Area (no per-file
            length is invented). You will see a preview first â€” nothing is saved until you confirm,
            and files that already have work history are never overwritten.
          </p>
        </div>
        <label className="operations-button">
          <Upload size={15} /> {busy ? 'Workingâ€¦' : 'Upload Excel'}
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
                : 'â€”'}
            </span>
          </div>
          {preview.conflicts.length > 0 && (
            <ul className="pt-preview-conflicts">
              {preview.conflicts.slice(0, 10).map((c) => (
                <li key={`${c.row}-${c.item_number}`}>
                  Row {c.row} Â· {c.lot} / {c.code} / {c.area_name} Â· file {c.item_number} â€” {c.reason}
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
              {busy ? 'Importingâ€¦' : 'Confirm Import'}
            </button>
          </div>
        </div>
      )}
    </section>
  )
}

// ===========================================================================================
// STEP 2 — ALLOCATE IMPORTED WORK (project-scope, V8.6).
// The implementation lives in ProjectAllocationPanel.tsx so there is ONE allocation UI.
// ===========================================================================================
export { ImportedAllocationPanel } from './ProjectAllocationPanel'
