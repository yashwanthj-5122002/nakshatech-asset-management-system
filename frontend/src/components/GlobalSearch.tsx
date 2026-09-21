import { Building2, CornerDownLeft, FolderKanban, Search, X } from 'lucide-react'
import { type KeyboardEvent as ReactKeyboardEvent, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/api'

type ProjectRow = {
  id: number
  project_code: string
  project_name: string
  client_code?: string | null
  client_name?: string | null
  workflow_status: string
}
type ClientRow = {
  id: number
  client_code: string
  client_name: string
  location?: string | null
  country?: string | null
  contact_person_name?: string | null
}
type Dashboard = { clients: ClientRow[]; projects: ProjectRow[] }
type SearchHit = { kind: 'client' | 'project'; id: number; code: string; name: string; sub?: string | null; url: string }

const MAX_RESULTS = 8

/**
 * Ribbon-level global search. Loads the caller's client/project register once (lazily on first
 * focus) and filters it in memory, so a match opens the record directly instead of filtering a list.
 * Only mounted for roles that can read the BD register.
 */
export function GlobalSearch() {
  const navigate = useNavigate()
  const rootRef = useRef<HTMLDivElement | null>(null)
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [data, setData] = useState<Dashboard | null>(null)
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)

  function ensureData() {
    if (data || loading) return
    setLoading(true)
    setFailed(false)
    void apiFetch<Dashboard>('/operations/workflow/bd/dashboard')
      .then(setData)
      .catch(() => setFailed(true))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (!open) return
    const handlePointerDown = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false)
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  const hits = useMemo<SearchHit[]>(() => {
    const needle = query.trim().toLowerCase()
    if (!needle || !data) return []
    const out: SearchHit[] = []
    for (const client of data.clients ?? []) {
      const haystack = [client.client_code, client.client_name, client.location, client.country, client.contact_person_name].filter(Boolean).join(' ').toLowerCase()
      if (haystack.includes(needle)) {
        out.push({ kind: 'client', id: client.id, code: client.client_code, name: client.client_name, sub: client.location || client.country, url: `/bd/clients?client=${client.id}` })
      }
    }
    for (const project of data.projects ?? []) {
      const haystack = [project.project_code, project.project_name, project.client_code, project.client_name, project.workflow_status].filter(Boolean).join(' ').toLowerCase()
      if (haystack.includes(needle)) {
        out.push({ kind: 'project', id: project.id, code: project.project_code, name: project.project_name, sub: project.client_code ? `Client ${project.client_code}` : null, url: `/bd/projects?project=${project.id}` })
      }
    }
    return out.slice(0, MAX_RESULTS)
  }, [data, query])

  useEffect(() => { setActiveIndex(0) }, [query])

  function openHit(hit: SearchHit) {
    setOpen(false)
    setQuery('')
    navigate(hit.url)
  }

  function onKeyDown(event: ReactKeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveIndex(current => Math.min(current + 1, Math.max(hits.length - 1, 0)))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex(current => Math.max(current - 1, 0))
    } else if (event.key === 'Enter') {
      if (hits.length) { event.preventDefault(); openHit(hits[activeIndex] ?? hits[0]) }
    }
  }

  const showPanel = open && query.trim().length > 0

  return <div className="ribbon-search" ref={rootRef}>
    <div className="ribbon-search-field">
      <Search size={16} aria-hidden="true" />
      <input
        type="search"
        role="combobox"
        aria-expanded={showPanel}
        aria-controls="ribbon-search-results"
        aria-autocomplete="list"
        aria-label="Search clients and projects"
        placeholder="Search clients or projects…"
        value={query}
        onFocus={() => { setOpen(true); ensureData() }}
        onChange={event => { setQuery(event.target.value); setOpen(true); ensureData() }}
        onKeyDown={onKeyDown}
      />
      {query
        ? <button type="button" className="ribbon-search-clear" aria-label="Clear search" onClick={() => { setQuery(''); setActiveIndex(0) }}><X size={14} /></button>
        : <span className="ribbon-search-hint" aria-hidden="true">/</span>}
    </div>

    {showPanel && <div className="ribbon-search-panel" id="ribbon-search-results" role="listbox" aria-label="Search results">
      {loading && <div className="ribbon-search-state">Searching…</div>}
      {!loading && failed && <div className="ribbon-search-state error">Search is temporarily unavailable.</div>}
      {!loading && !failed && !hits.length && <div className="ribbon-search-state">No client or project matches “{query.trim()}”.</div>}
      {!loading && !failed && hits.map((hit, index) => (
        <button
          type="button"
          role="option"
          aria-selected={index === activeIndex}
          key={`${hit.kind}-${hit.id}`}
          className={`ribbon-search-hit ${index === activeIndex ? 'active' : ''}`}
          onMouseEnter={() => setActiveIndex(index)}
          onClick={() => openHit(hit)}
        >
          <span className={`ribbon-search-hit-icon ${hit.kind}`}>
            {hit.kind === 'client' ? <Building2 size={15} /> : <FolderKanban size={15} />}
          </span>
          <span className="ribbon-search-hit-copy">
            <span className="ribbon-search-hit-kind">{hit.kind === 'client' ? 'Client' : 'Project'}</span>
            <strong>{hit.code}</strong>
            <small>{hit.name}{hit.sub ? ` · ${hit.sub}` : ''}</small>
          </span>
          {index === activeIndex && <CornerDownLeft size={14} aria-hidden="true" className="ribbon-search-hit-enter" />}
        </button>
      ))}
    </div>}
  </div>
}
