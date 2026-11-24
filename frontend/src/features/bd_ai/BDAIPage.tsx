
import { useState } from 'react'
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
import './bd-ai.css'

type BDAIAnalysis = {
  project_objective: string
  scope_of_work: string
  expected_deliverables: string[]
  technical_specifications: string[]
  constraints_deadline: string
  missing_information: string[]
  clarification_questions: string[]
  confirmed_requirements: string[]
  acceptance_criteria: string[]
  department_handover_notes: string[]
}

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

export function BDAIPage() {
  const { user } = useAuth()

  const [clientName, setClientName] = useState('')
  const [projectReference, setProjectReference] = useState('')
  const [department, setDepartment] = useState('')
  const [requirements, setRequirements] = useState('')
  const [answer, setAnswer] = useState('')

  const [approvedForAI, setApprovedForAI] = useState(false)
  const [analysis, setAnalysis] = useState<BDAIAnalysis | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const currentQuestion = analysis?.clarification_questions[0]

  if (!canAccessBDAI(user)) {
    return <Navigate
      to={user ? roleHomePath(user.role) : '/login'}
      replace
    />
  }

  function getContext() {
    return {
      client_name: clientName,
      project_reference: projectReference,
      department,
      requirements,
    }
  }

  function changeRequirements(value: string) {
    setRequirements(value)
    setAnalysis(null)
    setAnswer('')
    setApprovedForAI(false)
  }

  function changeDepartment(value: string) {
    setDepartment(value)
    setAnalysis(null)
    setAnswer('')
    setApprovedForAI(false)
  }

  function clearDraft() {
    setClientName('')
    setProjectReference('')
    setDepartment('')
    setRequirements('')
    setAnswer('')
    setAnalysis(null)
    setApprovedForAI(false)
    setError('')
  }

  async function generateSummary() {
    if (busy || !approvedForAI || requirements.trim().length < 20) {
      return
    }

    setBusy(true)
    setError('')

    try {
      const result = await apiFetch<BDAIAnalysis>(
        '/bd-ai/summarize',
        {
          method: 'POST',
          body: JSON.stringify(getContext()),
        }
      )

      setAnalysis(result)
      setAnswer('')
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to generate the AI summary.'
      )
    } finally {
      setBusy(false)
    }
  }

  async function submitAnswer() {
    if (
      busy ||
      !approvedForAI ||
      !analysis ||
      !currentQuestion ||
      !answer.trim()
    ) {
      return
    }

    setBusy(true)
    setError('')

    try {
      const result = await apiFetch<BDAIAnalysis>(
        '/bd-ai/refine',
        {
          method: 'POST',
          body: JSON.stringify({
            context: getContext(),
            previous: analysis,
            answers: [
              {
                question: currentQuestion,
                answer: answer.trim(),
              },
            ],
          }),
        }
      )

      setAnalysis(result)
      setAnswer('')
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to process the clarification.'
      )
    } finally {
      setBusy(false)
    }
  }

  function showList(items: string[] | undefined) {
    if (!items?.length) {
      return <p>Not available yet</p>
    }

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
          Understand client requirements, generate summaries
          and clarify missing technical information.
        </p>

        <span className="bd-ai-phase">
          Client Requirements Assistant
        </span>
      </header>

      {error && (
        <div className="bd-ai-info" role="alert">
          <strong>AI request failed:</strong> {error}
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
                value={clientName}
                onChange={e => setClientName(e.target.value)}
                placeholder="Enter client name"
              />
            </label>

            <label className="bd-ai-field">
              <span>Project Name / Reference</span>
              <input
                value={projectReference}
                onChange={e => setProjectReference(e.target.value)}
                placeholder="Enter project reference"
              />
            </label>

            <label className="bd-ai-field">
              <span>Department</span>
              <select
                value={department}
                onChange={e => changeDepartment(e.target.value)}
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
                value={requirements}
                onChange={e => changeRequirements(e.target.value)}
                placeholder="Enter the client's description, scope, survey location, deliverables and requirements..."
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
              onChange={e => setApprovedForAI(e.target.checked)}
              style={{ width: 'auto', marginTop: 3 }}
            />
            <span>
              I confirm this information is approved for
              processing through Gemini AI.
            </span>
          </label>

          <div className="bd-ai-actions">
            <button
              type="button"
              className="bd-ai-button-secondary"
              onClick={clearDraft}
              disabled={busy}
            >
              <RotateCcw size={16} />
              Clear Inputs
            </button>

            <button
              type="button"
              className="bd-ai-button-primary"
              disabled={
                busy ||
                !approvedForAI ||
                requirements.trim().length < 20
              }
              onClick={() => void generateSummary()}
            >
              <Sparkles size={16} />
              {busy ? 'Analyzing...' : 'Generate AI Summary'}
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
              Enter at least 20 characters, confirm approval,
              and click Generate AI Summary.
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
              {showList(analysis?.missing_information)}
            </div>

            <div>
              <span>Deadline / Constraints</span>
              <p>
                {analysis?.constraints_deadline || 'Not specified'}
              </p>
            </div>
          </div>
        </section>

        {/* MODULE 3: QUESTIONS AND ANSWERS */}
        <section className="bd-ai-card">
          <div className="bd-ai-card-title">
            <MessageSquareText size={20} />
            <div>
              <h2>3. AI Clarification Questions</h2>
              <p>Answer the questions raised by Gemini.</p>
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

          {analysis && analysis.clarification_questions.length > 1 && (
            <div className="bd-ai-info">
              {analysis.clarification_questions.length} questions
              remain in the current analysis.
            </div>
          )}

          <label className="bd-ai-field">
            <span>BD Team Answer</span>
            <textarea
              rows={4}
              value={answer}
              onChange={e => setAnswer(e.target.value)}
              disabled={!currentQuestion || busy}
              placeholder="Enter the answer, or state that the client has not confirmed it..."
            />
          </label>

          <div className="bd-ai-actions">
            <button
              type="button"
              className="bd-ai-button-primary"
              disabled={
                busy ||
                !approvedForAI ||
                !currentQuestion ||
                !answer.trim()
              }
              onClick={() => void submitAnswer()}
            >
              {busy ? 'Processing...' : 'Submit Answer to AI'}
            </button>
          </div>
        </section>

        {/* MODULE 4: FINAL BRIEF */}
        <section className="bd-ai-card">
          <div className="bd-ai-card-title">
            <ClipboardCheck size={20} />
            <div>
              <h2>4. Technical Requirement Brief</h2>
              <p>
                Draft technical information for BD verification.
              </p>
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
              {showList(analysis?.missing_information)}
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

          <div className="bd-ai-actions">
            <button
              type="button"
              className="bd-ai-button-primary"
              disabled
              title="Manager handover will be added in a later phase"
            >
              Finalize and Send to Manager
            </button>
          </div>
        </section>
      </div>

      <div className="bd-ai-footer">
        AI-generated analysis requires human review.
        No requirement brief is automatically saved or
        shared with a department manager.
      </div>
    </main>
  )
}
