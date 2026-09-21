const SERVER_TIME_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/

export function parseServerDateTime(value: string | null | undefined): Date | null {
  if (!value) return null
  const normalized = SERVER_TIME_RE.test(value) && !/[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? `${value}Z` : value
  const parsed = new Date(normalized)
  return Number.isFinite(parsed.getTime()) ? parsed : null
}

export function formatStandardDateTime(value: string | null | undefined): string {
  const date = parseServerDateTime(value)
  if (!date) return '—'

  const parts = new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  }).formatToParts(date)
  const byType = Object.fromEntries(parts.map(part => [part.type, part.value]))
  return `${byType.month} ${byType.day}, ${byType.year} · ${byType.hour}:${byType.minute}:${byType.second} ${byType.dayPeriod}`
}

/**
 * Short, scannable timestamp for notification lists: "Today, 12:05 PM",
 * "Yesterday, 3:12 PM" or "19 Sep, 12:05 PM". Seconds are deliberately omitted.
 */
export function formatNotificationTimestamp(value: string | null | undefined, nowMs = Date.now()): string {
  const date = parseServerDateTime(value)
  if (!date) return '—'

  const time = new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit', hour12: true }).format(date)
  const startOfDay = (input: Date) => new Date(input.getFullYear(), input.getMonth(), input.getDate()).getTime()
  const dayDelta = Math.round((startOfDay(new Date(nowMs)) - startOfDay(date)) / 86_400_000)
  if (dayDelta === 0) return `Today, ${time}`
  if (dayDelta === 1) return `Yesterday, ${time}`

  const day = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' }).format(date)
  if (date.getFullYear() === new Date(nowMs).getFullYear()) return `${day}, ${time}`
  return `${day} ${date.getFullYear()}, ${time}`
}

export function formatDuration(startValue: string | null | undefined, endValue?: string | null, nowMs = Date.now()): string {
  const start = parseServerDateTime(startValue)
  const end = endValue ? parseServerDateTime(endValue) : null
  if (!start) return '—'
  const elapsedMs = Math.max(0, (end?.getTime() ?? nowMs) - start.getTime())
  const totalMinutes = Math.floor(elapsedMs / 60_000)
  if (totalMinutes < 1) return '<1m'
  if (totalMinutes < 60) return `${totalMinutes}m`
  const totalHours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  if (totalHours < 24) return `${totalHours}h ${minutes}m`
  const days = Math.floor(totalHours / 24)
  const hours = totalHours % 24
  return `${days}d ${hours}h`
}
