import { Save } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import type { DroneSurveyAsset } from '../../../types'

const empty = {
  asset_name: '', category: 'Other', subcategory: '', manufacturer: '', model_number: '', serial_number: '', imported_equipment_id: '', quantity: 1,
  unit_of_measure: '', tracking_type: 'serialized_asset', current_status: 'available', working_condition: '', current_custodian: '', current_location: '',
  calibration_required: 'NA', maintenance_required: 'YES', technical_frequency: '', responsible_function: 'Drone Dept', equipment_tolerance: '', remarks: '', is_telemetry_capable: false,
}

export function DroneAssetFormPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [form, setForm] = useState(empty)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!id) return
    void apiFetch<DroneSurveyAsset>(`/drone/assets/${id}`).then(asset => setForm({
      ...empty,
      asset_name: asset.asset_name, category: asset.category, subcategory: asset.subcategory || '', manufacturer: asset.manufacturer || '', model_number: asset.model_number || '',
      serial_number: asset.serial_number || '', imported_equipment_id: asset.imported_equipment_id || '', quantity: asset.quantity, unit_of_measure: asset.unit_of_measure || '',
      tracking_type: asset.tracking_type, current_status: asset.current_status, working_condition: asset.working_condition || '', current_custodian: asset.current_custodian || '',
      current_location: asset.current_location || '', calibration_required: asset.calibration_required || '', maintenance_required: asset.maintenance_required || '',
      technical_frequency: asset.technical_frequency || '', responsible_function: asset.responsible_function || '', equipment_tolerance: asset.equipment_tolerance || '', remarks: asset.remarks || '',
      is_telemetry_capable: asset.is_telemetry_capable,
    })).catch(err => setError(err.message))
  }, [id])

  const set = (field: keyof typeof empty, value: string | number | boolean) => setForm(current => ({ ...current, [field]: value }))
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setSaving(true); setError('')
    try {
      const result = await apiFetch<DroneSurveyAsset>(id ? `/drone/assets/${id}` : '/drone/assets', {
        method: id ? 'PATCH' : 'POST',
        body: JSON.stringify({ ...form, quantity: Number(form.quantity), associated_people: form.current_custodian ? [form.current_custodian] : [] }),
      })
      navigate(`/drone/assets/${result.id}`)
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to save asset') }
    finally { setSaving(false) }
  }

  return (
    <>
      <DashboardHeader eyebrow="DRONE ASSET MASTER" title={id ? 'Edit Drone / Survey Asset' : 'Add Drone / Survey Asset'} description="Use this form for future drones, DGPS units, batteries, cameras, HDDs and equipment that are not coming through the monthly workbook." actions={<Link className="secondary-button" to="/drone/assets">Cancel</Link>} />
      {error && <div className="error-message">{error}</div>}
      <form className="panel full-page-form" onSubmit={submit}>
        <section className="form-section"><div className="form-section-heading"><span>1</span><div><h2>Permanent identity</h2><p>The system creates a unique NakshaTech asset tag automatically.</p></div></div><div className="form-grid drone-asset-identity-grid">
          <label><span>Equipment Name *</span><input required placeholder="Enter equipment name" value={form.asset_name} onChange={event => set('asset_name', event.target.value)} /></label>
          <label><span>Category *</span><select value={form.category} onChange={event => set('category', event.target.value)}><option>Drone</option><option>Survey Equipment</option><option>Battery</option><option>Camera / Sensor</option><option>Controller</option><option>Data Storage</option><option>Memory Card</option><option>Connectivity</option><option>Power / Cable</option><option>Accessory</option><option>Other</option></select></label>
          <label><span>Manufacturer</span><input placeholder="Enter manufacturer" value={form.manufacturer} onChange={event => set('manufacturer', event.target.value)} /></label>
          <label><span>Model Number</span><input placeholder="Enter model number" value={form.model_number} onChange={event => set('model_number', event.target.value)} /></label>
          <label><span>Serial Number</span><input placeholder="Enter serial number" value={form.serial_number} onChange={event => set('serial_number', event.target.value)} /></label>
          <label><span>Imported Equipment ID</span><input placeholder="Enter imported equipment ID" value={form.imported_equipment_id} onChange={event => set('imported_equipment_id', event.target.value)} /></label>
          <label><span>Tracking Type</span><select value={form.tracking_type} onChange={event => set('tracking_type', event.target.value)}><option value="serialized_asset">Serialized asset</option><option value="quantity_asset">Quantity-managed asset</option><option value="kit_component">Kit component</option><option value="data_delivery_device">Data delivery device</option></select></label>
          <label><span>Quantity</span><input type="number" min="0" step="0.01" value={form.quantity} onChange={event => set('quantity', Number(event.target.value))} /></label>
        </div></section>
        <section className="form-section"><div className="form-section-heading"><span>2</span><div><h2>Current operational state</h2><p>Project assignments and movements will later update these values through controlled transactions.</p></div></div><div className="form-grid drone-asset-state-grid">
          <label><span>Status</span><select value={form.current_status} onChange={event => set('current_status', event.target.value)}><option value="available">Available</option><option value="reserved">Reserved</option><option value="assigned_to_employee">Assigned to employee</option><option value="deployed_to_project">Deployed to project</option><option value="in_transit">In transit</option><option value="under_maintenance">Under maintenance</option><option value="sent_for_service">Sent for service</option><option value="under_calibration">Under calibration</option><option value="pending_verification">Pending verification</option><option value="missing">Missing</option><option value="damaged">Damaged</option><option value="retired">Retired</option></select></label>
          <label><span>Working Condition</span><input placeholder="Enter working condition" value={form.working_condition} onChange={event => set('working_condition', event.target.value)} /></label>
          <label><span>Current Custodian</span><input placeholder="Enter current custodian" value={form.current_custodian} onChange={event => set('current_custodian', event.target.value)} /></label>
          <label><span>Current Location</span><input placeholder="Enter current location" value={form.current_location} onChange={event => set('current_location', event.target.value)} /></label>
          <label className="checkbox-field"><input type="checkbox" checked={form.is_telemetry_capable} onChange={event => set('is_telemetry_capable', event.target.checked)} /><span>Telemetry-capable flight drone</span></label>
        </div></section>
        <section className="form-section"><div className="form-section-heading"><span>3</span><div><h2>Maintenance and technical details</h2><p>Technical frequency is kept separate from calibration interval.</p></div></div><div className="form-grid drone-asset-technical-grid">
          <label><span>Calibration Required</span><select value={form.calibration_required} onChange={event => set('calibration_required', event.target.value)}><option value="NA">Not Applicable</option><option value="YES">Yes</option><option value="NO">No</option></select></label>
          <label><span>Maintenance Required</span><select value={form.maintenance_required} onChange={event => set('maintenance_required', event.target.value)}><option value="YES">Yes</option><option value="NO">No</option><option value="NA">Not Applicable</option></select></label>
          <label><span>Technical Frequency</span><input value={form.technical_frequency} onChange={event => set('technical_frequency', event.target.value)} placeholder="20Hz / 2.4GHz" /></label>
          <label><span>Responsible Function</span><input placeholder="Drone Dept" value={form.responsible_function} onChange={event => set('responsible_function', event.target.value)} /></label>
          <label className="full-width"><span>Equipment Tolerance</span><textarea rows={3} placeholder="Enter equipment tolerance" value={form.equipment_tolerance} onChange={event => set('equipment_tolerance', event.target.value)} /></label>
          <label className="full-width"><span>Remarks</span><textarea rows={3} placeholder="Enter remarks" value={form.remarks} onChange={event => set('remarks', event.target.value)} /></label>
        </div></section>
        <div className="sticky-form-actions"><Link className="secondary-button" to="/drone/assets">Cancel</Link><button className="primary-button" disabled={saving}><Save size={17} /> {saving ? 'Saving…' : 'Save Asset'}</button></div>
      </form>
    </>
  )
}
