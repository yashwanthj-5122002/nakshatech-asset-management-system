
import { useRef, useState } from 'react'
import { Navigate } from 'react-router-dom'
import {
  BrainCircuit,
  ClipboardCheck,
  FileText,
  MessageSquareText,
  RotateCcw,
  Sparkles,
} from 'lucide-react'

import { useAuth } from '../../context/AuthContext'
import { roleHomePath } from '../../lib/roles'
import { apiFetch } from '../../lib/api'
import { canAccessBDAI } from './access'

import {
  BDSubmissionPanel,
  type BDAIContext,
  type BDAIAnalysis,
  type BDAIAnswer,
  type SubmissionSnapshot,
  type SubmissionRow,
  type SubmissionDetail,
} from './BDSubmissionPanel'

import './bd-ai.css'

const departments = [
  'GIS',
  'LiDAR',
  'Orthophoto',
  'Photogrammetry',
  'Mobile Mapping',
  'Laser Scanning',
  'Civil',
  'BIM',
]

const emptyContext: BDAIContext = {
  client_name: '',
  project_reference: '',
  department: '',
  requirements: '',
}

export function BDAIPage() {
  const { user } = useAuth()

  if (!user || !canAccessBDAI(user)) {
    return (
      <Navigate
        to={user ? roleHomePath(user.role) : '/login'}
        replace
      />
    )
  }

  return (
    <BDAIWorkspace
      key={`${user.role}:${user.email}`}
      isEmployee={user.role === 'bd_employee'}
      isManager={user.role === 'bd'}
    />
  )
}

