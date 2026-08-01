import { CheckCircle2, FileSpreadsheet, ShieldAlert, Upload } from 'lucide-react'
import { ChangeEvent, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch, downloadFile, uploadExcel } from '../../../lib/api'
import type { DroneImportBatch } from '../../../types'

export function DroneImportPage() {
  const { user } = useAuth()
  const [file, setFile] = useState<File | null>(null)
  const [month, setMonth] = useState('2026-05')
  const [batch, setBatch] = useState<DroneImportBatch | null>(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const choose = (event: ChangeEvent<HTMLInputElement>) => setFile(event.target.files?.[0] || null)
  const preview = async () => {
    if (!file) { setError('Choose the Drone hardware inventory workbook first.'); return }
    setLoading(true); setError(''); setMessage('')
    try { setBatch(await uploadExcel(`/drone/import/preview?reporting_month=${month}`, file) as unknown as DroneImportBatch) }
    catch (err) { setError(err instanceof Error ? err.message : 'Workbook preview failed') }
    finally { setLoading(false) }
  }
  const templatePreview = async () => {
    setLoading(true); setError(''); setMessage('')
    try { setBatch(await apiFetch<DroneImportBatch>('/drone/import/template-preview', { method: 'POST' })) }
    catch (err) { setError(err instanceof Error ? err.message : 'Template preview failed') }
    finally { setLoading(false) }
  }
  const commit = async () => {
    if (!batch) return
    setLoading(true); setError('')
    try {
      const result = await apiFetch<Record<string, number | string>>(`/drone/import/${batch.batch_id}/commit`, { method: 'POST', body: JSON.stringify({ allow_warnings: true }) })
      setMessage(`Import committed: ${result.created_assets} permanent assets, ${result.created_kits} kits and ${result.created_projects} project(s) created.`)
      setBatch({ ...batch, status: 'committed' })
    } catch (err) { setError(err instanceof Error ? err.message : 'Import commit failed') }
    finally { setLoading(false) }
  }

  if (user?.role !== 'admin') return <><DashboardHeader eyebrow="DRONE IMPORT" title="Workbook Reconciliation" description="Only Admin can upload and commit the permanent Drone master. Management and Drone users can use the approved records." /><div className="panel empty-state">Admin permission is required to preview and approve the source workbook.</div></>

  const summary = batch?.summary || {}
  const issueCounts = (summary.issue_counts || {}) as Record<string, number>
  return <>
    <DashboardHeader eyebrow="LOSSLESS EXCEL IMPORT" title="Drone Workbook Import & Reconciliation" description="The workbook is never written directly into the permanent master. First preview all four sheets, 52 source attributes, quality issues and exact source rows; then approve the batch." actions={<button className="secondary-button" onClick={() => void downloadFile('/drone/reports/source-template.xlsx', 'Hardware-Inventory Sheets - Preserved Template.xlsx')}><FileSpreadsheet size={17} /> Download Preserved Template</button>} />
    {error && <div className="error-message">{error}</div>}{message && <div className="success-message">{message}</div>}
    <section className="panel import-upload-panel">
      <div className="import-drop-zone"><Upload size={34} /><div><strong>{file?.name || 'Select Hardware-Inventory workbook'}</strong><span>Required sheets: May-2026, Trinity Equipment details, Amrut 2.0_Inventroy Sheet and Hard disk delivered to SoI.</span></div><label className="secondary-button">Choose Excel<input type="file" accept=".xlsx" onChange={choose} hidden /></label></div>
      <div className="import-actions"><label><span>Reporting Month</span><input type="month" value={month} onChange={event => setMonth(event.target.value)} /></label><button className="secondary-button" onClick={templatePreview} disabled={loading}>Preview Bundled Source</button><button className="primary-button" onClick={preview} disabled={loading || !file}>{loading ? 'Processing…' : 'Preview Workbook'}</button></div>
    </section>
    {batch && <>
      <section className="stats-grid import-summary-grid">
        {[
          ['Total parsed records', summary.total_records], ['Main inventory', summary.main_inventory_records], ['Trinity components', summary.trinity_components], ['Amrut custody rows', summary.amrut_assignment_records],
          ['UIN registrations', summary.uin_registrations], ['Airtel connections', summary.telecom_connections], ['HDD deliveries', summary.hdd_delivery_transactions], ['Named attributes', summary.named_source_attributes],
        ].map(([label, value]) => <article className="panel mini-stat" key={String(label)}><span>{label}</span><strong>{String(value ?? 0)}</strong></article>)}
      </section>
      <section className="dashboard-grid import-review-grid">
        <article className="panel"><div className="panel-heading"><div><span className="section-kicker">QUALITY REVIEW</span><h2>Detected Exceptions</h2></div><ShieldAlert /></div><div className="issue-list">{Object.entries(issueCounts).map(([name, count]) => <div key={name}><span>{name.replaceAll('_', ' ')}</span><strong>{count}</strong></div>)}{Object.keys(issueCounts).length === 0 && <div className="empty-state">No import warnings detected.</div>}</div></article>
        <article className="panel"><div className="panel-heading"><div><span className="section-kicker">BATCH CONTROL</span><h2>{batch.batch_code}</h2></div><span className={`status ${batch.status}`}>{batch.status}</span></div><div className="detail-list"><div><span>Workbook</span><strong>{batch.source_workbook}</strong></div><div><span>Reporting Month</span><strong>{batch.reporting_month}</strong></div><div><span>Records Needing Review</span><strong>{String(summary.records_needing_review || 0)}</strong></div><div><span>Trinity Kits Detected</span><strong>{String(summary.trinity_kits || 0)}</strong></div></div><button className="primary-button full-button" disabled={loading || batch.status === 'committed'} onClick={commit}><CheckCircle2 size={17} /> {batch.status === 'committed' ? 'Committed to Permanent Master' : 'Approve & Commit Import'}</button></article>
      </section>
      <section className="panel"><div className="panel-heading"><div><span className="section-kicker">SOURCE ROW PREVIEW</span><h2>Parsed Records</h2></div><span className="count-chip">{batch.records.length}</span></div><div className="table-wrap"><table className="data-table"><thead><tr><th>Source</th><th>Type</th><th>Normalized Record</th><th>Issues</th><th>Status</th></tr></thead><tbody>{batch.records.slice(0, 100).map(record => <tr key={record.id}><td><strong>{record.source_sheet}</strong><small>Row {record.source_row} · {record.source_section || 'No section'}</small></td><td>{record.record_type.replaceAll('_', ' ')}</td><td><strong>{String(record.normalized_payload.asset_name || record.normalized_payload.uav || record.normalized_payload.ulbs || record.normalized_payload.connection_number || 'Record')}</strong><small>{String(record.normalized_payload.serial_number || record.normalized_payload.hdd_serial_number || record.normalized_payload.imported_equipment_id || '')}</small></td><td>{record.issues.length ? record.issues.map(issue => <span className="issue-chip" key={issue}>{issue.replaceAll('_', ' ')}</span>) : <span className="success-chip">Ready</span>}</td><td>{record.reconciliation_status}</td></tr>)}</tbody></table></div>{batch.records.length > 100 && <p className="table-note">Showing the first 100 records. The backend retains every parsed row and original raw value.</p>}</section>
    </>}
  </>
}
