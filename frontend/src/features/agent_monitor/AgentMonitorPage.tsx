import {
  Activity,
  Clock3,
  Cpu,
  HardDrive,
  Laptop,
  MemoryStick,
  MonitorCheck,
  RefreshCw,
  Search,
  Wifi,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../components/DashboardHeader'
import { apiFetch } from '../../lib/api'
import './agent-monitor.css'

type AgentStatus = 'online' | 'delayed' | 'offline' | 'revoked' | string

interface AgentListItem {
  agent_id: string
  cpu_asset_number?: string | null
  cabin_name?: string | null
  department?: string | null
  hostname?: string | null
  operating_system?: string | null
  total_ram_bytes?: number | null
  primary_local_ip?: string | null
  status: AgentStatus
  last_seen_at?: string | null
  current_nt_id?: string | null
  current_username?: string | null
  current_display_name?: string | null
  current_application?: string | null
  window_title?: string | null
  activity_state?: string | null
}

interface AgentListPage {
  items: AgentListItem[]
  page: number
  page_size: number
  total: number
}

interface AgentStats {
  total_agents?: number
  online?: number
  delayed?: number
  offline?: number
  revoked?: number
  never_connected?: number
  server_time_utc?: string
}

interface AgentStatusResponse {
  enabled: boolean
  connected: boolean
  stats: AgentStats
}

type AgentDetail = AgentListItem & Record<string, unknown>

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

function detailValue(detail: AgentDetail | null, key: string): string {
  if (!detail) return '—'
  const value = detail[key]
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return String(value)
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
  const [detail, setDetail] = useState<AgentDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const load = useCallback(async (quiet = false) => {
    quiet ? setRefreshing(true) : setLoading(true)
    setError('')
    try {
      const [statusResponse, agentResponse] = await Promise.all([
        apiFetch<AgentStatusResponse>('/software-team/agents/status'),
        apiFetch<AgentListPage>('/software-team/agents?page_size=100'),
      ])
      setStatus(statusResponse)
      setAgents(agentResponse.items || [])
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

  useEffect(() => {
    if (!selectedId) {
      setDetail(null)
      return
    }
    setDetailLoading(true)
    void apiFetch<AgentDetail>(`/software-team/agents/${selectedId}`)
      .then(setDetail)
      .catch(err => setError(err instanceof Error ? err.message : 'Unable to load agent details'))
      .finally(() => setDetailLoading(false))
  }, [selectedId])

  const filteredAgents = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return agents.filter(agent => {
      if (statusFilter && agent.status !== statusFilter) return false
      if (!needle) return true
      return [agent.cpu_asset_number, agent.hostname, agent.current_nt_id, agent.current_username, agent.primary_local_ip, agent.cabin_name]
        .some(value => String(value || '').toLowerCase().includes(needle))
    })
  }, [agents, query, statusFilter])

  const stats = status?.stats || {}

  return (
    <>
      <DashboardHeader
        eyebrow="SOFTWARE TEAM · ENDPOINT VISIBILITY"
        title="Agent Monitoring"
        description="Live operational view of NakshaTech employee desktops reporting through the approved system agent service."
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
            <label><Search size={17} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Asset, hostname, user or IP" /></label>
            <button type="button" className="secondary-button" onClick={() => void load(true)} disabled={refreshing}><RefreshCw size={16} className={refreshing ? 'spin' : ''} /> Refresh</button>
          </div>
        </div>

        <div className="table-wrap">
          <table className="agent-monitor-table">
            <thead><tr><th>Status</th><th>Asset / Host</th><th>Current User</th><th>System</th><th>Network</th><th>Current Activity</th><th>Last Seen</th></tr></thead>
            <tbody>
              {!loading && filteredAgents.map(agent => (
                <tr key={agent.agent_id} onClick={() => setSelectedId(agent.agent_id)}>
                  <td><span className={`agent-status status-${agent.status}`}>{agent.status}</span></td>
                  <td><strong>{agent.cpu_asset_number || 'Unassigned'}</strong><small>{agent.hostname || 'Unknown hostname'}{agent.cabin_name ? ` · Cabin ${agent.cabin_name}` : ''}</small></td>
                  <td><strong>{displayUser(agent)}</strong><small>{agent.department || 'Department not reported'}</small></td>
                  <td><span>{agent.operating_system || '—'}</span><small>{bytesToRam(agent.total_ram_bytes)} RAM</small></td>
                  <td><strong>{agent.primary_local_ip || '—'}</strong></td>
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

      {selectedId && (
        <div className="agent-detail-backdrop" onClick={() => setSelectedId(null)}>
          <aside className="agent-detail-drawer" onClick={event => event.stopPropagation()}>
            <div className="agent-detail-header">
              <div><span>ENDPOINT DETAIL</span><h2>{detail?.cpu_asset_number || detail?.hostname || 'Agent'}</h2><p>{detail?.hostname || selectedId}</p></div>
              <button type="button" onClick={() => setSelectedId(null)} aria-label="Close agent details"><X /></button>
            </div>
            {detailLoading ? <div className="agent-detail-loading">Loading device details…</div> : (
              <div className="agent-detail-content">
                <section><h3><Cpu /> Device</h3><dl><div><dt>Hostname</dt><dd>{detailValue(detail, 'hostname')}</dd></div><div><dt>Asset number</dt><dd>{detailValue(detail, 'cpu_asset_number')}</dd></div><div><dt>Manufacturer</dt><dd>{detailValue(detail, 'manufacturer')}</dd></div><div><dt>Model</dt><dd>{detailValue(detail, 'model')}</dd></div><div><dt>BIOS serial</dt><dd>{detailValue(detail, 'bios_serial')}</dd></div><div><dt>Agent version</dt><dd>{detailValue(detail, 'agent_version')}</dd></div></dl></section>
                <section><h3><HardDrive /> Operating system</h3><dl><div><dt>OS</dt><dd>{detailValue(detail, 'operating_system')}</dd></div><div><dt>Build</dt><dd>{detailValue(detail, 'windows_build')}</dd></div><div><dt>Architecture</dt><dd>{detailValue(detail, 'architecture')}</dd></div><div><dt>Last inventory</dt><dd>{detailValue(detail, 'last_inventory_at')}</dd></div></dl></section>
                <section><h3><Wifi /> Network & location</h3><dl><div><dt>Local IP</dt><dd>{detailValue(detail, 'last_local_ip')}</dd></div><div><dt>Site</dt><dd>{detailValue(detail, 'site_code')}</dd></div><div><dt>Department</dt><dd>{detailValue(detail, 'department')}</dd></div><div><dt>Cabin</dt><dd>{detailValue(detail, 'cabin_name')}</dd></div></dl></section>
                <section><h3><MemoryStick /> Current session</h3><dl><div><dt>User</dt><dd>{detailValue(detail, 'current_nt_id')}</dd></div><div><dt>Application</dt><dd>{detailValue(detail, 'current_application')}</dd></div><div><dt>Activity state</dt><dd>{detailValue(detail, 'activity_state')}</dd></div><div><dt>Last seen</dt><dd>{detailValue(detail, 'last_seen_at')}</dd></div></dl></section>
              </div>
            )}
          </aside>
        </div>
      )}
    </>
  )
}
