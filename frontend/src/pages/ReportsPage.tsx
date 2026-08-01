import {
  CalendarDays, CheckCircle2, FileDown, FileSpreadsheet, History,
  LayoutDashboard, LockKeyhole, RefreshCw, UploadCloud,
} from 'lucide-react'
import { ChangeEvent, useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../components/DashboardHeader'
import { useAuth } from '../context/AuthContext'
import { apiFetch, downloadFile, uploadExcel } from '../lib/api'
import type { ReportMonth } from '../types'

export function ReportsPage() {
  const { user } = useAuth()
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [months, setMonths] = useState<ReportMonth[]>([])
  const [selectedMonth, setSelectedMonth] = useState('')

  const selected = useMemo(
    () => months.find(item => item.key === selectedMonth),
    [months, selectedMonth],
  )

  async function loadMonths() {
    try {
      const data = await apiFetch<ReportMonth[]>('/reports/months')
      setMonths(data)
      setSelectedMonth(current => current || data[0]?.key || '')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load report months')
    }
  }
  useEffect(() => { void loadMonths() }, [])

  async function download(path: string, name: string, key: string) {
    setBusy(key); setError(''); setMessage('')
    try {
      await downloadFile(path, name)
      setMessage(`${name} downloaded successfully.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Download failed')
    } finally { setBusy('') }
  }

  async function importFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    setBusy('import'); setError(''); setMessage('')
    try {
      const result = await uploadExcel('/imports/assets.xlsx', file)
      setMessage(`Import completed: ${result.created || 0} created, ${result.updated || 0} updated, ${result.skipped || 0} skipped.`)
      await loadMonths()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed')
    } finally { setBusy(''); event.target.value = '' }
  }

  async function finalizeSelectedMonth() {
    if (!selectedMonth) return
    setBusy('finalize'); setError(''); setMessage('')
    try {
      const result = await apiFetch<{ month: string; closing_count: number }>(
        `/monthly-snapshots/finalize?month=${encodeURIComponent(selectedMonth)}`,
        { method: 'POST' },
      )
      setMessage(`${result.month} finalized with ${result.closing_count} asset records.`)
      await loadMonths()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to finalize month')
    } finally { setBusy('') }
  }

  const monthLabel = selected?.label || 'Selected Month'
  const monthQuery = encodeURIComponent(selectedMonth)

  return (
    <>
      <DashboardHeader
        eyebrow="REPORTING CENTRE"
        title="Excel Downloads & Monthly Records"
        description="Choose a month and download its exact Asset Register, upgrade/replacement history and monthly movement summary. Current month is live; finalized months remain frozen."
      />
      {message && <div className="success-message">{message}</div>}
      {error && <div className="error-message">{error}</div>}

      <section className="panel monthly-report-control">
        <div className="monthly-report-heading">
          <div><span className="section-kicker">MONTH-WISE CONTROL</span><h2>Select the reporting month</h2><p>The selected month controls all three monthly Excel downloads below.</p></div>
          <div className={`month-state ${selected?.status || 'live'}`}>
            {selected?.status === 'live' ? <RefreshCw size={18} /> : <LockKeyhole size={18} />}
            <span>{selected?.status === 'live' ? 'Live current register' : selected?.status === 'finalized' ? 'Finalized system snapshot' : 'Original historical Excel'}</span>
          </div>
        </div>
        <div className="monthly-report-selector">
          <label><CalendarDays size={18} /><span>Month</span><select value={selectedMonth} onChange={event => setSelectedMonth(event.target.value)}>{months.map(month => <option key={month.key} value={month.key}>{month.label} — {month.status}</option>)}</select></label>
          <div className="month-count-summary"><strong>{selected?.closing_count ?? '—'}</strong><span>{selected?.closing_count !== undefined ? 'Closing assets' : selected?.status === 'live' ? 'Live register' : 'Historical workbook'}</span></div>
          {user?.role === 'admin' && selected?.status === 'live' && <button className="secondary-button" onClick={() => void finalizeSelectedMonth()} disabled={!!busy}><CheckCircle2 size={17} /> {busy === 'finalize' ? 'Finalizing…' : 'Finalize Selected Month'}</button>}
        </div>
      </section>

      <section className="report-grid monthly-download-grid">
        <article className="report-card featured-report">
          <FileSpreadsheet size={34} />
          <span className="section-kicker">MONTHLY CURRENT VALUES</span>
          <h2>{monthLabel} Asset Register</h2>
          <p>Downloads the selected month in the same NakshaTech Excel structure. It shows the active CPU tag, workstation and the latest monitor, mouse, keyboard, hardware, network and software values for that month.</p>
          <button className="primary-button" onClick={() => void download(`/reports/monthly-assets.xlsx?month=${monthQuery}`, `NakshaTech Asset Register - ${monthLabel}.xlsx`, 'monthly-assets')} disabled={!selectedMonth || !!busy}><FileDown size={17} /> {busy === 'monthly-assets' ? 'Preparing Register…' : 'Download Monthly Asset Register'}</button>
        </article>

        <article className="report-card">
          <History size={34} />
          <span className="section-kicker">OLD → NEW HISTORY</span>
          <h2>{monthLabel} Upgrade & Replacement History</h2>
          <p>Downloads a separate workbook containing every component/configuration item changed during the month, grouped by batch and work record, plus complete computer/laptop replacements.</p>
          <button className="secondary-button" onClick={() => void download(`/reports/monthly-changes.xlsx?month=${monthQuery}`, `NakshaTech Upgrade Replacement History - ${monthLabel}.xlsx`, 'monthly-changes')} disabled={!selectedMonth || !!busy}><FileDown size={17} /> {busy === 'monthly-changes' ? 'Preparing History…' : 'Download Monthly Change History'}</button>
        </article>

        <article className="report-card">
          <LayoutDashboard size={34} />
          <span className="section-kicker">MONTH MOVEMENT</span>
          <h2>{monthLabel} Asset Summary</h2>
          <p>Shows opening/imported baseline, manually added PCs and laptops, component upgrades, component replacements, complete asset replacements, returns, retirement and closing count.</p>
          <button className="secondary-button" onClick={() => void download(`/reports/monthly-summary.xlsx?month=${monthQuery}`, `NakshaTech Monthly Asset Summary - ${monthLabel}.xlsx`, 'monthly-summary')} disabled={!selectedMonth || !!busy}><FileDown size={17} /> {busy === 'monthly-summary' ? 'Preparing Summary…' : 'Download Monthly Summary'}</button>
        </article>
      </section>

      <section className="report-grid">
        <article className="report-card"><FileSpreadsheet size={34} /><span className="section-kicker">LIVE MASTER WORKBOOK</span><h2>NakshaTech Asset Details</h2><p>Downloads the complete live register and preserves the original historical monthly sheets from the workbook provided by your IT team.</p><button className="secondary-button" onClick={() => void download('/reports/nakshatech-assets.xlsx', 'NakshaTech Asset Details.xlsx', 'assets')} disabled={!!busy}><FileDown size={17} /> {busy === 'assets' ? 'Preparing Excel…' : 'Download Complete Asset Excel'}</button></article>
        <article className="report-card"><LayoutDashboard size={34} /><span className="section-kicker">MANAGEMENT REPORT</span><h2>IT Dashboard Workbook</h2><p>Includes KPI summary, current asset register, status and department charts, work records and data-quality checks.</p><button className="secondary-button" onClick={() => void download('/reports/dashboard.xlsx', 'NakshaTech IT Dashboard.xlsx', 'dashboard')} disabled={!!busy}><FileDown size={17} /> Download Dashboard Excel</button></article>
        <article className="report-card"><History size={34} /><span className="section-kicker">ALL-TIME HISTORY</span><h2>Complete Replacement History</h2><p>Downloads all component/configuration changes and complete asset replacements across every month.</p><button className="secondary-button" onClick={() => void download('/reports/replacement-history.xlsx', 'NakshaTech Replacement History.xlsx', 'replacement-history')} disabled={!!busy}><FileDown size={17} /> {busy === 'replacement-history' ? 'Preparing History…' : 'Download All-Time History'}</button></article>
        {user?.role === 'admin' && <article className="report-card"><UploadCloud size={34} /><span className="section-kicker">ADMIN ONLY</span><h2>Import Updated Excel</h2><p>Upload the NakshaTech workbook. Existing assets are matched using CPU tags or system names, and new records receive system asset IDs.</p><label className="secondary-button file-button"><UploadCloud size={17} /> {busy === 'import' ? 'Importing…' : 'Select Excel File'}<input hidden type="file" accept=".xlsx" onChange={event => void importFile(event)} /></label><button className="text-button" onClick={() => void download('/reports/upload-template.xlsx', 'NakshaTech IT Asset Upload Template.xlsx', 'template')}>Download blank upload template</button></article>}
      </section>

      <section className="panel report-notes"><h2>How month continuity works</h2><div className="check-grid"><span>✓ CPU / Asset Tag + Workstation identify the system</span><span>✓ Current register always shows latest active values</span><span>✓ Multiple changes can share one batch and work record</span><span>✓ Old values remain in separate history</span><span>✓ July closing values carry into August opening</span><span>✓ Finalized past months do not change silently</span><span>✓ User can select any available month</span><span>✓ Asset Register and History remain separate Excel files</span><span>✓ New manually added assets appear in monthly summary</span><span>✓ Complete live workbook remains available</span></div></section>
    </>
  )
}
