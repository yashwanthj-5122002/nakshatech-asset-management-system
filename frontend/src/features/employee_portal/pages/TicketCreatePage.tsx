import {
  AppWindow,
  BatteryCharging,
  Building2,
  CircleHelp,
  Cpu,
  Gauge,
  HardDrive,
  Keyboard,
  KeyRound,
  MemoryStick,
  Monitor,
  MousePointer2,
  Paperclip,
  PlaneTakeoff,
  Printer,
  Search,
  Send,
  Settings2,
  ShieldAlert,
  Upload,
  UserRound,
  Users,
  Wifi,
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
  TicketImpactAssessment,
  TicketPriority,
  TicketPriorityPreview,
} from '../../../types'

const departments: Array<{ value: TicketDepartment; label: string; description: string; icon: typeof Cpu }> = [
  { value: 'it', label: 'IT Department', description: 'Laptop, desktop, Wi-Fi, printer, hardware, or access issues.', icon: Cpu },
  { value: 'drone', label: 'Drone Department', description: 'Drone hardware, batteries, trackers, flight, or survey equipment.', icon: PlaneTakeoff },
  { value: 'software_team', label: 'Software Team', description: 'CRM errors, application bugs, login issues, data, or feature requests.', icon: Settings2 },
  { value: 'management', label: 'Management', description: 'Administrative, resource, policy, or escalation requests.', icon: Users },
]

const componentIcons: Record<string, typeof Cpu> = {
  system: Cpu,
  monitor: Monitor,
  mouse: MousePointer2,
  keyboard: Keyboard,
  memory: MemoryStick,
  storage: HardDrive,
  network: Wifi,
  operating_system: Settings2,
  software: AppWindow,
  printer: Printer,
  power_ups: BatteryCharging,
  login_account: KeyRound,
  other: CircleHelp,
}

const emptyImpact: TicketImpactAssessment = {
  work_stopped: false,
  alternative_available: true,
  multiple_users_affected: false,
  data_loss_risk: false,
  security_risk: false,
  client_delivery_affected: false,
  recurring_issue: false,
  started_when: '',
}

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

function priorityLabel(priority: TicketPriority): string {
  return priority === 'medium' ? 'Moderate' : priority.charAt(0).toUpperCase() + priority.slice(1)
}

