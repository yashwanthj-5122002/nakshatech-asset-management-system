import { CheckCircle2, FileUp, ShieldCheck } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { apiFetch } from '../../../lib/api'
import '../client-feedback.css'

type FeedbackForm = {
  request_code: string
  project_id: string
  project_name: string
  cycle_number: number
  message?: string | null
  expires_at: string
  expired: boolean
  responded: boolean
}

export function ClientFeedbackPage() {
  const { token = '' } = useParams()
  const [form, setForm] = useState<FeedbackForm | null>(null)
  const [responseType, setResponseType] = useState<'accepted' | 'correction' | 'additional_scope'>('accepted')
  const [comments, setComments] = useState('')
  const [description, setDescription] = useState('')
  const [clientName, setClientName] = useState('')
  const [clientEmail, setClientEmail] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  useEffect(() => {
    void apiFetch<FeedbackForm>(`/operations/lifecycle/public/feedback/${encodeURIComponent(token)}`)
      .then(setForm)
      .catch(error => setError(error instanceof Error ? error.message : 'This feedback link is unavailable.'))
      .finally(() => setLoading(false))
  }, [token])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (responseType !== 'accepted' && !description.trim()) {
      setError('Please describe the correction or additional scope requested.')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      await apiFetch(`/operations/lifecycle/public/feedback/${encodeURIComponent(token)}`, {
        method: 'POST',
        body: JSON.stringify({
          response_type: responseType,
          comments: comments.trim() || null,
          correction_description: responseType === 'accepted' ? null : description.trim(),
          client_name: clientName.trim() || null,
          client_email: clientEmail.trim() || null,
          attachments: [],
        }),
      })
      if (files.length) {
        const body = new FormData()
        files.forEach(file => body.append('files', file))
        await apiFetch(`/operations/lifecycle/public/feedback/${encodeURIComponent(token)}/attachments`, {
          method: 'POST',
          body,
        })
      }
      setSubmitted(true)
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Feedback could not be submitted.')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <main className="client-feedback-shell"><section className="client-feedback-card">Loading secure feedback request...</section></main>
  if (error && !form) return <main className="client-feedback-shell"><section className="client-feedback-card"><h1>Feedback link unavailable</h1><p>{error}</p></section></main>
  if (!form) return null
  if (submitted || form.responded) return <main className="client-feedback-shell"><section className="client-feedback-card client-feedback-success"><CheckCircle2 size={42}/><h1>Thank you</h1><p>Your response has been securely recorded against Project {form.project_id}. Nakshatech will follow up if any clarification is required.</p></section></main>
  if (form.expired) return <main className="client-feedback-shell"><section className="client-feedback-card"><h1>Feedback link expired</h1><p>Please contact your Nakshatech Business Development representative for a renewed secure link.</p></section></main>

  return <main className="client-feedback-shell">
    <form className="client-feedback-card" onSubmit={submit}>
      <div className="client-feedback-brand"><ShieldCheck/><div><strong>Nakshatech</strong><span>Secure Client Feedback</span></div></div>
      <span className="client-feedback-code">{form.request_code} · Cycle {form.cycle_number}</span>
      <h1>{form.project_name}</h1>
      <p>Project ID: <strong>{form.project_id}</strong></p>
      {form.message && <div className="client-feedback-note">{form.message}</div>}

      <fieldset>
        <legend>Your response</legend>
        <label><input type="radio" checked={responseType === 'accepted'} onChange={() => setResponseType('accepted')}/> Delivery accepted</label>
        <label><input type="radio" checked={responseType === 'correction'} onChange={() => setResponseType('correction')}/> Correction / rework required</label>
        <label><input type="radio" checked={responseType === 'additional_scope'} onChange={() => setResponseType('additional_scope')}/> Additional scope / change request</label>
      </fieldset>

      {responseType !== 'accepted' && <label className="client-feedback-field"><span>{responseType === 'correction' ? 'Correction details' : 'Additional scope details'} *</span><textarea value={description} onChange={event => setDescription(event.target.value)} required rows={5}/></label>}
      <label className="client-feedback-field"><span>Comments</span><textarea value={comments} onChange={event => setComments(event.target.value)} rows={3}/></label>
      <div className="client-feedback-grid">
        <label className="client-feedback-field"><span>Your name</span><input value={clientName} onChange={event => setClientName(event.target.value)}/></label>
        <label className="client-feedback-field"><span>Your email</span><input type="email" value={clientEmail} onChange={event => setClientEmail(event.target.value)}/></label>
      </div>
      <label className="client-feedback-upload"><FileUp/><span><strong>Supporting files</strong><small>PDF, JPG, PNG or WebP · 15 MB each · up to 20 files</small></span><input type="file" multiple accept="application/pdf,image/jpeg,image/png,image/webp" onChange={event => setFiles(Array.from(event.target.files || []))}/></label>
      {files.length > 0 && <small>{files.length} file(s) selected</small>}
      {error && <div className="client-feedback-error">{error}</div>}
      <button type="submit" disabled={submitting}>{submitting ? 'Submitting...' : 'Submit secure feedback'}</button>
      <small className="client-feedback-expiry">This single-use link expires {new Date(form.expires_at).toLocaleString()}.</small>
    </form>
  </main>
}
