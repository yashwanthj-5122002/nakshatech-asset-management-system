import { useEffect, useState } from 'react'
import { FileSpreadsheet, RefreshCcw, ShieldCheck, Trash2, Upload } from 'lucide-react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch, uploadExcel } from '../../../lib/api'

type MasterStatus = { published: boolean; record_count: number; linked_account_count: number }
type MasterRow = {
  id: number; source_sl_no: string | null; access_card_no: string; employee_number: string
  employee_name: string; phone: string; department: string; designation: string; email: string
  crm_account_status: string; source_batch_id: string
}
type Preview = {
  can_import: boolean
  report: { total_rows: number; valid_rows: number; rows_requiring_review: number[]; file: string }
  sample: { row: number; employee_number: string; employee_name: string; department: string; email: string }[]
}

export function ManagementEmployeeMasterPage() {
  const [status, setStatus] = useState<MasterStatus | null>(null)
  const [rows, setRows] = useState<MasterRow[]>([])
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function load() {
    const [state, records] = await Promise.all([
      apiFetch<MasterStatus>('/management/employee-master/status'),
      apiFetch<MasterRow[]>('/management/employee-master'),
    ])
    setStatus(state)
    setRows(records)
  }

  useEffect(() => { void load().catch(err => setError(err instanceof Error ? err.message : 'Could not load Employee Master')) }, [])

  async function chooseFile(selected: File | null) {
    setFile(selected)
    setPreview(null)
    setError('')
    setNotice('')
    if (!selected) return
    setBusy('preview')
    try {
      const result = await uploadExcel('/management/employee-master/preview', selected)
      setPreview(result as unknown as Preview)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not inspect workbook')
    } finally {
      setBusy('')
    }
  }

  async function importFile() {
    if (!file || !preview?.can_import) return
    setBusy('import')
    setError('')
    setNotice('')
    try {
      const result = await uploadExcel('/management/employee-master/import', file)
      setFile(null)
      setPreview(null)
      await load()
      setNotice(`Imported ${result.created ?? 0} new and ${result.updated ?? 0} updated records. The directory is private until you publish it.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not import workbook')
    } finally {
      setBusy('')
    }
  }

  async function setPublished(published: boolean) {
    setBusy('publication')
    setError('')
    setNotice('')
    try {
      await apiFetch('/management/employee-master/publication', {
        method: 'PUT', body: JSON.stringify({ published }),
      })
      await load()
      setNotice(published ? 'Employee Master is published to the Software Team directory and self-registration.' : 'Employee Master is hidden from the Software Team directory and self-registration.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not change publication')
    } finally {
      setBusy('')
    }
  }

  async function purge() {
    const confirmation = window.prompt('Type DELETE EMPLOYEE MASTER to permanently remove Excel-imported master records. Existing ERP user accounts, tickets, audits and backups remain.')
    if (confirmation !== 'DELETE EMPLOYEE MASTER') return
    setBusy('purge')
    setError('')
    setNotice('')
    try {
      const result = await apiFetch<{ removed: number; existing_accounts_retained: number }>('/management/employee-master/imported', {
        method: 'DELETE', body: JSON.stringify({ confirmation }),
      })
      await load()
      setNotice(`Removed ${result.removed} imported master records. ${result.existing_accounts_retained} existing ERP accounts remain.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not remove imported records')
    } finally {
      setBusy('')
    }
  }

  return <div className="operations-page">
    <DashboardHeader eyebrow="MANAGEMENT · EMPLOYEE MASTER" title="Employee data control"
      description="Import the Excel workbook privately, review it, then decide when the Employee Master is available for the Software Team directory and employee self-registration."
      actions={<button className="operations-button secondary" onClick={() => void load().catch(err => setError(String(err)))} disabled={!!busy}><RefreshCcw size={16} /> Refresh</button>} />

    {error && <div className="operations-alert error">{error}</div>}
    {notice && <div className="operations-alert success">{notice}</div>}

    <section className="operations-panel">
      <header><div><span className="operations-kicker">PUBLICATION</span><h2>{status?.published ? 'Published' : 'Private'}</h2>
        <p>{status?.record_count ?? 0} Excel records · {status?.linked_account_count ?? 0} linked ERP accounts</p></div></header>
      <p>When private, Excel records are hidden from the Software Team directory and cannot start or complete self-registration. Existing ERP accounts and their own profile data remain available.</p>
      <div className="operations-toolbar">
        <button className="operations-button" disabled={!!busy || !status?.record_count || !!status?.published} onClick={() => void setPublished(true)}><ShieldCheck size={16} /> Publish records</button>
        <button className="operations-button secondary" disabled={!!busy || !status?.published} onClick={() => void setPublished(false)}>Stop sharing</button>
      </div>
    </section>

    <section className="operations-panel">
      <header><div><span className="operations-kicker">PRIVATE IMPORT</span><h2>Review Excel workbook</h2>
        <p>Eight columns: SL.No, Accesscardno, Employee Number, Employee Name, Phone, Curr.Department, Curr.Designation, Email.</p></div></header>
      <label className="operations-button secondary" style={{ cursor: 'pointer', display: 'inline-flex' }}><FileSpreadsheet size={16} /> Choose .xlsx file
        <input hidden type="file" accept=".xlsx" onChange={event => { void chooseFile(event.target.files?.[0] || null); event.currentTarget.value = '' }} /></label>
      {busy === 'preview' && <p>Checking workbook...</p>}
      {preview && <div>
        <p><strong>{preview.report.file}</strong> · {preview.report.total_rows} rows · {preview.report.valid_rows} valid · {preview.report.rows_requiring_review.length} need review</p>
        {!preview.can_import && <div className="operations-alert warning">Fix the workbook rows requiring review before import: {preview.report.rows_requiring_review.join(', ')}</div>}
        {!!preview.sample.length && <div className="operations-table-wrap"><table className="operations-table"><thead><tr><th>Excel row</th><th>Employee number</th><th>Name</th><th>Department</th><th>Email</th></tr></thead>
          <tbody>{preview.sample.map(row => <tr key={row.row}><td>{row.row}</td><td>{row.employee_number}</td><td>{row.employee_name}</td><td>{row.department}</td><td>{row.email}</td></tr>)}</tbody></table></div>}
        {preview.report.total_rows > preview.sample.length && <p>Showing the first {preview.sample.length} rows. All rows are validated before import.</p>}
        <button className="operations-button" disabled={!!busy || !preview.can_import} onClick={() => void importFile()}><Upload size={16} /> {busy === 'import' ? 'Importing...' : 'Import privately'}</button>
      </div>}
    </section>

    <section className="operations-panel">
      <header><div><span className="operations-kicker">PRIVATE DIRECTORY</span><h2>Imported records</h2><p>Visible here to Management whether published or private.</p></div></header>
      {!rows.length ? <div className="operations-empty">No Excel records imported.</div> : <div className="operations-table-wrap"><table className="operations-table"><thead><tr><th>SL.No</th><th>Access card</th><th>Employee number</th><th>Name</th><th>Phone</th><th>Department</th><th>Designation</th><th>Email</th><th>CRM</th></tr></thead>
        <tbody>{rows.map(row => <tr key={row.id}><td>{row.source_sl_no}</td><td>{row.access_card_no}</td><td>{row.employee_number}</td><td>{row.employee_name}</td><td>{row.phone}</td><td>{row.department}</td><td>{row.designation}</td><td>{row.email}</td><td>{row.crm_account_status}</td></tr>)}</tbody></table></div>}
    </section>

    <section className="operations-panel">
      <header><div><span className="operations-kicker">REMOVE IMPORTED MASTER</span><h2>Delete Excel records</h2></div></header>
      <p>This removes Excel-imported Employee Master rows from the live ERP database and stops their self-registration. Existing user accounts, tickets, audit records and backups are retained.</p>
      <button className="operations-button secondary" disabled={!!busy || !status?.record_count} onClick={() => void purge()}><Trash2 size={16} /> Delete imported records</button>
    </section>
  </div>
}