function formatSla(minutes: number): string {
  if (minutes < 60) return `${minutes} minutes`
  if (minutes < 1440) return `${Math.round(minutes / 60)} hours`
  return `${Math.round(minutes / 1440)} day`
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

interface ImpactQuestionProps {
  label: string
  help: string
  value: boolean
  onChange: (value: boolean) => void
  invertLabels?: boolean
}

function ImpactQuestion({ label, help, value, onChange, invertLabels = false }: ImpactQuestionProps) {
  return <article className="ticket-impact-question">
    <div><strong>{label}</strong><span>{help}</span></div>
    <div className="ticket-binary-toggle" role="group" aria-label={label}>
      <button type="button" className={value ? 'selected' : ''} onClick={() => onChange(true)}>{invertLabels ? 'Available' : 'Yes'}</button>
      <button type="button" className={!value ? 'selected' : ''} onClick={() => onChange(false)}>{invertLabels ? 'Not Available' : 'No'}</button>
    </div>
  </article>
}

export function TicketCreatePage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [form, setForm] = useState(emptyForm)
  const [catalog, setCatalog] = useState<TicketCatalog>({ components: [] })
  const [catalogError, setCatalogError] = useState('')
  const [assetQuery, setAssetQuery] = useState('')
  const [assetResults, setAssetResults] = useState<TicketAsset[]>([])
  const [selectedAsset, setSelectedAsset] = useState<TicketAsset | null>(null)
  const [assetLoading, setAssetLoading] = useState(false)
  const [assetError, setAssetError] = useState('')
  const [componentCode, setComponentCode] = useState('')
  const [problemCode, setProblemCode] = useState('')
  const [impact, setImpact] = useState<TicketImpactAssessment>(emptyImpact)
  const [priorityPreview, setPriorityPreview] = useState<TicketPriorityPreview | null>(null)
  const [priorityLoading, setPriorityLoading] = useState(false)
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

  const descriptionCharacterCount = form.description.trim().length
  const descriptionIsValid = descriptionCharacterCount >= MIN_TICKET_DESCRIPTION_CHARACTERS

  useEffect(() => {
    void apiFetch<TicketCatalog>('/ticket-catalog')
      .then(setCatalog)
      .catch(err => setCatalogError(err instanceof Error ? err.message : 'Could not load IT issue options'))
  }, [])

  useEffect(() => {
    if (form.department !== 'it' || selectedAsset) {
      setAssetResults([])
      setAssetLoading(false)
      return
    }

    const query = assetQuery.trim()
    if (!query) {
      setAssetResults([])
      setAssetError('')
      return
    }

    let cancelled = false
    const timer = window.setTimeout(() => {
      setAssetLoading(true)
      setAssetError('')
      void apiFetch<TicketAsset[]>(`/ticket-assets?query=${encodeURIComponent(query)}&limit=20`)
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
    }, 250)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [assetQuery, form.department, selectedAsset])

  useEffect(() => {
    if (form.department !== 'it' || !componentCode || !problemCode) {
      setPriorityPreview(null)
      setPriorityLoading(false)
      return
    }

    let cancelled = false
    const timer = window.setTimeout(() => {
      setPriorityLoading(true)
      void apiFetch<TicketPriorityPreview>('/ticket-priority-preview', {
        method: 'POST',
        body: JSON.stringify({ component: componentCode, problem_code: problemCode, impact }),
      })
        .then(result => {
          if (!cancelled) setPriorityPreview(result)
        })
        .catch(err => {
          if (!cancelled) {
            setPriorityPreview(null)
            setError(err instanceof Error ? err.message : 'Could not calculate ticket priority')
          }
        })
        .finally(() => {
          if (!cancelled) setPriorityLoading(false)
        })
    }, 180)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [componentCode, form.department, impact, problemCode])

  function resetItClassification() {
    setComponentCode('')
    setProblemCode('')
    setImpact(emptyImpact)
    setPriorityPreview(null)
  }

  function selectDepartment(department: TicketDepartment) {
    setForm(current => ({ ...current, department }))
    setError('')
    if (department !== 'it') {
      setSelectedAsset(null)
      setAssetQuery('')
      setAssetResults([])
      setAssetError('')
      resetItClassification()
    }
  }

  function chooseAsset(asset: TicketAsset) {
    setSelectedAsset(asset)
    setAssetQuery(assetPrimaryLabel(asset))
    setAssetResults([])
    setAssetError('')
    setError('')
    resetItClassification()
    setForm(current => ({ ...current, location: current.location || asset.location || '' }))
  }

  function clearAsset() {
    setSelectedAsset(null)
    setAssetQuery('')
    setAssetResults([])
    setAssetError('')
    resetItClassification()
  }

  function selectComponent(item: TicketComponentOption) {
    setComponentCode(item.code)
    setProblemCode('')
    setPriorityPreview(null)
    setError('')
  }

  function updateImpact<K extends keyof TicketImpactAssessment>(key: K, value: TicketImpactAssessment[K]) {
    setImpact(current => ({ ...current, [key]: value }))
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
        setError('Search and select the affected CPU / asset tag before submitting the IT ticket.')
        return
      }
      if (!componentCode) {
        setError('Select which part of the system is not working.')
        return
      }
      if (!problemCode) {
        setError('Select the exact problem affecting the component.')
        return
      }
      if (!priorityPreview) {
        setError('Wait for the automatic priority calculation to finish.')
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
          impact: form.department === 'it' ? impact : undefined,
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
      description={`Select the affected asset and actual work impact. The system calculates priority automatically. Branch: ${user?.selected_branch_name || user?.branch}.`}
    />
    <form className="panel-card ticket-create-form" onSubmit={submit}>
      <div className="ticket-form-section">
        <span className="section-kicker">1 · SELECT RESPONSIBLE TEAM</span>
        <div className="ticket-department-grid">
          {departments.map(item => {
            const Icon = item.icon
            return <button
              type="button"
              key={item.value}
              className={form.department === item.value ? 'selected' : ''}
              onClick={() => selectDepartment(item.value)}
            >
              <Icon />
              <div><strong>{item.label}</strong><span>{item.description}</span></div>
            </button>
          })}
        </div>
      </div>

      {form.department === 'it' && <div className="ticket-form-section ticket-asset-section">
        <div className="ticket-section-heading">
          <div><span className="section-kicker">2 · SELECT THE AFFECTED ASSET</span><p>Search the current Asset Register using the existing CPU tag, internal asset code, workstation number, system name, user, or connected component tag.</p></div>
          {selectedAsset && <button type="button" className="ghost-button compact" onClick={clearAsset}><X size={15} />Change Asset</button>}
        </div>

        {!selectedAsset && <div className="ticket-asset-search-wrap">
          <label className="ticket-asset-search">
            <Search size={19} />
            <input
              autoComplete="off"
              value={assetQuery}
              onChange={event => setAssetQuery(event.target.value)}
              placeholder="Search CPU / physical asset tag, for example 2446"
              aria-label="Search Asset Register"
            />
            {assetLoading && <span className="ticket-search-state">Searching…</span>}
          </label>
          {assetError && <div className="error-message">{assetError}</div>}
          {!assetLoading && assetQuery.trim() && !assetError && assetResults.length === 0 && <div className="ticket-asset-empty">No active asset matches “{assetQuery.trim()}”. Check the CPU tag and try again.</div>}
          {assetResults.length > 0 && <div className="ticket-asset-results">
            {assetResults.map(asset => <button type="button" key={asset.id} onClick={() => chooseAsset(asset)}>
              <div className="ticket-asset-result-icon"><Cpu size={20} /></div>
              <div className="ticket-asset-result-main">
                <strong>{assetPrimaryLabel(asset)} <small>· Internal {asset.asset_code}</small></strong>
                <span>{asset.workstation_no || 'No workstation'} · {asset.device_type} · {asset.system_name || 'System name not recorded'}</span>
                <span>{asset.used_by || 'Unassigned'} · {asset.department || 'Department not recorded'}</span>
              </div>
              <span className={`status ${asset.status}`}>{asset.status.replaceAll('_', ' ')}</span>
            </button>)}
          </div>}
        </div>}

        {selectedAsset && <article className="ticket-selected-asset-card">
          <header>
            <div><span>SELECTED CPU / ASSET TAG</span><h2>{assetPrimaryLabel(selectedAsset)}</h2><p>Internal reference {selectedAsset.asset_code}</p></div>
            <span className={`status ${selectedAsset.status}`}>{selectedAsset.status.replaceAll('_', ' ')}</span>
          </header>
          <div className="ticket-asset-detail-grid">
            <div><Gauge size={17} /><span>Workstation</span><strong>{selectedAsset.workstation_no || 'Not recorded'}</strong></div>
            <div><UserRound size={17} /><span>Used By</span><strong>{selectedAsset.used_by || 'Unassigned'}</strong></div>
            <div><Building2 size={17} /><span>Department</span><strong>{selectedAsset.department || 'Not recorded'}</strong></div>
            <div><Cpu size={17} /><span>Device</span><strong>{selectedAsset.device_type} · {selectedAsset.system_name || 'Unnamed system'}</strong></div>
            <div><HardDrive size={17} /><span>Configuration</span><strong>{[selectedAsset.processor, selectedAsset.memory_gb, selectedAsset.ssd || selectedAsset.hdd].filter(Boolean).join(' · ') || 'Not recorded'}</strong></div>
            <div><Building2 size={17} /><span>Asset Location</span><strong>{selectedAsset.location || selectedAsset.work_mode || 'Not recorded'}</strong></div>
          </div>
          <div className="ticket-component-tags">
            <span><Monitor size={16} />Monitor <strong>{selectedAsset.monitor_asset_tags || 'Not recorded'}</strong></span>
            <span><MousePointer2 size={16} />Mouse <strong>{selectedAsset.mouse_asset_tag || 'Not recorded'}</strong></span>
            <span><Keyboard size={16} />Keyboard <strong>{selectedAsset.keyboard_asset_tag || 'Not recorded'}</strong></span>
          </div>
          <p className="ticket-asset-snapshot-note">These current Asset Register details will be saved with the ticket as a historical snapshot.</p>
        </article>}
      </div>}

      {form.department === 'it' && selectedAsset && <div className="ticket-form-section ticket-classification-section">
        <div className="ticket-section-heading"><div><span className="section-kicker">3 · SELECT THE FAULTY COMPONENT</span><p>Choose the exact part of this asset that is affected. Existing component tags are shown where available.</p></div></div>
        {catalogError && <div className="error-message">{catalogError}</div>}
        <div className="ticket-component-grid">
          {catalog.components.map(item => {
            const Icon = componentIcons[item.code] || CircleHelp
            const tag = componentTag(selectedAsset, item.code)
            return <button type="button" key={item.code} className={componentCode === item.code ? 'selected' : ''} onClick={() => selectComponent(item)}>
              <Icon size={21} />
              <div><strong>{item.label}</strong><span>{tag ? `Asset tag ${tag}` : 'No separate component tag'}</span></div>
            </button>
          })}
        </div>
      </div>}

      {form.department === 'it' && selectedComponent && <div className="ticket-form-section ticket-problem-section">
        <div className="ticket-section-heading"><div><span className="section-kicker">4 · SELECT THE EXACT PROBLEM</span><p>Choose the problem that best describes what is happening with {selectedComponent.label}.</p></div></div>
        <div className="ticket-problem-grid">
          {selectedComponent.problems.map(problem => <button type="button" key={problem.code} className={problemCode === problem.code ? 'selected' : ''} onClick={() => { setProblemCode(problem.code); setError('') }}>
            <span className="ticket-problem-radio" />
            <strong>{problem.label}</strong>
          </button>)}
        </div>
      </div>}

      {form.department === 'it' && problemCode && <div className="ticket-form-section ticket-impact-section">
        <div className="ticket-section-heading"><div><span className="section-kicker">5 · WORK IMPACT ASSESSMENT</span><p>Answer accurately. These answers determine the priority and queue order automatically.</p></div></div>
        <div className="ticket-impact-grid">
          <ImpactQuestion label="Is your work completely stopped?" help="Select Yes only when you cannot continue normal work." value={impact.work_stopped} onChange={value => updateImpact('work_stopped', value)} />
          <ImpactQuestion label="Is another system or workaround available?" help="A spare device or usable temporary method reduces urgency." value={impact.alternative_available} onChange={value => updateImpact('alternative_available', value)} invertLabels />
          <ImpactQuestion label="Are multiple employees affected?" help="Select Yes when this is not limited to only your system." value={impact.multiple_users_affected} onChange={value => updateImpact('multiple_users_affected', value)} />
          <ImpactQuestion label="Is there a possible data-loss risk?" help="Files may be lost, corrupted, or become inaccessible." value={impact.data_loss_risk} onChange={value => updateImpact('data_loss_risk', value)} />
          <ImpactQuestion label="Is there a security risk?" help="Suspicious access, compromise, malware, or exposed credentials." value={impact.security_risk} onChange={value => updateImpact('security_risk', value)} />
          <ImpactQuestion label="Is a project or client delivery affected?" help="A committed project deadline or client delivery may be delayed." value={impact.client_delivery_affected} onChange={value => updateImpact('client_delivery_affected', value)} />
          <ImpactQuestion label="Has this problem happened before?" help="Repeated problems may require deeper investigation." value={impact.recurring_issue} onChange={value => updateImpact('recurring_issue', value)} />
          <label className="ticket-impact-started"><span>When did the problem start? (Optional)</span><input value={impact.started_when || ''} onChange={event => updateImpact('started_when', event.target.value)} placeholder="Example: Today at 10:30 AM" /></label>
        </div>
      </div>}

      {form.department === 'it' && problemCode && <div className="ticket-form-section ticket-priority-section">
        <div className="ticket-section-heading"><div><span className="section-kicker">6 · AUTOMATIC PRIORITY</span><p>The employee cannot manually increase priority. The server recalculates and validates this result when the ticket is submitted.</p></div></div>
        {priorityLoading && <div className="ticket-priority-loading">Calculating impact-based priority…</div>}
        {priorityPreview && <article className={`ticket-priority-preview priority-preview-${priorityPreview.priority}`}>
          <div className="ticket-priority-preview-icon"><ShieldAlert size={24} /></div>
          <div><span>CALCULATED PRIORITY</span><h3>{priorityPreview.priority_label}</h3><p>{priorityPreview.reason}</p><small>Initial response target: {formatSla(priorityPreview.sla_target_minutes)}</small></div>
        </article>}
      </div>}

      <div className="ticket-form-section ticket-field-grid">
        <span className="section-kicker ticket-grid-span">{form.department === 'it' ? '7' : '2'} · DESCRIBE THE ISSUE</span>
        <label className="ticket-grid-span"><span>Reporting Manager Email</span><input type="email" value={form.reporting_manager_email} onChange={e => setForm({ ...form, reporting_manager_email: e.target.value })} placeholder="name@nakshatech.com" autoComplete="email" pattern="[^\s@]+@nakshatech\.com" title="Use a valid @nakshatech.com email address" required /><small>The reporting manager will receive email updates when this ticket is raised and resolved.</small></label>
        <label><span>Issue Title</span><input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="Example: Mouse is not detected after restart" required /></label>
        {form.department !== 'it' && <label><span>Category</span><input value={form.category} onChange={e => setForm({ ...form, category: e.target.value })} placeholder="Request category" /></label>}
        {form.department !== 'it' && <label><span>Priority</span><select value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value as TicketPriority })}><option value="low">Low</option><option value="medium">Moderate</option><option value="high">High</option><option value="critical">Critical</option></select></label>}
        <label><span>Issue Location</span><div className="field-with-icon"><Building2 size={17} /><input value={form.location} onChange={e => setForm({ ...form, location: e.target.value })} placeholder="Floor / room / desk / site" /></div></label>
        <label className="ticket-grid-span ticket-description-field">
          <span>Problem Description</span>
          <textarea
            className={descriptionIsValid ? 'ticket-description-valid' : 'ticket-description-invalid'}
            value={form.description}
            onChange={e => { setForm({ ...form, description: e.target.value }); setError('') }}
            rows={7}
            minLength={MIN_TICKET_DESCRIPTION_CHARACTERS}
            aria-invalid={!descriptionIsValid}
            aria-describedby="ticket-description-rule"
            placeholder="Explain what happened, when it started, and what you have already tried."
            required
          />
          <small
            id="ticket-description-rule"
            className={`ticket-description-rule ${descriptionIsValid ? 'valid' : 'invalid'}`}
            aria-live="polite"
          >
            {descriptionIsValid
              ? `Description requirement met · ${descriptionCharacterCount} characters`
              : `Enter at least ${MIN_TICKET_DESCRIPTION_CHARACTERS} characters · ${descriptionCharacterCount}/${MIN_TICKET_DESCRIPTION_CHARACTERS}`}
          </small>
        </label>
      </div>

      <div className="ticket-form-section ticket-attachment-section">
        <div className="ticket-section-heading">
          <div>
            <span className="section-kicker">{form.department === 'it' ? '8' : '3'} · ATTACH EVIDENCE (OPTIONAL)</span>
            <p>Add screenshots or photos that help the responsible team understand the issue. The ticket can still be submitted without an image.</p>
          </div>
          <span className="ticket-attachment-count">{attachments.length}/{MAX_TICKET_IMAGES}</span>
        </div>
        <input
          ref={fileInputRef}
          className="ticket-attachment-input"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          onChange={event => { addAttachmentFiles(Array.from(event.target.files || [])); event.target.value = '' }}
        />
        <button
          type="button"
          className="ticket-attachment-dropzone"
          onClick={() => fileInputRef.current?.click()}
          onDragOver={event => { event.preventDefault(); event.dataTransfer.dropEffect = 'copy' }}
          onDrop={event => { event.preventDefault(); addAttachmentFiles(Array.from(event.dataTransfer.files || [])) }}
          disabled={Boolean(createdTicket)}
        >
          <span className="ticket-attachment-dropzone-icon"><Upload size={22} /></span>
          <span><strong>Add screenshot or photo</strong><small>Browse, drag & drop, or paste an image with Ctrl + V · JPG, PNG or WebP · 10 MB max each</small></span>
          <Paperclip size={18} />
        </button>
        {attachments.length > 0 && <div className="ticket-attachment-preview-grid">
          {attachments.map(item => <article key={item.id} className="ticket-attachment-preview-card">
            <img src={item.previewUrl} alt={`Preview of ${item.file.name}`} />
            <div><strong>{item.file.name}</strong><span>{formatAttachmentSize(item.file.size)}</span></div>
            {!createdTicket && <button type="button" onClick={() => removeAttachment(item.id)} aria-label={`Remove ${item.file.name}`}><X size={15} /></button>}
          </article>)}
        </div>}
        {attachmentError && <div className={createdTicket ? 'ticket-attachment-warning' : 'error-message'}>{attachmentError}</div>}
        {createdTicket && <div className="ticket-attachment-recovery">
          <div><strong>{createdTicket.ticket_code} is already saved.</strong><span>Only the optional evidence upload needs attention. Retrying will not create a duplicate ticket.</span></div>
          <div>
            {attachments.length > 0 && <button type="button" className="secondary-button" onClick={retryTicketEvidence} disabled={loading}>{loading ? 'Retrying...' : 'Retry Image Upload'}</button>}
            <button type="button" className="primary-button" onClick={() => navigate(`/tickets/${createdTicket.id}`, { replace: true })}>Open Ticket</button>
          </div>
        </div>}
      </div>

      {error && <div className="error-message">{error}</div>}
      {!createdTicket && <div className="ticket-form-actions"><button type="button" className="ghost-button" onClick={() => navigate(-1)}>Cancel</button><button className="primary-button" disabled={loading || priorityLoading || !descriptionIsValid}><Send size={17} />{loading ? 'Submitting...' : 'Submit Ticket'}</button></div>}
    </form>
  </>
}
