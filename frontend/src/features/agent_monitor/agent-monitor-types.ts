export type AgentStatus = 'online' | 'delayed' | 'offline' | 'revoked' | string

export interface AgentListItem {
  agent_id: string
  workstation_number?: string | null
  cpu_asset_tag?: string | null
  cpu_asset_number?: string | null
  room_number?: string | null
  cabin_name?: string | null
  building_name?: string | null
  floor_number?: string | null
  department?: string | null
  hostname?: string | null
  operating_system?: string | null
  total_ram_bytes?: number | null
  primary_local_ip?: string | null
  last_public_ip?: string | null
  listening_port_count?: number | null
  status: AgentStatus
  last_seen_at?: string | null
  first_seen_at?: string | null
  current_nt_id?: string | null
  current_username?: string | null
  current_display_name?: string | null
  current_domain?: string | null
  current_application?: string | null
  current_process?: string | null
  window_title?: string | null
  activity_state?: string | null
  idle_seconds?: number | null
}

export interface AgentListPage {
  items: AgentListItem[]
  page: number
  page_size: number
  total: number
}

export interface AgentStats {
  total_agents?: number
  online?: number
  delayed?: number
  offline?: number
  revoked?: number
  never_connected?: number
  server_time_utc?: string
}

export interface AgentStatusResponse {
  enabled: boolean
  connected: boolean
  stats: AgentStats
}

export interface AgentDetail extends AgentListItem {
  device_id?: string | null
  organization_id?: string | null
  site_code?: string | null
  manufacturer?: string | null
  model?: string | null
  bios_serial?: string | null
  system_uuid?: string | null
  windows_build?: string | null
  architecture?: string | null
  agent_version?: string | null
  last_local_ip?: string | null
  current_console_user?: string | null
  logged_in_users?: Record<string, unknown>[] | null
  known_user_count?: number | null
  mouse_active?: boolean | null
  keyboard_active?: boolean | null
  last_activity_at?: string | null
  current_boot_id?: string | null
  current_boot_time?: string | null
  current_session_record_id?: string | null
  current_windows_session_id?: number | null
  current_session_type?: string | null
  current_session_login_time?: string | null
  session_state?: string | null
  current_connection_type?: string | null
  last_logout_time?: string | null
  last_shutdown_type?: string | null
  last_shutdown_reason?: string | null
  last_shutdown_at?: string | null
  last_inventory_at?: string | null
  created_at?: string | null
  updated_at?: string | null
  revoked?: boolean
  [key: string]: unknown
}

export interface InventoryResponse {
  agent_id: string
  inventory: Record<string, unknown> | null
}

export interface PaginatedResponse<T = Record<string, unknown>> {
  items: T[]
  page: number
  page_size: number
  total: number
  [key: string]: unknown
}

export interface KnownUser {
  nt_id: string
  username?: string | null
  domain?: string | null
  display_name?: string | null
  is_organization_user?: boolean
  first_seen_at?: string | null
  last_seen_at?: string | null
  session_count?: number
  current_state?: string | null
  current_windows_session_id?: number | null
  is_active?: boolean
}

export interface KnownUsersResponse {
  agent_id: string
  workstation_number?: string | null
  cpu_asset_tag?: string | null
  hostname?: string | null
  organization_windows_domain?: string
  total?: number
  total_observed_windows_users?: number
  total_organization_users?: number
  non_organization_users?: number
  items: KnownUser[]
}

export interface UserSwitchRecord {
  id: number
  agent_id?: string | null
  changed_at?: string | null
  workstation_number?: string | null
  cpu_asset_tag?: string | null
  cpu_asset_number?: string | null
  hostname?: string | null
  previous_nt_id?: string | null
  current_nt_id?: string | null
  previous_username?: string | null
  current_username?: string | null
  previous_session_id?: number | null
  current_session_id?: number | null
  source?: string | null
}

export interface ActivitySummaryItem {
  application_name: string
  occurrences: number
  total_active: number
  total_left: number
  total_right: number
  total_middle: number
  total_all: number
  last_used?: string | null
}

export interface ActivitySummaryResponse {
  agent_id: string
  event_type: 'APPLICATION_ACTIVITY' | 'MOUSE_CLICK'
  total_records: number
  items: ActivitySummaryItem[]
}

export interface UserUsageResponse {
  agent_id: string
  workstation: Record<string, unknown>
  user: {
    nt_id: string
    username?: string | null
    domain?: string | null
    display_name?: string | null
    first_seen_at?: string | null
    last_seen_at?: string | null
    observed_session_count?: number
    is_current?: boolean
    current_windows_session_id?: number | null
  }
  range?: { start?: string | null; end?: string | null }
  summary?: Record<string, number>
  sessions?: Record<string, unknown>[]
  switches?: Record<string, unknown>[]
  heartbeats?: Record<string, unknown>[]
  events?: Record<string, unknown>[]
  software_usage?: Record<string, unknown>[]
  application_timeline?: Record<string, unknown>[]
  mouse_activity?: {
    samples?: number
    left_clicks?: number
    right_clicks?: number
    middle_clicks?: number
    total_clicks?: number
    items?: Record<string, unknown>[]
  }
  inactivity_reports?: Record<string, unknown>[]
  user_context_snapshots?: Record<string, unknown>[]
  browser_activity?: Record<string, unknown>[]
  running_processes?: Record<string, unknown>[]
  boot_history?: Record<string, unknown>[]
  ports?: Record<string, unknown>
  workstation_inventory?: Record<string, unknown> | null
  workstation_inventory_context?: Record<string, unknown>
  attribution?: Record<string, unknown>
}
