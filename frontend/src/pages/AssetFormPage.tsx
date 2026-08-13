import {
  ArrowLeft,
  Boxes,
  CheckCircle2,
  CircleDollarSign,
  Cpu,
  Database,
  HardDrive,
  History,
  Network,
  Printer,
  Save,
  ShieldCheck,
  UserRound,
} from 'lucide-react'
import { FormEvent, ReactNode, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { DashboardHeader } from '../components/DashboardHeader'
import { useAuth } from '../context/AuthContext'
import { useITMonthUrl } from '../context/ITMonthContext'
import { apiFetch } from '../lib/api'
import {
  ASSET_LOCATION_OPTIONS,
  DEPARTMENT_OPTIONS,
  MANUAL_ENTRY_VALUE,
  OFFICE_LOCATION_VALUE,
  normaliseAssetEditLocation,
} from '../lib/assetOptions'
import { formatIndiaDateTime } from '../lib/date'
import { monthLabel, withITMonth } from '../lib/itMonth'
import type { Asset } from '../types'

const statusOptions = [
  'available', 'assigned', 'in_use', 'wfh', 'field_deployment', 'under_inspection', 'repair',
  'replacement_pending', 'replaced', 'damaged', 'beyond_repair', 'returned', 'missing', 'retired',
  'for_parts', 'disposal_pending', 'disposed',
]
const assignedStatuses = new Set(['assigned', 'in_use', 'wfh', 'field_deployment'])
const externalHddStatuses = ['available', 'in_use', 'issued', 'permanently_issued', 'returned', 'repair', 'replacement_pending', 'missing', 'retired', 'disposed']

type AssetForm = {
  device_type: string
  status: string
  used_by: string
  department: string
  workstation_no: string
  cpu_asset_tag: string
  monitor_asset_tags: string
  mouse_asset_tag: string
  keyboard_asset_tag: string
  system_name: string
  brand: string
  model: string
  serial_number: string
  connection_type: string
  capacity: string
  ownership: string
  client_name: string
  project_id: string
  current_holder: string
  processor: string
  memory_gb: string
  ssd: string
  hdd: string
  ip_address: string
  mac_address: string
  graphics_card: string
  operating_system: string
  antivirus: string
  network_type: string
  approved_by: string
  price: string
  remarks: string
  asset_date: string
  location: string
  work_mode: string
}

const fieldLabels: Record<keyof AssetForm, string> = {
  device_type: 'Device Type', status: 'Status', used_by: 'Used By', department: 'Department',
  workstation_no: 'Workstation Number', cpu_asset_tag: 'CPU / Asset Tag',
  monitor_asset_tags: 'Monitor Asset Tag(s)', mouse_asset_tag: 'Mouse Asset Tag',
  keyboard_asset_tag: 'Keyboard Asset Tag', system_name: 'System Name', brand: 'Brand',
  model: 'Model', serial_number: 'Serial Number', connection_type: 'Connection Type', capacity: 'Capacity',
  ownership: 'Ownership', client_name: 'Client Name', project_id: 'Project ID', current_holder: 'Current Holder', processor: 'Processor',
  memory_gb: 'Memory', ssd: 'SSD', hdd: 'HDD', ip_address: 'IP Address',
  mac_address: 'MAC Address', graphics_card: 'Graphics Card', operating_system: 'Operating System',
  antivirus: 'Antivirus', network_type: 'Network Type', approved_by: 'Approved By', price: 'Price',
  remarks: 'Remarks', asset_date: 'Asset Record Date', location: 'Location', work_mode: 'Work Mode',
}

function emptyAssetForm(): AssetForm {
  return {
    device_type: 'Computer', status: 'available', used_by: '', department: '', workstation_no: '',
    cpu_asset_tag: '', monitor_asset_tags: '', mouse_asset_tag: '', keyboard_asset_tag: '',
    system_name: '', brand: '', model: '', serial_number: '', connection_type: '', capacity: '',
    ownership: 'NakshaTech', client_name: '', project_id: '', current_holder: '', processor: '',
    memory_gb: '', ssd: '', hdd: '', ip_address: '', mac_address: '',
    graphics_card: '', operating_system: '', antivirus: '', network_type: 'DHCP', approved_by: '',
    price: '', remarks: '', asset_date: new Date().toISOString().slice(0, 10), location: OFFICE_LOCATION_VALUE,
    work_mode: 'office',
  }
}

function formFromAsset(asset: Asset, normaliseControlledFields = true): AssetForm {
  return {
    device_type: asset.device_type || 'Computer', status: asset.status || 'available',
    used_by: asset.used_by || '', department: asset.department || '', workstation_no: asset.workstation_no || '',
    cpu_asset_tag: asset.cpu_asset_tag || '', monitor_asset_tags: asset.monitor_asset_tags || '',
    mouse_asset_tag: asset.mouse_asset_tag || '', keyboard_asset_tag: asset.keyboard_asset_tag || '',
    system_name: asset.system_name || '', brand: asset.brand || '', model: asset.model || '',
    serial_number: asset.serial_number || '', connection_type: asset.connection_type || '',
    capacity: asset.capacity || '', ownership: asset.ownership || 'NakshaTech',
    client_name: asset.client_name || '', project_id: asset.project_id || '', current_holder: asset.current_holder || '',
    processor: asset.processor || '', memory_gb: asset.memory_gb || '',
    ssd: asset.ssd || '', hdd: asset.hdd || '', ip_address: asset.ip_address || '',
    mac_address: asset.mac_address || '', graphics_card: asset.graphics_card || '',
    operating_system: asset.operating_system || '', antivirus: asset.antivirus || '',
    network_type: asset.network_type || 'DHCP', approved_by: asset.approved_by || '',
    price: asset.price === undefined || asset.price === null ? '' : String(asset.price), remarks: asset.remarks || '',
    asset_date: asset.asset_date || '',
    location: normaliseControlledFields && asset.device_type !== 'External HDD'
      ? normaliseAssetEditLocation(asset.location)
      : (asset.location || 'Head Office'),
    work_mode: asset.work_mode || 'office',
  }
}

function payloadFromForm(form: AssetForm) {
  const externalHdd = form.device_type === 'External HDD'
  return {
    ...form,
    price: externalHdd || form.price === '' ? null : Number(form.price),
    asset_date: form.asset_date || null,
    used_by: externalHdd ? null : (form.used_by || null),
    department: form.department || null,
    workstation_no: externalHdd ? null : (form.workstation_no || null),
    cpu_asset_tag: form.cpu_asset_tag || null,
    monitor_asset_tags: externalHdd ? null : (form.monitor_asset_tags || null),
    mouse_asset_tag: externalHdd ? null : (form.mouse_asset_tag || null),
    keyboard_asset_tag: externalHdd ? null : (form.keyboard_asset_tag || null),
    system_name: externalHdd ? null : (form.system_name || null),
    brand: form.brand || null,
    model: externalHdd ? null : (form.model || null),
    serial_number: form.serial_number || null,
    connection_type: externalHdd ? null : (form.connection_type || null),
    capacity: form.capacity || null,
    ownership: form.ownership || null,
    client_name: form.client_name || null,
    project_id: form.project_id || null,
    current_holder: form.current_holder || null,
    processor: externalHdd ? null : (form.processor || null),
    memory_gb: externalHdd ? null : (form.memory_gb || null),
    ssd: externalHdd ? null : (form.ssd || null),
    hdd: externalHdd ? null : (form.hdd || null),
    ip_address: externalHdd ? null : (form.ip_address || null),
    mac_address: externalHdd ? null : (form.mac_address || null),
    graphics_card: externalHdd ? null : (form.graphics_card || null),
    operating_system: externalHdd ? null : (form.operating_system || null),
    antivirus: externalHdd ? null : (form.antivirus || null),
    network_type: externalHdd ? null : (form.network_type || null),
    approved_by: externalHdd ? null : (form.approved_by || null),
    remarks: form.remarks || null,
    location: externalHdd ? (form.current_holder || form.department || null) : (form.location || null),
    work_mode: externalHdd ? 'office' : form.work_mode,
  }
}

function FormSection({
  icon,
  title,
  description,
  children,
}: {
  icon: ReactNode
  title: string
  description: string
  children: ReactNode
}) {
  return (
    <section className="asset-form-section panel">
      <div className="asset-form-section-heading">
        <span className="asset-form-section-icon">{icon}</span>
        <div><h2>{title}</h2><p>{description}</p></div>
      </div>
      <div className="asset-form-fields">{children}</div>
    </section>
  )
}

export function AssetFormPage() {
  const { id } = useParams()
  const isEdit = Boolean(id)
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { user } = useAuth()
  const { selectedMonth } = useITMonthUrl()
  const requestedDeviceType = searchParams.get('device_type')
  const returnToPrinterDrawer = searchParams.get('return_to') === 'printer-drawer'
  const returnToExternalHddDrawer = searchParams.get('return_to') === 'external-hdd-drawer'
  const returnToAssetDrawer = searchParams.get('return_to') === 'asset-drawer'
  const returnDrawerScope = searchParams.get('drawer_scope') || 'primary'
  const returnDrawerValue = searchParams.get('drawer_value') || ''
  const [form, setForm] = useState<AssetForm>(() => {
    const initial = emptyAssetForm()
    if (!isEdit && requestedDeviceType === 'Printer') initial.device_type = 'Printer'
    if (!isEdit && requestedDeviceType === 'External HDD') initial.device_type = 'External HDD'
    return initial
  })
  const [originalForm, setOriginalForm] = useState<AssetForm | null>(null)
  const [auditReason, setAuditReason] = useState('')
  const [auditRemarks, setAuditRemarks] = useState('')
  const [assetCode, setAssetCode] = useState('Generated automatically after save')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(isEdit)
  const [error, setError] = useState('')
  const [validationErrors, setValidationErrors] = useState<string[]>([])
  const [manualLocationEntry, setManualLocationEntry] = useState(false)
  const [manualDepartmentEntry, setManualDepartmentEntry] = useState(false)

  useEffect(() => {
    if (!id) return
    void (async () => {
      try {
        const asset = await apiFetch<Asset>(`/assets/${id}`)
        const loadedForm = formFromAsset(asset)
        const originalLoadedForm = formFromAsset(asset, false)
        setForm(loadedForm)
        setOriginalForm(originalLoadedForm)
        setAssetCode(asset.asset_code)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unable to load asset')
      } finally {
        setLoading(false)
      }
    })()
  }, [id])

  const isPrinter = form.device_type === 'Printer'
  const isExternalHdd = form.device_type === 'External HDD'
  const isStandaloneAsset = isPrinter || isExternalHdd
  const assetDrawerReturnPath = (() => {
    const params = new URLSearchParams({ drawer: 'assets', drawer_scope: returnDrawerScope })
    if (returnDrawerValue) params.set('drawer_value', returnDrawerValue)
    return withITMonth(`/it?${params.toString()}`, selectedMonth)
  })()
  const returnPath = returnToPrinterDrawer
    ? withITMonth('/it?drawer=printers', selectedMonth)
    : returnToExternalHddDrawer
      ? withITMonth('/it?drawer=external-hdds', selectedMonth)
      : returnToAssetDrawer
        ? assetDrawerReturnPath
        : withITMonth('/assets', selectedMonth)

  const primaryIdentity = useMemo(() => {
    if (isPrinter) {
      const tag = form.cpu_asset_tag.trim() || 'Printer Asset ID not entered'
      const identity = [form.brand.trim(), form.model.trim()].filter(Boolean).join(' ') || 'Brand / model not entered'
      return `${tag} / ${identity}`
    }
    if (isExternalHdd) {
      const tag = form.cpu_asset_tag.trim() || 'External HDD Asset ID not entered'
      const identity = [form.brand.trim(), form.capacity.trim()].filter(Boolean).join(' ') || 'Brand / capacity not entered'
      return `${tag} / ${identity}`
    }
    const cpu = form.cpu_asset_tag.trim() || 'CPU tag not entered'
    const ws = form.workstation_no.trim() || 'Workstation not entered'
    return `${cpu} / ${ws}`
  }, [form.brand, form.capacity, form.cpu_asset_tag, form.model, form.workstation_no, isExternalHdd, isPrinter])

  const changedFields = useMemo(() => {
    if (!isEdit || !originalForm) return [] as Array<keyof AssetForm>
    return (Object.keys(form) as Array<keyof AssetForm>).filter(key => {
      const current = String(form[key] ?? '').trim()
      const original = String(originalForm[key] ?? '').trim()
      return current !== original
    })
  }, [form, isEdit, originalForm])

  function update<K extends keyof AssetForm>(key: K, value: AssetForm[K]) {
    setForm(current => {
      const next = { ...current, [key]: value }
      if (key === 'status' && !assignedStatuses.has(String(value))) {
        next.used_by = ''
      }
      if (key === 'work_mode') {
        if (value === 'wfh') next.status = 'wfh'
        if (value === 'field') next.status = 'field_deployment'
        if (value === 'office' && ['wfh', 'field_deployment'].includes(next.status)) {
          next.status = next.used_by ? 'assigned' : 'available'
        }
      }
      return next
    })
  }

  function validate(): string[] {
    const errors: string[] = []
    if (!form.cpu_asset_tag.trim()) errors.push(isPrinter ? 'Printer Asset ID is required.' : isExternalHdd ? 'External HDD Asset ID is required.' : 'CPU / Physical Asset Tag is required.')
    if (!form.device_type.trim()) errors.push('Device Type is required.')
    if (form.device_type === 'Printer') {
      if (!form.brand.trim()) errors.push('Printer Brand is required.')
      if (!form.model.trim()) errors.push('Printer Model is required.')
    }
    if (isExternalHdd) {
      if (!form.brand.trim()) errors.push('External HDD Brand is required.')
      if (!form.capacity.trim()) errors.push('External HDD Capacity is required.')
      if (!form.serial_number.trim()) errors.push('External HDD Serial Number is required.')
      if (!form.ownership.trim()) errors.push('External HDD Ownership is required.')
      if (form.ownership === 'Client' && !form.client_name.trim()) errors.push('Client Name is required for a client-owned External HDD.')
      if (['in_use', 'issued', 'permanently_issued'].includes(form.status) && !form.current_holder.trim()) errors.push('Current Holder is required for an in-use or issued External HDD.')
    }
    if (assignedStatuses.has(form.status)) {
      if (isExternalHdd) {
        // External HDD holder and movement rules are validated above.
      } else if (form.device_type === 'Printer') {
        if (!form.department.trim()) errors.push('Department is required for an assigned printer.')
        if (!form.used_by.trim() && !form.location.trim()) errors.push('Assigned printers require an Assigned User or Floor / Location.')
      } else {
        if (!form.used_by.trim()) errors.push('Used By is required for assigned or in-use assets.')
        if (!form.department.trim()) errors.push('Department is required for assigned or in-use assets.')
        if (!form.workstation_no.trim()) errors.push('Workstation Number is required for assigned or in-use assets.')
      }
    }
    if (!isExternalHdd && form.status === 'available' && form.used_by.trim()) {
      errors.push('Available assets cannot have an employee. To register directly to a user, change Status to Assigned / In Use; otherwise leave Used By blank and assign after registration.')
    }
    if (!isStandaloneAsset && form.network_type.toLowerCase().includes('static') && !form.ip_address.trim()) {
      errors.push('Static network type requires an IP Address.')
    }
    if (form.price && Number.isNaN(Number(form.price))) errors.push('Price must be a valid number.')
    if (isEdit && changedFields.length === 0) errors.push('No asset details were changed.')
    return errors
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    const errors = validate()
    setValidationErrors(errors)
    setError('')
    if (errors.length) {
      window.scrollTo({ top: 0, behavior: 'smooth' })
      return
    }
    setBusy(true)
    try {
      const requestPayload = payloadFromForm(form) as ReturnType<typeof payloadFromForm> & {
        reporting_month: string
        audit_reason?: string
        audit_remarks?: string
      }
      requestPayload.reporting_month = selectedMonth
      if (isEdit) {
        requestPayload.audit_reason = auditReason.trim() || undefined
        requestPayload.audit_remarks = auditRemarks.trim() || undefined
      }
      const saved = await apiFetch<Asset>(isEdit ? `/assets/${id}` : '/assets', {
        method: isEdit ? 'PATCH' : 'POST',
        body: JSON.stringify(requestPayload),
      })
      const savedAt = formatIndiaDateTime(saved.updated_at)
      navigate(returnPath, {
        replace: true,
        state: {
          message: isEdit
            ? `${saved.cpu_asset_tag || saved.asset_code} updated successfully. ${changedFields.length} field${changedFields.length === 1 ? '' : 's'} changed by ${user?.full_name || 'the logged-in user'} on ${savedAt}.`
            : isPrinter
              ? `Printer ${saved.cpu_asset_tag || saved.asset_code} was added successfully.`
              : isExternalHdd
                ? `External HDD ${saved.cpu_asset_tag || saved.asset_code} was added successfully.`
                : `${saved.asset_code} created successfully. CPU / Asset Tag ${saved.cpu_asset_tag || 'not recorded'} is now in the live register.`,
          openAssetId: saved.id,
        },
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to save asset')
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <div className="panel loading-panel">Loading asset details…</div>

  return (
    <>
      <DashboardHeader
        eyebrow={isEdit ? 'UPDATE INVENTORY' : 'NEW INVENTORY'}
        title={isPrinter
          ? (isEdit ? `Edit Printer ${form.cpu_asset_tag || assetCode}` : 'Add New Printer')
          : isExternalHdd
            ? (isEdit ? `Edit External HDD ${form.cpu_asset_tag || assetCode}` : 'Add New External HDD')
            : (isEdit ? `Edit ${assetCode}` : 'Add IT Asset')}
        description={isPrinter
          ? `Maintain the dedicated Printer Asset Register fields for ${monthLabel(selectedMonth)}. Last updated date and time are recorded automatically by the server.`
          : isExternalHdd
            ? `Maintain only External HDD register fields for ${monthLabel(selectedMonth)}. Holder, project and status changes remain in the audit timeline.`
            : `Complete one full form. This activity will be reported in ${monthLabel(selectedMonth)}, while the actual server save date and time remain unchanged.`}
        actions={<button className="secondary-button" onClick={() => navigate(returnPath)}><ArrowLeft size={17} /> {returnToPrinterDrawer ? 'Back to Printer Assets' : returnToExternalHddDrawer ? 'Back to External HDD Assets' : 'Back to Register'}</button>}
      />

      {(error || validationErrors.length > 0) && <div className="asset-form-alerts">
        {error && <div className="error-message">{error}</div>}
        {validationErrors.length > 0 && <div className="error-message"><strong>Correct these items before saving:</strong><ul>{validationErrors.map(item => <li key={item}>{item}</li>)}</ul></div>}
      </div>}

      <form className="asset-full-page-form" onSubmit={submit}>
        <section className="asset-identity-banner panel">
          <div>
            <span className="section-kicker">PRIMARY OPERATIONAL IDENTIFICATION</span>
            <h2>{primaryIdentity}</h2>
            <p>{isPrinter ? 'Brand, model, serial number, connection, assignment, department, floor, status and remarks are linked to this Printer Asset ID.' : isExternalHdd ? 'Brand, capacity, serial number, ownership, department, client, project, current holder, status and remarks are linked to this External HDD Asset ID.' : 'All employee, department, component, hardware, network, software, price and audit information is linked to this CPU tag and workstation.'}</p>
          </div>
          <div className="asset-system-reference"><small>Internal System Asset ID</small><strong>{assetCode}</strong></div>
        </section>

        <FormSection
          icon={isPrinter ? <Printer size={22} /> : isExternalHdd ? <Database size={22} /> : <Cpu size={22} />}
          title="1. Asset Identity"
          description={isPrinter
            ? 'Record the printer ID, current status and physical floor or location.'
            : isExternalHdd
              ? 'Record the portable External HDD ID and its current operational status.'
              : 'Record the physical asset and where it is placed. These fields appear first in daily IT searches.'}
        >
          <label>{isPrinter ? 'Printer Asset ID' : isExternalHdd ? 'External HDD Asset ID' : 'CPU / Physical Asset Tag'} <span>*</span><input autoFocus required value={form.cpu_asset_tag} onChange={e => update('cpu_asset_tag', e.target.value)} placeholder={isPrinter ? 'Example: PRN001' : isExternalHdd ? 'Example: HDD001' : 'Example: 3953'} /></label>
          {!isStandaloneAsset && <label>Workstation Number<input value={form.workstation_no} onChange={e => update('workstation_no', e.target.value)} placeholder="Example: NW045 / 2nd Floor" /></label>}
          <label>Device Type{isStandaloneAsset ? <input value={form.device_type} readOnly aria-readonly="true" /> : <select value={form.device_type} onChange={e => update('device_type', e.target.value)}><option>Computer</option><option>Laptop</option><option>Smartphone</option><option>Printer</option><option>External HDD</option><option>Server</option><option>Network Device</option><option>Other</option></select>}</label>
          <label>Status<select value={form.status} onChange={e => update('status', e.target.value)}>{(isExternalHdd ? externalHddStatuses : statusOptions).map(item => <option key={item} value={item}>{item.replaceAll('_', ' ')}</option>)}</select></label>
          {!isStandaloneAsset && <label>System Name<input value={form.system_name} onChange={e => update('system_name', e.target.value)} placeholder="Windows computer name" /></label>}
          {isPrinter && <label>Floor / Location<input value={form.location} onChange={e => update('location', e.target.value)} placeholder="Example: 3rd Floor / Finance" /></label>}
          {!isStandaloneAsset && <label>Location<select value={manualLocationEntry ? MANUAL_ENTRY_VALUE : form.location} onChange={e => { const value = e.target.value; if (value === MANUAL_ENTRY_VALUE) { setManualLocationEntry(true); update('location', '') } else { setManualLocationEntry(false); update('location', value) } }}><option value="">Select location</option>{!manualLocationEntry && form.location && !ASSET_LOCATION_OPTIONS.some(option => option.value === form.location) && <option value={form.location}>Current legacy value — {form.location}</option>}{ASSET_LOCATION_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}<option value={MANUAL_ENTRY_VALUE}>Other / Manual Entry</option></select>{manualLocationEntry && <input autoFocus value={form.location} onChange={e => update('location', e.target.value)} placeholder="Enter custom location" />}</label>}
          {!isStandaloneAsset && <label>Work Mode<select value={form.work_mode} onChange={e => update('work_mode', e.target.value)}><option value="office">Office</option><option value="wfh">Work From Home</option><option value="field">Field</option></select></label>}
          {!isExternalHdd && <label>Asset / Record Date<input type="date" value={form.asset_date} onChange={e => update('asset_date', e.target.value)} /></label>}
        </FormSection>

        {isPrinter && <FormSection icon={<Printer size={22} />} title="2. Printer Details" description="Record the printer attributes from the approved Printer Asset Register Excel.">
          <label>Brand <span>*</span><input required value={form.brand} onChange={e => update('brand', e.target.value)} placeholder="Epson / Canon / Konica Minolta" /></label>
          <label>Model <span>*</span><input required value={form.model} onChange={e => update('model', e.target.value)} placeholder="L3250 / bizhub C258" /></label>
          <label>Serial Number<input value={form.serial_number} onChange={e => update('serial_number', e.target.value)} placeholder="May be blank when not available" /></label>
          <label>Connection Type<input value={form.connection_type} onChange={e => update('connection_type', e.target.value)} placeholder="WiFi/USB / LAN/USB" /></label>
        </FormSection>}

        {isExternalHdd && <>
          <FormSection icon={<Database size={22} />} title="2. External HDD Details" description="Record only the attributes from the External HDD Asset Register Excel.">
            <label>Brand <span>*</span><input required value={form.brand} onChange={e => update('brand', e.target.value)} placeholder="Seagate / WD / Toshiba" /></label>
            <label>Capacity <span>*</span><input required value={form.capacity} onChange={e => update('capacity', e.target.value)} placeholder="1 TB / 2 TB / 10 TB" /></label>
            <label>Serial Number <span>*</span><input required value={form.serial_number} onChange={e => update('serial_number', e.target.value)} placeholder="Manufacturer serial number" /></label>
            <label>Ownership <span>*</span><select required value={form.ownership} onChange={e => update('ownership', e.target.value)}><option value="NakshaTech">NakshaTech</option><option value="Client">Client</option></select></label>
          </FormSection>
          <FormSection icon={<UserRound size={22} />} title="3. Holder, Department and Project" description="Track where the External HDD is, who currently holds it, and the client/project context.">
            <div className="full-span form-guidance">Changing Current Holder, Department, Client, Project or Status creates a timestamped audit entry. This register tracks portable External HDDs only.</div>
            <label>Department<input value={form.department} onChange={e => update('department', e.target.value)} placeholder="Drone / Mapping / LiDAR / BIM" /></label>
            <label>Current Holder<input required={['in_use', 'issued', 'permanently_issued'].includes(form.status)} value={form.current_holder} onChange={e => update('current_holder', e.target.value)} placeholder="Department, employee or Client" /></label>
            <label>Client Name<input required={form.ownership === 'Client'} value={form.client_name} onChange={e => update('client_name', e.target.value)} placeholder="Client organization or blank" /></label>
            <label>Project ID<input value={form.project_id} onChange={e => update('project_id', e.target.value)} placeholder="PRJ-001 or blank" /></label>
          </FormSection>
        </>}

        {!isExternalHdd && <>
        <FormSection icon={<UserRound size={22} />} title={isPrinter ? '3. User, Department and Placement' : '2. User, Department and Placement'} description={isPrinter ? "Show the printer's assigned user, department and floor." : "Show who uses the system and the workstation where it is installed."}>
          <div className="full-span form-guidance">{assignedStatuses.has(form.status) ? (isPrinter ? 'Assigned printers require Department and either Assigned User or Floor / Location. Workstation Number is optional.' : 'This asset will be registered/kept as assigned. Enter Used By, Department and Workstation Number. Use the Asset Register Assign / Transfer action for later custody changes.') : (isPrinter ? 'An available printer must not have an assigned user. Department and floor may still be recorded for physical placement.' : 'Available means the asset is in company/IT custody, so Used By must be blank. To register it directly to an employee, change Status to Assigned / In Use and then enter the employee, department and workstation.')}</div>
          <label>{isPrinter ? 'Assigned User' : 'Used By'}<input required={assignedStatuses.has(form.status) && !isPrinter} value={form.used_by} onChange={e => update('used_by', e.target.value)} placeholder="Employee name" /></label>
          <label>Department<select required={assignedStatuses.has(form.status)} value={manualDepartmentEntry ? MANUAL_ENTRY_VALUE : form.department} onChange={e => { const value = e.target.value; if (value === MANUAL_ENTRY_VALUE) { setManualDepartmentEntry(true); update('department', '') } else { setManualDepartmentEntry(false); update('department', value) } }}><option value="">Select department</option>{!manualDepartmentEntry && form.department && !DEPARTMENT_OPTIONS.some(option => option === form.department) && <option value={form.department}>Current legacy value — {form.department}</option>}{DEPARTMENT_OPTIONS.map(option => <option key={option} value={option}>{option}</option>)}<option value={MANUAL_ENTRY_VALUE}>Other / Manual Entry</option></select>{manualDepartmentEntry && <input autoFocus required={assignedStatuses.has(form.status)} value={form.department} onChange={e => update('department', e.target.value)} placeholder="Enter custom department" />}</label>
        </FormSection>
        </>}

        {!isStandaloneAsset && <FormSection icon={<Boxes size={22} />} title="3. Connected Components" description="Record the current active component tags. Old-to-new changes are captured through Work Records → Component Replacement.">
          <label>Monitor Asset Tag(s)<input value={form.monitor_asset_tags} onChange={e => update('monitor_asset_tags', e.target.value)} placeholder="Example: 7102, 7103" /></label>
          <label>Mouse Asset Tag<input value={form.mouse_asset_tag} onChange={e => update('mouse_asset_tag', e.target.value)} placeholder="Example: 7349" /></label>
          <label>Keyboard Asset Tag<input value={form.keyboard_asset_tag} onChange={e => update('keyboard_asset_tag', e.target.value)} placeholder="Example: 6120" /></label>
          <div className="form-info-card"><strong>Replacement rule</strong><span>The Asset Register stores only current active tags. Separate replacement history stores old tag → new tag.</span></div>
        </FormSection>}

        {!isStandaloneAsset && <FormSection icon={<HardDrive size={22} />} title="4. Hardware Configuration" description="Record the current processor, memory, drives and graphics configuration installed in this CPU or laptop.">
          <label>Processor<input value={form.processor} onChange={e => update('processor', e.target.value)} placeholder="Intel Core i5 12th Gen" /></label>
          <label>Memory in GB<input value={form.memory_gb} onChange={e => update('memory_gb', e.target.value)} placeholder="16 GB" /></label>
          <label>SSD<input value={form.ssd} onChange={e => update('ssd', e.target.value)} placeholder="512 GB" /></label>
          <label>HDD<input value={form.hdd} onChange={e => update('hdd', e.target.value)} placeholder="1 TB" /></label>
          <label className="full-span">Graphics Card (GC)<input value={form.graphics_card} onChange={e => update('graphics_card', e.target.value)} placeholder="Integrated / NVIDIA / AMD / model and serial" /></label>
        </FormSection>}

        {!isStandaloneAsset && <FormSection icon={<Network size={22} />} title="5. Network and Software" description="Keep the latest live network and software configuration for this CPU tag and workstation.">
          <label>Network Type<select value={form.network_type} onChange={e => update('network_type', e.target.value)}><option>DHCP</option><option>STATIC</option><option>Not Connected</option></select></label>
          <label>IP Address<input value={form.ip_address} onChange={e => update('ip_address', e.target.value)} placeholder="192.168.1.100" /></label>
          <label>MAC Address<input value={form.mac_address} onChange={e => update('mac_address', e.target.value)} placeholder="AA:BB:CC:DD:EE:01" /></label>
          <label>Operating System<input value={form.operating_system} onChange={e => update('operating_system', e.target.value)} placeholder="Windows 11 Pro" /></label>
          <label className="full-span">Antivirus<input value={form.antivirus} onChange={e => update('antivirus', e.target.value)} placeholder="Product / enabled status / expiry" /></label>
        </FormSection>}

        <FormSection
          icon={isExternalHdd ? <Database size={22} /> : <CircleDollarSign size={22} />}
          title={isPrinter ? '4. Printer Remarks and Audit' : isExternalHdd ? '4. External HDD Remarks and Audit' : '6. Financial, Approval and Permanent Notes'}
          description={isPrinter
            ? 'Keep the Printer Asset Register remarks current. User and date/time are captured automatically.'
            : isExternalHdd
              ? 'Keep the External HDD register note current. Every holder, project and status edit is timestamped.'
              : 'Record cost and approval. Asset Master Remarks are permanent live-register notes and should not be used for a one-month activity comment.'}
        >
          {!isStandaloneAsset && <label>Price (₹)<input type="number" min="0" step="0.01" value={form.price} onChange={e => update('price', e.target.value)} placeholder="65000" /></label>}
          {!isStandaloneAsset && <label>Approved By<input value={form.approved_by} onChange={e => update('approved_by', e.target.value)} placeholder="Manager / approver" /></label>}
          <div className="form-info-card"><strong>Performed By</strong><span>{user?.full_name || 'Logged-in user'} — automatic from login</span></div>
          <div className="form-info-card"><strong>Audit behavior</strong><span>{isExternalHdd ? 'Holder, ownership, client, project, department and status changes are stored in the asset timeline.' : 'Every later edit, assignment, return, work record and replacement is written to the asset timeline.'}</span></div>
          <label className="full-span">{isPrinter ? 'Printer Remarks' : isExternalHdd ? 'External HDD Remarks' : 'Asset Master Remarks — Permanent'}<textarea value={form.remarks} onChange={e => update('remarks', e.target.value)} rows={5} placeholder={isPrinter ? 'Printer condition, assignment or permanent operational note' : isExternalHdd ? 'Usage, custody, transfer or project note' : 'Permanent condition, ownership or warranty note. This remains until intentionally edited.'} /><small>{isPrinter ? 'This value appears in the dedicated Printer Excel export.' : isExternalHdd ? 'This value appears in the dedicated External HDD Excel export.' : 'Do not enter a monthly activity comment here. Use Edit Activity Remarks below.'}</small></label>
        </FormSection>

        {isEdit && <FormSection icon={<History size={22} />} title={isPrinter || isExternalHdd ? '5. Monthly Edit Activity Details' : '7. Monthly Edit Activity Details'} description="Explain this specific edit. Its activity remark stays only with this audit entry and selected reporting month; it does not carry into later months.">
          <label className="full-span">Reason for Edit (Optional)<input value={auditReason} onChange={event => setAuditReason(event.target.value)} placeholder="Example: Employee transfer, inventory correction, network update or approved hardware change" /></label>
          <label className="full-span">Edit Activity Remarks — This Month Only (Optional)<textarea rows={3} value={auditRemarks} onChange={event => setAuditRemarks(event.target.value)} placeholder="Approval reference, ticket number or explanation for this activity only" /></label>
          <div className="full-span asset-change-preview">
            <div><strong>{changedFields.length}</strong><span>field{changedFields.length === 1 ? '' : 's'} changed</span></div>
            <p>{changedFields.length ? changedFields.map(field => fieldLabels[field]).join(' · ') : 'Change any field above to create an audit entry.'}</p>
            <small>Effective reporting month: {monthLabel(selectedMonth)} · Changed by {user?.full_name || 'logged-in user'} · Actual date and time are generated by the server in Asia/Kolkata timezone.</small>
          </div>
        </FormSection>}

        <section className="asset-form-review panel">
          <div><ShieldCheck size={24} /><div><h2>Final Review</h2><p>{isPrinter ? 'Confirm the dedicated Printer Excel attributes before saving.' : isExternalHdd ? 'Confirm the dedicated External HDD register attributes before saving.' : 'Confirm the CPU / Asset Tag and Workstation first. The downloaded Asset Register Excel will contain the latest values entered here.'}</p></div></div>
          <dl>
            {isPrinter ? <>
              <div><dt>Printer Asset ID</dt><dd>{form.cpu_asset_tag || 'Not entered'}</dd></div>
              <div><dt>Brand / Model</dt><dd>{[form.brand, form.model].filter(Boolean).join(' · ') || 'Not recorded'}</dd></div>
              <div><dt>Serial Number</dt><dd>{form.serial_number || 'Not recorded'}</dd></div>
              <div><dt>Connection</dt><dd>{form.connection_type || 'Not recorded'}</dd></div>
              <div><dt>Assigned User</dt><dd>{form.used_by || 'Unassigned'}</dd></div>
              <div><dt>Department</dt><dd>{form.department || 'Not recorded'}</dd></div>
              <div><dt>Floor / Location</dt><dd>{form.location || 'Not recorded'}</dd></div>
              <div><dt>Status</dt><dd>{form.status.replaceAll('_', ' ')}</dd></div>
            </> : isExternalHdd ? <>
              <div><dt>External HDD Asset ID</dt><dd>{form.cpu_asset_tag || 'Not entered'}</dd></div>
              <div><dt>Brand / Capacity</dt><dd>{[form.brand, form.capacity].filter(Boolean).join(' · ') || 'Not recorded'}</dd></div>
              <div><dt>Serial Number</dt><dd>{form.serial_number || 'Not recorded'}</dd></div>
              <div><dt>Ownership</dt><dd>{form.ownership || 'Not recorded'}</dd></div>
              <div><dt>Department</dt><dd>{form.department || 'Not recorded'}</dd></div>
              <div><dt>Client / Project</dt><dd>{[form.client_name, form.project_id].filter(Boolean).join(' · ') || 'Internal / not linked'}</dd></div>
              <div><dt>Current Holder</dt><dd>{form.current_holder || 'Not recorded'}</dd></div>
              <div><dt>Status</dt><dd>{form.status.replaceAll('_', ' ')}</dd></div>
            </> : <>
              <div><dt>CPU / Asset Tag</dt><dd>{form.cpu_asset_tag || 'Not entered'}</dd></div>
              <div><dt>Workstation</dt><dd>{form.workstation_no || 'Not entered'}</dd></div>
              <div><dt>Used By</dt><dd>{form.used_by || 'Unassigned'}</dd></div>
              <div><dt>Department</dt><dd>{form.department || 'Not recorded'}</dd></div>
              <div><dt>Current Components</dt><dd>{[form.monitor_asset_tags && `Monitor ${form.monitor_asset_tags}`, form.mouse_asset_tag && `Mouse ${form.mouse_asset_tag}`, form.keyboard_asset_tag && `Keyboard ${form.keyboard_asset_tag}`].filter(Boolean).join(' · ') || 'Not recorded'}</dd></div>
            </>}
          </dl>
        </section>

        <div className="asset-form-sticky-actions">
          <button type="button" className="secondary-button" onClick={() => navigate(returnPath)}><ArrowLeft size={17} /> Cancel</button>
          <span><CheckCircle2 size={17} /> {isEdit ? `${changedFields.length} changed fields · user/date/time tracked` : isPrinter ? 'Dedicated Printer Excel fields · complete audit trail' : isExternalHdd ? 'External HDD-only fields · holder and project audit trail' : 'One page · all Excel fields · complete audit trail'}</span>
          <button className="primary-button" disabled={busy}><Save size={17} /> {busy ? (isPrinter ? 'Saving Printer…' : isExternalHdd ? 'Saving External HDD…' : 'Saving Asset…') : isEdit ? 'Save Changes' : isPrinter ? 'Save Printer' : isExternalHdd ? 'Save External HDD' : 'Save Asset'}</button>
        </div>
      </form>
    </>
  )
}
