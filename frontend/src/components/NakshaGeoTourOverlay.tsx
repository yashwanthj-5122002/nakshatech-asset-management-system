import { useEffect, useMemo, useRef, useState } from 'react'
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

type BoundaryLayer = 'country' | 'state' | 'district' | 'taluk'

type TourPolygon = BaseGeoFeature & {
  __layer: BoundaryLayer
  displayName: string
}

type GeoFeatureCollection = {
  type: 'FeatureCollection'
  features: BaseGeoFeature[]
}

type GeoBoundaryMetadata = {
  boundarySource?: string
  boundaryLicense?: string
  simplifiedGeometryGeoJSON?: string
}

type TourStage = 'world' | 'india' | 'karnataka' | 'bengaluru'

type TourPoint = {
  name: string
  lat: number
  lng: number
}

const INDIA_NUMERIC_ID = '356'
const WORLD_POV = { lat: 18, lng: 58, altitude: 1.58 }
const INDIA_POV = { lat: 21.0, lng: 78.7, altitude: 0.88 }
const KARNATAKA_POV = { lat: 15.25, lng: 75.7, altitude: 0.57 }
const BENGALURU_POV = { lat: 12.9716, lng: 77.5946, altitude: 0.34 }
const BENGALURU_POINT: TourPoint = { name: 'Bengaluru', lat: 12.9716, lng: 77.5946 }

function normalizeName(value: string) {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
}

function isPolygonGeometry(geometry: BaseGeoFeature['geometry'] | undefined): geometry is PolygonGeometry {
  return geometry?.type === 'Polygon' || geometry?.type === 'MultiPolygon'
}

function isCoordinate(value: unknown): value is [number, number] {
  return Array.isArray(value) && value.length >= 2 && typeof value[0] === 'number' && typeof value[1] === 'number'
}

function collectCoordinates(value: unknown, output: Array<[number, number]>) {
  if (isCoordinate(value)) {
    output.push([value[0], value[1]])
    return
  }
  if (!Array.isArray(value)) return
  for (const child of value) collectCoordinates(child, output)
}

function ringContainsPoint(ring: unknown, point: [number, number]) {
  if (!Array.isArray(ring)) return false
  const points = ring.filter(isCoordinate)
  if (points.length < 3) return false

  const [x, y] = point
  let inside = false
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const [xi, yi] = points[i]
    const [xj, yj] = points[j]
    const crosses = ((yi > y) !== (yj > y)) &&
      x < ((xj - xi) * (y - yi)) / ((yj - yi) || Number.EPSILON) + xi
    if (crosses) inside = !inside
  }
  return inside
}

function polygonCoordinatesContainPoint(polygon: unknown, point: [number, number]) {
  if (!Array.isArray(polygon) || !polygon.length) return false
  if (!ringContainsPoint(polygon[0], point)) return false
  for (let index = 1; index < polygon.length; index += 1) {
    if (ringContainsPoint(polygon[index], point)) return false
  }
  return true
}

function geometryContainsPoint(geometry: PolygonGeometry, point: [number, number]) {
  if (geometry.type === 'Polygon') {
    return polygonCoordinatesContainPoint(geometry.coordinates, point)
  }
  if (!Array.isArray(geometry.coordinates)) return false
  return geometry.coordinates.some((polygon) => polygonCoordinatesContainPoint(polygon, point))
}

function representativePoints(feature: BaseGeoFeature): Array<[number, number]> {
  const coordinates: Array<[number, number]> = []
  collectCoordinates(feature.geometry.coordinates, coordinates)
  if (!coordinates.length) return []

  let sumLng = 0
  let sumLat = 0
  let minLng = Number.POSITIVE_INFINITY
  let minLat = Number.POSITIVE_INFINITY
  let maxLng = Number.NEGATIVE_INFINITY
  let maxLat = Number.NEGATIVE_INFINITY

  for (const [lng, lat] of coordinates) {
    sumLng += lng
    sumLat += lat
    minLng = Math.min(minLng, lng)
    minLat = Math.min(minLat, lat)
    maxLng = Math.max(maxLng, lng)
    maxLat = Math.max(maxLat, lat)
  }

  return [
    [sumLng / coordinates.length, sumLat / coordinates.length],
    [(minLng + maxLng) / 2, (minLat + maxLat) / 2],
  ]
}

