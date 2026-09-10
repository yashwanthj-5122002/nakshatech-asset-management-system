import { ArrowLeft, BadgeCheck, Camera, CheckCircle2, Download, Gauge, LocateFixed, Mail, MailCheck, MailWarning, MapPin, Navigation, Radio, RefreshCw, Route, Send, Settings2, ShieldCheck, Square, Target, TriangleAlert, UserCheck, XCircle } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { useAuth } from '../../../context/AuthContext'
import { apiFetch, downloadFile } from '../../../lib/api'
import type { CapturedGps, TravelKmAttachment, TravelKmClaim, TravelKmProjectGeofence, TravelKmSmartVerification, TravelKmTrackingSnapshot } from '../travel-km-types'
import { EmailRecipientChips, isValidTravelEmail } from '../EmailRecipientChips'
import { captureLiveGps, displayDate, km, money, statusTone, travelStatusLabels, verificationLabel, workflowStage } from '../travel-km-utils'
import '../travel-km.css'

interface PreviewMap { [attachmentId: number]: string }

function Workflow({ claim }: { claim: TravelKmClaim }) {
  const stage = workflowStage(claim.status)
  const steps = ['Employee Submitted', 'Admin Verified', 'HR Approved', 'Finance Review', 'Finance Approved']
  return <div className="travel-km-workflow">{steps.map((label, index) => <div className={`travel-km-step ${stage >= index + 1 ? 'done' : ''}`} key={label}><i>{index + 1}</i><span>{label}</span></div>)}</div>
}

function EvidenceCard({ claim, attachment, previews }: { claim: TravelKmClaim, attachment?: TravelKmAttachment, previews: PreviewMap }) {
  const phase = attachment?.phase || 'start'
  return <article className="travel-km-evidence">
    <div className="travel-km-inline"><Camera size={17}/><div><span className="travel-km-kicker">{phase.toUpperCase()} EVIDENCE</span><h3>{phase === 'start' ? 'Start Odometer' : 'End Odometer'}</h3></div></div>
    {attachment && previews[attachment.id] ? <img src={previews[attachment.id]} alt={`${phase} odometer evidence`} /> : <div className="travel-km-evidence-placeholder">{attachment ? 'Loading secure preview...' : 'No evidence uploaded'}</div>}
    {attachment && <>
      <div className="travel-km-evidence-meta">
        <div><small>Live GPS</small><strong>{attachment.device_latitude.toFixed(6)}, {attachment.device_longitude.toFixed(6)}</strong></div>
        <div><small>GPS Accuracy</small><strong>{attachment.device_accuracy_m == null ? 'N/A' : `${Math.round(attachment.device_accuracy_m)} m`}</strong></div>
        <div><small>Captured</small><strong>{displayDate(attachment.device_captured_at)}</strong></div>
        <div><small>Verification</small><strong>{verificationLabel(attachment.verification_flag)}</strong></div>
        <div><small>Image EXIF GPS</small><strong>{attachment.exif_gps_present ? 'Present' : 'Not present'}</strong></div>
        <div><small>EXIF vs Live GPS</small><strong>{attachment.exif_device_distance_m == null ? 'N/A' : `${Math.round(attachment.exif_device_distance_m)} m`}</strong></div>
      </div>
      <div className="travel-km-actions"><a className="travel-km-secondary" href={`https://www.google.com/maps/search/?api=1&query=${attachment.device_latitude},${attachment.device_longitude}`} target="_blank" rel="noreferrer"><MapPin size={15}/> View GPS on Map</a><a className="travel-km-secondary" href={`https://www.openstreetmap.org/?mlat=${attachment.device_latitude}&mlon=${attachment.device_longitude}#map=18/${attachment.device_latitude}/${attachment.device_longitude}&layers=M`} target="_blank" rel="noreferrer"><MapPin size={15}/> OpenStreetMap</a><button className="travel-km-secondary" onClick={() => void downloadFile(`/travel-km/claims/${claim.id}/attachments/${attachment.id}/download`, attachment.original_filename)}><Download size={15}/> Download Original</button></div>
    </>}
  </article>
}

function LiveRoutePreview({ tracking }: { tracking: TravelKmTrackingSnapshot }) {
  const points = tracking.points
  if (points.length === 0) return <div className="travel-km-route-empty"><Navigation size={24}/><span>No live route points yet. Start tracking on the employee phone to build the route.</span></div>
  const lats = points.map(point => point.latitude)
  const lons = points.map(point => point.longitude)
  const minLat = Math.min(...lats); const maxLat = Math.max(...lats)
  const minLon = Math.min(...lons); const maxLon = Math.max(...lons)
  const latSpan = Math.max(maxLat - minLat, 0.00001)
  const lonSpan = Math.max(maxLon - minLon, 0.00001)
  const coords = points.map(point => {
    const x = 8 + ((point.longitude - minLon) / lonSpan) * 84
    const y = 92 - ((point.latitude - minLat) / latSpan) * 84
    return `${x.toFixed(2)},${y.toFixed(2)}`
  }).join(' ')
  const first = points[0]; const last = points[points.length - 1]
  return <div className="travel-km-route-preview">
    <svg viewBox="0 0 100 100" role="img" aria-label="Live GPS route preview"><polyline points={coords} fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/><circle cx={8 + ((first.longitude - minLon) / lonSpan) * 84} cy={92 - ((first.latitude - minLat) / latSpan) * 84} r="2.8"/><circle className="travel-km-route-current" cx={8 + ((last.longitude - minLon) / lonSpan) * 84} cy={92 - ((last.latitude - minLat) / latSpan) * 84} r="3.6"/></svg>
    <div className="travel-km-route-caption"><span>Start</span><span>Latest GPS</span></div>
  </div>
}


