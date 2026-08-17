import { useEffect, useMemo, useRef, useState } from 'react'
import Globe, { type GlobeMethods } from 'react-globe.gl'
import { feature as topojsonFeature } from 'topojson-client'
import worldAtlas from 'world-atlas/countries-110m.json'
import { LoginParticleField } from './LoginParticleField'
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
  const [dimensions, setDimensions] = useState({ width: 1280, height: 760 })
  const [ready, setReady] = useState(false)
  const [reducedMotion, setReducedMotion] = useState(false)
  const [compact, setCompact] = useState(false)

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
    controls.autoRotateSpeed = 0.22

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

  return (
    <div
      ref={hostRef}
      className={`naksha-geo-tour naksha-particle-globe${ready ? ' is-ready' : ''}`}
      aria-hidden="true"
    >
      <LoginParticleField />

      <div className="naksha-particle-globe-haze" />

      <div className="naksha-geo-tour-stage naksha-particle-globe-stage">
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
          arcColor={() => 'rgba(62, 217, 241, .50)'}
          arcAltitudeAutoScale={0.20}
          arcStroke={0.24}
          arcDashLength={0.24}
          arcDashGap={0.76}
          arcDashAnimateTime={reducedMotion ? 0 : 4800}
          arcsTransitionDuration={0}
          pointsData={NETWORK_NODES}
          pointLat="lat"
          pointLng="lng"
          pointColor={() => 'rgba(220, 252, 255, .94)'}
          pointAltitude={0.012}
          pointRadius={0.095}
          pointResolution={8}
          onGlobeReady={() => setReady(true)}
          enablePointerInteraction={false}
          showPointerCursor={false}
        />
      </div>
    </div>
  )
}
