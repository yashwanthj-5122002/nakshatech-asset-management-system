import { Mail, Plus, X } from 'lucide-react'
import { type KeyboardEvent, useState } from 'react'

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function isValidTravelEmail(value: string): boolean {
  return EMAIL_PATTERN.test(value.trim())
}

interface EmailRecipientChipsProps {
  label: string
  values: string[]
  onChange: (values: string[]) => void
  placeholder?: string
  disabled?: boolean
  help?: string
}

export function EmailRecipientChips({ label, values, onChange, placeholder, disabled, help }: EmailRecipientChipsProps) {
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')

  function addDraft() {
    const email = draft.trim().replace(/,$/, '').toLowerCase()
    if (!email) return
    if (!isValidTravelEmail(email)) {
      setError('Enter a valid email address.')
      return
    }
    if (values.some(value => value.toLowerCase() === email)) {
      setDraft('')
      setError('')
      return
    }
    if (values.length >= 25) {
      setError('Maximum 25 email addresses are allowed here.')
      return
    }
    onChange([...values, email])
    setDraft('')
    setError('')
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault()
      addDraft()
    }
  }

  function remove(email: string) {
    onChange(values.filter(value => value !== email))
  }

  return <label className="travel-km-field full travel-km-email-field">
    <span>{label}</span>
    <div className={`travel-km-email-chipbox ${disabled ? 'is-disabled' : ''}`}>
      <Mail size={16}/>
      <div className="travel-km-email-chip-content">
        <div className="travel-km-email-chips">
          {values.map(email => <span className="travel-km-email-chip" key={email}>{email}{!disabled && <button type="button" aria-label={`Remove ${email}`} onClick={() => remove(email)}><X size={13}/></button>}</span>)}
        </div>
        {!disabled && <div className="travel-km-email-entry"><input type="email" value={draft} onChange={event => { setDraft(event.target.value); setError('') }} onKeyDown={onKeyDown} onBlur={() => { if (draft.trim()) addDraft() }} placeholder={placeholder || 'Type email and press Enter'} autoComplete="off"/><span><Plus size={14}/> Enter to add</span></div>}
      </div>
    </div>
    {help && <small>{help}</small>}
    {error && <small className="travel-km-email-error">{error}</small>}
  </label>
}
