import { ArrowLeft, Camera, MailPlus, MapPin, Save } from 'lucide-react'
import exifr from 'exifr'
import { type FormEvent, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import type { TravelKmClaim, TravelKmProjectGeofence } from '../travel-km-types'
import { EmailRecipientChips, isValidTravelEmail } from '../EmailRecipientChips'
import '../travel-km.css'

type ProjectOption = { id: number; project_number: string; project_name: string; task?: string | null; lifecycle_status: string; claim_allowed: boolean; claim_block_reason?: string | null }

/** Photo GPS comes only from the image EXIF metadata; no browser location permission is used. */
type PhotoGps = { latitude: number; longitude: number; capturedAt: string; timeLabel: string }

function localStamp(value: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}T${pad(value.getHours())}:${pad(value.getMinutes())}:${pad(value.getSeconds())}`
}

function photoTimeLabel(value: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())} ${pad(value.getHours())}:${pad(value.getMinutes())}:${pad(value.getSeconds())}`
}

export function TravelKmCreatePage() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState<ProjectOption[]>([])
  const [projectId, setProjectId] = useState('')
  const [travelDate, setTravelDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [purpose, setPurpose] = useState('')
  const [startKm, setStartKm] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)
  const [photoGps, setPhotoGps] = useState<PhotoGps | null>(null)
  const [photoGpsState, setPhotoGpsState] = useState<'idle' | 'reading' | 'missing'>('idle')
  const [photoGpsNote, setPhotoGpsNote] = useState('')
  const photoInputRef = useRef<HTMLInputElement | null>(null)
  const photoRequestRef = useRef(0)
  const [reportingManagerEmail, setReportingManagerEmail] = useState('')
  const [toEmails, setToEmails] = useState<string[]>([])
  const [ccEmails, setCcEmails] = useState<string[]>([])
  const [projectGeofence, setProjectGeofence] = useState<TravelKmProjectGeofence | null>(null)
  const [loading, setLoading] = useState(false)
  const [initialLoading, setInitialLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    void apiFetch<ProjectOption[]>('/travel-km/projects')
      .then(rows => {
        if (cancelled) return
        setProjects(rows)
      })
      .catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load Project Numbers') })
      .finally(() => { if (!cancelled) setInitialLoading(false) })
    return () => { cancelled = true }
  }, [])

  const selectedProject = projects.find(item => String(item.id) === projectId) || null
  const openProjectCount = projects.filter(item => item.claim_allowed).length

  useEffect(() => {
    if (!projectId) { setProjectGeofence(null); return }
    let cancelled = false
    void apiFetch<TravelKmProjectGeofence>(`/travel-km/projects/${projectId}/geofence`)
      .then(result => { if (!cancelled) setProjectGeofence(result) })
      .catch(() => { if (!cancelled) setProjectGeofence(null) })
    return () => { cancelled = true }
  }, [projectId])

  async function readPhotoGps(file: File | null) {
    const request = ++photoRequestRef.current
    setPhoto(file)
    setPhotoGps(null)
    setPhotoGpsNote('')
    if (!file) { setPhotoGpsState('idle'); return }
    setPhotoGpsState('reading')
    try {
      const gps = await exifr.gps(file)
      if (request !== photoRequestRef.current) return
      const latitude = Number(gps?.latitude)
      const longitude = Number(gps?.longitude)
      if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) {
        setPhotoGpsState('missing')
        setPhotoGpsNote(`${file.name}: no GPS tag found. Use the original camera photo with location tagging enabled.`)
        return
      }
      const exif = await exifr.parse(file, ['DateTimeOriginal', 'CreateDate']) as { DateTimeOriginal?: unknown; CreateDate?: unknown } | undefined
      if (request !== photoRequestRef.current) return
      const takenAt = exif?.DateTimeOriginal ?? exif?.CreateDate
      const stamp = takenAt instanceof Date && Number.isFinite(takenAt.getTime())
        ? takenAt
        : new Date(file.lastModified || Date.now())
      setPhotoGps({ latitude, longitude, capturedAt: localStamp(stamp), timeLabel: photoTimeLabel(stamp) })
      setPhotoGpsState('idle')
    } catch {
      if (request !== photoRequestRef.current) return
      setPhotoGpsState('missing')
      setPhotoGpsNote(`${file.name}: GPS metadata could not be read from this photo.`)
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!projectId || !selectedProject) return setError('Select an active ongoing Project ID.')
    if (!selectedProject.claim_allowed) return setError(selectedProject.claim_block_reason || 'This project is not open for new Travel/KM claims.')
    if (purpose.trim().length < 5) return setError('Enter the travel purpose.')
    if (!isValidTravelEmail(reportingManagerEmail)) return setError('Enter a valid Reporting Manager email address.')
    if (toEmails.length === 0) return setError('Add at least one TO email recipient. The Reporting Manager is included automatically as well.')
    if (!(Number(startKm) >= 0)) return setError('Enter a valid Start KM.')
    if (!photo) return setError('Capture or select the Start odometer photo.')
    if (photo.size > 15 * 1024 * 1024) return setError('Start odometer photo must be 15 MB or smaller.')
    if (!photoGps) return setError('The Start odometer photo has no GPS tag. Use the original camera photo with location tagging enabled.')
    setLoading(true); setError('')
    let createdClaimId: number | null = null
    try {
      const claim = await apiFetch<TravelKmClaim>('/travel-km/claims', { method: 'POST', body: JSON.stringify({
        project_id: Number(projectId), travel_date: travelDate, purpose_description: purpose.trim(), start_km: Number(startKm),
        start_latitude: photoGps.latitude, start_longitude: photoGps.longitude, start_accuracy_m: null, start_captured_at: photoGps.capturedAt,
        email_routing: { reporting_manager_email: reportingManagerEmail.trim().toLowerCase(), to_emails: toEmails, cc_emails: ccEmails },
      }) })
      createdClaimId = claim.id
      const form = new FormData(); form.append('file', photo)
      const params = new URLSearchParams({ phase: 'start', latitude: String(photoGps.latitude), longitude: String(photoGps.longitude), captured_at: photoGps.capturedAt })
      await apiFetch(`/travel-km/claims/${claim.id}/attachments?${params.toString()}`, { method: 'POST', body: form })
      navigate(`/travel-km/${claim.id}`)
    } catch (err) {
      if (createdClaimId) {
        navigate(`/travel-km/${createdClaimId}`)
        return
      }
      setError(err instanceof Error ? err.message : 'Could not create travel claim')
    }
    finally { setLoading(false) }
  }

  if (initialLoading) return <div className="travel-km-page"><div className="travel-km-panel travel-km-empty">Loading Projects...</div></div>

  return <div className="travel-km-page">
    <DashboardHeader eyebrow="EMPLOYEE TRAVEL & KM · START JOURNEY" title="Create Travel Claim" description="Attach a geo-tagged odometer image at the start of project travel. GPS coordinates and the photo time are read from the image EXIF metadata, so no live location permission is requested." actions={<Link className="travel-km-secondary" to="/travel-km"><ArrowLeft size={16}/> My Claims</Link>} />
    {error && <div className="travel-km-error">{error}</div>}
    <form className="travel-km-panel travel-km-form" onSubmit={submit}>
      <div><span className="travel-km-kicker">STEP 1 · PROJECT & PURPOSE</span><h2>Travel Information</h2><p>Select the ongoing Project ID maintained by Finance/Admin. The linked client is resolved automatically in the background. Completed, on-hold, inactive and upcoming projects remain visible for reference but cannot be used for a new claim.</p></div>
      <div className="travel-km-form-grid">
        <label className="travel-km-field"><span>Project ID *</span><select value={projectId} onChange={e => setProjectId(e.target.value)} required><option value="">Select an ongoing Project ID</option>{projects.map(project => <option key={project.id} value={project.id} disabled={!project.claim_allowed}>{project.project_number} · {project.project_name} · {project.claim_allowed ? 'ACTIVE' : project.lifecycle_status.toUpperCase()}</option>)}</select><small>{selectedProject?.task ? `Task: ${selectedProject.task}` : openProjectCount > 0 ? `${openProjectCount} active project(s) are currently open for claims. Client mapping is automatic.` : 'No active project is currently open for a new claim.'}</small></label>
        <label className="travel-km-field"><span>Travel Date *</span><input type="date" value={travelDate} onChange={e => setTravelDate(e.target.value)} required /></label>
        <label className="travel-km-field full"><span>Project Travel Purpose *</span><textarea value={purpose} onChange={e => setPurpose(e.target.value)} placeholder="Explain the site visit, survey, client meeting, project movement, or other official travel purpose." required /></label>
      </div>
      <div className={`travel-km-geofence-banner ${projectGeofence?.configured && projectGeofence.active ? 'is-configured' : ''}`}>
        <MapPin size={18}/><div><strong>Project Site Verification</strong>{projectGeofence?.configured && projectGeofence.active ? <span>Project site zone configured · {Math.round(projectGeofence.radius_m || 0)} m radius. Smart Journey Verification will check whether the live route enters the project zone.</span> : <span>No active site geofence is configured for this Project Number. The claim can still proceed and the verification score will not penalize the employee for an unconfigured geofence.</span>}</div>
      </div>
      <section className="travel-km-email-card">
        <div className="travel-km-email-card-heading"><MailPlus size={19}/><div><span className="travel-km-kicker">STEP 2 · EMAIL NOTIFICATION</span><h2>Submission Email Recipients</h2><p>For this test version, type email addresses manually. The email is sent only when you finally submit the completed Travel/KM claim.</p></div></div>
        <div className="travel-km-form-grid">
          <label className="travel-km-field full"><span>Reporting Manager Email *</span><input type="email" value={reportingManagerEmail} onChange={e => setReportingManagerEmail(e.target.value)} placeholder="reporting.manager@nakshatech.com" autoComplete="email" required/><small>The Reporting Manager is automatically included in the actual TO recipients.</small></label>
          <EmailRecipientChips label="TO *" values={toEmails} onChange={setToEmails} placeholder="Type HR / Admin / Finance / Manager email and press Enter" help="Add one or more recipients. Press Enter after each email."/>
          <EmailRecipientChips label="CC" values={ccEmails} onChange={setCcEmails} placeholder="Type Management or other CC email and press Enter" help="CC is optional and supports multiple email addresses."/>
        </div>
        <div className="travel-km-email-note">Email notification will not be sent at Start Journey. It is sent after End Journey evidence is complete and the employee presses Submit Claim.</div>
      </section>
      <div><span className="travel-km-kicker">STEP 3 · START ODOMETER</span><h2>Start Journey Evidence</h2></div>
      <div className="travel-km-form-grid">
        <label className="travel-km-field"><span>Start KM *</span><input type="number" min="0" step="0.01" value={startKm} onChange={e => setStartKm(e.target.value)} placeholder="Example: 25420" required /></label>
        <div className="travel-km-gps-card"><div className="travel-km-inline"><MapPin size={16}/><strong>Geo-Tagged Images</strong><span>{photoGps ? `${photoGps.latitude.toFixed(6)}, ${photoGps.longitude.toFixed(6)}` : photoGpsState === 'reading' ? 'Reading GPS tags...' : photo ? 'No GPS tag in photo' : 'No photo selected'}</span><span>{photoGps ? `Photo time ${photoGps.timeLabel}` : 'Upload the original odometer photo with GPS location tags enabled.'}</span><button className="travel-km-secondary" type="button" onClick={() => photoInputRef.current?.click()} disabled={photoGpsState === 'reading'}><Camera size={15}/>{photoGpsState === 'reading' ? 'Reading GPS...' : photo ? 'Replace Photo' : 'Add Geo-Tagged Photo'}</button></div>{photoGpsNote && <small>{photoGpsNote}</small>}</div>
        <label className="travel-km-field full"><span>Start Odometer Photo *</span><div className="travel-km-photo-input"><Camera size={18}/><input ref={photoInputRef} type="file" accept="image/jpeg,image/png,image/webp" onChange={e => void readPhotoGps(e.target.files?.[0] || null)} /></div><small>{photo ? `${photo.name} · ${(photo.size / 1024 / 1024).toFixed(2)} MB${photoGps ? ' · GPS tag found' : photoGpsState === 'missing' ? ' · no GPS tag' : ''}` : 'Choose the original odometer photo from the gallery (taken with location tagging enabled). GPS coordinates and photo time are read from the image EXIF metadata, so no precise location permission is required.'}</small></label>
      </div>
      <div className="travel-km-actions"><button className="travel-km-primary" type="submit" disabled={loading || openProjectCount === 0}><Save size={16}/>{loading ? 'Creating Claim...' : 'Start Travel Claim'}</button></div>
    </form>
  </div>
}
