export type Role = 'admin' | 'management' | 'it' | 'drone'

export interface AuthUser {
  id: number
  email: string
  full_name: string
  role: Role
  branch: string
}

export interface DashboardSummary {
  role: Role
  assets_total: number
  available_assets: number
  repair_assets: number
  drones_total: number
  deployed_drones: number
  pending_work: number
}

export interface DistributionItem {
  name: string
  value: number
}

export interface AlertItem {
  severity: 'critical' | 'high' | 'medium' | 'info'
  title: string
  count: number
  filter?: string
  details?: string[]
}

export interface Asset {
  id: number
  asset_code: string
  source_sheet?: string
  source_row?: number
  used_by?: string
  workstation_no?: string
  department?: string
  cpu_asset_tag?: string
  monitor_asset_tags?: string
  mouse_asset_tag?: string
  keyboard_asset_tag?: string
  system_name?: string
  device_type: string
  processor?: string
  memory_gb?: string
  ssd?: string
  hdd?: string
  ip_address?: string
  mac_address?: string
  graphics_card?: string
  operating_system?: string
  antivirus?: string
  network_type?: string
  performed_by?: string
  approved_by?: string
  price?: number
  remarks?: string
  asset_date?: string
  location?: string
  work_mode: string
  status: string
  created_at: string
  updated_at: string
  history?: Array<{
    action: string
    old_value?: string
    new_value?: string
    remarks?: string
    changed_by?: string
    created_at: string
  }>
  work_records?: WorkRecord[]
  replacement_records?: ReplacementRecord[]
  component_replacements?: ComponentReplacementRecord[]
  can_delete_test_record?: boolean
}

export interface WorkRecord {
  id: number
  work_code: string
  module: string
  asset_id?: number
  asset_code?: string
  title: string
  work_type: string
  project?: string
  assigned_to?: string
  technician?: string
  priority: string
  issue_description?: string
  details?: string
  status: string
  root_cause?: string
  resolution?: string
  replaced_component?: string
  replacement_asset_tag?: string
  cost?: number
  approval_status: string
  start_date?: string
  expected_completion_date?: string
  completed_at?: string
  created_at: string
  updated_at: string
}

export interface ComponentReplacementRecord {
  id: number
  replacement_code: string
  batch_code?: string
  sequence_no?: number
  asset_id: number
  asset_code: string
  cpu_asset_tag?: string
  workstation_no?: string
  component_type: string
  change_type: string
  field_name: string
  old_value?: string
  new_value: string
  reason: string
  old_condition?: string
  technician?: string
  replacement_date?: string
  performed_by?: string
  approved_by?: string
  remarks?: string
  work_record_id?: number
  work_code?: string
  created_at: string
}

export interface ReplacementRecord {
  id: number
  replacement_code: string
  old_asset_id: number
  old_asset_code: string
  new_asset_id?: number
  new_asset_code?: string
  reason: string
  damage_category: string
  inspection_finding?: string
  approval_status: string
  final_action: string
  requested_by?: string
  approved_by?: string
  created_at: string
  approved_at?: string
}

export interface ITDashboardData {
  month: {
    key: string
    label: string
    status: 'live' | 'finalized' | 'historical'
    source: string
    is_live: boolean
    read_only: boolean
  }
  monthly_activity: {
    new_assets: number
    work_records: number
    component_changes: number
    complete_replacements: number
  }
  kpis: {
    total: number
    computers: number
    laptops: number
    smartphones: number
    assigned: number
    available: number
    repair: number
    replacement_pending: number
    wfh: number
    field: number
    returned: number
    damaged: number
  }
  device_distribution: DistributionItem[]
  status_distribution: DistributionItem[]
  department_distribution: DistributionItem[]
  location_distribution: DistributionItem[]
  memory_distribution: DistributionItem[]
  os_distribution: DistributionItem[]
  alerts: AlertItem[]
  recent_work: WorkRecord[]
  recent_replacements: ReplacementRecord[]
}

export interface DroneLocation {
  id: number
  drone_id: number
  latitude: number
  longitude: number
  altitude?: number
  speed?: number
  heading?: number
  battery_percent?: number
  source: string
  recorded_at: string
}

