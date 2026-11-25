
import {
  useCallback, useEffect, useState,
  type FormEvent,
} from 'react'

import { useSearchParams } from 'react-router-dom'

import {
  Archive, BookOpen, CheckCircle2, ClipboardCheck,
  Download, FileText, Plus, RefreshCw, Upload,
} from 'lucide-react'

import { useAuth } from '../../context/AuthContext'
import { apiFetch, apiBlob, downloadFile } from '../../lib/api'

import './organisation-policies.css'


const BASE = '/organisation-policies'

type PolicyVersion = {
  id: number
  number: number
  revision: number
  title: string
  category: string
  content: string
  revision_notes: string
  has_pdf: boolean
  pdf_name: string | null
  effective_date: string | null
  published_at: string | null
}

type Policy = {
  id: number
  archived: boolean
  published: PolicyVersion | null
  draft: PolicyVersion | null
  acknowledged_at: string | null
}

type Library = {
  policies: Policy[]
  reminder_hours: number
  declaration: string
}

type ComplianceRow = {
  user_id: number
  employee_id: string
  employee_name: string
  department: string
  policy_id: number
  policy_title: string
  version: number
  acknowledged_at: string | null
  pending_days: number
  overdue: boolean
}

type AckRecord = {
  title: string
  version: number
  acknowledged_at: string
}

type DraftForm = {
  policyId: number | null
  baseId: number | null
  revision: number | null
  title: string
  category: string
  content: string
  effectiveDate: string
  notes: string
  existingPdf: string | null
  removePdf: boolean
}

const blankDraft: DraftForm = {
  policyId: null,
  baseId: null,
  revision: null,
  title: '',
  category: 'General Company Policies',
  content: '',
  effectiveDate: '',
  notes: '',
  existingPdf: null,
  removePdf: false,
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : 'Not specified'
}

function errorText(error: unknown) {
  return error instanceof Error
    ? error.message
    : 'Unable to complete the request.'
}


