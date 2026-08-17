import {
  type PointerEvent as ReactPointerEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import Globe, { type GlobeMethods } from 'react-globe.gl'
import { feature as topojsonFeature } from 'topojson-client'
import worldAtlas from 'world-atlas/countries-110m.json'
import '../login-geo-tour.css'

type PolygonGeometry = {
  type: 'Polygon' | 'MultiPolygon'
  coordinates: unknown
}

type BaseGeoFeature = {
  type: 'Feature'
  id?: string | number
  properties?: Record<string, unknown>
  geometry: PolygonGeometry
}

type WorldCountry = BaseGeoFeature & {
  displayName: string
}

type GeoFeatureCollection = {
  type: 'FeatureCollection'
  features: BaseGeoFeature[]
}

type NetworkNode = {
  id: string
  lat: number
  lng: number
}

type NetworkArc = {
  id: string
  startLat: number
  startLng: number
  endLat: number
  endLng: number
}

const DEFAULT_POV = { lat: 18, lng: 58, altitude: 1.56 }
const MOBILE_POV = { lat: 17, lng: 66, altitude: 2.08 }

// Decorative coordinates only. These do not represent live NakshaTech locations,
// asset routes, customers, or operational telemetry.
const NETWORK_NODES: NetworkNode[] = [
  { id: 'n1', lat: 37.8, lng: -122.4 },
  { id: 'n2', lat: 51.5, lng: -0.1 },
  { id: 'n3', lat: 25.2, lng: 55.3 },
  { id: 'n4', lat: 12.9, lng: 77.6 },
  { id: 'n5', lat: 1.3, lng: 103.8 },
  { id: 'n6', lat: -33.9, lng: 151.2 },
  { id: 'n7', lat: 35.7, lng: 139.7 },
]

const NETWORK_ARCS: NetworkArc[] = [
  { id: 'a1', startLat: 37.8, startLng: -122.4, endLat: 51.5, endLng: -0.1 },
  { id: 'a2', startLat: 51.5, startLng: -0.1, endLat: 25.2, endLng: 55.3 },
  { id: 'a3', startLat: 25.2, startLng: 55.3, endLat: 12.9, endLng: 77.6 },
  { id: 'a4', startLat: 12.9, startLng: 77.6, endLat: 1.3, endLng: 103.8 },
  { id: 'a5', startLat: 1.3, startLng: 103.8, endLat: -33.9, endLng: 151.2 },
  { id: 'a6', startLat: 35.7, startLng: 139.7, endLat: 12.9, endLng: 77.6 },
]

function isPolygonGeometry(geometry: unknown): geometry is PolygonGeometry {
  if (!geometry || typeof geometry !== 'object') return false
  const type = (geometry as { type?: unknown }).type
  return type === 'Polygon' || type === 'MultiPolygon'
}

export function NakshaGeoTourOverlay({ onComplete: _onComplete }: { onComplete: () => void }) {
  const globeRef = useRef<GlobeMethods>()
  const hostRef = useRef<HTMLDivElement | null>(null)
  const hitboxRef = useRef<HTMLDivElement | null>(null)
  const pointerFrameRef = useRef<number | null>(null)
  const [dimensions, setDimensions] = useState({ width: 1280, height: 760 })
  const [ready, setReady] = useState(false)
  const [reducedMotion, setReducedMotion] = useState(false)
  const [compact, setCompact] = useState(false)
  const [pointerActive, setPointerActive] = useState(false)

  const countries = useMemo<WorldCountry[]>(() => {
    const topology = worldAtlas as unknown as { objects: { countries: unknown } }
    const collection = topojsonFeature(
      worldAtlas as never,
      topology.objects.countries as never,
    ) as unknown as GeoFeatureCollection

    return collection.features
      .filter((feature) => isPolygonGeometry(feature.geometry))
      .map((feature) => ({
        ...feature,
        displayName: String(feature.properties?.name ?? 'Country'),
      }))
  }, [])

  useEffect(() => {
    const host = hostRef.current
    if (!host || typeof window === 'undefined') return

    const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    const pointerQuery = window.matchMedia('(pointer: coarse)')

    const syncPreferences = () => setReducedMotion(motionQuery.matches)
    const resize = () => {
      const rect = host.getBoundingClientRect()
      setDimensions({
        width: Math.max(320, Math.round(rect.width)),
        height: Math.max(320, Math.round(rect.height)),
      })
      setCompact(rect.width < 860 || pointerQuery.matches)
    }

    syncPreferences()
    resize()

    const observer = new ResizeObserver(resize)
    observer.observe(host)
    motionQuery.addEventListener?.('change', syncPreferences)
    pointerQuery.addEventListener?.('change', resize)

    return () => {
      observer.disconnect()
      motionQuery.removeEventListener?.('change', syncPreferences)
      pointerQuery.removeEventListener?.('change', resize)
      if (pointerFrameRef.current !== null) window.cancelAnimationFrame(pointerFrameRef.current)
    }
  }, [])

  useEffect(() => {
    if (!ready) return
    const globe = globeRef.current
    const controls = globe?.controls()
    if (!globe || !controls) return

    controls.enableDamping = true
    controls.dampingFactor = 0.075
    controls.enablePan = false
    controls.enableZoom = false
    controls.enableRotate = false
    controls.autoRotate = !reducedMotion && !compact
    controls.autoRotateSpeed = 0.24

    globe.pointOfView(compact ? MOBILE_POV : DEFAULT_POV, reducedMotion ? 0 : 720)
  }, [compact, ready, reducedMotion])

  useEffect(() => {
    const onVisibilityChange = () => {
      if (document.hidden) globeRef.current?.pauseAnimation()
      else globeRef.current?.resumeAnimation()
    }
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => document.removeEventListener('visibilitychange', onVisibilityChange)
  }, [])

  function resetPointer() {
    const host = hostRef.current
    const hitbox = hitboxRef.current
    if (!host || !hitbox) return

    setPointerActive(false)
    host.style.setProperty('--ambient-shift-x', '0px')
    host.style.setProperty('--ambient-shift-y', '0px')
    host.style.setProperty('--ambient-tilt-x', '0deg')
    host.style.setProperty('--ambient-tilt-y', '0deg')
    hitbox.style.setProperty('--ambient-cursor-x', '50%')
    hitbox.style.setProperty('--ambient-cursor-y', '50%')
    hitbox.style.setProperty('--ambient-glow-x', '50%')
    hitbox.style.setProperty('--ambient-glow-y', '50%')
  }

  function movePointer(event: ReactPointerEvent<HTMLDivElement>) {
    if (compact || reducedMotion) return
    const host = hostRef.current
    const hitbox = hitboxRef.current
    if (!host || !hitbox) return

    if (pointerFrameRef.current !== null) window.cancelAnimationFrame(pointerFrameRef.current)
    const clientX = event.clientX
    const clientY = event.clientY

    pointerFrameRef.current = window.requestAnimationFrame(() => {
      const rect = hitbox.getBoundingClientRect()
      const x = Math.max(0, Math.min(rect.width, clientX - rect.left))
      const y = Math.max(0, Math.min(rect.height, clientY - rect.top))
      const nx = rect.width ? (x / rect.width) * 2 - 1 : 0
      const ny = rect.height ? (y / rect.height) * 2 - 1 : 0

      host.style.setProperty('--ambient-shift-x', `${nx * 7}px`)
      host.style.setProperty('--ambient-shift-y', `${ny * 5}px`)
      host.style.setProperty('--ambient-tilt-x', `${ny * -0.65}deg`)
      host.style.setProperty('--ambient-tilt-y', `${nx * 0.85}deg`)
      hitbox.style.setProperty('--ambient-cursor-x', `${x}px`)
      hitbox.style.setProperty('--ambient-cursor-y', `${y}px`)
      hitbox.style.setProperty('--ambient-glow-x', `${x}px`)
      hitbox.style.setProperty('--ambient-glow-y', `${y}px`)
      setPointerActive(true)
      pointerFrameRef.current = null
    })
  }

  const visibleRings = reducedMotion ? [] : NETWORK_NODES

  return (
    <div
      ref={hostRef}
      className={`naksha-geo-tour naksha-ambient-globe${ready ? ' is-ready' : ''}${pointerActive ? ' is-pointer-active' : ''}`}
      aria-hidden="true"
    >
      <div className="naksha-geo-tour-stage naksha-ambient-globe-stage">
        <Globe
          ref={globeRef}
          width={dimensions.width}
          height={dimensions.height}
          globeOffset={compact ? [0, 0] : [-72, 0]}
          backgroundColor="rgba(0,0,0,0)"
          showAtmosphere
          atmosphereColor="#16c7e8"
          atmosphereAltitude={0.13}
          rendererConfig={{ antialias: !compact, alpha: true }}
          animateIn={!reducedMotion}
          polygonsData={countries}
          polygonCapColor={() => 'rgba(5, 36, 62, .74)'}
          polygonSideColor={() => 'rgba(2, 18, 34, .30)'}
          polygonStrokeColor={() => 'rgba(55, 163, 211, .58)'}
          polygonAltitude={0.002}
          polygonCapCurvatureResolution={compact ? 8 : 4}
          polygonsTransitionDuration={0}
          arcsData={NETWORK_ARCS}
          arcStartLat="startLat"
          arcStartLng="startLng"
          arcEndLat="endLat"
          arcEndLng="endLng"
          arcColor={() => 'rgba(62, 217, 241, .56)'}
          arcAltitudeAutoScale={0.22}
          arcStroke={0.28}
          arcDashLength={0.28}
          arcDashGap={0.72}
          arcDashAnimateTime={reducedMotion ? 0 : 4200}
          arcsTransitionDuration={0}
          pointsData={NETWORK_NODES}
          pointLat="lat"
          pointLng="lng"
          pointColor={() => 'rgba(220, 252, 255, .96)'}
          pointAltitude={0.012}
          pointRadius={0.11}
          pointResolution={8}
          ringsData={visibleRings}
          ringLat="lat"
          ringLng="lng"
          ringColor={() => 'rgba(62, 225, 241, .42)'}
          ringMaxRadius={2.2}
          ringPropagationSpeed={1.25}
          ringRepeatPeriod={2200}
          onGlobeReady={() => setReady(true)}
          enablePointerInteraction={false}
          showPointerCursor={false}
        />
      </div>

      <div className="naksha-ambient-orbits" aria-hidden="true">
        <span className="naksha-ambient-orbit naksha-ambient-orbit--outer"><i /></span>
        <span className="naksha-ambient-orbit naksha-ambient-orbit--mid"><i /></span>
        <span className="naksha-ambient-orbit naksha-ambient-orbit--inner"><i /></span>
      </div>

      <div className="naksha-ambient-globe-vignette" />
      <div className="naksha-ambient-scan" />

      <div
        ref={hitboxRef}
        className="naksha-ambient-globe-hitbox"
        onPointerEnter={() => !compact && setPointerActive(true)}
        onPointerMove={movePointer}
        onPointerLeave={resetPointer}
      >
        <span className="naksha-ambient-inspection-lens">
          <i className="naksha-ambient-lens-tick naksha-ambient-lens-tick--top" />
          <i className="naksha-ambient-lens-tick naksha-ambient-lens-tick--right" />
          <i className="naksha-ambient-lens-tick naksha-ambient-lens-tick--bottom" />
          <i className="naksha-ambient-lens-tick naksha-ambient-lens-tick--left" />
        </span>
        <span className="naksha-ambient-cursor" />
        <span className="naksha-ambient-cursor-trail" />
      </div>

      <div className="naksha-ambient-status">
        <span className="naksha-ambient-status-pulse" />
        <div>
          <strong>NAKSHA DIGITAL ASSET NETWORK</strong>
          <small>Interactive ambient visualization</small>
        </div>
      </div>

      <div className="naksha-ambient-orbit-label" aria-hidden="true">
        <span>GLOBAL</span>
        <i />
        <span>CONNECTED</span>
        <i />
        <span>CONTROLLED</span>
      </div>
    </div>
  )
}