export interface Drone {
  id: number
  asset_code: string
  name: string
  model: string
  pilot?: string
  project?: string
  status: string
  battery_percent?: number
  latest_location?: DroneLocation
}

export interface ComponentChangeBatchResponse {
  batch_code: string
  work_code: string
  asset_id: number
  asset_code: string
  cpu_asset_tag?: string
  workstation_no?: string
  change_type: string
  records: ComponentReplacementRecord[]
}

export interface ReportMonth {
  key: string
  label: string
  status: 'live' | 'finalized' | 'historical'
  source: string
  opening_count?: number
  closing_count?: number
  is_current?: boolean
}

export interface DroneSurveyAsset {
  id: number
  asset_tag: string
  imported_equipment_id?: string
  asset_name: string
  category: string
  subcategory?: string
  manufacturer?: string
  model_number?: string
  serial_number?: string
  raw_serial_number?: string
  quantity: number
  allocated_quantity?: number
  available_quantity?: number
  raw_quantity?: string
  unit_of_measure?: string
  tracking_type: string
  calibration_required?: string
  maintenance_required?: string
  technical_frequency?: string
  responsible_function?: string
  last_calibration_date?: string
  next_calibration_date?: string
  equipment_tolerance?: string
  current_status: string
  working_condition?: string
  current_custodian?: string
  associated_people: string[]
  current_project_id?: number
  current_project?: string
  current_location?: string
  parent_kit_id?: number
  parent_kit?: string
  is_serialized: boolean
  is_telemetry_capable: boolean
  source_workbook?: string
  source_sheet?: string
  source_row?: number
  source_section?: string
  original_raw_payload?: Record<string, unknown>
  original_header_map?: Record<string, string>
  reconciliation_status: string
  remarks?: string
  created_at: string
  updated_at: string
}

export interface DroneAssetListResponse {
  items: DroneSurveyAsset[]
  total: number
  offset: number
  limit: number
}

export interface DroneProject {
  id: number
  project_code: string
  project_name: string
  client?: string
  project_manager?: string
  start_date?: string
  expected_end_date?: string
  actual_completion_date?: string
  closure_date?: string
  status: string
  financial_year?: string
  location?: string
  project_area?: string
  description?: string
  remarks?: string
  created_at: string
}

export interface DroneKitComponent {
  id: number
  asset_id: number
  asset_tag: string
  component_name: string
  serial_number?: string
  quantity: number
  status: string
  is_essential: boolean
}

export interface DroneKit {
  id: number
  kit_tag: string
  kit_name: string
  model?: string
  unit_number?: string
  uin?: string
  current_status: string
  current_custodian?: string
  current_project_id?: number
  current_project?: string
  current_location?: string
  remarks?: string
  component_count: number
  available_components: number
  missing_components: number
  readiness_percentage: number
  components: DroneKitComponent[]
}

export interface DroneDashboardData {
  kpis: {
    total_assets: number
    total_quantity: number
    flight_capable_drones: number
    available_assets: number
    assets_with_employees: number
    assets_at_projects: number
    under_maintenance: number
    calibration_overdue: number
    flight_ready_kits: number
    incomplete_kits: number
    missing_assets: number
    pending_verification: number
    active_projects: number
    completed_projects: number
    hdd_deliveries: number
    in_transit?: number
    active_operations?: number
    overdue_returns?: number
  }
  category_distribution: DistributionItem[]
  status_distribution: DistributionItem[]
  project_distribution: DistributionItem[]
  recent_assets: DroneSurveyAsset[]
  import_quality: {
    missing_serial_numbers: number
    duplicate_imported_ids: number
    unresolved_import_exceptions: number
  }
  recent_movements?: DroneMovement[]
  active_operations?: DroneOperation[]
  telemetry: Array<{
    id: number
    asset_code: string
    name: string
    status: string
    freshness: 'Live' | 'Recent' | 'Stale' | 'No Data'
    latest_location?: {
      latitude: number
      longitude: number
      recorded_at: string
      source: string
    }
  }>
}

export interface DroneImportRecord {
  id: number
  source_sheet: string
  source_row: number
  source_section?: string
  record_type: string
  original_raw_payload: Record<string, unknown>
  normalized_payload: Record<string, unknown>
  issues: string[]
  classification: string
  reconciliation_status: string
  created_asset_id?: number
}

