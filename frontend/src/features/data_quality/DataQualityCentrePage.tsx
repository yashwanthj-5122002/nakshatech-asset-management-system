import { useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  BadgeCheck,
  CalendarDays,
  ChevronDown,
  CircleAlert,
  DatabaseZap,
  RefreshCw,
  SearchCheck,
  ShieldCheck,
} from 'lucide-react'
import { apiFetch } from '../../lib/api'
import { useITMonthUrl } from '../../context/ITMonthContext'
import { monthLabel } from '../../lib/itMonth'
import './data-quality-centre.css'

type Severity = 'high' | 'medium' | 'low' | 'info'

interface DataQualityMonth {
  key: string
  label: string
  source: string
  status: string
  is_live: boolean
  data_available: boolean
}

interface DataQualityRecord {
  record_type: string
  record_id: string
  asset_code?: string
  device_type?: string
  status?: string
  department?: string
  serial_number?: string
  current_value?: string
  expected_value?: string
  note?: string
}

interface DataQualityIssue {
  code: string
  title: string
  severity: Severity
  scope: string
  description: string
  count: number
  records: DataQualityRecord[]
}

interface DataQualitySummary {
  read_only: boolean
  allowed_actions: string[]
  checked_at: string
  month: DataQualityMonth
  metrics: Record<string, number>
  reconciliation: Record<string, number | string | boolean>
  issues: DataQualityIssue[]
}

const severityLabels: Record<Severity, string> = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
  info: 'Information',
}

