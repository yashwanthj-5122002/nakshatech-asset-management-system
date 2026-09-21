/**
 * Pure search / sort / pagination helpers for the Client Register.
 * Frontend display logic only: they read the client list the existing client API
 * already returns and never modify or re-order the source array.
 */

export type ClientViewMode = 'cards' | 'excel'
export type ClientSortKey = 'newest' | 'oldest' | 'name_asc' | 'name_desc' | 'code_asc' | 'code_desc'

export const CLIENT_SORT_OPTIONS: { value: ClientSortKey; label: string }[] = [
  { value: 'newest', label: 'Newest First' },
  { value: 'oldest', label: 'Oldest First' },
  { value: 'name_asc', label: 'Client Name A–Z' },
  { value: 'name_desc', label: 'Client Name Z–A' },
  { value: 'code_asc', label: 'Client ID A–Z' },
  { value: 'code_desc', label: 'Client ID Z–A' },
]

export const PAGE_SIZE_OPTIONS = [25, 50, 100] as const
export type PageSize = typeof PAGE_SIZE_OPTIONS[number]
export const DEFAULT_PAGE_SIZE: PageSize = 25
export const DEFAULT_SORT: ClientSortKey = 'newest'
export const DEFAULT_VIEW: ClientViewMode = 'cards'

/** Only fields the existing client API already returns; anything absent is simply not searched. */
export type SearchableClient = {
  id: number
  client_code: string
  client_name: string
  created_at?: string | null
  country?: string | null
  location?: string | null
  address?: string | null
  contact_person_name?: string | null
  contact_person_email?: string | null
  contact_person_phone?: string | null
  primary_phone?: string | null
  client_email?: string | null
  organization_email?: string | null
}

export function isClientViewMode(value: unknown): value is ClientViewMode {
  return value === 'cards' || value === 'excel'
}

export function isPageSize(value: unknown): value is PageSize {
  return typeof value === 'number' && (PAGE_SIZE_OPTIONS as readonly number[]).includes(value)
}

export function isClientSortKey(value: unknown): value is ClientSortKey {
  return CLIENT_SORT_OPTIONS.some(option => option.value === value)
}

function searchText(row: SearchableClient): string {
  const digits = [row.contact_person_phone, row.primary_phone].map(value => (value || '').replace(/\D/g, ''))
  return [
    row.client_code, row.client_name, row.country, row.location, row.address,
    row.contact_person_name, row.contact_person_email, row.contact_person_phone, row.primary_phone,
    row.client_email, row.organization_email, ...digits,
  ].filter(Boolean).join('\n').toLowerCase()
}

/** Case-insensitive partial match; every whitespace-separated term must appear somewhere in the searched fields. */
export function searchClients<T extends SearchableClient>(rows: T[], query: string): T[] {
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean)
  if (!terms.length) return rows
  return rows.filter(row => {
    const text = searchText(row)
    return terms.every(term => text.includes(term))
  })
}

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })

function createdAtMs(row: SearchableClient): number {
  const parsed = row.created_at ? Date.parse(row.created_at) : Number.NaN
  return Number.isNaN(parsed) ? 0 : parsed
}

/** Returns a sorted copy. Ties always fall back to the record id so the order is deterministic. */
export function sortClients<T extends SearchableClient>(rows: T[], sort: ClientSortKey): T[] {
  const byCode = (a: T, b: T) => collator.compare(a.client_code || '', b.client_code || '') || a.id - b.id
  const byName = (a: T, b: T) => collator.compare(a.client_name || '', b.client_name || '') || byCode(a, b)
  const comparators: Record<ClientSortKey, (a: T, b: T) => number> = {
    newest: (a, b) => createdAtMs(b) - createdAtMs(a) || b.id - a.id,
    oldest: (a, b) => createdAtMs(a) - createdAtMs(b) || a.id - b.id,
    name_asc: byName,
    name_desc: (a, b) => byName(b, a),
    code_asc: byCode,
    code_desc: (a, b) => byCode(b, a),
  }
  return [...rows].sort(comparators[sort])
}

export type PageSlice<T> = {
  rows: T[]
  page: number
  pageCount: number
  total: number
  /** 1-based, inclusive; both 0 when there are no rows. */
  rangeStart: number
  rangeEnd: number
}

export function paginate<T>(rows: T[], page: number, pageSize: number): PageSlice<T> {
  const total = rows.length
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const current = Math.min(Math.max(1, Math.floor(page) || 1), pageCount)
  const start = (current - 1) * pageSize
  const slice = rows.slice(start, start + pageSize)
  return { rows: slice, page: current, pageCount, total, rangeStart: total ? start + 1 : 0, rangeEnd: total ? start + slice.length : 0 }
}

export type PageItem = number | 'gap'

/** e.g. 1 2 3 4 5 … 41 — always the first and last page, a window around the current one, and a gap marker where pages are skipped. */
export function buildPageList(current: number, pageCount: number): PageItem[] {
  if (pageCount <= 7) return Array.from({ length: pageCount }, (_, index) => index + 1)
  if (current <= 4) return [1, 2, 3, 4, 5, 'gap', pageCount]
  if (current >= pageCount - 3) return [1, 'gap', pageCount - 4, pageCount - 3, pageCount - 2, pageCount - 1, pageCount]
  return [1, 'gap', current - 1, current, current + 1, 'gap', pageCount]
}
