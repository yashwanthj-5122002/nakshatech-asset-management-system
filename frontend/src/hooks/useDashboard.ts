import { useEffect, useState } from 'react'
import { apiFetch } from '../lib/api'
import type { DashboardSummary } from '../types'

export function useDashboard() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    apiFetch<DashboardSummary>('/dashboard/summary').then(setSummary).catch((err) => setError(err.message))
  }, [])

  return { summary, error }
}