function childBelongsToParent(child: BaseGeoFeature, parent: BaseGeoFeature) {
  return representativePoints(child).some((point) => geometryContainsPoint(parent.geometry, point))
}

async function fetchJson<T>(url: string, timeoutMs = 12000): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: { Accept: 'application/json' },
      cache: 'force-cache',
    })
    if (!response.ok) throw new Error(`Boundary request failed (${response.status})`)
    return await response.json() as T
  } finally {
    window.clearTimeout(timeout)
  }
}

async function loadIndiaBoundary(
  admLevel: 'ADM1' | 'ADM2' | 'ADM3',
  layer: Exclude<BoundaryLayer, 'country'>,
) {
  const metadata = await fetchJson<GeoBoundaryMetadata>(
    `https://www.geoboundaries.org/api/current/gbOpen/IND/${admLevel}/`,
  )
  if (!metadata.simplifiedGeometryGeoJSON) throw new Error(`${admLevel} geometry unavailable`)

  const collection = await fetchJson<GeoFeatureCollection>(metadata.simplifiedGeometryGeoJSON, 16000)
  const features: TourPolygon[] = collection.features
    .filter((feature) => isPolygonGeometry(feature.geometry))
    .map((feature, index) => ({
      ...feature,
      id: feature.id ?? `IND-${admLevel}-${index}`,
      __layer: layer,
      displayName: String(feature.properties?.shapeName ?? feature.properties?.name ?? `${layer} ${index + 1}`),
    }))

  return {
    features,
    attribution: [metadata.boundarySource, metadata.boundaryLicense].filter(Boolean).join(' · '),
  }
}

function sleep(duration: number, cancelled: () => boolean) {
  return new Promise<void>((resolve) => {
    const started = performance.now()
    const tick = () => {
      if (cancelled() || performance.now() - started >= duration) {
        resolve()
        return
      }
      window.setTimeout(tick, Math.min(120, duration))
    }
    tick()
  })
}

function layerLabel(stage: TourStage) {
  if (stage === 'india') return 'INDIA · STATE BOUNDARIES'
  if (stage === 'karnataka') return 'KARNATAKA · DISTRICTS & TALUKS'
  if (stage === 'bengaluru') return 'BENGALURU · KARNATAKA'
  return 'NAKSHA GIS · GLOBAL VIEW'
}

function layerDescription(stage: TourStage, localDetailReady: boolean) {
  if (stage === 'india') return 'Locating India and revealing state / union territory boundaries'
  if (stage === 'karnataka') {
    return localDetailReady
      ? 'Karnataka highlighted with district and taluk / sub-district detail'
      : 'Karnataka highlighted · loading local administrative detail'
  }
  if (stage === 'bengaluru') return 'Focusing Bengaluru inside Karnataka'
  return 'Rotating world view · beginning geographic fly-in'
}

