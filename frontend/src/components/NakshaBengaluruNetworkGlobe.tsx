import { MapPin } from 'lucide-react'
import {
  type PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import Globe, { type GlobeMethods } from 'react-globe.gl'
import { feature as topojsonFeature } from 'topojson-client'
import worldAtlas from 'world-atlas/countries-110m.json'

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

type CountryPolygon = BaseGeoFeature & {
  displayName: string
}

type IndiaStatePolygon = BaseGeoFeature & {
  displayName: string
  isIndiaState: true
}

type IndiaNationalBoundaryPolygon = BaseGeoFeature & {
  displayName: string
  isIndiaNationalBoundary: true
}

type GlobePolygon = CountryPolygon | IndiaStatePolygon | IndiaNationalBoundaryPolygon

type GlobePov = {
  lat: number
  lng: number
  altitude: number
}

type NetworkNode = {
  id: string
  name: string
  lat: number
  lng: number
  kind: 'hub' | 'source'
}

type NetworkArc = {
  id: string
  startLat: number
  startLng: number
  endLat: number
  endLng: number
  phase: number
}

type GeoFeatureCollection = {
  type: 'FeatureCollection'
  features: BaseGeoFeature[]
}

const BENGALURU = {
  id: 'bengaluru',
  name: 'Bengaluru',
  lat: 12.9716,
  lng: 77.5946,
  kind: 'hub' as const,
}

const INDIA_STATES_RENDER_URL = '/data/india-states-globe.b64'
const INDIA_NATIONAL_BOUNDARY_RENDER_URLS = [
  '/data/india-national-boundary-osm/part-01.b64',
  '/data/india-national-boundary-osm/part-02.b64',
  '/data/india-national-boundary-osm/part-03.b64',
] as const
const EXPECTED_INDIA_STATE_COUNT = 36

const NETWORK_SOURCES: NetworkNode[] = [
  { id: 'san-francisco', name: 'San Francisco', lat: 37.7749, lng: -122.4194, kind: 'source' },
  { id: 'new-york', name: 'New York', lat: 40.7128, lng: -74.0060, kind: 'source' },
  { id: 'sao-paulo', name: 'Sao Paulo', lat: -23.5505, lng: -46.6333, kind: 'source' },
  { id: 'london', name: 'London', lat: 51.5074, lng: -0.1278, kind: 'source' },
  { id: 'frankfurt', name: 'Frankfurt', lat: 50.1109, lng: 8.6821, kind: 'source' },
  { id: 'dubai', name: 'Dubai', lat: 25.2048, lng: 55.2708, kind: 'source' },
  { id: 'johannesburg', name: 'Johannesburg', lat: -26.2041, lng: 28.0473, kind: 'source' },
  { id: 'singapore', name: 'Singapore', lat: 1.3521, lng: 103.8198, kind: 'source' },
  { id: 'tokyo', name: 'Tokyo', lat: 35.6762, lng: 139.6503, kind: 'source' },
  { id: 'seoul', name: 'Seoul', lat: 37.5665, lng: 126.9780, kind: 'source' },
  { id: 'sydney', name: 'Sydney', lat: -33.8688, lng: 151.2093, kind: 'source' },
  { id: 'mumbai', name: 'Mumbai', lat: 19.0760, lng: 72.8777, kind: 'source' },
]

const NETWORK_ARCS: NetworkArc[] = NETWORK_SOURCES.map((node, index) => ({
  id: `${node.id}-to-bengaluru`,
  startLat: node.lat,
  startLng: node.lng,
  endLat: BENGALURU.lat,
  endLng: BENGALURU.lng,
  phase: index / NETWORK_SOURCES.length,
}))

const NETWORK_NODES: NetworkNode[] = [...NETWORK_SOURCES, BENGALURU]
const HUB_RING = [{ lat: BENGALURU.lat, lng: BENGALURU.lng }]

const DESKTOP_POV: GlobePov = { lat: 14.8, lng: BENGALURU.lng, altitude: 1.52 }
const MOBILE_POV: GlobePov = { lat: 15.5, lng: BENGALURU.lng, altitude: 2.02 }
const SWEEP_MAX_LNG = 11
const SWEEP_MAX_LAT = 1.6
const POINTER_MAX_LNG = 3.5
const POINTER_MAX_LAT = 2.2
const SWEEP_PERIOD_MS = 18000

function isPolygonGeometry(geometry: BaseGeoFeature['geometry'] | undefined): geometry is PolygonGeometry {
  return geometry?.type === 'Polygon' || geometry?.type === 'MultiPolygon'
}

function normalizeLongitude(value: number) {
  let longitude = value
  while (longitude > 180) longitude -= 360
  while (longitude < -180) longitude += 360
  return longitude
}

function countryId(feature: CountryPolygon) {
  return String(feature.id ?? '').padStart(3, '0')
}

function isIndia(feature: CountryPolygon) {
  return countryId(feature) === '356'
}

function isIndiaStatePolygon(feature: GlobePolygon): feature is IndiaStatePolygon {
  return 'isIndiaState' in feature && feature.isIndiaState === true
}

function isIndiaNationalBoundaryPolygon(feature: GlobePolygon): feature is IndiaNationalBoundaryPolygon {
  return 'isIndiaNationalBoundary' in feature && feature.isIndiaNationalBoundary === true
}

async function decodeCompressedGeoJson(encoded: string, expectedFeatureCount: number): Promise<GeoFeatureCollection> {
  const binary = window.atob(encoded.trim())
  const bytes = Uint8Array.from(binary, char => char.charCodeAt(0))
  const decompressionStream = new DecompressionStream('gzip')
  const stream = new Blob([bytes]).stream().pipeThrough(decompressionStream)
  const json = await new Response(stream).text()
  const parsed = JSON.parse(json) as GeoFeatureCollection

  if (
    parsed.type !== 'FeatureCollection'
    || !Array.isArray(parsed.features)
    || parsed.features.length !== expectedFeatureCount
  ) {
    throw new Error('Invalid India map data')
  }

  return parsed
}

async function fetchText(url: string, label: string): Promise<string> {
  const response = await fetch(url, { cache: 'force-cache' })
  if (!response.ok) throw new Error(`${label} returned HTTP ${response.status}`)
  return response.text()
}

export function NakshaBengaluruNetworkGlobe() {
  const globeRef = useRef<GlobeMethods>()
  const hostRef = useRef<HTMLDivElement | null>(null)
  const pointerOffsetRef = useRef({ lat: 0, lng: 0 })
  const [dimensions, setDimensions] = useState({ width: 640, height: 640 })
  const [ready, setReady] = useState(false)
  const [coarsePointer, setCoarsePointer] = useState(false)
  const [reducedMotion, setReducedMotion] = useState(false)
  const [indiaStates, setIndiaStates] = useState<IndiaStatePolygon[]>([])
  const [indiaNationalBoundary, setIndiaNationalBoundary] = useState<IndiaNationalBoundaryPolygon | null>(null)

  const countries = useMemo<CountryPolygon[]>(() => {
    const topology = worldAtlas as unknown as { objects: { countries: unknown } }
    const collection = topojsonFeature(
      worldAtlas as never,
      topology.objects.countries as never,
    ) as unknown as GeoFeatureCollection

    return collection.features
      .filter((item) => isPolygonGeometry(item.geometry))
      .map((item) => ({
        ...item,
        displayName: String(item.properties?.name ?? 'Country'),
      }))
  }, [])

  const polygons = useMemo<GlobePolygon[]>(() => {
    if (!indiaStates.length) return countries

    const indiaLayers: GlobePolygon[] = [...indiaStates]
    if (indiaNationalBoundary) indiaLayers.push(indiaNationalBoundary)

    return [
      ...countries.filter(country => !isIndia(country)),
      ...indiaLayers,
    ]
  }, [countries, indiaNationalBoundary, indiaStates])

  useEffect(() => {
    let cancelled = false

    void Promise.all([
      fetchText(INDIA_STATES_RENDER_URL, 'India state map')
        .then(encoded => decodeCompressedGeoJson(encoded, EXPECTED_INDIA_STATE_COUNT)),
      Promise.all(
        INDIA_NATIONAL_BOUNDARY_RENDER_URLS.map((url, index) =>
          fetchText(url, `India national boundary chunk ${index + 1}`),
        ),
      )
        .then(parts => decodeCompressedGeoJson(parts.join(''), 1)),
    ])
      .then(([stateCollection, nationalCollection]) => {
        if (cancelled) return

        const states = stateCollection.features
          .filter(item => isPolygonGeometry(item.geometry))
          .map<IndiaStatePolygon>(item => ({
            ...item,
            properties: item.properties ?? {},
            displayName: String(item.properties?.st_nm ?? 'India'),
            isIndiaState: true,
          }))

        const nationalFeature = nationalCollection.features.find(item => isPolygonGeometry(item.geometry))
        if (states.length !== EXPECTED_INDIA_STATE_COUNT || !nationalFeature) {
          throw new Error('India map data is incomplete')
        }

        setIndiaStates(states)
        setIndiaNationalBoundary({
          ...nationalFeature,
          properties: nationalFeature.properties ?? {},
          displayName: String(nationalFeature.properties?.name ?? 'India'),
          isIndiaNationalBoundary: true,
        })
      })
      .catch(() => {
        if (!cancelled) {
          setIndiaStates([])
          setIndiaNationalBoundary(null)
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const host = hostRef.current
    if (!host || typeof window === 'undefined') return

    const pointerQuery = window.matchMedia('(pointer: coarse)')
    const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')

    const syncPreferences = () => {
      setCoarsePointer(pointerQuery.matches)
      setReducedMotion(motionQuery.matches)
    }

    const resize = () => {
      const rect = host.getBoundingClientRect()
      setDimensions({
        width: Math.max(260, Math.round(rect.width)),
        height: Math.max(260, Math.round(rect.height)),
      })
    }

    syncPreferences()
    resize()

    const observer = new ResizeObserver(resize)
    observer.observe(host)
    pointerQuery.addEventListener?.('change', syncPreferences)
    motionQuery.addEventListener?.('change', syncPreferences)

    return () => {
      observer.disconnect()
      pointerQuery.removeEventListener?.('change', syncPreferences)
      motionQuery.removeEventListener?.('change', syncPreferences)
    }
  }, [])

  useEffect(() => {
    if (!ready) return
    const globe = globeRef.current
    const controls = globe?.controls()
    if (!globe || !controls) return

    const radius = globe.getGlobeRadius()
    controls.enableDamping = true
    controls.dampingFactor = 0.075
    controls.enablePan = false
    controls.enableRotate = false
    controls.enableZoom = false
    controls.autoRotate = false
    controls.minDistance = radius * 1.45
    controls.maxDistance = radius * 4.3

    const basePov = coarsePointer ? MOBILE_POV : DESKTOP_POV
    globe.pointOfView(basePov, reducedMotion ? 0 : 900)
  }, [coarsePointer, ready, reducedMotion])

  useEffect(() => {
    if (!ready || reducedMotion) return

    let animationFrame = 0
    const startedAt = performance.now()

    const animate = (now: number) => {
      animationFrame = window.requestAnimationFrame(animate)
      if (document.hidden) return

      const globe = globeRef.current
      if (!globe) return

      const basePov = coarsePointer ? MOBILE_POV : DESKTOP_POV
      const progress = ((now - startedAt) % SWEEP_PERIOD_MS) / SWEEP_PERIOD_MS
      const angle = progress * Math.PI * 2
      const pointer = pointerOffsetRef.current

      const pov: GlobePov = {
        lat: basePov.lat + Math.sin(angle * 0.72) * SWEEP_MAX_LAT + pointer.lat,
        lng: normalizeLongitude(BENGALURU.lng + Math.sin(angle) * SWEEP_MAX_LNG + pointer.lng),
        altitude: basePov.altitude,
      }

      globe.pointOfView(pov, 0)
    }

    animationFrame = window.requestAnimationFrame(animate)
    return () => window.cancelAnimationFrame(animationFrame)
  }, [coarsePointer, ready, reducedMotion])

  useEffect(() => {
    const onVisibilityChange = () => {
      if (document.hidden) globeRef.current?.pauseAnimation()
      else globeRef.current?.resumeAnimation()
    }

    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => document.removeEventListener('visibilitychange', onVisibilityChange)
  }, [])

  const onPointerMove = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (coarsePointer || reducedMotion) return
    const host = hostRef.current
    if (!host) return

    const rect = host.getBoundingClientRect()
    const nx = Math.max(-1, Math.min(1, ((event.clientX - rect.left) / Math.max(1, rect.width)) * 2 - 1))
    const ny = Math.max(-1, Math.min(1, ((event.clientY - rect.top) / Math.max(1, rect.height)) * 2 - 1))

    pointerOffsetRef.current = {
      lng: nx * POINTER_MAX_LNG,
      lat: -ny * POINTER_MAX_LAT,
    }
  }, [coarsePointer, reducedMotion])

  const onPointerLeave = useCallback(() => {
    pointerOffsetRef.current = { lat: 0, lng: 0 }
  }, [])

  const polygonCapColor = useCallback((polygon: GlobePolygon) => {
    if (isIndiaNationalBoundaryPolygon(polygon)) return 'rgba(21, 201, 228, .035)'
    if (isIndiaStatePolygon(polygon)) return 'rgba(10, 116, 157, .42)'
    if (isIndia(polygon as CountryPolygon)) return 'rgba(11, 138, 180, .40)'
    return 'rgba(5, 36, 62, .72)'
  }, [])

  const polygonSideColor = useCallback((polygon: GlobePolygon) => {
    if (isIndiaNationalBoundaryPolygon(polygon)) return 'rgba(28, 207, 235, .14)'
    if (isIndiaStatePolygon(polygon)) return 'rgba(3, 47, 68, .20)'
    return 'rgba(2, 21, 38, .30)'
  }, [])

  const polygonStrokeColor = useCallback((polygon: GlobePolygon) => {
    if (isIndiaNationalBoundaryPolygon(polygon)) return '#67f2ff'
    if (isIndiaStatePolygon(polygon)) return 'rgba(73, 173, 201, .58)'
    if (isIndia(polygon as CountryPolygon)) return '#74eff8'
    return 'rgba(57, 156, 207, .45)'
  }, [])

  const polygonAltitude = useCallback((polygon: GlobePolygon) => {
    if (isIndiaNationalBoundaryPolygon(polygon)) return 0.014
    if (isIndiaStatePolygon(polygon)) return 0.007
    return 0.0025
  }, [])

  return (
    <div
      ref={hostRef}
      className="naksha-login-globe"
      aria-label="Bengaluru-centred global network globe"
      onPointerMove={onPointerMove}
      onPointerLeave={onPointerLeave}
    >
      <div className="naksha-login-globe-stage" aria-hidden="true">
        <Globe
          ref={globeRef}
          width={dimensions.width}
          height={dimensions.height}
          backgroundColor="rgba(0,0,0,0)"
          showAtmosphere
          atmosphereColor="#16c7e8"
          atmosphereAltitude={0.13}
          rendererConfig={{ antialias: !coarsePointer, alpha: true }}
          animateIn={!reducedMotion}
          polygonsData={polygons}
          polygonCapColor={(polygon: unknown) => polygonCapColor(polygon as GlobePolygon)}
          polygonSideColor={(polygon: unknown) => polygonSideColor(polygon as GlobePolygon)}
          polygonStrokeColor={(polygon: unknown) => polygonStrokeColor(polygon as GlobePolygon)}
          polygonAltitude={(polygon: unknown) => polygonAltitude(polygon as GlobePolygon)}
          polygonCapCurvatureResolution={coarsePointer ? 7 : 4}
          polygonsTransitionDuration={reducedMotion ? 0 : 260}
          arcsData={NETWORK_ARCS}
          arcStartLat="startLat"
          arcStartLng="startLng"
          arcEndLat="endLat"
          arcEndLng="endLng"
          arcColor={() => ['rgba(57, 220, 241, .28)', 'rgba(53, 230, 239, .96)']}
          arcStroke={0.06}
          arcAltitudeAutoScale={0.31}
          arcDashLength={0.18}
          arcDashGap={0.42}
          arcDashInitialGap={(arc: unknown) => (arc as NetworkArc).phase}
          arcDashAnimateTime={reducedMotion ? 0 : 3600}
          arcsTransitionDuration={0}
          pointsData={NETWORK_NODES}
          pointLat="lat"
          pointLng="lng"
          pointLabel={(node: unknown) => String((node as NetworkNode).name)}
          pointColor={(node: unknown) => (node as NetworkNode).kind === 'hub' ? '#f4ffff' : 'rgba(76, 220, 236, .86)'}
          pointAltitude={(node: unknown) => (node as NetworkNode).kind === 'hub' ? 0.028 : 0.011}
          pointRadius={(node: unknown) => (node as NetworkNode).kind === 'hub' ? 0.34 : 0.115}
          pointResolution={coarsePointer ? 7 : 10}
          pointsTransitionDuration={0}
          ringsData={reducedMotion ? [] : HUB_RING}
          ringLat="lat"
          ringLng="lng"
          ringColor={() => (time: number) => `rgba(70, 235, 244, ${Math.max(0, 0.72 - time)})`}
          ringMaxRadius={2.7}
          ringPropagationSpeed={1.35}
          ringRepeatPeriod={1450}
          labelsData={[BENGALURU]}
          labelLat="lat"
          labelLng="lng"
          labelText="name"
          labelColor={() => 'rgba(238, 254, 255, .98)'}
          labelAltitude={0.052}
          labelSize={0.46}
          labelDotRadius={0.075}
          labelResolution={2}
          onGlobeReady={() => setReady(true)}
          enablePointerInteraction={false}
          showPointerCursor={false}
        />
      </div>

      <div className="naksha-login-globe-chrome" aria-live="polite">
        <div className="naksha-login-globe-status">
          <span className="naksha-login-globe-pulse" aria-hidden="true" />
          <div>
            <strong>Bengaluru Global Network</strong>
            <small>
              {indiaStates.length === EXPECTED_INDIA_STATE_COUNT && indiaNationalBoundary
                ? 'OSM India national outline · 36 state / union territory boundaries · global routes converging on Bengaluru'
                : 'Animated global routes converging on the NakshaTech hub in Bengaluru'}
            </small>
          </div>
        </div>
      </div>

      <div className="naksha-login-globe-city-chip">
        <MapPin size={14} aria-hidden="true" />
        <span>Bengaluru · Global Hub</span>
      </div>

      <div className="naksha-login-globe-source">
        India national outline from supplied OSM GeoJSON · 36 state / UT boundaries · controlled India-facing sweep
      </div>
    </div>
  )
}
