export type Role = 'software_team' | 'admin' | 'management' | 'it' | 'drone' | 'finance' | 'hr' | 'bd' | 'ortho' | 'lidar' | 'civil' | 'laser_scanning' | 'bim' | 'mobile_mapping' | 'employee'

export interface ManagementLoginAccount {
  display_name: string
  full_name: string
  email: string
}

export interface AuthUser {
  id: number
  email: string
  full_name: string
  role: Role
  branch: string
  employee_id?: string
  department?: string
  designation?: string
  phone_number?: string | null
  joining_date?: string | null
  date_of_birth?: string | null
  created_at?: string | null
  selected_branch_id?: number
  selected_branch_name?: string
  email_verified?: boolean
  mfa_enabled?: boolean
}

export interface AuthLoginResponse {
  access_token?: string
  token_type: string
  user?: AuthUser
  requires_mfa: boolean
  mfa_setup_required: boolean
  pre_auth_token?: string
  mfa_setup_token?: string
  otpauth_uri?: string
  qr_code_data_uri?: string
  password_change_required: boolean
  password_change_token?: string
  branch_selection_required: boolean
}

export interface Branch {
  id: number
  code: string
  name: string
  address?: string
}

export type FinanceClaimType = 'advance' | 'reimbursement' | 'additional_advance'
export type FinanceClientSourceTeam = 'bd_team' | 'software_team' | 'team_manager' | 'manager' | 'department_head' | 'management' | 'other'
export type FinanceProjectMasterStatus = 'active' | 'on_hold' | 'completed' | 'inactive'
export type FinanceClientType = 'client' | 'uav'

export interface FinanceProjectMasterUser {
  id: number
  full_name: string
  email: string
  employee_id?: string | null
  department?: string | null
  designation?: string | null
  role: string
}

export interface FinanceProjectAssignedEmployee {
  id: number
  full_name: string
  email: string
  employee_id?: string | null
  department?: string | null
}
export type FinanceClaimStatus =
  | 'draft'
  | 'submitted'
  | 'admin_approved'
  | 'admin_rejected'
  | 'admin_sent_back'
  | 'finance_approved'
  | 'partially_paid'
  | 'finance_rejected'
  | 'finance_sent_back'
  | 'paid'

export interface FinanceProject {
  id: number
  project_code: string
  project_name: string
  client_id?: number | null
  client_code?: string | null
  client_name?: string
  project_number?: number | null
  project_source_team?: FinanceClientSourceTeam | null
  project_source_person_name?: string | null
  client_awarded_by_name?: string | null
  project_award_date?: string | null
  description?: string | null
  start_date?: string | null
  end_date?: string | null
  is_active: boolean
  lifecycle_status: string
  expense_allowed: boolean
  expense_block_reason?: string | null
  task?: string | null
  project_status: FinanceProjectMasterStatus
  project_manager_id?: number | null
  project_manager_name?: string | null
  reporting_manager_id?: number | null
  reporting_manager_name?: string | null
  assigned_employee_ids: number[]
  assigned_employees: FinanceProjectAssignedEmployee[]
}

export interface FinanceClient {
  id: number
  vendor_code?: string | null
  client_type: FinanceClientType
  import_source?: string | null
  imported_at?: string | null
  client_code: string
  client_name: string
  primary_phone?: string | null
  client_email?: string | null
  organization_email?: string | null
  contact_person_name: string
  contact_person_phone?: string | null
  contact_person_email?: string | null
  task?: string | null
  bd_name?: string | null
  address?: string | null
  location?: string | null
  description?: string | null
  country: string
  gst_number?: string | null
  source_team: FinanceClientSourceTeam
  source_person_name?: string | null
  is_active: boolean
  project_count: number
  active_project_count: number
  created_at: string
  updated_at: string
  created_by_name?: string | null
  updated_by_name?: string | null
}

export interface ExpenseClaimItem {
  id: number
  category: string
  other_category?: string
  description: string
  amount: number
  payment_mode?: FinancePaymentMode | null
  expense_date?: string | null
}

export interface ExpenseClaimAttachment {
  id: number
  original_filename: string
  mime_type: string
  file_size: number
  content_sha256?: string | null
  uploaded_by_id: number
  uploaded_by_name: string
  created_at: string
}

