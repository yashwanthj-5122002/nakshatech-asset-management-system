import {
  Activity,
  AppWindow,
  Clock3,
  Cpu,
  Globe2,
  HardDrive,
  History,
  MousePointer2,
  Network,
  RefreshCw,
  Server,
  Users,
  Wifi,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { apiFetch } from '../../lib/api'
import type {
  ActivitySummaryResponse,
  AgentDetail,
  InventoryResponse,
  KnownUser,
  KnownUsersResponse,
  PaginatedResponse,
  UserSwitchRecord,
  UserUsageResponse,
} from './agent-monitor-types'

type DetailTab = 'overview' | 'hardware' | 'network' | 'users' | 'switches' | 'software' | 'activity' | 'browser' | 'ports' | 'history'
type ResourceKey = 'inventory' | 'users' | 'sessions' | 'switches' | 'app-summary' | 'mouse-summary' | 'inactivity' | 'ports' | 'boot' | 'heartbeats' | 'events' | 'inventory-history'

interface Props { agentId: string; onClose: () => void }

const TABS: Array<{ id: DetailTab; label: string; icon: ReactNode }> = [
  { id: 'overview', label: 'Overview', icon: <Server size={15} /> },
  { id: 'hardware', label: 'Hardware', icon: <Cpu size={15} /> },
  { id: 'network', label: 'Network', icon: <Network size={15} /> },
  { id: 'users', label: 'Users', icon: <Users size={15} /> },
  { id: 'switches', label: 'User Switches', icon: <History size={15} /> },
  { id: 'software', label: 'Software', icon: <AppWindow size={15} /> },
  { id: 'activity', label: 'Activity', icon: <MousePointer2 size={15} /> },
  { id: 'browser', label: 'Browser', icon: <Globe2 size={15} /> },
  { id: 'ports', label: 'Ports', icon: <Wifi size={15} /> },
  { id: 'history', label: 'History', icon: <Clock3 size={15} /> },
]

const TAB_RESOURCES: Record<DetailTab, ResourceKey[]> = {
  overview: [], hardware: ['inventory'], network: ['inventory'], users: ['users', 'sessions'], switches: ['switches'],
  software: ['inventory', 'app-summary'], activity: ['app-summary', 'mouse-summary', 'inactivity'], browser: ['inventory'],
  ports: ['ports'], history: ['boot', 'heartbeats', 'events', 'inventory-history'],
}

function record(value: unknown): Record<string, unknown> { return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {} }
function array(value: unknown): Record<string, unknown>[] { return Array.isArray(value) ? value.filter(item => item && typeof item === 'object') as Record<string, unknown>[] : [] }
function text(value: unknown, fallback = '—'): string {
  if (value === null || value === undefined || value === '') return fallback
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
function date(value: unknown): string { if (!value) return '—'; const parsed = new Date(String(value)); return Number.isNaN(parsed.getTime()) ? text(value) : parsed.toLocaleString() }
function bytes(value: unknown): string {
  let size = Number(value); if (!Number.isFinite(size) || size <= 0) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']; let index = 0
  while (size >= 1024 && index < units.length - 1) { size /= 1024; index += 1 }
  return `${size >= 100 ? Math.round(size) : size.toFixed(1)} ${units[index]}`
}
function pick(source: Record<string, unknown>, ...keys: string[]): unknown { for (const key of keys) if (source[key] !== undefined && source[key] !== null && source[key] !== '') return source[key]; return null }

function Card({ title, icon, rows }: { title: string; icon: ReactNode; rows: Array<[string, unknown]> }) {
  return <section className="agent-detail-card"><h3>{icon}{title}</h3><dl>{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{text(value)}</dd></div>)}</dl></section>
}

function SimpleTable({ rows, columns, empty = 'No records available.' }: { rows: Record<string, unknown>[]; columns: Array<{ key: string; label: string; format?: 'date' | 'bytes' }>; empty?: string }) {
  if (!rows.length) return <div className="agent-feature-empty">{empty}</div>
  return <div className="agent-detail-table-wrap"><table className="agent-detail-table"><thead><tr>{columns.map(column => <th key={column.key}>{column.label}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={String(row.id ?? row.event_id ?? row.session_id ?? index)}>{columns.map(column => <td key={column.key}>{column.format === 'date' ? date(row[column.key]) : column.format === 'bytes' ? bytes(row[column.key]) : text(row[column.key])}</td>)}</tr>)}</tbody></table></div>
}

export function AgentMonitorDetailPanel({ agentId, onClose }: Props) {
  const [tab, setTab] = useState<DetailTab>('overview')
  const [detail, setDetail] = useState<AgentDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [resources, setResources] = useState<Record<string, unknown>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [usage, setUsage] = useState<UserUsageResponse | null>(null)
  const [usageLoading, setUsageLoading] = useState(false)

  const loadDetail = useCallback(async () => {
    setRefreshing(true)
    try { setDetail(await apiFetch<AgentDetail>(`/software-team/agents/${agentId}`)) }
    finally { setLoading(false); setRefreshing(false) }
  }, [agentId])

  useEffect(() => { setLoading(true); setResources({}); setErrors({}); setUsage(null); setTab('overview'); void loadDetail() }, [agentId, loadDetail])

  const resourcePath = useCallback((key: ResourceKey): string => {
    const base = `/software-team/agents/${agentId}`
    switch (key) {
      case 'inventory': return `${base}/inventory`
      case 'users': return `${base}/users`
      case 'sessions': return `${base}/sessions?page_size=100`
      case 'switches': return `${base}/user-switches?page_size=100`
      case 'app-summary': return `${base}/activity-summary?event_type=APPLICATION_ACTIVITY`
      case 'mouse-summary': return `${base}/activity-summary?event_type=MOUSE_CLICK`
      case 'inactivity': return `${base}/events?event_type=INACTIVITY_REPORT&page_size=100`
      case 'ports': return `${base}/ports`
      case 'boot': return `${base}/boot-sessions?page_size=100`
      case 'heartbeats': return `${base}/heartbeats?page_size=100`
      case 'events': return `${base}/events?page_size=100`
      case 'inventory-history': return `${base}/inventory/history?page_size=100`
    }
  }, [agentId])

  const loadResource = useCallback(async (key: ResourceKey, force = false) => {
    if (!force && (resources[key] !== undefined || errors[key])) return
    try {
      const value = await apiFetch<unknown>(resourcePath(key))
      setResources(current => ({ ...current, [key]: value }))
      setErrors(current => { const next = { ...current }; delete next[key]; return next })
    } catch (err) {
      setErrors(current => ({ ...current, [key]: err instanceof Error ? err.message : 'Feature unavailable' }))
    }
  }, [errors, resourcePath, resources])

  useEffect(() => { for (const key of TAB_RESOURCES[tab]) void loadResource(key) }, [loadResource, tab])

  const loadUserUsage = useCallback(async (user: KnownUser, switchId?: number) => {
    setUsageLoading(true); setUsage(null)
    try {
      const params = new URLSearchParams({ nt_id: user.nt_id })
      if (switchId) params.set('switch_id', String(switchId))
      setUsage(await apiFetch<UserUsageResponse>(`/software-team/agents/${agentId}/user-usage?${params.toString()}`))
    } catch (err) {
      setErrors(current => ({ ...current, usage: err instanceof Error ? err.message : 'User usage unavailable' }))
    } finally { setUsageLoading(false) }
  }, [agentId])

  const inventory = record((resources.inventory as InventoryResponse | undefined)?.inventory)
  const users = (resources.users as KnownUsersResponse | undefined)?.items || []
  const sessions = (resources.sessions as PaginatedResponse | undefined)?.items || []
  const switches = (resources.switches as PaginatedResponse<UserSwitchRecord> | undefined)?.items || []
  const appSummary = resources['app-summary'] as ActivitySummaryResponse | undefined
  const mouseSummary = resources['mouse-summary'] as ActivitySummaryResponse | undefined
  const ports = record(resources.ports)
  const overviewTitle = detail?.workstation_number || detail?.hostname || 'Agent endpoint'

  const hardwareRows = useMemo(() => {
    const cpu = record(pick(inventory, 'cpu', 'processor')); const memory = record(pick(inventory, 'memory', 'ram'))
    return [
      ['Manufacturer', pick(inventory, 'manufacturer', 'system_manufacturer')], ['Model', pick(inventory, 'model', 'system_model')],
      ['BIOS Serial', pick(inventory, 'bios_serial', 'serial_number')], ['CPU', pick(cpu, 'name', 'model', 'processor_name')],
      ['Cores / Threads', `${text(pick(cpu, 'cores', 'physical_cores'))} / ${text(pick(cpu, 'logical_processors', 'threads'))}`],
      ['Memory', bytes(pick(memory, 'total_bytes', 'total_ram_bytes') ?? detail?.total_ram_bytes)],
    ] as Array<[string, unknown]>
  }, [detail, inventory])

  return <div className="agent-detail-backdrop" onClick={onClose}>
    <aside className="agent-detail-drawer agent-detail-drawer--expanded" onClick={event => event.stopPropagation()}>
      <div className="agent-detail-header">
        <div><span>SOFTWARE TEAM · READ-ONLY ENDPOINT INTELLIGENCE</span><h2>{overviewTitle}</h2><p>CPU Asset Tag: {detail?.cpu_asset_tag || '—'} · {detail?.hostname || agentId}</p></div>
        <div className="agent-detail-header-actions"><button type="button" onClick={() => void loadDetail()} aria-label="Refresh endpoint"><RefreshCw size={18} className={refreshing ? 'spin' : ''} /></button><button type="button" onClick={onClose} aria-label="Close endpoint"><X size={18} /></button></div>
      </div>
      <nav className="agent-detail-tabs">{TABS.map(item => <button key={item.id} type="button" className={tab === item.id ? 'active' : ''} onClick={() => setTab(item.id)}>{item.icon}{item.label}</button>)}</nav>
      {loading ? <div className="agent-detail-loading">Loading endpoint details…</div> : <div className="agent-detail-content agent-detail-content--tabs">
        {TAB_RESOURCES[tab].map(key => errors[key] ? <div key={key} className="agent-feature-warning"><strong>{key} unavailable.</strong><span>{errors[key]}</span></div> : null)}

        {tab === 'overview' && <div className="agent-detail-grid">
          <Card title="Fixed Identity" icon={<Server size={18} />} rows={[["Workstation Number", detail?.workstation_number], ["CPU Asset Tag", detail?.cpu_asset_tag], ["Hostname", detail?.hostname], ["Agent Version", detail?.agent_version], ["Status", detail?.status], ["Last Seen", date(detail?.last_seen_at)]]} />
          <Card title="Current User" icon={<Users size={18} />} rows={[["NT ID", detail?.current_nt_id], ["Username", detail?.current_username], ["Display Name", detail?.current_display_name], ["Domain", detail?.current_domain], ["Session", detail?.current_windows_session_id], ["Session State", detail?.session_state]]} />
          <Card title="Current Activity" icon={<Activity size={18} />} rows={[["Application", detail?.current_application], ["Process", detail?.current_process], ["Window", detail?.window_title], ["Activity State", detail?.activity_state], ["Idle Seconds", detail?.idle_seconds], ["Last Activity", date(detail?.last_activity_at)]]} />
          <Card title="Location & Network" icon={<Network size={18} />} rows={[["Department", detail?.department], ["Building", detail?.building_name], ["Floor", detail?.floor_number], ["Cabin / Room", detail?.cabin_name || detail?.room_number], ["Local IP", detail?.primary_local_ip || detail?.last_local_ip], ["Public IP", detail?.last_public_ip]]} />
        </div>}

        {tab === 'hardware' && <div className="agent-detail-stack"><Card title="System Hardware" icon={<Cpu size={18} />} rows={hardwareRows} /><section className="agent-detail-block"><h3><HardDrive size={18} />Storage / GPU / Monitors</h3><SimpleTable rows={[...array(inventory.disks), ...array(inventory.storage), ...array(inventory.gpus), ...array(inventory.monitors)]} columns={[{ key: 'name', label: 'Name' }, { key: 'model', label: 'Model' }, { key: 'type', label: 'Type' }, { key: 'size_bytes', label: 'Size', format: 'bytes' }, { key: 'status', label: 'Status' }]} /></section></div>}

        {tab === 'network' && <div className="agent-detail-stack"><Card title="Network Summary" icon={<Network size={18} />} rows={[["Primary Local IP", detail?.primary_local_ip || detail?.last_local_ip], ["Public IP", detail?.last_public_ip], ["Connection Type", detail?.current_connection_type], ["Listening Ports", detail?.listening_port_count]]} /><section className="agent-detail-block"><h3><Wifi size={18} />Adapters</h3><SimpleTable rows={[...array(inventory.network_adapters), ...array(inventory.network)]} columns={[{ key: 'name', label: 'Adapter' }, { key: 'mac_address', label: 'MAC' }, { key: 'ipv4', label: 'IPv4' }, { key: 'ipv6', label: 'IPv6' }, { key: 'status', label: 'Status' }]} /></section></div>}

        {tab === 'users' && <div className="agent-detail-stack">
          <section className="agent-detail-block"><h3><Users size={18} />Observed Workstation Users</h3>{users.length ? <div className="agent-detail-table-wrap"><table className="agent-detail-table"><thead><tr><th>NT ID</th><th>User</th><th>First Seen</th><th>Last Seen</th><th>Sessions</th><th>Usage</th></tr></thead><tbody>{users.map(user => <tr key={user.nt_id}><td>{user.nt_id}</td><td>{user.display_name || user.username || '—'}</td><td>{date(user.first_seen_at)}</td><td>{date(user.last_seen_at)}</td><td>{user.session_count ?? '—'}</td><td><button type="button" className="agent-inline-button" onClick={() => void loadUserUsage(user)}>View Usage</button></td></tr>)}</tbody></table></div> : <div className="agent-feature-empty">No observed users reported.</div>}</section>
          <section className="agent-detail-block"><h3><Clock3 size={18} />Sessions</h3><SimpleTable rows={sessions} columns={[{ key: 'nt_id', label: 'NT ID' }, { key: 'username', label: 'Username' }, { key: 'session_type', label: 'Type' }, { key: 'login_time', label: 'Login', format: 'date' }, { key: 'logout_time', label: 'Logout', format: 'date' }, { key: 'state', label: 'State' }]} /></section>
          {(usageLoading || usage) && <UserUsage usage={usage} loading={usageLoading} onClose={() => setUsage(null)} />}
        </div>}

        {tab === 'switches' && <section className="agent-detail-block"><h3><History size={18} />User Switch History</h3>{switches.length ? <div className="agent-detail-table-wrap"><table className="agent-detail-table"><thead><tr><th>Changed</th><th>Previous User</th><th>Current User</th><th>Source</th><th>Usage</th></tr></thead><tbody>{switches.map(row => <tr key={row.id}><td>{date(row.changed_at)}</td><td>{row.previous_nt_id || row.previous_username || '—'}</td><td>{row.current_nt_id || row.current_username || '—'}</td><td>{row.source || '—'}</td><td>{row.current_nt_id ? <button type="button" className="agent-inline-button" onClick={() => { setTab('users'); void loadUserUsage({ nt_id: row.current_nt_id || '', display_name: row.current_username }, row.id) }}>View User</button> : '—'}</td></tr>)}</tbody></table></div> : <div className="agent-feature-empty">No user switches reported.</div>}</section>}

        {tab === 'software' && <div className="agent-detail-stack"><section className="agent-detail-block"><h3><AppWindow size={18} />Installed Software</h3><SimpleTable rows={[...array(inventory.installed_software), ...array(inventory.software)]} columns={[{ key: 'name', label: 'Application' }, { key: 'version', label: 'Version' }, { key: 'publisher', label: 'Publisher' }, { key: 'install_date', label: 'Installed' }]} /></section><section className="agent-detail-block"><h3><Activity size={18} />Software Usage</h3><SimpleTable rows={(appSummary?.items || []) as unknown as Record<string, unknown>[]} columns={[{ key: 'application_name', label: 'Application' }, { key: 'occurrences', label: 'Occurrences' }, { key: 'total_active', label: 'Active Samples' }, { key: 'last_used', label: 'Last Used', format: 'date' }]} /></section></div>}

        {tab === 'activity' && <div className="agent-detail-stack"><section className="agent-detail-block"><h3><Activity size={18} />Application Activity</h3><SimpleTable rows={(appSummary?.items || []) as unknown as Record<string, unknown>[]} columns={[{ key: 'application_name', label: 'Application' }, { key: 'occurrences', label: 'Occurrences' }, { key: 'total_active', label: 'Active' }, { key: 'last_used', label: 'Last Used', format: 'date' }]} /></section><section className="agent-detail-block"><h3><MousePointer2 size={18} />Mouse Activity</h3><SimpleTable rows={(mouseSummary?.items || []) as unknown as Record<string, unknown>[]} columns={[{ key: 'application_name', label: 'Application' }, { key: 'total_left', label: 'Left' }, { key: 'total_right', label: 'Right' }, { key: 'total_middle', label: 'Middle' }, { key: 'total_all', label: 'Total' }]} /></section><section className="agent-detail-block"><h3><Clock3 size={18} />Inactivity Reports</h3><SimpleTable rows={(resources.inactivity as PaginatedResponse | undefined)?.items || []} columns={[{ key: 'created_at', label: 'Time', format: 'date' }, { key: 'nt_id', label: 'NT ID' }, { key: 'event_type', label: 'Event' }, { key: 'severity', label: 'Severity' }, { key: 'message', label: 'Details' }]} /></section></div>}

        {tab === 'browser' && <section className="agent-detail-block"><h3><Globe2 size={18} />Browser Activity</h3><SimpleTable rows={[...array(inventory.browser_activity), ...array(inventory.browser_history)]} columns={[{ key: 'visited_at', label: 'Visited', format: 'date' }, { key: 'browser', label: 'Browser' }, { key: 'title', label: 'Title' }, { key: 'url', label: 'URL' }, { key: 'nt_id', label: 'NT ID' }]} empty="Browser activity is available when the v1.5 agent backend reports it for this workstation/user." /></section>}

        {tab === 'ports' && <section className="agent-detail-block"><h3><Wifi size={18} />Listening Ports</h3><SimpleTable rows={[...array(ports.items), ...array(ports.ports), ...array(ports.listening_ports)]} columns={[{ key: 'protocol', label: 'Protocol' }, { key: 'local_address', label: 'Address' }, { key: 'local_port', label: 'Port' }, { key: 'process_name', label: 'Process' }, { key: 'pid', label: 'PID' }]} /></section>}

        {tab === 'history' && <div className="agent-detail-stack"><section className="agent-detail-block"><h3><Server size={18} />Boot History</h3><SimpleTable rows={(resources.boot as PaginatedResponse | undefined)?.items || []} columns={[{ key: 'boot_time', label: 'Boot', format: 'date' }, { key: 'shutdown_at', label: 'Shutdown', format: 'date' }, { key: 'shutdown_type', label: 'Shutdown Type' }, { key: 'reason', label: 'Reason' }]} /></section><section className="agent-detail-block"><h3><Activity size={18} />Heartbeats</h3><SimpleTable rows={(resources.heartbeats as PaginatedResponse | undefined)?.items || []} columns={[{ key: 'received_at', label: 'Received', format: 'date' }, { key: 'nt_id', label: 'NT ID' }, { key: 'application_name', label: 'Application' }, { key: 'activity_state', label: 'Activity' }, { key: 'idle_seconds', label: 'Idle Seconds' }]} /></section><section className="agent-detail-block"><h3><History size={18} />Events</h3><SimpleTable rows={(resources.events as PaginatedResponse | undefined)?.items || []} columns={[{ key: 'created_at', label: 'Time', format: 'date' }, { key: 'event_type', label: 'Type' }, { key: 'severity', label: 'Severity' }, { key: 'nt_id', label: 'NT ID' }, { key: 'message', label: 'Message' }]} /></section><section className="agent-detail-block"><h3><HardDrive size={18} />Inventory History</h3><SimpleTable rows={(resources['inventory-history'] as PaginatedResponse | undefined)?.items || []} columns={[{ key: 'captured_at', label: 'Captured', format: 'date' }, { key: 'hostname', label: 'Hostname' }, { key: 'operating_system', label: 'OS' }, { key: 'agent_version', label: 'Agent Version' }]} /></section></div>}
      </div>}
    </aside>
  </div>
}

function UserUsage({ usage, loading, onClose }: { usage: UserUsageResponse | null; loading: boolean; onClose: () => void }) {
  if (loading) return <div className="agent-user-usage-panel"><div className="agent-detail-loading">Loading retained user usage…</div></div>
  if (!usage) return null
  const summary = usage.summary || {}
  return <section className="agent-user-usage-panel"><div className="agent-user-usage-heading"><div><span>PER-USER USAGE · READ ONLY</span><h3>{usage.user.display_name || usage.user.nt_id}</h3><p>{usage.user.nt_id} · workstation activity attributed by the v1.5 agent backend.</p></div><button type="button" onClick={onClose}><X size={16} /></button></div><div className="agent-detail-stack"><div className="agent-usage-kpis">{Object.entries(summary).slice(0, 8).map(([key, value]) => <div key={key}><span>{key.replaceAll('_', ' ')}</span><strong>{value}</strong></div>)}</div><section className="agent-detail-block"><h3><AppWindow size={18} />Software Usage</h3><SimpleTable rows={usage.software_usage || []} columns={[{ key: 'application_name', label: 'Application' }, { key: 'started_at', label: 'Started', format: 'date' }, { key: 'ended_at', label: 'Ended', format: 'date' }, { key: 'duration_seconds', label: 'Duration (s)' }]} /></section><section className="agent-detail-block"><h3><Globe2 size={18} />Browser Activity</h3><SimpleTable rows={usage.browser_activity || []} columns={[{ key: 'visited_at', label: 'Visited', format: 'date' }, { key: 'browser', label: 'Browser' }, { key: 'title', label: 'Title' }, { key: 'url', label: 'URL' }]} /></section><section className="agent-detail-block"><h3><MousePointer2 size={18} />Mouse / Inactivity</h3><SimpleTable rows={[...(usage.mouse_activity?.items || []), ...(usage.inactivity_reports || [])]} columns={[{ key: 'created_at', label: 'Time', format: 'date' }, { key: 'application_name', label: 'Application' }, { key: 'event_type', label: 'Event' }, { key: 'total_clicks', label: 'Clicks' }, { key: 'idle_seconds', label: 'Idle Seconds' }]} /></section><section className="agent-detail-block"><h3><Clock3 size={18} />Sessions</h3><SimpleTable rows={usage.sessions || []} columns={[{ key: 'login_time', label: 'Login', format: 'date' }, { key: 'logout_time', label: 'Logout', format: 'date' }, { key: 'session_type', label: 'Type' }, { key: 'state', label: 'State' }]} /></section></div></section>
}
