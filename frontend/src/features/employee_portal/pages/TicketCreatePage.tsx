import { Building2, Cpu, Gauge, PlaneTakeoff, Send, Settings2, Users } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch } from '../../../lib/api'
import type { SupportTicket, TicketDepartment, TicketPriority } from '../../../types'

const departments: Array<{ value: TicketDepartment; label: string; description: string; icon: typeof Cpu }> = [
  { value: 'it', label: 'IT Department', description: 'Laptop, desktop, Wi-Fi, printer, hardware, or access issues.', icon: Cpu },
  { value: 'drone', label: 'Drone Department', description: 'Drone hardware, batteries, trackers, flight, or survey equipment.', icon: PlaneTakeoff },
  { value: 'software_team', label: 'Software Team', description: 'CRM errors, application bugs, login issues, data, or feature requests.', icon: Settings2 },
  { value: 'management', label: 'Management', description: 'Administrative, resource, policy, or escalation requests.', icon: Users },
]

export function TicketCreatePage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [form, setForm] = useState({ department: 'it' as TicketDepartment, category: '', title: '', description: '', priority: 'medium' as TicketPriority, location: '', asset_number: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault(); setLoading(true); setError('')
    try {
      const ticket = await apiFetch<SupportTicket>('/tickets', { method: 'POST', body: JSON.stringify(form) })
      navigate(`/tickets/${ticket.id}`, { replace: true })
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not create ticket') }
    finally { setLoading(false) }
  }

  return <>
    <DashboardHeader eyebrow="EMPLOYEE SUPPORT" title="Raise a New Ticket" description={`The selected department receives the actionable ticket. Software Team receives monitoring information for every ticket. Branch: ${user?.selected_branch_name || user?.branch}.`} />
    <form className="panel-card ticket-create-form" onSubmit={submit}>
      <div className="ticket-form-section"><span className="section-kicker">1 · SELECT RESPONSIBLE TEAM</span><div className="ticket-department-grid">{departments.map(item => { const Icon = item.icon; return <button type="button" key={item.value} className={form.department === item.value ? 'selected' : ''} onClick={() => setForm({ ...form, department: item.value })}><Icon /><div><strong>{item.label}</strong><span>{item.description}</span></div></button> })}</div></div>
      <div className="ticket-form-section ticket-field-grid"><span className="section-kicker ticket-grid-span">2 · DESCRIBE THE ISSUE</span>
        <label><span>Issue Title</span><input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="Example: Laptop cannot connect to Wi-Fi" required /></label>
        <label><span>Category</span><input value={form.category} onChange={e => setForm({ ...form, category: e.target.value })} placeholder="Hardware / Network / CRM / Request" /></label>
        <label><span>Priority</span><select value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value as TicketPriority })}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select></label>
        <label><span>Location</span><div className="field-with-icon"><Building2 size={17} /><input value={form.location} onChange={e => setForm({ ...form, location: e.target.value })} placeholder="Floor / room / site" /></div></label>
        <label><span>Asset Number (optional)</span><div className="field-with-icon"><Gauge size={17} /><input value={form.asset_number} onChange={e => setForm({ ...form, asset_number: e.target.value })} placeholder="CPU / laptop / drone asset tag" /></div></label>
        <label className="ticket-grid-span"><span>Problem Description</span><textarea value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} rows={7} placeholder="Explain what happened, when it started, and what you have already tried." required /></label>
      </div>
      {error && <div className="error-message">{error}</div>}
      <div className="ticket-form-actions"><button type="button" className="ghost-button" onClick={() => navigate(-1)}>Cancel</button><button className="primary-button" disabled={loading}><Send size={17} />{loading ? 'Submitting...' : 'Submit Ticket'}</button></div>
    </form>
  </>
}