export interface ExpenseClaimEvent {
  id: number
  action: string
  actor_name?: string
  actor_email?: string
  actor_role?: string
  from_status?: string
  to_status: FinanceClaimStatus
  comments?: string
  created_at: string
}

export type FinancePaymentMode = 'bank_transfer' | 'upi' | 'cash' | 'cheque' | 'card' | 'other'

export interface ExpenseClaimPayment {
  id: number
  payment_reference: string
  payment_mode: FinancePaymentMode
  amount: number
  payment_date: string
  recorded_by_id: number
  recorded_by_name: string
  comments?: string
  created_at: string
}


export type ExpenseSettlementStatus =
  | 'draft'
  | 'submitted'
  | 'admin_approved'
  | 'admin_rejected'
  | 'admin_sent_back'
  | 'finance_finalized'
  | 'finance_rejected'
  | 'finance_sent_back'

export interface ExpenseSettlementItem {
  id: number
  category: string
  other_category?: string | null
  description: string
  amount: number
  payment_mode: FinancePaymentMode
  expense_date?: string | null
}

export interface ExpenseSettlementAttachment {
  id: number
  original_filename: string
  mime_type: string
  file_size: number
  content_sha256?: string | null
  uploaded_by_id: number
  uploaded_by_name: string
  created_at: string
}

export interface ExpenseSettlementEvent {
  id: number
  action: string
  actor_name?: string | null
  actor_email?: string | null
  actor_role?: string | null
  from_status?: string | null
  to_status: string
  comments?: string | null
  created_at: string
}

export interface ExpenseSettlement {
  id: number
  settlement_code: string
  root_claim_id: number
  root_claim_code: string
  requester_id: number
  requester_name: string
  project: FinanceProject
  status: ExpenseSettlementStatus
  total_advance_received: number
  total_expense_amount: number
  balance_to_return: number
  shortage_amount: number
  tally_status: 'tallied' | 'balance_to_return' | 'shortage'
  submitted_at?: string | null
  finalized_at?: string | null
  admin_decision_by_name?: string | null
  admin_decision_at?: string | null
  admin_comments?: string | null
  finance_decision_by_name?: string | null
  finance_decision_at?: string | null
  finance_comments?: string | null
  items: ExpenseSettlementItem[]
  attachments: ExpenseSettlementAttachment[]
  events: ExpenseSettlementEvent[]
  can_edit: boolean
  can_submit: boolean
  can_admin_decide: boolean
  can_finance_decide: boolean
}

export interface ExpenseClaim {
  id: number
  claim_code: string
  requester_id: number
  requester_name: string
  requester_email: string
  requester_department?: string
  project: FinanceProject
  claim_type: FinanceClaimType
  purpose_description: string
  currency: string
  total_amount: number
  previous_advance_amount?: number
  amount_already_used?: number
  parent_advance_claim_id?: number | null
  parent_advance_claim_code?: string | null
  requested_work_start_date?: string | null
  requested_work_end_date?: string | null
  requested_work_days?: number | null
  approved_work_start_date?: string | null
  approved_work_end_date?: string | null
  approved_work_days?: number | null
  settlement_due_date?: string | null
  settlement_status: string
  settlement_overdue: boolean
  status: FinanceClaimStatus
  admin_decision_by_name?: string
  admin_decision_at?: string
  admin_comments?: string
  finance_decision_by_name?: string
  finance_decision_at?: string
  finance_comments?: string
  finance_approved_amount?: number
  remaining_amount: number
  payment_reference?: string
  paid_amount?: number
  paid_at?: string
  submitted_at?: string
  created_at: string
  updated_at: string
  items: ExpenseClaimItem[]
  attachments: ExpenseClaimAttachment[]
  events: ExpenseClaimEvent[]
  payments: ExpenseClaimPayment[]
  settlement?: ExpenseSettlement | null
  linked_additional_advance_ids: number[]
  can_edit: boolean
  can_submit: boolean
  can_admin_decide: boolean
  can_finance_decide: boolean
  can_mark_paid: boolean
  can_settle_advance: boolean
  can_request_additional_advance: boolean
}

export interface FinanceBreakdownItem {
  key: string
  label: string
  amount: number
  count: number
}

