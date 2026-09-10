import {
  Building2,
  Cpu,
  Gauge,
  HardDrive,
  Keyboard,
  Monitor,
  MousePointer2,
  Paperclip,
  Search,
  Send,
  Upload,
  UserRound,
  X,
} from 'lucide-react'
import { type FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch } from '../../../lib/api'
import type {
  SupportTicket,
  TicketAsset,
  TicketAttachment,
  TicketCatalog,
  TicketComponentOption,
  TicketDepartment,
  TicketPriority,
} from '../../../types'

const departments: Array<{ value: TicketDepartment; label: string }> = [
  { value: 'it', label: 'IT Department' },
  { value: 'drone', label: 'Drone Department' },
  { value: 'software_team', label: 'Software Team' },
  { value: 'management', label: 'Management' },
]

const priorities: Array<{ value: TicketPriority; label: string; help: string }> = [
  { value: 'low', label: 'Low', help: 'Can wait without affecting normal work' },
  { value: 'medium', label: 'Moderate', help: 'Needs attention, but work can continue' },
  { value: 'high', label: 'High', help: 'Work is significantly affected' },
  { value: 'critical', label: 'Critical', help: 'Work or delivery is completely blocked' },
]

const emptyForm = {
  department: 'it' as TicketDepartment,
  reporting_manager_email: '',
  category: '',
  title: '',
  description: '',
  priority: 'medium' as TicketPriority,
  location: '',
}

const MIN_TICKET_DESCRIPTION_CHARACTERS = 10
const MAX_TICKET_IMAGES = 5
const MAX_TICKET_IMAGE_BYTES = 10 * 1024 * 1024
const SUPPORTED_TICKET_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp'])

interface DraftTicketAttachment {
  id: string
  file: File
  previewUrl: string
}

function formatAttachmentSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function assetPrimaryLabel(asset: TicketAsset): string {
  return asset.cpu_asset_tag || asset.asset_code
}

function componentTag(asset: TicketAsset, component: string): string | undefined {
  if (component === 'monitor') return asset.monitor_asset_tags
  if (component === 'mouse') return asset.mouse_asset_tag
  if (component === 'keyboard') return asset.keyboard_asset_tag
  if (['system', 'memory', 'storage', 'network', 'operating_system', 'software', 'login_account'].includes(component)) {
    return asset.cpu_asset_tag || asset.asset_code
  }
  return undefined
}

