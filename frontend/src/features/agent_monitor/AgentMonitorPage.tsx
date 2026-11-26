import {
  Activity,
  Clock3,
  Download,
  History,
  Laptop,
  MonitorCheck,
  RefreshCw,
  Search,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../components/DashboardHeader'
import { apiFetch, downloadFile } from '../../lib/api'
import { AgentMonitorDetailPanel } from './AgentMonitorDetailPanel'
import type {
  AgentListItem,
  AgentListPage,
  AgentStatusResponse,
  PaginatedResponse,
  UserSwitchRecord,
} from './agent-monitor-types'
import './agent-monitor.css'

function bytesToRam(bytes?: number | null): string {
  if (!bytes) return '—'
  return `${Math.round(bytes / 1024 / 1024 / 1024)} GB`
}

function relativeTime(value?: string | null): string {
  if (!value) return 'Never'
  const ms = Date.now() - new Date(value).getTime()
  if (!Number.isFinite(ms)) return '—'
  const seconds = Math.max(0, Math.floor(ms / 1000))
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

function displayUser(agent: AgentListItem): string {
  return agent.current_display_name || agent.current_nt_id || agent.current_username || 'No active user'
}

function identitySearchValues(agent: AgentListItem): Array<string | null | undefined> {
  return [
    agent.workstation_number,
    agent.cpu_asset_tag,
    agent.cpu_asset_number,
    agent.hostname,
    agent.current_nt_id,
    agent.current_username,
    agent.primary_local_ip,
    agent.cabin_name,
  ]
}

function GlobalUserSwitchHistory({ onClose, onOpenAgent }: { onClose: () => void; onOpenAgent: (agentId: string) => void }) {
  const [query, setQuery] = useState('')
  const [rows, setRows] = useState<UserSwitchRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({ page_size: '100' })
      if (query.trim()) params.set('search', query.trim())
      const response = await apiFetch<PaginatedResponse<UserSwitchRecord>>(`/software-team/agents/user-switch-history?${params.toString()}`)
      setRows(response.items || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load user switch history')
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [query])

  useEffect(() => { void load() }, [load])

  return (
    <div className="agent-detail-backdrop" onClick={onClose}>
      <aside className="agent-detail-drawer agent-switch-history-drawer" onClick={event => event.stopPropagation()}>
        <div className="agent-detail-header">
          <div><span>SOFTWARE TEAM · SHARED WORKSTATIONS</span><h2>User Switch History</h2><p>Retained NT-ID changes across monitored workstations.</p></div>
          <button type="button" onClick={onClose} aria-label="Close user switch history"><X size={18} /></button>
        </div>
        <div className="agent-switch-history-toolbar">
          <label><Search size={16} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Workstation, CPU tag, hostname or user" /></label>
          <button type="button" className="secondary-button" onClick={() => void load()} disabled={loading}><RefreshCw size={16} className={loading ? 'spin' : ''} /> Refresh</button>
        </div>
        {error && <div className="agent-feature-warning"><strong>Feature unavailable.</strong><span>{error}</span></div>}
        <div className="agent-detail-table-wrap agent-switch-history-table-wrap">
          <table className="agent-detail-table">
            <thead><tr><th>Changed</th><th>Workstation</th><th>CPU Asset Tag</th><th>Previous User</th><th>Current User</th><th>Source</th><th>Endpoint</th></tr></thead>
            <tbody>
              {!loading && rows.map(row => (
                <tr key={row.id}>
                  <td>{row.changed_at ? new Date(row.changed_at).toLocaleString() : '—'}</td>
                  <td><strong>{row.workstation_number || '—'}</strong><small>{row.hostname || '—'}</small></td>
                  <td>{row.cpu_asset_tag || '—'}</td>
                  <td>{row.previous_nt_id || row.previous_username || '—'}</td>
                  <td>{row.current_nt_id || row.current_username || '—'}</td>
                  <td>{row.source || '—'}</td>
                  <td>{row.agent_id ? <button type="button" className="agent-inline-button" onClick={() => onOpenAgent(row.agent_id || '')}>Open</button> : '—'}</td>
                </tr>
              ))}
              {!loading && rows.length === 0 && <tr><td colSpan={7} className="agent-empty">No user switch records found.</td></tr>}
              {loading && <tr><td colSpan={7} className="agent-empty">Loading user switch history…</td></tr>}
            </tbody>
          </table>
        </div>
      </aside>
    </div>
  )
}

export function AgentMonitorPage() {
  const [status, setStatus] = useState<AgentStatusResponse | null>(null)
  const [agents, setAgents] = useState<AgentListItem[]>([])
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [showSwitchHistory, setShowSwitchHistory] = useState(false)

  const load = useCallback(async (quiet = false) => {
    quiet ? setRefreshing(true) : setLoading(true)
    setError('')
    try {
      const statusResponse = await apiFetch<AgentStatusResponse>(
        '/software-team/agents/status'
      )

      const allAgents: AgentListItem[] = []
      let page = 1
      const pageSize = 100

      while (true) {
        const agentResponse = await apiFetch<AgentListPage>(
          `/software-team/agents?page=${page}&page_size=${pageSize}`
        )

        const items = agentResponse.items || []
        allAgents.push(...items)

        if (items.length < pageSize) {
          break
        }

        page += 1
      }

      setStatus(statusResponse)
      setAgents(allAgents)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load agent monitoring data')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => void load(true), 15000)
    return () => window.clearInterval(timer)
  }, [load])

  const filteredAgents = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return agents.filter(agent => {
      if (statusFilter && agent.status !== statusFilter) return false
      if (!needle) return true
      return identitySearchValues(agent).some(value => String(value || '').toLowerCase().includes(needle))
    })
  }, [agents, query, statusFilter])

  const stats = status?.stats || {}

  return (
    <>
      <DashboardHeader
        variant="ops"
        icon={MonitorCheck}
        eyebrow="SOFTWARE TEAM · ENDPOINT VISIBILITY"
        title="Agent Monitoring"
        description="Read-only workstation, user, software, activity and lifecycle visibility through the approved NakshaTech system agent service."
        meta={<>
          <span className="nk-meta-chip"><MonitorCheck size={14} /> {stats.online ?? '—'} online · {stats.delayed ?? '—'} delayed · {stats.offline ?? '—'} offline</span>
          <span className="nk-meta-chip"><Activity size={14} /> Auto-refreshes every 15 seconds</span>
          <span className="nk-meta-chip"><Laptop size={14} /> {stats.total_agents ?? agents.length} enrolled endpoints</span>
        </>}
      />

      {error && <div className="agent-monitor-error"><strong>Agent monitor unavailable.</strong><span>{error}</span></div>}

      <section className="agent-monitor-stats">
        <button type="button" className={!statusFilter ? 'active' : ''} onClick={() => setStatusFilter('')}><Laptop /><span>Total Agents</span><strong>{stats.total_agents ?? agents.length}</strong></button>
        <button type="button" className={statusFilter === 'online' ? 'active' : ''} onClick={() => setStatusFilter('online')}><MonitorCheck /><span>Online</span><strong>{stats.online ?? '—'}</strong></button>
        <button type="button" className={statusFilter === 'delayed' ? 'active' : ''} onClick={() => setStatusFilter('delayed')}><Clock3 /><span>Delayed</span><strong>{stats.delayed ?? '—'}</strong></button>
        <button type="button" className={statusFilter === 'offline' ? 'active' : ''} onClick={() => setStatusFilter('offline')}><Activity /><span>Offline</span><strong>{stats.offline ?? '—'}</strong></button>
      </section>

      <section className="panel agent-monitor-panel">
        <div className="agent-monitor-toolbar">
          <div>
            <h3>Employee Systems</h3>
            <p>{loading ? 'Loading systems…' : `${filteredAgents.length} of ${agents.length} agents shown`} · refreshes every 15 seconds</p>
          </div>
          <div className="agent-monitor-actions">
            <label><Search size={17} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Workstation, CPU tag, hostname, user or IP" /></label>
            <button type="button" className="secondary-button" onClick={() => void downloadFile('/software-team/agents/export.xlsx', 'NakshaTech Agent Inventory.xlsx').catch(err => setError(err instanceof Error ? err.message : 'Unable to download agent inventory'))}><Download size={16} /> Download Agent Excel</button>
            <button type="button" className="secondary-button" onClick={() => setShowSwitchHistory(true)}><History size={16} /> User Switch History</button>
            <button type="button" className="secondary-button" onClick={() => void load(true)} disabled={refreshing}><RefreshCw size={16} className={refreshing ? 'spin' : ''} /> Refresh</button>
          </div>
        </div>

        <div className="table-wrap">
          <table className="agent-monitor-table">
            <thead><tr><th>Status</th><th>Workstation / CPU Asset</th><th>Current User</th><th>System</th><th>Network</th><th>Current Activity</th><th>Last Seen</th></tr></thead>
            <tbody>
              {!loading && filteredAgents.map(agent => (
                <tr key={agent.agent_id} onClick={() => setSelectedId(agent.agent_id)}>
                  <td><span className={`agent-status status-${agent.status}`}>{agent.status}</span></td>
                  <td>
                    <strong>{agent.workstation_number || 'Workstation not reported'}</strong>
                    <small>CPU Asset Tag: {agent.cpu_asset_tag || '—'} · {agent.hostname || 'Unknown hostname'}</small>
                    {agent.cpu_asset_number && agent.cpu_asset_number !== agent.workstation_number && agent.cpu_asset_number !== agent.cpu_asset_tag && <small>Legacy asset alias: {agent.cpu_asset_number}</small>}
                  </td>
                  <td><strong>{displayUser(agent)}</strong><small>{agent.department || 'Department not reported'}</small></td>
                  <td><span>{agent.operating_system || '—'}</span><small>{bytesToRam(agent.total_ram_bytes)} RAM</small></td>
                  <td><strong>{agent.primary_local_ip || '—'}</strong><small>{agent.listening_port_count !== null && agent.listening_port_count !== undefined ? `${agent.listening_port_count} listening ports` : ''}</small></td>
                  <td><strong>{agent.current_application || '—'}</strong><small>{agent.activity_state || 'No activity state'}</small></td>
                  <td><strong>{relativeTime(agent.last_seen_at)}</strong><small>{agent.last_seen_at ? new Date(agent.last_seen_at).toLocaleString() : 'Never connected'}</small></td>
                </tr>
              ))}
              {!loading && filteredAgents.length === 0 && <tr><td colSpan={7} className="agent-empty">No agents match the current filter.</td></tr>}
              {loading && <tr><td colSpan={7} className="agent-empty">Loading live agent data…</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      {selectedId && <AgentMonitorDetailPanel agentId={selectedId} onClose={() => setSelectedId(null)} />}
      {showSwitchHistory && <GlobalUserSwitchHistory onClose={() => setShowSwitchHistory(false)} onOpenAgent={agentId => { setShowSwitchHistory(false); setSelectedId(agentId) }} />}
    </>
  )
}
