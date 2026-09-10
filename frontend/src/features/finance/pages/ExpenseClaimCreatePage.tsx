import { ArrowLeft, CalendarDays, FileText, Plus, Send, Trash2, UploadCloud, X } from 'lucide-react'
import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import type { ExpenseClaim, ExpenseClaimAttachment, FinanceClaimType, FinancePaymentMode, FinanceProject } from '../../../types'
import { financeClaimTypeLabels, financeExpenseCategories, formatInr } from '../finance-utils'
import '../finance-expenses.css'

interface DraftItem {
  id: string
  category: string
  otherCategory: string
  description: string
  amount: string
  paymentMode: FinancePaymentMode
  expenseDate: string
}

function todayIso() {
  return new Date().toISOString().slice(0, 10)
}

function newItem(): DraftItem {
  return { id: crypto.randomUUID(), category: 'travel', otherCategory: '', description: '', amount: '', paymentMode: 'upi', expenseDate: todayIso() }
}

function claimItemsToDraft(claim: ExpenseClaim): DraftItem[] {
  return claim.items.map(item => ({
    id: `existing-${item.id}-${crypto.randomUUID()}`,
    category: item.category,
    otherCategory: item.other_category || '',
    description: item.description,
    amount: String(item.amount),
    paymentMode: item.payment_mode || 'upi',
    expenseDate: item.expense_date || claim.requested_work_start_date || todayIso(),
  }))
}

function clampDateToProject(project: FinanceProject | undefined): string {
  const today = todayIso()
  if (!project) return today
  if (project.start_date && today < project.start_date) return project.start_date
  if (project.end_date && today > project.end_date) return project.end_date
  return today
}

