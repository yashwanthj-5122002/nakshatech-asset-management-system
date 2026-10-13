import {
  CheckCircle2,
  CircleDollarSign,
  FileCheck2,
  LockKeyhole,
  RefreshCcw,
  Send,
  ShieldAlert,
  Truck,
  UsersRound,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { StatCard } from '../../../components/StatCard'
import { apiFetch } from '../../../lib/api'
import '../operations.css'
import '../project-completion.css'

type ViewerMode = 'bd_delivery' | 'department' | 'finance_closure' | 'read_only'

type Workstream = {
  id: number
  department_code: string
  department_label: string
  project_manager_user_id: number
  project_manager_name?: string | null
  status: string
  completed_at?: string | null
  incoming_handovers: number
  unresolved_incoming: number
  outgoing_handovers: number
  unresolved_outgoing: number
  can_complete: boolean
}

type Completion = {
  id: number
  project_id: number
  final_output_reference: string
  delivery_remarks?: string | null
  delivered_by_name?: string | null
  delivered_at: string
  finance_status: string
  finance_note?: string | null
  finance_acknowledged_by_name?: string | null
  finance_acknowledged_at?: string | null
  financially_closed_by_name?: string | null
  financially_closed_at?: string | null
  updated_at?: string | null
}

type ProjectRow = {
  project_id: number
  project_code: string
  project_name: string
  client_name?: string | null
  project_status: string
  opportunity_id?: number | null
  opportunity_code?: string | null
  readiness: {
    ready: boolean
    total_workstreams: number
    completed_workstreams: number
    incomplete_department_codes: string[]
    total_handovers: number
    accepted_handovers: number
    unresolved_handover_codes: string[]
  }
  workstreams: Workstream[]
  completion?: Completion | null
  permissions: {
    can_deliver: boolean
    can_update_finance: boolean
  }
}

type Dashboard = {
  viewer_mode: ViewerMode
  current_role: string
  demo_mode: boolean
  routing_mode?: string
  live_technical_routing_enabled?: boolean
  summary: {
    visible_projects: number
    ready_for_delivery: number
    delivered_projects: number
    pending_finance: number
    financially_closed: number
  }
  projects: ProjectRow[]
}

type DeliveryDraft = { reference: string; remarks: string }
type CompletionDraft = { note: string }
type FinanceDraft = { note: string }

function label(value: string) {
  return value.replaceAll('_', ' ').replace(/\b\w/g, char => char.toUpperCase())
}

function dateTime(value?: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString('en-IN')
}

export function ProjectCompletionPage() {
  const [data, setData] = useState<Dashboard | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState('')
  const [deliveryDrafts, setDeliveryDrafts] = useState<Record<number, DeliveryDraft>>({})
  const [completionDrafts, setCompletionDrafts] = useState<Record<number, CompletionDraft>>({})
  const [financeDrafts, setFinanceDrafts] = useState<Record<number, FinanceDraft>>({})

  function load() {
    setError('')
    void apiFetch<Dashboard>('/operations/project-completion/dashboard')
      .then(setData)
      .catch(err => setError(err instanceof Error ? err.message : 'Unable to load Project Completion'))
  }

  useEffect(load, [])

  const title = useMemo(() => {
    if (!data) return 'Project Completion'
    if (data.viewer_mode === 'bd_delivery') return 'Master Project Final Delivery'
    if (data.viewer_mode === 'finance_closure') return 'Delivered Projects · Finance Closure'
    if (data.viewer_mode === 'department') return 'Department Completion'
    return 'Master Project Completion Oversight'
  }, [data])

  function completionDraft(row: Workstream) {
    return completionDrafts[row.id] ?? { note: '' }
  }

  function deliveryDraft(project: ProjectRow) {
    return deliveryDrafts[project.project_id] ?? { reference: '', remarks: '' }
  }

  function financeDraft(project: ProjectRow) {
    return financeDrafts[project.project_id] ?? { note: project.completion?.finance_note ?? '' }
  }

  async function completeDepartment(row: Workstream) {
    const draft = completionDraft(row)
    setBusy(`complete-${row.id}`)
    setError('')
    setNotice('')
    try {
      const result = await apiFetch<Dashboard>(`/operations/project-completion/workstreams/${row.id}/complete`, {
        method: 'POST',
        body: JSON.stringify({ note: draft.note || null }),
      })
      setData(result)
      setCompletionDrafts(current => {
        const next = { ...current }
        delete next[row.id]
        return next
      })
      setNotice(`${row.department_label} marked complete. Master Project readiness was recalculated.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not complete department workstream')
    } finally {
      setBusy('')
    }
  }

  async function deliverProject(project: ProjectRow) {
    const draft = deliveryDraft(project)
    if (!draft.reference.trim()) {
      setError('Enter the final project output / shared folder / delivery reference.')
      return
    }
    setBusy(`deliver-${project.project_id}`)
    setError('')
    setNotice('')
    try {
      const result = await apiFetch<{
        project_id: number
        finance_notifications_created: number
        finance_email_sent: number
        finance_email_failed: number
      }>(`/operations/bd/project-completion/projects/${project.project_id}/deliver`, {
        method: 'POST',
        body: JSON.stringify({
          final_output_reference: draft.reference.trim(),
          remarks: draft.remarks.trim() || null,
        }),
      })
      setNotice(
        `${project.project_code} final delivery saved. Finance dashboard notifications: ${result.finance_notifications_created}. ` +
        `Email sent: ${result.finance_email_sent}; failed: ${result.finance_email_failed}. Email failure does not roll back delivery.`
      )
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not record Master Project final delivery')
    } finally {
      setBusy('')
    }
  }

  async function updateFinance(project: ProjectRow, status: 'billing_in_progress' | 'financially_closed') {
    const draft = financeDraft(project)
    setBusy(`finance-${project.project_id}-${status}`)
    setError('')
    setNotice('')
    try {
      const result = await apiFetch<Dashboard & { bd_notifications_created?: number }>(
        `/operations/finance/project-completion/projects/${project.project_id}/status`,
        {
          method: 'PATCH',
          body: JSON.stringify({ status, note: draft.note.trim() || null }),
        },
      )
      setData(result)
      setNotice(
        status === 'financially_closed'
          ? `${project.project_code} marked financially closed. BD notification created: ${result.bd_notifications_created ?? 0}.`
          : `${project.project_code}: Finance billing / closure work started.`
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update Finance closure status')
    } finally {
      setBusy('')
    }
  }

  return <div className="operations-page project-completion-page">
    <DashboardHeader
      eyebrow="MASTER PROJECT · FINAL DELIVERY · FINANCE HANDOFF"
      title={title}
      description={data?.viewer_mode === 'bd_delivery'
        ? 'Final delivery unlocks only after every selected technical department is complete and every inter-team data handover is accepted. Finance is notified only after the delivery transaction is saved.'
        : data?.viewer_mode === 'department'
          ? 'Complete only your own department workstream after all required incoming and outgoing data handovers are accepted.'
          : data?.viewer_mode === 'finance_closure'
            ? 'Finance receives only projects whose Master Project Final Delivery is already recorded. Start billing/closure, then mark financially closed when financial follow-up is complete.'
            : 'Read-only oversight of technical completion, Master Project delivery and Finance closure status.'}
      actions={<button className="operations-button secondary" type="button" onClick={load}><RefreshCcw size={16}/> Refresh</button>}
      meta={<>
        <span className="nk-meta-chip"><LockKeyhole size={14}/> Delivery unlocks only after every handover is accepted</span>
        <span className="nk-meta-chip"><FileCheck2 size={14}/> Final delivery is recorded once per master project</span>
        <span className="nk-meta-chip"><CircleDollarSign size={14}/> Finance closure follows delivery</span>
      </>}
    />

    {data && <div className="completion-demo-banner"><ShieldAlert size={16}/><strong>{data.live_technical_routing_enabled?'Phase 7 LIVE:':'Phase 5 UAT:'}</strong> {data.live_technical_routing_enabled?'department completion is owned by the assigned real PM and configured real completion recipients are notified after commit.':'technical completion actions remain restricted to reserved demo department PM accounts.'}</div>}
    {notice && <div className="success-message">{notice}</div>}
    {error && <div className="error-message">{error}</div>}

    <section className="stats-grid completion-stats">
      <StatCard icon={FileCheck2} label="Visible Projects" value={data?.summary.visible_projects ?? '—'} />
      <StatCard icon={CheckCircle2} label="Ready for Final Delivery" value={data?.summary.ready_for_delivery ?? '—'} tone="green" />
      <StatCard icon={Truck} label="Master Projects Delivered" value={data?.summary.delivered_projects ?? '—'} tone="purple" />
      <StatCard icon={CircleDollarSign} label="Finance Follow-up Pending" value={data?.summary.pending_finance ?? '—'} tone="orange" />
      <StatCard icon={CheckCircle2} label="Financially Closed" value={data?.summary.financially_closed ?? '—'} tone="green" />
    </section>

    {!data
      ? <section className="operations-panel"><div className="operations-empty">Loading Project Completion…</div></section>
      : data.projects.length === 0
        ? <section className="operations-panel"><div className="operations-empty">No projects are available for this login at the current completion stage.</div></section>
        : <div className="completion-project-list">{data.projects.map(project => {
            const delivery = deliveryDraft(project)
            const finance = financeDraft(project)
            const completeCount = project.readiness.completed_workstreams
            const totalCount = project.readiness.total_workstreams
            return <section className={`operations-panel completion-project ${project.completion ? 'is-delivered' : project.readiness.ready ? 'is-ready' : ''}`} key={project.project_id}>
              <header className="completion-project-head">
                <div>
                  <span className="operations-kicker">{project.opportunity_code || 'MASTER PROJECT'}</span>
                  <h2>{project.project_code} · {project.project_name}</h2>
                  <p>{project.client_name || 'Client not recorded'} · Finance Project status: {label(project.project_status)}</p>
                </div>
                <div className="completion-state-box">
                  {project.completion
                    ? <><span className="operations-status success">Delivered</span><strong>{label(project.completion.finance_status)}</strong></>
                    : project.readiness.ready
                      ? <><span className="operations-status success">Ready</span><strong>Final Delivery Unlocked</strong></>
                      : <><span className="operations-status warning">Not Ready</span><strong>{completeCount}/{totalCount} Teams Complete</strong></>}
                </div>
              </header>

              <div className="completion-readiness-strip">
                <span><strong>{completeCount}/{totalCount}</strong> department workstreams complete</span>
                <span><strong>{project.readiness.accepted_handovers}/{project.readiness.total_handovers}</strong> data handovers accepted</span>
                <span><strong>{project.readiness.unresolved_handover_codes.length}</strong> unresolved handovers</span>
              </div>

              {!project.readiness.ready && !project.completion && <div className="completion-gate-note"><LockKeyhole size={16}/><span>Final Delivery remains locked until every selected department is completed and every active data handover is accepted.</span></div>}

              <div className="completion-workstream-grid">
                {project.workstreams.map(row => {
                  const draft = completionDraft(row)
                  return <article className={`completion-workstream ${row.status === 'completed' ? 'done' : ''}`} key={row.id}>
                    <div className="completion-workstream-head">
                      <strong>{row.department_label}</strong>
                      <span className={`operations-status ${row.status === 'completed' ? 'success' : row.unresolved_incoming || row.unresolved_outgoing ? 'warning' : ''}`}>{label(row.status)}</span>
                    </div>
                    <div className="completion-pm"><UsersRound size={14}/><span>{row.project_manager_name || 'Project Manager'}</span></div>
                    <div className="completion-dependency-grid">
                      <span>Incoming <strong>{row.incoming_handovers - row.unresolved_incoming}/{row.incoming_handovers}</strong> accepted</span>
                      <span>Outgoing <strong>{row.outgoing_handovers - row.unresolved_outgoing}/{row.outgoing_handovers}</strong> accepted</span>
                    </div>
                    {row.completed_at && <small>Completed: {dateTime(row.completed_at)}</small>}
                    {row.can_complete && <div className="completion-team-action">
                      <label><span>Completion Note</span><textarea value={draft.note} onChange={event => setCompletionDrafts(current => ({ ...current, [row.id]: { note: event.target.value } }))} placeholder="Final output / milestone note"/></label>
                      <button className="operations-button" type="button" disabled={busy === `complete-${row.id}`} onClick={() => void completeDepartment(row)}><CheckCircle2 size={15}/> Complete My Department</button>
                    </div>}
                  </article>
                })}
              </div>

              {project.permissions.can_deliver && !project.completion && <div className="completion-delivery-box">
                <div><span className="operations-kicker">BD FINAL DELIVERY</span><h3>All Technical Gates Passed</h3><p>Record the Master Project delivery only after the client-facing final package is ready.</p></div>
                <label><span>Final Output / Shared Folder / Delivery Reference</span><input value={delivery.reference} onChange={event => setDeliveryDrafts(current => ({ ...current, [project.project_id]: { reference: event.target.value, remarks: current[project.project_id]?.remarks ?? '' } }))} placeholder="Shared folder, document reference, delivery URL or internal path"/></label>
                <label><span>Delivery Remarks</span><textarea value={delivery.remarks} onChange={event => setDeliveryDrafts(current => ({ ...current, [project.project_id]: { reference: current[project.project_id]?.reference ?? '', remarks: event.target.value } }))} placeholder="Client delivery note, package summary or final remarks"/></label>
                <button className="operations-button" type="button" disabled={busy === `deliver-${project.project_id}`} onClick={() => void deliverProject(project)}><Send size={16}/> Record Master Final Delivery</button>
              </div>}

              {project.completion && <div className="completion-delivered-box">
                <div className="completion-delivered-head"><Truck size={18}/><div><span className="operations-kicker">MASTER FINAL DELIVERY</span><h3>Delivered to Client / Finance Handoff Created</h3></div></div>
                <div className="completion-delivered-grid">
                  <span><strong>Final Output</strong>{project.completion.final_output_reference}</span>
                  <span><strong>Delivered By</strong>{project.completion.delivered_by_name || 'BD'}</span>
                  <span><strong>Delivered At</strong>{dateTime(project.completion.delivered_at)}</span>
                  <span><strong>Finance Status</strong>{label(project.completion.finance_status)}</span>
                </div>
                {project.completion.delivery_remarks && <p>{project.completion.delivery_remarks}</p>}
              </div>}

              {project.permissions.can_update_finance && project.completion && <div className="completion-finance-box">
                <div><span className="operations-kicker">FINANCE OWNERSHIP</span><h3>Billing / Settlement / Financial Closure</h3><p>Technical delivery is already locked and saved. Finance controls only the financial follow-up state below.</p></div>
                <label><span>Finance Note</span><textarea value={finance.note} onChange={event => setFinanceDrafts(current => ({ ...current, [project.project_id]: { note: event.target.value } }))} placeholder="Invoice, payment follow-up, settlement or closure note"/></label>
                <div className="operations-actions">
                  {project.completion.finance_status === 'pending_billing' && <button className="operations-button secondary" type="button" disabled={busy.startsWith(`finance-${project.project_id}`)} onClick={() => void updateFinance(project, 'billing_in_progress')}><CircleDollarSign size={15}/> Start Billing / Closure</button>}
                  {project.completion.finance_status === 'billing_in_progress' && <button className="operations-button" type="button" disabled={busy.startsWith(`finance-${project.project_id}`)} onClick={() => void updateFinance(project, 'financially_closed')}><CheckCircle2 size={15}/> Mark Financially Closed</button>}
                </div>
                {project.completion.finance_acknowledged_at && <small>Finance acknowledged: {dateTime(project.completion.finance_acknowledged_at)} · {project.completion.finance_acknowledged_by_name || 'Finance'}</small>}
                {project.completion.financially_closed_at && <small>Financially closed: {dateTime(project.completion.financially_closed_at)} · {project.completion.financially_closed_by_name || 'Finance'}</small>}
              </div>}
            </section>
          })}</div>}
  </div>
}