export function TravelKmDetailPage() {
  const { id } = useParams()
  const { user } = useAuth()
  const [claim, setClaim] = useState<TravelKmClaim | null>(null)
  const [previews, setPreviews] = useState<PreviewMap>({})
  const [startKmEdit, setStartKmEdit] = useState('')
  const [endKm, setEndKm] = useState('')
  const [endGps, setEndGps] = useState<CapturedGps | null>(null)
  const [endPhoto, setEndPhoto] = useState<File | null>(null)
  const [startReplacePhoto, setStartReplacePhoto] = useState<File | null>(null)
  const [endReplacePhoto, setEndReplacePhoto] = useState<File | null>(null)
  const [startReplaceGps, setStartReplaceGps] = useState<CapturedGps | null>(null)
  const [endReplaceGps, setEndReplaceGps] = useState<CapturedGps | null>(null)
  const [eligibleKm, setEligibleKm] = useState('')
  const [comments, setComments] = useState('')
  const [reportingManagerEmail, setReportingManagerEmail] = useState('')
  const [toEmails, setToEmails] = useState<string[]>([])
  const [ccEmails, setCcEmails] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [tracking, setTracking] = useState<TravelKmTrackingSnapshot | null>(null)
  const [verification, setVerification] = useState<TravelKmSmartVerification | null>(null)
  const [projectGeofence, setProjectGeofence] = useState<TravelKmProjectGeofence | null>(null)
  const [geofenceSiteName, setGeofenceSiteName] = useState('')
  const [geofenceLatitude, setGeofenceLatitude] = useState('')
  const [geofenceLongitude, setGeofenceLongitude] = useState('')
  const [geofenceRadius, setGeofenceRadius] = useState('500')
  const [geofenceActive, setGeofenceActive] = useState(true)
  const [trackingBusy, setTrackingBusy] = useState(false)
  const [isWatchingGps, setIsWatchingGps] = useState(false)
  const watchIdRef = useRef<number | null>(null)
  const lastPointSentAtRef = useRef(0)

  const staffView = user?.role !== 'employee'
  const backPath = user?.role === 'employee' ? '/travel-km' : user?.role === 'admin' ? '/admin/travel-km' : user?.role === 'hr' ? '/hr/travel-km' : user?.role === 'finance' ? '/finance/travel-km' : user?.role === 'software_team' ? '/software-team' : '/management/travel-km'

  function applyClaim(next: TravelKmClaim) {
    setClaim(next)
    setStartKmEdit(String(next.start_km))
    setEndKm(next.end_km == null ? '' : String(next.end_km))
    const defaultEligible = next.hr_eligible_km ?? next.admin_eligible_km ?? next.odometer_km
    setEligibleKm(defaultEligible == null ? '' : String(defaultEligible))
    setReportingManagerEmail(next.email_routing?.reporting_manager_email || '')
    setToEmails(next.email_routing?.to_emails || [])
    setCcEmails(next.email_routing?.cc_emails || [])
  }

  async function load() {
    if (!id) return
    setLoading(true); setError('')
    try { applyClaim(await apiFetch<TravelKmClaim>(`/travel-km/claims/${id}`)) }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not load travel claim') }
    finally { setLoading(false) }
  }
  useEffect(() => { void load() }, [id])


  async function loadTracking() {
    if (!id) return
    try { setTracking(await apiFetch<TravelKmTrackingSnapshot>(`/travel-km/claims/${id}/tracking`)) }
    catch { /* Claim view remains usable if live tracking status cannot be refreshed. */ }
  }

  async function loadVerification() {
    if (!id) return
    try { setVerification(await apiFetch<TravelKmSmartVerification>(`/travel-km/claims/${id}/verification`)) }
    catch { /* Smart verification is advisory; the main claim view remains usable if it cannot refresh. */ }
  }

  async function loadProjectGeofence(projectId: number) {
    try {
      const result = await apiFetch<TravelKmProjectGeofence>(`/travel-km/projects/${projectId}/geofence`)
      setProjectGeofence(result)
      setGeofenceSiteName(result.site_name || '')
      setGeofenceLatitude(result.center_latitude == null ? '' : String(result.center_latitude))
      setGeofenceLongitude(result.center_longitude == null ? '' : String(result.center_longitude))
      setGeofenceRadius(result.radius_m == null ? '500' : String(result.radius_m))
      setGeofenceActive(result.configured ? result.active : true)
    } catch { setProjectGeofence(null) }
  }

  useEffect(() => {
    void loadTracking()
    const timer = window.setInterval(() => void loadTracking(), 10_000)
    return () => window.clearInterval(timer)
  }, [id])

  useEffect(() => { void loadVerification() }, [id, tracking?.point_count, claim?.updated_at])

  useEffect(() => {
    if (claim?.project_id) void loadProjectGeofence(claim.project_id)
  }, [claim?.project_id])

  useEffect(() => () => {
    if (watchIdRef.current != null && navigator.geolocation) navigator.geolocation.clearWatch(watchIdRef.current)
  }, [])

  useEffect(() => {
    if (!claim) return
    let cancelled = false
    for (const item of claim.attachments) {
      if (previews[item.id]) continue
      void apiFetch<{ data_url: string }>(`/travel-km/claims/${claim.id}/attachments/${item.id}/preview`)
        .then(result => { if (!cancelled) setPreviews(current => ({ ...current, [item.id]: result.data_url })) })
        .catch(() => undefined)
    }
    return () => { cancelled = true }
  }, [claim])

  const startAttachment = useMemo(() => claim?.attachments.find(item => item.phase === 'start'), [claim])
  const endAttachment = useMemo(() => claim?.attachments.find(item => item.phase === 'end'), [claim])

  function browserGpsError(error: GeolocationPositionError): string {
    if (error.code === error.PERMISSION_DENIED) return 'Location permission was denied. Allow precise location for this site and try again.'
    if (error.code === error.POSITION_UNAVAILABLE) return 'Phone GPS is unavailable. Turn on Location/GPS and try again.'
    return 'Live GPS update timed out. Keep the Travel/KM page open and move to an area with better GPS reception.'
  }

  async function sendTrackPosition(position: GeolocationPosition, force = false) {
    if (!claim) return
    const now = Date.now()
    if (!force && now - lastPointSentAtRef.current < 10_000) return
    lastPointSentAtRef.current = now
    try {
      const coords = position.coords
      await apiFetch(`/travel-km/claims/${claim.id}/tracking/point`, { method: 'POST', body: JSON.stringify({
        latitude: coords.latitude, longitude: coords.longitude,
        accuracy_m: Number.isFinite(coords.accuracy) ? coords.accuracy : null,
        speed_mps: coords.speed != null && Number.isFinite(coords.speed) && coords.speed >= 0 ? coords.speed : null,
        heading_deg: coords.heading != null && Number.isFinite(coords.heading) && coords.heading >= 0 ? coords.heading : null,
        captured_at: new Date(position.timestamp || Date.now()).toISOString(),
      }) })
      await loadTracking()
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not send live GPS update') }
  }

  async function startLiveTracking() {
    if (!claim) return
    if (!navigator.geolocation) return setError('This phone/browser does not provide GPS location access.')
    setTrackingBusy(true); setError('')
    try {
      const first = await new Promise<GeolocationPosition>((resolve, reject) => navigator.geolocation.getCurrentPosition(resolve, reject, { enableHighAccuracy: true, timeout: 20_000, maximumAge: 0 }))
      await apiFetch(`/travel-km/claims/${claim.id}/tracking/start`, { method: 'POST' })
      await sendTrackPosition(first, true)
      if (watchIdRef.current != null) navigator.geolocation.clearWatch(watchIdRef.current)
      watchIdRef.current = navigator.geolocation.watchPosition(
        position => { void sendTrackPosition(position) },
        geoError => setError(browserGpsError(geoError)),
        { enableHighAccuracy: true, timeout: 20_000, maximumAge: 5_000 },
      )
      setIsWatchingGps(true)
      await loadTracking()
    } catch (err) {
      if (typeof err === 'object' && err !== null && 'code' in err) setError(browserGpsError(err as GeolocationPositionError))
      else setError(err instanceof Error ? err.message : 'Could not start live GPS tracking')
    } finally { setTrackingBusy(false) }
  }

  async function stopLiveTracking(silent = false) {
    if (!claim) return
    if (watchIdRef.current != null && navigator.geolocation) navigator.geolocation.clearWatch(watchIdRef.current)
    watchIdRef.current = null; setIsWatchingGps(false)
    if (!silent) { setTrackingBusy(true); setError('') }
    try {
      setTracking(await apiFetch<TravelKmTrackingSnapshot>(`/travel-km/claims/${claim.id}/tracking/stop`, { method: 'POST' }))
    } catch (err) { if (!silent) setError(err instanceof Error ? err.message : 'Could not stop live GPS tracking') }
    finally { if (!silent) setTrackingBusy(false) }
  }

  async function captureEndGps() {
    setBusy('gps'); setError('')
    try { setEndGps(await captureLiveGps()) }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not capture End GPS') }
    finally { setBusy('') }
  }

  async function saveEndJourney() {
    if (!claim) return
    if (!(Number(endKm) >= claim.start_km)) return setError('End KM must be equal to or greater than Start KM.')
    if (!endGps) return setError('Capture live End GPS before saving the End Journey.')
    if (!endPhoto && !endAttachment) return setError('Capture or select the End odometer photo.')
    setBusy('end'); setError('')
    try {
      if (isWatchingGps || tracking?.tracking_active) await stopLiveTracking(true)
      let next = await apiFetch<TravelKmClaim>(`/travel-km/claims/${claim.id}/end`, { method: 'PUT', body: JSON.stringify({ end_km: Number(endKm), end_latitude: endGps.latitude, end_longitude: endGps.longitude, end_accuracy_m: endGps.accuracy, end_captured_at: endGps.capturedAt }) })
      if (endPhoto) {
        const form = new FormData(); form.append('file', endPhoto)
        const params = new URLSearchParams({ phase: 'end', latitude: String(endGps.latitude), longitude: String(endGps.longitude), captured_at: endGps.capturedAt })
        if (endGps.accuracy != null) params.set('accuracy_m', String(endGps.accuracy))
        await apiFetch(`/travel-km/claims/${claim.id}/attachments?${params.toString()}`, { method: 'POST', body: form })
        next = await apiFetch<TravelKmClaim>(`/travel-km/claims/${claim.id}`)
      }
      applyClaim(next); setEndPhoto(null)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not save End Journey') }
    finally { setBusy('') }
  }


  async function captureReplacementGps(phase: 'start' | 'end') {
    setBusy(`gps-${phase}`); setError('')
    try {
      const gps = await captureLiveGps()
      if (phase === 'start') setStartReplaceGps(gps); else setEndReplaceGps(gps)
    } catch (err) { setError(err instanceof Error ? err.message : `Could not capture ${phase} GPS`) }
    finally { setBusy('') }
  }

  async function saveMissingStartEvidence() {
    if (!claim) return
    if (!startReplacePhoto) return setError('Capture or select the Start odometer photo.')
    if (!startReplaceGps) return setError('Capture fresh live Start GPS before uploading the Start odometer evidence.')
    if (startReplacePhoto.size > 15 * 1024 * 1024) return setError('Start odometer photo must be 15 MB or smaller.')
    setBusy('start-evidence'); setError('')
    try {
      const form = new FormData(); form.append('file', startReplacePhoto)
      const params = new URLSearchParams({ phase: 'start', latitude: String(startReplaceGps.latitude), longitude: String(startReplaceGps.longitude), captured_at: startReplaceGps.capturedAt })
      if (startReplaceGps.accuracy != null) params.set('accuracy_m', String(startReplaceGps.accuracy))
      await apiFetch(`/travel-km/claims/${claim.id}/attachments?${params.toString()}`, { method: 'POST', body: form })
      applyClaim(await apiFetch<TravelKmClaim>(`/travel-km/claims/${claim.id}`))
      setStartReplacePhoto(null); setStartReplaceGps(null)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not upload Start odometer evidence') }
    finally { setBusy('') }
  }

  async function saveCorrections() {
    if (!claim) return
    if (!(Number(startKmEdit) >= 0) || !(Number(endKm) >= Number(startKmEdit))) return setError('Corrected End KM must be equal to or greater than corrected Start KM.')
    const replacements: Array<{phase: 'start'|'end', file: File | null, gps: CapturedGps | null}> = [
      { phase: 'start', file: startReplacePhoto, gps: startReplaceGps },
      { phase: 'end', file: endReplacePhoto, gps: endReplaceGps },
    ]
    for (const item of replacements) {
      if (item.file && !item.gps) return setError(`Capture live ${item.phase} GPS before replacing the ${item.phase} odometer image.`)
      if (item.file && item.file.size > 15 * 1024 * 1024) return setError(`${item.phase === 'start' ? 'Start' : 'End'} odometer photo must be 15 MB or smaller.`)
    }
    setBusy('corrections'); setError('')
    try {
      let next = await apiFetch<TravelKmClaim>(`/travel-km/claims/${claim.id}/revise`, { method: 'PUT', body: JSON.stringify({ start_km: Number(startKmEdit), end_km: Number(endKm) }) })
      for (const item of replacements) {
        if (!item.file || !item.gps) continue
        const form = new FormData(); form.append('file', item.file)
        const params = new URLSearchParams({ phase: item.phase, latitude: String(item.gps.latitude), longitude: String(item.gps.longitude), captured_at: item.gps.capturedAt })
        if (item.gps.accuracy != null) params.set('accuracy_m', String(item.gps.accuracy))
        await apiFetch(`/travel-km/claims/${claim.id}/attachments?${params.toString()}`, { method: 'POST', body: form })
      }
      next = await apiFetch<TravelKmClaim>(`/travel-km/claims/${claim.id}`)
      applyClaim(next); setStartReplacePhoto(null); setEndReplacePhoto(null); setStartReplaceGps(null); setEndReplaceGps(null)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not save employee corrections') }
    finally { setBusy('') }
  }

  async function saveEmailRouting() {
    if (!claim) return
    if (!isValidTravelEmail(reportingManagerEmail)) return setError('Enter a valid Reporting Manager email address.')
    if (toEmails.length === 0) return setError('Add at least one TO email recipient.')
    setBusy('email-routing'); setError('')
    try {
      applyClaim(await apiFetch<TravelKmClaim>(`/travel-km/claims/${claim.id}/email-routing`, {
        method: 'PUT',
        body: JSON.stringify({ reporting_manager_email: reportingManagerEmail.trim().toLowerCase(), to_emails: toEmails, cc_emails: ccEmails }),
      }))
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not save Travel/KM email recipients') }
    finally { setBusy('') }
  }

  async function retryEmail() {
    if (!claim) return
    setBusy('email-retry'); setError('')
    try { applyClaim(await apiFetch<TravelKmClaim>(`/travel-km/claims/${claim.id}/email/retry`, { method: 'POST' })) }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not retry Travel/KM email') }
    finally { setBusy('') }
  }

  async function saveProjectGeofence() {
    if (!claim || user?.role !== 'admin') return
    if (geofenceSiteName.trim().length < 2) return setError('Enter a project site name for the geofence.')
    const latitude = Number(geofenceLatitude); const longitude = Number(geofenceLongitude); const radius = Number(geofenceRadius)
    if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90) return setError('Enter a valid project-site latitude.')
    if (!Number.isFinite(longitude) || longitude < -180 || longitude > 180) return setError('Enter a valid project-site longitude.')
    if (!Number.isFinite(radius) || radius < 50 || radius > 10000) return setError('Geofence radius must be between 50 m and 10,000 m.')
    setBusy('geofence'); setError('')
    try {
      const result = await apiFetch<TravelKmProjectGeofence>(`/travel-km/projects/${claim.project_id}/geofence`, {
        method: 'PUT',
        body: JSON.stringify({ site_name: geofenceSiteName.trim(), center_latitude: latitude, center_longitude: longitude, radius_m: radius, is_active: geofenceActive }),
      })
      setProjectGeofence(result)
      await loadVerification()
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not save project-site geofence') }
    finally { setBusy('') }
  }

  async function submitClaim() {
    if (!claim) return
    if (!claim.email_routing || claim.email_routing.to_emails.length === 0) return setError('Save Reporting Manager and TO/CC email recipients before submitting the claim.')
    setBusy('submit'); setError('')
    try { applyClaim(await apiFetch<TravelKmClaim>(`/travel-km/claims/${claim.id}/submit`, { method: 'POST' })) }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not submit claim') }
    finally { setBusy('') }
  }

  async function decision(stage: 'admin' | 'hr', action: 'approve' | 'send_back' | 'reject') {
    if (!claim) return
    setBusy(`${stage}-${action}`); setError('')
    try {
      applyClaim(await apiFetch<TravelKmClaim>(`/travel-km/claims/${claim.id}/${stage}-decision`, { method: 'POST', body: JSON.stringify({ action, comments: comments.trim(), eligible_km: action === 'approve' ? Number(eligibleKm) : null }) }))
      setComments('')
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not save approval decision') }
    finally { setBusy('') }
  }

  async function finance(action: 'approve' | 'reject') {
    if (!claim) return
    setBusy(`finance-${action}`); setError('')
    try {
      applyClaim(await apiFetch<TravelKmClaim>(`/travel-km/claims/${claim.id}/finance-decision`, { method: 'POST', body: JSON.stringify({ action, comments: comments.trim() }) }))
      setComments('')
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not save Finance decision') }
    finally { setBusy('') }
  }

  if (loading) return <div className="travel-km-page"><div className="travel-km-panel travel-km-empty">Loading travel workflow...</div></div>
  if (!claim) return <div className="travel-km-page"><div className="travel-km-error">{error || 'Travel claim not found.'}</div></div>
  const varianceAlert = (claim.distance_variance_percent || 0) > 25

  return <div className="travel-km-page">
    <DashboardHeader eyebrow={staffView ? 'TRAVEL KM · WORKFLOW REVIEW' : 'EMPLOYEE TRAVEL & KM'} title={claim.claim_code} description={`${claim.project_code} · ${claim.project_name || 'Project'}${claim.client_name ? ` · ${claim.client_name}` : ''} · ${claim.employee_name}`} actions={<Link className="travel-km-secondary" to={backPath}><ArrowLeft size={16}/> Back</Link>} />
    {error && <div className="travel-km-error">{error}</div>}
    {user?.role === 'management' && <div className="travel-km-readonly-banner"><ShieldCheck size={18}/><span>Management read-only oversight: Vinod and Chethan can see the complete Employee → Admin → HR → Finance movement, evidence and final monthly-salary approval status without operational approval controls.</span></div>}

    <section className="travel-km-panel"><div className="travel-km-inline"><Route size={18}/><div><span className="travel-km-kicker">LIVE WORKFLOW</span><h2>{travelStatusLabels[claim.status] || claim.status}</h2></div><span className={`travel-km-status ${statusTone(claim.status)}`}>{travelStatusLabels[claim.status] || claim.status}</span></div><Workflow claim={claim}/></section>

    <section className="travel-km-panel travel-km-email-card">
      <div className="travel-km-email-card-heading"><Mail size={19}/><div><span className="travel-km-kicker">EMAIL NOTIFICATION</span><h2>Reporting Manager, TO & CC</h2><p>The employee chooses recipients manually in this test version. The mail is triggered only when the completed claim is submitted.</p></div></div>
      {claim.permissions.can_edit_email_routing ? <div className="travel-km-form-grid">
        <label className="travel-km-field full"><span>Reporting Manager Email *</span><input type="email" value={reportingManagerEmail} onChange={e => setReportingManagerEmail(e.target.value)} placeholder="reporting.manager@nakshatech.com"/><small>The Reporting Manager is automatically kept in the actual TO list.</small></label>
        <EmailRecipientChips label="TO *" values={toEmails} onChange={setToEmails} placeholder="Type email and press Enter" help="Add HR, Admin, Finance, Manager, Management or any other valid recipient."/>
        <EmailRecipientChips label="CC" values={ccEmails} onChange={setCcEmails} placeholder="Type CC email and press Enter" help="Multiple CC email addresses are supported."/>
        <div className="travel-km-actions full"><button type="button" className="travel-km-secondary" onClick={() => void saveEmailRouting()} disabled={busy === 'email-routing'}><MailCheck size={16}/>{busy === 'email-routing' ? 'Saving Recipients...' : 'Save Email Recipients'}</button></div>
      </div> : claim.email_routing ? <div className="travel-km-email-readonly">
        <div><small>Reporting Manager</small><strong>{claim.email_routing.reporting_manager_email}</strong></div>
        <div><small>TO</small><div className="travel-km-email-chips">{claim.email_routing.to_emails.map(email => <span className="travel-km-email-chip" key={email}>{email}</span>)}</div></div>
        <div><small>CC</small><div className="travel-km-email-chips">{claim.email_routing.cc_emails.length ? claim.email_routing.cc_emails.map(email => <span className="travel-km-email-chip" key={email}>{email}</span>) : <span className="travel-km-email-none">No CC recipients</span>}</div></div>
      </div> : <div className="travel-km-email-note is-warning"><MailWarning size={16}/> Email recipients were not configured on this older draft. The employee must add them before submission.</div>}
      <div className="travel-km-email-history">
        <div className="travel-km-email-history-head"><strong>Mail Notification History</strong>{claim.permissions.can_retry_email && <button type="button" className="travel-km-secondary" onClick={() => void retryEmail()} disabled={busy === 'email-retry'}><RefreshCw size={15}/>{busy === 'email-retry' ? 'Retrying...' : 'Retry Email'}</button>}</div>
        {claim.email_history.length === 0 ? <span className="travel-km-email-none">No email has been sent yet. Submission will create the first mail record.</span> : [...claim.email_history].reverse().map(item => <article className="travel-km-email-history-row" key={item.id}>
          <div><span className={`travel-km-mail-status ${item.status}`}>{item.status === 'console' ? 'TEST / CONSOLE' : item.status.toUpperCase()}</span><strong>{item.event_type.replaceAll('_', ' ')}</strong><small>{displayDate(item.attempted_at)}</small></div>
          <div><small>TO</small><span>{item.to_emails.join(', ')}</span></div>
          <div><small>CC</small><span>{item.cc_emails.length ? item.cc_emails.join(', ') : 'None'}</span></div>
          {item.error_message && <div className="travel-km-email-history-error"><MailWarning size={14}/>{item.error_message}</div>}
        </article>)}
      </div>
    </section>

    <section className="travel-km-stat-grid">
      <article className="travel-km-stat"><span>Odometer Distance</span><strong>{km(claim.odometer_km)}</strong><small>{claim.start_km.toFixed(2)} → {claim.end_km == null ? 'Pending' : claim.end_km.toFixed(2)}</small></article>
      <article className="travel-km-stat"><span>GPS Straight-Line</span><strong>{km(claim.gps_straight_line_km)}</strong><small>Start ↔ End geolocation reference</small></article>
      <article className="travel-km-stat"><span>Distance Variance</span><strong>{claim.distance_variance_percent == null ? 'Pending' : `${claim.distance_variance_percent.toFixed(2)}%`}</strong><small>{varianceAlert ? 'Review variance carefully' : 'Odometer vs straight-line reference'}</small></article>
      <article className="travel-km-stat"><span>Allowance @ ₹5/KM</span><strong>{money(claim.final_allowance ?? claim.calculated_allowance)}</strong><small>Final eligible KM: {km(claim.final_eligible_km ?? claim.odometer_km)}</small></article>
    </section>

    <section className="travel-km-panel travel-km-smart-panel">
      <div className="travel-km-smart-header"><div className="travel-km-inline"><Gauge size={19}/><div><span className="travel-km-kicker">V5 · SMART JOURNEY VERIFICATION</span><h2>Evidence Confidence Score</h2></div></div>{verification && <span className={`travel-km-smart-outcome ${verification.outcome}`}>{verification.outcome_label}</span>}</div>
      {!verification ? <div className="travel-km-empty">Calculating journey evidence...</div> : <>
        <div className="travel-km-smart-summary"><div className="travel-km-score-ring"><strong>{verification.score == null ? '—' : verification.score}</strong><span>/ 100</span></div><div><strong>{verification.score == null ? 'Complete End Journey evidence to generate the final score.' : `${verification.outcome_label} · ${verification.score}/100`}</strong><p>{verification.snapshot_locked ? `Submission snapshot locked ${displayDate(verification.generated_at)}.` : 'Live preview updates as GPS and evidence are collected.'}</p><small>{verification.scoring_note}</small></div></div>
        <div className="travel-km-smart-metrics">
          <div><small>Tracked Route</small><strong>{km(verification.route.route_distance_km)}</strong></div>
          <div><small>Odometer vs Route</small><strong>{verification.route.variance_percent == null ? 'Pending' : `${verification.route.variance_percent.toFixed(1)}%`}</strong></div>
          <div><small>GPS Points</small><strong>{verification.route.point_count}</strong></div>
          <div><small>Median Accuracy</small><strong>{verification.route.median_accuracy_m == null ? 'N/A' : `${Math.round(verification.route.median_accuracy_m)} m`}</strong></div>
          <div><small>Largest GPS Gap</small><strong>{verification.route.max_gap_seconds == null ? 'N/A' : verification.route.max_gap_seconds < 60 ? `${Math.round(verification.route.max_gap_seconds)} sec` : `${Math.round(verification.route.max_gap_seconds / 60)} min`}</strong></div>
          <div><small>GPS Jumps Filtered</small><strong>{verification.route.discarded_segments}</strong></div>
        </div>
        <div className="travel-km-score-components">{verification.components.map(component => <div className="travel-km-score-row" key={component.key}><div><span>{component.label}</span><strong>{component.earned}/{component.available}</strong></div><div className="travel-km-score-track"><i style={{width: `${component.available ? (component.earned / component.available) * 100 : 0}%`}}/></div></div>)}</div>
        {verification.flags.length > 0 ? <div className="travel-km-smart-flags">{verification.flags.map(flag => <div className={`travel-km-smart-flag ${flag.severity}`} key={`${flag.code}-${flag.message}`}><TriangleAlert size={15}/><span>{flag.message}</span></div>)}</div> : <div className="travel-km-smart-clear"><CheckCircle2 size={16}/> No review flags in the current evidence set.</div>}
      </>}
    </section>

    <section className="travel-km-panel travel-km-geofence-panel">
      <div className="travel-km-inline"><Target size={19}/><div><span className="travel-km-kicker">PROJECT / SITE GEOFENCE</span><h2>{staffView && projectGeofence?.configured ? projectGeofence.site_name : 'Assigned Project Site'}</h2></div></div>
      {projectGeofence?.configured ? <div className="travel-km-geofence-grid">
        <div><small>Site Center</small><strong>{staffView && projectGeofence.center_latitude != null && projectGeofence.center_longitude != null ? `${projectGeofence.center_latitude.toFixed(6)}, ${projectGeofence.center_longitude.toFixed(6)}` : 'Protected project-site coordinates'}</strong></div>
        <div><small>Allowed Radius</small><strong>{Math.round(projectGeofence.radius_m || 0)} m</strong></div>
        <div><small>Geofence Status</small><strong>{projectGeofence.active ? 'Active' : 'Disabled'}</strong></div>
        <div><small>Journey Entered Site</small><strong>{verification?.geofence.site_entered ? '✓ Yes' : verification?.geofence.configured ? 'Not detected' : 'Not scored'}</strong></div>
        <div><small>Nearest Route Point</small><strong>{verification?.geofence.nearest_distance_m == null ? 'N/A' : `${Math.round(verification.geofence.nearest_distance_m)} m`}</strong></div>
        <div><small>Verified On-Site Time</small><strong>{verification?.geofence.onsite_minutes ? `${verification.geofence.onsite_minutes} min` : '0 min'}</strong></div>
      </div> : <div className="travel-km-geofence-empty"><MapPin size={17}/><span>No active project-site geofence is configured. Smart verification does not deduct geofence points when the project has no site zone.</span></div>}
      {verification?.geofence.first_entry_at && <div className="travel-km-geofence-entry"><CheckCircle2 size={15}/> First site entry detected {displayDate(verification.geofence.first_entry_at)}.</div>}
      {user?.role === 'admin' && <div className="travel-km-geofence-admin"><div className="travel-km-inline"><Settings2 size={16}/><strong>Admin · Configure Project Site</strong></div><p>This is project-level master data. Management remains read-only. A submitted verification snapshot stays locked; configuration changes apply to draft/future submissions.</p><div className="travel-km-form-grid"><label className="travel-km-field full"><span>Site Name *</span><input value={geofenceSiteName} onChange={e => setGeofenceSiteName(e.target.value)} placeholder="Example: Arkavathi Survey Site"/></label><label className="travel-km-field"><span>Latitude *</span><input type="number" step="0.000001" value={geofenceLatitude} onChange={e => setGeofenceLatitude(e.target.value)} placeholder="12.971600"/></label><label className="travel-km-field"><span>Longitude *</span><input type="number" step="0.000001" value={geofenceLongitude} onChange={e => setGeofenceLongitude(e.target.value)} placeholder="77.594600"/></label><label className="travel-km-field"><span>Radius (metres) *</span><input type="number" min="50" max="10000" step="10" value={geofenceRadius} onChange={e => setGeofenceRadius(e.target.value)}/></label><label className="travel-km-field travel-km-checkbox-field"><span>Active</span><input type="checkbox" checked={geofenceActive} onChange={e => setGeofenceActive(e.target.checked)}/></label></div><div className="travel-km-actions"><button type="button" className="travel-km-secondary" onClick={() => void saveProjectGeofence()} disabled={busy === 'geofence'}><Target size={15}/>{busy === 'geofence' ? 'Saving Site...' : 'Save Project Geofence'}</button></div></div>}
    </section>

    <section className="travel-km-panel travel-km-live-panel">
      <div className="travel-km-live-header"><div className="travel-km-inline"><Radio size={18}/><div><span className="travel-km-kicker">REAL-TIME JOURNEY GPS</span><h2>Live GPS Tracking</h2></div></div><span className={`travel-km-live-badge ${tracking?.live_now ? 'is-live' : tracking?.tracking_active ? 'is-waiting' : ''}`}>{tracking?.live_now ? '● LIVE' : tracking?.tracking_active ? 'Waiting for phone' : 'Stopped'}</span></div>
      <p>Tracking starts only when the employee taps <strong>Start Live GPS Tracking</strong> and grants phone location permission. It is limited to this active Travel/KM journey and stops when End Journey is saved.</p>
      {user?.role === 'employee' && claim.permissions.can_edit && !claim.end_captured_at && <div className="travel-km-actions">
        {!isWatchingGps ? <button type="button" className="travel-km-primary" onClick={() => void startLiveTracking()} disabled={trackingBusy}><LocateFixed size={16}/>{trackingBusy ? 'Starting GPS...' : tracking?.tracking_active ? 'Resume Live GPS' : 'Start Live GPS Tracking'}</button> : <button type="button" className="travel-km-danger" onClick={() => void stopLiveTracking()} disabled={trackingBusy}><Square size={15}/> Stop Live GPS</button>}
      </div>}
      <div className="travel-km-live-grid">
        <div><small>GPS Points</small><strong>{tracking?.point_count ?? 0}</strong></div>
        <div><small>Tracked Route Distance</small><strong>{km(tracking?.route_distance_km)}</strong></div>
        <div><small>Last GPS Update</small><strong>{tracking?.last_point ? displayDate(tracking.last_point.captured_at) : 'Waiting'}</strong></div>
        <div><small>Latest Accuracy</small><strong>{tracking?.last_point?.accuracy_m == null ? 'N/A' : `${Math.round(tracking.last_point.accuracy_m)} m`}</strong></div>
      </div>
      {tracking && <LiveRoutePreview tracking={tracking}/>}
      {tracking?.last_point && <div className="travel-km-actions"><a className="travel-km-secondary" href={`https://www.google.com/maps/search/?api=1&query=${tracking.last_point.latitude},${tracking.last_point.longitude}`} target="_blank" rel="noreferrer"><MapPin size={15}/> Open Latest GPS on Map</a><a className="travel-km-secondary" href={`https://www.openstreetmap.org/?mlat=${tracking.last_point.latitude}&mlon=${tracking.last_point.longitude}#map=18/${tracking.last_point.latitude}/${tracking.last_point.longitude}&layers=M`} target="_blank" rel="noreferrer"><MapPin size={15}/> OpenStreetMap</a></div>}
      <div className="travel-km-tracking-note"><ShieldCheck size={16}/><span>{tracking?.foreground_tracking_note || 'For reliable browser tracking, keep the Travel/KM page open. Mobile browsers can pause GPS when the phone is locked or the browser is suspended.'}</span></div>
    </section>

    <section className="travel-km-panel"><span className="travel-km-kicker">TRAVEL DETAILS</span><h2>Claim & Project Information</h2><div className="travel-km-evidence-meta" style={{marginTop:12}}><div><small>Employee</small><strong>{claim.employee_name} · {claim.employee_id || 'No ID'}</strong></div><div><small>Department</small><strong>{claim.department || 'Not specified'}</strong></div><div><small>Project</small><strong>{claim.project_code} · {claim.project_name || 'Project'}</strong></div><div><small>Client</small><strong>{claim.client_name || 'Not specified'}</strong></div><div><small>Travel Date</small><strong>{claim.travel_date}</strong></div><div><small>Purpose</small><strong>{claim.purpose_description}</strong></div><div><small>Start GPS</small><strong>{claim.start_latitude.toFixed(6)}, {claim.start_longitude.toFixed(6)} · {claim.start_accuracy_m == null ? 'accuracy N/A' : `${Math.round(claim.start_accuracy_m)} m`}</strong></div><div><small>End GPS</small><strong>{claim.end_latitude == null ? 'Pending' : `${claim.end_latitude.toFixed(6)}, ${claim.end_longitude?.toFixed(6)} · ${claim.end_accuracy_m == null ? 'accuracy N/A' : `${Math.round(claim.end_accuracy_m)} m`}`}</strong></div></div></section>

    {claim.permissions.can_edit && !startAttachment && <section className="travel-km-panel travel-km-form"><div><span className="travel-km-kicker">EMPLOYEE · START EVIDENCE RECOVERY</span><h2>Start Odometer Evidence Required</h2><p>The draft exists, but the Start image is missing. Capture fresh live GPS and attach the Start odometer image before submission.</p></div><div className="travel-km-form-grid"><div className="travel-km-gps-card"><strong>Fresh Start GPS</strong><span>{startReplaceGps ? `${startReplaceGps.latitude.toFixed(6)}, ${startReplaceGps.longitude.toFixed(6)} · ${startReplaceGps.accuracy == null ? 'N/A' : `${Math.round(startReplaceGps.accuracy)} m`}` : 'Not captured'}</span><button className="travel-km-secondary" type="button" onClick={() => void captureReplacementGps('start')} disabled={busy === 'gps-start'}><LocateFixed size={15}/>{busy === 'gps-start' ? 'Capturing...' : 'Capture Start GPS'}</button></div><label className="travel-km-field"><span>Start Odometer Photo *</span><input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={e => setStartReplacePhoto(e.target.files?.[0] || null)} /></label></div><button className="travel-km-primary" type="button" onClick={() => void saveMissingStartEvidence()} disabled={busy === 'start-evidence'}><Camera size={16}/>{busy === 'start-evidence' ? 'Uploading...' : 'Save Start Evidence'}</button></section>}

    {claim.permissions.can_edit && !claim.end_captured_at && <section className="travel-km-panel travel-km-form"><div><span className="travel-km-kicker">EMPLOYEE · END JOURNEY</span><h2>Capture End KM + Geo-Tagged Evidence</h2><p>The application calculates odometer KM, straight-line GPS reference, variance and ₹5/KM allowance after this step.</p></div><div className="travel-km-form-grid"><label className="travel-km-field"><span>End KM *</span><input type="number" min={claim.start_km} step="0.01" value={endKm} onChange={e => setEndKm(e.target.value)} /></label><div className="travel-km-gps-card"><strong>Live End GPS</strong><span>{endGps ? `${endGps.latitude.toFixed(6)}, ${endGps.longitude.toFixed(6)} · ${endGps.accuracy == null ? 'N/A' : `${Math.round(endGps.accuracy)} m`}` : 'Not captured'}</span><button type="button" className="travel-km-secondary" onClick={() => void captureEndGps()} disabled={busy === 'gps'}><LocateFixed size={15}/>{busy === 'gps' ? 'Capturing...' : 'Capture End GPS'}</button></div><label className="travel-km-field full"><span>End Odometer Photo *</span><input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={e => setEndPhoto(e.target.files?.[0] || null)} /></label></div><button className="travel-km-primary" onClick={() => void saveEndJourney()} disabled={busy === 'end'}><Camera size={16}/>{busy === 'end' ? 'Saving...' : 'Save End Journey'}</button></section>}

    <section className="travel-km-panel"><span className="travel-km-kicker">GEO-TAGGED ODOMETER PROOF</span><h2>Travel Verification Evidence</h2><p>Live device GPS is stored independently of image metadata. EXIF GPS is compared when the source image contains it.</p><div className="travel-km-evidence-grid"><EvidenceCard claim={claim} attachment={startAttachment} previews={previews}/><EvidenceCard claim={claim} attachment={endAttachment} previews={previews}/></div></section>


    {claim.permissions.can_edit && claim.end_captured_at && <section className="travel-km-panel travel-km-form"><div><span className="travel-km-kicker">EMPLOYEE CORRECTION / RESUBMISSION</span><h2>Correct KM or Replace Geo-Tagged Evidence</h2><p>Use this section when Admin or HR sends the claim back. Any replacement photo must be paired with a fresh live GPS capture.</p></div><div className="travel-km-form-grid"><label className="travel-km-field"><span>Start KM</span><input type="number" min="0" step="0.01" value={startKmEdit} onChange={e => setStartKmEdit(e.target.value)} /></label><label className="travel-km-field"><span>End KM</span><input type="number" min={Number(startKmEdit) || 0} step="0.01" value={endKm} onChange={e => setEndKm(e.target.value)} /></label><div className="travel-km-gps-card"><strong>Replace Start Evidence</strong><span>{startReplaceGps ? `${startReplaceGps.latitude.toFixed(6)}, ${startReplaceGps.longitude.toFixed(6)}` : 'Use only if Start evidence needs correction.'}</span><button className="travel-km-secondary" type="button" onClick={() => void captureReplacementGps('start')} disabled={busy === 'gps-start'}><LocateFixed size={15}/> Capture Fresh Start GPS</button><input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={e => setStartReplacePhoto(e.target.files?.[0] || null)} /></div><div className="travel-km-gps-card"><strong>Replace End Evidence</strong><span>{endReplaceGps ? `${endReplaceGps.latitude.toFixed(6)}, ${endReplaceGps.longitude.toFixed(6)}` : 'Use only if End evidence needs correction.'}</span><button className="travel-km-secondary" type="button" onClick={() => void captureReplacementGps('end')} disabled={busy === 'gps-end'}><LocateFixed size={15}/> Capture Fresh End GPS</button><input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={e => setEndReplacePhoto(e.target.files?.[0] || null)} /></div></div><button className="travel-km-secondary" onClick={() => void saveCorrections()} disabled={busy === 'corrections'}><RefreshCw size={16}/>{busy === 'corrections' ? 'Saving Corrections...' : 'Save Corrections'}</button></section>}

    {claim.permissions.can_submit && claim.end_captured_at && <section className="travel-km-panel"><span className="travel-km-kicker">EMPLOYEE SUBMISSION</span><h2>Send for Admin Verification</h2><p>Confirm both odometer photos, start/end KM, GPS locations and calculated allowance before submission. V5 freezes the current Smart Journey Verification score as an advisory audit snapshot when you submit.</p><button className="travel-km-primary" onClick={() => void submitClaim()} disabled={busy === 'submit'}><Send size={16}/>{busy === 'submit' ? 'Submitting...' : claim.status.includes('sent_back') ? 'Resubmit Claim' : 'Submit Claim'}</button></section>}

    {(claim.permissions.can_admin_decide || claim.permissions.can_hr_decide) && <section className="travel-km-panel travel-km-review"><div className="travel-km-inline">{claim.permissions.can_admin_decide ? <ShieldCheck size={18}/> : <UserCheck size={18}/>}<div><span className="travel-km-kicker">{claim.permissions.can_admin_decide ? 'ADMIN VERIFICATION' : 'HR VERIFICATION'}</span><h2>{claim.permissions.can_admin_decide ? 'Verify Travel Evidence' : 'Verify Eligibility & Policy'}</h2></div></div><div className="travel-km-review-grid"><label className="travel-km-field"><span>Eligible KM</span><input type="number" min="0" max={claim.permissions.can_hr_decide ? claim.admin_eligible_km ?? claim.odometer_km ?? 0 : claim.odometer_km ?? 0} step="0.01" value={eligibleKm} onChange={e => setEligibleKm(e.target.value)} /></label><label className="travel-km-field"><span>Verification Remarks</span><textarea value={comments} onChange={e => setComments(e.target.value)} placeholder="Required for Send Back / Reject and whenever eligible KM is adjusted." /></label></div><div className="travel-km-actions"><button className="travel-km-primary" onClick={() => void decision(claim.permissions.can_admin_decide ? 'admin' : 'hr', 'approve')} disabled={Boolean(busy)}><CheckCircle2 size={16}/> Approve</button><button className="travel-km-warning" onClick={() => void decision(claim.permissions.can_admin_decide ? 'admin' : 'hr', 'send_back')} disabled={Boolean(busy)}><RefreshCw size={16}/> Send Back</button><button className="travel-km-danger" onClick={() => void decision(claim.permissions.can_admin_decide ? 'admin' : 'hr', 'reject')} disabled={Boolean(busy)}><XCircle size={16}/> Reject</button></div></section>}

    {(claim.permissions.can_finance_decide ?? claim.permissions.can_finance_pay) && <section className="travel-km-panel travel-km-review"><div className="travel-km-inline"><BadgeCheck size={18}/><div><span className="travel-km-kicker">FINANCE APPROVAL</span><h2>Final Approval for Monthly Salary Addition</h2></div></div><p>The approved allowance is system-controlled: {km(claim.final_eligible_km)} × ₹5 = <strong>{money(claim.final_allowance)}</strong>. Finance only approves or rejects this claim. No payment, UTR, bank mode or cash entry is required because the allowance is added through the monthly salary process.</p><div className="travel-km-review-grid"><label className="travel-km-field full"><span>Finance Remarks</span><textarea value={comments} onChange={e => setComments(e.target.value)} placeholder="Optional for approval; required if Finance rejects the claim." /></label></div><div className="travel-km-actions"><button className="travel-km-primary" onClick={() => void finance('approve')} disabled={Boolean(busy)}><BadgeCheck size={16}/> Approve for Monthly Salary · {money(claim.final_allowance)}</button><button className="travel-km-danger" onClick={() => void finance('reject')} disabled={Boolean(busy)}><XCircle size={16}/> Reject</button></div></section>}

    {(claim.status === 'finance_approved' || claim.status === 'paid') && <div className="travel-km-success"><CheckCircle2 size={17}/><span>Finance approval completed. This final status is visible to the Employee, Admin, HR and Management, and the approved allowance is ready for monthly salary processing.</span></div>}

    <section className="travel-km-panel"><span className="travel-km-kicker">FULL AUDIT MOVEMENT</span><h2>Employee → Admin → HR → Finance Timeline</h2><div className="travel-km-timeline" style={{marginTop:14}}>{[...claim.events].reverse().map(event => <div className="travel-km-event" key={event.id}><span className="travel-km-event-dot"/><div className="travel-km-event-body"><strong>{event.action.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}</strong><span>{event.actor_name} · {event.actor_role.replaceAll('_', ' ')}</span>{event.comments && <span>{event.comments}</span>}<small>{displayDate(event.created_at)}{event.from_status || event.to_status ? ` · ${event.from_status || 'start'} → ${event.to_status || 'same'}` : ''}</small></div></div>)}</div></section>
  </div>
}
