import { CircleDollarSign, RefreshCcw, Save, Send, ShieldCheck } from 'lucide-react'
import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import { uploadRevisionDocuments, type PendingDocument } from '../commercial-api'
import { commercialFormFromRevision, commercialFormProblems, commercialFormToPayload, emptyCommercialForm, type CommercialFormState } from '../commercial-form'
import { CommercialDetailsSection } from '../components/CommercialDetailsSection'
import { FinanceCommercialSummary } from '../components/FinanceCommercialSummary'
import { PendingDocumentsPicker } from '../components/SupportingDocuments'
import type { CommercialEstimate, CurrencyPayload, SimpleProject } from '../types'
import { money, statusLabel, statusTone } from '../types'
import '../commercial.css'
import '../commercial-workflow.css'

type BDDashboard = { projects: SimpleProject[] }

const today = () => new Date().toISOString().slice(0, 10)
const PROJECT_FLOW_STATES = ['draft', 'finance_returned', 'pending_finance_approval']

/**
 * Commercial Estimates. Revision 1 is entered on the Create Project form and approved together with the project.
 * This page is therefore mainly COMMERCIAL REVISION MANAGEMENT: after Finance locks Revision 1, later scope / value /
 * rate changes are new revisions (R2, R3 …) that Finance approves; Revision 1 is never overwritten.
 */
