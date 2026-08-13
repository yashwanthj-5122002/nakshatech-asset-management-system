import {
  CalendarDays, CheckCircle2, FileClock, FileDown, FileSpreadsheet, History,
  LayoutDashboard, LockKeyhole, Printer, RefreshCw, RotateCcw, UploadCloud,
} from 'lucide-react'
import { ChangeEvent, useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../components/DashboardHeader'
import { useAuth } from '../context/AuthContext'
import { useITMonthUrl } from '../context/ITMonthContext'
import { isFullAccessRole } from '../lib/roles'
import { apiFetch, downloadFile, uploadExcel } from '../lib/api'
import type { ReportMonth } from '../types'

export function ReportsPage() {
  const { user } = useAuth()
  const { selectedMonth, setSelectedMonth, presentMonth, returnToPresent } = useITMonthUrl()
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [months, setMonths] = useState<ReportMonth[]>([])
  const [yearPeriod, setYearPeriod] = useState<'calendar' | 'financial'>('calendar')
  const [reportYear, setReportYear] = useState(() => Number(presentMonth.slice(0, 4)))

  const selected = useMemo(
    () => months.find(item => item.key === selectedMonth),
    [months, selectedMonth],
  )

  async function loadMonths() {
    try {
      const data = await apiFetch<ReportMonth[]>('/reports/months')
      setMonths(data)
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

  async function importPrinterFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    setBusy('printer-import'); setError(''); setMessage('')
    try {
      const result = await uploadExcel('/imports/printers.xlsx', file)
      const warnings = Number(result.warning_count || 0)
      const errors = Number(result.error_count || 0)
      setMessage(`Printer import completed: ${result.created || 0} created, ${result.updated || 0} updated, ${result.skipped || 0} skipped, ${warnings} warning(s), ${errors} error(s).`)
      await loadMonths()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Printer import failed')
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
  const currentYear = Number(presentMonth.slice(0, 4))
  const reportYears = useMemo(() => {
    const availableYears = months
      .map(item => Number(item.key.slice(0, 4)))
      .filter(item => Number.isFinite(item))
    const earliestYear = availableYears.length ? Math.min(...availableYears) : currentYear
    const latestYear = Math.max(currentYear, ...availableYears)
    return Array.from({ length: latestYear - earliestYear + 1 }, (_, index) => latestYear - index)
  }, [months, currentYear])
  const yearlyLabel = yearPeriod === 'calendar'
    ? `Calendar Year ${reportYear}`
    : `Financial Year ${reportYear}-${String(reportYear + 1).slice(-2)}`

  return (
    <>
      <DashboardHeader
        eyebrow="REPORTING CENTRE"
        title="Monthly & Yearly Excel Reporting"
        description="Download complete monthly or yearly IT workbooks covering asset registers, Printers, External HDDs, changes, work records, replacements, handovers, returns, purchases and approval history."
      />
      {message && <div className="success-message">{message}</div>}
      {error && <div className="error-message">{error}</div>}

      <section className="panel monthly-report-control">
        <div className="monthly-report-heading">
          <div><span className="section-kicker">MONTH-WISE CONTROL</span><h2>Select the reporting month</h2><p>The selected month controls new IT activity reporting and every monthly Excel download below.</p></div>
          <div className={`month-state ${selected?.status || 'live'}`}>
            {selected?.status === 'live' ? <RefreshCw size={18} /> : <LockKeyhole size={18} />}
            <span>{selected?.status === 'live' ? 'Live current register' : selected?.status === 'finalized' ? 'Finalized system snapshot' : 'Original historical Excel'}</span>
          </div>
        </div>
        <div className="monthly-report-selector">
          <label><CalendarDays size={18} /><span>Month</span><select value={selectedMonth} onChange={event => setSelectedMonth(event.target.value)}>{months.map(month => <option key={month.key} value={month.key}>{month.label} — {month.status}</option>)}</select></label>
          <div className="month-count-summary"><strong>{selected?.closing_count ?? '—'}</strong><span>{selected?.closing_count !== undefined ? 'Closing assets' : selected?.status === 'live' ? 'Live register' : 'Historical workbook'}</span></div>
          {selectedMonth !== presentMonth && <button className="secondary-button" type="button" onClick={returnToPresent}><RotateCcw size={17} /> Return to Present Month</button>}
          {user && isFullAccessRole(user.role) && selected?.status === 'live' && <button className="secondary-button" onClick={() => void finalizeSelectedMonth()} disabled={!!busy}><CheckCircle2 size={17} /> {busy === 'finalize' ? 'Finalizing…' : 'Finalize Selected Month'}</button>}
        </div>
      </section>

      <section className="report-grid monthly-download-grid">
        <article className="report-card featured-report">
          <FileSpreadsheet size={34} />
          <span className="section-kicker">ALL MONTHLY INFORMATION</span>
          <h2>{monthLabel} Complete IT Workbook</h2>
          <p>Downloads one reconciled workbook with monthly asset totals, primary IT assets, Printers, External HDDs, asset changes, work records, component changes, full replacements, handovers, returns, purchases, purchase requests and approval history.</p>
          <button className="primary-button" onClick={() => void download(`/reports/complete-monthly.xlsx?month=${monthQuery}`, `NakshaTech Complete IT Report - ${monthLabel}.xlsx`, 'complete-monthly')} disabled={!selectedMonth || !!busy}><FileDown size={17} /> {busy === 'complete-monthly' ? 'Preparing Complete Report…' : 'Download Complete Monthly Workbook'}</button>
        </article>

        <article className="report-card">
          <FileSpreadsheet size={34} />
          <span className="section-kicker">MONTHLY CURRENT VALUES</span>
          <h2>{monthLabel} Asset Register</h2>
          <p>Downloads the selected month in the same NakshaTech Excel structure. It shows the active CPU tag, workstation and the latest monitor, mouse, keyboard, hardware, network and software values for that month.</p>
          <button className="primary-button" onClick={() => void download(`/reports/monthly-assets.xlsx?month=${monthQuery}`, `NakshaTech Asset Register - ${monthLabel}.xlsx`, 'monthly-assets')} disabled={!selectedMonth || !!busy}><FileDown size={17} /> {busy === 'monthly-assets' ? 'Preparing Register…' : 'Download Monthly Asset Register'}</button>
        </article>

        <article className="report-card">
          <History size={34} />
          <span className="section-kicker">USER + DATE/TIME AUDIT</span>
          <h2>{monthLabel} IT Asset Changes</h2>
          <p>Downloads every Full Edit and component operation assigned to the selected reporting month, with the effective month, actual system-recorded date/time, user, role, batch ID, reason, activity remark, and field-by-field old → new values.</p>
          <button className="secondary-button" onClick={() => void download(`/reports/monthly-changes.xlsx?month=${monthQuery}`, `NakshaTech IT Asset Changes - ${monthLabel}.xlsx`, 'monthly-changes')} disabled={!selectedMonth || !!busy}><FileDown size={17} /> {busy === 'monthly-changes' ? 'Preparing Changes…' : 'Download Monthly Asset Changes'}</button>
        </article>

        <article className="report-card">
          <LayoutDashboard size={34} />
          <span className="section-kicker">MONTH MOVEMENT</span>
          <h2>{monthLabel} Asset Summary</h2>
          <p>Shows opening/imported baseline, manually added PCs and laptops, component upgrades, replacements, downgrades, complete asset replacements, returns, retirement and closing count.</p>
          <button className="secondary-button" onClick={() => void download(`/reports/monthly-summary.xlsx?month=${monthQuery}`, `NakshaTech Monthly Asset Summary - ${monthLabel}.xlsx`, 'monthly-summary')} disabled={!selectedMonth || !!busy}><FileDown size={17} /> {busy === 'monthly-summary' ? 'Preparing Summary…' : 'Download Monthly Summary'}</button>
        </article>

        <article className="report-card">
          <FileClock size={34} />
          <span className="section-kicker">COMPLETE MONTHLY IT ACTIVITY</span>
          <h2>{monthLabel} Full Tracking Workbook</h2>
          <p>Combines asset edits, component changes, laptop and desktop handover/return records, purchase details and user activity assigned to the selected reporting month. Each row keeps the actual system-recorded timestamp separately.</p>
          <button className="primary-button" onClick={() => void download(`/it-activity/monthly.xlsx?month=${monthQuery}`, `NakshaTech IT Monthly Activity - ${monthLabel}.xlsx`, 'it-activity')} disabled={!selectedMonth || !!busy}><FileDown size={17} /> {busy === 'it-activity' ? 'Preparing Activity…' : 'Download Complete Monthly Activity'}</button>
        </article>

        <article className="report-card">
          <Printer size={34} />
          <span className="section-kicker">MONTHLY PRINTER REGISTER</span>
          <h2>{monthLabel} Printers</h2>
          <p>Downloads only the Printer assets available in the selected monthly register or finalized snapshot.</p>
          <button className="secondary-button" onClick={() => void download(`/reports/printers.xlsx?month=${monthQuery}`, `NakshaTech Printer Asset Register - ${monthLabel}.xlsx`, 'monthly-printers')} disabled={!selectedMonth || !!busy}><FileDown size={17} /> {busy === 'monthly-printers' ? 'Preparing Printers…' : 'Download Monthly Printers'}</button>
        </article>

        <article className="report-card">
          <FileSpreadsheet size={34} />
          <span className="section-kicker">MONTHLY EXTERNAL HDD REGISTER</span>
          <h2>{monthLabel} External HDDs</h2>
          <p>Downloads the portable External HDD register for the selected month while keeping it separate from the primary IT asset total.</p>
          <button className="secondary-button" onClick={() => void download(`/reports/external-hdds.xlsx?month=${monthQuery}`, `NakshaTech External HDD Asset Register - ${monthLabel}.xlsx`, 'monthly-hdds')} disabled={!selectedMonth || !!busy}><FileDown size={17} /> {busy === 'monthly-hdds' ? 'Preparing External HDDs…' : 'Download Monthly External HDDs'}</button>
        </article>
      </section>

      <section className="panel monthly-report-control">
        <div className="monthly-report-heading">
          <div><span className="section-kicker">YEARLY EXCEL CONTROL</span><h2>Select Calendar Year or Financial Year</h2><p>The complete yearly workbook includes month-by-month asset positions and every detailed IT operation recorded inside the selected period.</p></div>
          <div className="month-state finalized"><LockKeyhole size={18} /><span>Read-only reporting export</span></div>
        </div>
        <div className="monthly-report-selector">
          <label><CalendarDays size={18} /><span>Period</span><select value={yearPeriod} onChange={event => setYearPeriod(event.target.value as 'calendar' | 'financial')}><option value="calendar">Calendar Year — January to December</option><option value="financial">Financial Year — April to March</option></select></label>
          <label><CalendarDays size={18} /><span>Year</span><select value={reportYear} onChange={event => setReportYear(Number(event.target.value))}>{reportYears.map(year => <option key={year} value={year}>{yearPeriod === 'calendar' ? year : `${year}-${String(year + 1).slice(-2)}`}</option>)}</select></label>
          <div className="month-count-summary"><strong>{yearlyLabel}</strong><span>Selected reporting period</span></div>
        </div>
      </section>

      <section className="report-grid monthly-download-grid">
        <article className="report-card featured-report">
          <FileSpreadsheet size={34} />
          <span className="section-kicker">ALL YEARLY INFORMATION</span>
          <h2>{yearlyLabel} Complete IT Workbook</h2>
          <p>Includes all twelve monthly asset-source rows, the latest available closing register, primary assets, Printers, External HDDs, changes, work records, component operations, full replacements, handovers, returns, purchases, purchase requests, approval history and reconciliation checks. Missing historical source months are clearly marked and never replaced with invented values.</p>
          <button className="primary-button" onClick={() => void download(`/reports/complete-yearly.xlsx?year=${reportYear}&period=${yearPeriod}`, `NakshaTech Complete IT Report - ${yearlyLabel}.xlsx`, 'complete-yearly')} disabled={!!busy}><FileDown size={17} /> {busy === 'complete-yearly' ? 'Preparing Yearly Report…' : 'Download Complete Yearly Workbook'}</button>
        </article>
      </section>

      <section className="report-grid">
        <article className="report-card"><FileSpreadsheet size={34} /><span className="section-kicker">LIVE MASTER WORKBOOK</span><h2>NakshaTech Asset Details</h2><p>Downloads the complete live register and preserves the original historical monthly sheets from the workbook provided by your IT team.</p><button className="secondary-button" onClick={() => void download('/reports/nakshatech-assets.xlsx', 'NakshaTech Asset Details.xlsx', 'assets')} disabled={!!busy}><FileDown size={17} /> {busy === 'assets' ? 'Preparing Excel…' : 'Download Complete Asset Excel'}</button></article>
        <article className="report-card"><Printer size={34} /><span className="section-kicker">PRINTER ASSET REGISTER</span><h2>Printer Excel Import & Download</h2><p>Download the dedicated printer register with Asset ID, assigned user, brand, model, serial number, connection, department, floor, status, remarks and last updated date. IT can import the same 11-column format; blank serial numbers are accepted with a warning.</p><button className="secondary-button" onClick={() => void download('/reports/printers.xlsx', 'NakshaTech Printer Asset Register.xlsx', 'printers')} disabled={!!busy}><FileDown size={17} /> {busy === 'printers' ? 'Preparing Printers…' : 'Download Printer Excel'}</button>{user && (user.role === 'it' || isFullAccessRole(user.role)) && <label className="secondary-button file-button"><UploadCloud size={17} /> {busy === 'printer-import' ? 'Importing Printers…' : 'Import Printer Excel'}<input hidden type="file" accept=".xlsx" onChange={event => void importPrinterFile(event)} /></label>}</article>
        <article className="report-card"><LayoutDashboard size={34} /><span className="section-kicker">MANAGEMENT REPORT</span><h2>IT Dashboard Workbook</h2><p>Includes KPI summary, current asset register, status and department charts, work records and data-quality checks.</p><button className="secondary-button" onClick={() => void download('/reports/dashboard.xlsx', 'NakshaTech IT Dashboard.xlsx', 'dashboard')} disabled={!!busy}><FileDown size={17} /> Download Dashboard Excel</button></article>
        <article className="report-card"><History size={34} /><span className="section-kicker">ALL-TIME COMPONENT HISTORY</span><h2>Complete Component Change History</h2><p>Downloads all upgrades, replacements, downgrades and complete asset replacements across every month. Monthly Full Edit audits are available from the selected-month report above.</p><button className="secondary-button" onClick={() => void download('/reports/replacement-history.xlsx', 'NakshaTech Component Change History.xlsx', 'replacement-history')} disabled={!!busy}><FileDown size={17} /> {busy === 'replacement-history' ? 'Preparing History…' : 'Download All-Time History'}</button></article>
        {user && isFullAccessRole(user.role) && <article className="report-card"><UploadCloud size={34} /><span className="section-kicker">FULL ACCESS ONLY</span><h2>Import Updated Excel</h2><p>Upload the NakshaTech workbook. Existing assets are matched using CPU tags or system names, and new records receive system asset IDs.</p><label className="secondary-button file-button"><UploadCloud size={17} /> {busy === 'import' ? 'Importing…' : 'Select Excel File'}<input hidden type="file" accept=".xlsx" onChange={event => void importFile(event)} /></label><button className="text-button" onClick={() => void download('/reports/upload-template.xlsx', 'NakshaTech IT Asset Upload Template.xlsx', 'template')}>Download blank upload template</button></article>}
      </section>

      <section className="panel report-notes"><h2>How reporting-month continuity works</h2><div className="check-grid"><span>✓ The selected month remains active across all IT pages</span><span>✓ Current register always shows the latest live asset values</span><span>✓ New actions are assigned to the selected reporting month</span><span>✓ Actual system-recorded date and time remain immutable</span><span>✓ Present-month activity totals are not increased by a historical-month entry</span><span>✓ Activity remarks stay only with that individual activity and month</span><span>✓ Activity remarks never carry automatically into the next month</span><span>✓ Asset Master Remarks remain separate and persist only when intentionally edited</span><span>✓ Multiple component changes can share one batch and work record</span><span>✓ Old values remain in separate history</span><span>✓ Return to Present Month is the deliberate reset action</span><span>✓ Monthly Excel includes effective month and actual recorded timestamp</span></div></section>
    </>
  )
}