export interface FinanceDashboard {
  total_claims: number
  total_requested_amount: number
  pending_admin_count: number
  pending_admin_amount: number
  pending_finance_count: number
  pending_finance_amount: number
  approved_count: number
  approved_amount: number
  paid_count: number
  paid_amount: number
  outstanding_amount: number
  rejected_count: number
  sent_back_count: number
  partially_paid_count: number
  pending_settlement_count: number
  overdue_settlement_count: number
  settlement_under_review_count: number
  settled_count: number
  by_type: FinanceBreakdownItem[]
  by_category: FinanceBreakdownItem[]
  by_project: FinanceBreakdownItem[]
  recent_claims: ExpenseClaim[]
}

export type FinanceReportPeriod = 'month' | 'quarter' | 'year' | 'all'

export interface FinanceReportClaimRow {
  id: number
  claim_code: string
  submitted_at?: string
  requester_name: string
  requester_email: string
  requester_department?: string
  project_code: string
  project_name: string
  claim_type: FinanceClaimType
  status: FinanceClaimStatus
  requested_amount: number
  approved_amount: number
  paid_amount: number
  outstanding_amount: number
  attachment_count: number
  payment_count: number
  updated_at: string
}

export interface FinanceReport {
  period: FinanceReportPeriod
  period_label: string
  start_date?: string
  end_date?: string
  available_years: number[]
  total_records: number
  page: number
  page_size: number
  total_pages: number
  requested_amount: number
  approved_amount: number
  paid_amount: number
  outstanding_amount: number
  payment_period_amount: number
  payment_period_count: number
  pending_admin_amount: number
  pending_finance_amount: number
  integrity_issue_count: number
  by_project: FinanceBreakdownItem[]
  by_employee: FinanceBreakdownItem[]
  by_category: FinanceBreakdownItem[]
  by_type: FinanceBreakdownItem[]
  by_status: FinanceBreakdownItem[]
  claims: FinanceReportClaimRow[]
}

export type TicketDepartment = 'it' | 'drone' | 'software_team' | 'management'
export type TicketPriority = 'low' | 'medium' | 'high' | 'critical'
export type TicketStatus = 'new' | 'assigned' | 'in_progress' | 'waiting_for_employee' | 'resolved' | 'closed' | 'reopened'

export interface TicketProblemOption {
  code: string
  label: string
}

export interface TicketComponentOption {
  code: string
  label: string
  problems: TicketProblemOption[]
}

export interface TicketCatalog {
  components: TicketComponentOption[]
}

export interface TicketImpactAssessment {
  work_stopped: boolean
  alternative_available: boolean
  multiple_users_affected: boolean
  data_loss_risk: boolean
  security_risk: boolean
  client_delivery_affected: boolean
  recurring_issue: boolean
  started_when?: string
}

export interface TicketPriorityPreview {
  priority: TicketPriority
  priority_label: string
  reason: string
  sla_target_minutes: number
  problem_label: string
}

export interface SupportTicketSummary {
  id: number
  ticket_code: string
  requester_name: string
  requester_email: string
  branch_id: number
  branch_name: string
  department: TicketDepartment
  category?: string
  title: string
  priority: TicketPriority
  status: TicketStatus
  asset_number?: string
  component?: string
  component_asset_tag?: string
  problem_code?: string
  problem_label?: string
  priority_reason?: string
  sla_target_minutes?: number
  sla_status?: 'not_applicable' | 'on_track' | 'warning' | 'breached' | 'met'
  sla_due_at?: string
  sla_warning_at?: string
  sla_first_response_at?: string
  sla_remaining_seconds?: number
  sla_warning?: boolean
  sla_breached?: boolean
  sla_escalation_level?: 'none' | 'warning' | 'breach' | 'critical_breach'
  assigned_to_name?: string
  queue_position?: number
  created_at: string
  updated_at: string
  resolved_at?: string
  closed_at?: string
  can_handle: boolean
}

export interface TicketAttachment {
  id: number
  ticket_id: number
  message_id?: number
  uploaded_by_id: number
  uploaded_by_name: string
  original_filename: string
  mime_type: string
  file_size: number
  created_at: string
}

export interface TicketMessage {
  id: number
  author_id: number
  author_name: string
  author_email: string
  author_role: Role
  message: string
  created_at: string
}

