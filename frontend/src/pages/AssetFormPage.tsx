import {
  ArrowLeft,
  Boxes,
  CheckCircle2,
  CircleDollarSign,
  Cpu,
  HardDrive,
  Network,
  Save,
  ShieldCheck,
  UserRound,
} from 'lucide-react'
import { FormEvent, ReactNode, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { DashboardHeader } from '../components/DashboardHeader'
import { useAuth } from '../context/AuthContext'
import { apiFetch } from '../lib/api'
import type { Asset } from '../types'

const statusOptions = [
  'available', 'assigned', 'in_use', 'wfh', 'field_deployment', 'under_inspection', 'repair',
  'replacement_pending', 'replaced', 'damaged', 'beyond_repair', 'returned', 'missing', 'retired',
  'for_parts', 'disposal_pending', 'disposed',
]
const assignedStatuses = new Set(['assigned', 'in_use', 'wfh', 'field_deployment'])

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

function emptyAssetForm(): AssetForm {
  return {
    device_type: 'Computer', status: 'available', used_by: '', department: '', workstation_no: '',
    cpu_asset_tag: '', monitor_asset_tags: '', mouse_asset_tag: '', keyboard_asset_tag: '',
    system_name: '', processor: '', memory_gb: '', ssd: '', hdd: '', ip_address: '', mac_address: '',
    graphics_card: '', operating_system: '', antivirus: '', network_type: 'DHCP', approved_by: '',
    price: '', remarks: '', asset_date: new Date().toISOString().slice(0, 10), location: 'Head Office',
    work_mode: 'office',
  }
}

function formFromAsset(asset: Asset): AssetForm {
  return {
    device_type: asset.device_type || 'Computer', status: asset.status || 'available',
    used_by: asset.used_by || '', department: asset.department || '', workstation_no: asset.workstation_no || '',
    cpu_asset_tag: asset.cpu_asset_tag || '', monitor_asset_tags: asset.monitor_asset_tags || '',
    mouse_asset_tag: asset.mouse_asset_tag || '', keyboard_asset_tag: asset.keyboard_asset_tag || '',
    system_name: asset.system_name || '', processor: asset.processor || '', memory_gb: asset.memory_gb || '',
    ssd: asset.ssd || '', hdd: asset.hdd || '', ip_address: asset.ip_address || '',
    mac_address: asset.mac_address || '', graphics_card: asset.graphics_card || '',
    operating_system: asset.operating_system || '', antivirus: asset.antivirus || '',
    network_type: asset.network_type || 'DHCP', approved_by: asset.approved_by || '',
    price: asset.price === undefined || asset.price === null ? '' : String(asset.price), remarks: asset.remarks || '',
    asset_date: asset.asset_date || '', location: asset.location || 'Head Office', work_mode: asset.work_mode || 'office',
  }
}

function payloadFromForm(form: AssetForm) {
  return {
    ...form,
    price: form.price === '' ? null : Number(form.price),
    asset_date: form.asset_date || null,
    used_by: form.used_by || null,
    department: form.department || null,
    workstation_no: form.workstation_no || null,
    cpu_asset_tag: form.cpu_asset_tag || null,
    monitor_asset_tags: form.monitor_asset_tags || null,
    mouse_asset_tag: form.mouse_asset_tag || null,
    keyboard_asset_tag: form.keyboard_asset_tag || null,
    system_name: form.system_name || null,
    processor: form.processor || null,
    memory_gb: form.memory_gb || null,
    ssd: form.ssd || null,
    hdd: form.hdd || null,
    ip_address: form.ip_address || null,
    mac_address: form.mac_address || null,
    graphics_card: form.graphics_card || null,
    operating_system: form.operating_system || null,
    antivirus: form.antivirus || null,
    network_type: form.network_type || null,
    approved_by: form.approved_by || null,
    remarks: form.remarks || null,
    location: form.location || null,
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
  const { user } = useAuth()
  const [form, setForm] = useState<AssetForm>(emptyAssetForm())
  const [assetCode, setAssetCode] = useState('Generated automatically after save')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(isEdit)
  const [error, setError] = useState('')
  const [validationErrors, setValidationErrors] = useState<string[]>([])

  useEffect(() => {
    if (!id) return
    void (async () => {
      try {
        const asset = await apiFetch<Asset>(`/assets/${id}`)
        setForm(formFromAsset(asset))
        setAssetCode(asset.asset_code)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unable to load asset')
      } finally {
        setLoading(false)
      }
    })()
  }, [id])

  const primaryIdentity = useMemo(() => {
    const cpu = form.cpu_asset_tag.trim() || 'CPU tag not entered'
    const ws = form.workstation_no.trim() || 'Workstation not entered'
    return `${cpu} / ${ws}`
  }, [form.cpu_asset_tag, form.workstation_no])

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
    if (!form.cpu_asset_tag.trim()) errors.push('CPU / Physical Asset Tag is required.')
    if (!form.device_type.trim()) errors.push('Device Type is required.')
    if (assignedStatuses.has(form.status)) {
      if (!form.used_by.trim()) errors.push('Used By is required for assigned or in-use assets.')
      if (!form.department.trim()) errors.push('Department is required for assigned or in-use assets.')
      if (!form.workstation_no.trim()) errors.push('Workstation Number is required for assigned or in-use assets.')
    }
    if (form.status === 'available' && form.used_by.trim()) {
      errors.push('Available assets cannot have an employee. Use Assign / Transfer after registration.')
    }
    if (form.network_type.toLowerCase().includes('static') && !form.ip_address.trim()) {
      errors.push('Static network type requires an IP Address.')
    }
    if (form.price && Number.isNaN(Number(form.price))) errors.push('Price must be a valid number.')
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
      const saved = await apiFetch<Asset>(isEdit ? `/assets/${id}` : '/assets', {
        method: isEdit ? 'PATCH' : 'POST',
        body: JSON.stringify(payloadFromForm(form)),
      })
      navigate('/assets', {
        replace: true,
        state: {
          message: isEdit
            ? `${saved.asset_code} updated successfully.`
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
        title={isEdit ? `Edit ${assetCode}` : 'Add IT Asset'}
        description="Complete one full form. CPU / Physical Asset Tag and Workstation Number identify the system used by the IT team."
        actions={<button className="secondary-button" onClick={() => navigate('/assets')}><ArrowLeft size={17} /> Back to Register</button>}
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
            <p>All employee, department, component, hardware, network, software, price and audit information is linked to this CPU tag and workstation.</p>
          </div>
          <div className="asset-system-reference"><small>Internal System Asset ID</small><strong>{assetCode}</strong></div>
        </section>

        <FormSection icon={<Cpu size={22} />} title="1. Asset Identity" description="Record the physical asset and where it is placed. These fields appear first in daily IT searches.">
          <label>CPU / Physical Asset Tag <span>*</span><input autoFocus required value={form.cpu_asset_tag} onChange={e => update('cpu_asset_tag', e.target.value)} placeholder="Example: 3953" /></label>
          <label>Workstation Number<input value={form.workstation_no} onChange={e => update('workstation_no', e.target.value)} placeholder="Example: NW045 / 2nd Floor" /></label>
          <label>Device Type<select value={form.device_type} onChange={e => update('device_type', e.target.value)}><option>Computer</option><option>Laptop</option><option>Smartphone</option><option>Printer</option><option>Server</option><option>Network Device</option><option>Other</option></select></label>
          <label>Status<select value={form.status} onChange={e => update('status', e.target.value)}>{statusOptions.map(item => <option key={item} value={item}>{item.replaceAll('_', ' ')}</option>)}</select></label>
          <label>System Name<input value={form.system_name} onChange={e => update('system_name', e.target.value)} placeholder="Windows computer name" /></label>
          <label>Location<input value={form.location} onChange={e => update('location', e.target.value)} placeholder="Head Office / floor / branch" /></label>
          <label>Work Mode<select value={form.work_mode} onChange={e => update('work_mode', e.target.value)}><option value="office">Office</option><option value="wfh">Work From Home</option><option value="field">Field</option></select></label>
          <label>Asset / Record Date<input type="date" value={form.asset_date} onChange={e => update('asset_date', e.target.value)} /></label>
        </FormSection>

        <FormSection icon={<UserRound size={22} />} title="2. User, Department and Placement" description="Show who uses the system and the workstation where it is installed.">
          <div className="full-span form-guidance">{assignedStatuses.has(form.status) ? 'Assigned, in-use, WFH and field assets require Used By, Department and Workstation Number.' : 'An available asset must not have an employee. Its workstation may still be recorded for physical placement.'}</div>
          <label>Used By<input required={assignedStatuses.has(form.status)} value={form.used_by} onChange={e => update('used_by', e.target.value)} placeholder="Employee name" /></label>
          <label>Department<input required={assignedStatuses.has(form.status)} value={form.department} onChange={e => update('department', e.target.value)} placeholder="IT / LiDAR / Mapping / BIM" /></label>
        </FormSection>

        <FormSection icon={<Boxes size={22} />} title="3. Connected Components" description="Record the current active component tags. Old-to-new changes are captured through Work Records → Component Replacement.">
          <label>Monitor Asset Tag(s)<input value={form.monitor_asset_tags} onChange={e => update('monitor_asset_tags', e.target.value)} placeholder="Example: 7102, 7103" /></label>
          <label>Mouse Asset Tag<input value={form.mouse_asset_tag} onChange={e => update('mouse_asset_tag', e.target.value)} placeholder="Example: 7349" /></label>
          <label>Keyboard Asset Tag<input value={form.keyboard_asset_tag} onChange={e => update('keyboard_asset_tag', e.target.value)} placeholder="Example: 6120" /></label>
          <div className="form-info-card"><strong>Replacement rule</strong><span>The Asset Register stores only current active tags. Separate replacement history stores old tag → new tag.</span></div>
        </FormSection>

        <FormSection icon={<HardDrive size={22} />} title="4. Hardware Configuration" description="Record the current processor, memory, drives and graphics configuration installed in this CPU or laptop.">
          <label>Processor<input value={form.processor} onChange={e => update('processor', e.target.value)} placeholder="Intel Core i5 12th Gen" /></label>
          <label>Memory in GB<input value={form.memory_gb} onChange={e => update('memory_gb', e.target.value)} placeholder="16 GB" /></label>
          <label>SSD<input value={form.ssd} onChange={e => update('ssd', e.target.value)} placeholder="512 GB" /></label>
          <label>HDD<input value={form.hdd} onChange={e => update('hdd', e.target.value)} placeholder="1 TB" /></label>
          <label className="full-span">Graphics Card (GC)<input value={form.graphics_card} onChange={e => update('graphics_card', e.target.value)} placeholder="Integrated / NVIDIA / AMD / model and serial" /></label>
        </FormSection>

        <FormSection icon={<Network size={22} />} title="5. Network and Software" description="Keep the latest live network and software configuration for this CPU tag and workstation.">
          <label>Network Type<select value={form.network_type} onChange={e => update('network_type', e.target.value)}><option>DHCP</option><option>STATIC</option><option>Not Connected</option></select></label>
          <label>IP Address<input value={form.ip_address} onChange={e => update('ip_address', e.target.value)} placeholder="192.168.1.100" /></label>
          <label>MAC Address<input value={form.mac_address} onChange={e => update('mac_address', e.target.value)} placeholder="AA:BB:CC:DD:EE:01" /></label>
          <label>Operating System<input value={form.operating_system} onChange={e => update('operating_system', e.target.value)} placeholder="Windows 11 Pro" /></label>
          <label className="full-span">Antivirus<input value={form.antivirus} onChange={e => update('antivirus', e.target.value)} placeholder="Product / enabled status / expiry" /></label>
        </FormSection>

        <FormSection icon={<CircleDollarSign size={22} />} title="6. Financial, Approval and Notes" description="Record cost, approval and remarks while preserving who performed the entry automatically.">
          <label>Price (₹)<input type="number" min="0" step="0.01" value={form.price} onChange={e => update('price', e.target.value)} placeholder="65000" /></label>
          <label>Approved By<input value={form.approved_by} onChange={e => update('approved_by', e.target.value)} placeholder="Manager / approver" /></label>
          <div className="form-info-card"><strong>Performed By</strong><span>{user?.full_name || 'Logged-in user'} — automatic from login</span></div>
          <div className="form-info-card"><strong>Audit behavior</strong><span>Every later edit, assignment, return, work record and replacement is written to the asset timeline.</span></div>
          <label className="full-span">Remarks<textarea value={form.remarks} onChange={e => update('remarks', e.target.value)} rows={5} placeholder="Condition, ownership, warranty, reason, special notes…" /></label>
        </FormSection>

        <section className="asset-form-review panel">
          <div><ShieldCheck size={24} /><div><h2>Final Review</h2><p>Confirm the CPU / Asset Tag and Workstation first. The downloaded Asset Register Excel will contain the latest values entered here.</p></div></div>
          <dl>
            <div><dt>CPU / Asset Tag</dt><dd>{form.cpu_asset_tag || 'Not entered'}</dd></div>
            <div><dt>Workstation</dt><dd>{form.workstation_no || 'Not entered'}</dd></div>
            <div><dt>Used By</dt><dd>{form.used_by || 'Unassigned'}</dd></div>
            <div><dt>Department</dt><dd>{form.department || 'Not recorded'}</dd></div>
            <div><dt>Current Components</dt><dd>{[form.monitor_asset_tags && `Monitor ${form.monitor_asset_tags}`, form.mouse_asset_tag && `Mouse ${form.mouse_asset_tag}`, form.keyboard_asset_tag && `Keyboard ${form.keyboard_asset_tag}`].filter(Boolean).join(' · ') || 'Not recorded'}</dd></div>
          </dl>
        </section>

        <div className="asset-form-sticky-actions">
          <button type="button" className="secondary-button" onClick={() => navigate('/assets')}><ArrowLeft size={17} /> Cancel</button>
          <span><CheckCircle2 size={17} /> One page · all Excel fields · complete audit trail</span>
          <button className="primary-button" disabled={busy}><Save size={17} /> {busy ? 'Saving Asset…' : isEdit ? 'Save Changes' : 'Save Asset'}</button>
        </div>
      </form>
    </>
  )
}
