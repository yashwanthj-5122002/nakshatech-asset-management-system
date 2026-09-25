import { ArrowRightLeft, ClipboardCheck, PackageCheck, RotateCcw, Send, UserCheck } from 'lucide-react'
import { FormEvent, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import type { DroneAssetListResponse, DroneKit, DroneOperation, DroneOperationItem, DroneProject, DroneSurveyAsset } from '../../../types'

type OperationTab = 'dispatch' | 'return' | 'transfer' | 'assign'
type SelectedItem = { asset_id?: number; kit_id?: number; quantity: number }
type ReturnState = { checked: boolean; quantity: number; condition: string; next_status: string; remarks: string }

const today = new Date().toISOString().slice(0, 10)

function itemKey(item: SelectedItem) {
  return item.asset_id ? `asset-${item.asset_id}` : `kit-${item.kit_id}`
}

export function DroneOperationsPage() {
  const [searchParams] = useSearchParams()
  const [tab, setTab] = useState<OperationTab>('dispatch')
  const [projects, setProjects] = useState<DroneProject[]>([])
  const [assets, setAssets] = useState<DroneSurveyAsset[]>([])
  const [kits, setKits] = useState<DroneKit[]>([])
  const [operations, setOperations] = useState<DroneOperation[]>([])
  const [selected, setSelected] = useState<SelectedItem[]>([])
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [saving, setSaving] = useState(false)
  const [dispatchForm, setDispatchForm] = useState({ project_id: '', custodian: '', destination: '', dispatch_date: today, expected_return_date: '', purpose: '', condition: 'Working / flight ready', approved_by: '', remarks: '', allow_incomplete_kit: false, override_reason: '' })
  const [assignmentForm, setAssignmentForm] = useState({ project_id: '', custodian: '', location: '', assignment_date: today, expected_return_date: '', purpose: '', approved_by: '', remarks: '' })
  const [transferForm, setTransferForm] = useState({ to_project_id: '', to_custodian: '', destination: '', transfer_date: today, reason: '', approved_by: '', remarks: '' })
  const [returnOperationId, setReturnOperationId] = useState('')
  const [returnDate, setReturnDate] = useState(today)
  const [returnLocation, setReturnLocation] = useState('NakshaTech Head Office')
  const [receiver, setReceiver] = useState('Drone Store')
  const [returnRemarks, setReturnRemarks] = useState('')
  const [returnSelection, setReturnSelection] = useState<Record<number, ReturnState>>({})

  const load = async () => {
    setError('')
    try {
      const [projectRows, assetRows, kitRows, operationRows] = await Promise.all([
        apiFetch<DroneProject[]>('/drone/projects'),
        apiFetch<DroneAssetListResponse>('/drone/assets?limit=500'),
        apiFetch<DroneKit[]>('/drone/kits'),
        apiFetch<DroneOperation[]>('/drone/operations?limit=200'),
      ])
      setProjects(projectRows)
      setAssets(assetRows.items)
      setKits(kitRows)
      setOperations(operationRows)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load Drone operations')
    }
  }

  useEffect(() => { void load() }, [])
  useEffect(() => { const project = searchParams.get('project'); if (project) setDispatchForm(current => ({ ...current, project_id: project })) }, [searchParams])
  useEffect(() => { setSelected([]); setSearch(''); setSuccess(''); setError('') }, [tab])

  const availableAssets = useMemo(() => assets.filter(asset => ['available', 'reserved'].includes(asset.current_status) || (!asset.is_serialized && (asset.available_quantity || 0) > 0)), [assets])
  const availableKits = useMemo(() => kits.filter(kit => ['available', 'reserved'].includes(kit.current_status)), [kits])
  const transferableAssets = useMemo(() => assets.filter(asset => !['retired', 'disposed', 'missing'].includes(asset.current_status)), [assets])
  const transferableKits = useMemo(() => kits.filter(kit => !['retired', 'disposed', 'missing'].includes(kit.current_status)), [kits])
  const activeOperations = useMemo(() => operations.filter(operation => ['dispatch', 'assignment'].includes(operation.operation_type) && ['active', 'partial'].includes(operation.status)), [operations])
  const currentReturnOperation = activeOperations.find(operation => operation.id === Number(returnOperationId))

  const toggleSelection = (item: SelectedItem, defaultQuantity = 1) => {
    const key = itemKey(item)
    setSelected(current => current.some(row => itemKey(row) === key)
      ? current.filter(row => itemKey(row) !== key)
      : [...current, { ...item, quantity: defaultQuantity }])
  }

  const updateQuantity = (key: string, quantity: number) => {
    setSelected(current => current.map(row => itemKey(row) === key ? { ...row, quantity: Math.max(quantity, 0.01) } : row))
  }

  const filteredAssets = (tab === 'dispatch' || tab === 'assign' ? availableAssets : transferableAssets).filter(asset => {
    const text = `${asset.asset_tag} ${asset.asset_name} ${asset.serial_number || ''} ${asset.model_number || ''} ${asset.current_project || ''}`.toLowerCase()
    return text.includes(search.toLowerCase())
  })
  const filteredKits = (tab === 'dispatch' || tab === 'assign' ? availableKits : transferableKits).filter(kit => {
    const text = `${kit.kit_tag} ${kit.kit_name} ${kit.unit_number || ''} ${kit.current_project || ''}`.toLowerCase()
    return text.includes(search.toLowerCase())
  })

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(''); setSuccess('')
    if (selected.length === 0) { setError('Select at least one asset or kit.'); return }
    setSaving(true)
    try {
      let result: DroneOperation
      if (tab === 'dispatch') {
        result = await apiFetch<DroneOperation>('/drone/operations/dispatch', {
          method: 'POST',
          body: JSON.stringify({
            ...dispatchForm,
            project_id: Number(dispatchForm.project_id),
            expected_return_date: dispatchForm.expected_return_date || null,
            items: selected,
          }),
        })
      } else if (tab === 'assign') {
        result = await apiFetch<DroneOperation>('/drone/operations/assign', {
          method: 'POST',
          body: JSON.stringify({
            ...assignmentForm,
            project_id: assignmentForm.project_id ? Number(assignmentForm.project_id) : null,
            expected_return_date: assignmentForm.expected_return_date || null,
            items: selected,
          }),
        })
      } else {
        result = await apiFetch<DroneOperation>('/drone/operations/transfer', {
          method: 'POST',
          body: JSON.stringify({
            ...transferForm,
            to_project_id: transferForm.to_project_id ? Number(transferForm.to_project_id) : null,
            items: selected,
          }),
        })
      }
      setSuccess(`${result.operation_code} recorded successfully. All linked asset, project and work-record views were updated.`)
      setSelected([])
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to save Drone operation')
    } finally { setSaving(false) }
  }

  const submitReturn = async (event: FormEvent) => {
    event.preventDefault(); setError(''); setSuccess('')
    const items = (Object.entries(returnSelection) as Array<[string, ReturnState]>)
      .filter(([, value]) => value.checked)
      .map(([id, value]) => ({ operation_item_id: Number(id), quantity: value.quantity, condition: value.condition, next_status: value.next_status, remarks: value.remarks || null }))
    if (!returnOperationId || items.length === 0) { setError('Select an active dispatch and at least one item to return.'); return }
    setSaving(true)
    try {
      const result = await apiFetch<{ return_operation: DroneOperation; source_operation: DroneOperation }>('/drone/operations/return', {
        method: 'POST',
        body: JSON.stringify({ dispatch_operation_id: Number(returnOperationId), return_date: returnDate, receiver, return_location: returnLocation, remarks: returnRemarks, items }),
      })
      setSuccess(`${result.return_operation.operation_code} recorded. Source ${result.source_operation.operation_code} is now ${result.source_operation.status}.`)
      setReturnSelection({}); setReturnOperationId('')
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to record return')
    } finally { setSaving(false) }
  }

  const returnItems = currentReturnOperation?.items || []

  return <>
    <DashboardHeader
      eyebrow="CONTROLLED DRONE OPERATIONS"
      title="Dispatch, Return, Transfer & Assignment"
      description="Every transaction updates current custody, project allocation, movement history, work records and the live Drone dashboard in one controlled operation."
      meta={<>
        <span className="nk-meta-chip"><ArrowRightLeft size={14} /> Dispatch · Return · Transfer · Assign</span>
        <span className="nk-meta-chip"><ClipboardCheck size={14} /> Custody, project, movement and work records update together</span>
        <span className="nk-meta-chip"><UserCheck size={14} /> Every transaction recorded with its performer</span>
      </>}
    />
    <div className="operation-tab-bar">
      <button className={tab === 'dispatch' ? 'active' : ''} onClick={() => setTab('dispatch')}><Send size={17} /> Dispatch</button>
      <button className={tab === 'return' ? 'active' : ''} onClick={() => setTab('return')}><RotateCcw size={17} /> Return</button>
      <button className={tab === 'transfer' ? 'active' : ''} onClick={() => setTab('transfer')}><ArrowRightLeft size={17} /> Transfer</button>
      <button className={tab === 'assign' ? 'active' : ''} onClick={() => setTab('assign')}><UserCheck size={17} /> Assign</button>
    </div>
    {error && <div className="error-message">{error}</div>}
    {success && <div className="success-message">{success}</div>}

    {tab !== 'return' ? <form className="operations-layout" onSubmit={submit}>
      <section className="panel operation-form-card">
        <div className="panel-heading"><div><span className="section-kicker">{tab.toUpperCase()}</span><h2>{tab === 'dispatch' ? 'Dispatch to Project' : tab === 'assign' ? 'Assign to Employee / Custodian' : 'Transfer Custody or Project'}</h2></div><ClipboardCheck /></div>
        {tab === 'dispatch' && <div className="form-grid operation-form-grid">
          <label><span>Project *</span><select required value={dispatchForm.project_id} onChange={e => setDispatchForm({ ...dispatchForm, project_id: e.target.value })}><option value="">Select project</option>{projects.filter(p => !['closed','cancelled'].includes(p.status)).map(p => <option key={p.id} value={p.id}>{p.project_code} · {p.project_name}</option>)}</select></label>
          <label><span>Custodian *</span><input required value={dispatchForm.custodian} onChange={e => setDispatchForm({ ...dispatchForm, custodian: e.target.value })} placeholder="Employee / responsible person" /></label>
          <label><span>Destination *</span><input required value={dispatchForm.destination} onChange={e => setDispatchForm({ ...dispatchForm, destination: e.target.value })} placeholder="Project site / location" /></label>
          <label><span>Dispatch Date *</span><input required type="date" value={dispatchForm.dispatch_date} onChange={e => setDispatchForm({ ...dispatchForm, dispatch_date: e.target.value })} /></label>
          <label><span>Expected Return</span><input type="date" value={dispatchForm.expected_return_date} onChange={e => setDispatchForm({ ...dispatchForm, expected_return_date: e.target.value })} /></label>
          <label><span>Condition</span><input value={dispatchForm.condition} onChange={e => setDispatchForm({ ...dispatchForm, condition: e.target.value })} /></label>
          <label><span>Approved By</span><input value={dispatchForm.approved_by} onChange={e => setDispatchForm({ ...dispatchForm, approved_by: e.target.value })} placeholder="Drone manager / approver" /></label>
          <label className="wide"><span>Purpose *</span><textarea required value={dispatchForm.purpose} onChange={e => setDispatchForm({ ...dispatchForm, purpose: e.target.value })} placeholder="Survey purpose and field activity" /></label>
          <label className="wide"><span>Remarks</span><textarea value={dispatchForm.remarks} onChange={e => setDispatchForm({ ...dispatchForm, remarks: e.target.value })} /></label>
          <label className="checkbox-row wide"><input type="checkbox" checked={dispatchForm.allow_incomplete_kit} onChange={e => setDispatchForm({ ...dispatchForm, allow_incomplete_kit: e.target.checked })} /> Allow incomplete-kit override</label>
          {dispatchForm.allow_incomplete_kit && <label className="wide"><span>Override Reason *</span><textarea required value={dispatchForm.override_reason} onChange={e => setDispatchForm({ ...dispatchForm, override_reason: e.target.value })} /></label>}
        </div>}
        {tab === 'assign' && <div className="form-grid operation-form-grid">
          <label><span>Custodian *</span><input required value={assignmentForm.custodian} onChange={e => setAssignmentForm({ ...assignmentForm, custodian: e.target.value })} /></label>
          <label><span>Optional Project</span><select value={assignmentForm.project_id} onChange={e => setAssignmentForm({ ...assignmentForm, project_id: e.target.value })}><option value="">Employee custody only</option>{projects.filter(p => !['closed','cancelled'].includes(p.status)).map(p => <option key={p.id} value={p.id}>{p.project_name}</option>)}</select></label>
          <label><span>Location *</span><input required value={assignmentForm.location} onChange={e => setAssignmentForm({ ...assignmentForm, location: e.target.value })} /></label>
          <label><span>Assignment Date *</span><input required type="date" value={assignmentForm.assignment_date} onChange={e => setAssignmentForm({ ...assignmentForm, assignment_date: e.target.value })} /></label>
          <label><span>Expected Return</span><input type="date" value={assignmentForm.expected_return_date} onChange={e => setAssignmentForm({ ...assignmentForm, expected_return_date: e.target.value })} /></label>
          <label><span>Approved By</span><input value={assignmentForm.approved_by} onChange={e => setAssignmentForm({ ...assignmentForm, approved_by: e.target.value })} /></label>
          <label className="wide"><span>Purpose *</span><textarea required value={assignmentForm.purpose} onChange={e => setAssignmentForm({ ...assignmentForm, purpose: e.target.value })} /></label>
          <label className="wide"><span>Remarks</span><textarea value={assignmentForm.remarks} onChange={e => setAssignmentForm({ ...assignmentForm, remarks: e.target.value })} /></label>
        </div>}
        {tab === 'transfer' && <div className="form-grid operation-form-grid">
          <label><span>To Project</span><select value={transferForm.to_project_id} onChange={e => setTransferForm({ ...transferForm, to_project_id: e.target.value })}><option value="">No project</option>{projects.filter(p => !['closed','cancelled'].includes(p.status)).map(p => <option key={p.id} value={p.id}>{p.project_name}</option>)}</select></label>
          <label><span>To Custodian</span><input value={transferForm.to_custodian} onChange={e => setTransferForm({ ...transferForm, to_custodian: e.target.value })} /></label>
          <label><span>Destination *</span><input required value={transferForm.destination} onChange={e => setTransferForm({ ...transferForm, destination: e.target.value })} /></label>
          <label><span>Transfer Date *</span><input required type="date" value={transferForm.transfer_date} onChange={e => setTransferForm({ ...transferForm, transfer_date: e.target.value })} /></label>
          <label><span>Approved By</span><input value={transferForm.approved_by} onChange={e => setTransferForm({ ...transferForm, approved_by: e.target.value })} /></label>
          <label className="wide"><span>Reason *</span><textarea required value={transferForm.reason} onChange={e => setTransferForm({ ...transferForm, reason: e.target.value })} /></label>
          <label className="wide"><span>Remarks</span><textarea value={transferForm.remarks} onChange={e => setTransferForm({ ...transferForm, remarks: e.target.value })} /></label>
        </div>}
      </section>

      <section className="panel operation-picker-card">
        <div className="panel-heading"><div><span className="section-kicker">SELECT ITEMS</span><h2>Assets and Kits</h2></div><span className="count-chip">{selected.length} selected</span></div>
        <input className="operation-search" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search asset tag, equipment, serial, model or kit…" />
        <div className="operation-picker-list">
          {filteredKits.map(kit => {
            const key = `kit-${kit.id}`; const checked = selected.some(row => itemKey(row) === key)
            return <label className={`operation-picker-row ${checked ? 'selected' : ''}`} key={key}><input type="checkbox" checked={checked} onChange={() => toggleSelection({ kit_id: kit.id, quantity: 1 })} /><PackageCheck size={18} /><div><strong>{kit.kit_tag} · {kit.kit_name}</strong><span>{kit.readiness_percentage}% ready · {kit.component_count} components · {kit.current_status.replaceAll('_',' ')}</span></div></label>
          })}
          {filteredAssets.map(asset => {
            const key = `asset-${asset.id}`; const row = selected.find(item => itemKey(item) === key); const checked = Boolean(row)
            return <div className={`operation-picker-row ${checked ? 'selected' : ''}`} key={key}><label><input type="checkbox" checked={checked} onChange={() => toggleSelection({ asset_id: asset.id, quantity: 1 }, asset.is_serialized ? 1 : Math.min(asset.available_quantity ?? asset.quantity, 1))} /></label><div className="picker-asset-copy"><strong>{asset.asset_tag} · {asset.asset_name}</strong><span>{asset.serial_number || asset.model_number || 'No serial/model'} · Available {asset.available_quantity ?? asset.quantity} / {asset.quantity} · {asset.current_status.replaceAll('_',' ')}</span></div>{checked && <input className="quantity-input" type="number" min="0.01" step="0.01" max={asset.available_quantity ?? asset.quantity} value={row?.quantity || 1} disabled={asset.is_serialized} onChange={e => updateQuantity(key, Number(e.target.value))} />}</div>
          })}
          {filteredAssets.length === 0 && filteredKits.length === 0 && <div className="empty-state">No matching available items.</div>}
        </div>
        <button className="primary-button operation-submit" disabled={saving}>{saving ? 'Saving…' : tab === 'dispatch' ? 'Confirm Dispatch' : tab === 'assign' ? 'Confirm Assignment' : 'Confirm Transfer'}</button>
      </section>
    </form> : <form className="panel return-workflow" onSubmit={submitReturn}>
      <div className="panel-heading"><div><span className="section-kicker">RETURN / PARTIAL RETURN</span><h2>Receive Equipment</h2><p>Select an open dispatch or assignment, then choose all or only some items.</p></div><RotateCcw /></div>
      <div className="form-grid operation-form-grid return-header-grid">
        <label className="wide"><span>Active Dispatch / Assignment *</span><select required value={returnOperationId} onChange={e => { setReturnOperationId(e.target.value); setReturnSelection({}) }}><option value="">Select operation</option>{activeOperations.map(operation => <option key={operation.id} value={operation.id}>{operation.operation_code} · {operation.project || operation.to_custodian} · {operation.status}</option>)}</select></label>
        <label><span>Return Date *</span><input required type="date" value={returnDate} onChange={e => setReturnDate(e.target.value)} /></label>
        <label><span>Receiver</span><input value={receiver} onChange={e => setReceiver(e.target.value)} /></label>
        <label><span>Return Location *</span><input required value={returnLocation} onChange={e => setReturnLocation(e.target.value)} /></label>
        <label className="wide"><span>Remarks</span><textarea value={returnRemarks} onChange={e => setReturnRemarks(e.target.value)} /></label>
      </div>
      {currentReturnOperation && <div className="return-source-summary"><strong>{currentReturnOperation.operation_code}</strong><span>{currentReturnOperation.project || 'Employee assignment'} · Custodian: {currentReturnOperation.to_custodian || 'Not recorded'} · Expected: {currentReturnOperation.expected_return_date || 'Open'}</span></div>}
      <div className="return-items-list">
        {returnItems.filter(item => item.open_quantity > 0).map((item: DroneOperationItem) => {
          const state = returnSelection[item.id] || { checked: false, quantity: item.open_quantity, condition: 'Working', next_status: 'available', remarks: '' }
          return <div className={`return-item-row ${item.is_kit_component ? 'component' : ''}`} key={item.id}>
            <input type="checkbox" checked={state.checked} onChange={e => setReturnSelection(current => ({ ...current, [item.id]: { ...state, checked: e.target.checked } }))} />
            <div><strong>{item.kit_tag || item.asset_tag} · {item.kit_name || item.asset_name}</strong><span>{item.is_kit_component ? 'Kit component · ' : ''}Open quantity {item.open_quantity}</span></div>
            <input type="number" min="0.01" max={item.open_quantity} step="0.01" value={state.quantity} onChange={e => setReturnSelection(current => ({ ...current, [item.id]: { ...state, quantity: Number(e.target.value) } }))} />
            <input value={state.condition} onChange={e => setReturnSelection(current => ({ ...current, [item.id]: { ...state, condition: e.target.value } }))} placeholder="Condition" />
            <select value={state.next_status} onChange={e => setReturnSelection(current => ({ ...current, [item.id]: { ...state, next_status: e.target.value } }))}><option value="available">Available</option><option value="under_maintenance">Under Maintenance</option><option value="under_calibration">Under Calibration</option><option value="damaged">Damaged</option><option value="missing">Missing</option><option value="retired">Retired</option></select>
          </div>
        })}
        {currentReturnOperation && returnItems.filter(item => item.open_quantity > 0).length === 0 && <div className="empty-state">This operation has no open items.</div>}
      </div>
      <div className="form-actions"><button className="primary-button" disabled={saving}>{saving ? 'Saving…' : 'Confirm Return'}</button></div>
    </form>}

    <section className="panel operation-history-panel">
      <div className="panel-heading"><div><span className="section-kicker">RECENT OPERATIONS</span><h2>Dispatch, Return, Transfer & Assignment History</h2></div></div>
      <div className="operation-history-list">
        {operations.slice(0, 15).map(operation => <article key={operation.id}><div><strong>{operation.operation_code} · {operation.operation_type.replaceAll('_',' ')}</strong><span>{operation.project || operation.to_project || operation.to_custodian || 'No project/custodian'} · {operation.operation_date}</span></div><div><span className={`status ${operation.status}`}>{operation.status}</span><small>{operation.items.length} item records</small></div></article>)}
        {operations.length === 0 && <div className="empty-state">No Drone operations recorded yet.</div>}
      </div>
    </section>
  </>
}
