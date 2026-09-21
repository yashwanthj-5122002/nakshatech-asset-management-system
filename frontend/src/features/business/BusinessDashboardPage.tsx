import { CheckCircle2, Clock3, History, IndianRupee, RefreshCcw, Save, TrendingUp, WalletCards } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../components/DashboardHeader'
import { useAuth } from '../../context/AuthContext'
import { apiFetch } from '../../lib/api'
import type { BusinessHistoryEntry, BusinessOverview, BusinessRecordRow } from '../../types'
import '../finance/finance-expenses.css'
import './business.css'
import {
  businessDepartments,
  businessStatusTone,
  businessViewerLabel,
  canEnterBusiness,
  canSeeBusinessTotals,
  currentReportingMonth,
  formatInr,
  monthLabel,
} from './business-utils'

interface Draft {
  amount_total: string
  amount_released: string
  amount_decided: string
  amount_pending: string
  department_code: string
  notes: string
}

type HistoryState = { row: BusinessRecordRow; entries: BusinessHistoryEntry[] } | null

function toNumber(value: string): number | null {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed < 0) return null
  return parsed
}

function DraftInput({
  label,
  value,
  onChange,
  disabled,
}: {
  label: string
  value: string
  onChange: (next: string) => void
  disabled: boolean
}) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span style={{ fontSize: '0.68rem', color: '#5a6b7c', textTransform: 'uppercase', letterSpacing: '0.03em' }}>{label}</span>
      <input
        className="business-amount-input"
        type="number"
        min={0}
        step="0.01"
        inputMode="decimal"
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  )
}

