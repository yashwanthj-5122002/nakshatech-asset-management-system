import { RefreshCcw } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import type { FinanceClient, FinanceProject } from '../../../types'
import { BackToClientsButton, ClientDetailPanel, ClientProjectsPanel, ClientRegisterPanel, type RegisterClientProject } from '../../operations/components/ClientRegister'
import { useClientRegister } from '../../operations/components/useClientRegister'
import '../../operations/operations.css'

/**
 * Finance Client Register: view-only. It renders the same shared Client Register
 * presentation as BD Client Management with `readOnly`, so no New Client, Create
 * Project or Edit control exists. Client Master writes stay Admin-only and are
 * enforced server-side (POST/PUT /finance/clients*).
 */
export function FinanceClientRegisterPage() {
  const [clients, setClients] = useState<FinanceClient[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [projects, setProjects] = useState<RegisterClientProject[]>([])
  const [projectsLoading, setProjectsLoading] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  function load() {
    setLoading(true)
    setError('')
    void apiFetch<FinanceClient[]>('/finance/clients')
      .then(setClients)
      .catch(err => setError(err instanceof Error ? err.message : 'Unable to load the Client Register'))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  // Finance keeps its primary-phone fallback for clients with no contact-person phone.
  const registerClients = useMemo(() => clients.map(row => ({ ...row, contact_person_phone: row.contact_person_phone || row.primary_phone })), [clients])
  const register = useClientRegister(registerClients)
  const selected = registerClients.find(row => row.id === selectedId) ?? null

  useEffect(() => {
    if (!selectedId) { setProjects([]); return }
    let cancelled = false
    setProjectsLoading(true)
    void apiFetch<FinanceProject[]>(`/finance/clients/${selectedId}/projects`)
      .then(rows => { if (!cancelled) setProjects(rows.map(row => ({ id: row.id, project_code: row.project_code, project_name: row.project_name, scope_text: row.task || row.description, start_date: row.start_date, end_date: row.end_date, status: row.lifecycle_status }))) })
      .catch(err => { if (!cancelled) { setProjects([]); setError(err instanceof Error ? err.message : 'Unable to load projects for this client') } })
      .finally(() => { if (!cancelled) setProjectsLoading(false) })
    return () => { cancelled = true }
  }, [selectedId])

  return <div className="operations-page">
    <DashboardHeader
      eyebrow="FINANCE · VIEW ONLY"
      title="Client Register"
      description="Find any client and review its details and project history. This register is view-only."
      actions={<button className="operations-button secondary" onClick={load}><RefreshCcw size={16} /> Refresh</button>}
    />
    {error && <div className="operations-alert error">{error}</div>}

    {!selected && <ClientRegisterPanel readOnly loading={loading} register={register} onView={setSelectedId} />}

    {selected && <>
      <BackToClientsButton onClick={() => setSelectedId(null)} />
      <ClientDetailPanel readOnly client={selected} />
      <ClientProjectsPanel clientCode={selected.client_code} projects={projects} loading={projectsLoading} />
    </>}
  </div>
}