export function OrganisationPoliciesPage() {
  const { user } = useAuth()
  const isHR = user?.role === 'hr'

  const [params, setParams] = useSearchParams()
  const selectedId = Number(params.get('policy') || 0)

  const [library, setLibrary] = useState<Library | null>(null)
  const [tab, setTab] = useState('policies')
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const [form, setForm] = useState<DraftForm | null>(null)
  const [upload, setUpload] = useState<File | null>(null)

  const [defaultFiles, setDefaultFiles] = useState<File[]>([])
  const [importConfirmed, setImportConfirmed] = useState(false)

  const [versions, setVersions] = useState<PolicyVersion[]>([])
  const [viewId, setViewId] = useState<number | null>(null)
  const [pdfUrl, setPdfUrl] = useState('')
  const [pdfError, setPdfError] = useState('')
  const [confirmed, setConfirmed] = useState(false)

  const [reportRows, setReportRows] = useState<ComplianceRow[]>([])
  const [reportSearch, setReportSearch] = useState('')
  const [reportStatus, setReportStatus] = useState('all')
  const [reportPolicy, setReportPolicy] = useState('all')

  const [history, setHistory] = useState<AckRecord[]>([])
  const [reminderInput, setReminderInput] = useState('24')

  const reload = useCallback(async () => {
    const result = await apiFetch<Library>(BASE)
    setLibrary(result)
  }, [])

  useEffect(() => {
    if (user?.role === 'hr' || user?.role === 'employee') {
      void reload().catch(err => setError(errorText(err)))
    }
  }, [reload, user?.role, user?.email])

  useEffect(() => {
    if (library) {
      setReminderInput(String(library.reminder_hours))
    }
  }, [library?.reminder_hours])

  useEffect(() => {
    setViewId(null)
    setConfirmed(false)
    setVersions([])

    if (!isHR || !selectedId) return

    let active = true

    void apiFetch<{ versions: PolicyVersion[] }>(
      `${BASE}/${selectedId}/versions`
    ).then(result => {
      if (active) setVersions(result.versions)
    }).catch(err => {
      if (active) setError(errorText(err))
    })

    return () => { active = false }
  }, [isHR, selectedId, library])

  useEffect(() => {
    let active = true

    if (isHR && tab === 'compliance') {
      void apiFetch<{ rows: ComplianceRow[] }>(
        `${BASE}/compliance`
      ).then(result => {
        if (active) setReportRows(result.rows)
      }).catch(err => {
        if (active) setError(errorText(err))
      })
    }

    if (!isHR && tab === 'history') {
      void apiFetch<{ records: AckRecord[] }>(
        `${BASE}/my-acknowledgements`
      ).then(result => {
        if (active) setHistory(result.records)
      }).catch(err => {
        if (active) setError(errorText(err))
      })
    }

    return () => { active = false }
  }, [isHR, tab, library])

  const policies = library?.policies ?? []

  const selected = policies.find(p => p.id === selectedId)

  const latest = isHR
    ? selected?.draft ?? selected?.published
    : selected?.published

  const view = isHR && viewId
    ? versions.find(v => v.id === viewId) ?? latest
    : latest

  useEffect(() => {
    setPdfUrl('')
    setPdfError('')
    setConfirmed(false)

    if (!selectedId || !view?.id || !view.has_pdf) return

    let active = true
    let objectUrl = ''

    void apiBlob(
      `${BASE}/${selectedId}/versions/${view.id}/document`
    ).then(blob => {
      if (!active) return

      objectUrl = URL.createObjectURL(blob)
      setPdfUrl(objectUrl)
    }).catch(err => {
      if (active) setPdfError(errorText(err))
    })

    return () => {
      active = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [selectedId, view?.id, view?.revision, view?.has_pdf])

  async function perform(
    action: () => Promise<void>,
    message: string,
  ) {
    if (busy) return

    setBusy(true)
    setError('')
    setNotice('')

    try {
      await action()
      await reload()
      if (message) setNotice(message)
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  function choosePolicy(id: number) {
    setParams(id ? { policy: String(id) } : {})
    setForm(null)
    setViewId(null)
    setConfirmed(false)
  }

  function newDraft() {
    setForm({ ...blankDraft })
    setUpload(null)
    setTab('policies')
  }

  function editDraft(policy: Policy) {
    const base = policy.draft ?? policy.published

    if (!base) return

    setForm({
      policyId: policy.id,
      baseId: base.id,
      revision: base.revision,
      title: base.title,
      category: base.category,
      content: base.content,
      effectiveDate: base.effective_date || '',
      notes: base.revision_notes,
      existingPdf: base.pdf_name,
      removePdf: false,
    })

    setUpload(null)
  }

  function changeForm<K extends keyof DraftForm>(
    field: K, value: DraftForm[K],
  ) {
    setForm(previous => (
      previous ? { ...previous, [field]: value } : previous
    ))
  }

  async function saveDraft(event: FormEvent) {
    event.preventDefault()

    if (!form) return

    const body = new FormData()

    body.append('title', form.title)
    body.append('category', form.category)
    body.append('content', form.content)
    body.append('effective_date', form.effectiveDate)
    body.append('revision_notes', form.notes)
    body.append('remove_pdf', String(form.removePdf))

    if (form.baseId !== null) {
      body.append('expected_version_id', String(form.baseId))
      body.append('expected_revision', String(form.revision))
    }

    if (upload) {
      body.append('pdf', upload)
    }

    await perform(async () => {
      const saved = await apiFetch<Policy>(
        form.policyId
          ? `${BASE}/${form.policyId}/draft`
          : BASE,
        {
          method: form.policyId ? 'PATCH' : 'POST',
          body,
        },
      )

      setForm(null)
      setUpload(null)
      choosePolicy(saved.id)

    }, 'Policy draft saved successfully.')
  }

  async function importDefaults() {
    if (defaultFiles.length !== 11 || !importConfirmed) return

    await perform(async () => {
      const body = new FormData()

      defaultFiles.forEach(file => {
        body.append('documents', file)
      })

      body.append('confirmed', 'true')

      const result = await apiFetch<{
        created: number
        skipped: number
      }>(`${BASE}/defaults/import`, {
        method: 'POST',
        body,
      })

      setDefaultFiles([])
      setImportConfirmed(false)

      setNotice(
        `${result.created} policies imported and published. ` +
        `${result.skipped} existing policies skipped.`
      )

    }, '')
  }

  async function publishPolicy(policy: Policy) {
    if (!policy.draft) return

    const draft = policy.draft

    if (!window.confirm(
      `Publish "${draft.title}"? Employees will be notified ` +
      'and must acknowledge this version.'
    )) return

    await perform(async () => {
      await apiFetch(`${BASE}/${policy.id}/publish`, {
        method: 'POST',
        body: JSON.stringify({
          version_id: draft.id,
          revision: draft.revision,
        }),
      })

    }, 'Policy published. Employees have been notified.')
  }

  async function archivePolicy(policy: Policy) {
    if (!window.confirm(
      'Archive this policy? It will disappear from employee ' +
      'view, while previous versions and records are retained.'
    )) return

    await perform(async () => {
      await apiFetch(`${BASE}/${policy.id}/archive`, {
        method: 'POST',
      })

      choosePolicy(0)

    }, 'Policy archived successfully.')
  }

  async function acknowledge() {
    if (
      !selected ||
      !selected.published ||
      !confirmed ||
      selected.acknowledged_at
    ) return

    const version = selected.published

    await perform(async () => {
      await apiFetch(`${BASE}/${selected.id}/acknowledge`, {
        method: 'POST',
        body: JSON.stringify({
          version_id: version.id,
          confirmed: true,
        }),
      })

      setConfirmed(false)

    }, 'Acknowledgement recorded successfully.')
  }

  async function saveReminderSettings() {
    await perform(async () => {
      await apiFetch(`${BASE}/settings`, {
        method: 'PUT',
        body: JSON.stringify({
          reminder_hours: Number(reminderInput),
        }),
      })

    }, 'Reminder settings updated.')
  }

  const activePolicies = policies.filter(p => !p.archived)
  const published = activePolicies.filter(p => p.published)
  const acknowledged = published.filter(p => p.acknowledged_at)
  const pending = published.length - acknowledged.length

  const progress = published.length
    ? Math.round(acknowledged.length / published.length * 100)
    : 0

  const visiblePolicies = policies.filter(policy => {
    if (tab === 'archive' ? !policy.archived : policy.archived) {
      return false
    }

    const version = policy.draft ?? policy.published
    const query = search.trim().toLowerCase()

    if (
      query &&
      !`${version?.title || ''} ${version?.category || ''}`
        .toLowerCase().includes(query)
    ) return false

    if (!isHR && filter === 'pending' && policy.acknowledged_at) {
      return false
    }

    if (!isHR && filter === 'acknowledged' && !policy.acknowledged_at) {
      return false
    }

    return true
  })

  const filteredReport = reportRows.filter(row => {
    const query = reportSearch.trim().toLowerCase()

    if (
      query &&
      !`${row.employee_name} ${row.employee_id} ${row.department}`
        .toLowerCase().includes(query)
    ) return false

    if (
      reportPolicy !== 'all' &&
      String(row.policy_id) !== reportPolicy
    ) return false

    if (
      reportStatus === 'pending' &&
      row.acknowledged_at
    ) return false

    if (
      reportStatus === 'acknowledged' &&
      !row.acknowledged_at
    ) return false

    if (reportStatus === 'overdue' && !row.overdue) {
      return false
    }

    return true
  })

  if (user?.role !== 'hr' && user?.role !== 'employee') {
    return <p>Access denied.</p>
  }

  return (
    <main className="op-page">

      <header className="op-hero">
        <div>
          <div className="op-eyebrow">NAKSHATECH · HUMAN RESOURCES</div>
          <h1><BookOpen size={28} /> Organisation Policies</h1>
          <p>
            {isHR
              ? 'Publish official policies and monitor employee acknowledgements.'
              : 'Read the official company policies and complete your acknowledgements.'}
          </p>
        </div>

        <div className="op-actions">
          <button
            className="op-btn op-light"
            disabled={busy}
            onClick={() => void perform(async () => {}, '')}
          >
            <RefreshCw size={16} /> Refresh
          </button>

          {isHR && (
            <button
              className="op-btn op-light"
              disabled={busy}
              onClick={newDraft}
            >
              <Plus size={18} /> Add New Policy
            </button>
          )}
        </div>
      </header>

      {error && (
        <div className="op-error" role="alert">{error}</div>
      )}

      {notice && (
        <div className="op-success" role="status">{notice}</div>
      )}

      {!library ? (
        <section className="op-card">
          Loading organisation policies...
        </section>
      ) : (
        <>
          <div className="op-stats">
            <div className="op-card">
              <span>Total Policies</span>
              <strong>{activePolicies.length}</strong>
            </div>

            <div className="op-card">
              <span>{isHR ? 'Published' : 'Acknowledged'}</span>
              <strong>
                {isHR ? published.length : acknowledged.length}
              </strong>
            </div>

            <div className="op-card">
              <span>{isHR ? 'Drafts' : 'Pending'}</span>
              <strong>
                {isHR
                  ? activePolicies.filter(p => p.draft).length
                  : pending}
              </strong>
            </div>

            <div className="op-card">
              <span>{isHR ? 'Archived' : 'Your Progress'}</span>
              <strong>
                {isHR
                  ? policies.filter(p => p.archived).length
                  : `${progress}%`}
              </strong>
            </div>
          </div>

          {!isHR && (
            <section className="op-card">
              <div className="op-between">
                <strong>Policy Acknowledgement Progress</strong>
                <span>{acknowledged.length}/{published.length}</span>
              </div>

              <div className="op-progress">
                <div style={{ width: `${progress}%` }} />
              </div>

              <p className="op-muted">
                {pending
                  ? `${pending} policies still require your acknowledgement.`
                  : published.length
                    ? 'All current policies are acknowledged. Policy reminders will stop.'
                    : 'No policies have been published yet.'}
              </p>
            </section>
          )}

          <nav className="op-tabs">
            {[
              ['policies', 'Policies'],
              ...(isHR
                ? [
                    ['compliance', 'Compliance Tracking'],
                    ['archive', 'Archived Policies'],
                  ]
                : [['history', 'My Acknowledgements']]),
            ].map(([value, label]) => (
              <button
                key={value}
                className={tab === value ? 'active' : ''}
                disabled={busy}
                onClick={() => {
                  setTab(value)
                  setForm(null)
                  setError('')
                }}
              >
                {label}
              </button>
            ))}
          </nav>

          {isHR && tab === 'policies' && (
            <details className="op-card">
              <summary>
                <Upload size={17} /> Import 11 Default Company Policies
              </summary>

              <p className="op-muted">
                Select the 11 original NakshaTech PDF files together.
                Existing policies will not be duplicated or overwritten.
              </p>

              <input
                type="file"
                accept=".pdf,application/pdf"
                multiple
                disabled={busy}
                onChange={event => {
                  setDefaultFiles(Array.from(event.target.files || []))
                  setImportConfirmed(false)
                }}
              />

              <p>{defaultFiles.length}/11 documents selected</p>

              <label className="op-check">
                <input
                  type="checkbox"
                  checked={importConfirmed}
                  disabled={busy}
                  onChange={event => setImportConfirmed(event.target.checked)}
                />
                I confirm these are the official policy documents
                approved for initial publication.
              </label>

              <button
                className="op-btn"
                disabled={
                  busy ||
                  defaultFiles.length !== 11 ||
                  !importConfirmed
                }
                onClick={() => void importDefaults()}
              >
                <Upload size={16} /> Import & Publish Defaults
              </button>
            </details>
          )}

          {form && isHR && (
            <section className="op-card">
              <h2>
                {form.policyId ? 'Edit Policy Draft' : 'Create New Policy'}
              </h2>

              <form className="op-form" onSubmit={saveDraft}>
                <label>
                  Policy Title
                  <input
                    required
                    maxLength={200}
                    value={form.title}
                    onChange={e => changeForm('title', e.target.value)}
                  />
                </label>

                <label>
                  Category
                  <input
                    required
                    list="op-categories"
                    value={form.category}
                    maxLength={100}
                    onChange={e => changeForm('category', e.target.value)}
                  />
                  <datalist id="op-categories">
                    {[
                      'Attendance',
                      'Leave Management',
                      'Workplace Discipline',
                      'IT & Security',
                      'Employee Benefits',
                      'Performance Management',
                      'Holidays',
                      'General Company Policies',
                    ].map(category => (
                      <option key={category} value={category} />
                    ))}
                  </datalist>
                </label>

                <label>
                  Effective Date
                  <input
                    type="date"
                    value={form.effectiveDate}
                    onChange={e =>
                      changeForm('effectiveDate', e.target.value)
                    }
                  />
                </label>

                <label>
                  Policy Content
                  <textarea
                    rows={10}
                    maxLength={100000}
                    value={form.content}
                    onChange={e => changeForm('content', e.target.value)}
                    placeholder="Enter the official company policy text..."
                  />
                </label>

                <label>
                  PDF Document
                  <input
                    type="file"
                    accept=".pdf,application/pdf"
                    onChange={e => setUpload(e.target.files?.[0] ?? null)}
                  />
                </label>

                {form.existingPdf && (
                  <>
                    <p className="op-muted">
                      Existing PDF: {form.existingPdf}
                    </p>

                    <label className="op-check">
                      <input
                        type="checkbox"
                        checked={form.removePdf}
                        onChange={e =>
                          changeForm('removePdf', e.target.checked)
                        }
                      />
                      Remove existing PDF from this draft
                    </label>
                  </>
                )}

                <label>
                  Revision Notes
                  <textarea
                    rows={3}
                    maxLength={2000}
                    value={form.notes}
                    onChange={e => changeForm('notes', e.target.value)}
                  />
                </label>

                <div className="op-actions">
                  <button
                    type="button"
                    className="op-btn op-secondary"
                    disabled={busy}
                    onClick={() => setForm(null)}
                  >
                    Cancel
                  </button>

                  <button className="op-btn" disabled={busy}>
                    {busy ? 'Saving...' : 'Save Draft'}
                  </button>
                </div>
              </form>
            </section>
          )}

          {(tab === 'policies' || tab === 'archive') && (
            <div className="op-library-grid">

              <section className="op-card">
                <h2>
                  {tab === 'archive'
                    ? 'Archived Policies'
                    : 'Policy Library'}
                </h2>

                <input
                  className="op-search"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Search policy name or category..."
                />

                {!isHR && (
                  <select
                    value={filter}
                    onChange={e => setFilter(e.target.value)}
                  >
                    <option value="all">All Policies</option>
                    <option value="pending">Pending Acknowledgement</option>
                    <option value="acknowledged">Acknowledged</option>
                  </select>
                )}

                <div className="op-policy-list">
                  {visiblePolicies.map(policy => {
                    const version = policy.draft ?? policy.published

                    const status = policy.archived
                      ? 'Archived'
                      : isHR
                        ? policy.draft
                          ? policy.published
                            ? 'Published + New Draft'
                            : 'Draft'
                          : 'Published'
                        : policy.acknowledged_at
                          ? 'Acknowledged'
                          : 'Pending Acknowledgement'

                    return (
                      <button
                        key={policy.id}
                        disabled={busy}
                        className={
                          `op-policy-item ${selectedId === policy.id ? 'selected' : ''}`
                        }
                        onClick={() => choosePolicy(policy.id)}
                      >
                        <FileText size={21} />

                        <div>
                          <strong>{version?.title}</strong>

                          <small>{version?.category}</small>

                          <small>
                            Version {version?.number} · {status}
                          </small>
                        </div>
                      </button>
                    )
                  })}

                  {!visiblePolicies.length && (
                    <p className="op-muted">No policies found.</p>
                  )}
                </div>
              </section>

              <section className="op-card op-reader">
                {!selected || !view ? (
                  <div className="op-empty">
                    <BookOpen size={42} />
                    <h2>Select a policy</h2>
                    <p>
                      Choose a document from the policy library
                      to read its complete details.
                    </p>
                  </div>
                ) : (
                  <>
                    <div className="op-between">
                      <div>
                        <h2>{view.title}</h2>
                        <p className="op-muted">
                          {view.category} · Version {view.number}
                        </p>
                      </div>

                      <span className="op-chip">
                        {selected.archived
                          ? 'Archived'
                          : view.published_at
                            ? 'Published'
                            : 'Draft'}
                      </span>
                    </div>

                    <p className="op-muted">
                      Effective date: {view.effective_date || 'Not specified'}
                    </p>

                    {isHR && versions.length > 0 && (
                      <label className="op-field">
                        Policy Version History
                        <select
                          value={viewId ?? latest?.id}
                          onChange={e => setViewId(Number(e.target.value))}
                        >
                          {versions.map(version => (
                            <option key={version.id} value={version.id}>
                              Version {version.number} — {
                                version.published_at
                                  ? 'Published'
                                  : 'Draft'
                              }
                            </option>
                          ))}
                        </select>
                      </label>
                    )}

                    {view.content && (
                      <article className="op-policy-text">
                        {view.content}
                      </article>
                    )}

                    {view.has_pdf && (
                      <div className="op-document">
                        <div className="op-between">
                          <strong>
                            <FileText size={16} /> Official PDF
                          </strong>

                          {pdfUrl && (
                            <a
                              href={pdfUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              Open full document
                            </a>
                          )}
                        </div>

                        {pdfError ? (
                          <p className="op-error">{pdfError}</p>
                        ) : pdfUrl ? (
                          <iframe
                            title={view.title}
                            src={pdfUrl}
                            className="op-pdf-viewer"
                          />
                        ) : (
                          <p>Loading PDF...</p>
                        )}
                      </div>
                    )}

                    {isHR && !selected.archived && (
                      <div className="op-actions">
                        <button
                          className="op-btn op-secondary"
                          disabled={busy}
                          onClick={() => editDraft(selected)}
                        >
                          Edit Policy
                        </button>

                        {selected.draft && (
                          <button
                            className="op-btn"
                            disabled={
                              busy ||
                              view.id !== selected.draft.id
                            }
                            onClick={() => void publishPolicy(selected)}
                          >
                            Publish Draft
                          </button>
                        )}

                        <button
                          className="op-btn op-danger"
                          disabled={busy}
                          onClick={() => void archivePolicy(selected)}
                        >
                          <Archive size={16} /> Archive
                        </button>
                      </div>
                    )}

                    {!isHR && (
                      <section className="op-ack-panel">
                        {selected.acknowledged_at ? (
                          <>
                            <h3>
                              <CheckCircle2 size={20} />
                              Acknowledged
                            </h3>
                            <p>
                              Recorded on {
                                formatDate(selected.acknowledged_at)
                              }
                            </p>
                            <p>
                              No further reminders will be sent
                              for this policy version.
                            </p>
                          </>
                        ) : (
                          <>
                            <h3>
                              <ClipboardCheck size={20} />
                              Read & Acknowledge
                            </h3>

                            <label className="op-check">
                              <input
                                type="checkbox"
                                checked={confirmed}
                                disabled={
                                  busy ||
                                  (view.has_pdf && !pdfUrl)
                                }
                                onChange={e => setConfirmed(e.target.checked)}
                              />
                              {library.declaration}
                            </label>

                            <button
                              className="op-btn"
                              disabled={
                                busy ||
                                !confirmed ||
                                (view.has_pdf && !pdfUrl)
                              }
                              onClick={() => void acknowledge()}
                            >
                              Submit Acknowledgement
                            </button>
                          </>
                        )}
                      </section>
                    )}
                  </>
                )}
              </section>
            </div>
          )}

          {isHR && tab === 'compliance' && (
            <>
              <section className="op-card">
                <h2>Automatic Reminder Settings</h2>

                <p className="op-muted">
                  Only employees with pending current policy
                  acknowledgements will receive reminders.
                </p>

                <div className="op-actions">
                  <label className="op-field">
                    Reminder interval (hours)
                    <input
                      type="number"
                      min={1}
                      max={168}
                      value={reminderInput}
                      onChange={e => setReminderInput(e.target.value)}
                    />
                  </label>

                  <button
                    className="op-btn"
                    disabled={
                      busy ||
                      Number(reminderInput) < 1 ||
                      Number(reminderInput) > 168 ||
                      !Number.isInteger(Number(reminderInput))
                    }
                    onClick={() => void saveReminderSettings()}
                  >
                    Save Settings
                  </button>
                </div>
              </section>

              <section className="op-card">
                <div className="op-between">
                  <h2>Employee Compliance</h2>

                  <button
                    className="op-btn"
                    disabled={busy}
                    onClick={() => void perform(async () => {
                      await downloadFile(
                        `${BASE}/compliance/export`,
                        'organisation_policy_compliance.xlsx'
                      )
                    }, '')}
                  >
                    <Download size={16} /> Export Excel
                  </button>
                </div>

                <div className="op-filters">
                  <input
                    value={reportSearch}
                    onChange={e => setReportSearch(e.target.value)}
                    placeholder="Employee name, ID or department..."
                  />

                  <select
                    value={reportPolicy}
                    onChange={e => setReportPolicy(e.target.value)}
                  >
                    <option value="all">All Policies</option>

                    {published.map(policy => (
                      <option key={policy.id} value={policy.id}>
                        {policy.published?.title}
                      </option>
                    ))}
                  </select>

                  <select
                    value={reportStatus}
                    onChange={e => setReportStatus(e.target.value)}
                  >
                    <option value="all">All Statuses</option>
                    <option value="pending">Pending</option>
                    <option value="acknowledged">Acknowledged</option>
                    <option value="overdue">Overdue — 7+ days</option>
                  </select>
                </div>

                <p className="op-muted">
                  {filteredReport.length} acknowledgement records
                </p>

                <div className="op-table-scroll">
                  <table className="op-table">
                    <thead>
                      <tr>
                        <th>Employee</th>
                        <th>Department</th>
                        <th>Policy</th>
                        <th>Version</th>
                        <th>Status</th>
                        <th>Acknowledged At</th>
                        <th>Pending Days</th>
                      </tr>
                    </thead>

                    <tbody>
                      {filteredReport.map(row => (
                        <tr key={`${row.user_id}-${row.policy_id}`}>
                          <td>
                            <strong>{row.employee_name}</strong>
                            <small>{row.employee_id}</small>
                          </td>
                          <td>{row.department}</td>
                          <td>{row.policy_title}</td>
                          <td>{row.version}</td>
                          <td>
                            <span className={
                              row.acknowledged_at
                                ? 'op-status-green'
                                : row.overdue
                                  ? 'op-status-red'
                                  : 'op-status-orange'
                            }>
                              {row.acknowledged_at
                                ? 'Acknowledged'
                                : row.overdue
                                  ? 'Overdue'
                                  : 'Pending'}
                            </span>
                          </td>
                          <td>
                            {row.acknowledged_at
                              ? formatDate(row.acknowledged_at)
                              : '—'}
                          </td>
                          <td>{row.pending_days}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>

                  {!filteredReport.length && (
                    <p className="op-muted">
                      No matching acknowledgement records.
                    </p>
                  )}
                </div>
              </section>
            </>
          )}

          {!isHR && tab === 'history' && (
            <section className="op-card">
              <h2>My Acknowledgement History</h2>

              {history.map((record, index) => (
                <div className="op-history-item" key={index}>
                  <CheckCircle2 size={20} />

                  <div>
                    <strong>{record.title}</strong>
                    <p className="op-muted">
                      Version {record.version} · {
                        formatDate(record.acknowledged_at)
                      }
                    </p>
                  </div>
                </div>
              ))}

              {!history.length && (
                <p className="op-muted">
                  No policies acknowledged yet.
                </p>
              )}
            </section>
          )}
        </>
      )}
    </main>
  )
}