export function ExpenseClaimCreatePage() {
  const navigate = useNavigate()
  const { id: claimIdParam } = useParams()
  const [searchParams] = useSearchParams()
  const claimId = claimIdParam ? Number(claimIdParam) : null
  const isEditing = claimId !== null && Number.isFinite(claimId)

  const [projects, setProjects] = useState<FinanceProject[]>([])
  const [employeeClaims, setEmployeeClaims] = useState<ExpenseClaim[]>([])
  const [projectId, setProjectId] = useState('')
  const [claimType, setClaimType] = useState<FinanceClaimType>('advance')
  const [purpose, setPurpose] = useState('')
  const [requestedWorkStart, setRequestedWorkStart] = useState(todayIso())
  const [requestedWorkEnd, setRequestedWorkEnd] = useState(todayIso())
  const [parentAdvanceId, setParentAdvanceId] = useState('')
  const [previousAdvanceAmount, setPreviousAdvanceAmount] = useState('')
  const [amountAlreadyUsed, setAmountAlreadyUsed] = useState('')
  const [items, setItems] = useState<DraftItem[]>([newItem()])
  const [files, setFiles] = useState<File[]>([])
  const [existingAttachments, setExistingAttachments] = useState<ExpenseClaimAttachment[]>([])
  const [loading, setLoading] = useState(false)
  const [initialLoading, setInitialLoading] = useState(true)
  const [error, setError] = useState('')
  const [draftClaim, setDraftClaim] = useState<ExpenseClaim | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setInitialLoading(true)
      setError('')
      try {
        const [projectItems, claims] = await Promise.all([
          apiFetch<FinanceProject[]>('/finance/projects'),
          apiFetch<ExpenseClaim[]>('/finance/claims'),
        ])
        if (cancelled) return
        setProjects(projectItems)
        setEmployeeClaims(claims)

        if (isEditing && claimId) {
          const claim = await apiFetch<ExpenseClaim>(`/finance/claims/${claimId}`)
          if (cancelled) return
          if (!claim.can_edit) throw new Error('This claim is no longer editable.')
          setDraftClaim(claim)
          setProjectId(String(claim.project.id))
          setClaimType(claim.claim_type)
          setPurpose(claim.purpose_description)
          setRequestedWorkStart(claim.requested_work_start_date || clampDateToProject(claim.project))
          setRequestedWorkEnd(claim.requested_work_end_date || clampDateToProject(claim.project))
          setParentAdvanceId(claim.parent_advance_claim_id ? String(claim.parent_advance_claim_id) : '')
          setPreviousAdvanceAmount(claim.previous_advance_amount == null ? '' : String(claim.previous_advance_amount))
          setAmountAlreadyUsed(claim.amount_already_used == null ? '' : String(claim.amount_already_used))
          setItems(claimItemsToDraft(claim))
          setExistingAttachments(claim.attachments)
        } else if (projectItems.length > 0) {
          const requestedParentId = Number(searchParams.get('parent') || 0)
          const requestedParent = requestedParentId ? claims.find(item => item.id === requestedParentId && item.claim_type === 'advance' && item.can_request_additional_advance) : undefined
          const first = requestedParent?.project || projectItems.find(item => item.expense_allowed)
          if (first) {
            setProjectId(String(first.id))
            const date = clampDateToProject(first)
            setRequestedWorkStart(date)
            setRequestedWorkEnd(date)
          }
          if (requestedParent) {
            setClaimType('additional_advance')
            setParentAdvanceId(String(requestedParent.id))
            setPreviousAdvanceAmount(String(requestedParent.paid_amount || requestedParent.finance_approved_amount || requestedParent.total_amount))
          }
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load project expense form')
      } finally {
        if (!cancelled) setInitialLoading(false)
      }
    }
    void load()
    return () => { cancelled = true }
  }, [claimId, isEditing, searchParams])

  const selectedProject = useMemo(() => projects.find(project => String(project.id) === projectId), [projects, projectId])
  const openProjectCount = projects.filter(item => item.expense_allowed).length
  const eligibleAdvances = useMemo(() => employeeClaims.filter(claim => (
    claim.claim_type === 'advance'
    && claim.project.id === Number(projectId)
    && (claim.can_request_additional_advance || claim.id === Number(parentAdvanceId))
  )), [employeeClaims, parentAdvanceId, projectId])

  const totalAmount = useMemo(() => items.reduce((sum, item) => sum + (Number(item.amount) || 0), 0), [items])
  const requestedDays = useMemo(() => {
    if (!requestedWorkStart || !requestedWorkEnd) return 0
    const start = new Date(`${requestedWorkStart}T00:00:00`)
    const end = new Date(`${requestedWorkEnd}T00:00:00`)
    return end >= start ? Math.floor((end.getTime() - start.getTime()) / 86_400_000) + 1 : 0
  }, [requestedWorkStart, requestedWorkEnd])
  const canRemoveExistingAttachments = draftClaim?.status === 'draft'

  useEffect(() => {
    if (claimType !== 'additional_advance') return
    const parent = eligibleAdvances.find(item => item.id === Number(parentAdvanceId))
    if (parent) setPreviousAdvanceAmount(String(parent.paid_amount || parent.finance_approved_amount || parent.total_amount))
  }, [claimType, eligibleAdvances, parentAdvanceId])

  function changeProject(value: string) {
    setProjectId(value)
    setParentAdvanceId('')
    setPreviousAdvanceAmount('')
    const project = projects.find(item => String(item.id) === value)
    const date = clampDateToProject(project)
    setRequestedWorkStart(date)
    setRequestedWorkEnd(date)
  }

  function updateItem(id: string, patch: Partial<DraftItem>) {
    setItems(current => current.map(item => item.id === id ? { ...item, ...patch } : item))
  }

  function removeItem(id: string) {
    setItems(current => current.length === 1 ? current : current.filter(item => item.id !== id))
  }

  function validateForm(): string | null {
    if (!projectId || !selectedProject) return 'Select a Project ID.'
    if (!selectedProject.expense_allowed) return selectedProject.expense_block_reason || 'This project is not open for new expenses.'
    if (purpose.trim().length < 10) return 'Describe why this project expense is required.'
    if (!requestedWorkStart || !requestedWorkEnd) return 'Select the work start and end dates.'
    if (requestedWorkEnd < requestedWorkStart) return 'Work end date cannot be earlier than work start date.'
    if (selectedProject.start_date && requestedWorkStart < selectedProject.start_date) return `Work cannot start before the project start date (${selectedProject.start_date}).`
    if (selectedProject.end_date && requestedWorkEnd > selectedProject.end_date) return `Work cannot end after the project end date (${selectedProject.end_date}).`
    if (claimType === 'additional_advance') {
      if (!parentAdvanceId) return 'Select the original Advance Request.'
      if (!(Number(previousAdvanceAmount) > 0)) return 'The original advance must have a released amount.'
      if (amountAlreadyUsed === '' || Number(amountAlreadyUsed) < 0) return 'Enter how much of the previous advance has already been used.'
    }
    for (const item of items) {
      if (!item.description.trim()) return 'Explain what each expense item is for.'
      if (!(Number(item.amount) > 0)) return 'Every expense item must have an amount greater than zero.'
      if (item.category === 'other' && !item.otherCategory.trim()) return 'Describe the category for every Other expense item.'
      if (claimType === 'reimbursement' && !item.paymentMode) return 'Select how each reimbursable expense was paid.'
    }
    const attachmentCount = existingAttachments.length + files.length
    if (['reimbursement', 'additional_advance'].includes(claimType) && attachmentCount === 0) return 'Attach at least one bill, receipt, invoice, or proof for this request.'
    if (attachmentCount > 8) return 'A claim can contain at most 8 attachments.'
    const tooLarge = files.find(file => file.size > 15 * 1024 * 1024)
    if (tooLarge) return `${tooLarge.name} is larger than 15 MB.`
    return null
  }

  function claimBody() {
    return {
      project_id: Number(projectId),
      claim_type: claimType,
      purpose_description: purpose.trim(),
      requested_work_start_date: requestedWorkStart,
      requested_work_end_date: requestedWorkEnd,
      parent_advance_claim_id: claimType === 'additional_advance' ? Number(parentAdvanceId) : null,
      previous_advance_amount: claimType === 'additional_advance' ? Number(previousAdvanceAmount) : null,
      amount_already_used: claimType === 'additional_advance' ? Number(amountAlreadyUsed) : null,
      items: items.map(item => ({
        category: item.category,
        other_category: item.category === 'other' ? item.otherCategory.trim() : null,
        description: item.description.trim(),
        amount: Number(item.amount),
        payment_mode: claimType === 'reimbursement' ? item.paymentMode : null,
        expense_date: claimType === 'reimbursement' ? (item.expenseDate || null) : null,
      })),
    }
  }

  async function removeExistingAttachment(attachmentId: number) {
    if (!claimId || loading) return
    setLoading(true); setError('')
    try {
      await apiFetch(`/finance/claims/${claimId}/attachments/${attachmentId}`, { method: 'DELETE' })
      setExistingAttachments(current => current.filter(item => item.id !== attachmentId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not remove attachment')
    } finally { setLoading(false) }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    const validation = validateForm()
    if (validation) { setError(validation); return }
    setLoading(true); setError('')
    if (!isEditing) setDraftClaim(null)
    try {
      const workingClaim = isEditing && claimId
        ? await apiFetch<ExpenseClaim>(`/finance/claims/${claimId}`, { method: 'PUT', body: JSON.stringify(claimBody()) })
        : await apiFetch<ExpenseClaim>('/finance/claims', { method: 'POST', body: JSON.stringify(claimBody()) })
      setDraftClaim(workingClaim)
      if (files.length > 0) {
        const formData = new FormData(); files.forEach(file => formData.append('files', file))
        await apiFetch(`/finance/claims/${workingClaim.id}/attachments`, { method: 'POST', body: formData })
      }
      const submitted = await apiFetch<ExpenseClaim>(`/finance/claims/${workingClaim.id}/submit`, { method: 'POST' })
      navigate(`/expenses/${submitted.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not submit the expense claim')
    } finally { setLoading(false) }
  }

  if (initialLoading) return <div className="finance-page"><div className="finance-panel finance-empty-state">Loading project expense form...</div></div>

  return (
    <div className="finance-page">
      <DashboardHeader eyebrow="PROJECT EXPENSES" title={isEditing ? 'Update & Resubmit Expense Claim' : 'Create Project Expense Claim'} description="Project dates, requested work period, amount and supporting proof remain linked to the same auditable Finance workflow." actions={<Link className="finance-secondary-button" to={isEditing && claimId ? `/expenses/${claimId}` : '/expenses'}><ArrowLeft size={16} /> {isEditing ? 'Back to Claim' : 'My Claims'}</Link>} />

      <form className="finance-form-card" onSubmit={submit}>
        <section className="finance-form-section">
          <header><span>STEP 1</span><h2>Project, request type & work period</h2><p>Expenses are allowed only while the selected project is active. Employee-requested dates remain preserved even if Finance later approves a shorter period.</p></header>
          <div className="finance-form-grid">
            <label className="finance-field"><span>Project ID *</span><select value={projectId} onChange={event => changeProject(event.target.value)} required><option value="">Select an ongoing Project ID</option>{projects.map(project => <option key={project.id} value={project.id} disabled={!project.expense_allowed}>{project.project_code} · {project.project_name} · {project.expense_allowed ? 'ACTIVE' : project.lifecycle_status.toUpperCase()}</option>)}</select><small>{openProjectCount > 0 ? `${openProjectCount} active project(s) available. Completed/on-hold/inactive projects are shown for reference but cannot be selected.` : 'No active project is currently open for a new claim. Completed/on-hold/inactive projects are shown for reference.'}</small></label>
            <label className="finance-field"><span>Request Type *</span><select value={claimType} onChange={event => { const next = event.target.value as FinanceClaimType; setClaimType(next); if (next !== 'additional_advance') setParentAdvanceId('') }}><option value="advance">Advance Request</option><option value="reimbursement">Reimbursement</option><option value="additional_advance">Additional Advance</option></select></label>
            {selectedProject && <div className="finance-project-window full"><CalendarDays size={17} /><div><strong>{selectedProject.project_code} · {selectedProject.project_name}</strong><span>{selectedProject.start_date || 'Start not set'} → {selectedProject.end_date || 'End not set'} · {selectedProject.lifecycle_status.replaceAll('_', ' ')}{selectedProject.expense_block_reason ? ` · ${selectedProject.expense_block_reason}` : ''}</span></div></div>}
            <label className="finance-field"><span>Requested Work Start *</span><input type="date" min={selectedProject?.start_date || undefined} max={selectedProject?.end_date || undefined} value={requestedWorkStart} onChange={event => setRequestedWorkStart(event.target.value)} /></label>
            <label className="finance-field"><span>Requested Work End *</span><input type="date" min={requestedWorkStart || selectedProject?.start_date || undefined} max={selectedProject?.end_date || undefined} value={requestedWorkEnd} onChange={event => setRequestedWorkEnd(event.target.value)} /></label>
            <div className="finance-total-strip full"><span>Employee Requested Duration</span><strong>{requestedDays || 0} day(s)</strong></div>
            <label className="finance-field full"><span>Purpose / Description *</span><textarea value={purpose} onChange={event => setPurpose(event.target.value)} placeholder="Explain the work, site visit, purchase, travel, or project activity this money is for." required /></label>
          </div>
          <div className="finance-total-strip"><span>{financeClaimTypeLabels[claimType]}</span><strong>{formatInr(totalAmount)}</strong></div>
        </section>

        {claimType === 'additional_advance' && <section className="finance-form-section"><header><span>ADDITIONAL ADVANCE</span><h2>Link the original company advance</h2><p>The additional request remains part of the original advance chain and will be included in one final settlement.</p></header><div className="finance-form-grid">
          <label className="finance-field full"><span>Original Advance Request *</span><select value={parentAdvanceId} onChange={event => setParentAdvanceId(event.target.value)}><option value="">Select original released advance</option>{eligibleAdvances.map(advance => <option key={advance.id} value={advance.id}>{advance.claim_code} · released {formatInr(advance.paid_amount || 0)} · {advance.project.project_code}</option>)}</select></label>
          <label className="finance-field"><span>Company Advance Already Released</span><input value={previousAdvanceAmount} readOnly placeholder="Calculated from original advance" /></label>
          <label className="finance-field"><span>Amount Already Used *</span><input type="number" min="0" step="0.01" value={amountAlreadyUsed} onChange={event => setAmountAlreadyUsed(event.target.value)} placeholder="0.00" /></label>
        </div>{eligibleAdvances.length === 0 && <p className="finance-help-text">No released original Advance Request is currently eligible for this project.</p>}</section>}

        <section className="finance-form-section">
          <header><span>STEP 2</span><h2>{claimType === 'reimbursement' ? 'Actual reimbursable expense breakup' : 'Item-wise expense breakup'}</h2><p>{claimType === 'reimbursement' ? 'Enter the actual personally-paid expenses. The sum of these items is the reimbursement amount.' : 'Add hotel, food, travel, fuel, machine parts, site expenses, or any other planned expense separately.'}</p></header>
          <div className="finance-line-items">{items.map((item, index) => <div className="finance-line-item" key={item.id}>
            <label className="finance-field"><span>Category {index + 1}</span><select value={item.category} onChange={event => updateItem(item.id, { category: event.target.value })}>{financeExpenseCategories.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label className="finance-field"><span>What was / will be used for *</span><input value={item.description} onChange={event => updateItem(item.id, { description: event.target.value })} placeholder="Example: hotel for project site survey" /></label>
            <label className="finance-field"><span>Amount *</span><input type="number" min="0" step="0.01" value={item.amount} onChange={event => updateItem(item.id, { amount: event.target.value })} placeholder="0.00" /></label>
            <button className="finance-icon-button" type="button" onClick={() => removeItem(item.id)} aria-label="Remove expense item"><Trash2 size={17} /></button>
            {claimType === 'reimbursement' && <><label className="finance-field"><span>Payment Mode *</span><select value={item.paymentMode} onChange={event => updateItem(item.id, { paymentMode: event.target.value as FinancePaymentMode })}><option value="upi">UPI</option><option value="cash">Cash</option><option value="card">Card</option><option value="bank_transfer">Bank Transfer</option><option value="cheque">Cheque</option><option value="other">Other</option></select></label><label className="finance-field"><span>Expense Date</span><input type="date" value={item.expenseDate} onChange={event => updateItem(item.id, { expenseDate: event.target.value })} /></label></>}
            {item.category === 'other' && <label className="finance-field finance-line-item-other"><span>Other Category *</span><input value={item.otherCategory} onChange={event => updateItem(item.id, { otherCategory: event.target.value })} placeholder="Type the actual expense category" /></label>}
          </div>)}</div>
          <div className="finance-toolbar"><button className="finance-secondary-button" type="button" onClick={() => setItems(current => [...current, newItem()])}><Plus size={16} /> Add Expense Item</button><div className="finance-total-strip"><span>Total Claim Amount</span><strong>{formatInr(totalAmount)}</strong></div></div>
        </section>

        <section className="finance-form-section"><header><span>STEP 3</span><h2>Supporting bills / proof</h2><p>Reimbursement and Additional Advance require proof before submission. Advance settlement bills are uploaded later against the same released Advance Request.</p></header>
          {existingAttachments.length > 0 && <div className="finance-existing-files">{existingAttachments.map(attachment => <div key={attachment.id} className="finance-existing-file"><FileText size={16}/><span>{attachment.original_filename}</span>{canRemoveExistingAttachments && <button type="button" title="Remove attachment" onClick={() => void removeExistingAttachment(attachment.id)}><X size={15}/></button>}</div>)}</div>}
          {isEditing && !canRemoveExistingAttachments && existingAttachments.length > 0 && <p className="finance-help-text">Previously submitted proof is retained permanently for audit. Add corrected proof below; earlier evidence is not deleted.</p>}
          <div className="finance-upload-zone"><UploadCloud size={22}/><input type="file" multiple accept="application/pdf,image/jpeg,image/png,image/webp" onChange={event => setFiles(Array.from(event.target.files || []))}/><p>PDF, JPG, PNG or WebP · maximum 8 files total · 15 MB per file.</p>{files.length > 0 && <p><strong>{files.length}</strong> new file(s): {files.map(file => file.name).join(', ')}</p>}</div>
        </section>

        {draftClaim && error && <div className="finance-error">Claim <strong>{draftClaim.claim_code}</strong> is safely retained. {error}</div>}
        {!draftClaim && error && <div className="finance-error">{error}</div>}
        <div className="finance-toolbar"><div className="finance-help-text"><FileText size={15}/> Submission goes to Admin first; Finance receives it after Admin verification.</div><button className="finance-primary-button" type="submit" disabled={loading || projects.length === 0}><Send size={16}/> {loading ? 'Submitting...' : isEditing ? 'Update & Resubmit Claim' : 'Submit Expense Claim'}</button></div>
      </form>
    </div>
  )
}