export interface TicketAsset {
  id: number
  asset_code: string
  cpu_asset_tag?: string
  workstation_no?: string
  used_by?: string
  department?: string
  system_name?: string
  brand?: string
  model?: string
  serial_number?: string
  connection_type?: string
  capacity?: string
  ownership?: string
  client_name?: string
  project_id?: string
  current_holder?: string
  device_type: string
  processor?: string
  memory_gb?: string
  ssd?: string
  hdd?: string
  operating_system?: string
  location?: string
  work_mode?: string
  status: string
  monitor_asset_tags?: string
  mouse_asset_tag?: string
  keyboard_asset_tag?: string
}

export interface SupportTicket extends SupportTicketSummary {
  description: string
  reporting_manager_email?: string
  location?: string
  asset_number?: string
  asset_id?: number
  asset_snapshot?: TicketAsset
  impact_assessment?: TicketImpactAssessment
  resolution?: string
  attachments?: TicketAttachment[]
  messages: TicketMessage[]
}

export interface TicketNotification {
  id: number
  ticket_id: number
  ticket_code: string
  notification_type: string
  title: string
  message: string
  is_read: boolean
  created_at: string
}

export interface SoftwareUser {
  id: number
  full_name: string
  email: string
  employee_id?: string
  department?: string
  designation?: string
  phone_masked?: string
  role: Role
  branch: string
  email_verified: boolean
  account_status: string
  mfa_enabled: boolean
  is_active: boolean
  last_login_at?: string
  last_logout_at?: string
  created_at: string
}

export interface AuditEvent {
  id: number
  actor_email?: string
  event_type: string
  result: string
  branch_name?: string
  module?: string
  target_type?: string
  target_id?: string
  details?: string
  ip_address?: string
  user_agent?: string
  created_at: string
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
  key?: string
}

export type ActivityMetricKey =
  | 'total_activities'
  | 'asset_edit_operations'
  | 'component_changes'
  | 'handover_operations'
  | 'return_operations'
  | 'purchases_recorded'

export interface ActivityTrendPoint {
  month: string
  label: string
  total_activities: number
  asset_edit_operations: number
  component_changes: number
  handover_operations: number
  return_operations: number
  purchases_recorded: number
}

