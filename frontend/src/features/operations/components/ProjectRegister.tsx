import { CheckCircle2, ChevronDown, Search } from 'lucide-react'
import type { ReactNode } from 'react'
import { FINANCE_STATUS_OPTIONS, OPERATIONAL_STATUS_OPTIONS, financeLabel, label, operationalLabel, statusKey, type ProjectFilterFields, type StatusOption } from './register-utils'
import '../operations.css'

/**
 * Project Register presentation shared by BD Project Management (mutating) and
 * the Finance Project Register (readOnly). With `readOnly`, the per-row
 * mutation slots (`renderProjectManager`, `renderActions`) are never invoked, so
 * only the Details button remains.
 */

export type RegisterProjectEvent = {
  id: number; event_type: string; from_status?: string | null; to_status: string; comments?: string | null
  actor_name?: string | null; actor_role?: string | null; created_at: string
}

export type RegisterProject = ProjectFilterFields & {
  id: number; project_name: string; client_name?: string | null
  start_date?: string | null; end_date?: string | null; scope_text?: string | null
  commercial_value?: number | null; currency?: string | null; po_wo_number?: string | null; attachment_references?: string[]
  finance_feedback?: string | null; project_manager_id?: number | null; project_manager_name?: string | null
  submission_count?: number; finance_reviewer_name?: string | null; finance_reviewed_at?: string | null; events?: RegisterProjectEvent[]
}

export function ProjectRegisterFilters({ query, onQueryChange, financeFilter, onFinanceFilterChange, operationalFilter, onOperationalFilterChange, financeOptions = FINANCE_STATUS_OPTIONS }: {
  query: string
  onQueryChange: (value: string) => void
  financeFilter: string
  onFinanceFilterChange: (value: string) => void
  operationalFilter: string
  onOperationalFilterChange: (value: string) => void
  financeOptions?: StatusOption[]
}) {
  return <div className="operations-filter-grid"><label className="operations-search"><Search size={16} /><input value={query} onChange={e => onQueryChange(e.target.value)} placeholder="Search Project ID / Client ID" /></label><label className="operations-field"><span>Finance Status</span><select value={financeFilter} onChange={e => onFinanceFilterChange(e.target.value)}><option value="all">All</option>{financeOptions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label><label className="operations-field"><span>Operational Status</span><select value={operationalFilter} onChange={e => onOperationalFilterChange(e.target.value)}><option value="all">All</option>{OPERATIONAL_STATUS_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label></div>
}

export function ProjectRegisterTable<T extends RegisterProject>({ rows, readOnly = false, onDetails, renderProjectManager, renderActions }: {
  rows: T[]
  readOnly?: boolean
  onDetails: (row: T) => void
  /** Editable Project Manager cell. Return null to fall back to the plain name. Ignored when readOnly. */
  renderProjectManager?: (row: T) => ReactNode | null
  /** Extra row actions shown after Details. Ignored when readOnly. */
  renderActions?: (row: T) => ReactNode
}) {
  return <div className="operations-table-wrap"><table className="operations-table"><thead><tr><th>Project / Client</th><th>Finance Status</th><th>Operational Status</th><th>Project Manager</th><th>Actions</th></tr></thead><tbody>{rows.map(row => {
    const editableManager = readOnly ? null : renderProjectManager?.(row) ?? null
    const tone = statusKey(row) === 'finance_returned' ? ' danger' : statusKey(row) ? ' warning' : ''
    return <tr key={row.id}><td><button className="operations-row-link" onClick={() => onDetails(row)}><strong>{row.project_code}</strong><small>{row.client_code} · {row.project_name}</small></button></td><td><span className={`operations-status${tone}`}>{financeLabel(row)}</span></td><td>{operationalLabel(row)}</td><td>{editableManager ?? (row.project_manager_name || 'Not assigned')}</td><td><div className="operations-actions"><button className="operations-button secondary" onClick={() => onDetails(row)}><ChevronDown size={14} /> Details</button>{!readOnly && renderActions?.(row)}</div></td></tr>
  })}{!rows.length && <tr><td colSpan={5}><div className="operations-empty">No projects match these filters.</div></td></tr>}</tbody></table></div>
}

export function ProjectDetailsPanel({ project }: { project: RegisterProject }) {
  return <section className="operations-panel"><header><div><span className="operations-kicker">{project.client_code} · {project.project_code}</span><h2>{project.project_name}</h2><p>{project.start_date || '—'} → {project.end_date || '—'}</p></div><span className="operations-status">{financeLabel(project)}</span></header>
    <div className="operations-detail-grid"><div><span>Project Scope</span><strong>{project.scope_text || '—'}</strong></div><div><span>Commercial</span><strong>{project.currency || 'INR'} {project.commercial_value?.toLocaleString('en-IN') || '—'}</strong></div><div><span>PO / WO</span><strong>{project.po_wo_number || '—'}</strong></div><div><span>Attachments</span><strong>{project.attachment_references?.join(', ') || 'None recorded'}</strong></div><div><span>Finance Reviewer</span><strong>{project.finance_reviewer_name || 'Not reviewed'} {project.finance_reviewed_at ? `· ${new Date(project.finance_reviewed_at).toLocaleString('en-IN')}` : ''}</strong></div><div><span>Submission Count</span><strong>{project.submission_count || 0}</strong></div></div>
    {project.finance_feedback && <div className="operations-alert error"><b>Finance feedback:</b> {project.finance_feedback}</div>}
    <div className="operations-activity-list">{(project.events ?? []).slice().reverse().map(event => <div key={event.id}><CheckCircle2 size={15} /><div><strong>{label(event.event_type)} · {event.actor_name || 'System'}</strong><span>{new Date(event.created_at).toLocaleString('en-IN')} · {label(event.to_status)}</span>{event.comments && <small>{event.comments}</small>}</div></div>)}</div>
  </section>
}