export function TicketCreatePage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [form, setForm] = useState(emptyForm)
  const [catalog, setCatalog] = useState<TicketCatalog>({ components: [] })
  const [catalogError, setCatalogError] = useState('')
  const [workstationNumber, setWorkstationNumber] = useState('')
  const [assetQuery, setAssetQuery] = useState('')
  const [assetResults, setAssetResults] = useState<TicketAsset[]>([])
  const [selectedAsset, setSelectedAsset] = useState<TicketAsset | null>(null)
  const [assetLoading, setAssetLoading] = useState(false)
  const [assetError, setAssetError] = useState('')
  const [componentCode, setComponentCode] = useState('')
  const [problemCode, setProblemCode] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [attachments, setAttachments] = useState<DraftTicketAttachment[]>([])
  const [attachmentError, setAttachmentError] = useState('')
  const [createdTicket, setCreatedTicket] = useState<SupportTicket | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const attachmentsRef = useRef<DraftTicketAttachment[]>([])

  const selectedComponent = useMemo(
    () => catalog.components.find(item => item.code === componentCode) || null,
    [catalog.components, componentCode],
  )

  const assetSearchTerm = useMemo(() => {
    if (selectedAsset || form.department !== 'it') return ''
    return assetQuery.trim() || workstationNumber.trim()
  }, [assetQuery, form.department, selectedAsset, workstationNumber])

  const descriptionCharacterCount = form.description.trim().length
  const descriptionIsValid = descriptionCharacterCount >= MIN_TICKET_DESCRIPTION_CHARACTERS

  useEffect(() => {
    void apiFetch<TicketCatalog>('/ticket-catalog')
      .then(setCatalog)
      .catch(err => setCatalogError(err instanceof Error ? err.message : 'Could not load IT issue options'))
  }, [])

  useEffect(() => {
    if (!assetSearchTerm) {
      setAssetResults([])
      setAssetLoading(false)
      setAssetError('')
      return
    }

    let cancelled = false
    const timer = window.setTimeout(() => {
      setAssetLoading(true)
      setAssetError('')
      void apiFetch<TicketAsset[]>(`/ticket-assets?query=${encodeURIComponent(assetSearchTerm)}&limit=20`)
        .then(items => {
          if (!cancelled) setAssetResults(items)
        })
        .catch(err => {
          if (!cancelled) {
            setAssetResults([])
            setAssetError(err instanceof Error ? err.message : 'Could not search the Asset Register')
          }
        })
        .finally(() => {
          if (!cancelled) setAssetLoading(false)
        })
    }, 220)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [assetSearchTerm])

  function resetItClassification() {
    setComponentCode('')
    setProblemCode('')
  }

  function selectDepartment(department: TicketDepartment) {
    setForm(current => ({ ...current, department }))
    setError('')
    if (department !== 'it') {
      setSelectedAsset(null)
      setWorkstationNumber('')
      setAssetQuery('')
      setAssetResults([])
      setAssetError('')
      resetItClassification()
    }
  }

  function chooseAsset(asset: TicketAsset) {
    setSelectedAsset(asset)
    setWorkstationNumber(asset.workstation_no || workstationNumber)
    setAssetQuery(assetPrimaryLabel(asset))
    setAssetResults([])
    setAssetError('')
    setError('')
    resetItClassification()
    setForm(current => ({ ...current, location: current.location || asset.location || '' }))
  }

  function clearAsset({ preserveWorkstation = true }: { preserveWorkstation?: boolean } = {}) {
    setSelectedAsset(null)
    setAssetQuery('')
    setAssetResults([])
    setAssetError('')
    resetItClassification()
    if (!preserveWorkstation) setWorkstationNumber('')
  }

  function selectComponent(item: TicketComponentOption) {
    setComponentCode(item.code)
    setProblemCode('')
    setError('')
  }

  const addAttachmentFiles = useCallback((incomingFiles: File[]) => {
    if (!incomingFiles.length) return
    const current = attachmentsRef.current
    const next = [...current]
    const existingKeys = new Set(current.map(item => `${item.file.name}:${item.file.size}:${item.file.lastModified}`))
    let rejected = ''

    for (const file of incomingFiles) {
      if (next.length >= MAX_TICKET_IMAGES) {
        rejected = `You can attach up to ${MAX_TICKET_IMAGES} images to one ticket.`
        break
      }
      if (!SUPPORTED_TICKET_IMAGE_TYPES.has(file.type)) {
        rejected = 'Only JPG, PNG, and WebP images are supported.'
        continue
      }
      if (file.size > MAX_TICKET_IMAGE_BYTES) {
        rejected = 'Each image must be 10 MB or smaller.'
        continue
      }
      const key = `${file.name}:${file.size}:${file.lastModified}`
      if (existingKeys.has(key)) continue
      existingKeys.add(key)
      next.push({
        id: globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`,
        file,
        previewUrl: URL.createObjectURL(file),
      })
    }

    attachmentsRef.current = next
    setAttachments(next)
    setAttachmentError(rejected)
  }, [])

  function removeAttachment(id: string) {
    const current = attachmentsRef.current
    const removed = current.find(item => item.id === id)
    if (removed) URL.revokeObjectURL(removed.previewUrl)
    const next = current.filter(item => item.id !== id)
    attachmentsRef.current = next
    setAttachments(next)
    setAttachmentError('')
  }

  useEffect(() => {
    attachmentsRef.current = attachments
  }, [attachments])

  useEffect(() => () => {
    for (const item of attachmentsRef.current) URL.revokeObjectURL(item.previewUrl)
  }, [])

  useEffect(() => {
    const handlePaste = (event: ClipboardEvent) => {
      const pasted = Array.from(event.clipboardData?.files || []).filter(file => file.type.startsWith('image/'))
      if (!pasted.length) return
      event.preventDefault()
      addAttachmentFiles(pasted)
    }
    window.addEventListener('paste', handlePaste)
    return () => window.removeEventListener('paste', handlePaste)
  }, [addAttachmentFiles])

  async function uploadTicketEvidence(ticketId: number) {
    if (!attachments.length) return
    const body = new FormData()
    for (const item of attachments) body.append('files', item.file)
    await apiFetch<TicketAttachment[]>(`/tickets/${ticketId}/attachments`, { method: 'POST', body })
  }

  async function retryTicketEvidence() {
    if (!createdTicket || !attachments.length) return
    setLoading(true)
    setAttachmentError('')
    try {
      await uploadTicketEvidence(createdTicket.id)
      navigate(`/tickets/${createdTicket.id}`, { replace: true })
    } catch (err) {
      setAttachmentError(err instanceof Error ? err.message : 'The ticket was created, but the images could not be uploaded. Try again or open the ticket without images.')
    } finally {
      setLoading(false)
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (createdTicket) return
    setError('')
    setAttachmentError('')

    const reportingManagerEmail = form.reporting_manager_email.trim().toLowerCase()
    if (!/^[^\s@]+@nakshatech\.com$/i.test(reportingManagerEmail)) {
      setError('Enter a valid Reporting Manager Email ending with @nakshatech.com.')
      return
    }

    if (!descriptionIsValid) {
      setError(`Problem Description must contain at least ${MIN_TICKET_DESCRIPTION_CHARACTERS} characters.`)
      return
    }

    if (form.department === 'it') {
      if (!selectedAsset) {
        setError('Enter the workstation or search the Asset Register, then select the affected asset.')
        return
      }
      if (!componentCode) {
        setError('Select the faulty component.')
        return
      }
      if (!problemCode) {
        setError('Select the problem affecting the component.')
        return
      }
    }

    setLoading(true)
    try {
      const ticket = await apiFetch<SupportTicket>('/tickets', {
        method: 'POST',
        body: JSON.stringify({
          ...form,
          reporting_manager_email: reportingManagerEmail,
          asset_id: selectedAsset?.id,
          component: form.department === 'it' ? componentCode : undefined,
          problem_code: form.department === 'it' ? problemCode : undefined,
        }),
      })
      if (attachments.length) {
        try {
          await uploadTicketEvidence(ticket.id)
        } catch (uploadError) {
          setCreatedTicket(ticket)
          setAttachmentError(
            uploadError instanceof Error
              ? `Ticket ${ticket.ticket_code} was created successfully, but the images were not uploaded: ${uploadError.message}`
              : `Ticket ${ticket.ticket_code} was created successfully, but the images were not uploaded.`,
          )
          return
        }
      }
      navigate(`/tickets/${ticket.id}`, { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create ticket')
    } finally {
      setLoading(false)
    }
  }

  return <>
    <DashboardHeader
      eyebrow="EMPLOYEE SUPPORT"
      title="Raise a New Ticket"
      description={`Enter the issue in a simple form, select the affected asset and priority, and submit it to the responsible team. Branch: ${user?.selected_branch_name || user?.branch}.`}
    />
    <form className="panel-card ticket-create-form ticket-simple-create-form" onSubmit={submit}>
      <section className="ticket-simple-section">
        <div className="ticket-simple-section-heading"><span>1</span><div><h2>Request details</h2><p>Choose the responsible team and your reporting manager.</p></div></div>
        <div className="ticket-simple-grid">
          <label><span>Responsible Team *</span><select value={form.department} onChange={event => selectDepartment(event.target.value as TicketDepartment)}>{departments.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
          <label><span>Reporting Manager Email *</span><input type="email" value={form.reporting_manager_email} onChange={event => setForm({ ...form, reporting_manager_email: event.target.value })} placeholder="name@nakshatech.com" autoComplete="email" pattern="[^\s@]+@nakshatech\.com" required /></label>
        </div>
      </section>

      {form.department === 'it' && <section className="ticket-simple-section">
        <div className="ticket-simple-section-heading"><span>2</span><div><h2>Select workstation and asset</h2><p>Enter the workstation number or search by CPU / Asset Tag. Select the correct asset before continuing.</p></div></div>
        <div className="ticket-simple-grid ticket-asset-search-grid">
          <label><span>Workstation Number</span><input value={workstationNumber} onChange={event => { const value = event.target.value; setWorkstationNumber(value); if (selectedAsset && value !== (selectedAsset.workstation_no || '')) clearAsset({ preserveWorkstation: true }) }} placeholder="Example: 8405" autoComplete="off" /></label>
          <label><span>CPU / Asset Tag</span><div className="ticket-simple-search-field"><Search size={18} /><input value={assetQuery} onChange={event => { setAssetQuery(event.target.value); if (selectedAsset) clearAsset({ preserveWorkstation: true }) }} placeholder="Example: 2646 or NT-PC-0098" autoComplete="off" />{assetLoading && <small>Searching…</small>}</div></label>
        </div>
        {assetError && <div className="error-message">{assetError}</div>}
        {!selectedAsset && assetSearchTerm && !assetLoading && !assetError && assetResults.length === 0 && <div className="ticket-asset-empty">No active asset matches “{assetSearchTerm}”. Check the workstation or asset tag.</div>}
        {!selectedAsset && assetResults.length > 0 && <div className="ticket-simple-asset-results">
          {assetResults.map(asset => <button type="button" key={asset.id} onClick={() => chooseAsset(asset)}>
            <Cpu size={20} />
            <div><strong>{assetPrimaryLabel(asset)}</strong><span>Workstation {asset.workstation_no || 'Not recorded'} · {asset.used_by || 'Unassigned'} · {asset.device_type}</span></div>
            <small>{asset.status.replaceAll('_', ' ')}</small>
          </button>)}
        </div>}
        {selectedAsset && <article className="ticket-simple-selected-asset">
          <div className="ticket-simple-selected-title"><div><small>SELECTED ASSET</small><strong>{assetPrimaryLabel(selectedAsset)}</strong><span>{selectedAsset.system_name || selectedAsset.asset_code}</span></div><button type="button" className="ghost-button compact" onClick={() => clearAsset({ preserveWorkstation: false })}><X size={15} /> Change</button></div>
          <div className="ticket-simple-asset-facts">
            <span><Gauge size={16} /><small>Workstation</small><strong>{selectedAsset.workstation_no || 'Not recorded'}</strong></span>
            <span><UserRound size={16} /><small>Used By</small><strong>{selectedAsset.used_by || 'Unassigned'}</strong></span>
            <span><Building2 size={16} /><small>Location</small><strong>{selectedAsset.location || selectedAsset.work_mode || 'Not recorded'}</strong></span>
            <span><HardDrive size={16} /><small>Device</small><strong>{selectedAsset.device_type}</strong></span>
          </div>
        </article>}
      </section>}

      {form.department === 'it' && selectedAsset && <section className="ticket-simple-section">
        <div className="ticket-simple-section-heading"><span>3</span><div><h2>Fault details</h2><p>Select the faulty component from the scrollable list, the exact problem, and the priority.</p></div></div>
        {catalogError && <div className="error-message">{catalogError}</div>}
        <div className="ticket-simple-fault-grid">
          <label><span>Faulty Component *</span><select className="ticket-component-listbox" size={6} value={componentCode} onChange={event => { const item = catalog.components.find(component => component.code === event.target.value); if (item) selectComponent(item) }}>{catalog.components.map(item => <option key={item.code} value={item.code}>{item.label}{componentTag(selectedAsset, item.code) ? ` — ${componentTag(selectedAsset, item.code)}` : ''}</option>)}</select><small>Scroll to view all available components.</small></label>
          <div className="ticket-simple-fault-side">
            <label><span>Problem *</span><select value={problemCode} onChange={event => { setProblemCode(event.target.value); setError('') }} disabled={!selectedComponent}><option value="">Select the problem</option>{selectedComponent?.problems.map(problem => <option key={problem.code} value={problem.code}>{problem.label}</option>)}</select></label>
            <fieldset className="ticket-priority-choice"><legend>Priority *</legend><div>{priorities.map(item => <button type="button" key={item.value} className={`ticket-manual-priority priority-${item.value} ${form.priority === item.value ? 'selected' : ''}`} onClick={() => setForm(current => ({ ...current, priority: item.value }))}><strong>{item.label}</strong><span>{item.help}</span></button>)}</div></fieldset>
          </div>
        </div>
      </section>}

      <section className="ticket-simple-section">
        <div className="ticket-simple-section-heading"><span>{form.department === 'it' ? '4' : '2'}</span><div><h2>Describe the issue</h2><p>Give the team enough information to understand and act on the request.</p></div></div>
        <div className="ticket-simple-grid">
          <label><span>Issue Title *</span><input value={form.title} onChange={event => setForm({ ...form, title: event.target.value })} placeholder="Example: Mouse right click not working" required /></label>
          {form.department !== 'it' && <label><span>Category</span><input value={form.category} onChange={event => setForm({ ...form, category: event.target.value })} placeholder="Request category" /></label>}
          {form.department !== 'it' && <label><span>Priority *</span><select value={form.priority} onChange={event => setForm({ ...form, priority: event.target.value as TicketPriority })}><option value="low">Low</option><option value="medium">Moderate</option><option value="high">High</option><option value="critical">Critical</option></select></label>}
          <label><span>Issue Location</span><input value={form.location} onChange={event => setForm({ ...form, location: event.target.value })} placeholder="Floor / room / desk / site" /></label>
          <label className="ticket-simple-span"><span>Problem Description *</span><textarea className={descriptionIsValid ? 'ticket-description-valid' : 'ticket-description-invalid'} value={form.description} onChange={event => { setForm({ ...form, description: event.target.value }); setError('') }} rows={5} minLength={MIN_TICKET_DESCRIPTION_CHARACTERS} placeholder="Explain the problem clearly and mention anything you already tried." required /><small className={`ticket-description-rule ${descriptionIsValid ? 'valid' : 'invalid'}`}>{descriptionIsValid ? `Ready to submit · ${descriptionCharacterCount} characters` : `Minimum ${MIN_TICKET_DESCRIPTION_CHARACTERS} characters · ${descriptionCharacterCount}/${MIN_TICKET_DESCRIPTION_CHARACTERS}`}</small></label>
        </div>
      </section>

      <section className="ticket-simple-section ticket-attachment-section">
        <div className="ticket-simple-section-heading"><span>{form.department === 'it' ? '5' : '3'}</span><div><h2>Attach screenshot or photo</h2><p>Optional. Add up to five images so the support team can see the issue immediately.</p></div><em>{attachments.length}/{MAX_TICKET_IMAGES}</em></div>
        <input ref={fileInputRef} className="ticket-attachment-input" type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={event => { addAttachmentFiles(Array.from(event.target.files || [])); event.target.value = '' }} />
        <button type="button" className="ticket-attachment-dropzone ticket-simple-dropzone" onClick={() => fileInputRef.current?.click()} onDragOver={event => { event.preventDefault(); event.dataTransfer.dropEffect = 'copy' }} onDrop={event => { event.preventDefault(); addAttachmentFiles(Array.from(event.dataTransfer.files || [])) }} disabled={Boolean(createdTicket)}>
          <span className="ticket-attachment-dropzone-icon"><Upload size={22} /></span>
          <span><strong>Upload image evidence</strong><small>Browse, drag & drop, or paste with Ctrl + V · JPG, PNG or WebP · 10 MB max each</small></span>
          <Paperclip size={18} />
        </button>
        {attachments.length > 0 && <div className="ticket-attachment-preview-grid">{attachments.map(item => <article key={item.id} className="ticket-attachment-preview-card"><img src={item.previewUrl} alt={`Preview of ${item.file.name}`} /><div><strong>{item.file.name}</strong><span>{formatAttachmentSize(item.file.size)}</span></div>{!createdTicket && <button type="button" onClick={() => removeAttachment(item.id)} aria-label={`Remove ${item.file.name}`}><X size={15} /></button>}</article>)}</div>}
        {attachmentError && <div className={createdTicket ? 'ticket-attachment-warning' : 'error-message'}>{attachmentError}</div>}
        {createdTicket && <div className="ticket-attachment-recovery"><div><strong>{createdTicket.ticket_code} is already saved.</strong><span>Only the optional image upload needs attention. Retrying will not create a duplicate ticket.</span></div><div>{attachments.length > 0 && <button type="button" className="secondary-button" onClick={retryTicketEvidence} disabled={loading}>{loading ? 'Retrying...' : 'Retry Image Upload'}</button>}<button type="button" className="primary-button" onClick={() => navigate(`/tickets/${createdTicket.id}`, { replace: true })}>Open Ticket</button></div></div>}
      </section>

      {error && <div className="error-message">{error}</div>}
      {!createdTicket && <div className="ticket-form-actions ticket-simple-actions"><button type="button" className="ghost-button" onClick={() => navigate(-1)}>Cancel</button><button className="primary-button" disabled={loading || !descriptionIsValid}><Send size={18} />{loading ? 'Submitting...' : 'Submit Ticket'}</button></div>}
    </form>
  </>
}