function displayValue(value: string | number | boolean | undefined): string {
  if (value === undefined || value === null || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return String(value)
}

export function DataQualityCentrePage() {
  const { selectedMonth, presentMonth, setSelectedMonth } = useITMonthUrl()
  const [summary, setSummary] = useState<DataQualitySummary | null>(null)
  const [severity, setSeverity] = useState<'all' | Severity>('all')
  const [issueCode, setIssueCode] = useState('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refreshToken, setRefreshToken] = useState(0)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    void apiFetch<DataQualitySummary>(`/data-quality/summary?month=${selectedMonth}`)
      .then(result => {
        if (active) setSummary(result)
      })
      .catch(err => {
        if (active) setError(err instanceof Error ? err.message : 'Could not load the Data Quality Centre.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [refreshToken, selectedMonth])

  const filteredIssues = useMemo(() => {
    if (!summary) return []
    return summary.issues.filter(issue => (
      (severity === 'all' || issue.severity === severity)
      && (issueCode === 'all' || issue.code === issueCode)
    ))
  }, [issueCode, severity, summary])

  const sourceLabel = summary?.month.source === 'live'
    ? 'Live register'
    : summary?.month.source === 'snapshot'
      ? 'Finalized snapshot'
      : summary?.month.source === 'template'
        ? 'Historical workbook'
        : 'No verified source'

  return (
    <section className="data-quality-page">
      <header className="data-quality-hero">
        <div className="data-quality-hero-icon"><SearchCheck size={25} /></div>
        <div>
          <span className="data-quality-eyebrow">Read-only IT validation</span>
          <h1>Data Quality Centre</h1>
          <p>Review asset, reporting-month and reconciliation findings without changing any source record.</p>
        </div>
        <div className="data-quality-readonly"><ShieldCheck size={16} /> Read-only</div>
      </header>

      <div className="data-quality-safety-banner">
        <BadgeCheck size={21} />
        <div>
          <strong>No corrections can be made from this page</strong>
          <p>Filters, month selection and refresh only change what you see. Existing authorised asset, Printer, External HDD and reporting workflows remain the only places where data can be corrected.</p>
        </div>
      </div>

      <section className="data-quality-controls" aria-label="Data quality filters">
        <label>
          <span>Reporting month</span>
          <input
            type="month"
            value={selectedMonth}
            max={presentMonth}
            onChange={event => setSelectedMonth(event.target.value)}
          />
        </label>
        <label>
          <span>Severity</span>
          <select value={severity} onChange={event => setSeverity(event.target.value as 'all' | Severity)}>
            <option value="all">All severities</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
            <option value="info">Information</option>
          </select>
        </label>
        <label>
          <span>Issue type</span>
          <select value={issueCode} onChange={event => setIssueCode(event.target.value)}>
            <option value="all">All issue types</option>
            {summary?.issues.map(issue => (
              <option key={issue.code} value={issue.code}>{issue.title}</option>
            ))}
          </select>
        </label>
        <button type="button" className="data-quality-refresh" onClick={() => setRefreshToken(value => value + 1)} disabled={loading}>
          <RefreshCw size={16} className={loading ? 'spinning' : ''} /> Refresh findings
        </button>
      </section>

      {error && <div className="data-quality-error"><AlertTriangle size={18} /><span>{error}</span></div>}

      <section className="data-quality-summary-grid">
        <article>
          <CircleAlert size={20} />
          <span>Issue groups</span>
          <strong>{summary?.metrics.issue_groups ?? 0}</strong>
          <small>{summary?.metrics.findings ?? 0} total findings</small>
        </article>
        <article>
          <AlertTriangle size={20} />
          <span>High findings</span>
          <strong>{summary?.metrics.high_findings ?? 0}</strong>
          <small>Requires review in source workflows</small>
        </article>
        <article>
          <DatabaseZap size={20} />
          <span>Total IT assets</span>
          <strong>{summary?.metrics.primary_it_assets ?? 0}</strong>
          <small>{summary?.metrics.external_hdds ?? 0} External HDDs separate</small>
        </article>
        <article>
          <CalendarDays size={20} />
          <span>{summary?.month.label ?? monthLabel(selectedMonth)}</span>
          <strong className="data-quality-source-value">{sourceLabel}</strong>
          <small>{summary?.month.data_available ? 'Verified source available' : 'Historical data unavailable'}</small>
        </article>
      </section>

      <section className="data-quality-reconciliation-card">
        <div>
          <h2>Selected-month reconciliation</h2>
          <p>Every distribution should reconcile to the same primary IT asset population.</p>
        </div>
        <span className={summary?.reconciliation.reconciled ? 'reconciled' : 'not-reconciled'}>
          {summary?.reconciliation.reconciled ? 'Reconciled' : 'Review required'}
        </span>
        <dl>
          <div><dt>Total IT Assets</dt><dd>{displayValue(summary?.reconciliation.primary_it_assets)}</dd></div>
          <div><dt>Device distribution</dt><dd>{displayValue(summary?.reconciliation.device_distribution_total)}</dd></div>
          <div><dt>Status distribution</dt><dd>{displayValue(summary?.reconciliation.status_distribution_total)}</dd></div>
          <div><dt>Department distribution</dt><dd>{displayValue(summary?.reconciliation.department_distribution_total)}</dd></div>
          <div><dt>Visible department chart</dt><dd>{displayValue(summary?.reconciliation.dashboard_department_visible_total)}</dd></div>
          <div><dt>All asset records</dt><dd>{displayValue(summary?.reconciliation.all_asset_records)}</dd></div>
        </dl>
      </section>

      <section className="data-quality-findings">
        <div className="data-quality-section-heading">
          <div>
            <h2>Detected findings</h2>
            <p>{filteredIssues.length} issue group{filteredIssues.length === 1 ? '' : 's'} match the current filters.</p>
          </div>
          {loading && <span className="data-quality-loading"><RefreshCw size={15} className="spinning" /> Checking data…</span>}
        </div>

        {!loading && filteredIssues.length === 0 && (
          <div className="data-quality-empty">
            <BadgeCheck size={38} />
            <strong>No findings for the selected filters</strong>
            <p>This page remains read-only. Change the month or filters to inspect another view.</p>
          </div>
        )}

        {filteredIssues.map(issue => (
          <details className={`data-quality-issue severity-${issue.severity}`} key={issue.code} open={issue.severity === 'high'}>
            <summary>
              <span className="data-quality-severity">{severityLabels[issue.severity]}</span>
              <span className="data-quality-issue-title">
                <strong>{issue.title}</strong>
                <small>{issue.description}</small>
              </span>
              <span className="data-quality-count">{issue.count}</span>
              <ChevronDown size={18} />
            </summary>
            <div className="data-quality-issue-body">
              {issue.records.length === 0 ? (
                <p className="data-quality-no-details">No row-level details are available for this finding.</p>
              ) : (
                <div className="data-quality-table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Type / Reference</th>
                        <th>Asset / Device</th>
                        <th>Status / Department</th>
                        <th>Current value</th>
                        <th>Expected / Note</th>
                      </tr>
                    </thead>
                    <tbody>
                      {issue.records.map((record, index) => (
                        <tr key={`${issue.code}-${record.record_type}-${record.record_id}-${index}`}>
                          <td><strong>{record.record_type}</strong><small>{record.record_id}</small></td>
                          <td><strong>{record.asset_code || '—'}</strong><small>{record.device_type || '—'}{record.serial_number ? ` · ${record.serial_number}` : ''}</small></td>
                          <td><strong>{record.status || '—'}</strong><small>{record.department || '—'}</small></td>
                          <td>{record.current_value || '—'}</td>
                          <td><strong>{record.expected_value || '—'}</strong><small>{record.note || ''}</small></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </details>
        ))}
      </section>
    </section>
  )
}
