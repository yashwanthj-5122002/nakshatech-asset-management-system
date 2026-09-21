import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth } from '../../../context/AuthContext'
import {
  DEFAULT_PAGE_SIZE, DEFAULT_SORT, DEFAULT_VIEW, isClientViewMode, isPageSize, paginate, searchClients, sortClients,
  type ClientSortKey, type ClientViewMode, type PageSize, type SearchableClient,
} from './client-register-utils'

const SEARCH_DEBOUNCE_MS = 300

/**
 * Per-user display preference, kept only in this browser. The search text and
 * page number are deliberately not persisted.
 */
function preferenceKey(name: 'view' | 'pageSize', userKey: string) {
  return `naksha.clientRegister.${name}.${userKey}`
}

function readPreference(name: 'view' | 'pageSize', userKey: string): string | null {
  try { return window.localStorage.getItem(preferenceKey(name, userKey)) } catch { return null }
}

function writePreference(name: 'view' | 'pageSize', userKey: string, value: string) {
  try { window.localStorage.setItem(preferenceKey(name, userKey), value) } catch { /* private mode / blocked storage: preference just isn't remembered */ }
}

export type ClientRegisterState<T extends SearchableClient> = {
  searchInput: string
  /** The applied (debounced, trimmed) search text. */
  query: string
  setSearchInput: (value: string) => void
  clearSearch: () => void
  sort: ClientSortKey
  setSort: (value: ClientSortKey) => void
  view: ClientViewMode
  setView: (value: ClientViewMode) => void
  pageSize: PageSize
  setPageSize: (value: PageSize) => void
  page: number
  setPage: (value: number) => void
  pageCount: number
  /** Clients in the source list, before any search. */
  totalCount: number
  /** Clients matching the search. */
  filteredCount: number
  rangeStart: number
  rangeEnd: number
  /** Only the rows for the current page; Cards and Excel both render exactly these. */
  pageRows: T[]
}

/**
 * One client list in, one search → sort → paginate pipeline out. Cards and Excel
 * views render the same `pageRows`, so switching view never changes the result.
 */
export function useClientRegister<T extends SearchableClient>(clients: T[]): ClientRegisterState<T> {
  const { user } = useAuth()
  const userKey = user?.id != null ? String(user.id) : 'anonymous'

  const [searchInput, setSearchInput] = useState('')
  const [query, setQuery] = useState('')
  const [sort, setSortState] = useState<ClientSortKey>(DEFAULT_SORT)
  const [view, setViewState] = useState<ClientViewMode>(() => {
    const saved = readPreference('view', userKey)
    return isClientViewMode(saved) ? saved : DEFAULT_VIEW
  })
  const [pageSize, setPageSizeState] = useState<PageSize>(() => {
    const saved = Number(readPreference('pageSize', userKey))
    return isPageSize(saved) ? saved : DEFAULT_PAGE_SIZE
  })
  const [requestedPage, setRequestedPage] = useState(1)

  useEffect(() => {
    const handle = window.setTimeout(() => setQuery(searchInput.trim()), SEARCH_DEBOUNCE_MS)
    return () => window.clearTimeout(handle)
  }, [searchInput])

  useEffect(() => { setRequestedPage(1) }, [query])

  const setSort = useCallback((value: ClientSortKey) => { setSortState(value); setRequestedPage(1) }, [])
  const setView = useCallback((value: ClientViewMode) => { setViewState(value); writePreference('view', userKey, value) }, [userKey])
  const setPageSize = useCallback((value: PageSize) => { setPageSizeState(value); setRequestedPage(1); writePreference('pageSize', userKey, String(value)) }, [userKey])
  const clearSearch = useCallback(() => { setSearchInput(''); setQuery('') }, [])

  const filtered = useMemo(() => searchClients(clients, query), [clients, query])
  const sorted = useMemo(() => sortClients(filtered, sort), [filtered, sort])
  const slice = useMemo(() => paginate(sorted, requestedPage, pageSize), [sorted, requestedPage, pageSize])

  return {
    searchInput, query, setSearchInput, clearSearch,
    sort, setSort, view, setView, pageSize, setPageSize,
    page: slice.page, setPage: setRequestedPage, pageCount: slice.pageCount,
    totalCount: clients.length, filteredCount: slice.total,
    rangeStart: slice.rangeStart, rangeEnd: slice.rangeEnd, pageRows: slice.rows,
  }
}