export interface ITActivitySummaryData {
  month: {
    key: string
    label: string
  }
  summary: {
    assets_edited: number
    asset_edit_operations: number
    component_changes: number
    upgrades: number
    replacements: number
    downgrades: number
    combined_changes: number
    laptop_handovers: number
    desktop_handovers: number
    handover_operations: number
    return_operations: number
    purchases_recorded: number
    purchase_value: number
    total_activities: number
  }
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
  brand?: string
  model?: string
  serial_number?: string
  connection_type?: string
  capacity?: string
  ownership?: string
  client_name?: string
  project_id?: string
  current_holder?: string
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
  performed_by_email?: string
  performed_by_role?: string
  approved_by?: string
  price?: number
  remarks?: string
  asset_date?: string
  original_asset_date?: string
  location?: string
  work_mode: string
  status: string
  created_at: string
  updated_at: string
  last_change_at?: string
  last_changed_by?: string
  last_changed_by_role?: string
  last_change_type?: string
  last_change_reason?: string
  last_field_count?: number
  history?: Array<{
    action: string
    change_type?: string
    batch_code?: string
    old_value?: string
    new_value?: string
    remarks?: string
    reason?: string
    changed_by?: string
    changed_by_name?: string
    changed_by_role?: string
    field_count?: number
    reporting_month?: string
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
  submitted_by_name?: string
  submitted_by_email?: string
  submitted_by_role?: Role
  submitted_at?: string
  approved_by_name?: string
  approved_by_email?: string
  approved_by_role?: Role
  approved_at?: string
  approval_comments?: string
  start_date?: string
  expected_completion_date?: string
  completed_at?: string
  reporting_month?: string
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
  performed_by_email?: string
  performed_by_role?: string
  approved_by?: string
  remarks?: string
  work_record_id?: number
  work_code?: string
  reporting_month?: string
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
  requested_by_email?: string
  requested_by_role?: string
  approved_by?: string
  approved_by_email?: string
  approved_by_role?: string
  reporting_month?: string
  created_at: string
  approved_at?: string
  decision_remarks?: string
  updated_at?: string
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
    asset_edit_operations: number
    assets_edited: number
  }
  kpis: {
    total: number
    computers: number
    laptops: number
    smartphones: number
    printers: number
    external_hdds: number
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

export interface ITActivityItem {
  activity_id: string
  source_type: 'asset_edit' | 'component_change' | 'handover_return' | 'purchase' | string
  record_id: number
  asset_id?: number
  asset_code?: string
  cpu_asset_tag?: string
  workstation_no?: string
  device_category?: string
  department?: string
  action_type: string
  action_label: string
  field_or_component?: string
  old_value?: unknown
  new_value?: unknown
  reason?: string
  remarks?: string
  performed_by?: string
  performed_by_email?: string
  performed_by_role?: string
  batch_code?: string
  activity_date?: string
  activity_time?: string
  timestamp?: string
  reporting_month?: string
  system_recorded_at?: string
  time_recorded: boolean
  condition?: string
  accessories?: string
  supplier_name?: string
  po_number?: string
  quantity?: number
  total_price?: number
}

export interface ITActivitySummary {
  month: { key: string; label: string; start: string; end: string; timezone: string }
  summary: {
    assets_edited: number
    asset_edit_operations: number
    component_changes: number
    upgrades: number
    replacements: number
    downgrades: number
    combined_changes: number
    laptop_handovers: number
    desktop_handovers: number
    handover_operations: number
    return_operations: number
    purchases_recorded: number
    purchase_value: number
    total_activities: number
  }
  visual_summary: DistributionItem[]
  user_activity: DistributionItem[]
  timeline: ITActivityItem[]
  items: ITActivityItem[]
  total: number
  filters: {
    departments: string[]
    users: string[]
    device_categories: string[]
    action_types: string[]
  }
}

export interface ITHandoverRecord {
  id: number
  activity_code: string
  asset_id?: number
  asset_code_snapshot?: string
  device_category: 'laptop' | 'desktop'
  employee_name?: string
  from_employee_name?: string
  to_employee_name?: string
  dc_number?: string
  department?: string
  work_mode?: string
  internal_asset_no?: string
  specification?: string
  serial_number?: string
  accessories_provided?: string
  condition?: string
  action_type: string
  action_raw?: string
  activity_date: string
  activity_time?: string
  issued_by?: string
  remarks?: string
  asset_updated_status?: string
  source_file?: string
  source_sheet?: string
  source_row?: number
  imported: boolean
  performed_by?: string
  performed_by_email?: string
  performed_by_role?: string
  reporting_month?: string
  created_at: string
}

export interface ITPurchaseRecord {
  id: number
  purchase_code: string
  purchase_request_id?: number
  purchase_request_code?: string
  linked_asset_id?: number
  linked_asset_code_snapshot?: string
  purchase_date: string
  po_number?: string
  asset_number?: string
  supplier_name: string
  supplier_contact?: string
  item_description: string
  warranty_number?: string
  quantity: number
  unit_price?: number
  total_price?: number
  received_date?: string
  inspection_status?: string
  approved_by?: string
  department?: string
  remarks?: string
  source_file?: string
  source_sheet?: string
  source_row?: number
  imported: boolean
  created_by?: string
  created_by_email?: string
  created_by_role?: string
  reporting_month?: string
  created_at: string
}

export type PurchaseRequestStatus = 'pending_approval' | 'approved' | 'rejected' | 'sent_back' | 'purchase_completed'

export interface PurchaseRequestHistory {
  id: number
  action: string
  from_status?: string
  to_status: PurchaseRequestStatus
  remarks?: string
  performed_by_name: string
  performed_by_email: string
  performed_by_role: Role
  created_at: string
}

export interface ITPurchaseRequest {
  id: number
  request_code: string
  reporting_month?: string
  requesting_department: string
  requested_employee: string
  item_type: 'hardware' | 'software' | 'other'
  item_name: string
  item_description?: string
  quantity: number
  estimated_unit_price?: number
  estimated_total_amount?: number
  business_reason: string
  required_by_date?: string
  priority: 'low' | 'medium' | 'high' | 'critical'
  it_remarks?: string
  status: PurchaseRequestStatus
  branch?: string
  requested_by_name: string
  requested_by_email: string
  requested_by_role: Role
  requested_at: string
  approved_amount?: number
  management_remarks?: string
  decided_by_name?: string
  decided_by_email?: string
  decided_by_role?: Role
  decided_at?: string
  purchase_completed_at?: string
  updated_at: string
  purchase_record_id?: number
  purchase_code?: string
  actual_purchase_amount?: number
  purchase_date?: string
  histories: PurchaseRequestHistory[]
}

export interface PurchaseRequestSummary {
  total: number
  pending_approval: number
  approved: number
  rejected: number
  sent_back: number
  purchase_completed: number
  estimated_value: number
  approved_value: number
  departments: string[]
}

export type ITAssetDrilldownScope = 'all' | 'primary' | 'device' | 'status' | 'department'

export interface ITAssetDrilldownSelection {
  scope: ITAssetDrilldownScope
  value?: string
}

export interface ITAssetDrilldownData {
  month: {
    key: string
    label: string
    source: string
    is_live: boolean
  }
  scope: {
    type: ITAssetDrilldownScope
    value?: string
    label: string
  }
  scope_total: number
  filtered_total: number
  page: number
  page_size: number
  pages: number
  summary: {
    total: number
    computers: number
    laptops: number
    smartphones: number
    printers: number
    external_hdds: number
    nakshatech_owned: number
    client_owned: number
    issued: number
    permanently_issued: number
    returned: number
    assigned: number
    available: number
    repair: number
    replacement_pending: number
  }
  filtered_summary: {
    total: number
    computers: number
    laptops: number
    smartphones: number
    printers: number
    external_hdds: number
    nakshatech_owned: number
    client_owned: number
    issued: number
    permanently_issued: number
    returned: number
    assigned: number
    available: number
    repair: number
    replacement_pending: number
  }
  visuals: {
    device_distribution: DistributionItem[]
    status_distribution: DistributionItem[]
    department_distribution: DistributionItem[]
  }
  filter_options: {
    devices: string[]
    departments: string[]
    statuses: string[]
    locations: string[]
    work_modes: string[]
    ownerships: string[]
    clients: string[]
    projects: string[]
    holders: string[]
    brands: string[]
    capacities: string[]
  }
    assets: Asset[]
}

export type BusinessViewer = 'finance' | 'management' | 'bd' | 'project_manager' | 'unavailable'

export type BusinessRecordStatus = 'submitted' | 'verified'

export interface BusinessTotals {
  total: number
  released: number
  pending: number
  currency: string
}

export interface BusinessBreakdownRow {
  key: string
  label: string
  total: number
  released: number
  pending: number
  project_count: number
}

export interface BusinessBillingSuggestion {
  total: number
  released: number
  pending: number
  currency: string
  invoice_count: number
  payment_count: number
}

export interface BusinessRecordRow {
  record_id?: number | null
  project_id: number
  project_code: string
  project_name: string
  client_id?: number | null
  client_code?: string | null
  client_name?: string | null
  project_manager_user_id?: number | null
  project_manager_name?: string | null
  department_code: string
  department_label: string
  amount_total: number
  amount_released: number
  amount_pending: number
  currency: string
  notes?: string | null
  status: BusinessRecordStatus
  verified_at?: string | null
  updated_at?: string | null
  billing: BusinessBillingSuggestion
}

export interface BusinessMonthPoint {
  month: string
  label: string
  total: number
  released: number
  pending: number
}

export interface BusinessHistoryChange {
  from: string | number | null
  to: string | number | null
}

export interface BusinessHistoryEntry {
  id: number
  action: string
  actor_name?: string | null
  actor_role?: string | null
  reporting_month: string
  changes?: Record<string, BusinessHistoryChange> | null
  created_at: string
}

export interface BusinessOverview {
  month: string
  viewer: BusinessViewer
  can_enter: boolean
  totals: BusinessTotals
  by_department: BusinessBreakdownRow[]
  by_project_manager: BusinessBreakdownRow[]
  by_client: BusinessBreakdownRow[]
  rows: BusinessRecordRow[]
  months: string[]
  my_monthly_history: BusinessMonthPoint[]
}
