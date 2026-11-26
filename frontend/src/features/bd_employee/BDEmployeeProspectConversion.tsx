import { useEffect, useState, type FormEvent } from 'react'
import { Building2, CheckCircle2, FolderPlus, Link2, ShieldCheck, UserRoundCheck, X } from 'lucide-react'
import { apiFetch } from '../../lib/api'
import './bde-prospect-conversion.css'

type Prospect = {
  id: number
  company_name: string
  contact_person: string | null
  contact_email: string | null
  contact_phone: string | null
  service_interest: string | null
}
type ClientOption = { id: number; client_code: string; client_name: string }
type DepartmentOption = { code: string; label: string }
type Options = { converted: boolean; converted_client_id: number | null; clients: ClientOption[]; departments: DepartmentOption[] }
type Converted = { client_id: number; client_code: string; client_name: string; already_converted: boolean }
type ClientForm = {
  client_code: string; client_name: string; contact_person_name: string
  contact_person_email: string; contact_person_phone: string; primary_phone: string
  client_email: string; organization_email: string; task: string; address: string; country: string
  gst_number: string; client_type: 'client' | 'uav'
}

export function BDEmployeeProspectConversion({
  prospect, onClose, onConverted, onViewClient, onCreateProject,
}: {
  prospect: Prospect
  onClose: () => void
  onConverted: () => void
  onViewClient: (clientId: number) => void
  onCreateProject: (clientId: number) => void
}) {
  const [mode, setMode] = useState<'new' | 'existing'>('new')
  const [options, setOptions] = useState<Options | null>(null)
  const [existingId, setExistingId] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [converted, setConverted] = useState<Converted | null>(null)
  const [form, setForm] = useState<ClientForm>({
    client_code: '', client_name: prospect.company_name,
    contact_person_name: prospect.contact_person || '',
    contact_person_email: prospect.contact_email || '',
    contact_person_phone: prospect.contact_phone || '',
    primary_phone: prospect.contact_phone || '',
    client_email: prospect.contact_email || '', organization_email: '',
    task: prospect.service_interest || '', address: '', country: 'India',
    gst_number: '', client_type: 'client',
  })

  useEffect(() => {
    let cancelled = false
    void apiFetch<Options>(`/bd-employee/prospects/${prospect.id}/conversion-options`)
      .then(data => {
        if (cancelled) return
        setOptions(data)
        if (data.converted && data.converted_client_id) {
          const row = data.clients.find(c => c.id === data.converted_client_id)
          if (row) setConverted({client_id: row.id, client_code: row.client_code, client_name: row.client_name, already_converted: true})
        }
        const matching = data.clients.find(c => c.client_name.trim().toLowerCase() === prospect.company_name.trim().toLowerCase())
        if (matching) { setMode('existing'); setExistingId(String(matching.id)) }
      })
      .catch(exc => { if (!cancelled) setError(exc instanceof Error ? exc.message : 'Could not load client options') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [prospect.id, prospect.company_name])

  const setField = <K extends keyof ClientForm>(key: K, value: ClientForm[K]) => setForm(old => ({...old, [key]: value}))
  const exactMatches = options?.clients.filter(c => c.client_name.trim().toLowerCase() === prospect.company_name.trim().toLowerCase()) || []

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy || loading || converted) return
    setBusy(true); setError('')
    try {
      const data = await apiFetch<Converted>(`/bd-employee/prospects/${prospect.id}/convert`, {
        method: 'POST',
        body: JSON.stringify(mode === 'existing'
          ? {mode, existing_client_id: Number(existingId)}
          : {mode, client: {
            ...form, client_code: form.client_code.trim().toUpperCase(),
            client_name: prospect.company_name,
            contact_person_name: form.contact_person_name.trim(),
            primary_phone: form.primary_phone || null,
            client_email: form.client_email || null, organization_email: form.organization_email.trim() || null,
            contact_person_email: form.contact_person_email || null,
            contact_person_phone: form.contact_person_phone || null,
            task: form.task || null, address: form.address || null,
            gst_number: form.gst_number || null,
          }}),
      })
      setConverted(data)
      onConverted()
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Client conversion could not be completed')
    } finally { setBusy(false) }
  }

  return <div className="bde-modal-backdrop bde-convert-backdrop" onMouseDown={event => { if (event.target === event.currentTarget && !busy) onClose() }}>
    <section className="bde-convert-dialog" role="dialog" aria-modal="true" aria-label="Convert prospect to client">
      <header className="bde-convert-header">
        <div><span className="bde-convert-eyebrow">BUSINESS DEVELOPMENT · CLIENT REGISTRATION</span>
          <h2>{converted ? (converted.already_converted ? 'Client Already Linked' : mode === 'existing' ? 'Client Linked Successfully!' : 'Client Created Successfully!') : 'Convert Prospect to Client'}</h2></div>
        <button type="button" className="bde-convert-icon" onClick={onClose} disabled={busy} aria-label="Close"><X size={20}/></button>
      </header>
      {converted ? <div className="bde-convert-success">
        <CheckCircle2 size={52} color="#13a66c"/>
        <h3>{converted.already_converted ? 'Client Already Linked' : mode === 'existing' ? 'Client Linked Successfully!' : 'Client Registered Successfully!'}</h3>
        <p><strong>{converted.client_name}</strong> is linked to this prospect.</p>
        <small>Client ID: {converted.client_code} · Your original contact history is preserved.</small>
        <div className="bde-convert-actions center">
          <button className="bde-convert-primary" type="button" onClick={() => onCreateProject(converted.client_id)}><FolderPlus size={17}/> Create Project for this Client</button>
          <button className="bde-convert-secondary" type="button" onClick={() => onViewClient(converted.client_id)}><Building2 size={17}/> View Client Details</button>
        </div>
      </div> : <>
        <div className="bde-convert-info"><UserRoundCheck size={18}/> Prospect details are prefilled below. Enter the official Client ID and review the details before saving.</div>
        {error && <div className="bde-convert-error" role="alert">{error}</div>}
        {loading ? <p className="bde-convert-muted">Checking your existing BD clients…</p> : options?.converted ?
          <p className="bde-convert-muted">This prospect has already been converted. Contact your BD Manager if its linked client is unavailable.</p> :
          <form onSubmit={submit} className="bde-convert-form">
            <fieldset className="bde-convert-modes"><legend>Client Type</legend>
              <label><input type="radio" checked={mode === 'new'} onChange={() => setMode('new')}/> New Client</label>
              <label><input type="radio" checked={mode === 'existing'} onChange={() => setMode('existing')}/> Existing Client (Link)</label>
            </fieldset>
            {mode === 'new' ? <div className="bde-convert-grid">
              <label>Company / Client Name *<input value={form.client_name} disabled readOnly title="Same company as prospect" /></label>
              <label>Client ID / Code *<input required maxLength={32} value={form.client_code} onChange={e => setField('client_code', e.target.value.toUpperCase())} placeholder="Enter unique official Client ID" /></label>
              <label>Contact Person *<input required minLength={2} maxLength={255} value={form.contact_person_name} onChange={e => setField('contact_person_name', e.target.value)}/></label>
              <label>Phone / WhatsApp<input maxLength={40} value={form.contact_person_phone} onChange={e => setField('contact_person_phone', e.target.value)}/></label>
              <label>Contact Person Email ID<input type="email" maxLength={255} value={form.contact_person_email} onChange={e => setField('contact_person_email', e.target.value)}/></label>
              <label>Client Email ID<input type="email" maxLength={255} value={form.client_email} onChange={e => setField('client_email', e.target.value)}/></label>
              <label>Organization Email ID<input type="email" maxLength={255} value={form.organization_email} onChange={e => setField('organization_email', e.target.value)}/></label>
              <label>Primary Service ({options?.departments?.length || 0} departments)
                <select value={form.task} onChange={e => setField('task', e.target.value)}>
                  <option value="">Select primary department</option>
                  {form.task && !(options?.departments || []).some(dept => dept.label === form.task) &&
                    <option value={form.task}>{form.task} (existing prospect service)</option>}
                  {(options?.departments || []).map(dept =>
                    <option key={dept.code} value={dept.label}>{dept.label}</option>)}
                </select>
              </label>
              <label>Client Category<select value={form.client_type} onChange={e => setField('client_type', e.target.value as 'client' | 'uav')}><option value="client">Client</option><option value="uav">UAV</option></select></label>
              <label>Country<input required value={form.country} maxLength={100} onChange={e => setField('country', e.target.value)}/></label>
              <label>GST Number (optional)<input value={form.gst_number} maxLength={32} onChange={e => setField('gst_number', e.target.value.toUpperCase())}/></label>
              <label className="bde-convert-wide">Address<textarea rows={2} maxLength={3000} value={form.address} onChange={e => setField('address', e.target.value)}/></label>
            </div> : <div className="bde-convert-grid">
              <label className="bde-convert-wide">Select Your Existing Client *<select required value={existingId} onChange={e => setExistingId(e.target.value)}><option value="">Select an existing authorized BD client</option>{exactMatches.map(c => <option key={c.id} value={c.id}>{c.client_code} · {c.client_name}</option>)}</select></label>
              <p className="bde-convert-wide bde-convert-muted">Only clients already authorized for your BD Employee account are shown. The company name must match the prospect.</p>
            </div>}
            <div className="bde-convert-duplicate"><ShieldCheck size={18}/><div><strong>Duplicate Check</strong>
              <p>{exactMatches.length > 0 ? `${exactMatches.length} matching client(s) found in your register. Choose Existing Client (Link) to avoid duplicates.` : 'No same-name client found in your accessible BD client register. The server checks all client names and IDs again before creation.'}</p>
            </div></div>
            <footer className="bde-convert-actions">
              <button type="button" className="bde-convert-secondary" onClick={onClose}>Cancel</button>
              <button type="submit" className="bde-convert-primary" disabled={busy || (mode === 'existing' ? !existingId : exactMatches.length > 0)}>
                {busy ? 'Saving…' : mode === 'new' ? 'Create Client' : 'Link Client'}
              </button>
            </footer>
          </form>}
      </>}
    </section>
  </div>
}
