import { ArrowLeft, Building2, FolderOpen, FolderPlus, LayoutGrid, MapPin, Search, Table2, UserRound, X } from 'lucide-react'
import { useRef } from 'react'
import { buildPageList, CLIENT_SORT_OPTIONS, isClientSortKey, isPageSize, PAGE_SIZE_OPTIONS } from './client-register-utils'
import { label } from './register-utils'
import type { ClientRegisterState } from './useClientRegister'
import '../operations.css'
import '../client-register.css'

/**
 * Client Register presentation shared by BD Client Management (mutating) and the
 * Finance Client Register (readOnly). With `readOnly`, every mutation control is
 * omitted from the DOM, not merely hidden. Search, sort, pagination and the
 * Cards / Excel switch come from `useClientRegister`, so both pages behave the same.
 */

export type RegisterClient = {
  id: number; client_code: string; client_name: string; client_email?: string | null; organization_email?: string | null
  location?: string | null; country?: string | null; gst_number?: string | null; contact_person_name: string
  contact_person_email?: string | null; contact_person_phone?: string | null; bd_name?: string | null; source_person_name?: string | null
  project_count: number; created_by_name?: string | null; updated_by_name?: string | null
  address?: string | null; primary_phone?: string | null; created_at?: string | null
}

export type RegisterClientProject = {
  id: number; project_code: string; project_name: string; scope_text?: string | null
  start_date?: string | null; end_date?: string | null; status: string
}

export function ClientRegisterPanel({ register, onView, onCreateProject, onCreateClient, readOnly = false, loading = false }: {
  register: ClientRegisterState<RegisterClient>
  onView: (clientId: number) => void
  onCreateProject?: (clientId: number) => void
  onCreateClient?: () => void
  readOnly?: boolean
  loading?: boolean
}) {
  const panelRef = useRef<HTMLElement>(null)
  const createProject = !readOnly ? onCreateProject : undefined
  const createClient = !readOnly ? onCreateClient : undefined
  const rows = register.pageRows
  const goToPage = (page: number) => { register.setPage(page); panelRef.current?.scrollIntoView({ block: 'start' }) }
  return <section ref={panelRef} className="operations-panel client-register"><header><div><span className="operations-kicker">CLIENT REGISTER</span><h2>Existing Clients</h2></div></header>
    <ClientRegisterToolbar register={register} loading={loading} />
    {loading && <div className="operations-empty">Loading clients...</div>}
    {!loading && rows.length > 0 && (register.view === 'excel'
      ? <ClientExcelView rows={rows} onView={onView} onCreateProject={createProject} />
      : <ClientCardView rows={rows} onView={onView} onCreateProject={createProject} />)}
    {!loading && !rows.length && (register.totalCount === 0
      ? <div className="nk-empty"><span className="nk-empty-icon"><Building2 size={22} /></span><h3>No clients registered yet</h3><p>Clients are the starting point for every project in this register. Register the first client to begin creating and tracking project work.</p>{createClient && <div className="nk-empty-action"><button className="operations-button" onClick={createClient}>New Client</button></div>}</div>
      : <div className="nk-empty"><span className="nk-empty-icon"><Search size={22} /></span><h3>No matching clients</h3><p>Nothing matches “{register.query}”. Try another Client ID, name, country or contact, or clear the search to see the full Client Register.</p><div className="nk-empty-action"><button type="button" className="operations-button secondary" onClick={register.clearSearch}>Clear search</button></div></div>)}
    {!loading && register.pageCount > 1 && <ClientPagination page={register.page} pageCount={register.pageCount} onChange={goToPage} />}
  </section>
}

