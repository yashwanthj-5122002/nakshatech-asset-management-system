import { CheckCircle2, History, IndianRupee, RefreshCcw, Save, TrendingUp, Wand2, WalletCards } from 'lucide-react'
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

function draftFromBilling(row: BusinessRecordRow): Draft {
  return {
    amount_total: String(row.billing.total ?? 0),
    amount_released: String(row.billing.released ?? 0),
    amount_pending: String(row.billing.pending ?? 0),
    department_code: row.department_code,
    notes: '',
  }
}

function billingDiffers(row: BusinessRecordRow): boolean {
  if (row.record_id == null) return false
  return Math.abs(row.amount_total - row.billing.total) > 0.004
    || Math.abs(row.amount_released - row.billing.released) > 0.004
    || Math.abs(row.amount_pending - row.billing.pending) > 0.004
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

  // Not-yet-saved rows start from the Billing & Invoices figures so Finance only has to verify and save.
  useEffect(() => {
    if (!data) return
    const next: Record<number, Draft> = {}
    for (const row of data.rows) {
      const saved = row.record_id != null
      next[row.project_id] = saved
        ? {
            amount_total: String(row.amount_total ?? 0),
            amount_released: String(row.amount_released ?? 0),
            amount_pending: String(row.amount_pending ?? 0),
            department_code: row.department_code,
            notes: row.notes ?? '',
          }
        : draftFromBilling(row)
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
  const pendingBillingRows = (data?.rows ?? []).filter(
    (row) => row.record_id == null && (row.billing.invoice_count > 0 || row.billing.payment_count > 0),
  )

  function updateDraft(projectId: number, patch: Partial<Draft>) {
    setDrafts((current) => ({ ...current, [projectId]: { ...current[projectId], ...patch } }))
  }

  function fillFromBilling(row: BusinessRecordRow) {
    setDrafts((current) => ({ ...current, [row.project_id]: { ...current[row.project_id], ...draftFromBilling(row) } }))
  }

  function fillAllFromBilling() {
    setDrafts((current) => {
      const next = { ...current }
      for (const row of pendingBillingRows) next[row.project_id] = { ...next[row.project_id], ...draftFromBilling(row) }
      return next
    })
    setNotice(`Filled ${pendingBillingRows.length} project(s) from Billing & Invoices. Review, then save.`)
  }

  async function saveRow(row: BusinessRecordRow) {
    const draft = drafts[row.project_id]
    if (!draft) return
    const amounts = {
      amount_total: toNumber(draft.amount_total),
      amount_released: toNumber(draft.amount_released),
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
      {isFinance && pendingBillingRows.length > 0 && (
        <button className="finance-secondary-button" type="button" onClick={fillAllFromBilling}>
          <Wand2 size={16} /> Fill {pendingBillingRows.length} from Billing
        </button>
      )}
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
          ? 'Figures come from Billing & Invoices for the month. Verify them, save, and every change is kept in history.'
          : 'Track how much business your projects have done and how much the client has paid.'}
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

      {!loading && data?.viewer === 'project_manager' && (
        <>
          <section className="finance-kpi-grid" style={{ gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' }}>
            <article className="finance-kpi-card"><span><TrendingUp size={15} /> Business done</span><strong>{formatInr(data.totals.total)}</strong><small>{monthLabel(data.month)}</small></article>
            <article className="finance-kpi-card"><span><IndianRupee size={15} /> Client paid</span><strong>{formatInr(data.totals.released)}</strong><small>Amount received from the client</small></article>
          </section>

          {data.my_monthly_history.length > 0 && (
            <section className="finance-panel">
              <div className="finance-panel-header">
                <div><span className="finance-panel-kicker">MONTH-BY-MONTH</span><h2>My Business History</h2><p>Business done and client payments each month across your projects.</p></div>
              </div>
              <div className="finance-table-wrap">
                <table className="finance-table business-trend-table">
                  <thead><tr><th>Month</th><th>Business done</th><th>Client paid</th></tr></thead>
                  <tbody>
                    {data.my_monthly_history.map((point) => (
                      <tr key={point.month}>
                        <td><strong>{point.label}</strong></td>
                        <td>{formatInr(point.total)}</td>
                        <td>{formatInr(point.released)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <section className="finance-panel">
            <div className="finance-panel-header">
              <div><span className="finance-panel-kicker">MY PROJECTS</span><h2>{monthLabel(data.month)} Business</h2><p>Business done and the amount the client has paid for each of your projects.</p></div>
            </div>
            {data.rows.length === 0
              ? <div className="finance-empty-state">No business recorded for your projects this month.</div>
              : <div className="finance-table-wrap">
                  <table className="finance-table">
                    <thead><tr><th>Project</th><th>Client</th><th>Business done</th><th>Client paid</th></tr></thead>
                    <tbody>
                      {data.rows.map((row) => (
                        <tr key={row.project_id}>
                          <td><strong>{row.project_code}</strong><br /><small>{row.project_name}</small></td>
                          <td>{row.client_name || '—'}</td>
                          <td><strong>{formatInr(row.amount_total)}</strong></td>
                          <td>{formatInr(row.amount_released)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>}
          </section>
        </>
      )}

      {!loading && data && isPrivileged && (
        <>
          <section className="finance-kpi-grid" style={{ gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' }}>
            <article className="finance-kpi-card"><span><TrendingUp size={15} /> Total business</span><strong>{formatInr(data.totals.total)}</strong><small>{monthLabel(data.month)} · invoiced</small></article>
            <article className="finance-kpi-card"><span><IndianRupee size={15} /> Released</span><strong>{formatInr(data.totals.released)}</strong><small>Received from clients this month</small></article>
            <article className="finance-kpi-card"><span><WalletCards size={15} /> Pending</span><strong>{formatInr(data.totals.pending)}</strong><small>Still outstanding</small></article>
          </section>

          <section className="finance-breakdown-grid">
            {([['By Department', data.by_department], ['By Project Manager', data.by_project_manager], ['By Client', data.by_client]] as const).map(([title, items]) => (
              <BreakdownPanel key={title} title={title} items={items} />
            ))}
          </section>

          <section className="finance-panel">
            <div className="finance-panel-header">
              <div>
                <span className="finance-panel-kicker">{isFinance ? 'FINANCE ENTRY · FROM BILLING & INVOICES' : 'MONTHLY BUSINESS BY PROJECT'}</span>
                <h2>{isFinance ? 'Monthly Business Entry' : `${monthLabel(data.month)} Business`}</h2>
                <p>{isFinance
                  ? 'Values are pre-filled from Billing & Invoices. Check them against the billing record, adjust if needed, then Save. Every change is kept in history.'
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
                        <th>Pending</th>
                        <th>Status</th>
                        <th>{isFinance ? 'Action' : 'History'}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row) => {
                        const draft = drafts[row.project_id]
                        const editable = isFinance
                        const hasBilling = row.billing.invoice_count > 0 || row.billing.payment_count > 0
                        return (
                          <tr key={row.project_id} className={savedRow === row.project_id ? 'business-row-saved' : undefined}>
                            <td>
                              <strong>{row.project_code}</strong><br /><small>{row.project_name}</small>
                              {!row.record_id && hasBilling && <><br /><span className="business-source-tag">From Billing</span></>}
                              {billingDiffers(row) && <><br /><small className="business-drift">Billing now: {formatInr(row.billing.total)} / {formatInr(row.billing.released)}</small></>}
                            </td>
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
                                <td><DraftInput label="pending" value={draft.amount_pending} disabled={busy} onChange={(value) => updateDraft(row.project_id, { amount_pending: value })} /></td>
                              </>
                            ) : (
                              <>
                                <td><strong>{formatInr(row.amount_total)}</strong></td>
                                <td>{formatInr(row.amount_released)}</td>
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
                                {editable && hasBilling && <button className="finance-secondary-button" type="button" disabled={busy} onClick={() => fillFromBilling(row)}><Wand2 size={15} /> Use Billing</button>}
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
