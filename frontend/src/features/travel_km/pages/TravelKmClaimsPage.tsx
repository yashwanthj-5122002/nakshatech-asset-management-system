import { ArrowRight, MapPin, Plus, Route } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import type { TravelKmClaim } from '../travel-km-types'
import { displayDate, km, money, statusTone, travelStatusLabels } from '../travel-km-utils'
import '../travel-km.css'

export function TravelKmClaimsPage() {
  const [claims, setClaims] = useState<TravelKmClaim[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    void apiFetch<TravelKmClaim[]>('/travel-km/claims')
      .then(rows => { if (!cancelled) setClaims(rows) })
      .catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load travel claims') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const totalKm = claims.reduce((sum, item) => sum + (item.odometer_km || 0), 0)
  const totalAllowance = claims.reduce((sum, item) => sum + (item.final_allowance ?? item.calculated_allowance ?? 0), 0)
  const active = claims.filter(item => !['paid', 'admin_rejected', 'hr_rejected', 'finance_rejected'].includes(item.status)).length

  return <div className="travel-km-page">
    <DashboardHeader eyebrow="EMPLOYEE TRAVEL & KM" title="My Travel Claims" description="Capture start/end odometer evidence with live GPS, calculate eligible project travel, and follow the Admin → HR → Finance workflow." actions={<Link className="travel-km-primary" to="/travel-km/new"><Plus size={16}/> New Travel Claim</Link>} />
    {error && <div className="travel-km-error">{error}</div>}
    <section className="travel-km-stat-grid">
      <article className="travel-km-stat"><span>Total claims</span><strong>{claims.length}</strong><small>Your complete claim history</small></article>
      <article className="travel-km-stat"><span>Total odometer KM</span><strong>{km(totalKm)}</strong><small>Recorded project travel</small></article>
      <article className="travel-km-stat"><span>Allowance value</span><strong>{money(totalAllowance)}</strong><small>Calculated / approved value</small></article>
      <article className="travel-km-stat"><span>Active workflow</span><strong>{active}</strong><small>Draft, approval or payment stages</small></article>
    </section>
    <section className="travel-km-panel">
      <div className="travel-km-inline"><Route size={18}/><div><span className="travel-km-kicker">CLAIM HISTORY</span><h2>Project Travel</h2></div></div>
      {loading ? <div className="travel-km-empty">Loading travel claims...</div> : claims.length === 0 ? <div className="travel-km-empty">No travel claims yet. Start your first claim when beginning a project-related journey.</div> : <div className="travel-km-table-wrap"><table className="travel-km-table"><thead><tr><th>Claim</th><th>Project</th><th>Travel Date</th><th>KM</th><th>Allowance</th><th>Status</th><th></th></tr></thead><tbody>{claims.map(claim => <tr key={claim.id}><td><strong>{claim.claim_code}</strong><small style={{display:'block'}}>{claim.department || 'Employee'}</small></td><td><strong>{claim.project_code}{claim.project_name ? ` · ${claim.project_name}` : ''}</strong><small style={{display:'block'}}>{claim.client_name || 'Assigned client/project'}</small></td><td>{displayDate(`${claim.travel_date}T00:00:00`)}</td><td><MapPin size={13}/> {km(claim.odometer_km)}</td><td>{money(claim.final_allowance ?? claim.calculated_allowance)}</td><td><span className={`travel-km-status ${statusTone(claim.status)}`}>{travelStatusLabels[claim.status] || claim.status}</span></td><td><Link className="travel-km-secondary" to={`/travel-km/${claim.id}`}>View <ArrowRight size={14}/></Link></td></tr>)}</tbody></table></div>}
    </section>
  </div>
}