export function BusinessDashboardPage() {
  const { user } = useAuth()
  const role = user?.role
  const isFinance = canEnterBusiness(role)
  const isPrivileged = canSeeBusinessTotals(role)
  const canVerify = role === 'management' || role === 'admin' || role === 'software_team'

  const [month, setMonth] = useState(currentReportingMonth)
  const [data, setData] = useState<BusinessOverview | null>(null)
  const [drafts, setDrafts] = useState<Record<number, Draft>>({})
  const [history, setHistory] = useState<HistoryState>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [savedRow, setSavedRow] = useState<number | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    setHistory(null)
    void apiFetch<BusinessOverview>(`/business/overview?month=${encodeURIComponent(month)}`)
      .then((payload) => setData(payload))
      .catch((err) => setError(err instanceof Error ? err.message : 'Could not load Business data'))
      .finally(() => setLoading(false))
  }, [month])

  useEffect(load, [load])

  useEffect(() => {
    if (!data) return
    const next: Record<number, Draft> = {}
    for (const row of data.rows) {
      next[row.project_id] = {
        amount_total: String(row.amount_total ?? 0),
        amount_released: String(row.amount_released ?? 0),
        amount_decided: String(row.amount_decided ?? 0),
        amount_pending: String(row.amount_pending ?? 0),
        department_code: row.department_code,
        notes: row.notes ?? '',
      }
    }
    setDrafts(next)
  }, [data])

  const groups = useMemo(() => {
    const map = new Map<string, BusinessRecordRow[]>()
    for (const row of data?.rows ?? []) {
      const key = row.client_name || 'Unassigned client'
      const list = map.get(key)
      if (list) list.push(row)
      else map.set(key, [row])
    }
    return [...map.entries()]
  }, [data])

  const enteredRows = (data?.rows ?? []).filter((row) => row.record_id != null)
  const verifiedCount = enteredRows.filter((row) => row.status === 'verified').length

  function updateDraft(projectId: number, patch: Partial<Draft>) {
    setDrafts((current) => ({ ...current, [projectId]: { ...current[projectId], ...patch } }))
  }

  async function saveRow(row: BusinessRecordRow) {
    const draft = drafts[row.project_id]
    if (!draft) return
    const amounts = {
      amount_total: toNumber(draft.amount_total),
      amount_released: toNumber(draft.amount_released),
      amount_decided: toNumber(draft.amount_decided),
      amount_pending: toNumber(draft.amount_pending),
    }
    if (Object.values(amounts).some((value) => value === null)) {
      setError('Enter a valid non-negative amount for every field.')
      return
    }
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await apiFetch('/business/records', {
        method: 'POST',
        body: JSON.stringify({
          project_id: row.project_id,
          reporting_month: month,
          ...amounts,
          department_code: draft.department_code,
          notes: draft.notes || null,
        }),
      })
      setNotice(`Saved ${row.project_code} for ${monthLabel(month)}.`)
      setSavedRow(row.project_id)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save this month')
    } finally {
      setBusy(false)
      window.setTimeout(() => setSavedRow(null), 2500)
    }
  }

  async function verifyMonth(verified: boolean) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const result = await apiFetch<{ records_updated: number }>('/business/verify', {
        method: 'POST',
        body: JSON.stringify({ reporting_month: month, verified }),
      })
      setNotice(`${monthLabel(month)} ${verified ? 'verified' : 'reopened'} (${result.records_updated} record(s)).`)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update the verification state')
    } finally {
      setBusy(false)
    }
  }

  async function openHistory(row: BusinessRecordRow) {
    if (row.record_id == null) return
    setError('')
    try {
      const entries = await apiFetch<BusinessHistoryEntry[]>(`/business/records/${row.record_id}/history`)
      setHistory({ row, entries })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load history')
    }
  }

  const headerActions = (
    <div className="finance-header-actions">
      <button className="finance-secondary-button" type="button" onClick={load}><RefreshCcw size={16} /> Refresh</button>
      {canVerify && enteredRows.length > 0 && (verifiedCount < enteredRows.length
        ? <button className="finance-primary-button" type="button" disabled={busy} onClick={() => verifyMonth(true)}><CheckCircle2 size={16} /> Verify Month</button>
        : <button className="finance-secondary-button" type="button" disabled={busy} onClick={() => verifyMonth(false)}>Reopen Month</button>)}
    </div>
  )

  return (
    <div className="finance-page">
      <DashboardHeader
        eyebrow="BUSINESS · TOTAL SELL"
        title={data ? businessViewerLabel(data.viewer) : 'Business & Total Sell'}
        description={isPrivileged
          ? 'Finance records the monthly business done per client/project. Totals roll up by department, Project Manager and client, and every change is kept in history.'
          : 'Track how much business your projects have done each month and how the funds have moved. Only BD and Finance see company-wide totals.'}
        actions={headerActions}
      />

      <section className="business-month-bar">
        <label className="business-month-field">
          <span>Reporting month</span>
          <input type="month" value={month} onChange={(event) => setMonth(event.target.value || currentReportingMonth())} />
        </label>
        {!!data?.months?.length && (
          <div className="finance-header-actions">
            {data.months.slice(0, 6).map((value) => (
              <button
                key={value}
                type="button"
                className={value === month ? 'finance-primary-button' : 'finance-secondary-button'}
                onClick={() => setMonth(value)}
              >
                {monthLabel(value)}
              </button>
            ))}
          </div>
        )}
      </section>

      {notice && <div className="finance-success-message">{notice}</div>}
      {error && <div className="finance-error">{error} <button type="button" className="finance-inline-link" onClick={load}>Retry</button></div>}
      {loading && <div className="finance-panel finance-empty-state">Loading Business data…</div>}

      {!loading && data?.viewer === 'unavailable' && (
        <div className="finance-panel finance-empty-state">
          You are not currently assigned as a Project Manager on any project, so there is no business data to show.
        </div>
      )}

      {!loading && data && data.viewer !== 'unavailable' && (
        <>
          <section className="finance-kpi-grid finance-kpi-grid-4">
            <article className="finance-kpi-card"><span><TrendingUp size={15} /> Total business</span><strong>{formatInr(data.totals.total)}</strong><small>{monthLabel(data.month)}</small></article>
            <article className="finance-kpi-card"><span><IndianRupee size={15} /> Released</span><strong>{formatInr(data.totals.released)}</strong><small>Funds released by clients</small></article>
            <article className="finance-kpi-card"><span><WalletCards size={15} /> Decided</span><strong>{formatInr(data.totals.decided)}</strong><small>Approved / decided value</small></article>
            <article className="finance-kpi-card"><span><Clock3 size={15} /> Pending</span><strong>{formatInr(data.totals.pending)}</strong><small>Still pending</small></article>
          </section>

          {isPrivileged && (
            <section className="finance-breakdown-grid">
              {([['By Department', data.by_department], ['By Project Manager', data.by_project_manager], ['By Client', data.by_client]] as const).map(([title, items]) => (
                <BreakdownPanel key={title} title={title} items={items} />
              ))}
            </section>
          )}

          {data.viewer === 'project_manager' && data.my_monthly_history.length > 0 && (
            <section className="finance-panel">
              <div className="finance-panel-header">
                <div><span className="finance-panel-kicker">MONTH-BY-MONTH</span><h2>My Business History</h2><p>Total business you have done each month across your projects.</p></div>
              </div>
              <div className="finance-table-wrap">
                <table className="finance-table business-trend-table">
                  <thead><tr><th>Month</th><th>Total</th><th>Released</th><th>Decided</th><th>Pending</th></tr></thead>
                  <tbody>
                    {data.my_monthly_history.map((point) => (
                      <tr key={point.month}>
                        <td><strong>{point.label}</strong></td>
                        <td>{formatInr(point.total)}</td>
                        <td>{formatInr(point.released)}</td>
                        <td>{formatInr(point.decided)}</td>
                        <td>{formatInr(point.pending)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <section className="finance-panel">
            <div className="finance-panel-header">
              <div>
                <span className="finance-panel-kicker">{isFinance ? 'FINANCE ENTRY · PER CLIENT / PROJECT' : 'MONTHLY BUSINESS BY PROJECT'}</span>
                <h2>{isFinance ? 'Monthly Business Entry' : `${monthLabel(data.month)} Business`}</h2>
                <p>{isFinance
                  ? 'Record how much business each project did this month. Amounts roll up automatically; changes are kept in history.'
                  : 'Project-wise business recorded by Finance for the selected month.'}</p>
              </div>
              {isPrivileged && <small>{verifiedCount} of {enteredRows.length} record(s) verified</small>}
            </div>

            {groups.length === 0 && <div className="finance-empty-state">No projects are available to record for this month yet.</div>}

            {groups.map(([clientName, rows]) => (
              <div key={clientName} style={{ marginBottom: '1rem' }}>
                <h3 className="finance-panel-subheading">{clientName}</h3>
                <div className="finance-table-wrap">
                  <table className="finance-table business-entry-table">
                    <thead>
                      <tr>
                        <th>Project</th>
                        <th>Project Manager</th>
                        <th>Department</th>
                        <th>Total</th>
                        <th>Released</th>
                        <th>Decided</th>
                        <th>Pending</th>
                        <th>Status</th>
                        <th>{isFinance ? 'Action' : 'History'}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row) => {
                        const draft = drafts[row.project_id]
                        const editable = isFinance
                        return (
                          <tr key={row.project_id} className={savedRow === row.project_id ? 'business-row-saved' : undefined}>
                            <td><strong>{row.project_code}</strong><br /><small>{row.project_name}</small></td>
                            <td>{row.project_manager_name || 'PM not assigned'}</td>
                            <td>
                              {editable ? (
                                <select
                                  className="business-department-select"
                                  value={draft?.department_code || row.department_code}
                                  onChange={(event) => updateDraft(row.project_id, { department_code: event.target.value })}
                                >
                                  {businessDepartments.map((department) => (
                                    <option key={department.code} value={department.code}>{department.label}</option>
                                  ))}
                                </select>
                              ) : row.department_label}
                            </td>
                            {editable && draft ? (
                              <>
                                <td><DraftInput label="total" value={draft.amount_total} disabled={busy} onChange={(value) => updateDraft(row.project_id, { amount_total: value })} /></td>
                                <td><DraftInput label="released" value={draft.amount_released} disabled={busy} onChange={(value) => updateDraft(row.project_id, { amount_released: value })} /></td>
                                <td><DraftInput label="decided" value={draft.amount_decided} disabled={busy} onChange={(value) => updateDraft(row.project_id, { amount_decided: value })} /></td>
                                <td><DraftInput label="pending" value={draft.amount_pending} disabled={busy} onChange={(value) => updateDraft(row.project_id, { amount_pending: value })} /></td>
                              </>
                            ) : (
                              <>
                                <td>{formatInr(row.amount_total)}</td>
                                <td>{formatInr(row.amount_released)}</td>
                                <td>{formatInr(row.amount_decided)}</td>
                                <td>{formatInr(row.amount_pending)}</td>
                              </>
                            )}
                            <td>
                              {row.record_id == null
                                ? <span className="finance-status tone-draft">Not recorded</span>
                                : <span className={`finance-status tone-${businessStatusTone(row.status)}`}>{row.status}</span>}
                            </td>
                            <td>
                              <div className="finance-header-actions">
                                {editable && <button className="finance-primary-button" type="button" disabled={busy} onClick={() => saveRow(row)}><Save size={15} /> Save</button>}
                                {row.record_id != null && <button className="finance-secondary-button" type="button" onClick={() => openHistory(row)}><History size={15} /> History</button>}
                              </div>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}

            {history && (
              <div className="business-history-panel">
                <h4>History · {history.row.project_code} ({monthLabel(month)})</h4>
                {history.entries.length === 0 && <div className="finance-empty-state">No changes recorded yet.</div>}
                <div className="business-history-list">
                  {history.entries.map((entry) => (
                    <div className="business-history-item" key={entry.id}>
                      <b>{entry.action}</b> · {entry.actor_name || 'System'} ({entry.actor_role || 'system'}) · {new Date(entry.created_at).toLocaleString('en-IN')}
                      {entry.changes && (
                        <span> — {Object.entries(entry.changes).map(([field, change]) => `${field}: ${change.from ?? '—'} → ${change.to ?? '—'}`).join('; ')}</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}

function BreakdownPanel({ title, items }: { title: string; items: BusinessOverview['by_department'] }) {
  const max = useMemo(() => Math.max(1, ...items.map((item) => item.total)), [items])
  return (
    <article className="finance-panel">
      <div className="finance-panel-header">
        <div><span className="finance-panel-kicker">ANALYTICS</span><h2>{title}</h2><p>Business done in the selected month.</p></div>
      </div>
      {items.length === 0
        ? <div className="finance-empty-state">No business recorded for this month.</div>
        : <div className="finance-breakdown-list">
            {items.slice(0, 8).map((item) => (
              <div className="finance-breakdown-row" key={item.key}>
                <div><span>{item.label}</span><span>{formatInr(item.total)} · {item.project_count} project(s)</span></div>
                <div className="finance-breakdown-track"><i style={{ width: `${Math.max(4, (item.total / max) * 100)}%` }} /></div>
              </div>
            ))}
          </div>}
    </article>
  )
}
