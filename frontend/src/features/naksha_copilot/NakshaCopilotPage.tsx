import { useEffect, useMemo, useRef, useState } from 'react'
import { Bot, CalendarRange, ChevronDown, Send, ShieldCheck, Sparkles, TriangleAlert } from 'lucide-react'
import { apiFetch } from '../../lib/api'
import { useITMonth } from '../../context/ITMonthContext'
import './naksha-copilot.css'

type PeriodType = 'month' | 'selected_months' | 'calendar_year' | 'financial_year'

interface CopilotStatus {
  enabled: boolean
  configured: boolean
  model: string
  privacy_mode: string
  allowed_roles: string[]
  requests_per_hour: number
}

interface CopilotAnswer {
  request_id: string
  answer: string
  period_label: string
  period_type: PeriodType
  model: string
  privacy_mode: string
  sources: string[]
}

const monthOptions = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

const examples = [
  'Summarize the selected months for management.',
  'Compare device categories and status counts across the selected months.',
  'Identify aggregated data-quality issues in the selected months.',
  'Explain the main activity and purchase trends without exposing identities.',
]

export function NakshaCopilotPage() {
  const { selectedMonth } = useITMonth()
  const currentYear = Number(selectedMonth.slice(0, 4)) || new Date().getFullYear()
  const currentMonthNumber = Number(selectedMonth.slice(5, 7)) || new Date().getMonth() + 1
  const [year, setYear] = useState(currentYear)
  const [selectedMonths, setSelectedMonths] = useState<number[]>([currentMonthNumber])
  const [question, setQuestion] = useState(examples[0])
  const [status, setStatus] = useState<CopilotStatus | null>(null)
  const [answer, setAnswer] = useState<CopilotAnswer | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [monthDropdownOpen, setMonthDropdownOpen] = useState(false)
  const monthDropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    void apiFetch<CopilotStatus>('/naksha-copilot/status')
      .then(setStatus)
      .catch(err => setError(err instanceof Error ? err.message : 'Could not load Naksha Copilot status.'))
  }, [])

  useEffect(() => {
    setYear(currentYear)
    setSelectedMonths([currentMonthNumber])
  }, [currentMonthNumber, currentYear])

  useEffect(() => {
    if (!monthDropdownOpen) return undefined

    function closeOnOutsideClick(event: MouseEvent) {
      if (!monthDropdownRef.current?.contains(event.target as Node)) {
        setMonthDropdownOpen(false)
      }
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') setMonthDropdownOpen(false)
    }

    document.addEventListener('mousedown', closeOnOutsideClick)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('mousedown', closeOnOutsideClick)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [monthDropdownOpen])

  const selectedMonthNames = useMemo(
    () => selectedMonths.map(value => monthOptions[value - 1]).filter(Boolean),
    [selectedMonths],
  )

  const monthDropdownLabel = useMemo(() => {
    if (selectedMonthNames.length === 0) return 'Select months'
    if (selectedMonthNames.length === 1) return `${selectedMonthNames[0]} ${year}`
    if (selectedMonthNames.length <= 3) return `${selectedMonthNames.join(', ')} ${year}`
    return `${selectedMonthNames.length} months selected · ${year}`
  }, [selectedMonthNames, year])

  const periodHint = useMemo(() => {
    if (selectedMonthNames.length === 0) return 'Select at least one month.'
    if (selectedMonthNames.length === 12) return `All months selected for ${year}.`
    return `Selected: ${selectedMonthNames.join(', ')} ${year}`
  }, [selectedMonthNames, year])

  function toggleMonth(month: number) {
    setSelectedMonths(previous => {
      const next = previous.includes(month)
        ? previous.filter(value => value !== month)
        : [...previous, month]
      return next.sort((left, right) => left - right)
    })
  }

  async function askCopilot() {
    if (selectedMonths.length === 0) {
      setError('Select at least one month before asking Naksha Copilot.')
      return
    }
    setError('')
    setAnswer(null)
    setLoading(true)
    try {
      const result = await apiFetch<CopilotAnswer>('/naksha-copilot/ask', {
        method: 'POST',
        body: JSON.stringify({
          question,
          period_type: 'selected_months',
          year,
          months: selectedMonths,
        }),
      })
      setAnswer(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Naksha Copilot could not answer this request.')
    } finally {
      setLoading(false)
    }
  }

  const ready = Boolean(status?.enabled && status?.configured)

  return (
    <section className="copilot-page">
      <header className="copilot-hero">
        <div className="copilot-hero-icon"><Sparkles size={24} /></div>
        <div>
          <span className="copilot-eyebrow">Read-only AI reporting assistant</span>
          <h1>Naksha Copilot</h1>
          <p>Ask management-level questions using approved aggregate IT asset and activity statistics.</p>
        </div>
        <div className={`copilot-status ${ready ? 'ready' : 'offline'}`}>
          <span />
          {ready ? `Ready · ${status?.model}` : status?.enabled ? 'API key not configured' : 'Disabled'}
        </div>
      </header>

      <div className="copilot-privacy-banner">
        <ShieldCheck size={22} />
        <div>
          <strong>Strict privacy mode is active</strong>
          <p>Only aggregated totals, device categories, departments, status counts, monthly/yearly statistics and anonymized request references are sent. Names, emails, phone numbers, serial numbers, asset tags, ticket text, credentials, client names and raw rows are blocked.</p>
        </div>
      </div>

      <div className="copilot-layout">
        <article className="copilot-card copilot-compose-card">
          <div className="copilot-card-heading">
            <div><Bot size={20} /><span>Ask a reporting question</span></div>
            <small>{status?.requests_per_hour ?? 20} requests per user/hour</small>
          </div>

          <div className="copilot-period-grid copilot-simple-period-grid">
            <label>
              <span>Year</span>
              <input
                type="number"
                min={2020}
                max={2100}
                value={year}
                onChange={event => setYear(Number(event.target.value) || currentYear)}
              />
            </label>
            <div className="copilot-month-field">
              <span className="copilot-field-label">Month selection</span>
              <div className="copilot-month-dropdown" ref={monthDropdownRef}>
                <button
                  className="copilot-month-trigger"
                  type="button"
                  aria-haspopup="listbox"
                  aria-expanded={monthDropdownOpen}
                  onClick={() => setMonthDropdownOpen(open => !open)}
                >
                  <span>{monthDropdownLabel}</span>
                  <span className="copilot-month-count">{selectedMonths.length}/12</span>
                  <ChevronDown size={17} className={monthDropdownOpen ? 'open' : ''} />
                </button>

                {monthDropdownOpen && (
                  <div className="copilot-month-menu" role="listbox" aria-multiselectable="true">
                    <div className="copilot-month-menu-grid">
                      {monthOptions.map((name, index) => {
                        const month = index + 1
                        const selected = selectedMonths.includes(month)
                        return (
                          <label className={`copilot-month-option ${selected ? 'selected' : ''}`} key={name}>
                            <input
                              type="checkbox"
                              checked={selected}
                              onChange={() => toggleMonth(month)}
                            />
                            <span>{name}</span>
                          </label>
                        )
                      })}
                    </div>
                    <div className="copilot-month-menu-footer">
                      <button type="button" onClick={() => setSelectedMonths(monthOptions.map((_, index) => index + 1))}>Select all</button>
                      <button type="button" onClick={() => setSelectedMonths([])}>Clear</button>
                    </div>
                  </div>
                )}
              </div>
              <small>Open the dropdown and select one or more months. No Ctrl key is required.</small>
            </div>
          </div>
          <div className="copilot-period-hint">
            <CalendarRange size={16} />
            <span>{periodHint}</span>
            <strong>{selectedMonths.length} month{selectedMonths.length === 1 ? '' : 's'} selected</strong>
          </div>

          <label className="copilot-question-field">
            <span>Question</span>
            <textarea
              value={question}
              maxLength={600}
              onChange={event => setQuestion(event.target.value)}
              placeholder="Example: Compare the selected months and highlight important aggregate changes."
            />
            <small>{question.length}/600 characters</small>
          </label>

          <div className="copilot-examples">
            {examples.map(example => (
              <button type="button" key={example} onClick={() => setQuestion(example)}>{example}</button>
            ))}
          </div>

          <button
            className="copilot-submit"
            type="button"
            disabled={!ready || loading || question.trim().length < 3 || selectedMonths.length === 0}
            onClick={askCopilot}
          >
            {loading ? <span className="copilot-spinner" /> : <Send size={17} />}
            {loading ? 'Analyzing approved aggregates…' : 'Ask Naksha Copilot'}
          </button>

          {error && <div className="copilot-error"><TriangleAlert size={18} /><span>{error}</span></div>}
        </article>

        <article className="copilot-card copilot-answer-card">
          <div className="copilot-card-heading">
            <div><Sparkles size={20} /><span>AI response</span></div>
            {answer && <small>{answer.request_id}</small>}
          </div>
          {!answer ? (
            <div className="copilot-empty">
              <Bot size={44} />
              <strong>No response yet</strong>
              <p>Naksha Copilot will answer from sanitized reporting aggregates only. It cannot edit records or access raw confidential fields.</p>
            </div>
          ) : (
            <div className="copilot-answer">
              <div className="copilot-answer-meta">
                <span>{answer.period_label}</span>
                <span>{answer.model}</span>
              </div>
              <div className="copilot-answer-text">{answer.answer}</div>
              <div className="copilot-source-box">
                <strong>Approved sources used</strong>
                <ul>{answer.sources.map(source => <li key={source}>{source}</li>)}</ul>
                <small>{answer.privacy_mode}</small>
              </div>
            </div>
          )}
        </article>
      </div>
    </section>
  )
}