export function ClientRegisterToolbar({ register, loading = false }: { register: ClientRegisterState<RegisterClient>; loading?: boolean }) {
  const filtered = register.query !== '' && register.filteredCount !== register.totalCount
  const count = loading ? 'Loading clients...'
    : register.filteredCount === 0 ? `Showing 0 of ${register.filteredCount} clients${filtered ? ` (filtered from ${register.totalCount})` : ''}`
    : `Showing ${register.rangeStart}–${register.rangeEnd} of ${register.filteredCount} client${register.filteredCount === 1 ? '' : 's'}${filtered ? ` (filtered from ${register.totalCount})` : ''}`
  return <div className="client-register-toolbar">
    <div className="client-register-controls">
      <label className="operations-search client-register-search"><Search size={16} />
        <input type="text" aria-label="Search clients" value={register.searchInput} onChange={event => register.setSearchInput(event.target.value)} placeholder="Search Client ID, Name, Country, State, City, Contact..." />
        {register.searchInput !== '' && <button type="button" className="client-register-clear" aria-label="Clear search" onClick={register.clearSearch}><X size={15} /></button>}
      </label>
      <label className="client-register-control"><span>Sort</span>
        <select value={register.sort} onChange={event => { if (isClientSortKey(event.target.value)) register.setSort(event.target.value) }}>{CLIENT_SORT_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select>
      </label>
      <div className="client-register-control"><span id="client-register-view-label">View</span>
        <div className="client-register-viewswitch" role="group" aria-labelledby="client-register-view-label">
          <button type="button" aria-pressed={register.view === 'cards'} className={register.view === 'cards' ? 'active' : ''} onClick={() => register.setView('cards')}><LayoutGrid size={14} /> Cards</button>
          <button type="button" aria-pressed={register.view === 'excel'} className={register.view === 'excel' ? 'active' : ''} onClick={() => register.setView('excel')}><Table2 size={14} /> Excel</button>
        </div>
      </div>
      <label className="client-register-control"><span>Clients per page</span>
        <select value={register.pageSize} onChange={event => { const size = Number(event.target.value); if (isPageSize(size)) register.setPageSize(size) }}>{PAGE_SIZE_OPTIONS.map(size => <option key={size} value={size}>{size}</option>)}</select>
      </label>
    </div>
    <p className="client-register-count" aria-live="polite">{count}</p>
  </div>
}

type ClientViewProps = { rows: RegisterClient[]; onView: (clientId: number) => void; onCreateProject?: (clientId: number) => void }

export function ClientCardView({ rows, onView, onCreateProject }: ClientViewProps) {
  return <div className="operations-client-grid">{rows.map(row => <article key={row.id} className="operations-client-card"><div><Building2 size={22} /><span className="operations-status">{row.client_code}</span></div><h3>{row.client_name}</h3><p><MapPin size={14} />{row.location || row.country || 'Location not recorded'}</p><p><UserRound size={14} />{row.contact_person_name || 'Contact not recorded'}</p><strong>{row.project_count} Project{row.project_count === 1 ? '' : 's'}</strong><div className="operations-actions"><button className="operations-button secondary" onClick={() => onView(row.id)}>View Client</button>{onCreateProject && <button className="operations-button" onClick={() => onCreateProject(row.id)}><FolderPlus size={15} /> Create Project</button>}</div></article>)}</div>
}

function formatCreated(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleDateString('en-IN')
}

function cell(value?: string | null) {
  return value ? <span title={value}>{value}</span> : <span className="client-excel-empty">—</span>
}

export function ClientExcelView({ rows, onView, onCreateProject }: ClientViewProps) {
  return <div className="operations-table-wrap client-excel-wrap"><table className="operations-table client-excel-table">
    <thead><tr><th>Client ID</th><th>Client Name</th><th>Country</th><th>Location</th><th>Contact Person</th><th>Phone</th><th>Email</th><th className="client-excel-num">Projects</th><th>Created</th><th>Action</th></tr></thead>
    <tbody>{rows.map(row => <tr key={row.id}>
      <td className="client-excel-id">{row.client_code}</td>
      <td className="client-excel-name">{cell(row.client_name)}</td>
      <td>{cell(row.country)}</td>
      <td className="client-excel-wide">{cell(row.location || row.address)}</td>
      <td>{cell(row.contact_person_name)}</td>
      <td>{cell(row.contact_person_phone || row.primary_phone)}</td>
      <td className="client-excel-wide">{cell(row.contact_person_email || row.client_email || row.organization_email)}</td>
      <td className="client-excel-num">{row.project_count}</td>
      <td>{formatCreated(row.created_at)}</td>
      <td className="client-excel-actions"><button className="operations-button secondary" onClick={() => onView(row.id)}>View Client</button>{onCreateProject && <button className="operations-button" onClick={() => onCreateProject(row.id)}><FolderPlus size={14} /> Create Project</button>}</td>
    </tr>)}</tbody>
  </table></div>
}

export function ClientPagination({ page, pageCount, onChange }: { page: number; pageCount: number; onChange: (page: number) => void }) {
  return <nav className="client-register-pagination" aria-label="Client register pages">
    <button type="button" disabled={page <= 1} onClick={() => onChange(page - 1)}>Previous</button>
    {buildPageList(page, pageCount).map((item, index) => item === 'gap'
      ? <span key={`gap-${index}`} className="client-register-gap" aria-hidden="true">…</span>
      : <button key={item} type="button" className={item === page ? 'active' : ''} aria-current={item === page ? 'page' : undefined} aria-label={`Page ${item}`} onClick={() => onChange(item)}>{item}</button>)}
    <button type="button" disabled={page >= pageCount} onClick={() => onChange(page + 1)}>Next</button>
  </nav>
}

export function BackToClientsButton({ onClick }: { onClick: () => void }) {
  return <button className="operations-button secondary" onClick={onClick}><ArrowLeft size={15} /> Back to Clients</button>
}

export function ClientDetailPanel({ client, readOnly = false, onCreateProject }: { client: RegisterClient; readOnly?: boolean; onCreateProject?: () => void }) {
  return <section className="operations-panel"><header><div><span className="operations-kicker">{client.client_code}</span><h2>{client.client_name}</h2><p>{client.location || client.country || 'Location not recorded'}</p></div>{!readOnly && onCreateProject && <button className="operations-button" onClick={onCreateProject}><FolderPlus size={15} /> Create Project</button>}</header>
    <div className="operations-detail-grid operations-client-detail-grid"><div><span>GST</span><strong>{client.gst_number || '—'}</strong></div><div><span>Client Email</span><strong>{client.client_email || '—'}</strong></div><div><span>Organization Email</span><strong>{client.organization_email || '—'}</strong></div><div><span>Contact Person</span><strong>{client.contact_person_name || '—'}</strong></div><div><span>Contact Email</span><strong>{client.contact_person_email || '—'}</strong></div><div><span>Contact Phone</span><strong>{client.contact_person_phone || '—'}</strong></div><div><span>BD Person</span><strong>{client.bd_name || client.source_person_name || '—'}</strong></div><div><span>Audit</span><strong>Created by {client.created_by_name || 'System'} · Updated by {client.updated_by_name || 'System'}</strong></div></div>
  </section>
}

export function ClientProjectsPanel({ clientCode, projects, loading = false }: { clientCode: string; projects: RegisterClientProject[]; loading?: boolean }) {
  return <section className="operations-panel"><header><div><span className="operations-kicker">CLIENT PROJECTS</span><h2>Projects for {clientCode}</h2></div></header>
    {loading ? <div className="operations-empty">Loading projects...</div>
      : !projects.length ? <div className="nk-empty"><span className="nk-empty-icon"><FolderOpen size={22} /></span><h3>No projects for this client yet</h3><p>This client has no project history in the register. Projects created for {clientCode} will be listed here with their ID, scope, dates and status.</p></div>
      : <div className="operations-table-wrap"><table className="operations-table"><thead><tr><th>Project ID</th><th>Name / Scope</th><th>Dates</th><th>Status</th></tr></thead><tbody>{projects.map(row => <tr key={row.id}><td><strong>{row.project_code}</strong></td><td>{row.project_name}<small>{row.scope_text}</small></td><td>{row.start_date || '—'} → {row.end_date || '—'}</td><td><span className="operations-status">{label(row.status)}</span></td></tr>)}</tbody></table></div>}
  </section>
}
