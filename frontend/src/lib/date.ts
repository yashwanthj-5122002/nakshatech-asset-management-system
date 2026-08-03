const HAS_TIMEZONE = /(?:Z|[+-]\d{2}:?\d{2})$/i

export function parseServerUtc(value: string | Date): Date {
  if (value instanceof Date) return value
  const normalized = HAS_TIMEZONE.test(value) ? value : `${value}Z`
  return new Date(normalized)
}

export function formatIndiaDateTime(value?: string): string {
  if (!value) return 'No recorded change'
  const parsed = parseServerUtc(value)
  if (Number.isNaN(parsed.getTime())) return 'Invalid timestamp'
  return parsed.toLocaleString('en-IN', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export function isCurrentIndiaMonth(value?: string): boolean {
  if (!value) return false
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit',
  })
  return formatter.format(parseServerUtc(value)) === formatter.format(new Date())
}