function BDAIWorkspace({
  isEmployee,
  isManager,
}: {
  isEmployee: boolean
  isManager: boolean
}) {
  const [context, setContext] = useState<BDAIContext>({ ...emptyContext })
  const [analysis, setAnalysis] = useState<BDAIAnalysis | null>(null)
  const [answer, setAnswer] = useState('')
  const [answers, setAnswers] = useState<BDAIAnswer[]>([])

  const [approvedForAI, setApprovedForAI] = useState(false)
  const [humanVerified, setHumanVerified] = useState(false)
  const [pendingAcknowledged, setPendingAcknowledged] = useState(false)

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [submitted, setSubmitted] = useState<SubmissionRow | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  const [revision, setRevision] = useState<{
    id: number
    reference: string
    number: number
    managerNote: string
  } | null>(null)

  const [revisionNote, setRevisionNote] = useState('')

  const actionLock = useRef(false)

  const currentQuestion =
    analysis?.clarification_questions.find(item => item.trim()) || ''

  const pendingQuestions =
    analysis?.clarification_questions.filter(item => item.trim()).length || 0

  const hasMissingInformation = Boolean(
    analysis?.missing_information.some(item => item.trim())
  )

  const formLocked = busy || Boolean(submitted)

  const canFinalize = Boolean(
    isEmployee &&
    analysis &&
    context.client_name.trim() &&
    context.project_reference.trim() &&
    context.department.trim() &&
    context.requirements.trim().length >= 20 &&
    analysis.project_objective.trim() &&
    analysis.scope_of_work.trim() &&
    pendingQuestions === 0 &&
    humanVerified &&
    (!hasMissingInformation || pendingAcknowledged) &&
    (!revision || revisionNote.trim()) &&
    !busy &&
    !submitted
  )

  function invalidateVerification() {
    setHumanVerified(false)
    setPendingAcknowledged(false)
  }

  function changeContext(field: keyof BDAIContext, value: string) {
    if (formLocked || actionLock.current) return

    setContext(previous => ({
      ...previous,
      [field]: value,
    }))

    setAnalysis(null)
    setAnswer('')
    setAnswers([])
    setApprovedForAI(false)
    invalidateVerification()
    setNotice('')
    setError('')
  }

  function clearDraft() {
    if (actionLock.current) return

    if (
      !submitted &&
      (analysis || Object.values(context).some(value => value.trim())) &&
      !window.confirm('Clear the current unsaved draft?')
    ) return

    setContext({ ...emptyContext })
    setAnalysis(null)
    setAnswer('')
    setAnswers([])
    setApprovedForAI(false)
    invalidateVerification()
    setSubmitted(null)
    setRevision(null)
    setRevisionNote('')
    setNotice('')
    setError('')
  }

  async function run(task: () => Promise<void>) {
    if (actionLock.current) return

    actionLock.current = true
    setBusy(true)
    setError('')

    try {
      await task()
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to complete the request.'
      )
    } finally {
      actionLock.current = false
      setBusy(false)
    }
  }

  async function generateSummary() {
    if (
      formLocked ||
      analysis ||
      !approvedForAI ||
      context.requirements.trim().length < 20
    ) return

    await run(async () => {
      const result = await apiFetch<BDAIAnalysis>(
        '/bd-ai/summarize',
        {
          method: 'POST',
          body: JSON.stringify(context),
        }
      )

      setAnalysis(result)
      setAnswer('')
      setAnswers([])
      invalidateVerification()
      setNotice('')
    })
  }

  async function submitAnswer() {
    if (
      formLocked ||
      !approvedForAI ||
      !analysis ||
      !answer.trim()
    ) return

    if (answers.length >= 100) {
      setError('The clarification history limit has been reached.')
      return
    }

    const entry: BDAIAnswer = {
      question: currentQuestion || 'Additional client clarification or correction',
      answer: answer.trim(),
    }

    if (entry.question.length > 500) {
      setError('The generated question exceeds the backend length limit.')
      return
    }

    await run(async () => {
      const result = await apiFetch<BDAIAnalysis>(
        '/bd-ai/refine',
        {
          method: 'POST',
          body: JSON.stringify({
            context,
            previous: analysis,
            answers: [entry],
          }),
        }
      )

      setAnalysis(result)
      setAnswers(previous => [...previous, entry])
      setAnswer('')
      invalidateVerification()
      setNotice('')
    })
  }

  async function finalizeSubmission() {
    if (!canFinalize || !analysis || actionLock.current) return

    if (!window.confirm(
      revision
        ? 'Resubmit this revised technical brief to the BD Manager?'
        : 'Finalize and send this verified technical brief to the BD Manager?'
    )) return

    const payload: SubmissionSnapshot = {
      context,
      analysis,
      answers,
      human_verified: humanVerified,
      pending_acknowledged: pendingAcknowledged,
      revision_note: revisionNote.trim(),
    }

    await run(async () => {
      const endpoint = revision
        ? `/bd-ai/submissions/${revision.id}/resubmit`
        : '/bd-ai/submissions'

      const body = revision
        ? { ...payload, expected_revision: revision.number }
        : payload

      const result = await apiFetch<SubmissionRow>(
        endpoint,
        {
          method: 'POST',
          body: JSON.stringify(body),
        }
      )

      setSubmitted(result)
      setRefreshKey(value => value + 1)

      setNotice(
        result.already_submitted
          ? `${result.reference} already exists. View its status in My Submissions.`
          : `${result.reference} successfully submitted to the BD Manager.`
      )
    })
  }

  function beginRevision(detail: SubmissionDetail): boolean {
    if (
      !isEmployee ||
      actionLock.current ||
      detail.status !== 'returned' ||
      detail.viewed_revision !== detail.revision_number
    ) return false

    if (
      !submitted &&
      Object.values(context).some(value => value.trim()) &&
      !window.confirm('Replace the current unsaved draft with the returned brief?')
    ) return false

    const returnEvent = detail.events.find(
      event =>
        event.action === 'returned' &&
        event.revision_number === detail.revision_number
    )

    setContext({ ...detail.snapshot.context })
    setAnalysis(detail.snapshot.analysis)
    setAnswers([...detail.snapshot.answers])
    setAnswer('')
    setSubmitted(null)
    setApprovedForAI(false)

    setRevision({
      id: detail.id,
      reference: detail.reference,
      number: detail.revision_number,
      managerNote: returnEvent?.note || '',
    })

    setRevisionNote('')
    invalidateVerification()

    setError('')
    setNotice(`Revising ${detail.reference}. Address the Manager's remarks.`)

    return true
  }

  function showList(items?: string[], empty = 'Not available yet') {
    if (!items?.length) return <p>{empty}</p>

    return (
      <ul>
        {items.map((item, index) => (
          <li key={`${index}-${item}`}>{item}</li>
        ))}
      </ul>
    )
  }

  return (
    <main className="bd-ai-page">
      <header className="bd-ai-hero">
        <div className="bd-ai-hero-heading">
          <Sparkles size={25} />

          <div>
            <span className="bd-ai-eyebrow">
              BUSINESS DEVELOPMENT · CLIENT INTELLIGENCE
            </span>
            <h1>BD AI</h1>
          </div>
        </div>

        <p>
          Understand client requirements, generate summaries,
          clarify technical information and prepare verified briefs.
        </p>

        <span className="bd-ai-phase">
          Client Requirements Assistant
        </span>
      </header>

      {isManager && (
        <BDSubmissionPanel
          managerMode={true}
          refreshKey={refreshKey}
        />
      )}

      {error && (
        <div className="bd-ai-info" role="alert">
          <strong>Request failed:</strong> {error}
        </div>
      )}

      {notice && (
        <div className="bd-ai-info" role="status">
          <strong>{notice}</strong>
        </div>
      )}

      {revision && !submitted && (
        <div className="bd-ai-info">
          <strong>
            Revising {revision.reference} — Revision {revision.number}
          </strong>
          <p>Manager remarks: {revision.managerNote}</p>
          <p>
            Use the additional clarification field to update the brief,
            or edit the original requirements and regenerate the analysis.
            Previously submitted revisions remain saved.
          </p>
        </div>
      )}

      <div className="bd-ai-grid">

        {/* MODULE 1: CLIENT INPUT */}

        <section className="bd-ai-card">
          <div className="bd-ai-card-title">
            <FileText size={20} />

            <div>
              <h2>1. Client Requirements</h2>
              <p>Enter the requirements received from the client.</p>
            </div>
          </div>

          <div className="bd-ai-fields">
            <label className="bd-ai-field">
              <span>Client Name / Organization</span>
              <input
                value={context.client_name}
                maxLength={160}
                disabled={formLocked}
                onChange={e => changeContext('client_name', e.target.value)}
                placeholder="Enter client name"
              />
            </label>

            <label className="bd-ai-field">
              <span>Project Name / Reference</span>
              <input
                value={context.project_reference}
                maxLength={160}
                disabled={formLocked}
                onChange={e => changeContext('project_reference', e.target.value)}
                placeholder="Enter project reference"
              />
            </label>

            <label className="bd-ai-field">
              <span>Department</span>
              <select
                value={context.department}
                disabled={formLocked}
                onChange={e => changeContext('department', e.target.value)}
              >
                <option value="">Select department</option>

                {departments.map(name => (
                  <option key={name} value={name}>{name}</option>
                ))}
              </select>
            </label>

            <label className="bd-ai-field">
              <span>Original Client Requirements *</span>
              <textarea
                rows={7}
                maxLength={10000}
                value={context.requirements}
                disabled={formLocked}
                onChange={e => changeContext('requirements', e.target.value)}
                placeholder="Enter the client's scope, location and deliverables..."
              />
            </label>
          </div>

          <label
            className="bd-ai-field"
            style={{ flexDirection: 'row', alignItems: 'flex-start' }}
          >
            <input
              type="checkbox"
              checked={approvedForAI}
              disabled={formLocked}
              onChange={e => setApprovedForAI(e.target.checked)}
              style={{ width: 'auto', marginTop: 3 }}
            />

            <span>
              I confirm this information is approved for processing through Gemini AI.
            </span>
          </label>

          <div className="bd-ai-actions">
            <button
              type="button"
              className="bd-ai-button-secondary"
              disabled={busy}
              onClick={clearDraft}
            >
              <RotateCcw size={16} />
              {submitted ? 'New Requirement' : 'Clear Inputs'}
            </button>

            <button
              type="button"
              className="bd-ai-button-primary"
              disabled={
                formLocked ||
                Boolean(analysis) ||
                !approvedForAI ||
                context.requirements.trim().length < 20
              }
              onClick={() => void generateSummary()}
            >
              <Sparkles size={16} />
              Generate AI Summary
            </button>
          </div>
        </section>

        {/* MODULE 2: AI SUMMARY */}

        <section className="bd-ai-card">
          <div className="bd-ai-card-title">
            <BrainCircuit size={20} />

            <div>
              <h2>2. AI Requirement Summary</h2>
              <p>Gemini-generated understanding of the project.</p>
            </div>
          </div>

          {!analysis && (
            <div className="bd-ai-info">
              Enter the client requirements, confirm approval
              and generate the AI summary.
            </div>
          )}

          <div className="bd-ai-summary">
            <div>
              <span>Project Objective</span>
              <p>{analysis?.project_objective || 'Awaiting analysis'}</p>
            </div>

            <div>
              <span>Scope of Work</span>
              <p>{analysis?.scope_of_work || 'Awaiting analysis'}</p>
            </div>

            <div>
              <span>Expected Deliverables</span>
              {showList(analysis?.expected_deliverables)}
            </div>

            <div>
              <span>Technical Specifications</span>
              {showList(analysis?.technical_specifications)}
            </div>

            <div>
              <span>Missing Information</span>
              {showList(
                analysis?.missing_information,
                analysis ? 'None recorded' : 'Not available yet'
              )}
            </div>

            <div>
              <span>Deadline / Constraints</span>
              <p>{analysis?.constraints_deadline || 'Not specified'}</p>
            </div>
          </div>
        </section>

        {/* MODULE 3: CLARIFICATION QUESTIONS */}

        <section className="bd-ai-card">
          <div className="bd-ai-card-title">
            <MessageSquareText size={20} />

            <div>
              <h2>3. AI Clarification Questions</h2>
              <p>Answer questions and record additional client information.</p>
            </div>
          </div>

          <div className="bd-ai-message">
            <strong>BD AI</strong>

            <p>
              {currentQuestion ||
                (analysis
                  ? 'No pending questions in the current analysis.'
                  : 'Generate a summary to receive clarification questions.')}
            </p>
          </div>

          {analysis && (
            <div className="bd-ai-info">
              Pending questions: {pendingQuestions}
              {' · '}
              Answers recorded: {answers.length}
            </div>
          )}

          <label className="bd-ai-field">
            <span>
              {currentQuestion ? 'BD Team Answer' : 'Additional Clarification'}
            </span>

            <textarea
              rows={4}
              maxLength={2000}
              value={answer}
              disabled={formLocked || !analysis}
              onChange={e => {
                setAnswer(e.target.value)
                invalidateVerification()
              }}
              placeholder={
                currentQuestion
                  ? 'Enter the client answer or explicitly state what is unconfirmed...'
                  : 'Add corrections or newly confirmed client information...'
              }
            />
          </label>

          <div className="bd-ai-actions">
            <button
              type="button"
              className="bd-ai-button-primary"
              disabled={
                formLocked ||
                !approvedForAI ||
                !analysis ||
                !answer.trim() ||
                answers.length >= 100
              }
              onClick={() => void submitAnswer()}
            >
              {currentQuestion ? 'Submit Answer to AI' : 'Update Technical Brief'}
            </button>
          </div>

          {answers.length > 0 && (
            <details>
              <summary>Clarification History ({answers.length})</summary>

              {answers.map((item, index) => (
                <div className="bd-ai-message" key={index}>
                  <strong>{index + 1}. {item.question}</strong>
                  <p style={{ whiteSpace: 'pre-wrap' }}>{item.answer}</p>
                </div>
              ))}
            </details>
          )}
        </section>

        {/* MODULE 4: FINAL TECHNICAL BRIEF */}

        <section className="bd-ai-card">
          <div className="bd-ai-card-title">
            <ClipboardCheck size={20} />

            <div>
              <h2>4. Technical Requirement Brief</h2>
              <p>Review the generated information before submission.</p>
            </div>
          </div>

          <div className="bd-ai-brief">
            <div>
              <strong>Confirmed Client Requirements</strong>
              {showList(analysis?.confirmed_requirements)}
            </div>

            <div>
              <strong>Scope and Deliverables</strong>
              <p>{analysis?.scope_of_work || 'Not available yet'}</p>
              {showList(analysis?.expected_deliverables)}
            </div>

            <div>
              <strong>Accuracy / Standards / Formats</strong>
              {showList(analysis?.technical_specifications)}
            </div>

            <div>
              <strong>Pending Clarifications</strong>
              {showList(
                analysis?.missing_information,
                analysis ? 'None recorded' : 'Not available yet'
              )}
            </div>

            <div>
              <strong>Acceptance Criteria</strong>
              {showList(analysis?.acceptance_criteria)}
            </div>

            <div>
              <strong>Department Handover Notes</strong>
              {showList(analysis?.department_handover_notes)}
            </div>
          </div>

          {isEmployee && (
            <>
              {revision && (
                <label className="bd-ai-field">
                  <span>Describe the Revision *</span>

                  <textarea
                    rows={3}
                    maxLength={2000}
                    value={revisionNote}
                    disabled={formLocked}
                    onChange={e => {
                      setRevisionNote(e.target.value)
                      invalidateVerification()
                    }}
                    placeholder="Explain how the Manager's remarks were addressed..."
                  />
                </label>
              )}

              {hasMissingInformation && (
                <label
                  className="bd-ai-field"
                  style={{ flexDirection: 'row', alignItems: 'flex-start' }}
                >
                  <input
                    type="checkbox"
                    checked={pendingAcknowledged}
                    disabled={formLocked}
                    onChange={e => setPendingAcknowledged(e.target.checked)}
                    style={{ width: 'auto', marginTop: 3 }}
                  />

                  <span>
                    I acknowledge that the listed missing information
                    remains unconfirmed and must be reviewed by the Manager.
                  </span>
                </label>
              )}

              <label
                className="bd-ai-field"
                style={{ flexDirection: 'row', alignItems: 'flex-start' }}
              >
                <input
                  type="checkbox"
                  checked={humanVerified}
                  disabled={
                    formLocked ||
                    !analysis ||
                    pendingQuestions > 0 ||
                    Boolean(answer.trim())
                  }
                  onChange={e => setHumanVerified(e.target.checked)}
                  style={{ width: 'auto', marginTop: 3 }}
                />

                <span>
                  I have reviewed the technical requirement brief and
                  verified it against the client's confirmed requirements.
                </span>
              </label>

              {!submitted && !canFinalize && (
                <div className="bd-ai-info">
                  Complete the client details, address pending questions,
                  acknowledge any remaining unknown information and
                  confirm human verification to enable submission.
                </div>
              )}

              <div className="bd-ai-actions">
                <button
                  type="button"
                  className="bd-ai-button-primary"
                  disabled={!canFinalize || Boolean(answer.trim())}
                  onClick={() => void finalizeSubmission()}
                >
                  {submitted
                    ? 'Submitted to Manager'
                    : revision
                      ? 'Resubmit to Manager'
                      : 'Finalize and Send to Manager'}
                </button>
              </div>
            </>
          )}

          {!isEmployee && (
            <div className="bd-ai-info">
              This account can generate and review AI analyses.
              Technical brief submission is available to BD Employee accounts.
            </div>
          )}
        </section>
      </div>

      {busy && <div className="bd-ai-info" role="status">Processing request...</div>}

      {isEmployee && (
        <BDSubmissionPanel
          managerMode={false}
          refreshKey={refreshKey}
          editingBusy={busy}
          onRevise={beginRevision}
        />
      )}

      <div className="bd-ai-footer">
        AI-generated analysis requires human verification.
        Technical brief approval does not automatically create
        a project or authorize Finance approval.
      </div>
    </main>
  )
}