export function NakshaGeoTourOverlay({ onComplete }: { onComplete: () => void }) {
  const globeRef = useRef<GlobeMethods>()
  const hostRef = useRef<HTMLDivElement | null>(null)
  const onCompleteRef = useRef(onComplete)
  const [dimensions, setDimensions] = useState({ width: 1280, height: 760 })
  const [ready, setReady] = useState(false)
  const [stage, setStage] = useState<TourStage>('world')
  const [states, setStates] = useState<TourPolygon[]>([])
  const [districts, setDistricts] = useState<TourPolygon[]>([])
  const [taluks, setTaluks] = useState<TourPolygon[]>([])
  const [karnataka, setKarnataka] = useState<TourPolygon | null>(null)
  const [attribution, setAttribution] = useState('')
  const [fading, setFading] = useState(false)
  const [reducedMotion, setReducedMotion] = useState(false)
  const [compact, setCompact] = useState(false)

  useEffect(() => { onCompleteRef.current = onComplete }, [onComplete])

  const countries = useMemo<TourPolygon[]>(() => {
    const topology = worldAtlas as unknown as { objects: { countries: unknown } }
    const collection = topojsonFeature(
      worldAtlas as never,
      topology.objects.countries as never,
    ) as unknown as GeoFeatureCollection

    return collection.features
      .filter((feature) => isPolygonGeometry(feature.geometry))
      .map((feature) => ({
        ...feature,
        __layer: 'country' as const,
        displayName: String(feature.properties?.name ?? 'Country'),
      }))
  }, [])

  const india = useMemo(
    () => countries.find((country) => String(country.id ?? '').padStart(3, '0') === INDIA_NUMERIC_ID) ?? null,
    [countries],
  )

  const polygons = useMemo(() => {
    if (stage === 'world') return countries
    if (stage === 'india') return [...countries, ...states]
    return [...countries, ...states, ...districts, ...taluks]
  }, [countries, districts, stage, states, taluks])

  useEffect(() => {
    const host = hostRef.current
    if (!host || typeof window === 'undefined') return

    const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    const updatePreferences = () => setReducedMotion(motionQuery.matches)
    updatePreferences()

    const resize = () => {
      const rect = host.getBoundingClientRect()
      setDimensions({
        width: Math.max(320, Math.round(rect.width)),
        height: Math.max(320, Math.round(rect.height)),
      })
      setCompact(rect.width < 780)
    }
    resize()
    const observer = new ResizeObserver(resize)
    observer.observe(host)
    motionQuery.addEventListener?.('change', updatePreferences)

    return () => {
      observer.disconnect()
      motionQuery.removeEventListener?.('change', updatePreferences)
    }
  }, [])

  useEffect(() => {
    if (!ready) return
    let cancelled = false
    const isCancelled = () => cancelled

    const runTour = async () => {
      const globe = globeRef.current
      const controls = globe?.controls()
      if (!globe || !controls) {
        onCompleteRef.current()
        return
      }

      controls.enablePan = false
      controls.enableZoom = false
      controls.enableRotate = false
      controls.autoRotate = !reducedMotion
      controls.autoRotateSpeed = 0.38
      globe.pointOfView(WORLD_POV, reducedMotion ? 0 : 500)

      await sleep(reducedMotion ? 350 : 2200, isCancelled)
      if (cancelled) return

      controls.autoRotate = false
      setStage('india')
      globe.pointOfView(INDIA_POV, reducedMotion ? 0 : 1450)

      let stateRows: TourPolygon[] = []
      try {
        const result = await loadIndiaBoundary('ADM1', 'state')
        if (cancelled) return
        stateRows = result.features
        setStates(stateRows)
        setAttribution(result.attribution)
      } catch {
        stateRows = []
      }

      await sleep(reducedMotion ? 250 : 1200, isCancelled)
      if (cancelled) return

      const selectedKarnataka = stateRows.find((feature) => normalizeName(feature.displayName) === 'karnataka') ?? null
      setKarnataka(selectedKarnataka)
      setStage('karnataka')
      globe.pointOfView(KARNATAKA_POV, reducedMotion ? 0 : 1350)

      if (selectedKarnataka && !compact) {
        const [districtResult, talukResult] = await Promise.allSettled([
          loadIndiaBoundary('ADM2', 'district'),
          loadIndiaBoundary('ADM3', 'taluk'),
        ])
        if (cancelled) return

        if (districtResult.status === 'fulfilled') {
          setDistricts(
            districtResult.value.features.filter((feature) => childBelongsToParent(feature, selectedKarnataka)),
          )
          if (!attribution) setAttribution(districtResult.value.attribution)
        }
        if (talukResult.status === 'fulfilled') {
          setTaluks(
            talukResult.value.features.filter((feature) => childBelongsToParent(feature, selectedKarnataka)),
          )
          if (!attribution) setAttribution(talukResult.value.attribution)
        }
      }

      await sleep(reducedMotion ? 300 : 1800, isCancelled)
      if (cancelled) return

      setStage('bengaluru')
      globe.pointOfView(BENGALURU_POV, reducedMotion ? 0 : 1550)
      await sleep(reducedMotion ? 500 : 2400, isCancelled)
      if (cancelled) return

      setFading(true)
      await sleep(reducedMotion ? 80 : 720, isCancelled)
      if (!cancelled) onCompleteRef.current()
    }

    void runTour()
    return () => { cancelled = true }
  }, [compact, ready, reducedMotion])

  const polygonCapColor = (polygon: TourPolygon) => {
    if (polygon.__layer === 'country') {
      const isIndia = String(polygon.id ?? '').padStart(3, '0') === INDIA_NUMERIC_ID
      return isIndia && stage !== 'world' ? 'rgba(8, 116, 156, .48)' : 'rgba(5, 36, 62, .74)'
    }
    if (polygon.__layer === 'state') {
      const isKarnataka = normalizeName(polygon.displayName) === 'karnataka'
      if (isKarnataka && (stage === 'karnataka' || stage === 'bengaluru')) return 'rgba(13, 201, 228, .62)'
      return 'rgba(8, 73, 104, .24)'
    }
    if (polygon.__layer === 'district') return 'rgba(6, 96, 126, .12)'
    return 'rgba(2, 39, 61, .05)'
  }

  const polygonStrokeColor = (polygon: TourPolygon) => {
    if (polygon.__layer === 'country') {
      const isIndia = String(polygon.id ?? '').padStart(3, '0') === INDIA_NUMERIC_ID
      return isIndia && stage !== 'world' ? '#49e5f2' : 'rgba(57, 156, 207, .42)'
    }
    if (polygon.__layer === 'state') {
      return normalizeName(polygon.displayName) === 'karnataka'
        ? '#86f6ff'
        : 'rgba(81, 215, 235, .72)'
    }
    if (polygon.__layer === 'district') return 'rgba(159, 239, 247, .70)'
    return 'rgba(117, 205, 223, .40)'
  }

  const polygonAltitude = (polygon: TourPolygon) => {
    if (polygon.__layer === 'state') {
      return normalizeName(polygon.displayName) === 'karnataka' && stage !== 'india' ? 0.019 : 0.010
    }
    if (polygon.__layer === 'district') return 0.021
    if (polygon.__layer === 'taluk') return 0.022
    return String(polygon.id ?? '').padStart(3, '0') === INDIA_NUMERIC_ID && stage !== 'world' ? 0.006 : 0.002
  }

  const localDetailReady = districts.length > 0 || taluks.length > 0
  const points = stage === 'bengaluru' ? [BENGALURU_POINT] : []

  return (
    <div ref={hostRef} className={`naksha-geo-tour ${fading ? 'is-fading' : ''}`} aria-hidden="true">
      <div className="naksha-geo-tour-stage">
        <Globe
          ref={globeRef}
          width={dimensions.width}
          height={dimensions.height}
          backgroundColor="rgba(0,0,0,0)"
          showAtmosphere
          atmosphereColor="#16c7e8"
          atmosphereAltitude={0.13}
          rendererConfig={{ antialias: !compact, alpha: true }}
          animateIn={!reducedMotion}
          polygonsData={polygons}
          polygonCapColor={(polygon: unknown) => polygonCapColor(polygon as TourPolygon)}
          polygonSideColor={() => 'rgba(2, 21, 38, .28)'}
          polygonStrokeColor={(polygon: unknown) => polygonStrokeColor(polygon as TourPolygon)}
          polygonAltitude={(polygon: unknown) => polygonAltitude(polygon as TourPolygon)}
          polygonCapCurvatureResolution={compact ? 8 : 4}
          polygonsTransitionDuration={reducedMotion ? 0 : 320}
          pointsData={points}
          pointLat="lat"
          pointLng="lng"
          pointColor={() => '#f2ffff'}
          pointAltitude={0.032}
          pointRadius={0.28}
          pointResolution={10}
          labelsData={points}
          labelLat="lat"
          labelLng="lng"
          labelText="name"
          labelColor={() => 'rgba(232,253,255,.96)'}
          labelAltitude={0.045}
          labelSize={0.46}
          labelDotRadius={0.075}
          labelResolution={2}
          onGlobeReady={() => setReady(true)}
          enablePointerInteraction={false}
          showPointerCursor={false}
        />
      </div>

      <div className="naksha-geo-tour-status">
        <span className="naksha-geo-tour-pulse" />
        <div>
          <strong>{layerLabel(stage)}</strong>
          <small>{layerDescription(stage, localDetailReady)}</small>
        </div>
      </div>

      <div className="naksha-geo-tour-path">
        <span className={stage === 'world' ? 'active' : 'done'}>World</span>
        <i />
        <span className={stage === 'india' ? 'active' : stage === 'world' ? '' : 'done'}>India</span>
        <i />
        <span className={stage === 'karnataka' ? 'active' : stage === 'bengaluru' ? 'done' : ''}>Karnataka</span>
        <i />
        <span className={stage === 'bengaluru' ? 'active' : ''}>Bengaluru</span>
      </div>

      <div className="naksha-geo-tour-source">
        {attribution ? `Administrative boundaries: ${attribution}` : 'Administrative boundaries: geoBoundaries gbOpen'}
      </div>
    </div>
  )
}
