export function withITMonth(path: string, month: string): string {
  const [pathname, rawQuery = ''] = path.split('?')
  const params = new URLSearchParams(rawQuery)
  params.set('month', month)
  const query = params.toString()
  return query ? `${pathname}?${query}` : pathname
}

export function monthLabel(month: string): string {
  const [year, monthNumber] = month.split('-').map(Number)
  if (!year || !monthNumber) return month
  return new Intl.DateTimeFormat('en-IN', { month: 'long', year: 'numeric' }).format(new Date(year, monthNumber - 1, 1))
}
