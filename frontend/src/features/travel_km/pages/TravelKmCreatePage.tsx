import { indiaDateInput } from '../../../lib/date'
import { ArrowLeft, Camera, MailPlus, MapPin, Save } from 'lucide-react'
import * as exifr from 'exifr'
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
  const [travelDate, setTravelDate] = useState(() => indiaDateInput())
  const [purpose, setPurpose] = useState('')
  const [startKm, setStartKm] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)
  const [photoGps, setPhotoGps] = useState<PhotoGps | null>(null)
  const [photoGpsState, setPhotoGpsState] = useState<'idle' | 'reading' | 'missing'>('idle')
  const [photoGpsNote, setPhotoGpsNote] = useState('')
  const photoInputRef = useRef<HTMLInputElement | null>(null)
  const photoRequestRef = useRef(0)
  // Start Journey geo-tagged photo preview and actions. One file is used by the existing submit handler.
  const [photoPreviewUrl, setPhotoPreviewUrl] = useState<string | null>(null)
  useEffect(() => {
    if (!photo) { setPhotoPreviewUrl(null); return }
    const url = URL.createObjectURL(photo)
    setPhotoPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [photo])
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
        <div className="travel-km-gps-card" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div className="travel-km-inline" style={{ gap: 8, flexWrap: 'wrap' }}>
            <MapPin size={16}/>
            <strong>Geo-Tagged Images</strong>
            <span>{photoGpsState === 'reading' ? 'Reading photo metadata...' : photoGps ? 'Valid geo-tagged photo' : photo ? 'Photo needs valid GPS tags' : 'No photo selected'}</span>
          </div>
          <span style={{ fontSize: 12 }}>Upload one original photo showing the Start odometer reading, with GPS location tagging enabled (maximum 15 MB).</span>
          <input
            ref={photoInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            aria-label="Select Start Journey geo-tagged odometer photo"
            style={{ display: 'none' }}
            onChange={e => void readPhotoGps(e.target.files?.[0] || null)}
          />
          <div className="travel-km-actions" style={{ margin: 0 }}>
            <button
              className="travel-km-secondary"
              type="button"
              disabled={photoGpsState === 'reading' || loading}
              onClick={() => { if (photoInputRef.current) { photoInputRef.current.value = ''; photoInputRef.current.click() } }}
            >
              <Camera size={15}/>{photoGpsState === 'reading' ? 'Reading GPS...' : photo ? 'Replace Geo-Tagged Photo' : 'Add Geo-Tagged Photo'}
            </button>
          </div>
          {photo && <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {photoPreviewUrl && <img src={photoPreviewUrl} alt="Selected Start Journey odometer evidence" style={{ width: '100%', maxHeight: 210, objectFit: 'contain', borderRadius: 10, background: 'rgba(100,116,139,0.08)' }}/>} 
            <span style={{ fontSize: 12, overflowWrap: 'anywhere' }}>{photo.name} ({(photo.size / 1024 / 1024).toFixed(2)} MB)</span>
            {photoGps && <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
              <span><strong>Photo GPS:</strong> {photoGps.latitude.toFixed(6)}, {photoGps.longitude.toFixed(6)}</span>
              <span><strong>Capture time:</strong> {photoGps.timeLabel}</span>
              <span style={{ color: '#16803c', fontWeight: 600 }}>GPS metadata found</span>
            </div>}
            <div className="travel-km-actions" style={{ margin: 0, flexWrap: 'wrap' }}>
              <button className="travel-km-secondary" type="button" disabled={!photoPreviewUrl} onClick={() => { if (photoPreviewUrl) window.open(photoPreviewUrl, '_blank', 'noopener,noreferrer') }}>View Photo</button>
              <button className="travel-km-secondary" type="button" disabled={loading} onClick={() => { void readPhotoGps(null); if (photoInputRef.current) photoInputRef.current.value = '' }}>Remove Photo</button>
            </div>
          </div>}
          {photoGpsNote && <small role="alert" style={{ color: '#b42318' }}>{photoGpsNote}</small>}
        </div>
      </div>
      <div className="travel-km-actions"><button className="travel-km-primary" type="submit" disabled={loading || openProjectCount === 0}><Save size={16}/>{loading ? 'Creating Claim...' : 'Start Travel Claim'}</button></div>
    </form>
  </div>
}
