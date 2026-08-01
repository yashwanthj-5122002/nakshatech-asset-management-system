import {
  AlertTriangle,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Database,
  Download,
  FileJson,
  FileSpreadsheet,
  HardDrive,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../components/DashboardHeader'
import { useAuth } from '../context/AuthContext'
import { apiFetch, downloadFile } from '../lib/api'
import type { BackupRun, BackupStatus, BackupType } from '../types'

function todayKey() {
  const now = new Date()
  const offset = now.getTimezoneOffset() * 60_000
  return new Date(now.getTime() - offset).toISOString().slice(0, 10)
}

function currentMonthKey() {
  return todayKey().slice(0, 7)
}

function currentFinancialYear() {
  const now = new Date()
  const start = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1
  return `${start}-${String(start + 1).slice(-2)}`
}

function formatBytes(value?: number | null) {
  if (!value) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = value
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  return `${size.toFixed(index > 1 ? 1 : 0)} ${units[index]}`
}

function formatDate(value?: string | null) {
  if (!value) return 'Never'
  return new Date(value).toLocaleString()
}

function statusClass(status: string) {
  if (status === 'completed') return 'success'
  if (status === 'completed_with_warnings') return 'warning'
  if (status === 'failed') return 'danger'
  return 'info'
}

export function BackupCenterPage() {
  const { user } = useAuth()
  const [status, setStatus] = useState<BackupStatus | null>(null)
  const [history, setHistory] = useState<BackupRun[]>([])
  const [backupType, setBackupType] = useState<BackupType>('current_month')
  const [period, setPeriod] = useState(currentMonthKey())
  const [scope, setScope] = useState<'all' | 'it' | 'drone'>(
    user?.role === 'it' ? 'it' : user?.role === 'drone' ? 'drone' : 'all',
  )
  const [includeDatabase, setIncludeDatabase] = useState(true)
  const [includeMinio, setIncludeMinio] = useState(false)
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const canChooseScope = user?.role === 'admin' || user?.role === 'management'
  const canRunServerBackup = user?.role === 'admin'

  const periodInput = useMemo(() => {
    if (backupType === 'daily') return { type: 'date', value: period || todayKey() }
    if (backupType === 'monthly') return { type: 'month', value: period || currentMonthKey() }
    if (backupType === 'yearly') return { type: 'number', value: period || String(new Date().getFullYear()) }
    if (backupType === 'financial_year') return { type: 'text', value: period || currentFinancialYear() }
    return null
  }, [backupType, period])

  async function load() {
    setError('')
    try {
      const [statusData, historyData] = await Promise.all([
        apiFetch<BackupStatus>('/backups/status'),
        apiFetch<BackupRun[]>(`/backups/history?scope=${encodeURIComponent(scope)}&limit=50`),
      ])
      setStatus(statusData)
      setHistory(historyData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load backup status')
    }
  }

  useEffect(() => { void load() }, [scope])

  function changeType(value: BackupType) {
    setBackupType(value)
    if (value === 'daily') setPeriod(todayKey())
    else if (value === 'monthly' || value === 'current_month') setPeriod(currentMonthKey())
    else if (value === 'yearly') setPeriod(String(new Date().getFullYear()))
    else if (value === 'financial_year') setPeriod(currentFinancialYear())
    else setPeriod('')
  }

  async function downloadReport() {
    setBusy('download'); setMessage(''); setError('')
    try {
      const query = new URLSearchParams({ backup_type: backupType, scope })
      if (periodInput?.value) query.set('period', periodInput.value)
      await downloadFile(`/backups/export.xlsx?${query.toString()}`, `NakshaTech ${scope.toUpperCase()} Backup.xlsx`)
      setMessage('Excel backup downloaded successfully.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Excel download failed')
    } finally {
      setBusy('')
    }
  }

  async function runServerBackup() {
    setBusy('run'); setMessage(''); setError('')
    try {
      const query = new URLSearchParams({
        backup_type: backupType,
        scope,
        include_database: String(includeDatabase && scope === 'all'),
        include_minio: String(includeMinio && scope === 'all'),
      })
      if (periodInput?.value) query.set('period', periodInput.value)
      const result = await apiFetch<BackupRun>(`/backups/run?${query.toString()}`, { method: 'POST' })
      setMessage(`${result.backup_code} finished with status: ${result.status.replaceAll('_', ' ')}.`)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Server backup failed')
    } finally {
      setBusy('')
    }
  }

  async function downloadSaved(run: BackupRun, fileType: 'excel' | 'database' | 'minio' | 'manifest') {
    setBusy(`${run.id}-${fileType}`); setError(''); setMessage('')
    try {
      await downloadFile(`/backups/files/${run.id}/${fileType}`, `${run.backup_code}-${fileType}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Saved backup download failed')
    } finally {
      setBusy('')
    }
  }

  return (
    <>
      <DashboardHeader
        eyebrow="DISASTER-SAFE BACKUP CENTRE"
        title="Backups & Historical Excel"
        description="Download day, month, current-month, calendar-year and financial-year records. Scheduled server backups remain outside the public website folder."
      />

      {message && <div className="success-message">{message}</div>}
      {error && <div className="error-message">{error}</div>}

      <section className="backup-health-grid">
        <article className="backup-health-card">
          <span className="backup-health-icon success"><ShieldCheck size={22} /></span>
          <div><span>Storage</span><strong>{status?.storage_writable ? 'Ready' : 'Check required'}</strong><small>{status?.storage_root || 'Protected server folder'}</small></div>
        </article>
        <article className="backup-health-card">
          <span className="backup-health-icon info"><Clock3 size={22} /></span>
          <div><span>Last successful backup</span><strong>{formatDate(status?.last_success?.completed_at)}</strong><small>{status?.last_success?.backup_code || 'No completed backup yet'}</small></div>
        </article>
        <article className="backup-health-card">
          <span className={`backup-health-icon ${status?.pg_dump_available ? 'success' : 'warning'}`}><Database size={22} /></span>
          <div><span>Database recovery</span><strong>{status?.pg_dump_available ? 'pg_dump ready' : 'Needs server setup'}</strong><small>{status?.database_backup_enabled ? 'Database backup enabled' : 'Database backup disabled'}</small></div>
        </article>
        <article className="backup-health-card">
          <span className="backup-health-icon info"><RefreshCw size={22} /></span>
          <div><span>Automatic schedule</span><strong>Daily server cron</strong><small>{status?.timezone || 'Asia/Kolkata'}</small></div>
        </article>
      </section>

      <section className="panel backup-control-panel">
        <div className="backup-control-copy">
          <span className="section-kicker">DOWNLOAD OR SAVE</span>
          <h2>Create a protected report</h2>
          <p>Manual Download sends an Excel copy to your browser. Admin Server Backup also saves verified files in the protected server backup directory.</p>
        </div>
        <div className="backup-control-grid">
          <label><span>Report period</span><select value={backupType} onChange={event => changeType(event.target.value as BackupType)}>
            <option value="daily">Selected day</option>
            <option value="monthly">Selected month</option>
            <option value="current_month">Current month live</option>
            <option value="yearly">Calendar year</option>
            <option value="financial_year">Financial year</option>
            <option value="full">Complete current backup</option>
          </select></label>
          {periodInput && <label><span>{backupType === 'financial_year' ? 'Financial year' : 'Period'}</span><input type={periodInput.type} value={periodInput.value} placeholder={backupType === 'financial_year' ? '2026-27' : undefined} onChange={event => setPeriod(event.target.value)} /></label>}
          <label><span>Department scope</span><select value={scope} disabled={!canChooseScope} onChange={event => setScope(event.target.value as 'all' | 'it' | 'drone')}>
            {canChooseScope && <option value="all">Complete system</option>}
            {(canChooseScope || user?.role === 'it') && <option value="it">IT only</option>}
            {(canChooseScope || user?.role === 'drone') && <option value="drone">Drone only</option>}
          </select></label>
        </div>
        {canRunServerBackup && <div className="backup-option-row">
          <label className="checkbox-line"><input type="checkbox" checked={includeDatabase} disabled={scope !== 'all'} onChange={event => setIncludeDatabase(event.target.checked)} /> Include PostgreSQL recovery dump</label>
          <label className="checkbox-line"><input type="checkbox" checked={includeMinio} disabled={scope !== 'all' || !status?.minio_backup_enabled} onChange={event => setIncludeMinio(event.target.checked)} /> Include uploaded-file archive when enabled</label>
        </div>}
        <div className="backup-action-row">
          <button className="primary-button" disabled={!!busy} onClick={() => void downloadReport()}><FileSpreadsheet size={18} />{busy === 'download' ? 'Preparing Excel…' : 'Download Excel'}</button>
          {canRunServerBackup && <button className="secondary-button" disabled={!!busy} onClick={() => void runServerBackup()}><HardDrive size={18} />{busy === 'run' ? 'Creating protected backup…' : 'Save Backup on Server'}</button>}
          <button className="text-button" disabled={!!busy} onClick={() => void load()}><RefreshCw size={16} /> Refresh status</button>
        </div>
      </section>

      <section className="panel backup-history-panel">
        <div className="backup-history-heading">
          <div><span className="section-kicker">SAVED BACKUPS</span><h2>Server backup history</h2></div>
          <span className="record-count">{history.length}</span>
        </div>
        <div className="table-scroll">
          <table className="backup-history-table">
            <thead><tr><th>Backup</th><th>Period</th><th>Scope</th><th>Status</th><th>Excel</th><th>Database</th><th>Created</th><th>Files</th></tr></thead>
            <tbody>
              {history.map(run => (
                <tr key={run.id}>
                  <td><strong>{run.backup_code}</strong><small>{run.backup_type.replaceAll('_', ' ')}</small></td>
                  <td>{run.period_start || 'All time'}{run.period_end && run.period_end !== run.period_start ? ` → ${run.period_end}` : ''}</td>
                  <td>{run.scope.toUpperCase()}</td>
                  <td><span className={`status-badge ${statusClass(run.status)}`}>{run.status.replaceAll('_', ' ')}</span></td>
                  <td>{formatBytes(run.excel_size_bytes)}</td>
                  <td>{formatBytes(run.database_size_bytes)}</td>
                  <td>{formatDate(run.completed_at || run.created_at)}</td>
                  <td><div className="backup-file-actions">
                    {run.excel_filename && <button title="Download Excel" onClick={() => void downloadSaved(run, 'excel')} disabled={!!busy}><FileSpreadsheet size={16} /></button>}
                    {user?.role === 'admin' && run.database_filename && <button title="Download database dump" onClick={() => void downloadSaved(run, 'database')} disabled={!!busy}><Database size={16} /></button>}
                    {user?.role === 'admin' && run.minio_filename && <button title="Download uploaded-file archive" onClick={() => void downloadSaved(run, 'minio')} disabled={!!busy}><Download size={16} /></button>}
                    {user?.role === 'admin' && run.manifest_filename && <button title="Download manifest" onClick={() => void downloadSaved(run, 'manifest')} disabled={!!busy}><FileJson size={16} /></button>}
                  </div></td>
                </tr>
              ))}
              {!history.length && <tr><td colSpan={8}><div className="backup-empty-state"><CalendarDays size={28} /><strong>No saved backups yet</strong><span>Admin can create the first server backup, or the cPanel cron job will create it automatically.</span></div></td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section className="backup-note-grid">
        <article><CheckCircle2 size={20} /><div><strong>Safe location</strong><span>Production backups must be stored under the cPanel account home, outside public_html and outside the application directory.</span></div></article>
        <article><AlertTriangle size={20} /><div><strong>Full recovery</strong><span>Excel is for viewing and audit. Restore the PostgreSQL dump during disaster recovery; never restore from the browser.</span></div></article>
      </section>
    </>
  )
}