export interface DroneImportBatch {
  batch_id: number
  batch_code: string
  status: string
  source_workbook: string
  reporting_month?: string
  summary: Record<string, unknown>
  records: DroneImportRecord[]
  exceptions: Array<{
    id: number
    row_id?: number
    severity: string
    exception_type: string
    message: string
    resolved: boolean
    resolution?: string
  }>
  created_by?: string
  approved_by?: string
  created_at: string
  committed_at?: string
}

export interface DroneOperationItem {
  id: number
  parent_item_id?: number
  source_operation_item_id?: number
  asset_id?: number
  asset_tag?: string
  asset_name?: string
  asset_category?: string
  serial_number?: string
  kit_id?: number
  kit_tag?: string
  kit_name?: string
  quantity: number
  returned_quantity: number
  open_quantity: number
  item_status: string
  condition?: string
  next_status?: string
  remarks?: string
  is_kit_component: boolean
}

export interface DroneOperation {
  id: number
  operation_code: string
  operation_type: 'dispatch' | 'assignment' | 'return' | 'transfer' | string
  status: string
  project_id?: number
  project?: string
  from_project_id?: number
  from_project?: string
  to_project_id?: number
  to_project?: string
  parent_operation_id?: number
  from_custodian?: string
  to_custodian?: string
  source_location?: string
  destination?: string
  operation_date: string
  expected_return_date?: string
  purpose?: string
  condition?: string
  approved_by?: string
  override_reason?: string
  remarks?: string
  performed_by?: string
  created_at: string
  completed_at?: string
  items: DroneOperationItem[]
  open_item_count: number
  overdue: boolean
}

export interface DroneMovement {
  id: number
  movement_code: string
  operation_id?: number
  asset_id?: number
  asset_tag?: string
  asset_name?: string
  kit_id?: number
  kit_tag?: string
  kit_name?: string
  movement_type: string
  quantity: number
  old_status?: string
  new_status?: string
  old_project_id?: number
  old_project?: string
  new_project_id?: number
  new_project?: string
  old_custodian?: string
  new_custodian?: string
  old_location?: string
  new_location?: string
  condition?: string
  remarks?: string
  performed_by?: string
  occurred_at: string
}

export interface DroneWorkRecord {
  id: number
  work_code: string
  title: string
  work_type: string
  project_id?: number
  project?: string
  asset_id?: number
  asset_tag?: string
  asset_name?: string
  kit_id?: number
  kit_tag?: string
  kit_name?: string
  operation_id?: number
  assigned_to?: string
  technician?: string
  priority: string
  status: string
  approval_status: string
  description?: string
  initial_condition?: string
  resolution?: string
  start_date?: string
  expected_completion_date?: string
  completed_at?: string
  performed_by?: string
  approved_by?: string
  created_at: string
  updated_at: string
}

export interface DroneProjectDetail extends DroneProject {
  assets: DroneSurveyAsset[]
  kits: DroneKit[]
  operations: DroneOperation[]
  work_records: DroneWorkRecord[]
  movements: DroneMovement[]
  summary: {
    asset_count: number
    kit_count: number
    open_operations: number
    overdue_returns: number
    missing_or_damaged: number
    work_records: number
  }
}

export type BackupType = 'daily' | 'monthly' | 'current_month' | 'yearly' | 'financial_year' | 'full'

export interface BackupRun {
  id: number
  backup_code: string
  backup_type: BackupType
  scope: 'all' | 'it' | 'drone'
  status: string
  period_start?: string
  period_end?: string
  excel_filename?: string
  database_filename?: string
  minio_filename?: string
  manifest_filename?: string
  excel_size_bytes?: number
  database_size_bytes?: number
  minio_size_bytes?: number
  checksums?: Record<string, string>
  row_counts?: Record<string, number>
  message?: string
  created_by?: string
  created_at: string
  completed_at?: string
}

export interface BackupStatus {
  root_configured: boolean
  storage_root?: string
  storage_writable: boolean
  last_success?: BackupRun
  last_attempt?: BackupRun
  scheduled_mode: string
  timezone: string
  pg_dump_available: boolean
  database_backup_enabled: boolean
  minio_backup_enabled: boolean
  notes: string[]
}
