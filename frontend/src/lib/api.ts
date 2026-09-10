const API_BASE = import.meta.env.VITE_API_URL || '/api'

type ApiValidationIssue = {
  loc?: unknown
  msg?: unknown
  message?: unknown
  detail?: unknown
}

function fieldLabelFromLocation(location: unknown): string {
  if (!Array.isArray(location)) return ''
  const useful = location
    .filter(item => typeof item === 'string' || typeof item === 'number')
    .map(String)
    .filter(item => !['body', 'query', 'path', 'header', 'cookie'].includes(item.toLowerCase()))

  const field = useful.at(-1)
  if (!field || /^\d+$/.test(field)) return ''
  return field
    .replace(/_/g, ' ')
    .replace(/\b\w/g, letter => letter.toUpperCase())
}

function validationIssueMessage(issue: unknown): string | null {
  if (typeof issue === 'string' && issue.trim()) return issue.trim()
  if (!issue || typeof issue !== 'object') return null

  const item = issue as ApiValidationIssue
  const rawMessage =
    (typeof item.msg === 'string' && item.msg) ||
    (typeof item.message === 'string' && item.message) ||
    (typeof item.detail === 'string' && item.detail) ||
    ''

  if (!rawMessage) return null
  const field = fieldLabelFromLocation(item.loc)
  return field ? `${field}: ${rawMessage}` : rawMessage
}

export function apiErrorMessage(payload: unknown, fallback = 'Request failed'): string {
  if (typeof payload === 'string' && payload.trim()) return payload.trim()
  if (!payload || typeof payload !== 'object') return fallback

  const record = payload as Record<string, unknown>
  const detail = record.detail

  if (typeof detail === 'string' && detail.trim()) return detail.trim()

  if (Array.isArray(detail)) {
    const messages = detail
      .map(validationIssueMessage)
      .filter((message): message is string => Boolean(message))
    if (messages.length) return messages.join(' · ')
  }

  const detailMessage = validationIssueMessage(detail)
  if (detailMessage) return detailMessage

  for (const key of ['message', 'error', 'reason']) {
    const value = record[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
  }

  return fallback
}

export function getToken(): string | null {
  return localStorage.getItem('asset_token') ?? sessionStorage.getItem('asset_token')
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers = new Headers(options.headers)
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(`${API_BASE}${path}`, { cache: 'no-store', ...options, headers })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(apiErrorMessage(error))
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function apiBlob(path: string): Promise<Blob> {
  const token = getToken()
  const response = await fetch(`${API_BASE}${path}`, {
    cache: 'no-store',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(apiErrorMessage(error))
  }
  return response.blob()
}

export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const token = getToken()
  const response = await fetch(`${API_BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Download failed' }))
    throw new Error(apiErrorMessage(error, 'Download failed'))
  }
  const blob = await response.blob()
  const disposition = response.headers.get('content-disposition') || ''
  const match = disposition.match(/filename="?([^";]+)"?/)
  const fileName = match?.[1] || fallbackName
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export async function uploadExcel(path: string, file: File): Promise<Record<string, unknown>> {
  const token = getToken()
  const formData = new FormData()
  formData.append('file', file)
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(apiErrorMessage(data, 'Excel import failed'))
  return data
}