export function BDCommercialPage() {
  const [projects, setProjects] = useState<SimpleProject[]>([])
  const [currencies, setCurrencies] = useState<CurrencyPayload | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [estimates, setEstimates] = useState<CommercialEstimate[]>([])
  const [form, setForm] = useState<CommercialFormState>(emptyCommercialForm)
  const [reason, setReason] = useState('')
  const [estimateDate, setEstimateDate] = useState(today)
  const [docs, setDocs] = useState<PendingDocument[]>([])
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  function loadProjects() {
    setError('')
    void Promise.all([
      apiFetch<BDDashboard>('/operations/workflow/bd/dashboard'),
      apiFetch<CurrencyPayload>('/commercial/currencies'),
    ]).then(([dashboard, refs]) => {
      setProjects(dashboard.projects)
      setCurrencies(refs)
      if (!selectedId && dashboard.projects.length) setSelectedId(dashboard.projects[0].id)
    }).catch(err => setError(err instanceof Error ? err.message : 'Unable to load commercial projects'))
  }

  function loadEstimates(projectId: number) {
    setError('')
    void apiFetch<CommercialEstimate[]>(`/commercial/projects/${projectId}/estimates`)
      .then(rows => {
        setEstimates(rows)
        const approved = rows.find(row => row.status === 'APPROVED')   // rows are newest first
        const first = rows.find(row => row.revision_no === 1)
        const source = approved ?? (first && !first.is_locked ? first : null)
        setForm(source ? commercialFormFromRevision(source) : emptyCommercialForm())
        setReason(''); setDocs([]); setEstimateDate(today())
      })
      .catch(err => setError(err instanceof Error ? err.message : 'Unable to load commercial estimate history'))
  }

  useEffect(loadProjects, [])
  useEffect(() => { if (selectedId) loadEstimates(selectedId) }, [selectedId])

  const selected = projects.find(row => row.id === selectedId) ?? null
  const status = (selected?.normalized_status || selected?.workflow_status || '').toLowerCase()
  const baseline = estimates.find(row => row.revision_no === 1) ?? null
  const hasApproved = estimates.some(row => row.status === 'APPROVED')
  const pendingRevision = estimates.some(row => row.revision_no > 1 && row.status === 'PENDING_APPROVAL')
  // A project already under Finance review that never got a Revision 1 (submitted before the commercial layer) may still add one here.
  const mode: 'revision' | 'project_flow' | 'legacy_baseline' = hasApproved ? 'revision' : PROJECT_FLOW_STATES.includes(status) && !(status === 'pending_finance_approval' && !baseline) ? 'project_flow' : 'legacy_baseline'
  const nextRevision = (estimates[0]?.revision_no ?? 0) + 1
  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term) return projects
    return projects.filter(row => [row.project_code, row.project_name, row.client_code || '', row.client_name || ''].some(v => v.toLowerCase().includes(term)))
  }, [projects, search])

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!selectedId) return
    const problems = commercialFormProblems(form)
    if (problems.length) { setError(problems[0]); return }
    if (mode === 'revision' && !reason.trim()) { setError('A reason is required for a post-approval commercial revision.'); return }
    setBusy(true); setError(''); setNotice('')
    try {
      const payload = { ...commercialFormToPayload(form, estimateDate), reason: reason.trim() || null }
      let saved: CommercialEstimate
      if (mode === 'revision') {
        saved = await apiFetch<CommercialEstimate>(`/commercial/projects/${selectedId}/estimates/revisions`, { method: 'POST', body: JSON.stringify(payload) })
        setNotice(`Commercial Revision ${saved.revision_no} submitted to Finance. Revision 1 and every approved revision stay unchanged.`)
      } else {
        saved = await apiFetch<CommercialEstimate>(`/commercial/projects/${selectedId}/estimates/baseline`, { method: 'PUT', body: JSON.stringify(payload) })
        setNotice('Commercial baseline saved. It remains editable until Finance approval.')
      }
      if (docs.length) {
        const failed = await uploadRevisionDocuments(selectedId, saved.id, docs)
        if (failed.length) setError(`Saved, but ${failed.length} document(s) could not be uploaded: ${failed.join(', ')}`)
      }
      loadEstimates(selectedId)
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to save commercial estimate') }
    finally { setBusy(false) }
  }

  async function submitBaseline() {
    if (!selectedId) return
    setBusy(true); setError(''); setNotice('')
    try {
      await apiFetch(`/commercial/projects/${selectedId}/estimates/baseline/submit`, { method: 'POST' })
      setNotice('Commercial baseline marked Pending Approval for Finance.')
      loadEstimates(selectedId)
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to submit commercial baseline') }
    finally { setBusy(false) }
  }

  return <div className="commercial-page">
    <DashboardHeader eyebrow="BUSINESS DEVELOPMENT · COMMERCIAL REVISIONS" title="Commercial Estimates" description="Revision 1 is entered on the Create Project form and approved by Finance together with the project. After approval it is a locked baseline; scope, value or rate changes are created here as new revisions." actions={<button className="commercial-button secondary" onClick={loadProjects}><RefreshCcw size={15}/> Refresh</button>}/>
    {error && <div className="commercial-alert error">{error}</div>}
    {notice && <div className="commercial-alert success">{notice}</div>}
    <div className="commercial-grid">
      <aside className="commercial-panel">
        <header><div><span className="commercial-kicker">PROJECT REGISTER</span><h2>Projects</h2></div></header>
        <label className="commercial-field"><span>Search Project ID / client</span><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search..."/></label>
        <div className="commercial-list" style={{marginTop:12}}>{filtered.map(row => <button key={row.id} type="button" className={`commercial-project-button ${selectedId===row.id?'active':''}`} onClick={()=>setSelectedId(row.id)}><strong>{row.project_code}</strong><span>{row.project_name}</span><span>{row.client_code || row.client_name || 'Client not linked'} · {statusLabel(row.normalized_status || row.workflow_status || 'draft')}</span></button>)}</div>
      </aside>
      <main className="commercial-panel">
        {!selected ? <div className="commercial-empty">Select a project.</div> : <>
          <header><div><span className="commercial-kicker">{selected.project_code}</span>
            <h2>{mode === 'revision' ? `Create Commercial Revision ${nextRevision}` : mode === 'project_flow' ? 'Commercial Revision 1' : 'Commercial Baseline'}</h2>
            <p>{mode === 'revision' ? 'The approved baseline stays immutable. This form creates the next revision for Finance to decide.' : mode === 'project_flow' ? 'Revision 1 travels with the project to Finance and is locked as the baseline when Finance approves the project.' : 'This project was approved before commercial details existed. Save the baseline and submit it to Finance.'}</p></div>
            {baseline?.is_locked ? <span className="cw-locked"><ShieldCheck size={13}/> Revision 1 · Baseline locked</span> : baseline ? <span className="cw-pending">Revision 1 · {statusLabel(baseline.status)}</span> : null}</header>

          {mode === 'project_flow' && <div style={{ display: 'grid', gap: 12 }}>
            {baseline ? <FinanceCommercialSummary projectId={selected.id} /> : <div className="commercial-note">No Commercial &amp; Billing Details (Revision 1) yet.</div>}
            <div className="commercial-note">Revision 1 is edited on the project form, so the project and its commercial terms are always submitted together. {status === 'pending_finance_approval' ? 'It is under Finance review right now and cannot be edited unless Finance returns it.' : <><Link to="/bd/projects">Open Project Management</Link> and choose <b>Edit</b> to add or correct it, then <b>Submit</b>.</>}</div>
          </div>}

          {mode !== 'project_flow' && (pendingRevision
            ? <div className="commercial-note">A commercial revision is already waiting for Finance approval. Wait for the decision before creating another.</div>
            : <form className="commercial-form" onSubmit={save}>
                <div className="commercial-span-2"><CommercialDetailsSection form={form} onChange={setForm} currencies={currencies} disabled={busy}/></div>
                <label className="commercial-field"><span>{mode === 'revision' ? 'Revision date *' : 'Estimate date *'}</span><input required type="date" value={estimateDate} onChange={e=>setEstimateDate(e.target.value)}/></label>
                {mode === 'revision' && <label className="commercial-field commercial-span-2"><span>Reason for revision * (scope / value change, client reference)</span><textarea required value={reason} onChange={e=>setReason(e.target.value)}/></label>}
                <div className="commercial-span-2"><PendingDocumentsPicker docs={docs} onChange={setDocs} disabled={busy}/></div>
                <div className="commercial-actions commercial-span-2"><button className="commercial-button" disabled={busy}><Save size={15}/>{mode === 'revision' ? `Submit Revision ${nextRevision}` : 'Save Baseline'}</button>{mode === 'legacy_baseline' && baseline && !baseline.is_locked && baseline.status !== 'PENDING_APPROVAL' && <button type="button" className="commercial-button secondary" disabled={busy} onClick={()=>void submitBaseline()}><Send size={15}/> Submit to Finance</button>}</div>
              </form>)}
        </>}
      </main>
    </div>
    {selected && <section className="commercial-panel"><header><div><span className="commercial-kicker">IMMUTABLE HISTORY</span><h2>Commercial Revision History</h2><p>Revision 1 is the approved baseline; later revisions never overwrite it. Every foreign-currency value keeps the FX snapshot used for that event.</p></div><CircleDollarSign size={22}/></header>{estimates.length===0?<div className="commercial-empty">No detailed commercial estimate has been recorded yet.</div>:<div className="commercial-table-wrap"><table className="commercial-table"><thead><tr><th>Revision</th><th>Status</th><th>Estimate</th><th>Revenue Base (INR)</th><th>FX Snapshot</th><th>Reason / Decision</th></tr></thead><tbody>{estimates.map(row=><tr key={row.id}><td><strong>R{row.revision_no}</strong>{row.is_baseline&&<><br/><small>Approved baseline{row.is_locked?' · locked':''}</small></>}</td><td><span className={`commercial-status ${statusTone(row.status)}`}>{statusLabel(row.status)}</span></td><td>{money(row.estimated_amount,row.currency_code)}<br/><small>{row.billing_type_label || statusLabel(row.billing_type)}{row.unit_rate!=null?` · ${money(row.unit_rate,row.currency_code)}/${row.quantity_unit||'unit'}`:''} · {row.tax_percent}% tax · gross {money(row.expected_gross,row.currency_code)}</small></td><td><strong>{money(row.base_inr)}</strong><br/><small>Gross {money(row.gross_inr)}</small></td><td>{row.currency_code==='INR'?'INR · rate 1':<>1 {row.currency_code} = ₹{row.fx_rate_to_inr.toLocaleString('en-IN',{maximumFractionDigits:8})}<br/><small>{row.fx_rate_date} · {row.fx_rate_source} · {statusLabel(row.fx_rate_mode)}</small></>}</td><td>{row.reason || row.decision_comments || '—'}{row.reason && row.decision_comments ? <><br/><small>Finance: {row.decision_comments}</small></> : null}</td></tr>)}</tbody></table></div>}</section>}
  </div>
}
